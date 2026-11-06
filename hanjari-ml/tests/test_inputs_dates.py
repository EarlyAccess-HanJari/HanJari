import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import collect as C
import build_dataset as B
import serve as S
import date_paths as dates


class InputsAndDates(unittest.TestCase):
    def test_schedule_keeps_valid_entries_and_rejects_bad_shapes(self):
        bad=[None, True, [3], [True, 500], [-1, 400], [100, 99], [100, 2880], [1500,1600], ['330', 1500]]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'schedule.json'
            for value in bad:
                with self.subTest(value=value):
                    path.write_text(json.dumps({'sb02':{'wkd':[330,1480],'sat':value},'jr03':None}))
                    err=io.StringIO()
                    with patch.object(C,'SCHED',path),redirect_stderr(err):
                        self.assertEqual(C.load_sched(),{'sb02':{'wkd':[330,1480]}})
                    self.assertEqual(len(err.getvalue().splitlines()),1)
            for data in [[],42,True,{'unknown':{'wkd':[330,1480]}}]:
                path.write_text(json.dumps(data))
                with patch.object(C,'SCHED',path),redirect_stderr(io.StringIO()):self.assertEqual(C.load_sched(),{})
            path.write_text('{')
            with patch.object(C,'SCHED',path):self.assertEqual(C.load_sched(),{})
            path.unlink()
            with patch.object(C,'SCHED',path):self.assertEqual(C.load_sched(),{})

    def test_collector_copies_match(self):
        root=Path(__file__).resolve().parents[2]
        self.assertEqual((root/'hanjari-ml/src/collect.py').read_bytes(),(root/'hanjari/src/collect.py').read_bytes())

    def test_real_dates_across_years_and_cache_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ['20261231','20270101','20240229','20270229','20271301','2027011','.lite-staging']:
                (root/name).mkdir()
            self.assertEqual([p.name for p in dates.day_folders(root)],['20240229','20261231','20270101'])
            for name in ['20270101_sb02.json','20261231_jr03.json','20270230_sb02.json','20270101_x.json']:
                (root/name).write_text('{}')
            self.assertEqual([p.name for p in dates.day_caches(root)],['20261231_jr03.json','20270101_sb02.json'])

    def test_history_cache_reads_2027(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);(out/'days').mkdir()
            (out/'days/20270101_sb02.json').write_text(json.dumps({'source_schema':2,'ev':[[30,13,4,2]]}))
            with patch.object(B,'OUT',out):self.assertEqual(B.hist_from_cache('sb02'),{(30,13):2})

    def test_latest_ignores_invalid_day_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            logs=Path(folder)
            for name in ['20270000','20261300','20260930']:(logs/name).mkdir()
            now=dt.datetime(2027,1,1,12)
            with patch.object(B,'LOG',logs),patch.object(C,'load_sched',return_value={}):
                routes=S.source_health(now)
                self.assertEqual({v['status'] for v in routes.values()},{'missing'})


if __name__=='__main__':unittest.main()
