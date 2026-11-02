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
        self.write("arr", "174039", [self.first])
        empty = self.folder / "jr03_arr_174106.json"
        empty.write_text(json.dumps({"msgHeader": {"headerCd": "4"}, "msgBody": {"itemList": None}}))
        self.assertEqual(S.latest_snapshot(self.folder, "jr03")[0], "174106")
        self.assertEqual(S.predict_live(3, log_dir=self.folder), [])


if __name__ == "__main__":
    unittest.main()
