"""수집 감시 — 10분마다(systemd 타이머). '켜져 있는데 못 받는' 조용한 실패를 잡는다.

  - 노선 시간표 안인데 최신 스냅샷이 STALE 분보다 오래됨 → 수집기 재시작(30분에 한 번까지) + 알림
  - 최근 스냅샷 RECENT 개가 전부 API 오류 응답(키 만료·한도 초과) → 알림
  - 남은 디스크 MIN_FREE_GB 미만 → 알림
같은 문제는 한 번만 알리고(reports/watchdog.json), 사라지면 '복구' 알림.
"""
import datetime as dt, json, shutil, subprocess
import build_dataset as B
import collect as C
import notify as N

STALE = 10          # 분. 한산한 시간 수집 간격이 2분 반이라 넉넉히
RECENT = 10
MIN_FREE_GB = 5
RESTART_GAP = 30    # 분
STATE = N.REPORTS / "watchdog.json"


def ok_header(f):
    try:
        return json.loads(f.read_bytes())["msgHeader"].get("headerCd") == "0"
    except (OSError, ValueError):
        return False


def check(now):
    problems, stale = [], False
    sched = C.load_sched()
    # 자정 직후엔 새 날짜 폴더가 비어 있음(막차 00:42 까지 수집 중) → 어제 폴더까지 보고 가장 최근 파일로 판단 (10-02 헛알림 수정)
    folders = [B.LOG / (now - dt.timedelta(days=d)).strftime("%Y%m%d") for d in (1, 0)]
    for route in C.ROUTES:
        if not C.allowed(now, route, sched):
            continue
        day, m = C.service_day(now)
        first = sched.get(route, {}).get(C.day_type(day), C.FALLBACK)[0]
        if m < first - C.PAD + STALE:  # 수집 시작 직후는 아직 쌓이는 중
            continue
        fs = [f for fd in folders for f in sorted(fd.glob(f"{route}_arr_*.json"))]  # 날짜 순 → 마지막이 가장 최근
        age = (now - dt.datetime.strptime(fs[-1].parent.name + fs[-1].stem[-6:], "%Y%m%d%H%M%S")).total_seconds() / 60 if fs else None
        if age is None or age > STALE:
            problems.append(f"{route} 새 데이터 없음({'이틀간 0개' if age is None else f'{age:.0f}분째'})")
            stale = True
        elif fs and not any(ok_header(f) for f in fs[-RECENT:]):
            problems.append(f"{route} 최근 {RECENT}개 모두 API 오류 응답(키·한도 확인)")
    free = shutil.disk_usage(B.LOG.resolve()).free / 1e9
    if free < MIN_FREE_GB:
        problems.append(f"남은 디스크 {free:.1f}GB")
    return problems, stale


def main():
    now = dt.datetime.now(N.KST).replace(tzinfo=None)
    problems, stale = check(now)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    if stale:
        last = st.get("restarted")
        if not last or (now - dt.datetime.fromisoformat(last)).total_seconds() > RESTART_GAP * 60:
            r = subprocess.run(["sudo", "-n", "systemctl", "restart", "hanjari-collect"], capture_output=True, text=True)
            problems.append("수집기 재시작 " + ("함" if r.returncode == 0 else f"실패({r.stderr.strip()[:80]})"))
            st["restarted"] = now.isoformat()
    key = sorted(p.split("(")[0] for p in problems if not p.startswith("수집기 재시작"))
    if key and key != st.get("open"):
        N.send("수집 감시: " + " / ".join(problems), "ERROR")
    elif not key and st.get("open"):
        N.send("수집 감시: 복구됨 (" + " / ".join(st["open"]) + ")", "INFO")
    st["open"], st["checked"] = key, now.isoformat()
    N.REPORTS.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False))
    print(now.strftime("%H:%M"), "문제 없음" if not problems else problems)


if __name__ == "__main__":
    main()
