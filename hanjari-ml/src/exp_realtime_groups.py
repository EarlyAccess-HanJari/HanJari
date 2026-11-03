"""Offline comparison of real-time-only occupancy models; never promotes a model.

Labels are arrival API counts, not independently counted people. An API busType
split is explicitly provisional: it is NOT a verified small/large vehicle split.
Historical CSV values occur only in the separately named comparison model.
"""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import tarfile

import numpy as np
import pandas as pd

from api_response import response_items
import build_dataset as B
import data_quality as DQ


FILE = re.compile(r"(sb02|jr03)_(arr|pos)_(\d{6})\.json$")
REALTIME_FEATURES = [
    "eta", "stops_away", "r_now", "minute", "weekday", "route_code", "stop",
    "bus_type", "eta_gap", "eta2", "r2", "route_load", "pos_dwell",
    "pos_frac", "pos_sect", "source_age",
]
HISTORICAL_FEATURES = ["q_csv", "off_csv", "q_pending"]
PARAMS = dict(n_estimators=300, max_depth=5, learning_rate=0.06,
              min_child_weight=5, subsample=0.8, random_state=0, n_jobs=4,
              tree_method="hist", objective="reg:absoluteerror")
MIN_GROUP_TRIPS = 100


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_day(folder=None, archive=None):
    """Read one day without extracting archives or touching the source tree."""
    data = {r: {"arr": {}, "pos": {}} for r in B.STOPS}
    audit = Counter()

    def add(name, payload):
        match = FILE.fullmatch(Path(name).name)
        if not match:
            return
        route, kind, hms = match.groups()
        audit["files"] += 1
        try:
            items = response_items(json.loads(payload))
        except (ValueError, TypeError):
            audit["invalid_response"] += 1
            return
        if hms in data[route][kind]:
            raise ValueError(f"duplicate snapshot: {name}")
        data[route][kind][hms] = items

    if archive:
        with tarfile.open(archive, "r:gz") as t:
            for member in t:
                if member.isfile() and FILE.fullmatch(Path(member.name).name):
                    parts = Path(member.name).parts
                    if len(parts) != 2 or parts[0] != Path(archive).name[:8]:
                        raise ValueError(f"unexpected archive member: {member.name}")
                    with t.extractfile(member) as f:
                        add(member.name, f.read())
    else:
        for p in sorted(Path(folder).glob("*.json")):
            if FILE.fullmatch(p.name):
                add(p.name, p.read_bytes())
    return data, audit


def position_info(items, collected):
    result = {}
    for item in items:
        plate, vid = DQ.vehicle_key(item, "")
        made = DQ.source_time(item.get("dataTm"))
        if not plate or not vid or made is None or made.tzinfo is not None:
            continue
        if not -5 <= (collected - made).total_seconds() <= DQ.MAX_SOURCE_AGE:
            continue
        try:
            frac = float(item["sectDist"]) / float(item["fullSectDist"])
            if not np.isfinite(frac) or not 0 <= frac <= 1:
                frac = None
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            frac = None
        result[plate] = (vid, DQ.integer(item.get("sectOrd")),
                         DQ.integer(item.get("stopFlag")), frac)
    return result


