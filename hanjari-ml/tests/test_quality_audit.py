import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import quality_audit as Q


class QualityAudit(unittest.TestCase):
    def setUp(self):
        self.start = dt.datetime(2026, 11, 2, 10)
        self.tracker = Q.ShadowOffsets("100900039", (1, 30))

    def step(self, sec, count=5, section=1, vehicle="123"):
        now = self.start + dt.timedelta(seconds=sec)
        row = dict(vehicle_id=vehicle, plate="test-"+vehicle, station_id="100900039" if section==1 else "other",
                   section=section, count=count, source_time=now, position_time=now, gps=(127.0092,37.5803))
        return self.tracker.step(now, [row])

    def anchor(self):
        for sec in (0,30,60):
            self.step(sec)

    def test_shadow_range_never_changes_served_count_and_provider_reset_invalidates(self):
        self.anchor()
        result, = self.step(90,28,2)
        self.assertEqual((result["raw"],result["hypothetical_lower"],result["hypothetical_upper"],result["applied_subtraction"]),(28,23,28,0))
        self.assertEqual(self.step(120,3,3),[])
        self.assertEqual(self.step(150,28,4),[])
        self.assertEqual(self.tracker.stats["invalidated_by_lower_api_count"],1)

    def test_other_vehicle_or_next_trip_cannot_inherit_offset(self):
        self.anchor()
        self.assertEqual(self.step(90,28,2,"456"),[])
        self.tracker = Q.ShadowOffsets("100900039", (1,30))
        self.anchor();self.step(90,28,2);self.step(120,8,29)
        self.assertEqual(self.step(150,7,1),[])
        self.assertEqual(self.step(180,20,2),[])

    def test_gap_and_next_day_discard_offset(self):
        for sec in (400,86400):
            self.tracker = Q.ShadowOffsets("100900039", (1,30))
            self.anchor();self.step(90,28,2)
            self.assertEqual(self.step(sec,28,3),[])

    def test_saved_sample_report_does_not_claim_field_accuracy_or_apply_subtraction(self):
        report = Q.audit_day(Q.B.ROOT / "data/sample", "20260930")
        self.assertFalse(report["applied_to_display"])
        self.assertFalse(report["applied_to_training"])
        self.assertFalse(report["field_accuracy_verified"])
        self.assertTrue(all(v["snapshots"]==1 for v in report["routes"].values()))
        checkpoints = report["routes"]["sb02"]["terminal"]["checkpoints"]
        self.assertEqual({v["station_id"] for v in checkpoints.values()}, {"107900256", "107900329"})
        self.assertTrue(all(not v["empty_verified"] for v in checkpoints.values()))

    def test_sb02_offset_clears_at_other_turnaround_without_section_wrap(self):
        reset_points = {("107900256", 1), ("107900256", 38), ("107900329", 19)}
        self.tracker = Q.ShadowOffsets("107900256", (1,38), reset_points=reset_points)

        def step(sec, section, station, count=4):
            now = self.start + dt.timedelta(seconds=sec)
            row = dict(vehicle_id="107063707", plate="test", station_id=station, section=section,
                       count=count, source_time=now, position_time=now, gps=(127.01,37.58))
            return self.tracker.step(now, [row])

        for sec in (0,30,60):
            step(sec,1,"107900256")
        self.assertEqual(step(90,2,"other",20)[0]["hypothetical_lower"],16)
        self.assertEqual(step(120,19,"107900329",20),[])
        self.assertEqual(step(150,20,"other",20),[])

    def test_departure_candidate_cannot_be_created_at_other_checkpoint(self):
        self.tracker = Q.ShadowOffsets("100900039", (1,30), reset_points={("other",19)})
        self.anchor()
        self.assertEqual(self.step(90,28,19),[])
        self.assertEqual(self.step(120,28,20),[])


if __name__ == "__main__":
    unittest.main()
