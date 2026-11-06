import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import watchdog as W


class WatchdogHealth(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.state=self.root/'watchdog.json'
        for obj,name,value in [(W,'STATE',self.state),(W.N,'REPORTS',self.root)]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        for obj,name,value in [(W,'check',([],False)),(W.C,'load_sched',{}),(W.C,'allowed',True)]:
            p=patch.object(obj,name,return_value=value);p.start();self.addCleanup(p.stop)
        self.send=patch.object(W.N,'send').start();self.addCleanup(patch.stopall)
        self.command=patch.object(W.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')).start()

    def test_web_stale_restarts_only_web_and_rate_limits(self):
        with patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):
            W.main();W.main()
        self.assertEqual(self.command.call_count,1)
        self.assertEqual(self.command.call_args.args[0],['sudo','-n','systemctl','try-restart','hanjari-web'])
        self.assertEqual(self.send.call_count,1)
        self.assertIn('rollback',self.send.call_args.args[0])

    def test_web_missing_model_alerts_without_restarting_collector(self):
        with patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'missing'}}):W.main()
        self.command.assert_not_called();self.send.assert_called_once()

    def test_connection_failure_is_deduplicated(self):
        with patch.object(W,'web_health',side_effect=OSError('refused')):W.main();W.main()
        self.send.assert_called_once();self.command.assert_not_called()

    def test_collector_stale_and_web_stale_have_independent_limits(self):
        with patch.object(W,'check',return_value=(['sb02 새 데이터 없음'],True)), \
             patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):W.main()
        commands=[c.args[0][-1] for c in self.command.call_args_list]
        self.assertEqual(commands,['hanjari-collect','hanjari-web'])
        state=json.loads(self.state.read_text())
        self.assertIn('restarted',state);self.assertIn('web_restarted',state)

    def test_corrupt_state_is_quarantined_and_atomic_write_keeps_only_one(self):
        (self.root/'watchdog.json.corrupt-old').write_text('old')
        for text in ['{','[]','42','{"restarted":"bad","open":null}']:
            with self.subTest(text=text):
                self.state.write_text(text)
                with patch.object(W,'web_health',return_value={'ready':True}):W.main()
                self.assertIsInstance(json.loads(self.state.read_text()),dict)
                self.assertEqual(len(list(self.root.glob('watchdog.json.corrupt-*'))),1)
        self.assertTrue(any(c.args[1]=='WARN' for c in self.send.call_args_list))

    def test_corrupt_state_limits_restarts_until_next_gap(self):
        self.state.write_text('{')
        with patch.object(W,'check',return_value=(['sb02 stale'],True)), \
             patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):W.main()
        self.command.assert_not_called()

    def test_health_request_is_loopback_with_five_second_timeout(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"ready":true}'
        with patch.object(W.urllib.request,'urlopen',return_value=response) as request:
            self.assertTrue(W.web_health()['ready'])
        self.assertEqual(request.call_args.args[0],'http://127.0.0.1:8000/api/health')
        self.assertEqual(request.call_args.kwargs['timeout'],5)

    def test_failed_state_replace_preserves_previous_file(self):
        self.state.write_text('{"open":[]}')
        previous=self.state.read_bytes()
        with patch.object(W,'web_health',return_value={'ready':True}), \
             patch.object(W.C.os,'replace',side_effect=OSError('write failed')):
            with self.assertRaises(OSError):W.main()
        self.assertEqual(self.state.read_bytes(),previous)


if __name__=='__main__':unittest.main()
