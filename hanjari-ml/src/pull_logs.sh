#!/bin/bash
# 오라클 수집기(~/hanjari/data/api_logs) → 이 서버 data/api_logs 로 가져오기. 파일 수가 다른 날짜 폴더만 받는다.
# vi004 엔 rsync 가 없어 ssh+tar 사용. 분석(build_dataset) 전에 실행: bash src/pull_logs.sh
set -e
cd "$(dirname "$0")/../data/api_logs"
ssh oracle 'cd ~/hanjari/data/api_logs && for d in 2026*/; do echo "${d%/} $(ls "$d" | wc -l)"; done' | while read -r day n; do
  have=$(ls "$day" 2>/dev/null | wc -l)
  if [ "$have" != "$n" ]; then
    ssh oracle "tar cf - -C ~/hanjari/data/api_logs $day" < /dev/null | tar xf -
    echo "$day: $have → $(ls "$day" | wc -l)"
  fi
done
scp -q oracle:hanjari/data/api_logs/schedule.json schedule.json
scp -q oracle:hanjari/data/api_logs/collect.log collect_oracle.log
