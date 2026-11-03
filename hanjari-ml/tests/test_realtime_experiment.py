"""Regression checks for the offline experiment's labels and group boundaries."""
import datetime as dt
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
import exp_realtime_groups as E


def item(hms, plate="a", vid="101", count="8", sect="29", stop="30", **extra):
    return dict(plainNo1=plate, vehId1=vid, reride_Num1=count, rerdie_Div1="2",
                routeType="2", mkTm="2026-10-01 " + hms,
                staOrd=stop, sectOrd1=sect, traTime1="120", busType1="0", **extra)


def run_rows(snapshots):
    audit = Counter()
    rows = list(E.closed_rows("sb02", "20261001", {"arr": snapshots, "pos": {}}, {}, audit))
    return rows, audit


class ArrivalLabels(unittest.TestCase):
    def test_label_requires_confirmed_vehicle_change(self):
        start = item("12:00:00")
        end = item("12:01:00", count="10", sect="30")
        self.assertEqual(run_rows({"120000": [start], "120100": [end]})[0], [])
        rows, _ = run_rows({"120000": [start], "120100": [end],
                            "120130": [item("12:01:30", plate="b", vid="102")]})
        self.assertEqual([r["y"] for r in rows], [10, 10])
        self.assertTrue(all(r["label_available_at"] == "2026-10-01T12:01:30" for r in rows))
        self.assertTrue(all(r["time"] <= r["arrive_time"] < r["label_available_at"] for r in rows))

    def test_repeated_provider_timestamp_is_one_observation(self):
        rows, audit = run_rows({"120000": [item("12:00:00")], "120030": [item("12:00:00")],
                               "120100": [item("12:01:00", sect="30")],
                               "120130": [item("12:01:30", plate="b", vid="102")]})
        self.assertEqual(len(rows), 2)
        self.assertEqual(audit["duplicate_source_update"], 1)

    def test_missing_end_count_is_not_zero_or_an_earlier_label(self):
        rows, _ = run_rows({"120000": [item("12:00:00")],
                            "120100": [item("12:01:00", sect="30", count="")],
                            "120130": [item("12:01:30", plate="b", vid="102")]})
        self.assertEqual(rows, [])

    def test_expired_eta_can_supply_valid_arrival_label_but_not_input(self):
        end = item("12:01:00", sect="30", count="11")
        end["traTime1"] = "0"
        rows, _ = run_rows({"120000": [item("12:00:00")], "120105": [end],
                            "120130": [item("12:01:30", plate="b", vid="102")]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["y"], 11)
        self.assertEqual(rows[0]["time"], "2026-10-01T12:00:00")
        self.assertNotIn("_usable_input", rows[0])

    def test_data_gap_or_identity_change_does_not_make_an_arrival(self):
        for last in [item("12:10:00", plate="b", vid="102"), item("12:10:00", vid="999")]:
            rows, _ = run_rows({"120000": [item("12:00:00", sect="30")], "121000": [last]})
            self.assertEqual(rows, [])
        rows, _ = run_rows({"120000": [item("12:00:00", sect="30")],
                            "120030": [item("12:00:30", vid="999")]})
        self.assertEqual(rows, [])

    def test_cross_stop_conflict_and_stale_source_rejected(self):
        rows, audit = run_rows({"120000": [item("12:00:00", sect="30"), item("12:00:00", count="30", stop="31")],
                               "120100": [item("11:50:00", sect="30")],
                               "120130": [item("12:01:30", plate="b", vid="102")]})
        self.assertEqual(rows, [])
        self.assertGreater(audit["passenger_conflict"], 0)
        self.assertGreater(audit["source_stale"], 0)

    def test_eta_uses_provider_time_and_position_id_must_match(self):
        audit = Counter()
        t, _, rows = E.snapshot_rows("sb02", "20261001", "120030", [item("12:00:00")], [], {}, audit)
        self.assertEqual(rows[30]["eta"], 90)
        pos = dict(plainNo="a", vehId="999", dataTm="20261001120000", sectOrd="29", stopFlag="0")
        _, _, rows = E.snapshot_rows("sb02", "20261001", "120030", [item("12:00:00")], [pos], {}, audit)
        self.assertEqual(rows, {})
        self.assertEqual(audit["vehicle_mismatch"], 1)


class GroupBoundaries(unittest.TestCase):
    def test_bus_type_is_not_physical_size_evidence(self):
        row = SimpleNamespace(route="sb02", plate="a", vehicle_id="101", bus_type=0, date="20261001")
        self.assertEqual(E.group_for(row), "sb02_api0")
        self.assertEqual(E.group_for(row, {}), "unverified")
        registry = {("sb02", "a", "101"): {"group": "sb02_large", "valid_from": "20260901", "valid_until": "20261101"}}
        self.assertEqual(E.group_for(row, registry), "sb02_large")
        row.vehicle_id = "999"
        self.assertEqual(E.group_for(row, registry), "unverified")
        row.vehicle_id, row.date = "101", "20261201"
        self.assertEqual(E.group_for(row, registry), "unverified")

    def test_registry_requires_evidence_and_validity_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"groups.json"
            p.write_text(json.dumps({"version": 1, "vehicles": [{"route": "sb02", "plate": "a",
                         "vehicle_id": "101", "group": "sb02_small", "evidence": ""}]}))
            with self.assertRaises(ValueError):
                E.load_registry(p)

    def test_holdout_is_last_seven_days_with_no_overlap(self):
        dates = [(dt.date(2026, 9, 1)+dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(30)]
        d = E.pd.DataFrame({"date": dates})
        folds = list(E.splits(d))
        self.assertEqual(folds[-1][2], dates[-7:])
        for _, train, test in folds:
            self.assertLess(max(train), min(test))
            self.assertFalse(set(train) & set(test))


if __name__ == "__main__":
    unittest.main()
