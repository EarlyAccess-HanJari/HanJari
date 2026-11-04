"""모델·피처 비교 실험.

평가: 시간순 전진 검증. 날짜가 MIN_DAYS 이상이면 날짜 블록, 아니면 운행(시작 시각순) 블록 FOLDS+2 개로 나눠
      블록 i(2..) 를 그 앞 블록 전부로 학습해 예측 → 지표 평균. 하루짜리는 "점검용".
점 예측(도착 재차 y): persistence / 규칙(지금 재차 + 남은 구간 CSV 평균 순승차) / 부스팅(규칙 잔차 학습).
  - 운행 1회당 가중치 합 1. 바로 앞(k=0)은 숫자 = 지금 재차, 확률 = (정류장, 정차 여부) 조건 실제 변화 분포.
확률 P(탑승) = P(y − 하차 ≤ C − N − 1), N = 0..40 → Brier, '여유'(P≥0.9)·'어려움'(P≤0.3) 표시별 API 기준 계산 탑승률.
  - 규칙: 학습셋 잔차 경험분포. XGB: 다분위수(5~95%) 보간.
피처 묶음을 하나씩 더해 효과(ablation)를 본다.
'여유' 기준은 (시간대 × 거리) 칸별로 API 기준 계산 탑승 ≥ 목표(평소 97%, 수업 직전 피크 98%)를 지키는 가장 낮은 P 를 데이터로 고른다
  (너무 세면 늘 '어려움'만 뜸). 피크 = 버스 도착 후 10~35분 안에 강좌 40개 이상 시작(대면+BL, 10-05 전엔 대면만·20개).
수업 시작 정각(09:00·10:30·12:00·13:30·15:00 …) 직전 몰림: 버스가 정류장에 온 뒤 타고 가서 걷는 시간이 있으므로
  "도착 후 10~35분 사이에 시작하는 강좌 수"(class_board_win)와 다음 큰 수업까지 남은 분(min_to_class)으로 잡는다.
실행: env -u PYTHONPATH /data/VI001/vi004/workspace/miniconda3/envs/dacon/bin/python src/train.py
"""
import os
import numpy as np
import pandas as pd
from pathlib import Path
import xgboost as xgb
import data_quality as DQ
from feature_schema import GROUPS

P = Path(__file__).resolve().parents[1] / "data/processed"
DATASET = P / "dataset.csv"  # sweep.py 가 고정 스냅샷으로 바꿔 씀
MIN_DAYS, FOLDS = 5, 4
CAPACITY = {  # (노선, busType) → 실제 만차 인원(API 기준, 11-04 src/exp_practical_capacity.py). busType 은 일반/저상 구분일 뿐
    # 법정 정원(카운티 마을버스형 승객 20~22)보다 훨씬 끼어 탄다. 혼잡 시간 붐비는 정류장을 떠날 때 인원 상위 1%·더 못 타는 인원으로 정함.
    # 차량별 값은 config/boarding_policy.json 이 우선. 관측 최대로 올리지 않는다(그 방식이 종로03 71명·98% 오표시를 만들었다).
    ("sb02", "0"): 38, ("sb02", "1"): 60,
    ("jr03", "0"): 52, ("jr03", "1"): 54,
}


def cap(route, bt):
    # API 관측 최대는 실제 정원의 근거가 아니므로 사용하지 않는다.
    return CAPACITY.get((route, bt), 33)


def capacity_policy():
    """확률 검증에 쓴 판단 기준. 정원표나 예측 후처리가 바뀌면 이전 검증을 재사용하지 않는다."""
    return {"version": "verified-vehicles-unclipped-v2", "source_schema": DQ.SCHEMA_VERSION, "fallback": 33,
            "calibration": "practical-capacity-surge-v1",
            "values": [[r, b, c] for (r, b), c in sorted(CAPACITY.items())],
            "vehicles": sorted([[v["route"], v["plate"], v["vehicle_id"], v["capacity"]]
                                for v in DQ.boarding_policy()["vehicles"]])}


def row_capacities(d):
    """현장 확인 정원 우선. 미확인 차량의 잠정값은 오프라인 API 대리지표에만 쓴다."""
    verified = verified_capacities(d)
    return np.where(np.isfinite(verified), verified, [cap(r.route, r.bus_type) for r in d.itertuples()])


