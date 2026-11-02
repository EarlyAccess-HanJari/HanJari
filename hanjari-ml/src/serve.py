"""서비스 예측 — 백엔드가 부르는 곳.

  export(lite)             전체 데이터로 학습 → models/ 또는 models/lite/ (XGB json + meta.json). 날짜 분할 예측으로 '여유' 기준도 정함.
  predict_live(n_ahead)    [라이트] 버스 API 를 지금 1번 호출(노선 2개 × 도착·위치 = 4건) → 6개 정류장 첫째 버스 예측.
                           수집 이력 없이 어디서든 동작. 오라클 이력 모델과 정확도 같음(TASKS.md 09-30, MAE 3.045 vs 3.036).
  predict_now(n_ahead)     [전체] 오늘 수집 로그(오라클) → 같은 결과.
  결과: 정류장마다 예상 도착재차(10~90%)·P(탑승)·단계·근거.

피처는 학습과 **같은 코드**(build_dataset.build(open_=True) → train.features)로 만든다 → 학습/서비스 어긋남 방지.
단계(기능흐름도 F-04 순서):
  1. 확률 보류     — 정보가 오래됨 / 수업 없는 날(일요일·공휴일) / 그 칸(시간대×거리)에 기준을 정할 데이터 부족
  2. 판단하기 일러요 — 도착재차 10~90% 구간이 WIDE 명보다 넓음
  3. 여유 있음     — P ≥ 칸별 '여유' 기준(API 기준 계산 탑승 97%, 수업 직전 98% 를 지킨 가장 낮은 P)
  4. 어려울 수 있음 — P ≤ 0.3
  5. 빠듯함        — 그 사이
실행: python src/serve.py latest 5     라이트, 수집기가 방금 받은 스냅샷으로(운영 서버, API 호출 없음) = predict_latest — 백엔드는 이것
      python src/serve.py sample 5     라이트, 레포에 든 실제 스냅샷(data/sample, 9/30 13:11)으로 — 키·호출 없음
      python src/serve.py live 5       라이트, 앞에 5명 (API 키 필요, 호출 4건)
      python src/serve.py check        라이트 자체 점검 (호출 없음)
      python src/serve.py export-lite  라이트 모델 다시 학습 (수집 로그·원본 CSV 필요)
"""
import datetime as dt, json, sys, tempfile
from pathlib import Path
import numpy as np, pandas as pd, xgboost as xgb
import build_dataset as B
import collect as C
import train as T
import data_quality as DQ

MODELS = B.ROOT / "models"
SAMPLE = B.ROOT / "data/sample/20260930"  # 실제 스냅샷 1장(도착·위치 × 2노선) — 키 없이 돌려보기용
# 수집 이력(최근 60~90분 다른 버스들)이 있어야 계산되는 피처 — 라이트 모델은 뺀다
HISTORY = ["since_prev", "hw_ratio", "q_bias3", "q_prev", "q_today", "q_eb", "q_live2", "q_today2", "q_rate", "gap_sum"]
FULL = sum(T.GROUPS.values(), [])
LITE = [f for f in FULL if f not in HISTORY]


def lite_rule(d):
    """라이트 규칙: 지금 재차 + 남은 구간 CSV 평균 순승차 + 정차 중 미반영 몫 (오늘 실측 q_eb 대신)"""
    return d.r_now + d.q_csv + d.q_pending.fillna(0)
KST = dt.timezone(dt.timedelta(hours=9))
# ponytail: 기능흐름도는 60초지만 수집 간격이 한산한 시간 150초라 180초. 백엔드가 API 를 직접 부르게 되면 60초로.
MAX_AGE = 180
WIDE = 20      # ponytail: 10~90% 구간 폭(명) 잠정값. 데이터 쌓이면 '판단 이르다' 비율·정확도로 다시 정할 것
HARD = 0.3
NAMES = {("sb02", "30"): "한성대입구역5번출구", ("sb02", "31"): "한성대입구역2번출구", ("sb02", "32"): "녹십자약국",
         ("jr03", "19"): "동대문역.흥인지문", ("jr03", "20"): "동묘앞역", ("jr03", "23"): "창신역4번출구"}
