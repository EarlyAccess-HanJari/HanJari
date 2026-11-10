"""도착/위치 응답 순서가 달라도 지난 차량으로 되돌아가지 않는지 검사. 외부 API 호출 없음."""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import build_dataset as B
import collect as C
import serve as S


class ArrivalFreshness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "20261102"
        self.folder.mkdir()
        self.first = dict(staOrd="23", mkTm="2026-11-02 17:40:14.0", routeType="2",
                          plainNo1="서울70사5508", vehId1="100000014", sectOrd1="22", traTime1="96",
                          reride_Num1="53", rerdie_Div1="2", busType1="1",
                          plainNo2="서울75사3170", vehId2="100000069", sectOrd2="21", traTime2="219",
                          reride_Num2="19", rerdie_Div2="2", busType2="0")
        self.pos = dict(plainNo="서울70사5508", vehId="100000014", sectOrd="23", stopFlag="0", dataTm="20261102174035")

    def write(self, kind, stamp, items):
        f = self.folder / f"jr03_{kind}_{stamp}.json"
        C.write_snapshot(f, json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": items}}).encode())
        return f

    def prepare(self, first=None, positions=None):
        f = self.write("arr", "174039", [self.first if first is None else first])
        self.write("pos", "174039", [self.pos] if positions is None else positions)
        passed = S.exclude_departed(self.folder, dt.datetime(2026, 11, 2, 17, 40, 39))
        return passed, B.read_items(f)[0]

    def test_confirmed_departure_promotes_whole_second_vehicle_record(self):
        passed, item = self.prepare()
        self.assertEqual(passed, set())
        self.assertEqual((item["plainNo1"], item["vehId1"], item["reride_Num1"], item["traTime1"], item["sectOrd1"], item["busType1"]),
                         ("서울75사3170", "100000069", "19", "219", "21", "0"))
        self.assertEqual(item["plainNo2"], "")

    def test_promotion_never_inherits_missing_second_vehicle_fields(self):
        for missing in ("reride_Num2", "rerdie_Div2", "busType2"):
            with self.subTest(missing=missing):
                first = dict(self.first)
                first.pop(missing)
                _, item = self.prepare(first)
                self.assertEqual(item["plainNo1"], self.first["plainNo2"])
                self.assertIsNone(item.get(missing[:-1] + "1"))
                if missing != "busType2":
                    result = S.predict_live(0, log_dir=self.folder)[0]
                    self.assertIsNone(result["r_now"])
                    self.assertEqual(result["data_status"], "passenger_unavailable")

    def test_promotion_copies_second_count_when_first_count_field_is_missing(self):
        first = dict(self.first)
        first.pop("reride_Num1")
        _, item = self.prepare(first)
        self.assertEqual(item.get("reride_Num1"), "19")

    def test_recent_departure_survives_vehicle_missing_from_latest_position(self):
        self.write("arr", "174039", [self.first])
        self.write("pos", "174045", [dict(self.pos, dataTm="20261102174040")])
        self.write("pos", "174106", [dict(self.pos, plainNo="서울75사3170", vehId="100000069",
                                           sectOrd="21", dataTm="20261102174100")])
        got = S.predict_live(0, log_dir=self.folder)[0]
        self.assertEqual((got["plate"], got["r_now"]), ("서울75사3170", 19))

    def test_provider_time_can_prove_departure_before_arrival_file_was_collected(self):
        self.write("arr", "174039", [self.first])
        self.write("pos", "174036", [self.pos])
        got = S.predict_live(0, log_dir=self.folder)[0]
        self.assertEqual((got["plate"], got["r_now"]), ("서울75사3170", 19))

    def test_newer_wrapped_position_overrides_previous_departure(self):
        self.write("arr", "174039", [self.first])
        self.write("pos", "174045", [dict(self.pos, dataTm="20261102174040")])
        self.write("pos", "174106", [dict(self.pos, sectOrd="1", dataTm="20261102174100")])
        got = S.predict_live(0, log_dir=self.folder)[0]
        self.assertEqual(got["plate"], "서울70사5508")

    def test_after_midnight_position_is_used_for_previous_day_arrival(self):
        first = dict(self.first, mkTm="2026-11-02 23:59:40", traTime1="120", traTime2="180")
        self.write("arr", "235945", [first])
        next_day = self.folder.parent / "20261103"
        next_day.mkdir()
        position = dict(self.pos, dataTm="20261103000005")
        (next_day / "jr03_pos_000010.json").write_text(json.dumps(
            {"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": [position]}}))
        for folders in ([next_day, self.folder], [self.folder, next_day]):
            got = S.predict_live(0, log_dir=folders, reference_now=dt.datetime(2026, 11, 3, 0, 0, 10))[0]
            self.assertEqual((got["plate"], got["r_now"]), ("서울75사3170", 19))
            self.assertEqual(got["updated_at"], "2026-11-02T23:59:45+09:00")
            self.assertEqual(got["arrival_at"], "2026-11-03T00:02:40+09:00")

    def test_newer_empty_arrival_wins_regardless_of_folder_order(self):
        self.write("arr", "235945", [dict(self.first, mkTm="2026-11-02 23:59:40")])
        next_day = self.folder.parent / "20261103"
        next_day.mkdir()
        (next_day / "jr03_arr_000010.json").write_text(json.dumps(
            {"msgHeader": {"headerCd": "4"}, "msgBody": None}))
        self.assertEqual(S.predict_live(0, log_dir=[self.folder, next_day],
                                       reference_now=dt.datetime(2026, 11, 3, 0, 0, 10)), [])

    def test_combined_snapshot_clock_uses_the_latest_date(self):
        self.write("arr", "235945", [dict(self.first, mkTm="2026-11-02 23:59:40")])
        next_day = self.folder.parent / "20261103"
        next_day.mkdir()
        (next_day / "sb02_arr_000010.json").write_text(json.dumps(
            {"msgHeader": {"headerCd": "4"}, "msgBody": None}))
        stamp, files = S.latest_snapshot([self.folder, next_day])
        self.assertEqual(stamp, "000010")
        self.assertEqual(len(files), 2)

    def test_stopped_at_target_is_not_departure(self):
        passed, item = self.prepare(positions=[dict(self.pos, stopFlag="1")])
        self.assertFalse(passed)
        self.assertEqual(item["plainNo1"], self.first["plainNo1"])

    def test_old_mismatched_and_wrapped_positions_do_not_discard_bus(self):
        for changed in (dict(dataTm="20261102174000"), dict(vehId="999"), dict(plainNo="other"),
                        dict(sectOrd="1"), dict(dataTm="20261102174100")):
            with self.subTest(changed=changed):
                _, item = self.prepare(positions=[dict(self.pos, **changed)])
                self.assertEqual(item["plainNo1"], self.first["plainNo1"])

    def test_departed_both_buses_or_no_second_waits_for_new_arrival(self):
        second_pos = dict(self.pos, plainNo="서울75사3170", vehId="100000069")
        for first, positions in [(self.first, [self.pos, second_pos]), (dict(self.first, plainNo2="", vehId2="0"), [self.pos])]:
            passed, _ = self.prepare(first, positions)
            self.assertEqual(passed, {("jr03", "23")})

    def test_latest_position_can_exclude_bus_while_arrival_api_is_unchanged(self):
        self.write("arr", "174039", [self.first])
        self.write("pos", "174039", [dict(self.pos, sectOrd="22")])
        self.write("pos", "174106", [dict(self.pos, dataTm="20261102174105")])
        stamp, files = S.latest_snapshot(self.folder, "jr03")
        self.assertEqual(stamp, "174039")
        self.assertEqual(len(files), 3)  # 동일 시각 피처와 최신 통과 확인을 분리
        S.exclude_departed(self.folder, dt.datetime(2026, 11, 2, 17, 41, 6))
        self.assertEqual(B.read_items(self.folder / "jr03_arr_174039.json")[0]["vehId1"], "100000069")

    def test_stale_arrival_keeps_paired_position_and_skips_older_files(self):
        self.write("arr", "170000", [self.first])
        for stamp in ("165000", "170000", "174106"):
            self.write("pos", stamp, [self.pos])
        stamp, files = S.latest_snapshot(self.folder, "jr03", dt.datetime(2026, 11, 2, 17, 41, 10))
        self.assertEqual(stamp, "170000")
        self.assertEqual([f.name for f in files], ["jr03_arr_170000.json", "jr03_pos_174106.json", "jr03_pos_170000.json"])

    def test_snapshot_files_sorts_across_days_and_skips_bad_names(self):
        next_day = self.folder.parent / "20261103"
        next_day.mkdir()
        for path in (self.folder / "jr03_arr_235959.json", next_day / "jr03_arr_000001.json",
                     next_day / "jr03_arr_250000.json", next_day / "jr03_arr_12345.json", next_day / "sb02_arr_000002.json"):
            path.write_text("{}")
        found = [(when.strftime("%m%d%H%M%S"), path.name) for when, path in S._snapshot_files([self.folder, next_day], "jr03_arr_*.json")]
        self.assertEqual(found, [("1103000001", "jr03_arr_000001.json"), ("1102235959", "jr03_arr_235959.json")])

    def test_recorded_bus_switch_survives_missing_new_position_file(self):
        for route in B.STOPS:
            original = json.loads(next(S.SAMPLE.glob(f"{route}_arr_*.json")).read_text())
            for it in original["msgBody"]["itemList"]:
                it["mkTm"] = "2026-11-02 17:41:08.0"
                if route == "jr03" and it["staOrd"] == "23":
                    it.update(self.first, mkTm="2026-11-02 17:41:08.0", reride_Num1="54", traTime1="62", sectOrd1="23")
            (self.folder / f"{route}_arr_174133.json").write_text(json.dumps(original))
            shutil.copy(next(S.SAMPLE.glob(f"{route}_pos_*.json")), self.folder / f"{route}_pos_174133.json")
        newer = json.loads((self.folder / "jr03_arr_174133.json").read_text())
        for it in newer["msgBody"]["itemList"]:
            it["mkTm"] = "2026-11-02 17:41:54.0"
            for slot in "12":
                if it.get("vehId" + slot) == "100000069":
                    it["reride_Num" + slot] = "22"
            if it["staOrd"] == "23":
                it.update(plainNo1="서울75사3170", vehId1="100000069", reride_Num1="22", traTime1="53", sectOrd1="23", busType1="0",
                          plainNo2="", vehId2="0", reride_Num2="", rerdie_Div2="0")
        (self.folder / "jr03_arr_174200.json").write_text(json.dumps(newer))
        got = next(r for r in S.predict_live(3, log_dir=self.folder) if r["route"] == "jr03" and r["stop"] == "23")
        self.assertEqual((got["vehicle_id"], got["r_now"], got["updated"]), ("100000069", 22, "17:42:00"))
        self.assertEqual(got["arrival_at"], "2026-11-02T17:42:47+09:00")

    def test_expired_estimate_holds_instead_of_extending_on_every_read(self):
        row = dict(arrival_at="2026-11-02T17:41:50+09:00", arrival_stale=False, arrival_status="upcoming", r_now=53,
                   load_pred=53, load_10=50, load_90=55, p_board=0.8, level="여유 있음")
        now = dt.datetime(2026, 11, 2, 17, 41, 50)
        for offset in (0, 5, 20):
            got = copy.deepcopy(row)
            S.check_arrival(got, now + dt.timedelta(seconds=offset))
            self.assertEqual(got["arrival_status"], "checking")
            self.assertTrue(all(got[k] is None for k in ("r_now", "load_pred", "p_board")))

    def test_bus_waiting_just_before_stop_keeps_probability_while_eta_is_frozen(self):
        # 11-04 동대문: 앞 구간에서 4~5분 서 있는 동안 API 남은 시간이 5초에 멈춤 → 새 위치가 '바로 앞 구간'이면 '곧 도착' 유지
        now = dt.datetime(2026, 11, 2, 17, 41, 55)
        cases = (("17:41:30", "20261102174150", "upcoming"),   # 위치가 도착 정보보다 새 것
                 ("17:41:30", "20261102174120", "upcoming"),   # 위치가 조금 먼저 찍혀도 둘 다 60초 안
                 ("17:41:30", "20261102174040", "checking"),   # 위치 75초 전
                 ("17:40:50", "20261102174150", "checking"))   # 도착 정보 65초 전
        for made, pos_time, expected in cases:
            with self.subTest(made=made, pos_time=pos_time):
                first = dict(self.first, mkTm=f"2026-11-02 {made}.0", traTime1="5")
                for f in self.folder.glob("*.json"):
                    f.unlink()
                self.write("arr", "174135", [first])
                self.write("pos", "174152", [dict(self.pos, sectOrd="22", dataTm=pos_time)])
                got = S.predict_live(0, log_dir=self.folder, reference_now=now)[0]
                self.assertEqual((got["plate"], got["arrival_status"]), ("서울70사5508", expected))
                if expected == "upcoming":
                    self.assertEqual(got["r_now"], 53)
                    self.assertIsNotNone(got["p_board"])
                    self.assertEqual(got["arrival_at"], "2026-11-02T17:42:25+09:00")
                else:
                    self.assertIsNone(got["p_board"])

    def test_wrapped_or_far_position_does_not_extend_expired_estimate(self):
        first = dict(self.first, mkTm="2026-11-02 17:41:30.0", traTime1="5")
        for section in ("1", "20"):
            with self.subTest(section=section):
                for f in self.folder.glob("*.json"):
                    f.unlink()
                self.write("arr", "174135", [first])
                self.write("pos", "174152", [dict(self.pos, sectOrd=section, dataTm="20261102174150")])
                got = S.predict_live(0, log_dir=self.folder, reference_now=dt.datetime(2026, 11, 2, 17, 41, 55))[0]
                self.assertEqual(got["arrival_status"], "checking")

    def test_atomic_snapshot_does_not_publish_partial_file(self):
        path = self.folder / "jr03_arr_174039.json"
        C.write_snapshot(path, b"previous")
        real_replace = C.os.replace
        def inspect_before_replace(tmp, target):
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(Path(tmp).read_bytes(), b"complete new response")
            return real_replace(tmp, target)
        with patch.object(C.os, "replace", side_effect=inspect_before_replace):
            C.write_snapshot(path, b"complete new response")
        self.assertEqual(path.read_bytes(), b"complete new response")
        self.assertEqual(list(self.folder.glob("*.tmp")), [])

    def test_partial_route_outage_does_not_hide_working_route(self):
        for f in S.SAMPLE.glob("jr03_*.json"):
            target = self.folder.parent / S.SAMPLE.name
            target.mkdir(exist_ok=True)
            shutil.copy(f, target / f.name)
        got = S.predict_live(3, log_dir=target)
        self.assertTrue(got)
        self.assertEqual({r["route"] for r in got}, {"jr03"})

    def test_empty_new_day_preserves_original_date_and_clears_stale_counts(self):
        previous = self.folder.parent / S.SAMPLE.name
        previous.mkdir()
        for f in S.SAMPLE.glob("*.json"):
            shutil.copy(f, previous / f.name)
        got = S.predict_live(3, log_dir=[self.folder, previous], reference_now=dt.datetime(2026, 11, 2, 17, 40))
        self.assertEqual(len(got), 6)
        for row in got:
            self.assertTrue(row["updated_at"].startswith("2026-09-30"))
            self.assertTrue(row["arrival_stale"])
            self.assertIsNone(row["r_now"])
            self.assertIsNone(row["p_board"])
            self.assertEqual(row["prediction_status"], "collection_stale")

    def test_explicit_no_results_does_not_resurrect_an_older_arrival(self):
        for route in B.STOPS:
            for empty_body in ({"msgBody": {"itemList": None}}, {"msgBody": None}, {}):
                with self.subTest(route=route, body=empty_body):
                    for f in self.folder.glob("*.json"):
                        f.unlink()
                    (self.folder / f"{route}_arr_174039.json").write_text(json.dumps(
                        {"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": [self.first]}}))
                    empty = self.folder / f"{route}_arr_174106.json"
                    empty.write_text(json.dumps({"msgHeader": {"headerCd": "4"}, **empty_body}))
                    self.assertEqual(S.latest_snapshot(self.folder, route)[0], "174106")
                    self.assertEqual(S.predict_live(3, log_dir=self.folder), [])

    def test_invalid_envelope_is_skipped_without_crashing_other_route(self):
        for route in B.STOPS:
            shutil.copy(next(S.SAMPLE.glob(f"{route}_arr_*.json")), self.folder / f"{route}_arr_174039.json")
        for route in B.STOPS:
            invalid = self.folder / f"{route}_arr_174106.json"
            for payload in ({"msgHeader": None}, {"msgHeader": []},
                            {"msgHeader": {"headerCd": "4"}, "msgBody": "broken"}):
                with self.subTest(route=route, payload=payload):
                    invalid.write_text(json.dumps(payload))
                    self.assertEqual(S.latest_snapshot(self.folder, route)[0], "174039")
                    self.assertEqual(len(S.predict_live(3, log_dir=self.folder)), 6)
            invalid.unlink()


