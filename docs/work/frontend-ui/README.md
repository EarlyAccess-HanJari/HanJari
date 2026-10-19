# 프론트엔드 · 화면 사용성 개선

담당: **서재현** · 작업 브랜치: **`fe/ui-improvement`**

목표는 정류장 선택, 대기 인원 입력, 결과 확인 흐름을 더 편하게 만드는 것입니다. 아래 내용은 앞으로 진행할 작업 순서입니다.

## 1. 작업 브랜치로 이동

저장소 최상위에서 처음 한 번 실행합니다. 이미 로컬 브랜치가 있다면 `git switch fe/ui-improvement`로 이동합니다.

```sh
git fetch origin
git switch --track origin/fe/ui-improvement
```

## 2. 화면 실행

Node.js 24 기준입니다. 프론트엔드 폴더로 이동해 패키지를 설치합니다.

```sh
cd hanjari-web/frontend
npm ci
```

`.env`가 없다면 `.env.example`을 복사해 `.env`를 만듭니다. `VITE_MOCK=1`이면 저장된 예시 자료로 화면을 확인할 수 있습니다.

```sh
npm run dev
```

## 3. 기능 수정

1. 모바일에서 정류장 선택 → 인원 입력 → 결과 확인 흐름을 확인합니다.
2. 입력 범위 0~40명과 잘못된 입력 안내를 점검합니다.
3. 버튼, 글자 크기, 화면 배치를 필요한 범위에서 개선합니다.
4. 오류·지연 안내를 바꿔야 하면 황정원과 수정 범위를 먼저 나눕니다.

주요 수정 위치는 `hanjari-web/frontend/src/`입니다. API 응답 항목과 예측 단계의 의미를 임의로 바꾸지 않습니다.

## 4. 테스트와 빌드

같은 프론트엔드 폴더에서 실행합니다. Playwright 테스트는 목업 모드로 확인하고, 운영용 빌드는 실제 API 연결 모드로 생성합니다.

```sh
npx playwright install chromium
npm test
npm run build:prod
```

이 저장소는 `dist/`도 관리합니다. 화면 수정 후 운영용 빌드 결과를 소스와 함께 검토합니다. 테스트 보고서와 `node_modules/`는 올리지 않습니다.

## 5. PR 작성

[공통 협업 안내](../../../CONTRIBUTING.md)의 업로드 순서를 따릅니다. PR에 변경 전후 화면과 테스트 결과를 적고, 황정원에게 확인을 요청합니다. 실제 백엔드 연결은 [프론트엔드 개발 안내](../../../hanjari-web/frontend/README.md)를 참고합니다.

다른 역할의 폴더는 그대로 유지하며, 운영 서버에는 배포하지 않습니다.
