"""하루 마감 자동 작업 (MLOps). 매일 01:00 KST — 수집기가 쉬는 새벽(막차 00:42 ~ 첫차 05:45)에 돈다.

  ① 데이터 점검  어제 로그: 노선별 스냅샷 수, 07~22시 최대 공백, API 오류 응답 → OK / WARN / FAIL(그날 학습 안 함)
  ② 어제 성적    지금 서비스 중인 모델(models/lite)로 어제를 채점 → reports/daily_metrics.csv 한 줄
                 (처음 보는 날 성적 = 모니터링. 정답은 버스 도착 때 재차라 자동으로 생김)
  ③ 재학습      어제까지 전체 데이터로 후보 모델 → models/versions/YYYYMMDD/ (일요일·공휴일은 건너뜀 — 수업 있는 날만 학습, 토요일 포함)
  ④ 합격 판정    후보의 날짜 분할 성적이 지금 모델보다 10% 넘게 나쁘지 않음 · '여유' 후 실제 탑승 ≥ 97% · 자체 점검 통과
  ⑤ 배포        합격이면 models/lite 교체(이전 모델은 versions/ 에 남음 → 되돌리기 = 폴더 복사)
  ⑥ 정리        원본 로그는 최근 KEEP_RAW 일만 폴더로, 그 전은 tar.gz 로 압축(223MB → 15MB/일, 개수 확인 후 폴더 삭제)
                모델 버전은 최근 KEEP_VERSIONS 개만. 남은 디스크 < MIN_FREE_GB 면 경고
  기록: reports/models.csv (버전별 성적·합격 여부), reports/daily/YYYYMMDD.md (사람이 읽는 요약)

실행: python src/daily.py                    어제 마감
      python src/daily.py 20260929           그 날 마감
      python src/daily.py rollback [버전]     서비스 모델을 이전 버전(기본: 바로 전 버전)으로 되돌림
알림: 매일 요약(이상 있으면 WARN), 실패하면 ERROR — src/notify.py (디스코드 웹훅 설정 시)
"""
import datetime as dt, json, shutil, sys, tarfile, time
import numpy as np, pandas as pd
import build_dataset as B
import collect as C
import notify as N
import serve as S
import train as T

REPORTS = B.ROOT / "reports"
VERS = S.MODELS / "versions"
LIVE = S.MODELS / "lite"
MAX_WORSE = 1.10   # ponytail: 후보 날짜분할 MAE 가 지금 모델의 1.1배를 넘으면 불합격. 데이터 쌓이면 표준편차 기반으로
BUSY = ("07:00:00", "22:00:00")
KEEP_RAW = 3        # 마감한 날 포함 최근 3일은 원본 폴더 그대로(증분 빌드가 앞뒤 하루를 읽음)
KEEP_VERSIONS = 7
MIN_FREE_GB = 5


def header_ok(f):
    try:
        return json.loads(f.read_bytes())["msgHeader"].get("headerCd") == "0"
    except ValueError:  # 잘린 파일
        return False


def check_data(day):
    """(상태, 설명). 로그 폴더를 읽기만 한다."""
    folder = B.LOG / day
    notes, status = [], "OK"
    for route in B.STOPS:
        fs = sorted(folder.glob(f"{route}_arr_*.json"))
        if not fs:
            return "FAIL", f"{route} 스냅샷 0개"
        ts = [dt.datetime.strptime(day + f.stem[-6:], "%Y%m%d%H%M%S") for f in fs]
        busy = [t for t in ts if BUSY[0] <= t.strftime("%H:%M:%S") <= BUSY[1]]
        gap = max(((b - a).total_seconds() for a, b in zip(busy, busy[1:])), default=0) / 60
        bad = sum(not header_ok(f) for f in fs)
        notes.append(f"{route} 스냅샷 {len(fs)}개 · 07~22시 최대 공백 {gap:.1f}분 · 오류 응답 {bad}개")
        if gap > 30 or bad > 0.05 * len(fs):
            status = "FAIL"
        elif (gap > 5 or bad) and status == "OK":
            status = "WARN"
    return status, " / ".join(notes)


