"""DART 공시 손익계산서 수집 → data/raw/dart_<corp>_<year>.json (DART 스킬의 MCP 서버 함수를 직접 호출)."""
import importlib.util
import json
import os
import sys

_P = os.path.expanduser("~/.claude/skills/dart/assets/mcp_server.py")
_spec = importlib.util.spec_from_file_location("dart_server", _P)
dart = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dart)

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
os.makedirs(OUT, exist_ok=True)

PEERS = {
    "에스씨케이컴퍼니": "00359386",  # 스타벅스 (직영)
    "투썸플레이스": "01275948",      # PE 보유 커피·디저트
    "CJ푸드빌": "00357120",          # 뚜레쥬르
    "파리크라상": "01995325",        # 파리바게뜨
    "이디야": "00960942",
    "삼립": "00125530",
}

if __name__ == "__main__":
    years = sys.argv[1:] or ["2025", "2024", "2023"]
    for name, code in PEERS.items():
        for y in years:
            out = {}
            for tool, args in (("fin_key_accounts", {"corp": code, "year": y}),
                               ("fin_statements", {"corp": code, "year": y, "statement": "IS"})):
                body, err = dart.run_tool(tool, args)
                out[tool] = body
            path = os.path.join(OUT, f"dart_{name}_{y}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
            ka = out["fin_key_accounts"]
            print(name, y, "key_accounts:", "error" if ka.get("error") or ka.get("isError") else "ok",
                  json.dumps(ka, ensure_ascii=False)[:300], flush=True)
