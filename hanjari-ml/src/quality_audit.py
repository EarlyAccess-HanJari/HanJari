"""저장된 카드 집계의 일관성과 종점 보정 가정을 내부에서 검사한다. 외부 호출/인원 변경 없음.

실제 차내 인원 정답이 없으므로 정확도·미태그 인원 확정·탑승 성공률을 계산하지 않는다.
"""
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path

import build_dataset as B
import collect as C
import data_quality as DQ
import terminal_baseline as TB

# 저장된 노선 응답의 stId/staOrd와 위치 응답의 lastStnId/sectOrd 기준.
# 회차 지점이라는 사실만으로 전원 하차가 확인된 것은 아니다.
TERMINALS = {
    "jr03": {"naksan_park": ("낙산공원", "100900039", (1, 30))},
    "sb02": {"hansung_gate": ("한성대정문", "107900256", (1, 38)),
             "old_stone_museum": ("우리옛돌박물관.정법사", "107900329", (19,))},
}


class ShadowOffsets:
    """종점 잔여값을 뺀다는 가정을 회차 안에서만 검사한다. 운영 값으로 반환하지 않는다."""
    def __init__(self, terminal_id, sections, reset_points=()):
        self.terminal = TB.TerminalCandidates(terminal_id, sections)
        self.reset_points = set(reset_points) | {(str(terminal_id), section) for section in sections}
        self.previous, self.anchors = {}, {}
        self.stats = Counter()

    def step(self, now, rows):
        before = len(self.terminal.events)
        self.terminal.step(now, rows)
        current = {(r["vehicle_id"], r["plate"]): r for r in rows}
        for key in list(self.anchors):
            prev = self.previous.get(key)
            if prev is None or now.date() != prev[0].date() or (now - prev[0]).total_seconds() > 180:
                del self.anchors[key]
                self.stats["expired_after_gap_or_day"] += 1
        for key, row in current.items():
            prev = self.previous.get(key)
            at_terminal = (row["station_id"], row["section"]) in self.reset_points
            wrapped = prev and row["section"] is not None and prev[1] is not None and row["section"] < prev[1]
            if at_terminal or wrapped:
                if self.anchors.pop(key, None):
                    self.stats["cleared_at_next_trip"] += 1
            self.previous[key] = now, row["section"]
        for event in self.terminal.events[before:]:
            key = event["vehicle_id"], event["plate"]
            row = current.get(key)
            end = dt.datetime.fromisoformat(event["end"])
            if (row is not None and row["section"] is not None
                    and (row["station_id"], row["section"]) not in self.reset_points
                    and 0 <= (now - end).total_seconds() <= 90):
                self.anchors[key] = dict(offset=event["candidate_offset_max"], start=end)
                self.stats["departure_candidates"] += 1
        scenarios = []
        for key, row in current.items():
            anchor = self.anchors.get(key)
            if anchor is None:
                continue
            if (now - anchor["start"]).total_seconds() > 3600:
                del self.anchors[key]
                self.stats["expired_after_one_hour"] += 1
                continue
            if row["count"] < anchor["offset"]:
                del self.anchors[key]
                self.stats["invalidated_by_lower_api_count"] += 1
                continue
            self.stats["same_trip_observations"] += 1
            if anchor["offset"]:
                self.stats["positive_offset_observations"] += 1
            scenarios.append(dict(vehicle_id=key[0], raw=row["count"], hypothetical_lower=row["count"]-anchor["offset"],
                                  hypothetical_upper=row["count"], applied_subtraction=0))
        return scenarios


