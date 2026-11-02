# 한자리 프론트엔드

담당: 서재현 · 황정원

2026년 10월 19일 로컬 원본을 운영용으로 빌드한 결과가 서버 배포 파일 6개와 SHA-256 기준으로 모두 일치했습니다. `src/`, `public/`, 빌드 설정, 잠금 파일, 목업과 테스트를 함께 보관합니다. `dist/`는 서버에서 내려받은 배포본입니다.

## 환경과 설치

검증 환경: Node.js 24.15.0, npm 11.12.1. React 19 · TypeScript 6 · Vite 8을 사용하며 정확한 패키지 버전은 `package-lock.json`에 고정되어 있습니다.

아래 명령은 `hanjari-web/frontend`에서 실행합니다.

```sh
npm ci
npm run build:prod
```

`build:prod`는 `VITE_MOCK=0`으로 실제 API를 사용하는 화면을 `dist/`에 생성합니다. 이 명령은 로컬 배포 파일을 다시 만들며 운영 서버에는 전송하지 않습니다.

현재 배포 화면은 저장소 최상위의 Python 실행기로 바로 볼 수 있습니다. 방법은 [전체 실행 안내](../../README.md)를 참고하세요.

## 화면 개발

`.env.example`을 `.env`로 복사하면 목업 모드(`VITE_MOCK=1`)로 개발할 수 있습니다. `.env`는 Git에서 제외됩니다.

```sh
npm run dev
```

실제 백엔드와 연결할 때는 먼저 저장소 최상위 안내대로 백엔드를 실행하고, 별도 터미널에서 아래 명령을 실행합니다.

```sh
npm run dev:server
```

기본 프록시 대상은 `http://127.0.0.1:8000`입니다. 화면은 상대 주소 `/api/predict?n=3`으로 요청하며, 앞 대기 인원은 0~40명을 입력합니다.

## 목업과 테스트

목업 모드에서 `?scenario=stale`, `wide`, `night`, `error`, `down`, `slow`를 사용하면 예외 상황을 확인할 수 있습니다. 개발용 상태 전환 패널은 제거했으며, 운영용 빌드에서는 목업을 사용하지 않습니다.

`.env`에 `VITE_MOCK=1`을 설정한 뒤 아래 명령으로 기존 Playwright 테스트를 실행합니다.

```sh
npx playwright install chromium
npm test
```

테스트는 입력·정류장 전환·오류 안내, 로컬 UI의 반응형 배치, 스냅샷 시각을 반영한 카운트다운을 확인합니다. 최종 커밋 전 테스트와 운영용 빌드를 모두 실행합니다.

`npm run mock:pull`과 해당 스크립트는 과거 작업용으로 남겨 두었습니다. 이전 저장소의 `pm/jeongwon` 브랜치에 의존하므로 새 저장소에서는 실행하지 않습니다. 현재 목업 파일은 이미 `src/mock/`에 포함되어 있습니다.

## 인원 정보 품질 검사

보류 시 nullable 인원·확률을 숨기고 `arrival_stale`로 도착 안내를 판단합니다. 실제 HTTP 응답 경로 검사는 `VITE_MOCK=0 npx playwright test tests/api-quality.spec.ts`, 기존 목업 시나리오는 `VITE_MOCK=1 npx playwright test tests/scenarios.spec.ts tests/flow.spec.ts tests/countdown.spec.ts tests/layout.spec.ts`로 실행합니다. 두 실행 사이에 이전 Vite 개발 서버를 종료해 환경 변수가 섞이지 않게 합니다.

도착 예정 시각은 API 제공 시각을 기준으로 계산합니다. 2정류장·2분 이내 또는 갱신 대기 중에는 서버 기록을 5초 간격으로 조회하고, ETA 만료/통과한 차량의 인원·확률은 최신 값처럼 유지하지 않습니다. 같은 응답을 다시 받아도 예정 시각은 연장되지 않으며 오래된 응답으로 되돌아가지 않습니다. 차량번호는 내부 식별에 사용합니다. 관련 HTTP 회귀 검사는 `tests/api-quality.spec.ts`의 자동 차량 전환·만료 시나리오입니다.
