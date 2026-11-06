"""한자리 백엔드 — AI 예측(레포 src/serve.py)을 HTTP 로 내준다. AI 코드는 고치지 않고 import 만 한다.
frontend/dist 가 있으면(npm run build:prod) 화면도 같이 내준다 → 서버 하나로 전체 서비스.

환경 변수
  HANJARI_ML    AI 폴더. 기본: hanjari-web 옆의 hanjari-ml 폴더
  HANJARI_MODE  sample(기본) 레포에 든 9/30 13:11 실제 스냅샷 — 키·서버·API 호출 없이 개발용
                latest       수집기가 방금 저장한 스냅샷 — 운영 서버(161.33.132.80) 전용, API 호출 없음

실행: uvicorn main:app --port 8000   (워커 1개. 모델을 메모리에 약 400MB 올림)
"""
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

_import_started = time.perf_counter()
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
ML = Path(os.environ.get("HANJARI_ML", ROOT.parent / "hanjari-ml"))
DIST = ROOT / "frontend" / "dist"
MODE = os.environ.get("HANJARI_MODE", "sample")
RELEASE = os.environ.get("HANJARI_RELEASE", "development")
if MODE not in ("sample", "latest"):
    raise SystemExit(f"HANJARI_MODE 는 sample 또는 latest (지금: {MODE})")

sys.path.insert(0, str(ML / "src"))
import serve  # noqa: E402

log = logging.getLogger("hanjari")
_import_seconds = time.perf_counter() - _import_started

# serve.predict_live 는 모듈 전역을 바꿔치기하며 돌아서, 두 요청이 겹치면 결과가 섞인다
_lock = threading.Lock()


def _predict(n: int) -> list[dict]:
    with _lock:
        if MODE == "latest":
            return serve.predict_latest(n)
        return serve.predict_live(n, log_dir=serve.SAMPLE)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info('startup import=%.3fs', _import_seconds)
    try:
        started = time.perf_counter()
        if serve.DQ.boarding_policy()['enabled']:
            serve.load(True)
        log.info('startup model_load=%.3fs', time.perf_counter() - started)
        started = time.perf_counter()
        _predict(0)  # 모델을 미리 읽어 첫 사용자가 몇 초씩 기다리지 않게
        log.info('startup first_prediction=%.3fs', time.perf_counter() - started)
    except Exception:
        log.exception("워밍업 실패 — 요청이 오면 다시 시도함")
    yield


app = FastAPI(title="한자리 API", lifespan=lifespan)


@app.middleware("http")
async def prevent_prediction_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-HanJari-Release"] = RELEASE
    return response


@app.get("/api/health")
def health():
    try:
        routes = serve.source_health() if MODE == "latest" else {}
        model = serve.model_status()
    except Exception:
        log.exception('상태 확인 실패')
        routes, model = {}, {'status': 'broken', 'loaded': None, 'disk': None}
    inactive = bool(routes) and all(r['status'] == 'outside_service' for r in routes.values())
    ready = model['status'] in ('ok', 'not_required') or (model['status'] == 'not_loaded' and inactive)
    return {"status": "ok" if ready else "degraded", "mode": MODE, "release": RELEASE,
            "data_status": "degraded" if any(r["status"] in ("missing", "stale") for r in routes.values()) else "ok",
            "routes": routes, "model": model, "ready": ready}


@app.get("/api/predict")
def predict(n: int):
    """n: 내 앞 대기 인원(0~40). 결과가 빈 배열이면 운행 시간 아님(새벽)."""
    try:
        serve.check_n(n)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        results = _predict(n)
    except serve.NoSnapshotError:
        results = []  # 수집 실패를 운행 종료나 웹 서버 장애로 안내하지 않는다.
    except Exception as e:  # 스냅샷 없음·버스 API 오류 등 — 프론트는 503 을 '서버 연결 안 됨'으로 보여줌
        log.exception("예측 실패")
        raise HTTPException(503, f"예측 실패: {e}")
    return {"n_ahead": n, "results": results, "service": health()}


# /api 라우트 뒤에 붙여야 /api 가 가려지지 않음. 운영 서버에선 nginx 가 이 역할을 함
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