LEVELS = ["확률 보류", "판단하기 일러요", "여유 있음", "어려울 수 있음", "빠듯함"]


def seg_name(k):
    return next(n for n, (a, b) in T.SEGS.items() if a <= k <= b)


def calibration_mask(d, Q, qs):
    """서비스에서 안내할 수 있는 확인 차량·요일·구간 폭으로만 '여유' 기준을 정한다."""
    caps = T.verified_capacities(d)
    widths = np.array([np.interp(0.9, qs, q) - np.interp(0.1, qs, q) for q in Q])
    return (np.isfinite(caps) & (d.r_now.values <= caps) & (widths <= WIDE)
            & ~d.holiday.values & d.weekday.notna().values & (d.weekday.values != "일"))


def export(lite=False, until=None, out_dir=None):
    """until: 이 날짜(YYYYMMDD)까지만 학습(매일 작업·과거 재현용). 반환: meta (oof = 날짜 분할 예측 성적)."""
    d = T.features()
    if until:
        d = d[d.date <= until]
    feats, out_dir = (LITE, Path(out_dir or MODELS / "lite")) if lite else (FULL, Path(out_dir or MODELS))
    if lite:
        # 평일만 학습(10-01 실험: 평일 4폴드 모두 개선, MAE 3.09→2.84, 수업 직전 6.0→4.6). 일요일·공휴일은 서비스에서 '확률 보류'
        # 10-05: 토요일도 정규수업이 있어(지용) 학습에 포함 — 빼는 건 일요일·공휴일만
        d = d[~d.holiday & (d.weekday != "일")].assign(rule=lambda x: lite_rule(x))
    keep, oof = [], []
    for tr, te in T.folds(d):  # 날짜 블록 전진 검증 — '여유' 기준은 처음 보는 날 예측으로 정한다
        point, Pm, Q = T.predict(T.fit(tr, feats), te, quantiles=True)
        oof.append(T.metrics(point, Pm, te))
        valid = calibration_mask(te, Q, T.QS)
        keep.append((Pm[valid], (te.y.values[:, None] <= T.thresholds(te)).astype(float)[valid],
                     np.repeat(te.stops_away.values[:, None], len(T.NS), 1)[valid], np.repeat(te.is_peak.values[:, None] == 1, len(T.NS), 1)[valid]))
    if not keep:
        raise ValueError("날짜 분할 검증에 필요한 데이터가 부족함")
    Pm, Bd, K, PK = (np.concatenate(x) for x in zip(*keep))
    th = T.pick_thresholds(Pm, Bd, K, PK)
    m = T.fit(d, feats)
    if m["m0"] is None:
        raise ValueError("바로 앞 버스 학습 데이터가 50행 미만: 모델 저장 보류")
    log_days = sorted(p.name for p in B.LOG.glob("2026*") if p.is_dir() and (not until or p.name <= until))
    for route in B.STOPS:  # q_hist 용 과거 순증감 표 (로그 한 번 읽음)
        B.build(route, log_days)
    out_dir.mkdir(parents=True, exist_ok=True)
    m["pt"].save_model(out_dir / "point.json")
    m["qm"].save_model(out_dir / "quantile.json")
    m["m0"].save_model(out_dir / "k0.json")
    meta = dict(
        feats=feats, f0=T.F0, qs=T.QS.tolist(), cats=d.attrs["cats"],
        capacity_policy=T.capacity_policy(), calibration_rows=len(Pm),
        res0={str(k): v.tolist() for k, v in m["res0"].items()},
        thresholds=[[p, s, None if t in (None, "부족") else float(t), t == "부족"] for (p, s), (t, _, _) in th.items()],
        hist_all={r: [[j, h, v] for (j, h), v in tab.items()] for r, tab in B.HIST_ALL.items()},
        lite=lite, tab={r: [[j, h, *v] for (j, h), v in B.csv_tables(r).items()] for r in B.STOPS},  # 원본 CSV 없이 쓰는 과거 평균 표
        oof={k: float(np.nanmean([o[k] for o in oof])) for k in oof[0]},
        trained_on=sorted(d.date.unique().tolist()), xgb=T.XGB_KW, created=dt.datetime.now(KST).isoformat(timespec="seconds"))
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, default=lambda o: o.item()))  # numpy 스칼라
    (out_dir / "metrics.json").write_text(json.dumps(dict(meta["oof"], days=len(meta["trained_on"])), indent=1))  # dvc metrics show
    print("저장:", out_dir, "| 학습일", meta["trained_on"])
    for p, s, t, short in meta["thresholds"]:
        print(f"  {p:6} {s:10} '여유' 기준 {'데이터 부족 → 확률 보류' if short else ('없음(여유 표시 안 함)' if t is None else f'P ≥ {t:.2f}')}")
    return meta


