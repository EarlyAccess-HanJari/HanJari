"""탑승 예측 보류/운행시간 외에도 불필요한 모델 의존으로 안내가 중단되지 않는지 검사."""
import datetime as dt
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import serve as S


class ServingAvailability(unittest.TestCase):
    def test_disabled_predictions_keep_arrivals_without_model_files(self):
        with tempfile.TemporaryDirectory() as absent:
            with patch.object(S.DQ, "boarding_policy", return_value={"enabled": False, "vehicles": []}), \
                 patch.object(S, "load", side_effect=AssertionError("unneeded model load")):
                rows = S.predict_live(3, log_dir=S.SAMPLE, model_dir=absent)
            self.assertEqual(len(rows), 6)
            self.assertTrue(all(r["p_board"] is None and r["load_pred"] is None for r in rows))
            self.assertTrue(any(r["r_now"] is not None for r in rows))

    def test_outside_service_returns_no_current_buses_without_building_predictions(self):
        with patch.object(S.C, "load_sched", return_value={}), patch.object(S.C, "allowed", return_value=False), \
             patch.object(S, "predict_live", side_effect=AssertionError("no buses operating")):
            self.assertEqual(S.predict_latest(3), [])
            with self.assertRaises(ValueError):
                S.predict_latest(-1)

    def test_only_active_route_is_returned_when_service_hours_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs = Path(tmp)
            (logs / dt.datetime.now(S.KST).strftime("%Y%m%d")).mkdir()
            with patch.object(S.B, "LOG", logs), patch.object(S.C, "load_sched", return_value={}), \
                 patch.object(S.C, "allowed", side_effect=lambda now, route, sched: route == "sb02"), \
                 patch.object(S, "predict_live", return_value=[{"route": "sb02"}, {"route": "jr03"}]):
                self.assertEqual(S.predict_latest(3), [{"route": "sb02"}])

    def test_eligible_predictions_still_run_after_deferred_imports(self):
        import train as T
        rows = [r for route in S.B.STOPS for r in S.B.build(route, [str(S.SAMPLE)], open_=True, tab={})]
        now = dt.datetime.strptime(rows[0]["date"] + rows[0]["time"], "%Y%m%d%H:%M:%S")
        def predict(model, data, quantiles):
            return np.full(len(data), 10), np.full((len(data),41), .7), np.tile([8,10,12], (len(data),1))
        with patch.object(S, "probability_issue", return_value=None), \
             patch.object(T, "features", side_effect=lambda data,cats: data.assign(is_peak=0,holiday=False,weekday="월")), \
             patch.object(T, "predict", side_effect=predict) as infer, patch.object(S, "level", return_value=("빠듯함","test")):
            got = S.results(rows, object(), {"cats":{},"qs":[.1,.5,.9],"thresholds":[]}, 3, now, S.MAX_AGE, lite=True)
        infer.assert_called_once()
        self.assertTrue(any(row["p_board"]==.7 and row["load_pred"]==10 for row in got))


if __name__ == "__main__":
    unittest.main()