def snapshot_rows(route, day, hms, items, pos_items, tab, audit):
    collected = dt.datetime.strptime(day + hms, "%Y%m%d%H%M%S")
    positions = position_info(pos_items, collected)
    counts = defaultdict(set)
    for item in items:
        for slot in "12":
            count = DQ.passenger_count(item, slot)
            if count is not None:
                counts[DQ.vehicle_key(item, slot)].add(count)
    loads = {}
    for item in items:
        for slot in "12":
            plate, vid = DQ.vehicle_key(item, slot)
            item["_passenger_conflict" + slot] = len(counts[(plate, vid)]) > 1
            item["_vehicle_mismatch" + slot] = plate in positions and positions[plate][0] != vid
            count = DQ.valid_count(item, collected, slot)
            if count is not None:
                loads[(plate, vid)] = count
    route_load = float(np.mean(list(loads.values()))) if loads else None
    rows = {}
    identities = {}
    for item in items:
        stop = DQ.integer(item.get("staOrd"))
        if stop not in B.STOPS[route]:
            continue
        identities[stop] = DQ.vehicle_key(item)
        issue = DQ.source_issue(item, collected)
        if issue != "ok":
            audit[issue] += 1
            continue
        plate, vid = identities[stop]
        sect = DQ.integer(item.get("sectOrd1"))
        raw_eta = DQ.integer(item.get("traTime1"))
        if sect is None or sect < 0 or sect > stop:
            audit["invalid_location"] += 1
            continue
        made = DQ.source_time(item.get("mkTm"))
        age = (collected - made).total_seconds()
        eta = raw_eta - age if raw_eta is not None and raw_eta >= 0 else None
        usable = eta is not None and eta >= 0
        if not usable:
            audit["expired_eta"] += 1
        pos = positions.get(plate)
        ps, dwell, frac = pos[1:] if pos and pos[0] == vid else (None, None, None)
        eta2_raw = DQ.integer(item.get("traTime2"))
        r2 = DQ.valid_count(item, collected, "2")
        eta2 = eta2_raw - age if eta2_raw is not None and eta2_raw - age >= 0 and r2 is not None else None
        row = dict(
            _usable_input=usable,
            date=day, time=collected.isoformat(), source_time=made.isoformat(),
            source_schema=DQ.SCHEMA_VERSION, route=route, stop=stop,
            plate=plate, vehicle_id=str(vid), bus_type=DQ.integer(item.get("busType1")),
            eta=eta, stops_away=stop-sect, r_now=DQ.passenger_count(item),
            minute=collected.hour*60+collected.minute, weekday=collected.weekday(),
            route_code=0 if route == "sb02" else 1, source_age=age,
            eta2=eta2, r2=r2 if eta2 is not None else None,
            eta_gap=eta2-eta if eta2 is not None and eta is not None else None,
            route_load=route_load, pos_sect=ps, pos_dwell=dwell, pos_frac=frac,
            q_csv=sum(tab.get((j, collected.hour), (0, 0))[0] for j in range(sect, stop)),
            off_csv=tab.get((stop, collected.hour), (0, 0))[1],
            q_pending=tab.get((ps, collected.hour), (0, 0))[0] if dwell == 1 and ps is not None and ps < stop else 0,
        )
        rows[stop] = row
    return collected, identities, rows


def closed_rows(route, day, data, tab, audit):
    """A label is available only when a later snapshot confirms a vehicle change.

    Gaps, invalid end counts and identity changes without a new plate do not
    establish an arrival. Repeated copies of one source update are counted once.
    """
    current = {}
    for hms, items in sorted(data["arr"].items()):
        t, identities, rows = snapshot_rows(route, day, hms, items, data["pos"].get(hms, []), tab, audit)
        for stop, identity in identities.items():
            row = rows.get(stop)
            old = current.get(stop)
            gap = old is not None and (t-old["last_seen"]).total_seconds() > B.MAX_GAP
            if old and (gap or old["identity"] != identity):
                end = old["last_row"]
                changed_plate = bool(identity[0] and identity[1] and identity[0] != old["identity"][0])
                if not gap and changed_plate and end is not None and end["stops_away"] == 0:
                    trip = "|".join([route, str(stop), *map(str, old["identity"]), end["time"]])
                    for seen in old["rows"]:
                        if seen["source_time"] <= end["source_time"]:
                            yield {**{k: v for k, v in seen.items() if not k.startswith("_")},
                                   "trip": trip, "arrive_time": end["time"],
                                   "label_available_at": t.isoformat(), "y": end["r_now"]}
                        else:
                            audit["label_source_regression"] += 1
                    audit["arrival_events"] += 1
                else:
                    audit["unconfirmed_segments"] += 1
                current.pop(stop)
                old = None
            if not identity[0] or not identity[1]:
                continue
            if old is None:
                old = {"identity": identity, "rows": [], "source_keys": set()}
                current[stop] = old
            old["last_seen"], old["last_row"] = t, row
            if row is not None and row["_usable_input"]:
                # mkTm repeated at a later poll is not another independent observation.
                key = row["source_time"]
                if key not in old["source_keys"]:
                    old["rows"].append(row)
                    old["source_keys"].add(key)
                else:
                    audit["duplicate_source_update"] += 1


def build(archive_dir, raw_dir, out):
    out.mkdir(parents=True, exist_ok=True)
    sources = {}
    for p in sorted(archive_dir.glob("2026*.tar.gz")):
        sources[p.name[:8]] = ("archive", p)
    for p in sorted(raw_dir.glob("2026*")):
        if p.is_dir():
            if p.name in sources:
                raise ValueError(f"two sources for {p.name}; select one immutable snapshot")
            sources[p.name] = ("folder", p)
    tables = {r: B.csv_tables(r) for r in B.STOPS}
    manifest = {"schema": DQ.SCHEMA_VERSION, "sources": [], "days": [],
                "historical_files": [{"file": p.name, "sha256": digest(p)}
                                     for r in B.STOPS for p in [B.OUT/f"{r}_hourly.csv", B.OUT/f"{r}_trips.csv"]]}
    writer = None
    with (out/"dataset.csv").open("w", newline="") as f:
        for day, (kind, path) in sorted(sources.items()):
            data, audit = read_day(**{kind: path})
            n = 0
            for route in B.STOPS:
                for row in closed_rows(route, day, data[route], tables[route], audit):
                    if writer is None:
                        writer = csv.DictWriter(f, fieldnames=list(row))
                        writer.writeheader()
                    writer.writerow(row)
                    n += 1
            source = {"date": day, "kind": kind, "path": str(path)}
            if kind == "archive":
                source["sha256"] = digest(path)
            else:
                files = [{"file": p.name, "sha256": digest(p)} for p in sorted(path.glob("*.json")) if FILE.fullmatch(p.name)]
                source["file_count"] = len(files)
                source["content_manifest_sha256"] = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            manifest["sources"].append(source)
            manifest["days"].append({"date": day, "rows": n, **audit})
            print(json.dumps(manifest["days"][-1]), flush=True)
    manifest["dataset_sha256"] = digest(out/"dataset.csv")
    (out/"source_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n")


