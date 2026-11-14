"""임대료 게이트: 임대료 공공데이터가 없으므로 손익에서 '감당 가능한 월 임대료 상한'을 역산 → data/interim/rent_gate.json"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = json.loads((ROOT / "data/interim/pnl_v2.json").read_text(encoding="utf-8"))
out = {"method": "월 임대료 상한 = (모델 임차료 + 영업이익 − 목표이익) / 12. 모델 임차료는 재보정 손익(pnl_v2.json, 직영 베이커리 4사 중앙값 임차료율 11.1%) 기준.",
       "limitation": "남부터미널역 실제 상가 임대료는 연결된 공공데이터(서울 열린데이터광장)·DART에 없음 → 실제 매물 임대료를 이 상한과 비교해 출점 여부를 결정해야 함.",
       "rows": []}
for s, v in P["scenarios"].items():
    for y in ("Y1", "Y3"):
        d = v["연도별"][y]
        r, rent, oi = d["매출"], d["임차료"], d["영업이익"]
        out["rows"].append({"시나리오": s, "연도": y, "매출": r, "모델_월임차료": rent / 12,
                            "손익분기_월임대료상한": (rent + oi) / 12,
                            "이익률10_월임대료상한": (rent + oi - 0.10 * r) / 12})
(ROOT / "data/interim/rent_gate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("ok")
