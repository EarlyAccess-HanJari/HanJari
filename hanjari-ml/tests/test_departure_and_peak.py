"""11-25: 앞 정류장을 막 떠난 버스의 미반영 몫(q_pending)과 아침 '수업 직전'(is_peak) 회귀 검사. 외부 API 호출 없음."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import build_dataset as B
import serve as S
import train as T
from test_capacity import fixture

PLATE = "서울70사6419"  # 표본 13:11:33 위치에서 2번출구(31)에 서 있는 차 → 녹십자(32) 바로 앞 버스


class DepartedPending(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / S.SAMPLE.name
        shutil.copytree(S.SAMPLE, self.folder)
        self.pos = self.folder / "sb02_pos_131133.json"
        self.body = json.loads(self.pos.read_text())
        _, meta = S.load(True)
        self.tab = meta["tab_d"]["sb02"]

    def set_flag(self, body, flag, data_tm=None):
        for v in body["msgBody"]["itemList"]:
            if v["plainNo"] == PLATE:
                v["stopFlag"] = str(flag)
                if data_tm:
                    v["dataTm"] = data_tm
        return body

    def row32(self):
        rows = B.build("sb02", [str(self.folder)], open_=True, tab=self.tab)
        return next(r for r in rows if int(r["stop"]) == 32 and r["plate"] == PLATE)

    def test_dwelling_adds_previous_stop_share(self):
        r = self.row32()
        self.assertEqual((r["pos_sect"], r["pos_dwell"], r["run_sec"]), (31, 1, None))
        self.assertGreater(r["q_pending"], 0)

    def test_first_sighting_after_departure_keeps_share_until_reflected(self):
        dwelling = self.row32()["q_pending"]
        earlier = self.set_flag(json.loads(self.pos.read_text()), 1, "20260930131100")
        (self.folder / "sb02_pos_131106.json").write_text(json.dumps(earlier))
        self.pos.write_text(json.dumps(self.set_flag(self.body, 0)))
        r = self.row32()
        self.assertEqual((r["pos_dwell"], r["run_sec"]), (0, 0.0))
        self.assertEqual(r["q_pending"], dwelling)  # 출발 첫 관측: 정차 때와 같은 몫을 그대로 더한다

    def test_reflected_or_unknown_departure_adds_nothing(self):
        self.pos.write_text(json.dumps(self.set_flag(self.body, 0)))
        r = self.row32()
        self.assertEqual((r["run_sec"], r["q_pending"]), (None, 0.0))  # 언제 떠났는지 모르면 예전처럼 0
        old = B.REFLECT_SEC
        B.REFLECT_SEC = -1
        self.addCleanup(setattr, B, "REFLECT_SEC", old)
        earlier = self.set_flag(json.loads(self.pos.read_text()), 1, "20260930131100")
        (self.folder / "sb02_pos_131106.json").write_text(json.dumps(earlier))
        self.assertEqual(self.row32()["q_pending"], 0.0)  # 반영 시간이 지나면(여기선 기준을 −1초로) 더하지 않는다

    def test_departed_bus_before_reflection_uses_dwelling_spread(self):
        row, m, _ = fixture(50, stops=0)
        m["res0"] = {True: np.linspace(-20, 20, 41), False: np.zeros(41)}
        p = lambda **kw: T.predict(m, pd.DataFrame([dict(row, pos_dwell=0, pos_sect=int(row["stop"]) - 1, **kw)]))[1][0, 0]
        dwelling = T.predict(m, pd.DataFrame([dict(row, pos_dwell=1, pos_sect=int(row["stop"]) - 1)]))[1][0, 0]
        self.assertEqual(p(run_sec=0.0), dwelling)
        self.assertEqual(p(run_sec=27.0), 1)   # 둘째 관측(27초)은 이미 반영 → 주행 분포
        self.assertEqual(p(run_sec=np.nan), 1)


class MorningPeak(unittest.TestCase):
    def peaks(self, date, times):
        _, meta = S.load(True)
        base = B.build("sb02", [str(S.SAMPLE)], open_=True, tab=meta["tab_d"]["sb02"])[0]
        d = pd.DataFrame([dict(base, date=date, time=t, eta=0) for t in times])
        return T.features(d, cats=meta["cats"]).is_peak.tolist()

    def test_morning_first_classes_count_as_peak(self):
        # 수(20260930): 09:00 28개·10:30 30개 → 오전 0~35분 창 16개 이상, 12:00 43개 → 낮 10~35분 창 40개 이상
        self.assertEqual(self.peaks("20260930", ["08:40:00", "10:20:00", "11:40:00", "14:00:00"]), [1, 1, 1, 0])

    def test_morning_rule_stops_at_eleven(self):
        # 화(20261124): 12:00 35개 — 11:30 도착이면 0~35분 창 35개지만 오전이 아니고 낮 기준 40개에 못 미친다
        self.assertEqual(self.peaks("20261124", ["08:45:00", "11:30:00"]), [1, 0])


if __name__ == "__main__":
    unittest.main()