_M = {}


def load(lite, src=None):
    src = Path(src or (MODELS / "lite" if lite else MODELS))
    if src not in _M:
        meta = json.loads((src / "meta.json").read_text())
        m = dict(feats=meta["feats"], m0=xgb.XGBRegressor(), pt=xgb.XGBRegressor(), qm=xgb.XGBRegressor())
        for k, f in (("pt", "point"), ("qm", "quantile"), ("m0", "k0")):
            m[k].load_model(src / f"{f}.json")
        m["res0"] = {k == "True": np.array(v) for k, v in meta["res0"].items()}
        m["qs"] = np.array(meta["qs"])
        meta["hist_d"] = {r: {(j, h): v for j, h, v in tab} for r, tab in meta["hist_all"].items()}
        meta["tab_d"] = {r: {(j, h): tuple(v) for j, h, *v in tab} for r, tab in meta["tab"].items()} if "tab" in meta else {}
        _M[src] = (m, meta)
    m, meta = _M[src]
    return m, meta


def level(p, q10, q90, k, peak, weekday_ok, th, age):
    if age > MAX_AGE:
        return "확률 보류", f"정보가 {age:.0f}초 전 것"
    if not weekday_ok:
        return "확률 보류", "일요일·공휴일(수업 없는 날은 아직 검증 전)"
    cell = ("수업 직전" if peak else "평소", seg_name(k))
    t, short = th[cell]
    if short:
        return "확률 보류", "이 시간대·거리는 검증 데이터 부족"
    if q90 - q10 > WIDE:
        return "판단하기 일러요", f"도착 인원 예상 폭이 {q10:.0f}~{q90:.0f}명으로 넓음"
    if t is not None and p >= t:
        return "여유 있음", f"P {p:.2f} ≥ 기준 {t:.2f}"
    if p <= HARD:
        return "어려울 수 있음", f"P {p:.2f} ≤ {HARD}"
    if t is None:
        return "빠듯함", f"P {p:.2f}, {cell[0]}·{cell[1]}은 '여유' 안내 기준을 충족하지 못한 구간"
    return "빠듯함", f"P {p:.2f} < 기준 {t:.2f}"


def check_n(n_ahead):
    if not isinstance(n_ahead, (int, np.integer)) or not 0 <= n_ahead <= T.NS[-1]:
        raise ValueError(f"n_ahead 는 0~{T.NS[-1]} 정수")


def probability_issue(route, bus_type, r_now, meta, plate="", vehicle_id=""):
    issue = DQ.field_validation_issue(route, plate, str(vehicle_id))
    if issue:
        return issue
    if meta.get("capacity_policy") != T.capacity_policy():
        return "model_unverified"
    capacity = DQ.verified_capacity(route, plate, str(vehicle_id))
    if r_now is None or not np.isfinite(r_now) or r_now < 0:
        return "passenger_unavailable"
    if r_now > capacity:
        return "capacity_exceeded"
    return None


def probability_hold(route, bus_type, r_now, meta, plate="", vehicle_id=""):
    issue = probability_issue(route, bus_type, r_now, meta, plate, vehicle_id)
    return DQ.REASONS.get(issue) if issue else None


class NoSnapshotError(RuntimeError):
    pass


