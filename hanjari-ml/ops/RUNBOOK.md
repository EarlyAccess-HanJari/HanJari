# 한자리 운영 안내 (RUNBOOK)

사람 손 없이 **수집 → 감시 → 매일 채점·재학습·교체 → 정리**가 돌아갑니다. 이 문서는 "지금 잘 돌고 있나", "이상하면 뭘 하나"를 위한 것입니다.

문서 기준: PRD v1.10·WBS v1.13(2026-11-05). 운영 상태 확인 날짜: 2026-11-05. 12:37(KST)에 `main` 커밋 `587bb6d`의 웹 v9로 전환했습니다. 내부 `127.0.0.1:8000` 바인딩·공개 8000 차단과 nginx·인증서는 유지합니다.

서버 ML 테스트 116개, 백엔드 테스트 2개와 `serve.py check`를 통과했습니다. v8 전환 때 확인한 샘플 6개 정류장의 `eta2_sec`와 HTTPS·공개 8000 차단 상태는 유지됩니다. v9 전환 후에도 외부 8000번은 닫혀 있습니다. 실제 운행 시간의 화면은 아직 확인 전입니다.

## 1. 한눈에

```
[24시간]   hanjari-collect          버스 API 수집(실제 시간표대로, 07~19시 27초 간격, 01:30~05:00 호출 금지)
[10분마다] hanjari-watchdog.timer   새 데이터가 10분 넘게 없으면 수집기 재시작 + 알림 / API 오류·디스크 부족 알림
[매일 01:00 KST] hanjari-daily.timer   어제 마감:
              ① 데이터 점검 → ② 어제 채점 → ③ 재학습 → ④ 합격 판정 → ⑤ 모델 교체 → ⑥ 정리 → 알림
[실패하면]  hanjari-fail@            어느 작업이 실패했는지 알림
```

| 서버 경로 | 내용 |
|---|---|
| `~/hanjari/` | 수집기(`src/collect.py`), API 키(`.env`), 수집 로그 `data/api_logs/YYYYMMDD/`, 압축 로그 `data/archive/` |
| `~/hanjari-ml/` | 일일 재학습 작업 폴더. 서비스 모델 `models/lite/`, 버전 `models/versions/`, 보고서 `reports/` |
| `~/hanjari-ml/reports/` | `daily/YYYYMMDD.md` 하루 요약 · `daily_metrics.csv` 날짜별 성적 · `models.csv` 버전별 성적·합격 · `alerts.log` 알림 기록 |

웹은 `~/hanjari-releases/practical-20261105-v9/`의 코드와 별도 웹 가상환경을 사용합니다. 모델·데이터는 위 일일 작업 폴더를 링크합니다. `https://161.33.132.80/` → nginx 443 → `127.0.0.1:8000`이며, 2026-11-05 03:34(KST) 공개 8000 차단을 완료했습니다. HTTP 일반 요청은 308 이동하고 ACME 인증서 검증 경로는 예외입니다.

## 2. 잘 돌고 있나 (명령 3개)

