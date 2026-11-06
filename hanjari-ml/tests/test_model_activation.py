"""Model publication failures use dummy files; no training or system commands."""
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import daily as D


class ModelActivation(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.models=self.root/'models'
        self.live=self.models/'lite';self.versions=self.models/'versions';self.reports=self.root/'reports'
        for p in [self.versions,self.reports,self.root/'logs',self.root/'processed'] :p.mkdir(parents=True)
        for obj,name,value in [(D,'LIVE',self.live),(D,'VERS',self.versions),(D,'REPORTS',self.reports),
                               (D.B,'LOG',self.root/'logs'),(D.B,'OUT',self.root/'processed')]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.send=patch.object(D.N,'send').start();self.addCleanup(patch.stopall)
        self.restart=patch.object(D.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')).start()
        patch.object(D.shutil,'disk_usage',return_value=SimpleNamespace(free=100*10**9)).start()
        self.make(self.live,'20261104')
        self.candidate=self.versions/'20261105';self.meta=self.make(self.candidate,'20261105')
        self.old=self.contents(self.live)

    def make(self,path,day):
        path.mkdir(parents=True,exist_ok=True)
        meta={'created':day,'trained_on':[day],'oof':{'mae':1,'hi_ok':.99}}
        (path/'meta.json').write_text(json.dumps(meta))
        for name in ['point','quantile','k0']:(path/f'{name}.json').write_text(json.dumps({'version':day}))
        return meta

    def contents(self,path):return {p.name:p.read_bytes() for p in path.iterdir() if p.is_file()}

    def history(self,rows):
        with (self.reports/'models.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['version','promoted']);w.writeheader()
            for version,promoted in rows:w.writerow(dict(version=version,promoted=promoted))

    def test_activation_success_retains_real_previous_directory(self):
        D.activate_model(self.candidate,'20261105')
        self.assertEqual(self.contents(self.live),self.contents(self.candidate))
        self.assertEqual(self.contents(self.models/'.lite-previous'),self.old)
        self.assertFalse(self.live.is_symlink())

    def test_copy_failure_preserves_live(self):
        with patch.object(D.shutil,'copytree',side_effect=OSError('copy failed')):
            with self.assertRaises(D.ActivationError):D.activate_model(self.candidate,'20261105')
        self.assertEqual(self.contents(self.live),self.old)

    def test_hash_mismatch_preserves_live(self):
        original=shutil.copytree
        def corrupt(src,dst):
            original(src,dst);(dst/'point.json').write_text('corrupt')
        with patch.object(D.shutil,'copytree',side_effect=corrupt):
            with self.assertRaises(D.ActivationError):D.activate_model(self.candidate,'20261105')
        self.assertEqual(self.contents(self.live),self.old)

    def test_second_rename_failure_restores_previous(self):
        original=Path.rename
        def fail(path,target):
            if path.name=='.lite-staging':raise OSError('rename failed')
            return original(path,target)
        with patch.object(Path,'rename',fail):
            with self.assertRaises(D.ActivationError) as caught:D.activate_model(self.candidate,'20261105')
        self.assertIn('기존 모델 유지',str(caught.exception))
        self.assertEqual(self.contents(self.live),self.old)

    def test_restore_failure_is_not_reported_as_preserved(self):
        original=Path.rename
        def fail(path,target):
            if path.name in ('.lite-staging','.lite-previous'):raise OSError('rename failed')
            return original(path,target)
        with patch.object(Path,'rename',fail):
            with self.assertRaises(D.ActivationError) as caught:D.activate_model(self.candidate,'20261105')
        self.assertIn('서비스 모델 복구 실패, 즉시 확인',str(caught.exception))
        self.assertFalse(self.live.exists())

    def run_fake(self,cleanup=None):
        with patch.object(D,'check_data',return_value=('OK','test')),patch.object(D.B,'main'), \
             patch.object(D,'monitor',return_value=None),patch.object(D.S,'export',return_value=self.meta), \
             patch.object(D.S,'demo'),patch.object(D,'cleanup',side_effect=cleanup or (lambda day:[])):
            return D.run('20261105')

    def test_run_failure_records_false_and_preservation_warning(self):
        with patch.object(D.shutil,'copytree',side_effect=OSError('copy failed')):
            _,warn=self.run_fake()
        rows=list(csv.DictReader((self.reports/'models.csv').open()))
        self.assertEqual(rows[-1]['promoted'],'False')
        self.assertTrue(any('기존 모델 유지' in w for w in warn))
        self.assertEqual(self.contents(self.live),self.old)
        self.assertFalse((self.reports/'restart_required').exists())

    def test_cleanup_failure_after_promotion_still_succeeds(self):
        def fail(day):raise OSError('cleanup failed')
        _,warn=self.run_fake(fail)
        self.assertTrue((self.reports/'restart_required').exists())
        self.assertTrue(any('정리 실패' in w for w in warn))
        self.assertEqual(list(csv.DictReader((self.reports/'models.csv').open()))[-1]['promoted'],'True')

    def test_restore_failure_records_false_and_error_alert(self):
        original=Path.rename
        def fail(path,target):
            if path.name in ('.lite-staging','.lite-previous'):raise OSError('rename failed')
            return original(path,target)
        with patch.object(Path,'rename',fail):_,warn=self.run_fake()
        self.assertEqual(list(csv.DictReader((self.reports/'models.csv').open()))[-1]['promoted'],'False')
        self.assertTrue(any('서비스 모델 복구 실패, 즉시 확인' in w for w in warn))
        self.assertTrue(any('복구 실패' in c.args[0] and c.args[1]=='ERROR' for c in self.send.call_args_list))

    def test_daily_report_failure_does_not_lose_restart_marker(self):
        original=Path.write_text
        def fail(path,*args,**kwargs):
            if path.suffix=='.md':raise OSError('report failed')
            return original(path,*args,**kwargs)
        with patch.object(Path,'write_text',fail):_,warn=self.run_fake()
        self.assertTrue((self.reports/'restart_required').exists())
        self.assertTrue(any('보고서 기록 실패' in w for w in warn))

    def test_low_disk_skips_training(self):
        with patch.object(D.shutil,'disk_usage',return_value=SimpleNamespace(free=1)), \
             patch.object(D,'check_data',return_value=('OK','test')),patch.object(D.B,'main'), \
             patch.object(D,'monitor',return_value=None),patch.object(D.S,'export') as train, \
             patch.object(D,'cleanup',return_value=[]):
            _,warn=D.run('20261105')
        train.assert_not_called();self.assertTrue(any('디스크' in w for w in warn))
        self.assertEqual(self.contents(self.live),self.old)

    def test_activation_requires_twice_candidate_size(self):
        with patch.object(D.shutil,'disk_usage',return_value=SimpleNamespace(free=1)):
            with self.assertRaises(D.ActivationError):D.activate_model(self.candidate,'20261105')
        self.assertEqual(self.contents(self.live),self.old)

    def test_rollback_chooses_promoted_not_latest_candidate(self):
        self.make(self.versions/'20261103','20261103')
        self.history([('20261103',True),('20261105',False)])
        D.rollback()
        self.assertEqual(json.loads((self.live/'meta.json').read_text())['created'],'20261103')
        self.assertEqual(self.restart.call_args.args[0],['sudo','-n','systemctl','try-restart','hanjari-web'])

    def test_rollback_rejects_unapproved_unless_force(self):
        self.history([('20261105',False)])
        with self.assertRaises(SystemExit):D.rollback('20261105')
        self.assertEqual(self.contents(self.live),self.old)
        D.rollback('20261105',force=True)
        self.assertEqual(json.loads((self.live/'meta.json').read_text())['created'],'20261105')

    def test_rollback_without_candidate_changes_nothing(self):
        with self.assertRaises(SystemExit):D.rollback()
        self.assertEqual(self.contents(self.live),self.old)

    def test_rollback_restart_failure_warns_without_reverting_model(self):
        self.history([('20261105',True)])
        self.restart.return_value=SimpleNamespace(returncode=1,stderr='denied')
        D.rollback('20261105')
        self.assertEqual(json.loads((self.live/'meta.json').read_text())['created'],'20261105')
        self.assertTrue(any('재시작 실패' in c.args[0] for c in self.send.call_args_list))

    def test_retention_keeps_latest_seven_and_two_promoted(self):
        for i in range(1,12):self.make(self.versions/f'202701{i:02}',f'202701{i:02}')
        self.history([('20270101',True),('20270102',True),('20270111',False)])
        D.cleanup('20270112')
        self.assertTrue((self.versions/'20270101').exists());self.assertTrue((self.versions/'20270102').exists())
        self.assertFalse((self.versions/'20270103').exists())
        self.assertTrue((self.versions/'20270111').exists())


if __name__=='__main__':unittest.main()
