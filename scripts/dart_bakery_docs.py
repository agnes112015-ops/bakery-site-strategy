"""베이커리 전문·트렌드 업체 DART 감사보고서 원문 수집 (dart_audit_docs.py 재사용)."""
import json
import os

from dart_audit_docs import DOCS, audit_list, download

BAKERY = {
    "파리크라상": "01995325",       # 파리바게뜨
    "엘비엠_01844049": "01844049",  # 런던베이글뮤지엄 운영사 후보 (동명 2개 → 둘 다 확인)
    "엘비엠_01813687": "01813687",
    "지에프에프지": "01647835",     # 노티드 등
    "로쏘": "01070750",             # 성심당
    "보나비": "00821157",           # 아티제
    "신세계푸드": "00274933",       # 베이커리 사업 포함(상장)
}

if __name__ == "__main__":
    index = {}
    for name, code in BAKERY.items():
        rows = audit_list(code, bgn="20230101")
        # 파리크라상 등 기간 내 없으면 더 넓게
        if not rows:
            rows = audit_list(code, bgn="20200101", end="20221231")
        index[name] = rows
        print("==", name, code, len(rows), flush=True)
        for r in rows[:6]:
            print("  ", r["rcept_no"], r["rcept_dt"], r["report_nm"], r.get("flr_nm"), flush=True)
        sep = [r for r in rows if "연결" not in r["report_nm"]]
        if sep:
            p = sorted(sep, key=lambda x: x["rcept_dt"])[-1]
            files = download(code, p["rcept_no"], os.path.join(DOCS, name, p["rcept_no"]))
            print("  downloaded", p["rcept_no"], p["report_nm"], files, flush=True)
    with open(os.path.join(DOCS, "index_bakery.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