def verified_capacities(d):
    registry = {(v["route"], v["plate"], v["vehicle_id"]): v["capacity"] for v in DQ.boarding_policy()["vehicles"]}
    return np.array([registry.get((r.route, r.plate, str(getattr(r, "vehicle_id", ""))), np.nan) for r in d.itertuples()])


NS = np.arange(0, 41)
QS = np.round(np.linspace(0.05, 0.95, 9), 3)  # 10-01: 19개 → 9개(정확도 같고 학습 메모리·시간↓, 서버 한 대 1GB 용)
# 스윕 100개(09-23)에서 일관되게 좋았던 설정: 얕은 트리·낮은 학습률·운행 가중·바로 앞 규칙 고정. 실험에서 바꿔 쓰도록 모듈 변수
# 09-30 깊이2→5 (평일 3폴드 MAE 3.25→2.95). 10-01 트리 600·lr 0.03 → 300·0.06 (평일 4폴드 2.844→2.839, 학습 메모리 609→472MB, src/exp_small.py)
XGB_KW = dict(n_estimators=300, max_depth=5, learning_rate=0.06, min_child_weight=5, subsample=0.8, random_state=0,
              n_jobs=min(8, os.cpu_count() or 1))  # 코어 수만큼(오라클 2) — 공유 서버는 8로 제한
PEAK_CLASSES = 40  # 버스 도착 후 10~35분 안에 이만큼 이상 강좌가 시작하면 '수업 직전' (10-05: BL 포함으로 수업 수 ~2배 → 20→40, 피크 칸 비율 8%→6.5%)


CAT_COLS = ["route", "stop", "bus_type", "weekday", "term", "exam", "holiday"]


def features(d=None, cats=None):
    """d: build_dataset 행(없으면 dataset.csv). cats: 범주 → 코드 표(서비스는 학습 때 표를 그대로 써야 코드가 같음)."""
    training = d is None
    if training:
        d = pd.read_csv(DATASET, dtype={"date": str, "stop": str, "bus_type": str, "vehicle_id": str})
    if "source_schema" not in d or not (d.source_schema == DQ.SCHEMA_VERSION).all():
        raise ValueError("이전 검증 규칙의 데이터셋: 원본 로그에서 build_dataset.py 재빌드 필요")
    if "data_status" not in d or not d.data_status.eq("ok").all() or d.r_now.isna().any():
        raise ValueError("검증되지 않은 인원 입력은 학습/예측할 수 없음")
    if not (np.isfinite(d.r_now) & (d.r_now >= 0) & (d.r_now % 1 == 0)).all():
        raise ValueError("인원은 0 이상의 유한 정수여야 함")
    if training and ("y" not in d or d.y.isna().any()):
        raise ValueError("학습 정답이 비어 있음")
    if "y" in d and d.y.notna().any() and not (np.isfinite(d.y) & (d.y >= 0) & (d.y % 1 == 0)).all():
        raise ValueError("잘못된 학습 정답")
    d = d.astype({"date": str, "stop": str, "bus_type": str})
    cal = pd.read_csv(P / "calendar.csv", dtype=str)
    d = d.merge(cal[["date", "weekday", "term", "exam", "holiday"]], on="date", how="left")
    d["holiday"] = d["holiday"].notna() & (d["holiday"] != "")
    d["exam"] = d["exam"].fillna("")
    hh, mm, _ = d["time"].str.split(":", expand=True).astype(int).T.values
    d["minute"] = hh * 60 + mm
    # ponytail: 모든 날짜에 2026-2 시간표 적용. 다른 학기 데이터가 섞이면 yearhakgi 로 맞출 것.
    cs = pd.read_csv(P / "class_starts.csv", dtype=str)
    cs["m"] = cs["start"].str[:2].astype(int) * 60 + cs["start"].str[3:].astype(int)
    cs["n"] = cs["n"].astype(int)
    arrive = (d["minute"] + d["eta"] / 60).values
    # 요일별로 시작 시각순 정렬 + 누적 강좌 수 → [a+lo, a+hi) 강좌 수 = 누적[첫 m ≥ a+hi] − 누적[첫 m ≥ a+lo].
    #   (10-18: 행마다 시간표를 거르던 반복이 하루 마감에서 features() 한 번에 ~30분, 두 번 불려 ~60분 → 몇 초. 값은 같음)
    def win(lo, hi):
        out = np.zeros(len(d), dtype=np.int64)
        for wd, g in cs.sort_values("m", kind="stable").groupby("weekday"):
            at, cum = (d["weekday"] == wd).values, np.r_[0, g.n.cumsum().values]
            out[at] = cum[np.searchsorted(g.m.values, arrive[at] + hi)] - cum[np.searchsorted(g.m.values, arrive[at] + lo)]
        return out
    d["class_board_win"] = win(10, 35)
    for w in (30, 60):
        d[f"class_next{w}"] = win(0, w)
    big = cs[cs.n >= 5].sort_values("m", kind="stable")  # 강좌 5개 이상 시작하는 시각 = 몰리는 정각
    mtc = np.full(len(d), 999.0)
    for wd, g in big.groupby("weekday"):
        at = (d["weekday"] == wd).values
        i = np.searchsorted(g.m.values, arrive[at])  # 첫 m ≥ a (없으면 999)
        mtc[at] = np.where(i < len(g), g.m.values[np.minimum(i, len(g) - 1)] - arrive[at], 999.0)
    d["min_to_class"] = mtc
    cats = cats or {c: sorted(d[c].astype(str).unique()) for c in CAT_COLS}  # astype("category") 와 같은 정렬 → 기존 코드 그대로
    for c in CAT_COLS:
        d[c + "_c"] = pd.Categorical(d[c].astype(str), categories=cats[c]).codes
    d.attrs["cats"] = cats
    d["trip"] = d["date"] + d["route"] + d["stop"] + d["plate"] + d["arrive_time"]
    d["w"] = 1.0 / d.groupby("trip")["trip"].transform("size")
    # 규칙: 지금 재차 + 정차 중 미반영 몫 + 남은 구간 순승차(오늘 실측과 CSV 학기평균의 축소 평균).
    #   CSV 고정은 휴일(9/24 추석)에 persistence 보다 나빠짐 → 오늘 실측이 쌓일수록 CSV 에서 벗어나게.
    d["rule"] = d["r_now"] + d["q_eb"] + d["q_pending"].fillna(0)
    d["is_peak"] = (d["class_board_win"] >= PEAK_CLASSES).astype(int)
    d["cap"] = row_capacities(d)
    d["fill_ratio"] = d["r_now"] / d["cap"]
    return d


