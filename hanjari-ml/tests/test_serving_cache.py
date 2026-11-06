import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import build_dataset as B
import serve as S
import train as T


class ServingCache(unittest.TestCase):
    def test_csv_mtime_refresh_and_defensive_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'calendar.csv';p.write_text('x\n1\n')
            first=T.read_table(p);first.loc[0,'x']='changed'
            self.assertEqual(T.read_table(p).loc[0,'x'],'1')
            p.write_text('x\n222\n')
            self.assertEqual(T.read_table(p).loc[0,'x'],'222')

    def test_snapshot_reads_once_per_request_and_invalidates_changed_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'snapshot.json'
            def write(n):p.write_text(json.dumps({'msgHeader':{'headerCd':'0'},'msgBody':{'itemList':[{'x':n}]}}))
            write(1)
            with B.request_cache(),patch.object(B.json,'load',wraps=B.json.load) as read:
                item=B.read_items(p);item[0]['x']=100
                self.assertEqual(B.read_items(p)[0]['x'],1)
                self.assertEqual(read.call_count,1)
                write(222)
                self.assertEqual(B.read_items(p)[0]['x'],222)
                self.assertEqual(read.call_count,2)
            with patch.object(B.json,'load',wraps=B.json.load) as read:
                B.read_items(p);self.assertEqual(read.call_count,1)

    def test_inference_cache_requires_same_rows_and_model_and_returns_copies(self):
        rows=[{'x':1}];model={};meta={'cats':{},'created':'v1'}
        values=(np.array([1.]),np.ones((1,41)),np.ones((1,9)))
        with patch.object(T,'features',return_value=pd.DataFrame({'x':[1]})), \
             patch.object(T,'predict',return_value=values) as predict:
            a=S._run_inference(rows,model,meta,False)
            a[1][0]=900
            b=S._run_inference(rows,model,meta,False)
            self.assertEqual(b[1][0],1);self.assertEqual(predict.call_count,1)
            S._run_inference(rows,model,dict(meta,created='v2'),False)
            S._run_inference([{'x':2}],model,meta,False)
            S._run_inference(rows,{},meta,False)
            self.assertEqual(predict.call_count,4)
            for i in range(20):S._run_inference([{'x':i}],model,meta,False)
            self.assertLessEqual(S.inference_cache_info()['size'],8)


if __name__=='__main__':unittest.main()
