import concurrent.futures
import threading
import time
import unittest
from unittest.mock import patch
from fastapi import HTTPException
import main as A


class Requests(unittest.TestCase):
    def test_lock_wait_budget_is_seven_seconds_and_timeout_is_503(self):
        self.assertEqual(A.LOCK_WAIT_SECONDS,7)
        with patch.object(A,'_lock') as lock:
            lock.acquire.return_value=False
            with self.assertRaises(HTTPException) as caught:A._predict(20)
        self.assertEqual(caught.exception.status_code,503)
        self.assertLessEqual(lock.acquire.call_args.kwargs['timeout'],7)
        lock.release.assert_not_called()

    def test_same_n_inflight_requests_compute_once(self):
        entered=threading.Event();release=threading.Event();barrier=threading.Barrier(5)
        def compute(n,**kw):entered.set();release.wait(2);return [{'n':n}]
        with patch.object(A,'MODE','sample'),patch.object(A.serve,'predict_live',side_effect=compute) as prediction:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                def call():barrier.wait();return A._predict(21)
                futures=[pool.submit(call) for _ in range(5)]
                self.assertTrue(entered.wait(1));time.sleep(.05);release.set()
                values=[f.result() for f in futures]
        self.assertEqual(prediction.call_count,1)
        self.assertTrue(all(v==[{'n':21}] for v in values))
        values[0][0]['n']=0
        self.assertEqual(values[1][0]['n'],21)

    def test_completed_results_do_not_cache_later_sequential_requests(self):
        with patch.object(A,'MODE','sample'),patch.object(A.serve,'predict_live',return_value=[]) as prediction:
            A._predict(22);A._predict(22)
        self.assertEqual(prediction.call_count,2)

    def test_slow_request_logs_wait_compute_and_rss_without_sleeping(self):
        clock=[0.0]
        def compute(*args,**kwargs):clock[0]+=3;return []
        with patch.object(A.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(A,'MODE','sample'),patch.object(A.serve,'predict_live',side_effect=compute), \
             self.assertLogs(A.log,level='WARNING') as logs:
            A._predict(23)
        self.assertIn('compute=3.000s',logs.output[0]);self.assertIn('rss_mib=',logs.output[0])
        self.assertGreater(A.rss_mib(),0)


if __name__=='__main__':unittest.main()
