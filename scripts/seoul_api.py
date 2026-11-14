"""서울 열린데이터광장 호출 래퍼: 연결된 seoul-data MCP 서버의 fetch를 재사용한다 (API 키는 서버 쪽 .env에서만 읽음)."""
import importlib.util
import json
import os
import sys
import time

_SERVER = os.path.expanduser("~/.claude/mcp-servers/seoul-data/server.py")
_spec = importlib.util.spec_from_file_location("seoul_server", _SERVER)
_srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_srv)


def page(service, start, end, params=None, retries=3):
    for i in range(retries):
        try:
            return _srv.tool_query({"service": service, "start": start, "end": end, "params": params or []})
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def fetch_all(service, params=None, keep=None, row_filter=None):
    """전체 행을 1000건씩 받아 필터·컬럼 선택 후 리스트로 반환."""
    first = page(service, 1, 1000, params)
    total = first.get("total") or 0
    rows = list(first.get("rows", []))
    for s in range(1001, total + 1, 1000):
        rows += page(service, s, min(s + 999, total), params).get("rows", [])
    if row_filter:
        rows = [r for r in rows if row_filter(r)]
    if keep:
        rows = [{k: r.get(k) for k in keep} for r in rows]
    return total, rows


if __name__ == "__main__":
    out = page(sys.argv[1], 1, 1, json.loads(sys.argv[2]) if len(sys.argv) > 2 else [])
    print(json.dumps({"total": out.get("total"), "result": out.get("result"),
                      "fields": list(out["rows"][0].keys()) if out.get("rows") else None,
                      "sample": out["rows"][0] if out.get("rows") else out.get("hint")}, ensure_ascii=False))
