"""무작위 설정 N 개 실험 + 봉인 블록 재채점.

선택: 전진 검증 앞 3개 fold 평균 Brier(점 MAE 보조)로 순위.
봉인: 마지막 fold(가장 늦은 블록)는 선택에 쓰지 않고, 상위 TOP 개와 기준선만 한 번 채점 → 선택 점수와의 차이 = 운의 몫.
데이터는 실행 시점 dataset.csv 를 data/processed/sweep_snapshot.csv 로 고정해 씀.
실행: env -u PYTHONPATH /data/VI001/vi004/workspace/miniconda3/envs/dacon/bin/python src/sweep.py [N]
"""
import sys, shutil, time
import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostRegressor
import train as T

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
TOP = 5
rng = np.random.default_rng(0)
G = list(T.GROUPS)
SUBSETS = [G[:i] for i in range(1, len(G) + 1)] + [[g for g in G if g != x] for x in G[1:]]  # 누적 + 하나씩 빼기
BASES = {"지금 재차": lambda d: d.r_now.values, "규칙(CSV)": lambda d: d.rule.values,
         "규칙(오늘 실측)": lambda d: (d.r_now + d.q_today).values}


def sample():
    return dict(model=rng.choice(["xgb", "lgb", "cat"]), subset=int(rng.integers(len(SUBSETS))),
                base=str(rng.choice(list(BASES))), depth=int(rng.integers(2, 7)), n=int(rng.choice([100, 200, 300, 500])),
                lr=float(rng.choice([0.02, 0.05, 0.1])), mcw=int(rng.choice([1, 5, 10, 20])),
                sub=float(rng.choice([0.7, 0.8, 1.0])), weight=str(rng.choice(["운행", "균등"])), k0=bool(rng.integers(2)))


def fit_point(cfg, X, y, w):
    if cfg["model"] == "xgb":
        m = xgb.XGBRegressor(n_estimators=cfg["n"], max_depth=cfg["depth"], learning_rate=cfg["lr"], min_child_weight=cfg["mcw"],
                             subsample=cfg["sub"], objective="reg:absoluteerror", random_state=0, n_jobs=8)
    elif cfg["model"] == "lgb":
        m = lgb.LGBMRegressor(n_estimators=cfg["n"], max_depth=cfg["depth"], learning_rate=cfg["lr"], min_child_samples=cfg["mcw"],
                              subsample=cfg["sub"], subsample_freq=1, objective="l1", random_state=0, n_jobs=8, verbose=-1)
    else:
        m = CatBoostRegressor(iterations=cfg["n"], depth=cfg["depth"], learning_rate=cfg["lr"], loss_function="MAE",
                              random_seed=0, thread_count=8, verbose=0)
    return m.fit(X, y, sample_weight=w)


def run(cfg, tr, te):
    feats = sum((T.GROUPS[g] for g in SUBSETS[cfg["subset"]]), [])
    Xtr, Xte = tr[feats].astype(float), te[feats].astype(float)
    b = BASES[cfg["base"]]
    btr, bte = b(tr), b(te)
    w = tr.w.values if cfg["weight"] == "운행" else None
    point = bte + fit_point(cfg, Xtr, tr.y.values - btr, w).predict(Xte)
    # 확률: 점 예측 + 학습셋 OOF 대신 학습셋 잔차(k 구간별) 경험분포  # ponytail: 학습셋 잔차는 낙관적. 데이터 늘면 OOF 잔차로
    ptr = btr + fit_point(cfg, Xtr, tr.y.values - btr, w).predict(Xtr)
    thr = T.thresholds(te)
    Pm = np.zeros_like(thr)
    for a, c in [(0, 0), (1, 2), (3, 99)]:
        mt, me = (tr.stops_away >= a) & (tr.stops_away <= c), (te.stops_away.values >= a) & (te.stops_away.values <= c)
        if me.any():
            res = (tr.y.values - ptr)[mt.values] if mt.any() else tr.y.values - ptr
            Pm[me] = T.empirical_p(res, point[me], thr[me])
    if cfg["k0"]:
        k0 = te.stops_away.values == 0
        tk = tr[tr.stops_away == 0]
        if k0.any() and len(tk):
            point[k0] = te.rule.values[k0]
            Pm[k0] = T.empirical_p(tk.y.values - tk.rule.values, te.rule.values[k0], thr[k0])
    return T.metrics(point, Pm, te)


