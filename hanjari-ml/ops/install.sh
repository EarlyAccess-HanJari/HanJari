#!/bin/bash
# 한자리 운영 설치 — Ubuntu 22.04+, sudo 되는 사용자로 이 레포 안에서 실행. 여러 번 실행해도 안전(이미 된 건 건너뜀).
#   git clone https://github.com/YONGJI04/hanjari-ai.git ~/hanjari-ml && cd ~/hanjari-ml && bash ops/install.sh
#   서버 이전 중이면 HANJARI_NO_START=1 bash ops/install.sh (설치만 하고 수집기·타이머는 안 켬)
#
# 만드는 것
#   ~/hanjari                수집기 폴더(수집 로그·API 키). 수집기는 시스템 python3 만 씀(외부 라이브러리 없음)
#   <이 레포>/.venv           Python 3.11 + numpy·pandas·xgboost·scikit-learn (uv)
#   <이 레포>/data/api_logs   → ~/hanjari/data/api_logs 링크(읽기만)
#   systemd: hanjari-collect(상시) · hanjari-daily.timer(매일 01:00 KST) · hanjari-watchdog.timer(10분마다)
#   스왑 2GB(없을 때), logrotate(수집기 로그·알림 로그)
# 설치 전에 준비할 것(레포에 없음)
#   ~/hanjari/.env           SEOUL_BUS_API_KEY=… (키 여러 개면 SEOUL_BUS_API_KEY_2= … 줄마다)
#   <레포>/.env               (선택) HANJARI_WEBHOOK=디스코드 웹훅 주소 → 알림
#   <레포>/data/processed/{sb02,jr03}_{hourly,trips}.csv  공공 CSV 표 — `dvc pull` 또는 기존 서버에서 복사
set -euo pipefail
REPO=$(cd "$(dirname "$0")/.." && pwd)
COL=${HANJARI_COLLECT:-$HOME/hanjari}
ME=$(id -un)
say() { printf '\n== %s\n' "$*"; }

say "1. 스왑"
if ! swapon --show | grep -q .; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-hanjari-swap.conf >/dev/null && sudo sysctl -q -p /etc/sysctl.d/99-hanjari-swap.conf
fi
swapon --show

say "2. Python 3.11 환경"
command -v uv >/dev/null || [ -x ~/.local/bin/uv ] || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
UV=$(command -v uv || echo ~/.local/bin/uv)
[ -x "$REPO/.venv/bin/python" ] || "$UV" venv -q -p 3.11 "$REPO/.venv"
grep -E '^(numpy|pandas|xgboost|scikit-learn)==' "$REPO/requirements.txt" | sed 's/ *#.*//' > /tmp/hanjari-req.txt
nice -n 19 "$UV" pip install -q -p "$REPO/.venv/bin/python" -r /tmp/hanjari-req.txt
"$REPO/.venv/bin/python" -c "import numpy, pandas, xgboost, sklearn; print('ok', xgboost.__version__)"

say "3. 수집기 폴더 $COL"
mkdir -p "$COL/src" "$COL/data/api_logs" "$COL/data/processed"
cp "$REPO/src/collect.py" "$COL/src/collect.py"
[ -f "$REPO/data/processed/holidays.csv" ] && cp "$REPO/data/processed/holidays.csv" "$COL/data/processed/"
[ -f "$COL/.env" ] && chmod 600 "$COL/.env" || echo "⚠ $COL/.env 없음 — API 키를 넣어야 수집이 시작됩니다"
[ -e "$REPO/data/api_logs" ] || ln -s "$COL/data/api_logs" "$REPO/data/api_logs"
for t in sb02_hourly sb02_trips jr03_hourly jr03_trips; do
  [ -f "$REPO/data/processed/$t.csv" ] || echo "⚠ data/processed/$t.csv 없음 — 재학습에 필요(dvc pull 또는 기존 서버에서 복사)"
done

say "4. systemd·logrotate"
for f in "$REPO"/ops/systemd/*; do
  sed -e "s#@USER@#$ME#g" -e "s#@COL@#$COL#g" -e "s#@REPO@#$REPO#g" "$f" | sudo tee "/etc/systemd/system/$(basename "$f")" >/dev/null
done
sed -e "s#@USER@#$ME#g" -e "s#@COL@#$COL#g" -e "s#@REPO@#$REPO#g" "$REPO/ops/logrotate-hanjari" | sudo tee /etc/logrotate.d/hanjari >/dev/null
sudo systemctl daemon-reload
if [ "${HANJARI_NO_START:-0}" = 1 ]; then
  echo "HANJARI_NO_START=1 → 설치만, 켜지 않음(서버 이전 중). 켤 때: sudo systemctl enable --now hanjari-collect hanjari-daily.timer hanjari-watchdog.timer"
else
  if [ -f "$COL/.env" ]; then sudo systemctl enable --now hanjari-collect; fi
  sudo systemctl enable --now hanjari-daily.timer hanjari-watchdog.timer
fi

say "5. 상태"
systemctl is-active hanjari-collect || true
systemctl list-timers 'hanjari-*' --no-pager | head -4
echo "운영 안내: $REPO/ops/RUNBOOK.md"
