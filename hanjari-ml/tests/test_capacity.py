"""정원 팽창, 정원 클리핑, 이전 확률 기준 재사용에 대한 회귀 검사. 외부 API 호출 없음."""
import copy
import datetime as dt
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import serve as S
import train as T
import data_quality as DQ


class ConstantModel:
    def __init__(self, quantiles=False):
        self.quantiles = quantiles

    def predict(self, x):
        return np.zeros((len(x), len(T.QS))) if self.quantiles else np.zeros(len(x))


def fixture(load=20, stops=1):
    row = dict(route="jr03", bus_type="1", stop="23", plate="test", date="20261102",
               vehicle_id="123", source_schema=DQ.SCHEMA_VERSION, data_status="ok", source_updated="2026-11-02 10:00:00",
               time="10:00:00", eta=60, stops_away=stops, r_now=load, rule=load, off_csv=2,
               pos_dwell=0, pos_frac=0.5, q_pending=0, q_csv=0, stop_c=0, route_c=0,
               minute=600, holiday=False, weekday="월", is_peak=0)
    m = dict(feats=["r_now"], pt=ConstantModel(), qm=ConstantModel(True),
             m0=ConstantModel(), res0={True: np.array([-1., 0., 1.]), False: np.array([-1., 0., 1.])}, qs=T.QS)
    meta = dict(cats={}, qs=T.QS.tolist(), capacity_policy=T.capacity_policy(),
                thresholds=[[p, s, 0.8, False] for p in T.TARGET for s in T.SEGS])
    return row, m, meta


def result(row, m, meta, age=0):
    with patch.object(T, "features", return_value=pd.DataFrame([row])):
        return S.results([row], m, meta, 10, dt.datetime(2026, 11, 2, 10) + dt.timedelta(seconds=age),
                         S.MAX_AGE, lite=True)[0]


class CapacityRegression(unittest.TestCase):
    def setUp(self):
        self.policy = {"version": 1, "enabled": True, "validation_evidence": "test-only",
                       "vehicles": [{"route": "jr03", "plate": "test", "vehicle_id": "123", "capacity": 55, "evidence": "test-only"}]}
        patcher = patch.object(DQ, "boarding_policy", return_value=self.policy)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fixed_threshold_does_not_expand_with_observed_count(self):
        row, m, _ = fixture(53)
        d = pd.DataFrame([row])
        self.assertEqual(T.thresholds(d)[0, 10], 46)  # 55 - 10 - 1 + 2
        self.assertLess(T.predict(m, d)[1][0, 10], 0.3)

    def test_quantiles_above_capacity_are_preserved(self):
        row, m, _ = fixture(60)
        point, p, q = T.predict(m, pd.DataFrame([row]), quantiles=True)
        self.assertEqual(point[0], 60)
        self.assertTrue((q[0] == 60).all())
        self.assertLess(p[0, 0], 0.3)  # 클리핑 시 55 <= 56 으로 97.5%가 됐음

    def test_nearby_model_is_not_clipped_either(self):
        row, m, _ = fixture(60, stops=0)
        point, p, q = T.predict(m, pd.DataFrame([row]), quantiles=True)
        self.assertEqual(point[0], 60)
        self.assertGreater(q[0, -1], 55)
        self.assertEqual(p[0, 0], 0)

    def test_more_people_ahead_never_increase_probability(self):
        for stops in (0, 1):
            row, m, _ = fixture(53, stops)
            p = T.predict(m, pd.DataFrame([row]))[1]
            self.assertTrue((np.diff(p, axis=1) <= 0).all())

    def test_legacy_model_holds_and_preserves_arrival_and_raw_values(self):
        row, m, meta = fixture(53)
        del meta["capacity_policy"]
        meta["cap_obs"] = [["jr03", "1", 71]]
        got = result(row, m, meta)
        self.assertEqual(got["level"], "확률 보류")
        self.assertEqual(got["r_now"], 53)
        self.assertEqual(got["eta_sec"], 60)
        self.assertIsNone(got["p_board"])
        self.assertIsNone(got["load_pred"])
        self.assertEqual(T.cap("jr03", "1"), 54)

    def test_compatible_calibration_can_show_probability(self):
        row, m, meta = fixture()
        self.assertEqual(result(row, m, meta)["level"], "여유 있음")

    def test_changed_capacity_requires_revalidation(self):
        row, m, meta = fixture()
        with patch.dict(T.CAPACITY, {("jr03", "1"): 50}):
            self.assertEqual(result(row, m, meta)["level"], "확률 보류")

    def test_full_bus_shows_low_probability_instead_of_hold(self):
        # 11-04: 정원을 넘은 만차 버스는 보류하지 않고 확률(거의 0)로 '어려울 수 있음'
        row, m, meta = fixture(60)
        got = result(row, m, meta)
        self.assertEqual(got["level"], "어려울 수 있음")
        self.assertIsNotNone(got["p_board"])
        self.assertLess(got["p_board"], 0.3)

    def test_wide_range_alone_never_hides_probability(self):
        th = {(p, s): (0.8, False) for p in ("평소", "수업 직전") for s in T.SEGS}
        self.assertEqual(S.level(0.97, 13, 36, 1, False, True, th, 0)[0], "여유 있음")
        self.assertEqual(S.level(0.5, 13, 36, 1, False, True, th, 0)[0], "빠듯함")
        self.assertEqual(S.level(0.1, 0, 60, 1, False, True, th, 0)[0], "어려울 수 있음")

    def test_stale_reason_still_hides_countdown(self):
        row, m, meta = fixture(60)
        got = result(row, m, meta, age=181)
        self.assertEqual(got["level"], "확률 보류")
        self.assertTrue(got["arrival_stale"])
        self.assertEqual(got["prediction_status"], "collection_stale")

    def test_provider_and_collection_delays_are_added(self):
        row, m, meta = fixture()
        row["source_updated"] = "2026-11-02 09:59:15"
        got = result(row, m, meta, age=150)  # 수집 지연 150 + 제공 지연 45 = 195초
        self.assertEqual(got["prediction_status"], "source_stale")
        self.assertTrue(got["arrival_stale"])

    def test_export_metadata_alone_cannot_enable_unvalidated_predictions(self):
        row, m, meta = fixture()
        self.policy["enabled"] = False
        with patch.object(T, "predict", side_effect=AssertionError("must not infer")):
            got = result(row, m, meta)
        self.assertEqual(got["prediction_status"], "field_validation_pending")
        self.assertIsNone(got["p_board"])
        self.assertFalse(got["arrival_stale"])

    def test_verified_capacity_drives_probability_and_revalidation(self):
        row, m, meta = fixture(30)
        self.policy["vehicles"][0]["capacity"] = 33
        self.assertEqual(T.thresholds(pd.DataFrame([row]))[0, 10], 24)
        self.assertEqual(result(row, m, meta)["prediction_status"], "model_unverified")
        meta["capacity_policy"] = T.capacity_policy()
        self.assertEqual(result(row, m, meta)["level"], "어려울 수 있음")

    def test_unknown_vehicle_cannot_use_bus_type_as_verified_capacity(self):
        row, m, meta = fixture()
        row["vehicle_id"] = "456"
        self.assertEqual(result(row, m, meta)["prediction_status"], "capacity_unverified")

    def test_calibration_does_not_learn_display_threshold_from_unverified_or_hidden_rows(self):
        row, _, _ = fixture()
        rows = [row, dict(row, vehicle_id="unknown"), dict(row, r_now=60), dict(row, holiday=True), dict(row)]
        quantiles = np.full((5, len(T.QS)), 20.)
        quantiles[-1] = np.linspace(0, 80, len(T.QS))
        self.assertEqual(S.calibration_mask(pd.DataFrame(rows), quantiles, T.QS).tolist(), [True, False, True, False, True])

    def test_model_metadata_does_not_mutate_when_checked(self):
        row, m, meta = fixture()
        before = copy.deepcopy(meta)
        result(row, m, meta)
        self.assertEqual(meta, before)