def folds(d):
    days = sorted(d["date"].unique())
    if len(days) >= MIN_DAYS:
        key, blocks = d["date"], np.array_split(np.array(days), FOLDS + 2)
        note = f"날짜 블록 전진 검증 ({len(days)}일)"
    else:
        start = (d["date"] + " " + d["time"]).groupby(d["trip"]).min().sort_values()
        key, blocks = d["trip"], np.array_split(start.index.values, FOLDS + 2)
        note = f"⚠ 점검용(날짜 {len(days)}일): 운행 시간순 블록 전진 검증 — 성능 수치로 인용 금지"
    print(note)
    for i in range(2, FOLDS + 2):
        if len(blocks[i]):  # 날짜가 FOLDS+2 보다 적으면 빈 블록이 생김(5일 → 6조각) — 건너뜀
            yield d[key.isin(np.concatenate(blocks[:i]))], d[key.isin(blocks[i])]


def thresholds(df):
    C = row_capacities(df)[:, None]
    return C - NS[None, :] - 1 + df["off_csv"].values[:, None]


def empirical_p(res, center, thr):
    res = np.sort(res)
    return np.stack([np.searchsorted(res, t - c, side="right") / len(res) for c, t in zip(center, thr)])


def quantile_p(Q, thr, QS=QS):
    Q = np.sort(Q, axis=1)
    lo, hi = QS[0] / 2, 1 - (1 - QS[-1]) / 2
    return np.stack([np.interp(t, q, QS, left=lo, right=hi) for q, t in zip(Q, thr)])


def metrics(point, Pm, te):
    y, w = te["y"].values, te["w"].values
    board = (y[:, None] <= thresholds(te)).astype(float)
    W = np.repeat(w[:, None], len(NS), axis=1)
    hi, lo = Pm >= 0.9, Pm <= 0.3
    return dict(mae=np.sum(w * np.abs(point - y)) / np.sum(w),
                brier=np.sum(W * (Pm - board) ** 2) / np.sum(W),
                hi_share=hi.mean(), hi_ok=board[hi].mean() if hi.any() else np.nan,
                lo_ok=board[lo].mean() if lo.any() else np.nan)


