"""외부 API를 호출하지 않고 장애·재시작·복구·한도를 확인한다."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import collect as C
import watchdog as W


class CollectorRecovery(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name)
        self.now = dt.datetime(2026, 11, 2, 17, 40, tzinfo=C.KST)
        for obj, name, value in [(C, "LOG", self.log), (C, "SCHED", self.log / "schedule.json"), (W.B, "LOG", self.log)]:
            p = patch.object(obj, name, value); p.start(); self.addCleanup(p.stop)

    def test_failed_request_survives_restart_and_backoff_then_recovers(self):
        budget = C.UsageBudget(["test-key"], self.now)
        state = {}
        with patch.object(C, "fetch", side_effect=HTTPError("url", 503, "unavailable", {}, None)) as fetch:
            C.attempt("jr03", "arr", "test-key", self.now, budget, state, {})
            C.attempt("jr03", "arr", "test-key", self.now + dt.timedelta(seconds=27), budget, state, {})
            self.assertEqual(fetch.call_count, 1)
        restored = C.UsageBudget(["test-key"], self.now)
        self.assertEqual(restored.used[restored.ids["test-key"]]["arr"], 1)
        self.assertNotIn("test-key", restored.path.read_text())
        good = json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": []}}).encode()
        with patch.object(C, "fetch", return_value=good):
            C.attempt("jr03", "arr", "test-key", self.now + dt.timedelta(seconds=61), restored, state, {})
        self.assertEqual(state["endpoints"]["jr03:arr"]["status"], "ok")
        self.assertEqual(len(list((self.log / "20261102").glob("jr03_arr_*.json"))), 1)
        self.assertEqual(restored.used[restored.ids["test-key"]]["arr"], 2)

    def test_budget_is_separate_by_key_service_and_calendar_day(self):
        budget = C.UsageBudget(["key-a", "key-b"], self.now)
        with patch.object(C, "LIMIT", 1):
            self.assertTrue(budget.reserve("key-a", "arr"))
            self.assertFalse(budget.reserve("key-a", "arr"))
            self.assertTrue(budget.reserve("key-a", "pos"))
            self.assertTrue(budget.reserve("key-b", "arr"))
            new = C.UsageBudget(["key-a", "key-b"], self.now + dt.timedelta(days=1))
            self.assertTrue(new.reserve("key-a", "arr"))

    def test_exhausted_budget_never_sends_a_request(self):
        budget = C.UsageBudget(["key"], self.now)
        state = {}
        with patch.object(C, "LIMIT", 0), patch.object(C, "fetch") as fetch:
            C.attempt("jr03", "arr", "key", self.now, budget, state, {})
        fetch.assert_not_called()
        self.assertEqual(state["endpoints"]["jr03:arr"]["status"], "budget_exhausted")

    def test_legacy_errors_count_in_migration_and_corruption_does_not_reset(self):
        (self.log / "collect.log").write_text("2026-11-02T17:40:00+09:00 jr03 arr <HTTPError 503>\n" * 20)
        budget = C.UsageBudget(["key"], self.now)
        self.assertGreaterEqual(budget.used[budget.ids["key"]]["arr"], 20)
        budget.path.write_text("broken")
        with self.assertRaises(ValueError):
            C.UsageBudget(["key"], self.now)

    def test_live_collector_in_upstream_outage_does_not_trigger_restart(self):
        (self.log / "collector_state.json").write_text(json.dumps({"heartbeat": self.now.isoformat()}))
        with patch.object(W.C, "allowed", return_value=True), patch.object(W.C, "load_sched", return_value={}):
            problems, restart = W.check(self.now.replace(tzinfo=None))
            self.assertTrue(problems)
            self.assertFalse(restart)
            _, restart = W.check((self.now + dt.timedelta(minutes=11)).replace(tzinfo=None))
            self.assertTrue(restart)


if __name__ == "__main__":
    unittest.main()