def monitor(day, model_dir):
    """지금 모델로 그날을 채점. 서비스와 같은 칸별 '여유' 기준으로 '여유'→실제 탑승을 잰다."""
    m, meta = S.load(True, model_dir)
    d = T.features(cats=meta["cats"])
    d = d[d.date == day]
    if d.empty:
        return None
    d = d.assign(rule=S.lite_rule(d))
    point, Pm = T.predict(m, d)
    board = (d.y.values[:, None] <= T.thresholds(d)).astype(bool)
    th = {(p, s): t for p, s, t, _ in meta["thresholds"]}
    cell = np.array([th[("수업 직전" if pk else "평소", S.seg_name(k))] or 9 for pk, k in zip(d.is_peak == 1, d.stops_away)])
    shown = Pm >= cell[:, None]                                   # 서비스가 '여유'를 띄웠을 칸
    w, err = d.w.values, np.abs(point - d.y.values)
    far, pk = d.stops_away.values >= 3, d.is_peak.values == 1
    wavg = lambda x, msk: float(np.average(x[msk], weights=w[msk])) if msk.any() else np.nan
    base = T.metrics(point, Pm, d)
    return dict(day=day, trips=d.trip.nunique(), mae=base["mae"], brier=base["brier"],
                persistence_mae=wavg(np.abs(d.r_now.values - d.y.values), np.ones(len(d), bool)),
                far_mae=wavg(err, far), peak_mae=wavg(err, pk),
                yeoyu_share=float(shown.mean()), yeoyu_ok=float(board[shown].mean()) if shown.any() else np.nan,
                model=meta["trained_on"][-1])


def cleanup(day):
    """원본 압축·버전 정리·디스크 확인 → 설명 목록. 지우기 전에 압축본을 다시 열어 파일 수를 맞춰 본다."""
    notes, logs = [], B.LOG.resolve()
    arch = logs.parent / "archive"
    arch.mkdir(exist_ok=True)
    cutoff = (dt.datetime.strptime(day, "%Y%m%d") - dt.timedelta(days=KEEP_RAW - 1)).strftime("%Y%m%d")
    for folder in sorted(p for p in logs.glob("2026*") if p.is_dir() and p.name < cutoff):
        metas = [B.OUT / "days" / f"{folder.name}_{r}.json" for r in B.STOPS]
        if not all(m.exists() and "n" in json.loads(m.read_text()) for m in metas):
            notes.append(f"{folder.name} 캐시 없음 → 압축 보류")
            continue
        files = sorted(folder.iterdir())
        tgz = arch / f"{folder.name}.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            for f in files:
                t.add(f, arcname=f"{folder.name}/{f.name}")
        with tarfile.open(tgz) as t:
            ok = len([m for m in t.getmembers() if m.isfile()]) == len(files)
        if ok:
            shutil.rmtree(folder)
            notes.append(f"{folder.name} 압축({tgz.stat().st_size / 1e6:.0f}MB, {len(files)}파일)")
        else:
            tgz.unlink()
            notes.append(f"{folder.name} 압축 확인 실패 → 원본 유지")
    old = sorted(p for p in VERS.glob("2026*") if p.is_dir())[:-KEEP_VERSIONS]
    for v in old:
        shutil.rmtree(v)
    if old:
        notes.append(f"모델 버전 {len(old)}개 삭제(최근 {KEEP_VERSIONS}개 유지)")
    free = shutil.disk_usage(logs).free / 1e9
    notes.append(f"남은 디스크 {free:.1f}GB" + (f" ⚠ {MIN_FREE_GB}GB 미만" if free < MIN_FREE_GB else ""))
    return notes


def append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(path, mode="a", header=not path.exists(), index=False)


def adds_training_data(day):
    """서비스 모델은 수업 있는 날(월~토, 공휴일 제외)만 학습 → 일요일·공휴일 마감은 학습 데이터가 안 늘어 재학습해도 같은 모델(10/3·10/4 실측, 50분 낭비)."""
    return C.day_type(dt.datetime.strptime(day, "%Y%m%d").date()) in ("wkd", "sat")  # 토요일도 정규수업(10-05 지용), 공휴일은 day_type 이 sun


