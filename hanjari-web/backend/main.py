"""한자리 백엔드 — AI 예측(레포 src/serve.py)을 HTTP 로 내준다. AI 코드는 고치지 않고 import 만 한다.
frontend/dist 가 있으면(npm run build:prod) 화면도 같이 내준다 → 서버 하나로 전체 서비스.

환경 변수
  HANJARI_ML    AI 레포 폴더. 기본: 이 파일의 상위 폴더(레포 루트)
  HANJARI_MODE  sample(기본) 레포에 든 9/30 13:11 실제 스냅샷 — 키·서버·API 호출 없이 개발용
                latest       수집기가 방금 저장한 스냅샷 — 운영 서버(161.33.132.80) 전용, API 호출 없음

실행: uvicorn main:app --port 8000   (워커 1개. 모델을 메모리에 약 400MB 올림)
"""
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
ML = Path(os.environ.get("HANJARI_ML", ROOT))
DIST = ROOT / "frontend" / "dist"
MODE = os.environ.get("HANJARI_MODE", "sample")
if MODE not in ("sample", "latest"):
    raise SystemExit(f"HANJARI_MODE 는 sample 또는 latest (지금: {MODE})")

sys.path.insert(0, str(ML / "src"))
import serve  # noqa: E402

log = logging.getLogger("hanjari")

# serve.predict_live 는 모듈 전역(B.LOG, T.CAP_OBS)을 바꿔치기하며 돌아서, 두 요청이 겹치면 결과가 섞인다
_lock = threading.Lock()


def _predict(n: int) -> list[dict]:
    with _lock:
        if MODE == "latest":
            return serve.predict_latest(n)
        return serve.predict_live(n, log_dir=serve.SAMPLE)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        _predict(0)  # 모델을 미리 읽어 첫 사용자가 몇 초씩 기다리지 않게
    except Exception:
        log.exception("워밍업 실패 — 요청이 오면 다시 시도함")
    yield


app = FastAPI(title="한자리 API", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": MODE}


@app.get("/api/predict")
def predict(n: int):
    """n: 내 앞 대기 인원(0~40). 결과가 빈 배열이면 운행 시간 아님(새벽)."""
    try:
        serve.check_n(n)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        results = _predict(n)
    except Exception as e:  # 스냅샷 없음·버스 API 오류 등 — 프론트는 503 을 '서버 연결 안 됨'으로 보여줌
        log.exception("예측 실패")
        raise HTTPException(503, f"예측 실패: {e}")
    return {"n_ahead": n, "results": results}


# /api 라우트 뒤에 붙여야 /api 가 가려지지 않음. 운영 서버에선 nginx 가 이 역할을 함
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
