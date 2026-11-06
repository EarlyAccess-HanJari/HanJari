# 한자리 백엔드 (FastAPI)

AI 예측(레포 `src/serve.py`, 모델 `models/lite/`)을 HTTP로 내준다. AI 코드는 import만 하고 고치지 않는다.
`frontend/dist`가 있으면 화면도 같이 내준다 → 서버 하나로 전체 서비스.

| API | 응답 |
|---|---|
| `GET /api/health` | `{"status":"ok","mode":"sample"}` |
| `GET /api/predict?n=3` | `{"n_ahead":3,"results":[정류장 6곳]}` · 새벽엔 `results: []` |
| 다음 버스 | 결과의 `eta2_sec`(도착까지 초). 다음 버스가 없으면 `null` |
| 장애 대체 안내 | 정보가 오래돼 보류된 결과에만 `fallback`(마지막 정보 추정 또는 평소 이 시간). 기존 필드는 그대로 보류. [형식·문구안](../../hanjari-ml/docs/OUTAGE_FALLBACK_20261105.md) |
| n 이 0~40 밖 | 400 `{"detail":"n_ahead 는 0~40 정수"}` |
| n 이 숫자 아님 | 422 (FastAPI 기본) |
| 예측 실패(스냅샷 없음 등) | 503 |

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `HANJARI_ML` | `hanjari-web` 옆의 `hanjari-ml` | `src/serve.py`·`models/`가 있는 곳. 실행한 작업 폴더와 무관하게 찾는다. |
| `HANJARI_MODE` | `sample` | `sample` = 레포의 9/30 13:11 실제 스냅샷(키·서버 불필요) / `latest` = 수집기 최신 스냅샷(운영 서버 전용) |

## 운영 서버에서 (나중에)
- `HANJARI_MODE=latest`. Python 3.11 별도 venv (AI용 `.venv`에 설치 금지), uvicorn 워커 1개, `127.0.0.1:8000`에만 열고 nginx 가 `/api`와 `dist/`를 맡음
- 매일 03:00 재시작 (01:00 새 모델 교체, 한 번 읽은 모델은 메모리에 남음)

## 주의
- `serve.predict_live`가 모듈 전역을 바꿔치기해서 요청을 Lock 으로 한 번에 하나씩 처리한다 (동시 12건 = 순차 결과와 같음 확인)
- 예측 1회 약 0.1초 (sample)

## 2026-11-02 응답 계약

보류 결과의 `load_pred`, `load_10`, `load_90`, `p_board`는 `null`입니다. `r_now`도 결측이면 `null`이며 0으로 대체하지 않습니다. `data_status`, `prediction_status`, `arrival_stale`, `vehicle_id`, `updated_at`, `source_updated`, `arrival_at`, `arrival_status`가 추가되었습니다. 정상 도착 안내는 유지하고 입력 불량·현장 미검증 인원 예측은 실행하지 않습니다. 최신 정상 도착 파일을 우선 사용하며 위치 파일을 기다리느라 이전 차량을 반환하지 않습니다. 정상 도착 파일 자체가 없으면 503입니다. ETA 만료/위치상 통과가 확인된 안내는 갱신 대기로 반환하고 모든 예측 응답에 `Cache-Control: no-store`를 설정합니다. [계약과 재개 절차](../../hanjari-ml/docs/CAPACITY_FIX_20261102.md)를 함께 검토하세요.
