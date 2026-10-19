# 한자리 · 얼리액세스

버스 도착 정보와 AI 예측을 이용해 정류장에서 탑승 가능성을 안내하는 팀 프로젝트입니다.

이 폴더는 **2026년 10월 19일 09:22(KST) 운영 서버에서 내려받은 파일**을 새 저장소에 올리기 위해 정리한 것입니다. 운영 서버의 파일이나 서비스를 변경하지 않았습니다.

## 포함한 내용

- `hanjari/`: 버스 정보 수집기
- `hanjari-web/backend/`: FastAPI 서버
- `hanjari-web/frontend/`: 서버 배포본과 일치 확인한 화면 원본·빌드 설정·테스트
- `hanjari-web/frontend/dist/`: 실제 배포된 화면
- `hanjari-ml/`: 예측·학습 코드, 현재 모델, 노선별 통계, 샘플 데이터
- `deployment/installed/`: 서버에 설치된 서비스·타이머 설정 사본

**프론트엔드 원본을 추가했습니다.** 로컬 소스를 `npm ci`와 `npm run build:prod`로 빌드한 결과가 현재 서버의 파일 6개와 SHA-256 기준으로 모두 일치했습니다. 원본·잠금 파일·현재 배포본을 함께 보관합니다. [프론트엔드 실행·재빌드 안내](hanjari-web/frontend/README.md)를 참고하세요.

API 키, 실제 `.env`, 개인 SSH 키, 가상환경, 수집 로그, 생성된 학습 데이터, 과거 모델, 캐시와 백업은 제외했습니다. 기본 실행에 필요한 현재 모델과 노선별 통계 CSV는 포함했습니다.

## 내 PC에서 실행하기

운영 환경은 Python **3.11.16**입니다. 아래 명령은 저장소 최상위 폴더에서 실행합니다.

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe scripts/run_local.py
```

macOS / Linux:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python scripts/run_local.py
```

브라우저에서 http://127.0.0.1:8000 을 엽니다. 종료는 `Ctrl+C`입니다.

기본값은 **샘플 모드**입니다. 2026년 9월 30일 13:11:33의 저장 자료로 예측하므로 현재 버스 상황을 보여 주지는 않습니다. API 키와 외부 버스 API 호출 없이 화면과 예측 연결을 확인할 수 있습니다. 이 명령은 수집기나 자동 학습을 시작하지 않습니다.

- `/api/health`: 웹 서버 응답과 실행 모드 확인. 예측 성공까지 보장하는 검사는 아닙니다.
- `/api/predict?n=3`: 앞 대기 인원 3명에 대한 예측. 입력 범위는 0~40명입니다.

실시간 모드와 재학습에 필요한 자료는 [운영 구성 안내](deployment/README.md)를 참고하세요. 기존 하위 README와 문서는 작성 당시 설명이므로 현재 내보내기 구성은 이 안내를 우선합니다.

## 새 저장소 main에 올리기

GitHub에서 README·`.gitignore`·라이선스를 추가하지 않은 **빈 저장소**를 만든 뒤, 이 폴더에서 진행합니다. `.env`에 실제 키를 넣었다면 업로드 대상에 없는지 확인하세요.

```sh
git init -b main
git add .
git status --short
git commit -m "Import running server snapshot (2026-10-19)"
git remote add origin <새 저장소 URL>
git push -u origin main
```

`<새 저장소 URL>`을 `earlyaccess-hanjari` 조직에서 만든 저장소 주소로 바꿉니다. 이미 파일이나 커밋이 있는 원격 저장소라면 위 절차를 그대로 진행하거나 강제로 덮어쓰지 말고 이력을 먼저 확인합니다.

이 폴더에는 `.git`이 없으며 새 저장소의 첫 커밋으로 등록됩니다. 기존 팀원의 개발 이력은 [기존 저장소](https://github.com/YONGJI04/hanjari-ai)에서 확인합니다. 새 저장소만으로 과거 팀 기여 이력이 이어지지는 않습니다.

GitHub 업로드와 기존 저장소·운영 서버 변경은 이 자료 정리 과정에서 수행하지 않았습니다.

## 파일 확인 기록

- [서버 구성과 파일 해시](deployment/SERVER_SNAPSHOT.json)
- [로컬 검증 결과](deployment/VALIDATION.md)
- [프론트엔드 일치 확인](deployment/FRONTEND_MATCH.md)
