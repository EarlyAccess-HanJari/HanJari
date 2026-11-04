# 운영 구성 안내

## 현재 서버에서 확인한 구성

확인 시각: 2026년 11월 5일(KST).

- 웹: `/home/ubuntu/hanjari-releases/practical-20261104-v7/hanjari-web/backend`. 실행 환경은 `/home/ubuntu/hanjari-web/backend/.venv`를 사용합니다.
- 웹의 AI 코드: `/home/ubuntu/hanjari-releases/practical-20261104-v7/hanjari-ml`. 경로는 `installed/hanjari-web.service.d/20261102-freshness.conf`가 지정합니다.
- v7은 커밋 `b3f0134`로 11월 4일 18:20(KST)에 전환했습니다. 되돌릴 때 쓰는 v6 설정은 v7 폴더의 `previous-service.conf`에 있습니다.
- 이 레포의 `serve.py`·`train.py`는 서버 두 폴더의 변경을 합친 코드입니다. 서버의 웹(v7)에는 메모리 수정(PR #11)이 없고, 매일 작업 폴더에는 다음 버스 응답(`eta2_sec`)이 없습니다. 웹을 `/home/ubuntu/hanjari-ml`로 돌리면 다음 버스 표시가 사라집니다.
- 릴리스의 `hanjari-ml/models`와 `hanjari-ml/data`는 `/home/ubuntu/hanjari-ml` 아래를 가리키는 심볼릭 링크입니다. 따라서 매일 작업이 모델을 교체하면 웹 재시작 후 웹에도 반영되며, 그 뒤에는 `models/lite`가 Git과 달라질 수 있습니다.
- 매일 작업: `/home/ubuntu/hanjari-ml`
- 수집기: `/home/ubuntu/hanjari`. 코드는 `hanjari/src/`와 같습니다.
- 품질 점검: `/home/ubuntu/hanjari-quality`, `validation-20261103-v4` 릴리스를 가리키는 링크입니다.
- HTTPS: `installed/nginx-hanjari.conf`가 443 포트를 받아 8000 포트로 전달합니다. 인증서 갱신은 `installed/hanjari-cert-renew.*`가 맡습니다.

API 키가 든 `.env`, 인증서 개인키, SSH 키, 수집 로그, 가상환경, 과거 모델과 백업은 Git에 올리지 않습니다.

## 2026년 10월 19일에 확인한 구성

확인 시각: 2026년 10월 19일 09:25(KST).

- 수집기: `/home/ubuntu/hanjari`, 시스템 Python 3.10.12
- 웹: `/home/ubuntu/hanjari-web/backend`, Python 3.11.16
- AI: `/home/ubuntu/hanjari-ml`, Python 3.11.16
- 웹 환경 변수: `HANJARI_ML=/home/ubuntu/hanjari-ml`, `HANJARI_MODE=latest`
- AI의 `data/api_logs`는 수집기의 `/home/ubuntu/hanjari/data/api_logs`를 가리키는 심볼릭 링크입니다.

수집기와 웹 서비스, 일일 작업·감시 타이머가 활성 상태였으며 `/api/health`는 `status=ok`, `mode=latest`로 응답했습니다.

`installed/`에는 실제 설치된 systemd와 nginx 설정을 보관했습니다. 경로가 운영 서버 기준이므로 다른 PC에 그대로 적용하지 않습니다. 이 사본에는 매일 작업 후 웹 서비스를 재시작하는 설정이 포함됩니다.

## 실시간 조회와 재학습

기본 샘플 실행에는 키가 필요 없습니다. 별도 환경에서 실시간 조회를 구성하려면 아래 준비가 필요합니다.

1. `hanjari/.env.example`을 `.env`로 복사하고 본인의 버스 API 키를 입력합니다. 실제 키는 Git에 올리지 않습니다.
2. 수집기가 만든 자료를 `hanjari-ml/data/api_logs`에서도 읽을 수 있도록 폴더를 연결합니다. 운영 서버의 링크 대상은 위와 같습니다.
3. 최신 수집 자료가 준비된 뒤 로컬 실행기에 `--mode latest`를 지정합니다. 이 옵션만으로 수집기가 시작되지는 않습니다.

키 개수에 따라 수집 간격이 달라집니다. 기존 서버는 네 개의 키 변수를 사용하고 있었으며 값은 내보내지 않았습니다.

재학습에는 별도로 누적 수집 자료가 필요합니다. 이 자료에는 현재 모델, 노선별 통계와 단일 시점 샘플만 포함되어 있어 과거 학습 전체를 그대로 재현할 수는 없습니다. 제외한 `dataset.csv`는 수집 자료로 다시 생성하는 파일입니다.

원래의 DVC 파일은 보존했지만 DVC 저장소 설정과 캐시는 포함하지 않았습니다. 포함된 CSV와 현재 모델로 샘플 실행은 가능하며, `dvc pull`은 별도 저장소 연결 없이 바로 사용할 수 없습니다.

## 원본과 정리본의 차이

애플리케이션 코드, 모델, 배포 화면은 내려받은 내용을 그대로 보존했습니다. `hanjari-ml/.gitignore`만 노선별 통계 CSV 네 개가 새 저장소에 포함되도록 조정했습니다.

최상위 실행 안내, 제외 규칙, 실행기, 의존성 버전 목록과 검증 기록을 추가했습니다. 서버 파일별 원본 SHA-256은 `SERVER_SNAPSHOT.json`에 기록했습니다.

`hanjari-ml/ops/install.sh`는 기존 설치 스크립트입니다. 실행하면 시스템 설정과 서비스가 바뀌므로 로컬 확인 절차에는 사용하지 않습니다. `ops/systemd/`의 템플릿과 `installed/`의 실제 설정도 구분해야 합니다.

추가 확인 결과, 로컬 프론트엔드 소스의 운영용 빌드가 서버 파일 6개와 모두 일치해 `hanjari-web/frontend/`에 원본을 추가했습니다. 해당 폴더의 README를 현재 구성에 맞게 정리하고 `.gitignore`에서 배포본도 보관하도록 조정했습니다. 세부 근거는 `FRONTEND_MATCH.md`에 기록했습니다. 이 일치 확인은 소스의 빌드 결과에 대한 검증이며, 특정 Git 커밋과의 연결을 확정한 것은 아닙니다.
