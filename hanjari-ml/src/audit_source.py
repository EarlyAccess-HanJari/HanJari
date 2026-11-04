"""고정 원본 tar.gz의 API 의미·차량 식별·고인원 기록을 집계. 외부 호출/원본 변경 없음.
python src/audit_source.py /path/raw.tar.gz --output /path/report.json
현장 인원 오차를 측정하는 스크립트가 아니다. 같은 차량의 반복 조회는 독립 사건이 아니다.
"""
import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import tarfile

import data_quality as DQ

STOPS = {"jr03": {19, 20, 23}, "sb02": {30, 31, 32}}


def audit(path):
    vehicles, positions, targets = {}, {}, []
    files, errors = Counter(), Counter()
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            day, filename = Path(member.name).parts[-2:]
            route, kind, stamp = filename.removesuffix(".json").split("_")
            t = dt.datetime.strptime(day + stamp, "%Y%m%d%H%M%S")
            files[(day, route, kind)] += 1
            try:
                body = json.load(archive.extractfile(member))
                if str(body["msgHeader"].get("headerCd")) != "0":
                    errors["api_header"] += 1
                    continue
                items = body["msgBody"]["itemList"] or []
            except (ValueError, TypeError, KeyError):
                errors["malformed"] += 1
                continue
            for item in items:
                if kind == "pos":
                    positions[(route, t, str(item.get("plainNo") or "").strip())] = item
                    continue
                for slot in "12":
                    plate = str(item.get("plainNo" + slot) or "").strip()
                    if not plate:
                        continue
                    key = (route, t, plate, str(item.get("vehId" + slot)))
                    record = vehicles.setdefault(key, {"values": set(), "divs": set(), "ages": [], "statuses": set()})
                    n = DQ.integer(item.get("reride_Num" + slot))
                    if n is not None:
                        record["values"].add(n)
                    record["divs"].add(str(item.get("rerdie_Div" + slot)))
                    status = DQ.source_issue(item, t, slot)
                    record["statuses"].add(status)
                    made = DQ.source_time(item.get("mkTm"))
                    if made is not None and made.tzinfo is None:
                        record["ages"].append((t - made).total_seconds())
                    if slot == "1" and DQ.integer(item.get("staOrd")) in STOPS[route]:
                        targets.append((key, n, str(item.get("rerdie_Div1")), status))
    summaries = {}
    for route in STOPS:
        rows = [(key, v) for key, v in vehicles.items() if key[0] == route]
        high = [(key, v) for key, v in rows if max(v["values"], default=0) > 50]
        target = [(key, n, div, status) for key, n, div, status in targets if key[0] == route]
        mismatch, matched_high, ages, pos_ages = 0, 0, [], []
        for key, v in rows:
            p = positions.get(key[:3])
            match = p is not None and str(p.get("vehId")) == key[3]
            mismatch += int(p is not None and not match)
            if max(v["values"], default=0) > 50:
                matched_high += int(match)
                ages.extend(v["ages"])
                made = DQ.source_time(p.get("dataTm")) if p else None
                if made is not None and made.tzinfo is None:
                    pos_ages.append((key[1] - made).total_seconds())
        # 50 이하 기록 또는 수집 공백으로 끊은 연속 구간 수.
        previous, episodes = {}, 0
        for key, v in sorted(rows, key=lambda pair: pair[0][1]):
            n = max(v["values"], default=0)
            vehicle = key[2:]
            prev = previous.get(vehicle)
            if n > 50 and (prev is None or prev[1] <= 50 or (key[1] - prev[0]).total_seconds() > 180):
                episodes += 1
            previous[vehicle] = key[1], n
        summaries[route] = dict(
            vehicle_snapshots=len(rows), vehicles=len({k[2:] for k, _ in rows}),
            conflicting_counts=sum(len(v["values"]) > 1 for _, v in rows), identity_mismatches=mismatch,
            over50_snapshots=len(high), over50_vehicles=len({k[2:] for k, _ in high}), over50_episodes=episodes,
            max_api_count=max(n for _, v in rows for n in v["values"]),
            over50_position_id_matches=matched_high,
            over50_provider_age_sec=[min(ages), max(ages)] if ages else [],
            over50_position_age_sec=[min(pos_ages), max(pos_ages)] if pos_ages else [],
            target_rows=len(target), target_divisions=dict(Counter(div for _, _, div, _ in target)),
            target_quality=dict(Counter(status for _, _, _, status in target)),
            target_div0_zero=sum(div == "0" and n == 0 for _, n, div, _ in target),
            target_over50=sum(n is not None and n > 50 for _, n, _, _ in target))
    return dict(archive_sha256=hashlib.file_digest(open(path, "rb"), "sha256").hexdigest(),
                files=sum(files.values()), errors=dict(errors), source_schema=DQ.SCHEMA_VERSION,
                first=min(k[1] for k in vehicles).isoformat(), last=max(k[1] for k in vehicles).isoformat(),
                timezone="Asia/Seoul", routes=summaries,
                limitation="API 원본 감사. 현장 실인원·탑승 성공률 검증 아님. 50 초과는 오류 판정이 아님.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.archive)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
