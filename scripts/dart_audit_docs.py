"""비상장 외감법인 감사보고서 원문(OpenDART document.xml) 다운로드 → data/raw/dart_docs/<회사>/<rcept_no>/"""
import io
import json
import os
import sys
import zipfile

from collect_dart import PEERS, dart

DOCS = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "dart_docs")


def audit_list(code, bgn="20240101", end="20261114"):
    rows = dart.call("list.json", corp_code=code, bgn_de=bgn, end_de=end, pblntf_ty="F", page_count=100)
    return [r for r in rows if "감사보고서" in r.get("report_nm", "")]


def download(code, rcept_no, dest):
    c = dart.client()
    r = c.session.get("https://opendart.fss.or.kr/api/document.xml",
                      params={"crtfc_key": c.api_key, "rcept_no": rcept_no}, timeout=60)
    os.makedirs(dest, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(r.content)).extractall(dest)
    return os.listdir(dest)


if __name__ == "__main__":
    index = {}
    for name, code in PEERS.items():
        if name == "삼립":
            continue
        rows = audit_list(code)
        index[name] = rows
        for r in rows:
            print(name, r["rcept_no"], r["rcept_dt"], r["report_nm"], r.get("flr_nm"), flush=True)
        # 회사별 최신 (연결 아닌) 감사보고서 1건 + 연결 감사보고서 있으면 1건
        picks = []
        for kind in ("연결감사보고서", "감사보고서"):
            cand = [r for r in rows if r["report_nm"].strip().startswith(kind) or
                    (kind == "감사보고서" and "연결" not in r["report_nm"])]
            if cand:
                picks.append(sorted(cand, key=lambda x: x["rcept_dt"])[-1])
        for p in {p["rcept_no"]: p for p in picks}.values():
            files = download(code, p["rcept_no"], os.path.join(DOCS, name, p["rcept_no"]))
            print("  downloaded", p["rcept_no"], p["report_nm"], files, flush=True)
    with open(os.path.join(DOCS, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