if __name__ == "__main__":
    unittest.main()


class ArrivalLabel(unittest.TestCase):
    """11-10: 앞 정류장 탑승분이 s 항목에서 빠지는 순간에야 반영되면, 빠진 직후의 같은 차 인원이 정답이다."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "20261102"
        self.folder.mkdir()

    def snap(self, stamp, items, positions):
        for kind, body in (("arr", items), ("pos", positions)):
            (self.folder / f"jr03_{kind}_{stamp}.json").write_text(json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": body}}))

    def item(self, stop, plate, vid, sect, n, made):
        return dict(staOrd=str(stop), mkTm=f"2026-11-02 {made}.0", routeType="2", plainNo1=plate, vehId1=vid, sectOrd1=str(sect),
                    traTime1="30", reride_Num1=str(n), rerdie_Div1="2", busType1="1")

    def label(self, after):
        a, b = ("서울70사5508", "100000014"), ("서울75사3170", "100000069")
        pos = lambda made: [dict(plainNo=a[0], vehId=a[1], sectOrd="22", stopFlag="1", dataTm=made),
                            dict(plainNo=b[0], vehId=b[1], sectOrd="20", stopFlag="0", dataTm=made)]
        self.snap("174039", [self.item(23, *a, 23, 20, "17:40:30"), self.item(24, *b, 21, 5, "17:40:30")], pos("20261102174035"))
        self.snap(after, [self.item(23, *b, 21, 5, "17:41:00"), self.item(24, *a, 24, 38, "17:41:00")],
                  [dict(p, sectOrd="23" if p["plainNo"] == a[0] else "20", dataTm="20261102174102") for p in pos("")])
        self.snap("174300", [self.item(23, *b, 23, 5, "17:42:55"), self.item(24, *b, 22, 5, "17:42:55")], pos("20261102174258"))
        return next(r["y"] for r in B.build("jr03", [str(self.folder)], tab={}) if r["stop"] == 23 and r["plate"] == a[0])

    def test_label_uses_count_seen_right_after_bus_leaves_stop_entry(self):
        self.assertEqual(self.label("174106"), 38)  # 27초 뒤 스냅샷: 앞 정류장 탑승 18명 반영

    def test_late_snapshot_keeps_last_count_seen_in_stop_entry(self):
        self.assertEqual(self.label("174130"), 20)  # 51초 뒤면 s 출발 갱신이 섞일 수 있어 쓰지 않음