if __name__ == "__main__":
    unittest.main()


class SurgeGain(unittest.TestCase):
    def test_surge_history_lowers_overconfident_probability(self):
        # 1정류장 전 20명, 모델은 그대로 20명 도착을 예상하지만 과거 같은 칸에선 +30~40명이 탔다(몰림)
        row, m, _ = fixture(20, stops=1)
        d = pd.DataFrame([row])
        base = T.predict(m, d)[1][0, 3]
        slot = int(T.gain_slot(d)[0])
        m["gain_q"] = {f"jr03|23|1|{slot}": np.linspace(30, 40, len(T.GAIN_Q)).tolist()}
        p = T.predict(m, d)[1]
        self.assertGreater(base, 0.9)
        self.assertAlmostEqual(p[0, 3], 0.2)               # 정원 54-3-1+2=52 → +32명까지만 탈 수 있음
        self.assertTrue((np.diff(p, axis=1) <= 1e-12).all())  # 앞사람이 늘면 확률은 줄기만
        self.assertLessEqual(p[0, 0], base + 1e-12)

    def test_missing_position_uses_dwelling_spread_for_nearby_bus(self):
        row, m, _ = fixture(50, stops=0)
        m["res0"] = {True: np.linspace(-20, 20, 41), False: np.zeros(41)}
        running, dwelling, unknown = (T.predict(m, pd.DataFrame([dict(row, pos_dwell=v)]))[1][0, 0] for v in (0, 1, np.nan))
        self.assertEqual(running, 1)
        self.assertLess(dwelling, 0.9)
        self.assertEqual(unknown, dwelling)  # 위치를 모르면 '주행'으로 과신하지 않는다

    def test_gain_table_needs_enough_history_and_skips_nearby_bus(self):
        rows = [dict(route="sb02", stop="32", stops_away=1, minute=525, eta=60, y=30 + i % 5, r_now=10) for i in range(40)]
        rows += [dict(route="sb02", stop="32", stops_away=0, minute=525, eta=60, y=30, r_now=10)] * 40
        rows += [dict(route="sb02", stop="31", stops_away=1, minute=525, eta=60, y=30, r_now=10)] * 5
        g = T.gain_table(pd.DataFrame(rows))
        self.assertEqual(list(g), ["sb02|32|1|17"])
        self.assertAlmostEqual(g["sb02|32|1|17"][0], 20)


