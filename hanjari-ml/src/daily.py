"""하루 마감 자동 작업 (MLOps). 매일 01:00 KST — 수집기가 쉬는 새벽(막차 00:42 ~ 첫차 05:45)에 돈다.

  ① 데이터 점검  어제 로그: 노선별 스냅샷 수, 07~22시 최대 공백, API 오류 응답 → OK / WARN / FAIL(그날 학습 안 함)
  ② API 재생 평가 models/lite로 그날 API 집계를 재계산 → reports/daily_metrics.csv 한 줄 (현장 검증 별도)
                 (처음 보는 날 성적 = 모니터링. 정답은 버스 도착 때 재차라 자동으로 생김)
  ③ 재학습      어제까지 전체 데이터로 후보 모델 → models/versions/YYYYMMDD/ (일요일·공휴일은 건너뜀 — 수업 있는 날만 학습, 토요일 포함)
  ④ 합격 판정    후보의 날짜 분할 성적이 지금 모델보다 10% 넘게 나쁘지 않음 · '여유' 후 API 기준 계산 탑승 ≥ 97% · 자체 점검 통과
  ⑤ 배포        합격이면 models/lite 교체(이전 모델은 versions/ 에 남음 → 되돌리기 = 폴더 복사)
  ⑥ 정리        원본 로그는 최근 KEEP_RAW 일만 폴더로, 그 전은 tar.gz 로 압축(223MB → 15MB/일, 개수 확인 후 폴더 삭제)
                모델 버전은 최근 KEEP_VERSIONS 개만. 남은 디스크 < MIN_FREE_GB 면 경고
  기록: reports/models.csv (버전별 성적·합격 여부), reports/daily/YYYYMMDD.md (사람이 읽는 요약)

실행: python src/daily.py                    어제 마감
      python src/daily.py 20260929           그 날 마감
      python src/daily.py rollback [버전]     서비스 모델을 이전 버전(기본: 바로 전 버전)으로 되돌림
알림: 매일 요약(이상 있으면 WARN), 실패하면 ERROR — src/notify.py (디스코드 웹훅 설정 시)
"""
import csv, datetime as dt, hashlib, json, shutil, subprocess, sys, tarfile, time
import numpy as np, pandas as pd
import build_dataset as B
import collect as C
import notify as N
import serve as S
import train as T
from api_response import response_items
from date_paths import day_folders, valid_day

REPORTS = B.ROOT / "reports"
VERS = S.MODELS / "versions"
LIVE = S.MODELS / "lite"
MAX_WORSE = 1.10   # ponytail: 후보 날짜분할 MAE 가 지금 모델의 1.1배를 넘으면 불합격. 데이터 쌓이면 표준편차 기반으로
BUSY = ("07:00:00", "22:00:00")
KEEP_RAW = 3        # 마감한 날 포함 최근 3일은 원본 폴더 그대로(증분 빌드가 앞뒤 하루를 읽음)
KEEP_VERSIONS = 7
MIN_FREE_GB = 5
SIZE_WARN_GB = {"archive": 10, "processed": 5, "models": 2, "reports": 1}
MODEL_FILES = ("meta.json", "point.json", "quantile.json", "k0.json")


class ActivationError(RuntimeError):
    pass


def folder_size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def model_meta(path):
    if not all((path / name).is_file() for name in MODEL_FILES):
        raise ValueError('필수 모델 파일 없음')
    meta = json.loads((path / 'meta.json').read_text())
    if not isinstance(meta, dict) or not isinstance(meta.get('created'), str) or not meta['created']:
        raise ValueError('모델 created 없음')
    return meta


def fingerprint(path):
    hashes = {}
    for file in path.rglob('*'):
        if file.is_file():
            with file.open('rb') as stream:
                hashes[str(file.relative_to(path))] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return hashes


def live_message(before=None):
    try:
        model_meta(LIVE)
        if before is not None and fingerprint(LIVE) == before:
            return '기존 모델 유지'
        return '현재 모델 파일 존재, 활성 버전 확인 필요'
    except (OSError, ValueError, TypeError):
        return '서비스 모델 복구 실패, 즉시 확인'


