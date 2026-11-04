# 운영 구성 안내

계획 기준: [PRD v1.8·WBS v1.11·마일스톤 v1.4(2026-11-05)](../docs/plan/).

마감 일정: 문서·발표자료 초안 11/24~11/26, 최종 시험·보안 점검 11/27~11/30, 기술보고서·관련 문서 11/27~12/1. 11/27 이후 새 기능은 추가하지 않으며 12/2~12/8은 시연 준비·치명적 오류 수정만 합니다. 최종발표 12/9, 제출일은 수업 공지 확인.

## 현재 운영 구성

확인 날짜: 2026-11-05. 05:04(KST)에 `main` 커밋 `2fcffa1`의 웹 `practical-20261105-v8`로 전환했습니다. 전환 후 HTTPS 정상·공개 8000 무응답을 확인했습니다. nginx와 인증서는 변경하지 않았으며, 일반 HTTP 요청의 HTTPS 308 이동도 유지합니다.

- 웹: `/home/ubuntu/hanjari-releases/practical-20261105-v8/hanjari-web/backend`. 실행 환경은 `/home/ubuntu/hanjari-web/backend/.venv`를 사용합니다.
- 웹의 AI 코드: `/home/ubuntu/hanjari-releases/practical-20261105-v8/hanjari-ml`. 경로는 `installed/hanjari-web.service.d/20261102-freshness.conf`가 지정합니다.
- v7 릴리스는 되돌리기용으로 남겨 두었습니다. v7 설정은 v8 폴더의 `previous-service.conf`에 있습니다.
- `main`(`2fcffa1`), 웹 v8, 재학습 폴더 `~/hanjari-ml`의 `serve.py`·`train.py`가 같습니다. 웹과 재학습은 계속 서로 다른 폴더를 사용합니다.
- 재학습 폴더의 `src/serve.py`와 `tests/test_data_quality.py`를 같은 코드로 맞췄습니다. 교체 전 파일은 `~/hanjari-backups/daily-20261105-050434`에 보관했습니다.
- v8 검증: 서버 ML 테스트 114개, 백엔드 테스트 2개와 `serve.py check`를 통과했습니다. 샘플 자료에서 6개 정류장 모두 `eta2_sec`를 확인했고, 전환 후 HTTPS 정상·공개 8000 무응답을 확인했습니다. 실제 운행 시간의 화면은 아직 확인 전입니다.
- 릴리스의 `hanjari-ml/models`와 `hanjari-ml/data`는 `/home/ubuntu/hanjari-ml` 아래를 가리키는 심볼릭 링크입니다. 따라서 매일 작업이 모델을 교체하면 웹 재시작 후 웹에도 반영되며, 그 뒤에는 `models/lite`가 Git과 달라질 수 있습니다.
- 매일 작업: `/home/ubuntu/hanjari-ml`
- 관측용 모델 보관: 자동 재학습은 계속하며 서비스 모델을 고정하지 않습니다. 최지용이 11/8 관측 전 모델과 11/9~11/13 관측 기간 모델 버전을 복사해 보관합니다. 최근 7개 버전만 남기는 정리에서 보관본이 삭제되지 않게 하고, 기록표 시각과 `models.csv`로 예측 모델을 찾습니다. 보관 작업은 아직 미실시입니다.
- 수집기: `/home/ubuntu/hanjari`. 코드는 `hanjari/src/`와 같습니다.
- 품질 점검: `/home/ubuntu/hanjari-quality`, `validation-20261103-v4` 릴리스를 가리키는 링크입니다.
- HTTPS: `https://161.33.132.80/`. `installed/nginx-hanjari.conf`가 443 포트를 받아 내부 `127.0.0.1:8000`으로 전달합니다. 80의 일반 요청은 HTTPS로 308 이동하며 인증서 검증용 ACME 경로는 예외입니다. 인증서 갱신은 `installed/hanjari-cert-renew.*`가 맡습니다.
- 11/5 03:34(KST): uvicorn을 `127.0.0.1:8000`에만 바인딩하고 서버 방화벽의 8000 허용 규칙을 제거했습니다. 외부에서 `http://161.33.132.80:8000/`의 응답이 없음을 확인했으며, 서비스 주소는 `https://161.33.132.80/`입니다.
- 남은 접근 설정 점검은 11/8, 앱·모델 복구 검증은 11/13 예정입니다. 공개 8000 차단 완료가 이 검증의 완료를 뜻하지 않습니다.

### 웹 v8을 v7로 되돌리기

1. `~/hanjari-releases/practical-20261105-v8/previous-service.conf`의 대상이 v7인지와 uvicorn의 `127.0.0.1:8000` 바인딩을 확인합니다.
2. 이 파일을 `/etc/systemd/system/hanjari-web.service.d/20261102-freshness.conf`로 복원하고 `sudo systemctl daemon-reload`, `sudo systemctl restart hanjari-web`을 실행합니다.
3. 서비스의 v7 경로, HTTPS 응답, 다음 버스 표시와 공개 8000 무응답을 다시 확인합니다. 웹 릴리스 복원은 재학습 폴더의 코드나 모델을 복원하지 않습니다.

### 공개 8000 차단 설정 되돌리기

서버의 `~/hanjari-backups/close-8000-20261105-033411` 백업은 계속 유효합니다. 다만 **이 백업의 웹 설정은 v7을 가리키므로, 그대로 복원하면 웹도 v7로 돌아갈 수 있습니다.** v8 → v7 웹 릴리스 복원용 `previous-service.conf`와 목적이 다릅니다. 복원 전 대상 릴리스·바인딩·방화벽 규칙을 확인하고, 복원 후 nginx 연결과 외부 접근 범위를 다시 검증합니다. 실제 복구 성공 여부는 아직 확인 전입니다.

API 키가 든 `.env`, 인증서 개인키, SSH 키, 수집 로그, 가상환경, 과거 모델과 백업은 Git에 올리지 않습니다.

## 이전 웹 릴리스 전환 기록

- v7은 커밋 `b3f0134`로 11월 4일 18:20(KST)에 전환했습니다. 되돌릴 때 쓰는 v6 설정은 v7 폴더의 `previous-service.conf`에 있습니다.

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

## 초기 저장소 정리 기록 (2026년 10월 19일)

애플리케이션 코드, 모델, 배포 화면은 내려받은 내용을 그대로 보존했습니다. `hanjari-ml/.gitignore`만 노선별 통계 CSV 네 개가 새 저장소에 포함되도록 조정했습니다.

최상위 실행 안내, 제외 규칙, 실행기, 의존성 버전 목록과 검증 기록을 추가했습니다. 서버 파일별 원본 SHA-256은 `SERVER_SNAPSHOT.json`에 기록했습니다.

`hanjari-ml/ops/install.sh`는 기존 설치 스크립트입니다. 실행하면 시스템 설정과 서비스가 바뀌므로 로컬 확인 절차에는 사용하지 않습니다. `ops/systemd/`의 템플릿과 `installed/`의 실제 설정도 구분해야 합니다.

추가 확인 결과, 로컬 프론트엔드 소스의 운영용 빌드가 서버 파일 6개와 모두 일치해 `hanjari-web/frontend/`에 원본을 추가했습니다. 해당 폴더의 README를 현재 구성에 맞게 정리하고 `.gitignore`에서 배포본도 보관하도록 조정했습니다. 세부 근거는 `FRONTEND_MATCH.md`에 기록했습니다. 이 일치 확인은 소스의 빌드 결과에 대한 검증이며, 특정 Git 커밋과의 연결을 확정한 것은 아닙니다.
