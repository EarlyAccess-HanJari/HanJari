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


class ConstantModel:
    def __init__(self, quantiles=False):
        self.quantiles = quantiles

    def predict(self, x):
        return np.zeros((len(x), len(T.QS))) if self.quantiles else np.zeros(len(x))


def fixture(load=20, stops=1):
    row = dict(route="jr03", bus_type="1", stop="23", plate="test", date="20261102",
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
        self.assertEqual(T.cap("jr03", "1"), 55)

    def test_compatible_calibration_can_show_probability(self):
        row, m, meta = fixture()
        self.assertEqual(result(row, m, meta)["level"], "여유 있음")

    def test_changed_capacity_requires_revalidation(self):
        row, m, meta = fixture()
        with patch.dict(T.CAPACITY, {("jr03", "1"): 54}):
            self.assertEqual(result(row, m, meta)["level"], "확률 보류")

    def test_excess_raw_count_holds_even_with_current_calibration(self):
        row, m, meta = fixture(60)
        got = result(row, m, meta)
        self.assertEqual(got["level"], "확률 보류")
        self.assertIn("차내 인원 정보", got["reason"])

    def test_stale_reason_still_hides_countdown(self):
        row, m, meta = fixture(60)
        got = result(row, m, meta, age=181)
        self.assertEqual(got["level"], "확률 보류")
        self.assertIn("전 것", got["reason"])

    def test_model_metadata_does_not_mutate_when_checked(self):
        row, m, meta = fixture()
        before = copy.deepcopy(meta)
        result(row, m, meta)
        self.assertEqual(meta, before)


if __name__ == "__main__":
    unittest.main()
