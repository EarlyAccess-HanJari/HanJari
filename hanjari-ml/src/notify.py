"""알림. 항상 reports/alerts.log 에 남기고, .env 에 HANJARI_WEBHOOK(디스코드 웹훅 주소)이 있으면 거기로도 보낸다.
실행: python src/notify.py "메시지"   (systemd 실패 알림용)
"""
import datetime as dt, json, sys, urllib.request
import build_dataset as B

REPORTS = B.ROOT / "reports"
KST = dt.timezone(dt.timedelta(hours=9))


def webhook():
    try:
        return next((l.split("=", 1)[1].strip() for l in open(B.ROOT / ".env") if l.startswith("HANJARI_WEBHOOK=")), "") or None
    except OSError:
        return None


def send(text, level="INFO"):
    REPORTS.mkdir(exist_ok=True)
    with open(REPORTS / "alerts.log", "a") as f:
        f.write(f"{dt.datetime.now(KST):%Y-%m-%d %H:%M} [{level}] {text}\n")
    url = webhook()
    if not url:
        return
    icon = {"INFO": "🚌", "WARN": "⚠️", "ERROR": "🚨"}.get(level, "")
    body = json.dumps({"content": f"{icon} **한자리** {text}"[:1900]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json", "User-Agent": "hanjari"}), timeout=10)
    except Exception as e:  # 알림이 실패해도 본 작업은 계속
        print("알림 전송 실패:", repr(e))


if __name__ == "__main__":
    send(" ".join(sys.argv[1:]) or "(내용 없음)", "ERROR")