def latest_snapshot(src, route=None):
    """최신 정상 도착 응답을 우선한다. 위치 파일 지연 때문에 지난 버스로 되돌아가지 않는다."""
    if route is None:
        snapshots = [latest_snapshot(src, r) for r in B.STOPS]
        return max(t for t, _ in snapshots), [f for _, files in snapshots for f in files]
    for arr in sorted(src.glob(f"{route}_arr_*.json"), reverse=True):
        try:
            B.read_items(arr)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        stamp = arr.stem.rsplit("_", 1)[-1]
        files = [arr]
        # 같은 시각 위치는 모델 피처용. 더 최신 위치는 통과 확인에만 쓰며 과거 피처에 섞지 않는다.
        for pos in sorted(src.glob(f"{route}_pos_*.json"), reverse=True):
            if pos.stem.rsplit("_", 1)[-1] < stamp:
                break
            try:
                B.read_items(pos)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if len(files) == 1 or pos.stem.rsplit("_", 1)[-1] == stamp:
                files.append(pos)
        return stamp, files
    raise NoSnapshotError("정상 도착 스냅샷이 없음(수집 또는 API 응답 확인 필요)")


def exclude_departed(snap, now):
    """복사본에만 적용: 더 새로운 동일 차량 위치로 통과가 확인되면 둘째 버스를 첫째로 선택한다."""
    passed = set()
    for route in B.STOPS:
        positions = {}
        for f in sorted(snap.glob(f"{route}_pos_*.json")):
            for v in B.read_items(f):
                made = DQ.source_time(v.get("dataTm"))
                key = (str(v.get("vehId") or ""), str(v.get("plainNo") or "").strip())
                if made is not None and made.tzinfo is None and -5 <= (now - made).total_seconds() <= MAX_AGE:
                    if key not in positions or made > positions[key][0]:
                        positions[key] = made, v
        for f in snap.glob(f"{route}_arr_*.json"):
            body = json.loads(f.read_text())
            for it in body["msgBody"]["itemList"] or []:
                stop = B.num(it.get("staOrd"))
                if stop not in B.STOPS[route]:
                    continue
                source = DQ.source_time(it.get("mkTm"))

                def departed(slot):
                    key = (str(it.get("vehId" + slot) or ""), str(it.get("plainNo" + slot) or "").strip())
                    pos = positions.get(key)
                    if source is None or source.tzinfo is not None or pos is None or pos[0] < source:
                        return False
                    section = B.num(pos[1].get("sectOrd"))
                    # 목표 정류장에 정차 중인 차를 통과 차량으로 처리하지 않는다.
                    return section is not None and (section > stop or section == stop and B.num(pos[1].get("stopFlag")) == 0)

                if not departed("1"):
                    continue
                next_section = B.num(it.get("sectOrd2"))
                next_eta = B.num(it.get("traTime2"))
                if (str(it.get("plainNo2") or "").strip() and (DQ.integer(it.get("vehId2")) or 0) > 0
                        and next_section is not None and 0 < next_section <= stop
                        and next_eta is not None and next_eta >= 0 and not departed("2")):
                    for key, value in list(it.items()):
                        if key.endswith("2") and key[:-1] + "1" in it:
                            it[key[:-1] + "1"] = value
                    it.update(plainNo2="", vehId2="0", traTime2="0", reride_Num2="", rerdie_Div2="0")
                else:
                    passed.add((route, str(stop)))
            f.write_text(json.dumps(body, ensure_ascii=False))
    return passed


def check_arrival(result, now, passed=False):
    """ETA 만료는 통과 확정이 아니다. 새 안내를 기다리는 동안 옛 인원·확률을 현재 값으로 내주지 않는다."""
    if result["arrival_stale"]:
        return
    target = dt.datetime.fromisoformat(result["arrival_at"]).replace(tzinfo=None)
    if passed or now >= target:
        result["arrival_status"] = "passed" if passed else "checking"
        result["r_now"] = None
        hold_result(result, "arrival_passed" if passed else "arrival_checking")


def predict_now(n_ahead, now=None, max_age=MAX_AGE):
    """[전체] n_ahead: 내 앞에 기다리는 사람 수(0~40). 오늘 수집 로그에서 가장 최근 스냅샷 기준."""
    check_n(n_ahead)
    m, meta = load(False)
    now = now or dt.datetime.now(KST).replace(tzinfo=None)
    day = now - dt.timedelta(hours=5)  # 05시 전은 전날 운행일 — 전날 폴더도 같이 읽음
    days = sorted({day.strftime("%Y%m%d"), now.strftime("%Y%m%d")})
    rows = [r for route in B.STOPS for r in B.build(route, days, open_=True, hist_all=meta["hist_d"].get(route, {}))]
    return results(rows, m, meta, n_ahead, now, max_age, lite=False)