다음 절차는 service-hardening 변경을 설치한 뒤 적용합니다. 이 문서 갱신 자체는 운영 반영을 뜻하지 않습니다. `/api/health`는 항상 HTTP 200이므로 상태 코드만 보지 말고 `ready`, `model.status`, `model.loaded`, `model.disk`를 함께 확인합니다. 정상은 `status=ok`, `ready=true`입니다. 정책이 꺼진 `not_required`, 비운행 시간의 `not_loaded`는 정상일 수 있습니다. `missing/broken/stale`은 `ready=false`이며, 웹 감시는 연결 실패 또는 ready=false가 연속 2회일 때부터 알리고 stale이면 30분 간격 제한으로 웹만 try-restart합니다. 첫 실패는 로그만 남기며 ready=true이면 연속 실패 횟수를 초기화합니다. 모델 자동 rollback은 하지 않습니다.
```bash
systemctl is-active hanjari-collect; systemctl list-timers 'hanjari-*' --no-pager
cat ~/hanjari-ml/reports/daily/$(date -d '+9 hour -1 day' +%Y%m%d).md    # 어젯밤 마감 요약
tail -5 ~/hanjari-ml/reports/alerts.log                                   # 최근 알림
```
운영 웹의 AI 코드로 예측 확인(저장 스냅샷, 외부 API 호출 없음):
```bash
cd ~/hanjari-releases/practical-20261105-v9/hanjari-ml/src
~/hanjari-web/backend/.venv/bin/python serve.py latest 3
```
`main`(`587bb6d`), 웹 v9, 재학습 폴더 `~/hanjari-ml`의 `serve.py`·`train.py`가 같습니다. 웹과 재학습은 계속 서로 다른 폴더를 사용합니다. 재학습 폴더의 `src/serve.py`·`tests/test_arrival_freshness.py` 교체 전 파일은 `~/hanjari-backups/daily-20261105-123755`에 있습니다. [운영 구성](../../deployment/README.md)을 따릅니다.

## 3. 알림이 오면

| 알림 | 뜻 | 할 일 |
|---|---|---|
| `수집 감시: sb02 새 데이터 없음(N분째)` + `수집기 재시작 함` | 수집이 멈췄고 자동 재시작함 | 10분 뒤 '복구됨' 알림이 오면 끝. 안 오면 `tail ~/hanjari/data/api_logs/collect.log` |
| `최근 10개 모두 API 오류 응답` | 키 만료·하루 한도 초과·API 장애 | collect.log 의 오류 메시지 확인. 한도 초과면 다음 날 자동 회복. 키 만료면 `~/hanjari/.env` 교체 후 `sudo systemctl restart hanjari-collect` |
| `남은 디스크 N GB` | 5GB 미만 | `du -sh ~/hanjari/data/*`. 정리는 매일 돌지만 압축본(`archive/`)이 쌓이면 오래된 것을 다른 곳으로 옮기기 |
| `YYYYMMDD 마감 ⚠ 데이터 FAIL` | 어제 수집에 30분+ 공백·오류가 많음 → 그날은 학습 안 함 | 원인만 확인(서비스 모델은 그대로) |
| `⚠ '여유' 후 … NN% < 97%` | 알림 문구와 무관하게 API 인원·정원 정책으로 계산한 지표 하락. 실제 탑승 실패 관측값이 아님 | 하루면 지켜보기. 이틀 이상이면 `python src/daily.py rollback` 검토, 원인 분석(행사·시험·날씨) |
| `⚠ 새 모델 불합격` | 재학습 모델이 나빠서 교체 안 함 | 조치 불필요(이전 모델 유지). 계속되면 데이터 확인 |
| `마감 실패: …` / `hanjari-daily.service 실패(systemd)` | 코드 오류·메모리 초과 | `journalctl -u hanjari-daily -n 50`. 모델 유지/복구 실패 문구와 health의 활성 버전 확인 |

## 4. 자주 쓰는 조작
```bash
cd ~/hanjari-ml/src
../.venv/bin/python daily.py rollback            # 현재 모델을 제외한 가장 최근 승인 버전
../.venv/bin/python daily.py rollback 20260930   # 승인 기록과 폴더가 모두 있어야 함
sudo systemctl start hanjari-daily                # 마감을 지금 한 번 더(어제 날짜)
../.venv/bin/python daily.py 20260930             # 특정 날짜 마감(제한 없이 돌므로 수집기 바쁜 낮엔 피하기)
tar xzf ~/hanjari/data/archive/20260925.tar.gz -C ~/hanjari/data/api_logs   # 압축 로그 풀기(전체 재계산할 때만)
```

