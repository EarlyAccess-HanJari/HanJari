import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from terminal_baseline import TerminalCandidates, correction_scenario, observations


class TerminalBaselineTests(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 11, 2, 10)
        self.tracker = TerminalCandidates("100900039", (1, 30))

    def row(self, offset, count=5, **changes):
        t = self.start + dt.timedelta(seconds=offset)
        return dict(vehicle_id="123", plate="test", station_id="100900039", section=1,
                    count=count, source_time=t, position_time=t, gps=(127.0092, 37.5803), **changes)

    def add(self, offset, count=5, **changes):
        r = self.row(offset, count)
        r.update(changes)
        self.tracker.step(self.start + dt.timedelta(seconds=offset), [r])

    def test_stationary_terminal_uses_minimum_not_average_and_never_certifies_empty(self):
        for t, n in ((0, 6), (27, 5), (54, 5)):
            self.add(t, n)
        self.tracker.close()
        event, = self.tracker.events
        self.assertEqual(event["candidate_offset_max"], 5)
        self.assertEqual(event["automatic_subtraction"], 0)
        self.assertFalse(event["empty_verified"])
        self.assertEqual(correction_scenario(28, 5)["assumed_range"], [23, 28])

    def test_source_reset_to_zero_keeps_zero_baseline(self):
        for t, n in ((0, 6), (27, 5), (54, 0)):
            self.add(t, n)
        self.tracker.close()
        self.assertEqual(self.tracker.events[0]["candidate_offset_max"], 0)

    def test_repeated_stale_source_or_position_cannot_manufacture_confidence(self):
        for field in ("source_time", "position_time"):
            tracker = TerminalCandidates("100900039", (1, 30))
            for t in (0, 27, 54, 81):
                row = self.row(t)
                row[field] = self.start
                tracker.step(self.start + dt.timedelta(seconds=t), [row])
            tracker.close()
            self.assertEqual(tracker.events, [])

    def test_other_station_movement_and_vehicle_change_do_not_combine_samples(self):
        for change in (dict(station_id="other"), dict(gps=(127.012, 37.5803)), dict(vehicle_id="456")):
            self.tracker = TerminalCandidates("100900039", (1, 30))
            self.add(0)
            self.add(27, **change)
            self.add(54)
            self.tracker.close()
            self.assertEqual(self.tracker.events, [])

    def test_gap_and_next_day_do_not_extend_previous_checkpoint(self):
        self.add(0)
        self.add(27)
        self.add(200)
        self.add(86400)
        self.tracker.close()
        self.assertEqual(self.tracker.events, [])

    def test_provider_drop_below_baseline_invalidates_instead_of_creating_empty_bus(self):
        result = correction_scenario(2, 5)
        self.assertEqual(result["status"], "baseline_invalidated")
        self.assertEqual(result["raw"], 2)
        self.assertNotIn("assumed_range", result)
        self.assertEqual(result["automatic_subtraction"], 0)

    def test_raw_missing_count_conflict_and_old_position_do_not_become_zero_anchor(self):
        it = dict(routeType="2", rerdie_Div1="2", reride_Num1="5", plainNo1="test", vehId1="123", mkTm="2026-11-02 10:00:00")
        pos = dict(vehId="123", plainNo="test", dataTm="20261102100000", gpsX="127.0092", gpsY="37.5803",
                   lastStnId="100900039", sectOrd="1")
        self.assertEqual(observations([it], [pos], self.start)[0]["count"], 5)
        for arrivals, positions in (([dict(it, rerdie_Div1="0", reride_Num1="0")], [pos]),
                                   ([it, dict(it, reride_Num1="6")], [pos]),
                                   ([it], [dict(pos, vehId="456")]),
                                   ([it], [dict(pos, dataTm="20261102095859")])):
            self.assertEqual(observations(arrivals, positions, self.start), [])


if __name__ == "__main__":
    unittest.main()
