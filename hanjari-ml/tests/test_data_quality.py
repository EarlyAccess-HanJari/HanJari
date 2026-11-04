"""실제 샘플 API 형식으로 결측·식별·시각·캐시 경로 회귀 검증. API 호출 없음."""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import build_dataset as B
import data_quality as DQ
import serve as S
import train as T


class SourceQuality(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 2, 10)
        self.item = dict(rerdie_Div1="2", reride_Num1="0", routeType="2", mkTm="2026-11-02 10:00:00", plainNo1="test", vehId1="123")

    def test_zero_is_real_only_when_count_division_is_two(self):
        self.assertEqual(DQ.valid_count(self.item, self.now), 0)
        for div in ("0", "4", None):
            self.item["rerdie_Div1"] = div
            self.assertIsNone(DQ.valid_count(self.item, self.now))

    def test_unknown_route_and_negative_or_fractional_count_are_not_passengers(self):
        for value in (-1, "unknown", "2.5", None, True):
            self.item["reride_Num1"] = value
            self.assertIsNone(DQ.passenger_count(self.item))
        self.item.update(reride_Num1="21", routeType="6")
        self.assertIsNone(DQ.passenger_count(self.item))

    def test_second_bus_is_independently_checked(self):
        self.item.update(rerdie_Div2="0", reride_Num2="0", plainNo2="next", vehId2="456")
        self.assertIsNone(DQ.valid_count(self.item, self.now, "2"))
        self.item["rerdie_Div2"] = "2"
        self.assertEqual(DQ.valid_count(self.item, self.now, "2"), 0)

    def test_source_timestamp_not_fresh_collection_controls_validity(self):
        self.item["mkTm"] = "2026-11-02 09:56:59"
        self.assertEqual(DQ.source_issue(self.item, self.now), "source_stale")
        self.item["mkTm"] = "2026-11-02 10:01:00"
        self.assertEqual(DQ.source_issue(self.item, self.now), "source_stale")
        self.item["mkTm"] = "unknown"
        self.assertEqual(DQ.source_issue(self.item, self.now), "source_time_unknown")
        self.assertEqual(DQ.source_time("20261102100000"), self.now)

    def test_malformed_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            with patch.object(DQ, "POLICY_PATH", path):
                for data in (None, {}, {"version": 1, "enabled": True, "vehicles": []},
                             {"version": 1, "enabled": True, "vehicles": [1]}):
                    path.write_text(json.dumps(data))
                    self.assertFalse(DQ.boarding_policy()["enabled"])

    def test_legacy_dataset_and_missing_values_rejected_before_feature_generation(self):
        with self.assertRaisesRegex(ValueError, "재빌드"):
            T.features(pd.DataFrame([{"r_now": 0}]))
        with self.assertRaisesRegex(ValueError, "인원 입력"):
            T.features(pd.DataFrame([{"source_schema": DQ.SCHEMA_VERSION, "data_status": "ok", "r_now": None}]))

    def test_missing_endpoint_cannot_become_zero_training_label(self):
        end = dict(self.item, staOrd="23", sectOrd1="23", rerdie_Div1="0", reride_Num1="0")
        after = dict(end, plainNo1="next", vehId1="456")
        snapshots = [(self.now, {23: end}), (self.now + dt.timedelta(seconds=27), {23: after})]
        with patch.object(B, "snapshots", return_value=snapshots):
            self.assertEqual(list(B.segments("jr03")), [])
            end["rerdie_Div1"] = "2"
            self.assertEqual(len(list(B.segments("jr03"))), 1)  # 실제 0명은 유효 정답

    def test_short_history_folds_preserve_dates_not_just_clock_time(self):
        d = pd.DataFrame([{"date": date, "time": hour, "trip": f"{date}-{hour}"}
                          for date in ("20261030", "20261031") for hour in ("09:00:00", "10:00:00", "11:00:00")])
        for tr, te in T.folds(d):
            self.assertLess((tr.date + tr.time).max(), (te.date + te.time).min())

    def test_archived_legacy_cache_is_preserved_when_rebuild_impossible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "days").mkdir()
            cache = root / "days/20260930_jr03.json"
            before = '{"files": [4], "n": 4, "ev": []}'
            cache.write_text(before)
            dataset = root / "dataset.csv"
            dataset.write_text("previous data")
            with patch.object(B, "OUT", root), patch.object(B, "LOG", root / "absent"):
                with self.assertRaisesRegex(RuntimeError, "원본 archive 복구"):
                    B.main()
            self.assertEqual(cache.read_text(), before)
            self.assertEqual(dataset.read_text(), "previous data")


