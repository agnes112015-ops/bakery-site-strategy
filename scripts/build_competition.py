"""경쟁 현황 섹션 HTML: data/interim/competition.json → build_site.py 에서 import."""
import html as _h
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ["대형 프랜차이즈", "트렌드/프리미엄", "기타 다점포", "개인/독립", "합계"]
SRC = ("서울시 제과점영업 인허가 LOCALDATA_072218 · 휴게음식점 인허가 LOCALDATA_072405 (영업 중, 2026-11-14 수집) · "
       "상권영역 TbgisTrdarRelm · 추정매출 VwsmTrdarSelngQq 20262")


def e(s):
    return _h.escape(str(s))


def rent_html():
    p = ROOT / "data" / "interim" / "rent_gate.json"
    if not p.exists():
        return ""
    g = json.loads(p.read_text(encoding="utf-8"))
    man = lambda v: f"{v / 1e4:,.0f}만 원" if v > 0 else "감당 불가"  # noqa: E731
    rows = "".join(
        f'<tr><th scope="row">{e(r["시나리오"])} {e(r["연도"])}</th><td>{r["매출"] / 1e8:.2f}억 원</td>'
        f'<td>{man(r["모델_월임차료"])}</td><td><b>{man(r["손익분기_월임대료상한"])}</b></td><td>{man(r["이익률10_월임대료상한"])}</td></tr>'
        for r in g["rows"])
    return f"""
<section id="rent" class="sec">
  <div class="wrap">
    <p class="sec-no">04-B · 임대료 게이트 <span class="badge">가정</span></p>
    <h2>출점 조건: 기준 시나리오 기준 월 임대료 335만 원 이하 매물이어야 1년차 손익분기</h2>
    <p class="lead">임대료는 입지 점수에 반영하지 못했습니다. 연결된 공공데이터·공시에 상가 임대료가 없기 때문입니다. 대신 손익에서 이 매장이 감당할 수 있는 월 임대료 상한을 역산했습니다. 실제 매물 임대료가 이 상한을 넘으면 남부터미널역 결론은 재검토 대상입니다.</p>
    <div class="table-wrap"><table class="cmp"><thead><tr><th>시나리오</th><th>연매출</th><th>모델 월 임차료</th><th>손익분기 상한</th><th>이익률 10% 유지 상한</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p class="src"><span>출처</span> {e(g["method"])} {e(g["limitation"])} 계산: scripts/rent_gate.py</p>
  </div>
</section>"""


def competition_html():
    p = ROOT / "data" / "interim" / "competition.json"
    if not p.exists():
        return ""
    c = json.loads(p.read_text(encoding="utf-8"))
    rows = ""
    for k in c["candidates"]:
        a, b = k.get("counts_in_trdar", {}), k.get("counts_500m", {})
        n3 = k.get("new_entries_3y", {}).get("500m", "")
        rows += (f'<tr><th scope="row">{e(k["상권명"])}</th>'
                 + "".join(f'<td>{e(b.get(t, 0))}</td>' for t in TYPES)
                 + f'<td>{e(a.get("합계", 0))}</td><td>{e(n3)}</td></tr>')
    impl = "".join(f"<li>{e(x)}</li>" for x in c.get("implications", []) if isinstance(x, str))
    nb = next((k for k in c["candidates"] if k["상권명"] == "남부터미널역"), None)
    near = ""
    if nb and nb.get("stores_list"):
        near = "".join(
            f'<tr><td>{e(s.get("상호", ""))}</td><td>{e(s.get("유형", ""))}</td><td>{e(s.get("거리m", ""))}</td><td>{e(s.get("인허가일", ""))}</td></tr>'
            for s in nb["stores_list"][:12])
        near = f"""
      <h3 style="margin-top:28px">남부터미널역 반경 500m 베이커리 (가까운 순 12곳)</h3>
      <div class="table-wrap"><table class="plain"><thead><tr><th>상호</th><th>유형</th><th>거리(m)</th><th>인허가일</th></tr></thead><tbody>{near}</tbody></table></div>"""
    return f"""
<section id="competition" class="sec alt">
  <div class="wrap">
    <p class="sec-no">01-B · 베이커리 경쟁 현황</p>
    <h2>남부터미널역은 프리미엄 베이커리 공백 상권 — 500m 안 대형 프랜차이즈 2곳, 1km 안 트렌드 브랜드 0곳</h2>
    <p class="lead">서울시 인허가 데이터로 영업 중인 베이커리를 상권 중심 반경(상권 면적의 등가 원)과 500m 배후권으로 집계했습니다. 후보 3곳 중 남부터미널역이 밀도는 가장 낮고, 업소 1곳당 베이커리 매출은 가장 큽니다.</p>
    <div class="table-wrap"><table class="cmp"><thead><tr><th>상권</th>{''.join(f'<th>500m {e(t)}</th>' for t in TYPES)}<th>상권 반경 내 합계</th><th>최근 3년 신규(500m)</th></tr></thead><tbody>{rows}</tbody></table></div>
    <div class="card" style="margin-top:20px"><h3>시사점</h3><ul class="list">{impl}</ul></div>
    {near}
    <p class="src"><span>출처</span> {e(SRC)}. 브랜드 분류: 데이터에 반복 등장하는 다점포 상호 기준(파리바게뜨·뚜레쥬르 = 대형 프랜차이즈). 좌표계 검증: 최근접 상권 자치구 일치율 93%, 거리 중앙값 197m.</p>
  </div>
</section>"""