def load_registry(path):
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    if payload.get("version") != 1 or not isinstance(payload.get("vehicles"), list):
        raise ValueError("invalid vehicle group registry")
    registry = {}
    for item in payload["vehicles"]:
        key = (item.get("route"), item.get("plate"), item.get("vehicle_id"))
        if (key[0] != "sb02" or not all(isinstance(x, str) and x.strip() for x in key)
                or item.get("group") not in ("sb02_small", "sb02_large")
                or not isinstance(item.get("evidence"), str) or not item["evidence"].strip()):
            raise ValueError("vehicle groups require an identity and physical-size evidence")
        start, end = item.get("valid_from"), item.get("valid_until")
        for value in (start, end):
            dt.datetime.strptime(str(value), "%Y%m%d")
        if start > end or key in registry:
            raise ValueError("invalid or duplicate vehicle validity period")
        registry[key] = item
    return registry


def group_for(row, registry=None):
    if row.route == "jr03":
        return "jr03"
    if registry is not None:
        item = registry.get((row.route, row.plate, row.vehicle_id))
        return item["group"] if item and item["valid_from"] <= row.date <= item["valid_until"] else "unverified"
    return f"sb02_api{int(row.bus_type)}" if pd.notna(row.bus_type) and row.bus_type in (0, 1) else "unverified"


def splits(d):
    days = np.array(sorted(d.date.unique()))
    if len(days) < 23:
        raise ValueError("need at least 23 collected days for this fixed evaluation")
    development, holdout = days[:-7], days[-7:]
    blocks = np.array_split(development, 4)
    for i in range(1, 4):
        yield f"validation_{i}", np.concatenate(blocks[:i]).tolist(), blocks[i].tolist()
    yield "holdout", development.tolist(), holdout.tolist()


def metrics(d, pred):
    err = np.asarray(pred)-d.y.to_numpy()
    weights = 1 / d.groupby("trip")["trip"].transform("size").to_numpy()
    order = np.argsort(np.abs(err))
    p90 = np.interp(.9, np.cumsum(weights[order])/weights.sum(), np.abs(err)[order])
    return {"rows": len(d), "arrival_events": int(d.trip.nunique()), "days": int(d.date.nunique()),
            "mae": float(np.average(np.abs(err), weights=weights)),
            "bias": float(np.average(err, weights=weights)), "p90_absolute_error": float(p90),
            "error_over_10_share": float(np.average(np.abs(err)>10, weights=weights))}


def fit_predict(tr, te, historical=False, model_path=None):
    from xgboost import XGBRegressor
    features = REALTIME_FEATURES + (HISTORICAL_FEATURES if historical else [])
    base_tr = tr.r_now + (tr.q_csv+tr.q_pending if historical else 0)
    base_te = te.r_now + (te.q_csv+te.q_pending if historical else 0)
    weights = 1/tr.groupby("trip")["trip"].transform("size")
    model = XGBRegressor(**PARAMS).fit(tr[features].astype(float), tr.y-base_tr, sample_weight=weights)
    if model_path:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model.save_model(model_path)
    return np.maximum(0, base_te.to_numpy()+model.predict(te[features].astype(float)))


def summarize(d, pred):
    result = {"all": metrics(d, pred), "groups": {}, "distance": {}, "days": {}}
    for group in sorted(d.group.unique()):
        at = d.group.eq(group).to_numpy()
        result["groups"][group] = metrics(d[at], pred[at])
    for name, mask in [("at_stop", d.stops_away.eq(0)), ("1_to_2_stops", d.stops_away.between(1, 2)),
                       ("3_plus_stops", d.stops_away.ge(3)), ("1_plus_stops", d.stops_away.ge(1))]:
        at = mask.to_numpy()
        if at.any():
            result["distance"][name] = metrics(d[at], pred[at])
    for day in sorted(d.date.unique()):
        at = d.date.eq(day).to_numpy()
        result["days"][day] = metrics(d[at], pred[at])
    return result