F0 = ["pos_dwell", "pos_frac", "q_pending", "r_now", "stop_c", "route_c", "minute"]


def fit(tr, feats):
    """규칙 잔차를 XGB(점: MAE, 확률: 다분위수)로 학습. 바로 앞(k=0)은 전용 모델."""
    Xtr, dtr, kw = tr[feats].astype(float), tr.y.values - tr.rule.values, dict(XGB_KW)
    m = dict(feats=feats, qs=QS,
             pt=xgb.XGBRegressor(objective="reg:absoluteerror", **kw).fit(Xtr, dtr, sample_weight=tr.w),
             qm=xgb.XGBRegressor(objective="reg:quantileerror", quantile_alpha=QS, **kw).fit(Xtr, dtr, sample_weight=tr.w),
             m0=None)
    # 바로 앞(k=0): 앞 정류장(s−1)에 정차 중일 때만 그 정류장 승하차가 미반영이고, 구간 진행률(pos_frac)에 따라
    #   변화가 크게 다름(09-24 실측: frac 0.3~0.6 이면 평균 +3.9, 0.6+ 면 −2.3). → k=0 전용 얕은 중앙값 모델,
    #   확률은 그 모델 잔차의 (정차 여부) 조건 경험분포. 달리는 중이면 모델도 거의 0 을 냄(오차 0.12).
    tk = tr[tr.stops_away == 0]
    if len(tk) >= 50:
        m["m0"] = xgb.XGBRegressor(objective="reg:absoluteerror", **kw).fit(tk[F0].astype(float), tk.y - tk.r_now, sample_weight=tk.w)
        res0 = tk.y.values - tk.r_now.values - m["m0"].predict(tk[F0].astype(float))
        dwell = (tk.pos_dwell == 1).values
        m["res0"] = {dw: np.sort(res0[dwell == dw] if (dwell == dw).sum() >= 20 else res0) for dw in (True, False)}
    m["gain_q"] = gain_table(tr)
    return m


GAIN_Q = np.linspace(0, 1, 41)