def notify(message, level):
    try:
        N.send(message, level)
    except Exception as exc:
        print(f'알림 전송/기록 실패: {type(exc).__name__}', file=sys.stderr)


def activate_model(src, version):
    """Validate a complete copy before touching the shared real lite directory."""
    root = LIVE.parent.resolve()
    staging, previous = LIVE.parent / '.lite-staging', LIVE.parent / '.lite-previous'
    before = fingerprint(LIVE) if LIVE.is_dir() else None
    try:
        # Never follow a leftover child symlink while removing or renaming models.
        for path in (LIVE, staging, previous):
            if path.is_symlink() or path.resolve().parent != root:
                raise ValueError('모델 교체 경로 확인 필요')
        if staging.exists():
            shutil.rmtree(staging)
        if shutil.disk_usage(root).free < 2 * folder_size(src):
            raise OSError('모델 크기의 2배 미만 여유 디스크')
        shutil.copytree(src, staging)
        model_meta(staging)
        if fingerprint(src) != fingerprint(staging):
            raise ValueError('모델 SHA-256 불일치')
        if previous.exists():
            shutil.rmtree(previous)
        if LIVE.exists():
            LIVE.rename(previous)
        try:
            staging.rename(LIVE)
        except OSError:
            if previous.exists():
                previous.rename(LIVE)
            raise
    except (OSError, ValueError, TypeError) as exc:
        raise ActivationError(f'{version} 전환 실패: {exc} · {live_message(before)}') from exc
    return version


def mark_restart(version):
    REPORTS.mkdir(parents=True, exist_ok=True)
    C.write_snapshot(REPORTS / 'restart_required', str(version).encode())


def promoted_versions():
    try:
        with (REPORTS / 'models.csv').open(newline='') as stream:
            latest = {row['version']: row.get('promoted', '').lower() == 'true' for row in csv.DictReader(stream)}
    except FileNotFoundError:
        return []
    return sorted(v for v, ok in latest.items() if ok and valid_day(v) and (VERS / v).is_dir())


def header_ok(f):
    try:
        response_items(json.loads(f.read_bytes()))
        return True
    except (OSError, ValueError):
        return False


def check_data(day):
    """(상태, 설명). 로그 폴더를 읽기만 한다."""
    folder = B.LOG / day
    notes, status = [], "OK"
    base = dt.datetime.strptime(day, "%Y%m%d")
    sched = C.load_sched()
    busy_start, busy_end = (t.hour*60 + t.minute for t in map(dt.time.fromisoformat, BUSY))
    for route in B.STOPS:
        fs = sorted(folder.glob(f"{route}_arr_*.json"))
        if not fs:
            return "FAIL", f"{route} 스냅샷 0개"
        ts = [dt.datetime.strptime(day + f.stem[-6:], "%Y%m%d%H%M%S") for f in fs]
        first, last = sched.get(route, {}).get(C.day_type(base.date()), C.FALLBACK)
        start = base + dt.timedelta(minutes=max(busy_start, first-C.PAD))
        end = base + dt.timedelta(minutes=min(busy_end, last+C.PAD))
        # 파일 사이뿐 아니라 첫 파일 전/마지막 파일 뒤의 운행 중 누락도 검사한다.
        # 막차 이후와 첫차 이전의 정상 공백은 이 창에 포함하지 않는다.
        busy = [start] + [t for t in ts if start <= t <= end] + [end] if start < end else []
        gap = max(((b - a).total_seconds() for a, b in zip(busy, busy[1:])), default=0) / 60
        bad = sum(not header_ok(f) for f in fs)
        notes.append(f"{route} 스냅샷 {len(fs)}개 · 운행 중 점검창 {start:%H:%M}~{end:%H:%M} 최대 공백 {gap:.1f}분 · 오류 응답 {bad}개")
        if gap > 30 or bad > 0.05 * len(fs):
            status = "FAIL"
        elif (gap > 5 or bad) and status == "OK":
            status = "WARN"
    return status, " / ".join(notes)