새 rollback 명령은 복사·해시 검증 후 실제 `models/lite` 폴더를 교체하고 `sudo -n systemctl try-restart hanjari-web`을 시도합니다. 미승인 버전은 명시적으로 버전을 지정하고 `--force`를 붙일 때만 허용합니다. 재시작 실패는 모델 복원 실패와 구분해 알립니다. 실행 뒤 반드시 `ready=true`, loaded와 disk 일치를 확인합니다. `.lite-previous`는 직전 폴더 보관용이며 일반 모델 버전으로 탐색하지 않습니다. 두 rename 사이 강제 종료로 lite가 없으면 타이머와 웹을 관리자가 중지한 상태에서 previous를 검증하여 복원해야 합니다. 정상 자동 전환 실패는 이전 lite로 되돌립니다.

웹 릴리스를 되돌려도 공유 모델과 재학습 폴더 코드는 돌아가지 않습니다. 이전 릴리스 설정과 재학습 코드 백업을 별도로 확인하고 정원 정책·모델 호환성을 점검합니다. 과거 v9→v8 및 공개 8000 차단 복원 기록은 [운영 구성](../../deployment/README.md)에 남아 있습니다.

## 5. 저장 공간 정책 (⑥ 정리, 매일)
- 수집 원본: 최근 3일만 폴더, 그 전은 `archive/YYYYMMDD.tar.gz`(223MB → 15MB/일). 압축본 파일 수를 확인한 뒤에만 폴더 삭제.
- 모델 버전: 최근 7개에 더해 승인된 최근 2개와 현재 버전을 보존. 수집기 로그·알림 로그는 매주 압축, 8주 보관(logrotate).
- 5GB 미만이면 데이터셋 생성·재학습을 건너뛰고 현재 모델을 유지합니다. 전환에도 후보 크기 2배의 여유가 필요합니다. archive/processed/models/reports 용량을 마감 요약에서 확인합니다. archive와 학습 자료 자동 삭제는 추가하지 않았으며 총 보관량은 관리자가 결정합니다.

## 6. 알림 켜기 (디스코드)
디스코드 채널 → 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사 →
`echo 'HANJARI_WEBHOOK=<URL>' >> ~/hanjari-ml/.env && chmod 600 ~/hanjari-ml/.env`
확인: `cd ~/hanjari-ml/src && ../.venv/bin/python notify.py "알림 시험"`

## 7. 새 서버로 옮기기

현재 소스는 `https://github.com/EarlyAccess-HanJari/HanJari.git`의 모노레포입니다. 이전 별도 AI 저장소를 그대로 설치하는 절차는 사용하지 않습니다.

1. 소스를 준비한 뒤 `hanjari-ml/ops/install.sh`의 경로와 `deployment/installed/`의 운영 설정을 대조합니다. 이 스크립트는 기존 MLOps 설치 템플릿이며 현재 웹 릴리스·HTTPS·방화벽 전체를 자동 설치하지 않습니다.
2. 수집기, 일일 학습, 웹 릴리스의 경로·가상환경·모델/데이터 링크를 따로 준비합니다. DVC 원격 설정·캐시는 이 사본에 없으므로 연결 없이 `dvc pull`을 실행해도 복원되지 않습니다.
3. 키와 로그·캐시·모델은 공개 저장소 밖에서 인계합니다. `~/hanjari/data/{api_logs,archive}`와 `~/hanjari-ml/data/processed/days/`의 연속성을 확인합니다.
4. 같은 키를 쓰는 수집기는 한 서버에서만 실행합니다. 전환 시 기존 수집기 중지와 새 수집기 시작을 조율하고 수집 공백·중복 호출을 확인합니다.
5. HTTPS, 내부 8000 바인딩, 외부 8000 차단, 모델 응답·다음 버스 표시와 복구 절차를 검증합니다. 현재 문서만으로 새 서버의 설치·복구 성공을 보장하지 않습니다.

## 8. 바꾸면 안 되는 것
- 키는 `.env` 에만, 레포에 넣지 않기.
- 01:30~05:00 은 API 호출 금지(코드에 고정). 수집 범위(요일·시간)를 임의로 줄이지 않기.
- 수집기는 한 서버에서만.