def audit_day(logs, day):
    folder = Path(logs) / day
    routes = {}
    for route in B.STOPS:
        statuses, errors = Counter(), Counter()
        terminals = TERMINALS.get(route, {})
        reset_points = {(station, section) for _, station, sections in terminals.values() for section in sections}
        trackers = {key: ShadowOffsets(station, sections, reset_points)
                    for key, (_, station, sections) in terminals.items()}
        snapshots, switches, large_changes, previous = 0, 0, 0, {}
        counts, first, last = [], None, None
        for now, items in B.snapshots(route, [str(folder)]):
            snapshots += 1
            first, last = first or now.isoformat(), now.isoformat()
            for stop in B.STOPS[route]:
                item = items.get(stop)
                if item is None:
                    continue
                issue = DQ.source_issue(item, now)
                statuses[issue] += 1
                vehicle = str(item.get("vehId1") or ""), str(item.get("plainNo1") or "")
                n = DQ.valid_count(item, now)
                prev = previous.get(stop)
                if prev and prev[1] != vehicle:
                    switches += 1
                if prev and prev[1] == vehicle and prev[2] is not None and n is not None and (now - prev[0]).total_seconds() <= 180:
                    large_changes += int(abs(n - prev[2]) >= 20)  # 승하차일 수도 있으므로 오류로 판정하지 않는다.
                previous[stop] = now, vehicle, n
                if n is not None:
                    counts.append(n)
            if trackers:
                try:
                    positions = B.read_items(folder / f"{route}_pos_{now:%H%M%S}.json")
                    rows = TB.observations(list(items.values()), positions, now)
                except (OSError, ValueError, KeyError, TypeError):
                    rows = []
                    errors["position_pair_unavailable"] += 1
                for tracker in trackers.values():
                    tracker.step(now, rows)
        if trackers:
            checkpoints, checks, positives = {}, Counter(), []
            for key, tracker in trackers.items():
                tracker.terminal.close()
                candidates = [dict(e, checkpoint=key) for e in tracker.terminal.events if e["candidate_offset_max"] > 0]
                name, station, sections = terminals[key]
                checkpoints[key] = dict(name=name, station_id=station, sections=list(sections), empty_verified=False,
                                        qualified_windows=len(tracker.terminal.events), positive_windows=len(candidates),
                                        candidate_max=max((e["candidate_offset_max"] for e in candidates), default=0),
                                        checks=dict(tracker.stats), rejected=dict(tracker.terminal.rejected))
                checks.update(tracker.stats)
                positives.extend(candidates)
            terminal = dict(status="shadow_only", qualified_windows=sum(v["qualified_windows"] for v in checkpoints.values()),
                            positive_windows=len(positives), candidate_max=max((e["candidate_offset_max"] for e in positives), default=0),
                            checks=dict(checks), errors=dict(errors), positive_candidates=positives, checkpoints=checkpoints)
        else:
            terminal = dict(status="terminal_not_configured")
        routes[route] = dict(snapshots=snapshots, first=first, last=last, target_statuses=dict(statuses),
                             first_vehicle_switches=switches, same_vehicle_changes_ge20=large_changes,
                             max_valid_api_count=max(counts, default=None), terminal=terminal)
    return dict(day=day, created_at=dt.datetime.now(C.KST).isoformat(), mode="internal_only",
                applied_to_display=False, applied_to_training=False, field_accuracy_verified=False,
                routes=routes, limitation="API 내부 일관성과 종점 차감 가정 검사. 실인원·미태그 인원 확정 및 탑승 확률 검증이 아님.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, default=B.LOG)
    parser.add_argument("--day", default=(dt.datetime.now(C.KST)-dt.timedelta(days=1)).strftime("%Y%m%d"))
    parser.add_argument("--output-dir", type=Path, default=B.ROOT / "reports/source-quality")
    args = parser.parse_args()
    dt.datetime.strptime(args.day, "%Y%m%d")
    report = audit_day(args.logs, args.day)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    C.write_snapshot(args.output_dir / (args.day + ".json"), (json.dumps(report, ensure_ascii=False, indent=2)+"\n").encode())
    print(json.dumps({"day": report["day"], "mode": report["mode"], "routes": {
        route: {k: v for k, v in result.items() if k != "terminal"} for route, result in report["routes"].items()}}, ensure_ascii=False))