def monitor(day, model_dir):
    """그날의 API 기록을 models/lite로 재생 평가한다. '여유'와 계산 탑승은 모델 내부의 판정이다."""
    m, meta = S.load(True, model_dir)
    d = T.features(cats=meta["cats"])
    d = d[d.date == day]
    if d.empty:
        return None
    d = d.assign(rule=S.lite_rule(d))
    point, Pm, Q = T.predict(m, d, quantiles=True)
    board = (d.y.values[:, None] <= T.thresholds(d)).astype(bool)
    th = {(p, s): t for p, s, t, _ in meta["thresholds"]}
    cell = np.array([max(th[("수업 직전" if pk else "평소", S.seg_name(k))] or 9, S.STOP_MIN_TH.get((r, str(s)), 0.0))
                     for pk, k, r, s in zip(d.is_peak == 1, d.stops_away, d.route, d.stop)])
    shown = Pm >= cell[:, None]                                   # 서비스가 '여유'를 띄웠을 칸
    valid = np.array([S.probability_hold(r.route, r.bus_type, r.r_now, meta, r.plate, r.vehicle_id) is None
                      for r in d.itertuples()])
    valid &= S.calibration_mask(d, Q, np.array(meta["qs"]))
    shown &= valid[:, None]
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
    for folder in (p for p in day_folders(logs) if p.name < cutoff):
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
    protected = set(promoted_versions()[-2:])
    try:
        protected.add(model_meta(LIVE)['trained_on'][-1])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pass
    old = [p for p in day_folders(VERS)[:-KEEP_VERSIONS] if p.name not in protected]
    for v in old:
        shutil.rmtree(v)
    if old:
        notes.append(f"모델 버전 {len(old)}개 삭제(최근 {KEEP_VERSIONS}개 유지)")
    free = shutil.disk_usage(logs).free / 1e9
    notes.append(f"남은 디스크 {free:.1f}GB" + (f" ⚠ {MIN_FREE_GB}GB 미만" if free < MIN_FREE_GB else ""))
    for name, path in (("archive", arch), ("processed", B.OUT), ("models", LIVE.parent), ("reports", REPORTS)):
        size = folder_size(path) / 1e9
        notes.append(f'{name} {size:.2f}GB' + (f' ⚠ {SIZE_WARN_GB[name]}GB 초과' if size > SIZE_WARN_GB[name] else ''))
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
    disk_ok = shutil.disk_usage(LIVE.parent).free >= MIN_FREE_GB * 1e9
    if disk_ok:
        B.main()
    mon = monitor(day, LIVE) if disk_ok and (LIVE / "meta.json").exists() else None
    if mon:
        append(REPORTS / "daily_metrics.csv", mon)
        lines += [f"② API 재생 평가(학습 모델 ~{mon['model']}): 오차 {mon['mae']:.2f}명 (지금 재차 그대로 {mon['persistence_mae']:.2f}) · "
                  f"Brier {mon['brier']:.4f} · 3정류장+ {mon['far_mae']:.2f} · 수업 직전 {mon['peak_mae']:.2f} · "
                  f"'여유' 기준 해당 {mon['yeoyu_share']:.0%} → API 기준 계산 탑승 {mon['yeoyu_ok']:.1%}"]
        if mon["yeoyu_ok"] < T.TARGET["평소"]:
            warn.append(f"'여유' 후 API 기준 계산 탑승 {mon['yeoyu_ok']:.1%} < {T.TARGET['평소']:.0%}")
        if mon["mae"] >= mon["persistence_mae"]:
            warn.append(f"모델 오차 {mon['mae']:.2f} ≥ 지금 재차 그대로 {mon['persistence_mae']:.2f}")
    if not disk_ok:
        warn.append(f'여유 디스크 {MIN_FREE_GB}GB 미만 · 재학습 건너뜀 · 기존 모델 유지')
        lines += ['③ 재학습 안 함 (디스크 부족)']
    elif status == "FAIL":
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
            why.append(f"'여유' 후 API 기준 계산 탑승 {meta['oof']['hi_ok']:.1%} < {T.TARGET['평소']:.0%}")
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
        promoted = False
        if ok:
            try:
                activate_model(cand, day)
                promoted = True
            except ActivationError as exc:
                warn.append(str(exc))
                lines[-1] = str(exc)
                notify(str(exc), 'ERROR' if '복구 실패' in str(exc) else 'WARN')
            if promoted:
                try:
                    mark_restart(day)
                except OSError as exc:
                    warn.append(f'재시작 표식 기록 실패: {exc} · 웹 활성 버전 확인 필요')
                    notify(warn[-1], 'ERROR')
        try:
            append(REPORTS / "models.csv", dict(version=day, created=meta["created"], days=len(meta["trained_on"]),
                                                **{f"oof_{k}": v for k, v in meta["oof"].items()}, data=status, promoted=promoted))
        except OSError as exc:
            warn.append(f'모델 이력 기록 실패: {exc}')
    try:
        notes = cleanup(day)
    except Exception as exc:
        notes = [f'정리 실패: {exc}']
    warn += [x for x in notes if "⚠" in x or "실패" in x]
    lines += ["⑥ 정리: " + " · ".join(notes), f"소요 {(time.time() - t0) / 60:.0f}분"]
    try:
        (REPORTS / "daily").mkdir(parents=True, exist_ok=True)
        (REPORTS / "daily" / f"{day}.md").write_text("\n\n".join(lines) + "\n")
    except OSError as exc:
        warn.append(f'마감 보고서 기록 실패: {exc}')
    print("\n".join(lines))
    return lines, warn