MODEL_KEYS = {"load_pred", "load_10", "load_90", "p_board", "level", "reason"}


def arrival(rows):
    """모델 출력만 뺀 응답 — 선택 필드가 빠져 특징값이 바뀌면 확률은 조금 달라질 수 있지만 도착·상태는 그대로여야 한다."""
    return [{k: v for k, v in r.items() if k not in MODEL_KEYS} for r in rows]


class SnapshotIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / S.SAMPLE.name
        shutil.copytree(S.SAMPLE, self.folder)
        self.arr = next(self.folder.glob("jr03_arr_*.json"))
        self.body = json.loads(self.arr.read_text())
        self.item = next(i for i in self.body["msgBody"]["itemList"] if i["staOrd"] == "23")

    def run_sample(self):
        self.arr.write_text(json.dumps(self.body))
        real = T.predict

        def guarded(m, d, **kw):  # 다른 정류장은 확률을 내도 되지만, 보류된 행은 모델에 들어가면 안 된다
            assert not ((d.route == "jr03") & (d.stop.astype(str) == "23")).any(), "held rows must not infer"
            return real(m, d, **kw)
        with patch.object(T, "predict", side_effect=guarded):
            results = S.predict_live(10, log_dir=self.folder)
        self.assertEqual(len(results), 6)
        return next(r for r in results if r["route"] == "jr03" and r["stop"] == "23")

    def test_missing_count_retains_arrival_but_never_reports_empty_bus(self):
        self.item.update(rerdie_Div1="0", reride_Num1="0")
        got = self.run_sample()
        self.assertIsNone(got["r_now"])
        self.assertIsNone(got["p_board"])
        self.assertIsNone(got["load_pred"])
        self.assertEqual(got["prediction_status"], "passenger_unavailable")
        self.assertGreaterEqual(got["eta_sec"], 0)
        self.assertFalse(got["arrival_stale"])

    def test_stale_provider_timestamp_hides_countdown(self):
        self.item["mkTm"] = "2026-09-30 01:00:00"
        got = self.run_sample()
        self.assertEqual(got["prediction_status"], "source_stale")
        self.assertTrue(got["arrival_stale"])
        self.item["rerdie_Div1"] = "0"
        self.assertTrue(self.run_sample()["arrival_stale"])  # 인원 결측과 도착 정보 노후화는 독립

    def test_vehicle_mismatch_cannot_enter_prediction_or_training_label(self):
        self.item["vehId1"] = "999"
        got = self.run_sample()
        self.assertEqual(got["prediction_status"], "vehicle_mismatch")
        stamp, items = next(B.snapshots("jr03", [str(self.folder)]))
        self.assertIsNone(DQ.valid_count(items[23], stamp))

    def test_disagreeing_counts_for_same_vehicle_are_held(self):
        other = copy.deepcopy(self.item)
        other.update(staOrd="24", reride_Num1=str(int(self.item["reride_Num1"]) + 1))
        self.body["msgBody"]["itemList"].append(other)
        self.assertEqual(self.run_sample()["prediction_status"], "passenger_conflict")

    def test_new_arrival_does_not_wait_for_position_but_rejects_error_payloads(self):
        stamp, _ = S.latest_snapshot(self.folder)
        (self.folder / "jr03_arr_235900.json").write_text(self.arr.read_text())
        self.assertEqual(S.latest_snapshot(self.folder)[0], "235900")
        for route in B.STOPS:
            for kind in ("arr", "pos"):
                (self.folder / f"{route}_{kind}_235900.json").write_text('{"msgHeader":{"headerCd":"7"},"msgBody":{"itemList":[]}}')
        self.assertEqual(S.latest_snapshot(self.folder)[0], stamp)

    def test_position_outage_does_not_freeze_arrival(self):
        for f in self.folder.glob("*_pos_*.json"):
            f.unlink()
        self.assertEqual(len(S.predict_live(10, log_dir=self.folder)), 6)

    def test_no_valid_arrival_is_error_instead_of_no_buses(self):
        for f in self.folder.glob("*_arr_*.json"):
            f.unlink()
        with self.assertRaisesRegex(RuntimeError, "스냅샷이 없음"):
            S.predict_live(10, log_dir=self.folder)

    def test_route_snapshots_keep_separate_ages(self):
        original = dt.datetime.strptime(self.folder.name + self.arr.stem.rsplit("_", 1)[-1], "%Y%m%d%H%M%S")
        newer = original + dt.timedelta(seconds=181)
        for item in self.body["msgBody"]["itemList"]:
            item["mkTm"] = newer.isoformat(sep=" ")
        (self.folder / f"jr03_arr_{newer:%H%M%S}.json").write_text(json.dumps(self.body))
        shutil.copy(next(self.folder.glob("jr03_pos_*.json")), self.folder / f"jr03_pos_{newer:%H%M%S}.json")
        results = S.predict_live(10, log_dir=self.folder)
        for r in results:
            self.assertEqual(r["arrival_stale"], r["route"] == "sb02")
            if r["route"] == "sb02":
                self.assertEqual(r["prediction_status"], "collection_stale")

    def test_position_features_survive_valid_compact_timestamp(self):
        _, meta = S.load(True)
        rows = B.build("jr03", [str(self.folder)], open_=True, tab=meta["tab_d"]["jr03"])
        self.assertTrue(any(r["pos_sect"] is not None for r in rows))

    def test_optional_arrival_fields_cannot_fail_other_stops_or_route(self):
        baseline = S.predict_live(10, log_dir=self.folder)
        for route, stop in (("sb02", "30"), ("jr03", "23")):
            path = next(self.folder.glob(f"{route}_arr_*.json"))
            original = path.read_bytes()
            for field in ("plainNo1", "plainNo2", "busType1", "traTime2"):
                for mode in ("missing", "null"):
                    with self.subTest(route=route, field=field, mode=mode):
                        body = json.loads(original)
                        item = next(i for i in body["msgBody"]["itemList"] if i["staOrd"] == stop)
                        if mode == "missing":
                            item.pop(field, None)
                        else:
                            item[field] = None
                        path.write_text(json.dumps(body))
                        result = S.predict_live(10, log_dir=self.folder)
                        unaffected = lambda rows: [r for r in rows if (r["route"],r["stop"]) != (route,stop)]
                        self.assertEqual(unaffected(result), unaffected(baseline))
                        if field == "traTime2":  # 다음 버스 값만 함께 비고 이번 버스 도착은 그대로
                            no_next = lambda rows: [{k: v for k, v in r.items() if k != "eta2_sec"} for r in arrival(rows)]
                            self.assertEqual(no_next(result), no_next(baseline))
                            self.assertIsNone(next(r for r in result if (r["route"], r["stop"]) == (route, stop))["eta2_sec"])
                        elif field != "plainNo1":
                            self.assertEqual(arrival(result), arrival(baseline))
                        else:
                            self.assertFalse(any(r["route"] == route and r["stop"] == stop and r["r_now"] is not None for r in result))
                        path.write_bytes(original)

    def test_incomplete_position_cannot_fail_arrival_response(self):
        baseline = S.predict_live(10, log_dir=self.folder)
        for route in B.STOPS:
            path = next(self.folder.glob(f"{route}_pos_*.json"))
            original = path.read_bytes()
            for field in ("plainNo", "sectOrd", "stopFlag"):
                for mode in ("missing", "null"):
                    with self.subTest(route=route, field=field, mode=mode):
                        body = json.loads(original)
                        for item in body["msgBody"]["itemList"]:
                            if mode == "missing":
                                item.pop(field, None)
                            else:
                                item[field] = None
                        path.write_text(json.dumps(body))
                        self.assertEqual(arrival(S.predict_live(10, log_dir=self.folder)), arrival(baseline))
                        path.write_bytes(original)

    def test_malformed_identity_and_noninteger_arrival_never_become_valid_counts(self):
        baseline = S.predict_live(10, log_dir=self.folder)
        for route, stop in (("sb02", "30"), ("jr03", "23")):
            path = next(self.folder.glob(f"{route}_arr_*.json"))
            original = path.read_bytes()
            for field in ("vehId1", "plainNo1", "staOrd", "sectOrd1", "traTime1"):
                for value in ([], {}, True, 1.5, float("inf")):
                    with self.subTest(route=route, field=field, value=value):
                        body = json.loads(original)
                        item = next(i for i in body["msgBody"]["itemList"] if i["staOrd"] == stop)
                        item[field] = value
                        path.write_text(json.dumps(body))
                        result = S.predict_live(10, log_dir=self.folder)
                        self.assertFalse(any(r["route"] == route and r["stop"] == stop and r["r_now"] is not None for r in result))
                        self.assertEqual([r for r in result if r["route"] != route], [r for r in baseline if r["route"] != route])
                        path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