def run(day):
    """반환: (요약 줄들, 경고 목록)"""
    t0, warn = time.time(), []
    lines = [f"# {day} 마감 ({dt.datetime.now(S.KST):%m-%d %H:%M} KST)"]
    status, info = check_data(day)
    lines += [f"① 데이터 {status}: {info}"]
    if status != "OK":
        warn.append(f"데이터 {status}")
    B.main()  # 학습 데이터 다시 만들기(전체 로그) — ponytail: 로그가 몇 달 쌓이면 날짜별 증분으로
    mon = monitor(day, LIVE) if (LIVE / "meta.json").exists() else None
    if mon:
        append(REPORTS / "daily_metrics.csv", mon)
        lines += [f"② 어제 성적(모델 ~{mon['model']}): 오차 {mon['mae']:.2f}명 (지금 재차 그대로 {mon['persistence_mae']:.2f}) · "
                  f"Brier {mon['brier']:.4f} · 3정류장+ {mon['far_mae']:.2f} · 수업 직전 {mon['peak_mae']:.2f} · "
                  f"'여유' {mon['yeoyu_share']:.0%} 표시 → 실제 탑승 {mon['yeoyu_ok']:.1%}"]
        if mon["yeoyu_ok"] < T.TARGET["평소"]:
            warn.append(f"'여유' 후 실제 탑승 {mon['yeoyu_ok']:.1%} < {T.TARGET['평소']:.0%}")
        if mon["mae"] >= mon["persistence_mae"]:
            warn.append(f"모델 오차 {mon['mae']:.2f} ≥ 지금 재차 그대로 {mon['persistence_mae']:.2f}")
    if status == "FAIL":
        lines += ["③ 재학습 안 함 (데이터 FAIL)"]
    elif not adds_training_data(day):
        lines += ["③ 재학습 건너뜀 (일요일·공휴일 — 수업 있는 날만 학습이라 데이터가 안 늘어남, 지금 모델 유지)"]
    else:
        cand = VERS / day
        meta = S.export(lite=True, until=day, out_dir=cand)
        old = json.loads((LIVE / "meta.json").read_text()).get("oof") if (LIVE / "meta.json").exists() else None
        why = []
        if old and meta["oof"]["mae"] > old["mae"] * MAX_WORSE:
            why.append(f"날짜분할 오차 {meta['oof']['mae']:.2f} > 지금 {old['mae']:.2f}×{MAX_WORSE}")
        if not meta["oof"]["hi_ok"] >= T.TARGET["평소"]:
            why.append(f"'여유' 후 탑승 {meta['oof']['hi_ok']:.1%} < {T.TARGET['평소']:.0%}")
        try:
            S.demo(cand)
        except AssertionError as e:
            why.append(f"자체 점검 실패: {e}")
        ok = not why
        if not ok:
            warn.append("새 모델 불합격")
        lines += [f"③ 재학습: {len(meta['trained_on'])}일 · 날짜분할 오차 {meta['oof']['mae']:.2f} (지금 모델 {old['mae']:.2f})" if old
                  else f"③ 재학습: {len(meta['trained_on'])}일 · 날짜분할 오차 {meta['oof']['mae']:.2f} (첫 모델)",
                  "④ 합격 → ⑤ 배포 (models/lite 교체)" if ok else "④ 불합격: " + "; ".join(why) + " → 지금 모델 유지"]
        append(REPORTS / "models.csv", dict(version=day, created=meta["created"], days=len(meta["trained_on"]),
                                            **{f"oof_{k}": v for k, v in meta["oof"].items()}, data=status, promoted=ok))
        if ok:
            if LIVE.exists():
                shutil.rmtree(LIVE)
            shutil.copytree(cand, LIVE)
    notes = cleanup(day)
    warn += [x for x in notes if "⚠" in x or "실패" in x]
    lines += ["⑥ 정리: " + " · ".join(notes), f"소요 {(time.time() - t0) / 60:.0f}분"]
    (REPORTS / "daily").mkdir(parents=True, exist_ok=True)
    (REPORTS / "daily" / f"{day}.md").write_text("\n\n".join(lines) + "\n")
    print("\n".join(lines))
    return lines, warn


def rollback(version=None):
    vs = sorted(p.name for p in VERS.glob("2026*") if p.is_dir())
    now = json.loads((LIVE / "meta.json").read_text())["trained_on"][-1] if (LIVE / "meta.json").exists() else None
    version = version or next((v for v in reversed(vs) if v < (now or "9")), None)
    if version not in vs:
        raise SystemExit(f"버전 없음: {version} (있는 버전: {', '.join(vs)})")
    shutil.rmtree(LIVE, ignore_errors=True)
    shutil.copytree(VERS / version, LIVE)
    N.send(f"서비스 모델을 {version} 버전으로 되돌림 (이전: ~{now})", "WARN")
    print("되돌림:", version)


if __name__ == "__main__":
    if sys.argv[1:2] == ["rollback"]:
        rollback(sys.argv[2] if sys.argv[2:] else None)
        sys.exit()
    day = sys.argv[1] if sys.argv[1:] else (dt.datetime.now(S.KST) - dt.timedelta(days=1)).strftime("%Y%m%d")
    try:
        lines, warn = run(day)
    except Exception as e:
        N.send(f"{day} 마감 실패: {e!r} — journalctl -u hanjari-daily 확인. 서비스 모델은 그대로", "ERROR")
        raise
    N.send(f"{day} 마감" + (" ⚠ " + " / ".join(warn) if warn else " 정상") + "\n" + "\n".join(lines[1:]),
           "WARN" if warn else "INFO")
