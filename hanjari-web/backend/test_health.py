import asyncio
import json
import unittest
from unittest.mock import patch
import main as A


async def get(path,query=b''):
    messages=[];received=False
    async def receive():
        nonlocal received
        if not received:
            received=True
            return {'type':'http.request','body':b'','more_body':False}
        await asyncio.Event().wait()
    async def send(message):messages.append(message)
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','scheme':'http',
           'path':path,'raw_path':path.encode(),'query_string':query,'root_path':'','headers':[],
           'client':('127.0.0.1',1),'server':('localhost',80)}
    await A.app(scope,receive,send)
    return next(m['status'] for m in messages if m['type']=='http.response.start'),json.loads(b''.join(m.get('body',b'') for m in messages))


class Health(unittest.TestCase):
    def test_missing_model_health_200_predict_503(self):
        with patch.object(A.serve,'model_status',return_value={'status':'missing','loaded':None,'disk':None}), \
             patch.object(A.serve,'source_health',return_value={}),patch.object(A,'MODE','latest'), \
             patch.object(A,'_predict',side_effect=FileNotFoundError('model')):
            status,body=asyncio.run(get('/api/health'))
            self.assertEqual(status,200);self.assertFalse(body['ready']);self.assertEqual(body['status'],'degraded')
            self.assertEqual(asyncio.run(get('/api/predict',b'n=3'))[0],503)

    def test_inactive_not_loaded_is_ready_and_does_not_wait_for_prediction_lock(self):
        with patch.object(A.serve,'model_status',return_value={'status':'not_loaded','loaded':None,'disk':'v1'}), \
             patch.object(A.serve,'source_health',return_value={'sb02':{'status':'outside_service'},'jr03':{'status':'outside_service'}}), \
             patch.object(A,'MODE','latest'):
            with A._lock:
                result=A.health()
            self.assertTrue(result['ready']);self.assertEqual(result['status'],'ok')

    def test_warmup_loads_model_even_when_no_routes_are_active(self):
        events=[]
        with patch.object(A.serve.DQ,'boarding_policy',return_value={'enabled':True}), \
             patch.object(A.serve,'load',side_effect=lambda *a:events.append('load')), \
             patch.object(A,'_predict',side_effect=lambda n:events.append('predict')):
            async def start():
                async with A.lifespan(A.app):pass
            asyncio.run(start())
        self.assertEqual(events,['load','predict'])


if __name__=='__main__':unittest.main()
