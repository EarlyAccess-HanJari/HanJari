# 한자리 운영 안내 (RUNBOOK)

사람 손 없이 **수집 → 감시 → 매일 채점·재학습·교체 → 정리**가 돌아갑니다. 이 문서는 "지금 잘 돌고 있나", "이상하면 뭘 하나"를 위한 것입니다.

문서 기준: PRD·WBS v1.4(2026-11-05). 운영 상태 확인 날짜: 2026-11-05. 서버에서 웹 v7·내부 바인딩·방화벽 규칙 제거를 확인했고, 외부에서 HTTPS 200·일반 HTTP 308·공개 8000 무응답을 확인했습니다.

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

웹은 `~/hanjari-releases/practical-20261104-v7/`의 코드와 별도 웹 가상환경을 사용합니다. 모델·데이터는 위 일일 작업 폴더를 링크합니다. `https://161.33.132.80/` → nginx 443 → `127.0.0.1:8000`이며, 2026-11-05 03:34(KST) 공개 8000 차단을 완료했습니다. HTTP 일반 요청은 308 이동하고 ACME 인증서 검증 경로는 예외입니다.

## 2. 잘 돌고 있나 (명령 3개)
```bash
systemctl is-active hanjari-collect; systemctl list-timers 'hanjari-*' --no-pager
cat ~/hanjari-ml/reports/daily/$(date -d '+9 hour -1 day' +%Y%m%d).md    # 어젯밤 마감 요약
tail -5 ~/hanjari-ml/reports/alerts.log                                   # 최근 알림
```
운영 웹의 AI 코드로 예측 확인(저장 스냅샷, 외부 API 호출 없음):
```bash
cd ~/hanjari-releases/practical-20261104-v7/hanjari-ml/src
~/hanjari-web/backend/.venv/bin/python serve.py latest 3
```
일일 작업 폴더와 웹 v7의 코드는 아직 다릅니다. 웹 AI 경로를 `~/hanjari-ml`로 바꾸면 다음 버스 `eta2_sec` 응답이 사라지는 기존 운영 차이가 있으므로 [운영 구성](../../deployment/README.md)을 먼저 확인합니다.

## 3. 알림이 오면

| 알림 | 뜻 | 할 일 |
|---|---|---|
| `수집 감시: sb02 새 데이터 없음(N분째)` + `수집기 재시작 함` | 수집이 멈췄고 자동 재시작함 | 10분 뒤 '복구됨' 알림이 오면 끝. 안 오면 `tail ~/hanjari/data/api_logs/collect.log` |
| `최근 10개 모두 API 오류 응답` | 키 만료·하루 한도 초과·API 장애 | collect.log 의 오류 메시지 확인. 한도 초과면 다음 날 자동 회복. 키 만료면 `~/hanjari/.env` 교체 후 `sudo systemctl restart hanjari-collect` |
| `남은 디스크 N GB` | 5GB 미만 | `du -sh ~/hanjari/data/*`. 정리는 매일 돌지만 압축본(`archive/`)이 쌓이면 오래된 것을 다른 곳으로 옮기기 |
| `YYYYMMDD 마감 ⚠ 데이터 FAIL` | 어제 수집에 30분+ 공백·오류가 많음 → 그날은 학습 안 함 | 원인만 확인(서비스 모델은 그대로) |
| `⚠ '여유' 후 … NN% < 97%` | 알림 문구와 무관하게 API 인원·정원 정책으로 계산한 지표 하락. 실제 탑승 실패 관측값이 아님 | 하루면 지켜보기. 이틀 이상이면 `python src/daily.py rollback` 검토, 원인 분석(행사·시험·날씨) |
| `⚠ 새 모델 불합격` | 재학습 모델이 나빠서 교체 안 함 | 조치 불필요(이전 모델 유지). 계속되면 데이터 확인 |
| `마감 실패: …` / `hanjari-daily.service 실패(systemd)` | 코드 오류·메모리 초과 | `journalctl -u hanjari-daily -n 50`. 서비스 모델은 그대로 |

## 4. 자주 쓰는 조작
```bash
cd ~/hanjari-ml/src
../.venv/bin/python daily.py rollback            # 서비스 모델을 바로 전 버전으로 (특정 버전: rollback 20260930)
sudo systemctl start hanjari-daily                # 마감을 지금 한 번 더(어제 날짜)
../.venv/bin/python daily.py 20260930             # 특정 날짜 마감(제한 없이 돌므로 수집기 바쁜 낮엔 피하기)
tar xzf ~/hanjari/data/archive/20260925.tar.gz -C ~/hanjari/data/api_logs   # 압축 로그 풀기(전체 재계산할 때만)
```

모델을 수동 복원한 뒤에는 메모리에 남은 모델을 갱신하도록 `hanjari-web` 재시작과 응답 확인이 필요합니다. 정원 정책과 모델 메타데이터의 호환성도 확인합니다. 웹 릴리스 복원과 공개 8000 차단 설정 복원은 별도이며, 포트 설정 복원은 서버의 `~/hanjari-backups/close-8000-20261105-033411` 백업을 사용합니다. 백업 내용·복구 성공은 2026-11-05 기준 미확인입니다. 접근 설정 잔여 점검은 11/8, 복구 검증은 11/13 예정입니다.

## 5. 저장 공간 정책 (⑥ 정리, 매일)
- 수집 원본: 최근 3일만 폴더, 그 전은 `archive/YYYYMMDD.tar.gz`(223MB → 15MB/일). 압축본 파일 수를 확인한 뒤에만 폴더 삭제.
- 모델 버전: 최근 7개. 수집기 로그·알림 로그: 매주 압축, 8주 보관(logrotate).
- 하루 증가량 약 17MB → 40GB 디스크로 수년.

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
