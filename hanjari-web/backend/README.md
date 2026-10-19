# 한자리 백엔드 (FastAPI)

AI 예측(레포 `src/serve.py`, 모델 `models/lite/`)을 HTTP로 내준다. AI 코드는 import만 하고 고치지 않는다.
`frontend/dist`가 있으면 화면도 같이 내준다 → 서버 하나로 전체 서비스.

| API | 응답 |
|---|---|
| `GET /api/health` | `{"status":"ok","mode":"sample"}` |
| `GET /api/predict?n=3` | `{"n_ahead":3,"results":[정류장 6곳]}` · 새벽엔 `results: []` |
| n 이 0~40 밖 | 400 `{"detail":"n_ahead 는 0~40 정수"}` |
| n 이 숫자 아님 | 422 (FastAPI 기본) |
| 예측 실패(스냅샷 없음 등) | 503 |

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `HANJARI_ML` | 레포 루트(이 폴더의 상위) | `src/serve.py`·`models/`가 있는 곳 |
| `HANJARI_MODE` | `sample` | `sample` = 레포의 9/30 13:11 실제 스냅샷(키·서버 불필요) / `latest` = 수집기 최신 스냅샷(운영 서버 전용) |

## 운영 서버에서 (나중에)
- `HANJARI_MODE=latest`. Python 3.11 별도 venv (AI용 `.venv`에 설치 금지), uvicorn 워커 1개, `127.0.0.1:8000`에만 열고 nginx 가 `/api`와 `dist/`를 맡음
- 매일 03:00 재시작 (01:00 새 모델 교체, 한 번 읽은 모델은 메모리에 남음)

## 주의
- `serve.predict_live`가 모듈 전역을 바꿔치기해서 요청을 Lock 으로 한 번에 하나씩 처리한다 (동시 12건 = 순차 결과와 같음 확인)
- 예측 1회 약 0.1초 (sample)