def experiment(out, registry_path=None):
    import xgboost
    registry = load_registry(registry_path) if registry_path else None
    d = pd.read_csv(out/"dataset.csv", dtype={"date": str, "vehicle_id": str})
    if not (d.source_schema == DQ.SCHEMA_VERSION).all() or not np.isfinite(d["r_now"]).all():
        raise ValueError("invalid source dataset")
    if not (d.time <= d.arrive_time).all() or not (d.arrive_time < d.label_available_at).all():
        raise ValueError("invalid target availability")
    d["group"] = [group_for(row, registry) for row in d.itertuples()]
    inventory = []
    for keys, part in d.groupby(["route", "plate", "vehicle_id", "group"], sort=True):
        inventory.append(dict(zip(["route", "plate", "vehicle_id", "group"], keys),
                              rows=len(part), arrival_events=int(part.trip.nunique()),
                              days=int(part.date.nunique()), first_date=part.date.min(), last_date=part.date.max(),
                              api_bus_types=sorted(int(v) for v in part.bus_type.dropna().unique())))
    (out/"vehicle_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+"\n")
    split_list = list(splits(d))
    spec = {"status": "offline_experiment", "target": "arrival_API_count_not_physical_headcount",
            "group_basis": "verified_vehicle_size" if registry is not None else "API_busType_provisional_not_size",
            "registry": json.loads(registry_path.read_text()) if registry_path else None,
            "dataset_sha256": digest(out/"dataset.csv"), "source_schema": DQ.SCHEMA_VERSION,
            "realtime_features": REALTIME_FEATURES, "historical_comparison_features": HISTORICAL_FEATURES,
            "params": PARAMS, "xgboost_version": xgboost.__version__, "min_group_arrivals": MIN_GROUP_TRIPS,
            "date_splits": [{"name": name, "train": tr, "test": te} for name, tr, te in split_list],
            "limitations": ["API error can occur in both input and label", "no independent boarding labels or verified capacity",
                            "3-group API-code split is not a physical size classification without a registry",
                            "arrival events at neighboring stops may be correlated", "no model promotion"],
            "comparison": "same fixed point-model recipe, not an exact replay of the deployed model"}
    # Write the fixed specification before any score is computed.
    (out/"experiment_spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2)+"\n")
    results = {"spec": spec, "inventory": inventory, "folds": []}
    predictions = []
    for name, train_days, test_days in split_list:
        cutoff = dt.datetime.strptime(test_days[0], "%Y%m%d").isoformat()
        tr = d[d.date.isin(train_days) & d.label_available_at.lt(cutoff)].copy()
        te = d[d.date.isin(test_days)].copy()
        if set(tr.trip) & set(te.trip):
            raise ValueError("trip leakage")
        model_dir = out/"models"/name if name == "holdout" else None
        path = lambda label: model_dir/f"{label}.json" if model_dir else None
        preds = {"persistence": te.r_now.to_numpy(dtype=float)}
        for model_name, historical in [("historical_pooled", True), ("realtime_pooled", False)]:
            preds[model_name] = fit_predict(tr, te, historical, path(model_name))
        fallback = {}
        for model_name, column in [("realtime_2_routes", "route"), ("realtime_3_groups", "group")]:
            pred = preds["realtime_pooled"].copy()
            fallback[model_name] = []
            for group in sorted(te[column].unique()):
                sub_tr = tr[tr[column].eq(group)]
                at = te[column].eq(group).to_numpy()
                if group == "unverified" or sub_tr.trip.nunique() < MIN_GROUP_TRIPS or sub_tr.date.nunique() < 2:
                    fallback[model_name].append({"group": group, "rows": int(at.sum()), "reason": "unverified_or_insufficient_training"})
                    continue
                pred[at] = fit_predict(sub_tr, te[at], model_path=path(model_name+"_"+group))
            preds[model_name] = pred
        fold = {"name": name, "train_days": train_days, "test_days": test_days,
                "train_rows": len(tr), "test_rows": len(te), "fallback": fallback,
                "models": {label: summarize(te, pred) for label, pred in preds.items()}}
        results["folds"].append(fold)
        print(json.dumps({"fold": name, "metrics": {label: value["all"] for label, value in fold["models"].items()}}), flush=True)
        pred_frame = te[["date", "route", "group", "trip", "time", "stops_away", "r_now", "y"]].copy()
        pred_frame["fold"] = name
        for label, pred in preds.items():
            pred_frame[label] = pred
        predictions.append(pred_frame)
        (out/"results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    pd.concat(predictions).to_csv(out/"predictions.csv", index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "train"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--archives", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--vehicle-groups", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        if not args.archives or not args.raw:
            parser.error("build requires --archives and --raw")
        build(args.archives, args.raw, args.out)
    else:
        experiment(args.out, args.vehicle_groups)


if __name__ == "__main__":
    main()
