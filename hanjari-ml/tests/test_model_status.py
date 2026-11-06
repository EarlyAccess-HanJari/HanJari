import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import serve as S


class ModelStatus(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.live=self.root/'lite';self.live.mkdir()
        self.meta=self.live/'meta.json'
        self.meta.write_text(json.dumps({'created':'old'}))
        for name in ['point','quantile','k0']:(self.live/f'{name}.json').write_text('{}')
        for p in [patch.object(S,'MODELS',self.root),patch.object(S,'_M',{}),
                  patch.object(S.DQ,'boarding_policy',return_value={'enabled':True})]:
            p.start();self.addCleanup(p.stop)

    def test_status_and_mtime_changes(self):
        self.assertEqual(S.model_status(),{'status':'not_loaded','loaded':None,'disk':'old'})
        S._M[self.live]=({}, {'created':'old'})
        self.assertEqual(S.model_status()['status'],'ok')
        self.meta.write_text(json.dumps({'created':'changed'}))
        self.assertEqual(S.model_status(),{'status':'stale','loaded':'old','disk':'changed'})
        self.meta.write_text('{')
        self.assertEqual(S.model_status()['status'],'broken')
        self.meta.unlink()
        self.assertEqual(S.model_status()['status'],'missing')

    def test_metadata_is_cached_and_missing_weights_detected(self):
        original=Path.read_text
        calls=[]
        def read(path,*args,**kwargs):calls.append(path);return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):
            S.model_status();S.model_status()
        self.assertEqual(calls.count(self.meta),1)
        (self.live/'point.json').unlink()
        self.assertEqual(S.model_status()['status'],'missing')

    def test_policy_off_does_not_require_model_files(self):
        with patch.object(S.DQ,'boarding_policy',return_value={'enabled':False}):
            self.meta.unlink()
            self.assertEqual(S.model_status()['status'],'not_required')

    def test_failed_model_load_is_broken_until_disk_changes(self):
        self.meta.write_text(json.dumps({'created':'old','feats':[]}))
        with self.assertRaises(Exception):S.load(True)
        self.assertEqual(S.model_status()['status'],'broken')
        self.meta.write_text(json.dumps({'created':'repaired','feats':[]}))
        self.assertEqual(S.model_status()['status'],'not_loaded')


if __name__=='__main__':unittest.main()
