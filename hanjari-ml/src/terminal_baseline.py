"""종점 잔여 인원 보정 후보를 원본 로그에서 재생 검사한다. 운영 인원/학습값은 바꾸지 않는다.

노선 시작·끝 또는 정차는 빈 차의 증거가 아니다. 후보는 '전원 하차 후, 다음 승차 전'
구간이라는 운영 조건이 확인되어야 실제 차감에 쓸 수 있다. 같은 응답의 반복 수신은 제외한다.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import build_dataset as B
import data_quality as DQ


def distance_m(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return 6371000 * math.hypot(math.radians(a[0] - b[0]) * math.cos(lat), math.radians(a[1] - b[1]))


class TerminalCandidates:
    def __init__(self, terminal_id, sections, min_updates=3, min_span=30, max_gap=90, radius_m=15):
        self.terminal_id, self.sections = str(terminal_id), set(sections)
        self.min_updates, self.min_span = min_updates, min_span
        self.max_gap, self.radius_m = max_gap, radius_m
        self.active, self.events, self.rejected = {}, [], Counter()
        self.terminal_rows = Counter()

    def finish(self, key):
        seen = self.active.pop(key, [])
        if not seen:
            return
        sources, positions = {r["source_time"] for r in seen}, {r["position_time"] for r in seen}
        source_span = (max(sources) - min(sources)).total_seconds()
        position_span = (max(positions) - min(positions)).total_seconds()
        if min(len(sources), len(positions)) < self.min_updates or min(source_span, position_span) < self.min_span:
            self.rejected["insufficient_independent_updates"] += 1
            return
        counts = [r["count"] for r in seen]
        self.events.append(dict(
            vehicle_id=key[0], plate=key[1], start=seen[0]["time"].isoformat(), end=seen[-1]["time"].isoformat(),
            min_api_count=min(counts), max_api_count=max(counts),
            source_updates=len(sources), position_updates=len(positions),
            source_span_sec=source_span, position_span_sec=position_span,
            candidate_offset_max=min(counts), automatic_subtraction=0, empty_verified=False))

    def step(self, now, observations):
        eligible = set()
        for row in observations:
            key = row["vehicle_id"], row["plate"]
            if row["station_id"] != self.terminal_id or row["section"] not in self.sections:
                continue
            eligible.add(key)
            self.terminal_rows["positive" if row["count"] else "zero"] += 1
            previous = self.active.get(key, [])
            if previous:
                last = previous[-1]
                # 운행/날짜/관측 공백이 바뀌면 다른 운행의 잔여분을 물려주지 않는다.
                if (now.date() != last["time"].date() or (now - last["time"]).total_seconds() > self.max_gap
                        or row["source_time"] < last["source_time"] or row["position_time"] < last["position_time"]
                        or distance_m(previous[0]["gps"], row["gps"]) > self.radius_m):
                    self.finish(key)
            self.active.setdefault(key, []).append(dict(row, time=now))
        for key in list(self.active):
            if key not in eligible:
                self.finish(key)

    def close(self):
        for key in list(self.active):
            self.finish(key)


def observations(arrivals, positions, now, max_age=60):
    """같은 차량의 인원·위치를 결합한다. 결측 0, 충돌, 오래된 위치는 종점 기준값으로 쓸 수 없다."""
    counts, sources = {}, {}
    for it in arrivals:
        for slot in "12":
            if DQ.source_issue(it, now, slot) != "ok":
                continue
            source = DQ.source_time(it.get("mkTm"))
            if not -5 <= (now - source).total_seconds() <= max_age:
                continue
            key = str(it["vehId" + slot]), str(it["plainNo" + slot]).strip()
            counts.setdefault(key, set()).add(DQ.passenger_count(it, slot))
            sources[key] = max(source, sources.get(key, source))
    out = []
    for p in positions:
        key = str(p.get("vehId") or ""), str(p.get("plainNo") or "").strip()
        values = counts.get(key, set())
        made = DQ.source_time(p.get("dataTm"))
        if (len(values) != 1 or made is None or made.tzinfo is not None
                or not -5 <= (now - made).total_seconds() <= max_age):
            continue
        try:
            gps = float(p["gpsX"]), float(p["gpsY"])
            if not (-180 <= gps[0] <= 180 and -90 <= gps[1] <= 90):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        out.append(dict(vehicle_id=key[0], plate=key[1], count=next(iter(values)),
                        source_time=sources[key], position_time=made, gps=gps,
                        station_id=str(p.get("lastStnId") or ""), section=DQ.integer(p.get("sectOrd"))))
    return out


def correction_scenario(raw, baseline):
    """0~baseline명이 계속 남아 있다는 가정의 계산 예시. 실측 신뢰구간/운영 보정값이 아니다."""
    if type(raw) is not int or raw < 0 or type(baseline) is not int or baseline < 0:
        raise ValueError("raw/baseline must be nonnegative integers")
    if raw < baseline:
        return dict(status="baseline_invalidated", raw=raw, automatic_subtraction=0,
                    reason="원본이 기준값보다 낮아짐: 원본 초기화/지연 반영 가능, 중복 차감 금지")
    return dict(status="scenario_only", raw=raw, assumed_range=[raw - baseline, raw], automatic_subtraction=0)


def audit(logs, route, terminal_id, sections, start, end):
    tracker = TerminalCandidates(terminal_id, sections)
    files = sorted(f for folder in Path(logs).iterdir() if folder.is_dir() and start <= folder.name <= end
                   for f in folder.glob(f"{route}_arr_*.json"))
    manifest, errors, file_count = hashlib.sha256(), Counter(), 0
    for path in files:
        now = dt.datetime.strptime(path.parent.name + path.stem[-6:], "%Y%m%d%H%M%S")
        pos = path.with_name(path.name.replace("_arr_", "_pos_"))
        for f in (path, pos):
            if f.exists():
                manifest.update(f"{f.parent.name}/{f.name}\0".encode())
                manifest.update(hashlib.sha256(f.read_bytes()).digest())
                file_count += 1
        try:
            rows = observations(B.read_items(path), B.read_items(pos), now)
        except (OSError, ValueError, KeyError, TypeError):
            errors["invalid_or_missing_pair"] += 1
            rows = []
        tracker.step(now, rows)
    tracker.close()
    positives = [e for e in tracker.events if e["candidate_offset_max"] > 0]
    return dict(
        route=route, terminal_id=str(terminal_id), terminal_sections=sorted(sections), dates=[start, end], timezone="Asia/Seoul",
        mode="audit_only", applied_to_serving=False, applied_to_training=False, empty_checkpoint_verified=False,
        parameters=dict(max_source_age_sec=60, min_independent_updates=3, min_span_sec=30, max_gap_sec=90, stationary_radius_m=15),
        source_files=file_count, source_manifest_sha256=manifest.hexdigest(), errors=dict(errors),
        terminal_rows=dict(tracker.terminal_rows), candidates=len(tracker.events), positive_candidates=len(positives),
        candidate_max=max((e["candidate_offset_max"] for e in positives), default=0),
        rejected=dict(tracker.rejected), events=tracker.events,
        limitation="정차 후보/가정별 보정량 검사. 노선 시작·끝/정차만으로 전원 하차 및 승차 전 빈 차를 입증하지 않음. 미태그 원인·실측 정확도 검증 아님.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--route", choices=B.STOPS, required=True)
    parser.add_argument("--terminal-id", required=True)
    parser.add_argument("--sections", type=int, nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.logs, args.route, args.terminal_id, args.sections, args.start, args.end)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "events"}, ensure_ascii=False, indent=2))