def set_cap(tr):
    T.CAP_OBS.clear()
    T.CAP_OBS.update(pd.concat([tr.y, tr.r_now]).groupby(pd.concat([tr.route + "|" + tr.bus_type] * 2)).max()
                     .rename(lambda k: tuple(k.split("|"))).to_dict())


def main():
    snap = T.P / "sweep_snapshot.csv"
    shutil.copy(T.P / "dataset.csv", snap)
    T.DATASET = snap
    d = T.features()
    fs = list(T.folds(d))
    sel, sealed = fs[:-1], fs[-1]
    print(f"데이터 {len(d)}행 {d.trip.nunique()}운행 | 선택용 fold {len(sel)}개, 봉인 fold 1개 (평가 {sealed[1].trip.nunique()}운행)")
    t0, res = time.time(), []
    for i in range(N):
        cfg = sample()
        ms = []
        for tr, te in sel:
            set_cap(tr)
            ms.append(run(cfg, tr, te))
        res.append(dict(id=i, **cfg, subset_name=" / ".join(SUBSETS[cfg["subset"]]),
                        mae=np.mean([m["mae"] for m in ms]), brier=np.mean([m["brier"] for m in ms]),
                        hi_ok=np.nanmean([m["hi_ok"] for m in ms]), hi_share=np.mean([m["hi_share"] for m in ms])))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{N} ({time.time() - t0:.0f}s) 현재 최고 Brier {min(r['brier'] for r in res):.4f}", flush=True)
    r = pd.DataFrame(res).sort_values("brier")
    r.to_csv(T.P / "sweep_results.csv", index=False)

    # 기준선(선택 fold)
    base = {}
    for name, f in [("persistence", lambda tr, te: T.metrics(te.r_now.values, (te.r_now.values[:, None] <= T.thresholds(te)).astype(float), te)),
                    ("규칙+잔차", lambda tr, te: T.metrics(te.rule.values, T.empirical_p(tr.y.values - tr.rule.values, te.rule.values, T.thresholds(te)), te))]:
        ms = []
        for tr, te in sel:
            set_cap(tr)
            ms.append(f(tr, te))
        tr, te = sealed
        set_cap(tr)
        base[name] = (np.mean([m["brier"] for m in ms]), np.mean([m["mae"] for m in ms]), f(tr, te))

    print("\n=== 선택 점수 상위 / 하위 ===")
    cols = ["id", "model", "base", "subset_name", "depth", "n", "lr", "weight", "k0", "mae", "brier", "hi_ok"]
    with pd.option_context("display.width", 200, "display.max_colwidth", 40, "display.float_format", "{:.4f}".format):
        print(r[cols].head(10).to_string(index=False))
        print("...")
        print(r[cols].tail(3).to_string(index=False))
        print("\n모델별 최고/중앙 Brier:")
        print(r.groupby("model").brier.agg(["min", "median"]).to_string())
        print("\n출발점별 최고/중앙 Brier:")
        print(r.groupby("base").brier.agg(["min", "median"]).to_string())

    print("\n=== 봉인 블록 재채점 (선택에 안 쓴 가장 늦은 운행들) ===")
    print(f"{'':28} {'선택 Brier':>10} {'봉인 Brier':>10} {'선택 MAE':>9} {'봉인 MAE':>9} {'봉인 여유→탑승':>12}")
    for name, (sb, smae, m) in base.items():
        print(f"{name:28} {sb:10.4f} {m['brier']:10.4f} {smae:9.3f} {m['mae']:9.3f} {m['hi_ok']:12.1%}")
    tr, te = sealed
    set_cap(tr)
    for _, row in r.head(TOP).iterrows():
        cfg = {k: row[k] for k in ["model", "subset", "base", "depth", "n", "lr", "mcw", "sub", "weight", "k0"]}
        cfg.update(subset=int(cfg["subset"]), depth=int(cfg["depth"]), n=int(cfg["n"]), mcw=int(cfg["mcw"]), k0=bool(cfg["k0"]))
        m = run(cfg, tr, te)
        print(f"#{int(row.id):<3}{row.model:4}{row.base:10}{'':11} {row.brier:10.4f} {m['brier']:10.4f} {row.mae:9.3f} {m['mae']:9.3f} {m['hi_ok']:12.1%}")


if __name__ == "__main__":
    main()