def predict_live(n_ahead, key=None, log_dir=None, model_dir=None, reference_now=None):
    """[라이트] 버스 API 를 지금 1번 불러 예측. key 없으면 .env 의 SEOUL_BUS_API_KEY.
    log_dir 를 주면 API 대신 그 폴더(수집 로그 날짜 폴더)의 **가장 최근 스냅샷**으로 — 점검용, 호출 없음."""
    check_n(n_ahead)
    m, meta = load(True, model_dir)
    now = dt.datetime.now(KST).replace(tzinfo=None)
    with tempfile.TemporaryDirectory() as tmp:
        if log_dir is None:
            if not C.allowed(now):
                return []  # 01:30~05:00 새벽엔 API 를 부르지 않음(버스도 없음)
            key = key or (C.keys() or [None])[0]
            if not key:
                raise RuntimeError(".env 에 SEOUL_BUS_API_KEY 가 없음")
            snap = Path(tmp) / now.strftime("%Y%m%d")
            snap.mkdir()
            days = [str(snap)]
            for route, rid in C.ROUTES.items():
                for kind, url in C.URLS.items():
                    body = C.fetch(url, key, rid)
                    head = json.loads(body)["msgHeader"]
                    if str(head.get("headerCd")) != "0":
                        raise RuntimeError(f"버스 API 오류({route} {kind}): {head.get('headerMsg')}")
                    (snap / f"{route}_{kind}_{now:%H%M%S}.json").write_bytes(body)
        else:  # 가장 최근 스냅샷 1장만 복사 — 실시간 호출 결과와 같은 입력
            sources = list(log_dir) if isinstance(log_dir, (list, tuple)) else [Path(log_dir)]
            snapshots = []
            for route in B.STOPS:
                for src in sources:
                    try:
                        snapshots.append(latest_snapshot(Path(src), route))
                        break
                    except RuntimeError:
                        continue  # 한 노선의 실패가 다른 노선의 새 응답을 가리지 않게
            snapshot_files = [f for _, files in snapshots for f in files]
            if not snapshot_files:
                raise NoSnapshotError("정상 도착 스냅샷이 없음(수집 또는 API 응답 확인 필요)")
            for f in snapshot_files:
                dest = Path(tmp) / f.parent.name
                dest.mkdir(exist_ok=True)
                (dest / f.name).write_bytes(f.read_bytes())
            days = sorted(str(p) for p in Path(tmp).iterdir())
            now = max(dt.datetime.strptime(f.parent.name + f.stem[-6:], "%Y%m%d%H%M%S") for f in snapshot_files)
        # 위치 API가 먼저 갱신되고 도착 API가 옛 차량을 유지하는 경우도 처리한다.
        now = reference_now or now
        passed = set().union(*(exclude_departed(Path(day), now) for day in days))
        # 임시 폴더를 절대 경로로 넘김 — 예전엔 B.LOG 전역을 바꿨다 되돌려서 동시 요청이 꼬이고 B.LOG 가 지워진 폴더로 남았다(10-05 정원 발견)
        rows = [r for route in B.STOPS
                for r in B.build(route, days, open_=True, hist_all=meta["hist_d"].get(route, {}), tab=meta["tab_d"][route])]
    out = results(rows, m, meta, n_ahead, now, MAX_AGE, lite=True)
    for result in out:
        check_arrival(result, now, (result["route"], result["stop"]) in passed)
    return out


def predict_latest(n_ahead):
    """[운영 서버의 백엔드용] 수집기가 방금 저장한 스냅샷으로 예측 — 버스 API 를 따로 부르지 않음(한도 안 씀).
    스냅샷이 MAX_AGE 초보다 오래되면(수집 중단·새벽) 전부 '확률 보류'."""
    now = dt.datetime.now(KST).replace(tzinfo=None)
    folders = sorted((p for p in B.LOG.glob("20*") if p.is_dir() and p.name <= now.strftime("%Y%m%d")), reverse=True)[:2]
    if not folders:
        raise NoSnapshotError("버스 수집 로그가 없음")
    return predict_live(n_ahead, log_dir=folders, reference_now=now)


