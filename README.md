# 한자리

**지금 오는 마을버스, 탈 수 있을까?**

한자리는 한성대학교 통학생을 위한 버스 탑승 가능성 안내 서비스입니다. 정류장을 고르고 내 앞 대기 인원을 입력하면, 버스 도착 정보와 AI가 예측한 탑승 확률을 확인할 수 있습니다.

한성대학교 오픈소스 AI·SW 융합 프로젝트 · **팀 얼리액세스**

## 현재 사용할 수 있는 기능

- 성북02·종로03의 등교 방향 정류장 6곳 조회
- 내 앞 대기 인원 0~40명 입력
- 첫째 버스의 도착 예정 시간과 현재 승객 수 확인
- AI가 예측한 탑승 확률과 ‘여유 있음’, ‘빠듯함’ 등의 안내
- 자동 새로고침과 정보 지연·연결 오류 안내

예측 결과는 이동을 돕는 참고 정보이며, 실제 탑승 여부는 현장 상황에 따라 달라질 수 있습니다.

## 어떻게 동작하나요?

**서울시 버스 정보 수집 → 자료 저장 → AI 예측 → 화면 표시**

수집기는 운행 시간에 버스 정보를 자동으로 저장합니다. 사용자가 조회하면 저장된 자료와 대기 인원을 이용해 탑승 가능성을 예측합니다. 사용자 조회마다 외부 버스 API를 호출하지는 않습니다.

| 구분 | 사용 기술 | 역할 |
| --- | --- | --- |
| 화면 | React · TypeScript · Vite | 정류장 선택, 인원 입력, 결과 표시 |
| 서버 | Python · FastAPI | 화면과 예측 기능 연결 |
| AI | XGBoost · pandas · NumPy | 데이터 처리와 탑승 가능성 예측 |
| 운영 | Oracle Cloud · Ubuntu · systemd | 서비스 실행과 수집·학습 작업 관리 |

## 내 PC에서 실행하기

Python 3.11이 필요합니다. 저장소를 내려받은 뒤 최상위 폴더에서 실행하세요.

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe scripts/run_local.py
```

<details>
<summary>macOS · Linux 실행 방법</summary>

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python scripts/run_local.py
```

</details>

브라우저에서 **http://127.0.0.1:8000**을 열면 됩니다. 종료는 `Ctrl+C`입니다.

기본 실행은 **API 키가 필요 없는 샘플 모드**입니다. 2026년 9월 30일의 저장 자료를 사용하므로 현재 버스 상황과는 다릅니다. 실시간 수집이나 자동 학습은 시작하지 않습니다.

화면 수정과 빌드는 [프론트엔드 개발 안내](hanjari-web/frontend/README.md), 실시간 운영 설정은 [운영 안내](deployment/README.md)를 참고하세요.

## 팀 역할

| 팀원 | 담당 |
| --- | --- |
| 황정원 | 기획·일정·문서, 프론트엔드 공동 개발, 백엔드 초기 구현과 화면 연결 |
| 서재현 | 프론트엔드 공동 개발, UI 설계와 테스트 |
| 최지용 | 데이터 수집·처리, AI 모델 개발 |
| 유민준 | 백엔드 현재 담당, 서버 배포와 오픈소스 조사 |

## 앞으로 할 일

2026년 10월 19일 중간발표 준비 기준입니다.

- 익명 탑승 결과 기록 기능을 구현하고, 현장 평가로 예측 결과 확인
- 정보가 없거나 수집이 지연된 상황의 안내 개선
- 화면·서버 통합 테스트와 사용성 개선
- 둘째 버스 도착 정보는 현재 미구현·보류 상태로, 후속 일정 검토

## 관련 자료

- [프론트엔드 개발 안내](hanjari-web/frontend/README.md)
- [운영 안내](deployment/README.md)
- [검증 결과](deployment/VALIDATION.md)
- [프론트엔드와 배포 화면의 일치 확인](deployment/FRONTEND_MATCH.md)

이 저장소는 운영 중인 코드를 바탕으로 새로 구성했습니다. 이전 개발 과정은 [기존 저장소](https://github.com/YONGJI04/hanjari-ai)에서 확인할 수 있습니다.
