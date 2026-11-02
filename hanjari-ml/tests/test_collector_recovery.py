"""외부 API를 호출하지 않고 장애·재시작·복구·한도를 확인한다."""
import datetime as dt
import io
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
        (self.log / "collect.log").write_text("".join(f"{self.now + dt.timedelta(seconds=30*i):%Y-%m-%dT%H:%M:%S}+09:00 jr03 arr HTTPError 503\n" for i in range(20)))
        budget = C.UsageBudget(["key"], self.now)
        self.assertEqual(budget.used[budget.ids["key"]]["arr"], 0)
        self.assertEqual(budget.prior[budget.ids["key"]]["arr"], dict(lower=20, upper=20, unlogged=1))
        budget.path.write_text("broken")
        with self.assertRaises(ValueError):
            C.UsageBudget(["key"], self.now)

    def test_saved_response_and_error_after_save_count_as_one_request(self):
        folder = self.log / "20261102"; folder.mkdir()
        (folder / "jr03_arr_174000.json").write_text("{}")
        (self.log / "collect.log").write_text("2026-11-02T17:40:00+09:00 jr03 arr ValueError\n")
        got = C.replay_usage(self.log, "20261102", 4)
        self.assertEqual(got["recorded_total"]["arr"], 1)

    def test_restarts_keep_bounds_and_reserve_separate_from_new_attempts(self):
        lines = []
        for offset in (0, 600):
            start = self.now + dt.timedelta(seconds=offset)
            lines.append(f"{start.isoformat()} start, keys = 4 share = 0.5\n")
            for i in range(5):
                lines.append(f"{(start + dt.timedelta(seconds=i*30)).isoformat()} jr03 arr HTTPError 503\n")
        (self.log / "collect.log").write_text("".join(lines))
        keys = ["a", "b", "c", "d"]
        original = self.log / "usage" / "20261102.json";original.parent.mkdir()
        original.write_text(json.dumps({C.hashlib.sha256(k.encode()).hexdigest()[:16]: {"arr": 992, "pos": 992} for k in keys}))
        still = C.UsageBudget(keys, self.now)
        self.assertEqual(still.remaining("a", "arr"), 0)
        fixed = C.UsageBudget(keys, self.now, reconcile=True, manual_calls={"a": {"arr": 2}})
        self.assertEqual(fixed.prior[fixed.ids["a"]]["arr"], dict(lower=2, upper=4, unlogged=4))
        self.assertEqual(fixed.remaining("a", "arr"), C.LIMIT - 8)
        self.assertEqual(fixed.used[fixed.ids["a"]]["arr"], 0)
        self.assertTrue(fixed.reserve("a", "arr"))
        restored = C.UsageBudget(keys, self.now)
        self.assertEqual(restored.remaining("a", "arr"), C.LIMIT - 9)
        self.assertTrue(original.with_name(original.name + ".before-reconcile").exists())
        with self.assertRaises(ValueError):
            C.UsageBudget(keys, self.now, reconcile=True)

    def test_changed_historical_key_pool_cannot_be_divided_by_new_key_count(self):
        (self.log / "collect.log").write_text("2026-11-02T17:40:00+09:00 start, keys = 1 share = 2\n")
        with self.assertRaises(ValueError):
            C.UsageBudget(["a", "b"], self.now)

    def test_exhausted_key_does_not_block_another_keys_remaining_budget(self):
        budget = C.UsageBudget(["a", "b"], self.now)
        with patch.object(C, "LIMIT", 1):
            self.assertTrue(budget.reserve("a", "arr"))
            self.assertEqual(budget.choose("a", "arr"), "b")

    def test_live_collector_in_upstream_outage_does_not_trigger_restart(self):
        (self.log / "collector_state.json").write_text(json.dumps({"heartbeat": self.now.isoformat()}))
        with patch.object(W.C, "allowed", return_value=True), patch.object(W.C, "load_sched", return_value={}):
            problems, restart = W.check(self.now.replace(tzinfo=None))
            self.assertTrue(problems)
            self.assertFalse(restart)
            _, restart = W.check((self.now + dt.timedelta(minutes=11)).replace(tzinfo=None))
            self.assertTrue(restart)

    def test_service_end_does_not_send_false_recovery_notification(self):
        state = self.log / "watchdog.json"
        state.write_text(json.dumps({"open": ["sb02 새 데이터 없음", "jr03 새 데이터 없음"]}))
        with patch.object(W, "STATE", state), patch.object(W.N, "REPORTS", self.log), \
             patch.object(W, "check", return_value=([], False)), patch.object(W.C, "load_sched", return_value={}), \
             patch.object(W.C, "allowed", return_value=False), patch.object(W.N, "send") as send:
            W.main()
            send.assert_not_called()
        self.assertEqual(set(json.loads(state.read_text())["open"]), {"sb02 새 데이터 없음", "jr03 새 데이터 없음"})
        with patch.object(W, "STATE", state), patch.object(W.N, "REPORTS", self.log), \
             patch.object(W, "check", return_value=([], False)), patch.object(W.C, "load_sched", return_value={}), \
             patch.object(W.C, "allowed", side_effect=lambda now,route,sched: route == "jr03"), patch.object(W.N, "send") as send:
            W.main()
            send.assert_not_called()
        self.assertEqual(json.loads(state.read_text())["open"], ["sb02 새 데이터 없음"])
        with patch.object(W, "STATE", state), patch.object(W.N, "REPORTS", self.log), \
             patch.object(W, "check", return_value=([], False)), patch.object(W.C, "load_sched", return_value={}), \
             patch.object(W.C, "allowed", return_value=True), patch.object(W.N, "send") as send:
            W.main()
            send.assert_called_once()
        self.assertEqual(json.loads(state.read_text())["open"], [])

    def test_http_failure_keeps_diagnostics_without_url_or_body_secrets(self):
        budget = C.UsageBudget(["test-key"], self.now)
        state = {}
        body = b"<!DOCTYPE HTML><html>serviceKey=test-key</html>"
        err = HTTPError("http://example/?serviceKey=test-key", 503, "test-key", {}, io.BytesIO(body))
        with patch.object(C, "fetch", side_effect=err):
            C.attempt("jr03", "arr", "test-key", self.now, budget, state, {})
        entry = state["endpoints"]["jr03:arr"]
        self.assertEqual((entry["status"], entry["failure_stage"], entry["http_status"], entry["response_kind"]),
                         ("upstream_error", "request", 503, "html"))
        self.assertEqual(entry["response_prefix_sha256"], C.hashlib.sha256(body).hexdigest())
        self.assertNotIn("test-key", json.dumps(state))
        self.assertNotIn("example", json.dumps(state))

    def test_provider_code_is_separate_from_http_and_does_not_become_a_snapshot(self):
        budget = C.UsageBudget(["test-key"], self.now)
        state = {}
        body = json.dumps({"msgHeader": {"headerCd": "7", "headerMsg": "test-key"}}).encode()
        with patch.object(C, "fetch", return_value=body):
            C.attempt("jr03", "arr", "test-key", self.now, budget, state, {})
        entry = state["endpoints"]["jr03:arr"]
        self.assertEqual((entry["failure_stage"], entry["http_status"], entry["api_header_code"]), ("api_header", 200, "7"))
        self.assertFalse(list((self.log / "20261102").glob("*.json")))
        self.assertNotIn("test-key", json.dumps(state))

    def test_success_clears_previous_error_diagnostics(self):
        budget = C.UsageBudget(["key"], self.now)
        state = {"endpoints": {"jr03:arr": {"status": "upstream_error", "failure_stage": "request",
                 "error_type": "HTTPError", "response_kind": "html", "api_header_code": "7", "response_prefix_sha256": "old", "response_sample_bytes": 1}}}
        body = json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": []}}).encode()
        with patch.object(C, "fetch", return_value=body):
            C.attempt("jr03", "arr", "key", self.now, budget, state, {})
        entry = state["endpoints"]["jr03:arr"]
        self.assertEqual((entry["status"], entry["http_status"]), ("ok", 200))
        for key in ("failure_stage", "error_type", "api_header_code", "response_kind", "response_prefix_sha256", "response_sample_bytes"):
            self.assertNotIn(key, entry)

    def test_local_storage_failure_is_not_reported_as_provider_failure(self):
        budget = C.UsageBudget(["key"], self.now)
        state = {}
        body = json.dumps({"msgHeader": {"headerCd": "4"}, "msgBody": {"itemList": []}}).encode()
        write = C.write_snapshot
        def fail_snapshot(path, data):
            if path.parent.name == "20261102":
                raise OSError("disk full")
            return write(path, data)
        with patch.object(C, "fetch", return_value=body), patch.object(C, "write_snapshot", side_effect=fail_snapshot):
            C.attempt("jr03", "arr", "key", self.now, budget, state, {})
        entry = state["endpoints"]["jr03:arr"]
        self.assertEqual((entry["status"], entry["failure_stage"], entry["http_status"]), ("storage_error", "snapshot_store", 200))

    def test_invalid_json_is_a_decode_failure_with_no_snapshot(self):
        budget = C.UsageBudget(["key"], self.now)
        state = {}
        with patch.object(C, "fetch", return_value=b"<html>temporary error</html>"):
            C.attempt("jr03", "arr", "key", self.now, budget, state, {})
        entry = state["endpoints"]["jr03:arr"]
        self.assertEqual((entry["failure_stage"], entry["http_status"], entry["response_kind"]), ("decode", 200, "html"))
        self.assertFalse(list((self.log / "20261102").glob("*.json")))

    def test_broken_response_body_is_not_saved_as_successful_data(self):
        budget = C.UsageBudget(["key"], self.now)
        for route in C.ROUTES:
            for kind in C.URLS:
                for message in (None, {"itemList": {}}, {"itemList": [None]}):
                    state = {}
                    body = json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": message}).encode()
                    with self.subTest(route=route, kind=kind, message=message), patch.object(C, "fetch", return_value=body):
                        C.attempt(route, kind, "key", self.now, budget, state, {})
                        entry = state["endpoints"][route+":"+kind]
                        self.assertEqual((entry["status"],entry["failure_stage"]), ("upstream_error","api_body"))
                        self.assertNotIn("last_success",entry)
                        self.assertFalse(list((self.log / "20261102").glob("*.json")))

    def test_invalid_optional_timetable_keeps_successful_arrival_and_no_retry_delay(self):
        budget = C.UsageBudget(["key"], self.now)
        for route in C.ROUTES:
            for value in (None, 17, "not-a-time", "20261199051000", "20261102051099"):
                for field in ("firstTm", "lastTm"):
                    item = {"firstTm": "20261102055100", "lastTm": "20261103001000", field: value}
                    body = json.dumps({"msgHeader": {"headerCd": "0"}, "msgBody": {"itemList": [item]}}).encode()
                    state, sched = {}, {route: {"wkd": [351, 1450]}}
                    with self.subTest(route=route, field=field, value=value), patch.object(C, "fetch", return_value=body):
                        C.attempt(route, "arr", "key", self.now, budget, state, sched)
                        entry = state["endpoints"][route+":arr"]
                        self.assertEqual((entry["status"], entry["retry_after"]), ("ok", 0))
                        self.assertEqual(sched, {route: {"wkd": [351, 1450]}})
                        self.assertEqual((self.log / "20261102" / f"{route}_arr_174000.json").read_bytes(), body)

    def test_timetable_learns_overnight_window_and_ignores_other_day_or_invalid_values(self):
        # 금요일 운행의 자정 이후 막차를 토요일 시간표로 옮기지 않는다.
        sched = {}
        items = [{"firstTm": None, "lastTm": 3},
                 {"firstTm": "20261106055100", "lastTm": "20261107001000"},
                 {"firstTm": "", "lastTm": "20261207010000"},
                 {"firstTm": "", "lastTm": "20261105010000"}]
        with patch.object(C, "HOLIDAYS", self.log / "absent.csv"):
            C.learn(sched, items, "sb02")
        self.assertEqual(sched, {"sb02": {"wkd": [351, 1450]}})


if __name__ == "__main__":
    unittest.main()