def hold_result(result, issue, reason=None):
    result.update(level="확률 보류", reason=reason or DQ.REASONS[issue], prediction_status=issue,
                  load_pred=None, load_10=None, load_90=None, p_board=None)


def source_health(now=None):
    """프로세스 생존과 실제 데이터 갱신 상태를 분리한다. 추가 API 호출 없음."""
    now = now or dt.datetime.now(KST).replace(tzinfo=None)
    folders = sorted((p for p in B.LOG.glob("20*") if p.is_dir() and p.name <= now.strftime("%Y%m%d")), reverse=True)[:2]
    routes = {}
    sched = C.load_sched()
    for route in B.STOPS:
        entry = {"status": "missing", "collected_at": None, "age_sec": None}
        for folder in folders:
            try:
                _, files = latest_snapshot(folder, route)
            except RuntimeError:
                continue
            arr = files[0]
            made = dt.datetime.strptime(arr.parent.name + arr.stem[-6:], "%Y%m%d%H%M%S")
            age = (now - made).total_seconds()
            entry.update(status="fresh" if -5 <= age <= MAX_AGE else "stale",
                         collected_at=made.replace(tzinfo=KST).isoformat(), age_sec=round(age))
            items = B.read_items(arr)
            if entry["status"] == "fresh":
                times = [DQ.source_time(it.get("mkTm")) for it in items]
                if items and not any(t is not None and t.tzinfo is None and -5 <= (now - t).total_seconds() <= MAX_AGE for t in times):
                    entry["status"] = "stale"
            break
        if not C.allowed(now, route, sched):
            entry["status"] = "outside_service"
        routes[route] = entry
    return routes


def results(rows, m, meta, n_ahead, now, max_age, lite):
    out, eligible, indices = [], [], []
    for row in rows:
        r = dict(row)
        t_snap = dt.datetime.strptime(str(r["date"]) + r["time"], "%Y%m%d%H:%M:%S")
        age = (now - t_snap).total_seconds() if max_age is not None else 0
        status = r.get("data_status", "source_time_unknown")
        made = DQ.source_time(r.get("source_updated"))
        source_now = now if max_age is not None else t_snap
        source_stale = made is None or made.tzinfo is not None or not -5 <= (source_now - made).total_seconds() <= MAX_AGE
        if source_stale and status == "ok":
            status = "source_time_unknown" if made is None or made.tzinfo is not None else "source_stale"
        stale = source_stale or age > MAX_AGE or age < -5
        arrival_base = made if made is not None and made.tzinfo is None else t_snap
        result = dict(route=r["route"], stop=str(r["stop"]), stop_name=NAMES[(r["route"], str(r["stop"]))],
                      plate=r["plate"], vehicle_id=str(r.get("vehicle_id", "")),
                      stops_away=int(r["stops_away"]), eta_sec=int(r["eta"]), r_now=DQ.integer(r["r_now"]),
                      updated=t_snap.strftime("%H:%M:%S"), updated_at=t_snap.replace(tzinfo=KST).isoformat(),
                      source_updated=r.get("source_updated"), data_status=status, arrival_stale=stale,
                      arrival_at=(arrival_base + dt.timedelta(seconds=int(r["eta"]))).replace(tzinfo=KST).isoformat(),
                      arrival_status="upcoming")
        if stale or status != "ok":
            result["r_now"] = None
        check_arrival(result, source_now)
        issue = result.get("prediction_status") or ("collection_stale" if age > MAX_AGE or age < -5 else status if status != "ok" else None)
        if not issue:
            issue = probability_issue(r["route"], r["bus_type"], r["r_now"], meta, r["plate"], r.get("vehicle_id", ""))
        if issue:
            hold_result(result, issue)
            if stale:
                # 배포 전에 열어 둔 화면도 '전 것'으로 지연을 알아본다. 새 화면은 구조화 상태를 쓴다.
                source_age = (source_now - made).total_seconds() if made is not None and made.tzinfo is None else age
                seconds = max(age, source_age, 0)
                result["reason"] = f"정보가 {seconds:.0f}초 전 것이어서 갱신을 기다리고 있어요"
        else:
            indices.append(len(out))
            eligible.append(r)
        out.append(result)
    if not eligible:
        return out  # 결측을 0으로 채우거나 미검증 입력에 모델을 실행하지 않는다.
    d = T.features(pd.DataFrame(eligible).assign(arrive_time=""), cats=meta["cats"])
    if lite:
        d = d.assign(rule=lite_rule(d))
    point, Pm, Q = T.predict(m, d, quantiles=True)
    qs = np.array(meta["qs"])
    th = {(p, s): (t, short) for p, s, t, short in meta["thresholds"]}
    for i, r in enumerate(d.itertuples()):
        result = out[indices[i]]
        q10, q90 = np.interp([0.1, 0.9], qs, Q[i])
        p = float(Pm[i, n_ahead])
        if not np.isfinite([point[i], q10, q90, p]).all() or not 0 <= p <= 1:
            hold_result(result, "prediction_invalid")
            continue
        lv, why = level(p, q10, q90, r.stops_away, r.is_peak == 1,
                        not r.holiday and pd.notna(r.weekday) and r.weekday != "일", th, 0)
        if lv == "확률 보류":
            hold_result(result, "calibration_hold", why)
        else:
            result.update(load_pred=round(float(point[i]), 1), load_10=round(float(q10), 1),
                          load_90=round(float(q90), 1), p_board=round(p, 3), level=lv, reason=why,
                          prediction_status="ok")
    return out