def rollback(version=None, force=False):
    vs = [p.name for p in day_folders(VERS)]
    now = json.loads((LIVE / "meta.json").read_text())["trained_on"][-1] if (LIVE / "meta.json").exists() else None
    approved = promoted_versions()
    version = version or next((v for v in reversed(approved) if v != now), None)
    if version not in vs or (version not in approved and not force):
        raise SystemExit(f"승인된 되돌림 버전 없음: {version} (미승인 버전은 명시적 --force 필요)")
    try:
        activate_model(VERS / version, version)
    except ActivationError as exc:
        notify(str(exc), 'ERROR')
        raise SystemExit(str(exc)) from exc
    try:
        mark_restart(version)
    except OSError as exc:
        notify(f'되돌림 성공, 재시작 표식 기록 실패: {exc}', 'ERROR')
    try:
        result = subprocess.run(['sudo', '-n', 'systemctl', 'try-restart', 'hanjari-web'], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:160])
        (REPORTS / 'restart_required').unlink(missing_ok=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        notify(f'모델 {version} 되돌림 성공, 웹 재시작 실패: {exc} · 활성 버전 확인 필요', 'ERROR')
    notify(f"서비스 모델을 {version} 버전으로 되돌림 (이전: ~{now})", "WARN")
    print("되돌림:", version)


if __name__ == "__main__":
    if sys.argv[1:2] == ["rollback"]:
        args = [arg for arg in sys.argv[2:] if arg != '--force']
        rollback(args[0] if args else None, force='--force' in sys.argv[2:])
        sys.exit()
    day = sys.argv[1] if sys.argv[1:] else (dt.datetime.now(S.KST) - dt.timedelta(days=1)).strftime("%Y%m%d")
    before = fingerprint(LIVE) if LIVE.is_dir() else None
    try:
        lines, warn = run(day)
    except Exception as e:
        notify(f"{day} 마감 실패: {e!r} — journalctl -u hanjari-daily 확인. {live_message(before)}", "ERROR")
        raise
    notify(f"{day} 마감" + (" ⚠ " + " / ".join(warn) if warn else " 정상") + "\n" + "\n".join(lines[1:]),
           "WARN" if warn else "INFO")
