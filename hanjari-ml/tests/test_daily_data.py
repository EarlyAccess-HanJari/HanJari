"""운행 중 수집 누락과 정상적인 심야 공백을 구분한다. 외부 요청/학습/알림 없음."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import daily as D


class DailyCoverage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.logs = Path(tmp.name)
        self.folder = self.logs / "20261102"
        self.folder.mkdir()
        for obj, name, value in ((D.B, "LOG", self.logs), (D.C, "SCHED", self.logs / "schedule.json")):
            p = patch.object(obj, name, value)
            p.start(); self.addCleanup(p.stop)

    def snapshots(self, first=7*60, last=22*60, code="0"):
        for route in D.B.STOPS:
            for minute in range(first, last+1, 5):
                stamp = dt.datetime(2026,11,2) + dt.timedelta(minutes=minute)
                (self.folder / f"{route}_arr_{stamp:%H%M%S}.json").write_text(json.dumps(
                    {"msgHeader": {"headerCd": code}, "msgBody": {"itemList": []}}))

    def test_normal_night_without_buses_is_not_missing_daytime_data(self):
        self.snapshots()
        self.assertEqual(D.check_data("20261102")[0], "OK")

    def test_collection_stopping_before_end_of_service_cannot_pass(self):
        self.snapshots(last=18*60+30)
        status, details = D.check_data("20261102")
        self.assertEqual(status, "FAIL")
        self.assertIn("210.0분", details)

    def test_missing_start_of_day_cannot_pass(self):
        self.snapshots(first=12*60)
        self.assertEqual(D.check_data("20261102")[0], "FAIL")

    def test_saved_service_window_excludes_hours_when_buses_do_not_run(self):
        D.C.SCHED.write_text(json.dumps({route: {"wkd": [8*60, 19*60]} for route in D.B.STOPS}))
        self.snapshots(first=8*60-D.C.PAD,last=19*60+D.C.PAD)
        self.assertEqual(D.check_data("20261102")[0], "OK")

    def test_valid_no_results_is_not_provider_failure_and_bad_header_is(self):
        self.snapshots(code="4")
        self.assertEqual(D.check_data("20261102")[0], "OK")
        path = next(self.folder.glob("*.json"))
        for body in ("broken", '{"msgHeader":null}', '{"msgHeader":{"headerCd":"7"}}',
                     '{"msgHeader":{"headerCd":"0"},"msgBody":null}'):
            path.write_text(body)
            self.assertFalse(D.header_ok(path))


if __name__ == "__main__":
    unittest.main()