def demo(model_dir=None):
    """라이트 점검 — data/sample 스냅샷으로(API 호출 없음). 매일 작업의 합격 판정에도 씀."""
    run = lambda n: predict_live(n, log_dir=SAMPLE, model_dir=model_dir)
    res = run(0)
    assert res and all(r["level"] in LEVELS for r in res)
    assert T.cap("jr03", "0") == T.CAPACITY[("jr03", "0")], "정원은 관측 최대로 올라가지 않음"
    assert all(r["p_board"] is None and r["load_pred"] is None if r["level"] == "확률 보류"
               else np.isfinite([r["p_board"], r["load_pred"]]).all() for r in res), "보류/null 또는 유한 예측 계약"
    assert all(0 <= r["load_10"] <= r["load_pred"] + 1e-6 or r["stops_away"] == 0 for r in res if r["level"] != "확률 보류")
    for n in (0, 10, 30):  # 앞사람이 많을수록 확률은 줄기만 해야 함
        ps = [r["p_board"] for r in run(n)]
        if n:
            assert all(a is None and b is None or a is not None and b is not None and a <= b + 1e-9 for a, b in zip(ps, prev)), "앞사람이 늘었는데 확률이 올라감"
        prev = ps
    # 동시 요청: 스레드 4개가 같은 결과를 내고 B.LOG 전역이 그대로여야 함(백엔드가 여러 요청을 한꺼번에 받을 때)
    import threading
    log0, one, got = B.LOG, run(3), []
    ts = [threading.Thread(target=lambda: got.append(run(3))) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert B.LOG == log0, "예측이 B.LOG 전역을 바꿈"
    assert all(g == one for g in got) and len(got) == 4, "동시 요청 결과가 순차와 다름"
    try:
        predict_live(-1)
        raise AssertionError("음수 입력을 받음")
    except ValueError:
        pass
    print("점검 통과")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a in (["export"], ["export-lite"]):
        export(lite=a[0] == "export-lite")
    elif a == ["check"]:
        demo()
    else:  # live N (라이트, API 호출) / now N (전체, 수집 로그)
        mode, n = (a[0], int(a[1])) if len(a) == 2 else ("live", int(a[0]) if a else 0)
        res = {"live": lambda: predict_live(n), "sample": lambda: predict_live(n, log_dir=SAMPLE),
               "latest": lambda: predict_latest(n),  # 수집기 최신 스냅샷(운영 서버, API 호출 없음)
               "now": lambda: predict_now(n, max_age=None)}[mode]()
        if not res:
            print("표시할 버스 없음 (새벽이거나 운행 전)")
        for r in res:
            print(json.dumps(r, ensure_ascii=False, allow_nan=False))
