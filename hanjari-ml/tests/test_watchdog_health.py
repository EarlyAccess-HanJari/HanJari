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
        p=patch.object(W,'check',side_effect=lambda now:([],False));p.start();self.addCleanup(p.stop)
        for obj,name,value in [(W.C,'load_sched',{}),(W.C,'allowed',True)]:
            p=patch.object(obj,name,return_value=value);p.start();self.addCleanup(p.stop)
        self.send=patch.object(W.N,'send').start();self.addCleanup(patch.stopall)
        self.command=patch.object(W.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')).start()

    def test_web_stale_restarts_only_web_and_rate_limits(self):
        with patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):
            W.main();W.main()
            self.send.assert_called_once();self.command.assert_called_once()
            W.main()
        self.assertEqual(self.command.call_count,1)
        self.assertEqual(self.command.call_args.args[0],['sudo','-n','systemctl','try-restart','hanjari-web'])
        self.assertEqual(self.send.call_count,1)
        self.assertIn('rollback',self.send.call_args.args[0])

    def test_web_missing_model_alerts_without_restarting_collector(self):
        with patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'missing'}}):W.main();W.main()
        self.command.assert_not_called();self.send.assert_called_once()

    def test_connection_failure_is_deduplicated(self):
        with patch.object(W,'web_health',side_effect=OSError('refused')):
            W.main();W.main();self.send.assert_called_once();W.main()
        self.send.assert_called_once();self.command.assert_not_called()

    def test_collector_stale_and_web_stale_have_independent_limits(self):
        with patch.object(W,'check',return_value=(['sb02 새 데이터 없음'],True)), \
             patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):W.main()
        self.assertEqual([c.args[0][-1] for c in self.command.call_args_list],['hanjari-collect'])
        with patch.object(W,'check',return_value=(['sb02 새 데이터 없음'],True)), \
             patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):W.main()
        commands=[c.args[0][-1] for c in self.command.call_args_list]
        self.assertEqual(commands,['hanjari-collect','hanjari-web'])
        state=json.loads(self.state.read_text())
        self.assertIn('restarted',state);self.assertIn('web_restarted',state)

    def test_first_web_failure_only_prints_without_alert_or_restart(self):
        for failure in [{'ready':False,'model':{'status':'stale'}},
                        {'ready':False,'model':{'status':'missing'}},OSError('refused')]:
            with self.subTest(failure=failure):
                self.state.unlink(missing_ok=True);self.send.reset_mock();self.command.reset_mock()
                with patch.object(W,'web_health',side_effect=[failure]),patch('builtins.print') as output:
                    W.main()
                self.send.assert_not_called();self.command.assert_not_called()
                state=json.loads(self.state.read_text())
                self.assertEqual(state['web_failures'],1);self.assertEqual(state['open'],[])
                self.assertTrue(any('웹 감시 1회 실패' in str(c) for c in output.call_args_list))

    def test_ready_resets_failures_and_preserves_recovery_alert(self):
        for failure in [{'ready':False,'model':{'status':'stale'}},OSError('refused')]:
            with self.subTest(failure=failure):
                self.state.unlink(missing_ok=True);self.send.reset_mock();self.command.reset_mock()
                with patch.object(W,'web_health',side_effect=[failure,{'ready':True},failure,failure,{'ready':True},failure]):
                    W.main();W.main()
                    self.assertEqual(json.loads(self.state.read_text())['web_failures'],0)
                    W.main()
                    self.send.assert_not_called();self.command.assert_not_called()
                    W.main()
                    self.send.assert_called_once();self.assertEqual(self.send.call_args.args[1],'ERROR')
                    W.main()
                    self.assertEqual(json.loads(self.state.read_text())['web_failures'],0)
                    self.assertEqual(self.send.call_args.args[1],'INFO')
                    self.assertIn('복구됨',self.send.call_args.args[0])
                    calls=self.command.call_count
                    W.main()
                    self.assertEqual(json.loads(self.state.read_text())['web_failures'],1)
                    self.assertEqual(self.send.call_count,2);self.assertEqual(self.command.call_count,calls)

    def test_invalid_web_failure_count_uses_corrupt_state_recovery(self):
        for value in [True,False,None,'1',1.5,[],{}]:
            with self.subTest(value=value):
                self.state.write_text(json.dumps({'web_failures':value}))
                self.send.reset_mock()
                with patch.object(W,'web_health',return_value={'ready':True}):W.main()
                self.send.assert_called_once();self.assertEqual(self.send.call_args.args[1],'WARN')
                self.assertEqual(len(list(self.root.glob('watchdog.json.corrupt-*'))),1)
                state=json.loads(self.state.read_text())
                self.assertEqual(state['web_failures'],0)
                self.assertIn('web_restarted',state)

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
             patch.object(W,'web_health',return_value={'ready':False,'model':{'status':'stale'}}):W.main();W.main()
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
