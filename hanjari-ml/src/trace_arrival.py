"""정류장의 첫째/둘째 도착 차량을 원본에서 추적한다. 외부 호출·인원 보정·학습 없음.

python src/trace_arrival.py --logs /path/api_logs --date 20261102 --route jr03 --stop 23 \
    --start 17:38:00 --end 17:44:00 --output /path/trace.json
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import build_dataset as B
import data_quality as DQ


def trace(logs, day, route, stop, start, end):
    folder = Path(logs) / day
    first_changes, rows, sources, previous = [], [], [], None
    for path in sorted(folder.glob(f"{route}_arr_*.json")):
        time = dt.datetime.strptime(path.stem.rsplit("_", 1)[-1], "%H%M%S").strftime("%H:%M:%S")
        if not start <= time <= end:
            continue
        items = B.read_items(path)
        item = next((i for i in items if str(i.get("staOrd")) == str(stop)), None)
        if item is None:
            continue
        pos_path = path.with_name(path.name.replace("_arr_", "_pos_"))
        positions = B.read_items(pos_path) if pos_path.exists() else []
        for source in (path, pos_path):
            if source.exists():
                sources.append(dict(file=f"{day}/{source.name}", sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        row = dict(collected_at=f"{day[:4]}-{day[4:6]}-{day[6:]}T{time}+09:00",
                   source_updated=item.get("mkTm"), stop=str(stop), stop_name=item.get("stNm"), arrivals=[])
        for slot in "12":
            plate, vehicle_id = item.get("plainNo" + slot), item.get("vehId" + slot)
            if not plate or not vehicle_id or vehicle_id == "0":
                continue
            position = next((p for p in positions if p.get("vehId") == vehicle_id), {})
            seq = DQ.integer(item.get("sectOrd" + slot))
            row["arrivals"].append(dict(
                slot=int(slot), plate=plate, vehicle_id=vehicle_id,
                api_count=DQ.passenger_count(item, slot), eta_sec=DQ.integer(item.get("traTime" + slot)),
                stops_away=int(stop) - seq if seq is not None else None,
                position_matches=position.get("plainNo") == plate,
                position_section=DQ.integer(position.get("sectOrd")),
                position_updated=position.get("dataTm")))
        first = next((v for v in row["arrivals"] if v["slot"] == 1), None)
        if first and previous and first["vehicle_id"] != previous["vehicle"]["vehicle_id"]:
            first_changes.append(dict(previous_snapshot=previous["time"], current_snapshot=row["collected_at"],
                                      previous=previous["vehicle"], current=first,
                                      meaning="첫 도착예정 차량이 바뀜. 같은 차량의 인원 감소로 해석하지 않음."))
        previous = {"time": row["collected_at"], "vehicle": first} if first else None
        rows.append(row)
    return dict(route=route, stop=str(stop), date=day, rows=rows, first_bus_changes=first_changes,
                sources=sources, limitation="API 기록의 차량/시각 대조. 현장 인원 정확성은 이 기록만으로 검증할 수 없음.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logs", type=Path, required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--route", choices=B.STOPS, required=True)
    p.add_argument("--stop", type=int, required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = trace(args.logs, args.date, args.route, args.stop, args.start, args.end)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"조회 {len(report['rows'])}개, 첫 도착 차량 변경 {len(report['first_bus_changes'])}회 → {args.output}")