class RepoPolicy(unittest.TestCase):
    def test_repo_policy_registers_practical_capacity_for_every_observed_vehicle(self):
        p = DQ.boarding_policy()
        self.assertTrue(p["enabled"] and p["validation_evidence"].strip())
        self.assertEqual(len(p["vehicles"]), 14)
        caps = {(v["route"], v["capacity"]) for v in p["vehicles"]}
        self.assertEqual(caps, {("sb02", 38), ("sb02", 60), ("jr03", 52), ("jr03", 54)})
        self.assertTrue(all(v["evidence"].startswith("docs/PRACTICAL_CAPACITY") for v in p["vehicles"]))


class OutageFallback(unittest.TestCase):
    """11-05: API·수집이 끊겨도 기존 필드(보류)는 그대로, fallback 에만 추정을 담는다."""
    def setUp(self):
        policy = {"version": 1, "enabled": True, "validation_evidence": "test-only",
                  "vehicles": [{"route": "jr03", "plate": "test", "vehicle_id": "123", "capacity": 55, "evidence": "test-only"}]}
        p = patch.object(DQ, "boarding_policy", return_value=policy)
        p.start()
        self.addCleanup(p.stop)

    def table(self):
        return {"jr03|23|wkd|20": {"p": [1.0] * 10 + [0.96] * 31, "n": 25, "gap": 8.0},
                "jr03|23|wkd": {"p": [1.0] * 41, "n": 300, "gap": 9.0}}

    def test_short_outage_keeps_hold_contract_and_adds_last_known_estimate(self):
        row, m, meta = fixture(20)
        row["eta"] = 600
        got = result(row, m, meta, age=300)
        self.assertEqual((got["level"], got["p_board"], got["r_now"], got["arrival_stale"]), ("확률 보류", None, None, True))
        fb = got["fallback"]
        self.assertEqual((fb["mode"], fb["r_now"], fb["level"]), ("last_known", 20, "여유 있음"))
        self.assertEqual(fb["arrival_at"], "2026-11-02T10:10:00+09:00")  # 마지막 정보의 도착 예정 그대로
        self.assertEqual(fb["age_sec"], 300)

    def test_long_outage_or_arrived_bus_uses_typical_table_with_strict_threshold(self):
        for eta, age in ((600, 900), (60, 300)):  # 15분 끊김 / 첫 버스가 이미 도착했을 시각
            with self.subTest(eta=eta, age=age):
                row, m, meta = fixture(20)
                row["eta"], meta["typical"] = eta, self.table()
                fb = result(row, m, meta, age=age)["fallback"]
                self.assertEqual((fb["mode"], fb["basis"], fb["headway_min"]), ("typical", "jr03|23|wkd|20", 8.0))
                self.assertEqual((fb["p_board"], fb["level"]), (0.96, "빠듯함"))  # 앞 10명, 0.96 < 0.98 → '여유' 아님

    def test_no_table_or_sunday_has_no_fallback(self):
        row, m, meta = fixture(20)
        self.assertIsNone(result(row, m, meta, age=900)["fallback"])
        meta["typical"] = self.table()
        sunday = dict(row, date="20261101", source_updated="2026-11-01 10:00:00", weekday="일", eta=600)
        for age in (300, 900):
            with patch.object(T, "features", return_value=pd.DataFrame([sunday])):
                got = S.results([sunday], m, meta, 10, dt.datetime(2026, 11, 1, 10) + dt.timedelta(seconds=age), S.MAX_AGE, lite=True)[0]
            self.assertIsNone(got["fallback"])

    def test_typical_table_counts_each_trip_once_and_falls_back_to_wider_cells(self):
        rows = [dict(trip=f"t{i}", arrive_time=f"10:{i:02d}:00", y=50 if i == 0 else 20, weekday="월", route="jr03", stop="23",
                     date="20261102", bus_type="1", plate="test", vehicle_id="123", off_csv=2) for i in range(25)]
        rows += [dict(rows[1], arrive_time="10:59:00", trip="t1")]  # 같은 운행의 다른 조회 — 한 번만 센다
        tab = T.typical_table(pd.DataFrame(rows))
        cell = tab["jr03|23|wkd|20"]
        self.assertEqual((cell["n"], cell["gap"], cell["p"][0], cell["p"][10]), (25, 1.0, 1.0, 0.96))
        self.assertIn("jr03|23|wkd|h10", tab)
        self.assertIn("jr03|23|wkd", tab)
