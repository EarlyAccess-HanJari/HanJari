# 프론트엔드 · 오류와 지연 안내 개선

담당: **황정원** · 작업 브랜치: **`fe/status-guidance`**

목표는 버스가 없을 때, 자료가 오래됐을 때, 서버 연결에 문제가 있을 때를 사용자가 구분할 수 있도록 안내하는 것입니다.

## 1. 작업 브랜치로 이동

저장소 최상위에서 처음 한 번 실행합니다. 이미 로컬 브랜치가 있다면 `git switch fe/status-guidance`로 이동합니다.

```sh
git fetch origin
git switch --track origin/fe/status-guidance
```

## 2. 예외 화면 확인

Node.js 24 기준으로 `hanjari-web/frontend`에서 준비합니다. `.env`가 없다면 `.env.example`을 복사하고 `VITE_MOCK=1`로 설정합니다.

```sh
npm ci
npm run dev
```

개발 화면 주소 뒤에 아래 값을 붙여 확인합니다. 이 기능은 목업 모드에서만 동작합니다.

- `?scenario=down`: 서버 연결 실패
- `?scenario=slow`: 응답 지연
- `?scenario=stale`: 오래된 정보
- `?scenario=night`: 운행 시간 안내
- `?scenario=wide`: 예측 범위가 넓은 상황

## 3. 안내 개선

1. 상황별 문구, 재시도 버튼, 자동 갱신 동작을 확인합니다.
2. 빈 결과만으로 운행 종료를 단정하지 않도록 백엔드와 상태 구분을 협의합니다.
3. 서버에서 구분할 수 없는 상태는 화면에서 임의로 판단하지 않습니다.
4. 입력 중인 값과 마지막 조회 결과가 혼동되지 않도록 점검합니다.

주요 수정 위치는 `hanjari-web/frontend/src/`입니다. 서재현과 같은 파일을 수정할 때는 먼저 변경 범위를 공유합니다.

## 4. 테스트와 빌드

프론트엔드 폴더에서 실행하고, 정상 조회도 계속 동작하는지 확인합니다.

```sh
npx playwright install chromium
npm test
npm run build:prod
```

`dist/` 변경은 소스와 함께 검토합니다. 목업 화면을 운영 화면처럼 설명하지 않도록 캡처에 상황과 입력값을 적습니다.

## 5. PR 작성

[공통 협업 안내](../../../CONTRIBUTING.md)에 따라 업로드하고, 확인한 상황·입력값·결과를 PR에 적습니다. 서재현이 화면을 검토하며 API 변경이 있으면 유민준도 함께 확인합니다.

운영 서버 파일과 서비스는 수정하지 않습니다.
