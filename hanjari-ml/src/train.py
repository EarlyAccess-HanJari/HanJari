"""모델·피처 비교 실험.

평가: 시간순 전진 검증. 날짜가 MIN_DAYS 이상이면 날짜 블록, 아니면 운행(시작 시각순) 블록 FOLDS+2 개로 나눠
      블록 i(2..) 를 그 앞 블록 전부로 학습해 예측 → 지표 평균. 하루짜리는 "점검용".
점 예측(도착 재차 y): persistence / 규칙(지금 재차 + 남은 구간 CSV 평균 순승차) / 부스팅(규칙 잔차 학습).
  - 운행 1회당 가중치 합 1. 바로 앞(k=0)은 숫자 = 지금 재차, 확률 = (정류장, 정차 여부) 조건 실제 변화 분포.
확률 P(탑승) = P(y − 하차 ≤ C − N − 1), N = 0..40 → Brier, '여유'(P≥0.9)·'어려움'(P≤0.3) 표시별 실제 탑승률.
  - 규칙: 학습셋 잔차 경험분포. XGB: 다분위수(5~95%) 보간.
피처 묶음을 하나씩 더해 효과(ablation)를 본다.
'여유' 기준은 (시간대 × 거리) 칸별로 실제 탑승 ≥ 목표(평소 97%, 수업 직전 피크 98%)를 지키는 가장 낮은 P 를 데이터로 고른다
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

P = Path(__file__).resolve().parents[1] / "data/processed"
DATASET = P / "dataset.csv"  # sweep.py 가 고정 스냅샷으로 바꿔 씀
MIN_DAYS, FOLDS = 5, 4
CAPACITY = {  # (노선, busType) → 잠정 정원 (docs/DESIGN.md 2절)
    ("sb02", "0"): 33, ("sb02", "1"): 55,
    # 종로03은 busType 0 도 9/23 재차 48명 관측 → 성북02 소형차와 다른 차종. 관측 최대 이상으로 잠정 55, 차종 확인 필요
    ("jr03", "0"): 55, ("jr03", "1"): 55,
}
CAP_OBS = {}  # (노선, busType) → 학습 구간에서 관측된 최대 재차. 정원 = max(잠정값, 관측 최대). 만차 신호는 9/23 기준 한 번도 안 켜짐


def cap(route, bt):
    return max(CAPACITY.get((route, bt), 33), CAP_OBS.get((route, bt), 0))
NS = np.arange(0, 41)
QS = np.round(np.linspace(0.05, 0.95, 9), 3)  # 10-01: 19개 → 9개(정확도 같고 학습 메모리·시간↓, 서버 한 대 1GB 용)
# 스윕 100개(09-23)에서 일관되게 좋았던 설정: 얕은 트리·낮은 학습률·운행 가중·바로 앞 규칙 고정. 실험에서 바꿔 쓰도록 모듈 변수
# 09-30 깊이2→5 (평일 3폴드 MAE 3.25→2.95). 10-01 트리 600·lr 0.03 → 300·0.06 (평일 4폴드 2.844→2.839, 학습 메모리 609→472MB, src/exp_small.py)
XGB_KW = dict(n_estimators=300, max_depth=5, learning_rate=0.06, min_child_weight=5, subsample=0.8, random_state=0,
              n_jobs=min(8, os.cpu_count() or 1))  # 코어 수만큼(오라클 2) — 공유 서버는 8로 제한
PEAK_CLASSES = 40  # 버스 도착 후 10~35분 안에 이만큼 이상 강좌가 시작하면 '수업 직전' (10-05: BL 포함으로 수업 수 ~2배 → 20→40, 피크 칸 비율 8%→6.5%)
GROUPS = {  # 누적해서 더함
    "기본(위치·재차·시각)": ["eta", "stops_away", "r_now", "q_csv", "off_csv", "minute", "route_c", "stop_c", "bus_type_c"],
    "+배차·몰림": ["since_prev", "hw_ratio", "eta_gap", "eta2", "r2"],
    "+오늘 혼잡": ["route_load", "q_bias3", "q_prev"],
    "+수업 시작": ["class_board_win", "class_next30", "class_next60", "min_to_class"],
    "+달력": ["weekday_c", "term_c", "exam_c", "holiday_c"],
    "+정원·피크": ["is_peak", "cap", "fill_ratio"],  # 실패 분석에서 나온 것: 피크에 몰림, 정원 근처 포화
    "+앞 정류장 줄(실측)": ["q_today", "q_eb", "q_hist"],
    "+위치(정차·진행)": ["pos_dwell", "pos_frac", "q_pending"],  # 재차는 정류장 출발 때 갱신 → 정차 중이면 그 정류장 몫 미반영
    "+정밀 순승차(위치 기반)": ["q_live2", "q_today2"],
    "+쌓임속도×공백": ["q_rate", "gap_sum"],  # 구조 모델: 사람은 시간에 비례해 쌓이고 버스가 오면 비워짐  # 위치 API 출발 시각 기준 정류장별 순승차(직전 버스·최근 60분)
}


CAT_COLS = ["route", "stop", "bus_type", "weekday", "term", "exam", "holiday"]


def features(d=None, cats=None):
    """d: build_dataset 행(없으면 dataset.csv). cats: 범주 → 코드 표(서비스는 학습 때 표를 그대로 써야 코드가 같음)."""
    if d is None:
        d = pd.read_csv(DATASET, dtype={"date": str, "stop": str, "bus_type": str})
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
    d["r_now"] = d["r_now"].fillna(0)
    # 규칙: 지금 재차 + 정차 중 미반영 몫 + 남은 구간 순승차(오늘 실측과 CSV 학기평균의 축소 평균).
    #   CSV 고정은 휴일(9/24 추석)에 persistence 보다 나빠짐 → 오늘 실측이 쌓일수록 CSV 에서 벗어나게.
    d["rule"] = d["r_now"] + d["q_eb"] + d["q_pending"].fillna(0)
    d["is_peak"] = (d["class_board_win"] >= PEAK_CLASSES).astype(int)
    d["cap"] = [CAPACITY.get((r, b), 33) for r, b in zip(d["route"], d["bus_type"])]  # 피처는 잠정값(관측 최대는 fold 마다 달라 thresholds 에서만)
    d["fill_ratio"] = d["r_now"] / d["cap"]
    return d


def folds(d):
    days = sorted(d["date"].unique())
    if len(days) >= MIN_DAYS:
        key, blocks = d["date"], np.array_split(np.array(days), FOLDS + 2)
        note = f"날짜 블록 전진 검증 ({len(days)}일)"
    else:
        start = d.groupby("trip")["time"].min().sort_values()
        key, blocks = d["trip"], np.array_split(start.index.values, FOLDS + 2)
        note = f"⚠ 점검용(날짜 {len(days)}일): 운행 시간순 블록 전진 검증 — 성능 수치로 인용 금지"
    print(note)
    for i in range(2, FOLDS + 2):
        if len(blocks[i]):  # 날짜가 FOLDS+2 보다 적으면 빈 블록이 생김(5일 → 6조각) — 건너뜀
            yield d[key.isin(np.concatenate(blocks[:i]))], d[key.isin(blocks[i])]


def thresholds(df):
    C = np.array([cap(r, b) for r, b in zip(df["route"], df["bus_type"])])[:, None]
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
    return m


def predict(m, te, quantiles=False):
    """(점 예측, P(탑승) 행렬 [행 × N=0..40]). quantiles=True 면 도착재차 분위수(QS)도."""
    Xte = te[m["feats"]].astype(float)
    # 재차는 0 이상·정원 이하 (정원 = max(잠정, 관측 최대)) — 붐빌 때 정원을 넘는 과대예측을 자름
    cap_te = np.array([cap(r, b) for r, b in zip(te["route"], te["bus_type"])])
    point = np.clip(te.rule.values + m["pt"].predict(Xte), 0, cap_te)
    Q = np.sort(np.clip(m["qm"].predict(Xte) + te.rule.values[:, None], 0, cap_te[:, None]), axis=1)
    thr = thresholds(te)
    qs = m.get("qs", QS)  # 모델마다 분위수 개수가 다를 수 있음(19 → 9, 10-01) — 모델에 저장된 값으로
    Pm = quantile_p(Q, thr, qs)
    k0 = te.stops_away.values == 0
    if k0.any() and m["m0"] is not None:
        te0 = te[k0]
        point[k0] = np.clip(te0.r_now.values + m["m0"].predict(te0[F0].astype(float)), 0, cap_te[k0])
        for dw in (True, False):
            me = k0 & ((te.pos_dwell.values == 1) == dw)
            if me.any():
                Pm[me] = empirical_p(m["res0"][dw], point[me], thr[me])
                Q[me] = np.clip(point[me, None] + np.quantile(m["res0"][dw], qs)[None, :], 0, cap_te[me, None])
    return (point, Pm, Q) if quantiles else (point, Pm)


def run(tr, te, feats):
    return predict(fit(tr, feats), te)


SEGS = {"바로 앞": (0, 0), "1~2정류장 전": (1, 2), "3정류장+ 전": (3, 99)}
TARGET = {"평소": 0.97, "수업 직전": 0.98}  # '여유' 표시 → 실제 탑승률 목표. 수업 직전 피크는 더 엄격


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
        CAP_OBS.clear()
        CAP_OBS.update(pd.concat([tr.y, tr.r_now]).groupby(pd.concat([tr.route + "|" + tr.bus_type] * 2)).max()
                       .rename(lambda k: tuple(k.split("|"))).to_dict())
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
    print(f"\n'여유' 기준 (목표 실제 탑승: " + ", ".join(f"{k} ≥ {v:.0%}" for k, v in TARGET.items()) + ", 그중 가장 많이 뜨는 기준)")
    for (pname, name), (th, share, ok) in pick_thresholds(Pm, B, K, PK).items():
        msg = ("데이터 부족 → 기준 미정" if th == "부족" else
               f"P ≥ {th:.2f} → '여유' {share:5.1%} 표시, 실제 탑승 {ok:5.1%}" if th else "목표 달성 불가 → '여유' 표시 안 함")
        print(f"  {pname:6} {name:10} {msg}")


if __name__ == "__main__":
    main()
