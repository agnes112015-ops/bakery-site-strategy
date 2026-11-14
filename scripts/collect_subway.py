"""지하철 역별 일별 승하차(CardSubwayStatsNew): 3년 전 같은 요일 주간 vs 최근 주간 → data/raw/subway_<date>.json"""
import datetime as dt
import json
import os

from seoul_api import fetch_all

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

# 2026-11-02(월)~11-08(일)  vs  2023-11-06(월)~11-12(일): 같은 요일 정렬
RECENT = [dt.date(2026, 11, 2) + dt.timedelta(d) for d in range(7)]
BASE = [dt.date(2023, 11, 6) + dt.timedelta(d) for d in range(7)]

if __name__ == "__main__":
    for d in BASE + RECENT:
        ymd = d.strftime("%Y%m%d")
        path = os.path.join(OUT, f"subway_{ymd}.json")
        if os.path.exists(path):
            continue
        total, rows = fetch_all("CardSubwayStatsNew", [ymd])
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": ymd, "api_total": total, "rows": rows}, f, ensure_ascii=False)
        print(ymd, total, flush=True)
