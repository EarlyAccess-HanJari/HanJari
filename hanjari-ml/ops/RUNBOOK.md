# 한자리 운영 안내 (RUNBOOK)

사람 손 없이 **수집 → 감시 → 매일 채점·재학습·교체 → 정리**가 돌아갑니다. 이 문서는 "지금 잘 돌고 있나", "이상하면 뭘 하나"를 위한 것입니다.

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
| `~/hanjari-ml/` | 이 레포. 서비스 모델 `models/lite/`, 버전 `models/versions/`, 보고서 `reports/` |
| `~/hanjari-ml/reports/` | `daily/YYYYMMDD.md` 하루 요약 · `daily_metrics.csv` 날짜별 성적 · `models.csv` 버전별 성적·합격 · `alerts.log` 알림 기록 |

## 2. 잘 돌고 있나 (명령 3개)
```bash
systemctl is-active hanjari-collect; systemctl list-timers 'hanjari-*' --no-pager
cat ~/hanjari-ml/reports/daily/$(date -d '+9 hour -1 day' +%Y%m%d).md    # 어젯밤 마감 요약
tail -5 ~/hanjari-ml/reports/alerts.log                                   # 최근 알림
```
지금 예측 한 번 해 보기(수집기 최신 스냅샷, API 호출 없음): `cd ~/hanjari-ml/src && ../.venv/bin/python serve.py latest 3`

## 3. 알림이 오면

| 알림 | 뜻 | 할 일 |
|---|---|---|
| `수집 감시: sb02 새 데이터 없음(N분째)` + `수집기 재시작 함` | 수집이 멈췄고 자동 재시작함 | 10분 뒤 '복구됨' 알림이 오면 끝. 안 오면 `tail ~/hanjari/data/api_logs/collect.log` |
| `최근 10개 모두 API 오류 응답` | 키 만료·하루 한도 초과·API 장애 | collect.log 의 오류 메시지 확인. 한도 초과면 다음 날 자동 회복. 키 만료면 `~/hanjari/.env` 교체 후 `sudo systemctl restart hanjari-collect` |
| `남은 디스크 N GB` | 5GB 미만 | `du -sh ~/hanjari/data/*`. 정리는 매일 돌지만 압축본(`archive/`)이 쌓이면 오래된 것을 다른 곳으로 옮기기 |
| `YYYYMMDD 마감 ⚠ 데이터 FAIL` | 어제 수집에 30분+ 공백·오류가 많음 → 그날은 학습 안 함 | 원인만 확인(서비스 모델은 그대로) |
| `⚠ '여유' 후 실제 탑승 NN% < 97%` | 어제 서비스가 '여유'라 했는데 못 탄 경우가 많았음 | 하루면 지켜보기. 이틀 이상이면 `python src/daily.py rollback` 검토, 원인 분석(행사·시험·날씨) |
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

## 5. 저장 공간 정책 (⑥ 정리, 매일)
- 수집 원본: 최근 3일만 폴더, 그 전은 `archive/YYYYMMDD.tar.gz`(223MB → 15MB/일). 압축본 파일 수를 확인한 뒤에만 폴더 삭제.
- 모델 버전: 최근 7개. 수집기 로그·알림 로그: 매주 압축, 8주 보관(logrotate).
- 하루 증가량 약 17MB → 40GB 디스크로 수년.

## 6. 알림 켜기 (디스코드)
디스코드 채널 → 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사 →
`echo 'HANJARI_WEBHOOK=<URL>' >> ~/hanjari-ml/.env && chmod 600 ~/hanjari-ml/.env`
확인: `cd ~/hanjari-ml/src && ../.venv/bin/python notify.py "알림 시험"`

## 7. 새 서버로 옮기기 (예: Oracle ARM)
```bash
git clone https://github.com/YONGJI04/hanjari-ai.git ~/hanjari-ml && cd ~/hanjari-ml
# 키: ~/hanjari/.env 에 SEOUL_BUS_API_KEY… 줄 / 공공 CSV 표: dvc pull 또는 기존 서버에서 scp
bash ops/install.sh
```
옛 서버의 수집기는 **새 서버가 돌기 시작한 뒤에** `sudo systemctl disable --now hanjari-collect` (두 곳에서 같은 키로 돌면 하루 한도 초과).
수집 로그·캐시를 이어 가려면 `~/hanjari/data/{api_logs,archive}` 와 `~/hanjari-ml/data/processed/days/` 를 함께 복사.

## 8. 바꾸면 안 되는 것
- 키는 `.env` 에만, 레포에 넣지 않기.
- 01:30~05:00 은 API 호출 금지(코드에 고정). 수집 범위(요일·시간)를 임의로 줄이지 않기.
- 수집기는 한 서버에서만.