def gain_slot(d):
    return ((d.minute.values + np.nan_to_num(d.eta.values.astype(float)) / 60) // 30).astype(int)


def gain_table(tr):
    """1~2정류장 전 조회에서 도착까지 실제로 늘어난 인원(y − 지금 재차)의 분위수 — (노선, 정류장, 거리, 30분 칸)별.
    11-04: 몰림 시간(2번출구 08:45 등)엔 한 정류장에서 +30명도 생겨 모델 분위수가 과신했다(15명+ 몰림의 55%가 90% 위쪽 초과).
    예측 확률을 이 경험 분포로 계산한 값 이하로 낮춘다 → 몰림 시간 '여유' 오류 5.4%→3.6%, 평균 P 0.95→0.92(실제 0.92)."""
    x = tr[tr.stops_away.between(1, 2) & tr.y.notna() & tr.r_now.notna()]
    gain = (x.y - x.r_now).values
    out = {}
    for key, idx in pd.Series(range(len(x))).groupby([x.route.values, x.stop.values, x.stops_away.values.astype(int), gain_slot(x)]).groups.items():
        if len(idx) >= 30:
            out["|".join(map(str, key))] = np.quantile(gain[idx], GAIN_Q).tolist()
    return out


def predict(m, te, quantiles=False):
    """(점 예측, P(탑승) 행렬 [행 × N=0..40]). quantiles=True 면 도착재차 분위수(QS)도."""
    Xte = te[m["feats"]].astype(float)
    # 예측 대상은 API 재차. 잠정 정원으로 자르면 초과값을 숨기고 확률·구간 폭을 왜곡한다.
    point = np.maximum(te.rule.values + m["pt"].predict(Xte), 0)
    Q = np.sort(np.maximum(m["qm"].predict(Xte) + te.rule.values[:, None], 0), axis=1)
    thr = thresholds(te)
    qs = m.get("qs", QS)  # 모델마다 분위수 개수가 다를 수 있음(19 → 9, 10-01) — 모델에 저장된 값으로
    Pm = quantile_p(Q, thr, qs)
    gq = m.get("gain_q") or {}
    if gq:  # 1~2정류장 전: 과거 같은 칸의 실제 증가 분포로 낸 확률보다 높게 말하지 않는다(몰림 과신 방지)
        for i, key in enumerate(zip(te.route.values, te.stop.values, te.stops_away.values, gain_slot(te))):
            q = gq.get(f"{key[0]}|{key[1]}|{int(key[2])}|{key[3]}") if 1 <= key[2] <= 2 else None
            if q is not None and np.isfinite(te.r_now.values[i]):
                Pm[i] = np.minimum(Pm[i], np.interp(thr[i] - te.r_now.values[i], q, GAIN_Q, left=0, right=1))
    k0 = te.stops_away.values == 0
    if k0.any() and m["m0"] is not None:
        te0 = te[k0]
        point[k0] = np.maximum(te0.r_now.values + m["m0"].predict(te0[F0].astype(float)), 0)
        for dw in (True, False):
            me = k0 & ((te.pos_dwell.values == 1) == dw)
            if me.any():
                Pm[me] = empirical_p(m["res0"][dw], point[me], thr[me])
                Q[me] = np.maximum(point[me, None] + np.quantile(m["res0"][dw], qs)[None, :], 0)
    return (point, Pm, Q) if quantiles else (point, Pm)


def run(tr, te, feats):
    return predict(fit(tr, feats), te)


SEGS = {"바로 앞": (0, 0), "1~2정류장 전": (1, 2), "3정류장+ 전": (3, 99)}
TARGET = {"평소": 0.97, "수업 직전": 0.98}  # '여유' 표시 → API 기준 계산 탑승률 목표. 수업 직전 피크는 더 엄격


def pick_thresholds(Pm, B, K, peak):
    """(시간대 × 거리) 칸마다 '여유' 정확도 ≥ 목표를 지키면서 표시가 가장 많이 뜨는(가장 낮은) 기준.
    칸의 표시 건수가 30 미만이면 기준을 못 정함(데이터 부족)."""
    out = {}
    for pname, pm in (("평소", ~peak), ("수업 직전", peak)):
      for name, (a, b) in SEGS.items():
        m = (K >= a) & (K <= b) & pm
        tgt = TARGET[pname]
        if m.sum() < 30:
            out[(pname, name)] = ("부족", 0.0, np.nan)
            continue
        ok = [th for th in np.arange(0.80, 0.995, 0.01)
              if ((Pm >= th) & m).sum() >= 30 and B[(Pm >= th) & m].mean() >= tgt]
        th = min(ok) if ok else None
        out[(pname, name)] = (th, ((Pm >= th) & m).sum() / m.sum() if th else 0.0, B[(Pm >= th) & m].mean() if th else np.nan)
    return out


def main():
    d = features()
    rows, keep = [], []
    for tr, te in folds(d):
        rule_res = tr.y.values - tr.rule.values
        rows.append(("persistence", metrics(te.r_now.values, (te.r_now.values[:, None] <= thresholds(te)).astype(float), te)))
        rows.append(("규칙 + 잔차분포", metrics(te.rule.values, empirical_p(rule_res, te.rule.values, thresholds(te)), te)))
        feats = []
        for g, cols in GROUPS.items():
            feats = feats + cols
            point, Pm = run(tr, te, feats)
            rows.append((f"XGB {g}", metrics(point, Pm, te)))
        keep.append((Pm, (te.y.values[:, None] <= thresholds(te)).astype(float),
                     np.repeat(te.stops_away.values[:, None], len(NS), 1),
                     np.repeat((te.class_board_win.values >= PEAK_CLASSES)[:, None], len(NS), 1)))  # 전체 피처 모델
    r = pd.DataFrame([dict(model=m, **v) for m, v in rows]).groupby("model", sort=False).mean()
    r.columns = ["MAE", "Brier", "'여유' 비율", "'여유'→탑승", "'어려움'→탑승"]
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 140):
        print(r)
    Pm, B, K, PK = (np.concatenate(x) for x in zip(*keep))
    print(f"\n'여유' 기준 (목표 API 기준 계산 탑승: " + ", ".join(f"{k} ≥ {v:.0%}" for k, v in TARGET.items()) + ", 그중 가장 많이 뜨는 기준)")
    for (pname, name), (th, share, ok) in pick_thresholds(Pm, B, K, PK).items():
        msg = ("데이터 부족 → 기준 미정" if th == "부족" else
               f"P ≥ {th:.2f} → '여유' {share:5.1%} 표시, API 기준 계산 탑승 {ok:5.1%}" if th else "목표 달성 불가 → '여유' 표시 안 함")
        print(f"  {pname:6} {name:10} {msg}")


if __name__ == "__main__":
    main()
