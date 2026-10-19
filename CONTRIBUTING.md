# 한자리 협업 안내

**최신 main에서 작업을 시작하고, 확인한 변경만 PR로 합칩니다.** 모든 브랜치에 전체 코드를 유지하며 담당 폴더를 중심으로 수정합니다.

## 이번 작업 브랜치

| 브랜치 | 담당 | 작업 순서 |
| --- | --- | --- |
| `fe/ui-improvement` | 서재현 | [화면 사용성 개선](docs/work/frontend-ui/README.md) |
| `fe/status-guidance` | 황정원 | [오류·지연 안내 개선](docs/work/frontend-status/README.md) |
| `be/boarding-record` | 유민준 | [익명 탑승 결과 기록](docs/work/backend/README.md) |
| `ai/prediction-improvement` | 최지용 | [예측 모델 개선](docs/work/ai/README.md) |

프론트엔드 두 사람은 서로 다른 브랜치를 사용합니다. 같은 파일을 고칠 때는 수정 범위를 먼저 상의합니다. 브랜치는 작업 공간을 구분하는 것으로, 다른 폴더에 대한 수정 권한을 제한하지는 않습니다.

## 1. 처음 한 번 준비하기

저장소 접근 권한을 받은 GitHub 계정으로 로그인하고 아래 명령을 실행합니다. 이미 이 저장소를 내려받았다면 해당 폴더를 사용합니다.

```sh
git clone https://github.com/EarlyAccess-HanJari/HanJari.git
cd HanJari
git config user.name "본인 이름"
git config user.email "본인 GitHub 등록 이메일"
git fetch origin
```

이름과 이메일은 실제 본인 정보로 바꿉니다. 기본 샘플 실행에는 버스 API 키가 필요 없습니다.

### 로컬 프로그램 실행

Python 3.11을 설치한 뒤 저장소 최상위에서 실행합니다. 아래는 Windows PowerShell 기준입니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe scripts/run_local.py
```

macOS·Linux에서는 `python3.11 -m venv .venv`로 환경을 만들고 위의 Python 실행 경로를 `.venv/bin/python`으로 바꿉니다.

브라우저에서 http://127.0.0.1:8000 을 엽니다. 기본값은 과거 저장 자료를 사용하는 샘플 모드입니다. 현재 버스 상황은 아니며, 수집기나 자동 학습은 시작하지 않습니다. 프론트엔드 개발에는 Node.js 24도 준비합니다.

## 2. 담당 브랜치로 이동하기

위 표에서 자신의 작업 순서를 열어 브랜치 이동 명령을 실행합니다. 작업 전 `git status`로 현재 브랜치와 남은 변경을 확인합니다.

작업 중 최신 main을 반영할 때는 **자신의 변경을 먼저 커밋하고** 담당 브랜치에서 실행합니다.

```sh
git fetch origin
git merge origin/main
```

충돌이 나면 파일 내용을 확인하고 관련 담당자와 함께 정리합니다. 모르는 내용을 덮어쓰거나 강제 업로드하지 않습니다.

## 3. 수정·확인·업로드하기

역할별 README의 순서대로 작업하고 필요한 테스트를 진행합니다. 아래 명령은 저장소 최상위에서 실행하며, 경로와 메시지는 자신의 작업에 맞게 바꿉니다.

```sh
git status
git diff
git add 수정한파일경로
git diff --cached
git commit -m "변경 내용을 설명하는 문장"
git push
```

코드와 필요한 테스트·설정만 올립니다. 실제 `.env`, API 키, 수집 로그, 가상환경과 설치 패키지는 올리지 않습니다.

## 4. PR로 main에 합치기

GitHub에서 **Pull requests → New pull request**를 열고, `base: main`, `compare: 자신의 작업 브랜치`를 선택합니다.

PR에는 아래 세 가지를 짧게 적습니다.

- 무엇을 바꿨는지
- 어떻게 확인했는지: 실행 결과, 테스트 또는 화면
- 다른 담당자에게 영향이 있는지

팀원 한 명 이상이 검토하고 화면·서버·예측 연결을 확인한 뒤 병합합니다. 응답 항목을 바꾸면 프론트엔드·백엔드·AI 담당자가 먼저 합의합니다. 이 절차는 팀의 작업 규칙이며, 자동으로 강제하는 저장소 보호 설정은 별도입니다.

## 5. 다음 작업 시작하기

병합한 작업 브랜치는 정리하고 최신 main에서 새 작업 브랜치를 만듭니다. 아래 이름은 예시이므로 새 작업에 맞게 바꿉니다.

```sh
git switch main
git pull --ff-only origin main
git switch -c fe/next-task
git push -u origin fe/next-task
```

프론트엔드는 `fe/`, 백엔드는 `be/`, AI는 `ai/` 뒤에 작업 이름을 붙입니다. 이번에 만든 브랜치를 영구적인 역할별 저장소로 사용하지 않습니다.

**이번 작업은 로컬 개발과 GitHub 협업을 위한 것입니다. 운영 서버의 파일 수정·설치·재시작·배포는 별도 합의 없이 진행하지 않습니다.**
