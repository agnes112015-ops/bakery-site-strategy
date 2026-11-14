"""서울시 인허가(LOCALDATA): 제과점영업(072218) 전체 + 휴게음식점(072405) 중 베이커리성 업소 → data/raw/license_*.json
영업 중인 업소만 보관. 좌표 X,Y는 원자료 그대로(중부원점 TM)."""
import json
import os
import re

from seoul_api import page

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
KEEP = ["MGTNO", "APVPERMYMD", "TRDSTATENM", "DTLSTATENM", "DCBYMD", "SITEWHLADDR", "RDNWHLADDR",
        "BPLCNM", "UPTAENM", "SNTUPTAENM", "X", "Y", "SITEAREA", "FACILTOTSCP"]
BAKERY_PAT = re.compile(r"베이커리|베이크|제과|빵|베이글|bake|bagel|boulang|브레드|bread|파리바게|뚜레쥬르|크로와상|크루아상|도넛|도너츠|노티드|성심당|아티제|런던베이글|타르트|케이크|케익|휘낭시에|스콘|패스츄리|파티스|patisserie", re.I)


def collect(service, name, flt):
    first = page(service, 1, 1000)
    total = first["total"]
    rows = []
    for s in range(1, total + 1, 1000):
        res = first if s == 1 else page(service, s, min(s + 999, total))
        for r in res.get("rows", []):
            if (r.get("TRDSTATENM") or "").startswith("영업") and flt(r):
                rows.append({k: (r.get(k) or "").strip() if isinstance(r.get(k), str) else r.get(k) for k in KEEP})
        if s % 20000 == 1:
            print(name, s, "/", total, "kept", len(rows), flush=True)
    with open(os.path.join(OUT, f"license_{name}.json"), "w", encoding="utf-8") as f:
        json.dump({"service": service, "api_total": total, "filter": "영업 중" + ("" if name == "bakery" else " & 베이커리성 상호/업태"), "rows": rows}, f, ensure_ascii=False)
    print("saved", name, len(rows), flush=True)


if __name__ == "__main__":
    collect("LOCALDATA_072218", "bakery", lambda r: True)
    collect("LOCALDATA_072405", "cafe_bakery",
            lambda r: bool(BAKERY_PAT.search((r.get("BPLCNM") or "") + " " + (r.get("UPTAENM") or ""))))
    print("ALL DONE", flush=True)
