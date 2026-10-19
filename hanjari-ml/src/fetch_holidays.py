"""한국 공휴일(대체·임시 포함) → data/processed/holidays.csv

출처: 한국천문연구원 특일정보 getRestDeInfo (공공데이터포털 15012690). 키는 .env SEOUL_BUS_API_KEY (같은 계정).
임시공휴일은 연중 추가 지정되므로 학기 중 가끔 다시 실행할 것.
"""
import csv, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
YEARS = range(2023, 2028)


def key():
    for line in open(ROOT / ".env"):
        if line.startswith("SEOUL_BUS_API_KEY="):
            return line.split("=", 1)[1].strip()


def main():
    k, rows = key(), []
    for y in YEARS:
        q = urllib.parse.urlencode({"serviceKey": k, "solYear": y, "numOfRows": 100})
        root = ET.fromstring(urllib.request.urlopen(f"{URL}?{q}", timeout=20).read())
        assert root.findtext("header/resultCode") == "00", root.findtext("header/resultMsg")
        items = root.findall("body/items/item")
        assert int(root.findtext("body/totalCount")) == len(items)  # 100건 넘어 잘리면 실패
        rows += [(i.findtext("locdate"), i.findtext("dateName")) for i in items if i.findtext("isHoliday") == "Y"]
    out = ROOT / "data/processed/holidays.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "name"])
        w.writerows(sorted(set(rows)))
    print(out, len(rows))


if __name__ == "__main__":
    main()
