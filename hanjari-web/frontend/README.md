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

목업 모드에서 `?scenario=stale`, `wide`, `night`, `error`, `down`, `slow`를 사용하면 예외 상황을 확인할 수 있습니다. 운영용 빌드에서는 이 목업 기능을 사용하지 않습니다.

`.env`에 `VITE_MOCK=1`을 설정한 뒤 아래 명령으로 기존 Playwright 테스트를 실행합니다.

```sh
npx playwright install chromium
npm test
```

이번 정리 작업에서는 TypeScript 검사와 운영용 빌드·파일 일치를 확인했습니다. 기존 Playwright 테스트를 다시 실행한 결과로 간주하지 않습니다.

`npm run mock:pull`과 해당 스크립트는 과거 작업용으로 남겨 두었습니다. 이전 저장소의 `pm/jeongwon` 브랜치에 의존하므로 새 저장소에서는 실행하지 않습니다. 현재 목업 파일은 이미 `src/mock/`에 포함되어 있습니다.
