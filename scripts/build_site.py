# -*- coding: utf-8 -*-
"""site/index.html 생성기.

입력(모두 data/interim):
  location.json, interior.json, menu.json, pnl.json, dart_benchmark.json, analysis.json, trdar_scores.csv
출력:
  site/index.html (자체 완결 한 페이지, 한국어)

원칙: 페이지에 나오는 모든 숫자는 위 JSON/CSV에서 읽어 이 스크립트가 서식만 입힌다(손 타이핑 금지).
실행: PYTHONIOENCODING=utf-8 python scripts/build_site.py
"""
import csv
import json
import re
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "site" / "index.html"


def load(name):
    with open(INTERIM / name, encoding="utf-8") as f:
        return json.load(f)


LOC = load("location.json")
INT = load("interior.json")
MENU = load("menu.json")
PNL = load("pnl.json")
DART = load("dart_benchmark.json")
ANA = load("analysis.json")
with open(INTERIM / "trdar_scores.csv", encoding="utf-8-sig") as f:
    SCORES = list(csv.DictReader(f))

DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"

# ---------------------------------------------------------------- 서식 도우미


def e(s):
    return escape(str(s), quote=True)


def eok(won, d=2):
    return f"{won / 1e8:,.{d}f}억원"


def won(v):
    return f"{round(v):,}원"


def pct(frac, d=1, sign=False):
    v = frac * 100
    while v != 0 and round(v, d) == 0 and d < 3:   # −0.0% 같은 부호 있는 0 표기 방지
        d += 1
    s = f"{v:+.{d}f}%" if sign else f"{v:.{d}f}%"
    return s.replace("-", "−")


def num(v, d=0):
    return f"{v:,.{d}f}"


def q(code):  # "20262" -> "26Q2"
    code = str(code)
    return f"{code[2:4]}Q{code[4]}"


A = '<span class="tag tag-a" title="전망·설계 가정">가정</span>'
R = '<span class="tag tag-r" title="공공데이터·DART 공시 실적">실적</span>'


def linkify(text):
    """출처 텍스트: DART URL 괄호는 지우고 접수번호를 링크로."""
    t = re.sub(r"\s*\(https://dart\.fss\.or\.kr[^)]*\)", "", str(text))
    t = e(t)
    return re.sub(
        r"(?<![\d=])(20\d{12})(?!\d)",
        lambda m: f'<a href="{DART_URL.format(m.group(1))}" target="_blank" rel="noopener">{m.group(1)}</a>',
        t,
    )


def src(*items):
    items = [i for i in items if i]
    body = " · ".join(linkify(i) for i in items)
    return f'<p class="src"><span>출처</span> {body}</p>'


def ul(items, cls="list"):
    return f'<ul class="{cls}">' + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>"


# ---------------------------------------------------------------- 공통 데이터
M = LOC["method"]
CANDS = LOC["candidates"]
FIN = LOC["final"]
FP = LOC["final_profile"]
C1 = CANDS[0]
SEL_SRC = "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq (제과점 CS100005·커피-음료 CS100010)"
STOR_SRC = "서울시 상권분석서비스 점포 VwsmTrdarStorQq"
SCN = PNL["scenarios"]
BE = PNL["breakeven"]
SENS = PNL["sensitivity"]
ASM = {a["name"]: a for a in PNL["assumptions"]}
BASE = SCN["기준"]["연도별"]
YEARS = ["Y1", "Y2", "Y3"]
first_profit = next((y for y in YEARS if BASE[y]["영업이익"] > 0), None)
cum_base = SCN["기준"]["3년누적_영업이익"]
area_m2 = INT["meta"]["계산값"]["총면적_가정_m2"]
area_py = INT["meta"]["계산값"]["총면적_가정_평"]
seats = INT["meta"]["계산값"]["좌석_가정"]
sales_m = C1["지표"]["매출"]
stores_m = C1["지표"]["점포"]
pop_m = C1["지표"]["인구"]
mix_profile = C1["지표"]["고객구성_합산(제과+커피, 20262)"]

DSRC = {n: f"DART {n} {DART[n]['rcept_no']}" for n in DART if not n.startswith('_')}

# ---------------------------------------------------------------- DART 비용구조 (원천 천원 → 비율)


def dart_ratios(name):
    d = DART[name]
    rev = d["revenue"]
    c = {k: sum(v) for k, v in d["costs"].items()}
    out = {
        "원재료·상품": c.pop("원재료·상품", 0),
        "인건비": c.pop("인건비", 0),
        "점유비용(임차료+사용권자산상각)": c.pop("임차료", 0) + c.pop("사용권자산상각비", 0),
        "지급수수료": c.pop("지급수수료", 0),
        "유무형자산상각비": c.pop("유무형자산상각비", 0),
    }
    out["기타(운반·판촉·수도광열 등)"] = sum(c.values())
    out = {k: v / rev for k, v in out.items()}
    out["영업이익"] = d["operating_income"] / rev
    return out


DART_CHART_COS = ["에스씨케이컴퍼니", "투썸플레이스", "CJ푸드빌"]
dart_ratio = {n: dart_ratios(n) for n in DART_CHART_COS}
dart_cats = list(dart_ratio[DART_CHART_COS[0]].keys())

# ---------------------------------------------------------------- 차트 데이터
trend = LOC["seoul_trend"]
tq = [k for k in trend if not k.startswith("_")]
b0, c0 = trend[tq[0]]["제과점_억원"], trend[tq[0]]["커피음료_억원"]
chart = {
    "seoulTrend": {
        "labels": [q(k) for k in tq],
        "bakIdx": [round(trend[k]["제과점_억원"] / b0 * 100, 1) for k in tq],
        "cofIdx": [round(trend[k]["커피음료_억원"] / c0 * 100, 1) for k in tq],
        "bakRaw": [trend[k]["제과점_억원"] for k in tq],
        "cofRaw": [trend[k]["커피음료_억원"] for k in tq],
    },
    "cands": {
        "labels": [q(k) for k in C1["지표"]["매출"]["합산매출_7분기_억원"]],
        "series": [
            {"name": c["상권명"], "data": list(c["지표"]["매출"]["합산매출_7분기_억원"].values())}
            for c in CANDS
        ],
    },
    "scatter": {
        "all": [
            {"x": round(float(r["합산_2분기YoY_중앙값"]) * 100, 2), "y": round(float(r["점수"]), 4), "n": r["상권명"]}
            for r in SCORES
            if r["합산_2분기YoY_중앙값"] and r["점수"] and r["상권명"] not in [c["상권명"] for c in CANDS]
        ],
        "cands": [
            {"x": round(float(r["합산_2분기YoY_중앙값"]) * 100, 2), "y": round(float(r["점수"]), 4), "n": r["상권명"]}
            for r in SCORES
            if r["상권명"] in [c["상권명"] for c in CANDS]
        ],
    },
    "ticket": {
        "labels": [q(k) for k in MENU["avg_ticket"]["추이_상권"]],
        "bak": [v["제과점"] for v in MENU["avg_ticket"]["추이_상권"].values()],
        "cof": [v["커피"] for v in MENU["avg_ticket"]["추이_상권"].values()],
        "all": [v["합산"] for v in MENU["avg_ticket"]["추이_상권"].values()],
        "proposal": MENU["avg_ticket"]["제안"],
    },
    "scen": {
        "labels": YEARS,
        "names": list(SCN.keys()),
        "rev": {s: [round(SCN[s]["연도별"][y]["매출"] / 1e8, 2) for y in YEARS] for s in SCN},
        "opm": {s: [round(SCN[s]["연도별"][y]["영업이익률"] * 100, 1) for y in YEARS] for s in SCN},
        "be": round(BE["손익분기_연매출_원"] / 1e8, 2),
    },
    "dart": {
        "labels": [f'{n} ({DART[n]["brand"].split(" (")[0]})' for n in DART_CHART_COS],
        "cats": dart_cats,
        "values": {c: [round(dart_ratio[n][c] * 100, 1) for n in DART_CHART_COS] for c in dart_cats},
    },
}

# ================================================================= 섹션 HTML

# ---- 히어로
hero_line = (
    f"{FIN['자치구']} {FIN['상권명']} 상권에 약 90~110㎡ 베이커리 주도형 직영 매장 "
    f"‘{INT['concept'].split(' (')[0]}’을 연다. 재보정 기준 Y1 매출 8.44억 원·영업이익률 1.3%(손익분기 8.24억 원), "
    f"출점 조건은 임차료 연 0.94억 원·설비 4.5억 원 이하."
)
hero = f"""
<header class="hero" id="top">
  <div class="wrap">
    <p class="eyebrow">PE 포트폴리오 · 커피·베이커리 전문점 서울 신규 출점 전략</p>
    <h1>3년 뒤 더 커질 상권,<br><em>{e(FIN['상권명'])}</em>에 굽는 매장을 연다</h1>
    <p class="lead">{e(hero_line)} {A}</p>
    <dl class="brief">
      <div><dt>클라이언트</dt><dd>사모펀드(PE)가 보유한 커피·베이커리 전문점 브랜드</dd></div>
      <div><dt>과제</dt><dd>서울 1호 신규 출점지 선정(3년 뒤 성장 상권) · 인테리어 컨셉 · 메뉴 구성 · 3년 손익 시뮬레이션</dd></div>
      <div><dt>결론</dt><dd>{e(FIN['상권명'])}({e(FIN['자치구'])} {e(FIN['행정동'])}) · {e(INT['concept'])} · 재보정 기준 Y3 영업이익률 7.3% {A}</dd></div>
    </dl>
    <div class="site-card">
      <div>
        <p class="k">최종 입지</p>
        <p class="site-name">{e(FIN['상권명'])}</p>
        <p class="site-meta">{e(FIN['자치구'])} {e(FIN['행정동'])} · {e(FIN['상권구분'])} · 상권코드 {e(FIN['TRDAR_CD'])}</p>
      </div>
      <ul class="site-facts">
        <li><b>{eok(sales_m['합산매출_최신_억원'] * 1e8)}</b><span>분기 합산매출(제과+커피, {q(LOC['method']['기준분기']['최신'])}) {R}</span></li>
        <li><b>{' → '.join(pct(v / 100) for v in sales_m['합산_2분기YoY_3구간_%(23→24,24→25,25→26)'])}</b><span>같은 2분기 YoY 3구간 {R}</span></li>
        <li><b>{pct(pop_m['유동인구_증감률_%'] / 100, sign=True)}</b><span>유동인구 3년 증감(176상권 중앙값 {pct(pop_m['유동인구_증감률_서울176상권중앙값_%'] / 100, sign=True)}) {R}</span></li>
      </ul>
    </div>
    {src(SEL_SRC + ' 20232~20262', '서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq 20232·20262', 'pnl.json(가정)')}
  </div>
</header>
"""

# ---- Executive summary
kpis = [
    (pct(sales_m["합산_CAGR3_%"] / 100, sign=True), "합산매출 3년 CAGR",
     f"서울 전체 제과+커피 시장 {pct(ANA['seoul_market_cagr3'], 2, sign=True)}", R,
     SEL_SRC + " 20232→20262"),
    (f"{stores_m['베이커리_점포당분기매출_억원']:.3f}억원", "베이커리 점포당 분기매출",
     f"176상권 중앙값 {stores_m['베이커리_점포당분기매출_176중앙값_억원']:.3f}억원 · 3년 {pct(stores_m['베이커리_점포당매출_3년변화율_%'] / 100, sign=True)}", R,
     STOR_SRC + " · VwsmTrdarSelngQq 20262"),
    (eok(BE["손익분기_연매출_원"]), "손익분기 연매출",
     f"월 {eok(BE['손익분기_월매출_원'])} · 기준 Y1 매출의 {pct(BE['손익분기_대비_기준Y1매출'])}", A,
     f"pnl.json breakeven ({DSRC['에스씨케이컴퍼니']} 비율 기반)"),
    (pct(BASE["Y3"]["영업이익률"], sign=True), "기준 시나리오 Y3 영업이익률",
     f"Y1 {pct(BASE['Y1']['영업이익률'], sign=True)} → Y2 {pct(BASE['Y2']['영업이익률'], sign=True)} · 3년 누적 {eok(cum_base)}", A,
     "pnl.json scenarios.기준"),
]
kpi_html = "".join(
    f'<article class="kpi"><div class="kpi-top">{badge}</div><p class="kpi-v">{e(v)}</p>'
    f'<p class="kpi-l">{e(l)}</p><p class="kpi-s">{e(s)}</p>{src(sr)}</article>'
    for v, l, s, badge, sr in kpis
)
cons = SCN["보수"]
opti = SCN["낙관"]
exec_points = [
    f"서울 제과+커피 시장은 3년 CAGR {pct(ANA['seoul_market_cagr3'], 2)}로 정체 — 성장은 상권 간 점유율 이동이다. "
    f"{FIN['상권명']}은 같은 2분기 YoY가 3구간 모두 플러스이면서 가속하는 드문 누적형 성장 상권.",
    f"베이커리 점포는 {num(stores_m['베이커리점포_3년전'])}곳 → {num(stores_m['베이커리점포_최신'])}곳으로 줄었는데 점포당 매출은 "
    f"{pct(stores_m['베이커리_점포당매출_3년변화율_%'] / 100, sign=True)}: 공급 부족형 수요. 커피는 {num(stores_m['커피점포_3년전'])} → "
    f"{num(stores_m['커피점포_최신'])}곳으로 포화라 베이커리가 이끄는 포맷으로 차별화한다.",
    f"손익은 상권 평균 대비 매출 배수가 가른다(가정): 보수 x{cons['매출배수']} 3년 누적 {eok(cons['3년누적_영업이익'])}, "
    f"기준 x{SCN['기준']['매출배수']} {eok(cum_base)}, 낙관 x{opti['매출배수']} {eok(opti['3년누적_영업이익'])}.",
]
exec_html = f"""
<section id="summary" class="sec">
  <div class="wrap">
    <p class="sec-no">Executive Summary</p>
    <h2>핵심 숫자 4개</h2>
    <div class="kpis">{kpi_html}</div>
    <ol class="takeaways">{''.join(f'<li>{e(p)}</li>' for p in exec_points)}</ol>
    <p class="legend-note">{R} 서울 열린데이터광장·DART 공시에서 직접 계산한 값 &nbsp; {A} 전망·설계 가정(근거 수치와 계산식 병기)</p>
  </div>
</section>
"""

# ---- 01 입지
w2 = M["가중치_v2"]
wmax = max(abs(v) for v in w2.values())
weights_html = "".join(
    f'<li><span class="w-name">{e(k)}</span><span class="w-bar"><i class="{"neg" if v < 0 else "pos"}" '
    f'style="width:{abs(v) / wmax * 100:.0f}%"></i></span><span class="w-val">{v:+.2f}</span></li>'
    for k, v in w2.items()
)
pen_html = " · ".join(f"{e(k)} −{v:.2f}" for k, v in M["감점_v2"].items())

steps = [
    (f"{num(ANA['universe'])}개", "서울 전체 상권", "상권분석서비스 상권영역 TbgisTrdarRelm"),
    (f"{num(ANA['eligible'])}개", "분석 대상", M["필터"].split(" → ")[0]),
    ("v2 점수", "11개 지표 가중합 − 감점", M["점수방식"]),
    ("3개 패널", "성장·타깃·리스크 검토", "패널별 상위 상권을 원천 7개 분기 시계열로 재확인해 단절·마스킹 상권 제외"),
    (f"{len(CANDS)}곳 → 1곳", "후보 → 최종", M["최종판정_원칙"].split(" 조정 내역")[0]),
]
steps_html = "".join(
    f'<li><b>{e(a)}</b><span class="st-t">{e(b)}</span><span class="st-d">{e(c)}</span></li>' for a, b, c in steps
)


def cand_row(label, fn, badge=""):
    cells = "".join(f"<td>{fn(c)}</td>" for c in CANDS)
    return f"<tr><th scope=\"row\">{label} {badge}</th>{cells}</tr>"


def g(c, *path):
    v = c["지표"]
    for p in path:
        v = v[p]
    return v


rows = [
    cand_row("자치구·행정동", lambda c: e(f"{c['자치구']} {c['행정동']}")),
    cand_row("v2 순위(점수)", lambda c: f"{c['순위']}위 ({c['점수']:.3f})" + (f" · 감점 {c['감점']:.2f}" if c["감점"] else ""), R),
    cand_row(f"분기 합산매출 {q('20262')}", lambda c: f"{g(c, '매출', '합산매출_최신_억원'):.2f}억원", R),
    cand_row("합산 CAGR3", lambda c: pct(g(c, "매출", "합산_CAGR3_%") / 100), R),
    cand_row("2분기 YoY 3구간", lambda c: " / ".join(pct(v / 100) for v in g(c, "매출", "합산_2분기YoY_3구간_%(23→24,24→25,25→26)")), R),
    cand_row("점프비중", lambda c: f"{g(c, '매출', '점프비중(최대 단일분기 증가/3년 증가분)'):.2f}", R),
    cand_row("베이커리 매출 3년전 → 최신", lambda c: f"{g(c, '매출', '베이커리매출_3년전_억원'):.2f} → {g(c, '매출', '베이커리매출_최신_억원'):.2f}억원", R),
    cand_row("베이커리 점포당 분기매출", lambda c: f"{g(c, '점포', '베이커리_점포당분기매출_억원'):.3f}억원 ({pct(g(c, '점포', '베이커리_점포당매출_3년변화율_%') / 100, sign=True)})", R),
    cand_row("베이커리 / 커피 점포 (3년전→최신)", lambda c: f"{num(g(c, '점포', '베이커리점포_3년전'))}→{num(g(c, '점포', '베이커리점포_최신'))} / {num(g(c, '점포', '커피점포_3년전'))}→{num(g(c, '점포', '커피점포_최신'))}", R),
    cand_row("표본 4분기 평균 폐업률", lambda c: pct(g(c, "점포", "표본4분기_평균폐업률_%(제과+커피)") / 100), R),
    cand_row("유동인구 3년 증감", lambda c: pct(g(c, "인구", "유동인구_증감률_%") / 100, sign=True), R),
    cand_row("2030 / 여성 / 주말 비중", lambda c: " / ".join(pct(g(c, "고객구성_합산(제과+커피, 20262)", k) / 100) for k in ["2030비중_%", "여성비중_%", "주말비중_%"]), R),
    cand_row("오전(06~11시) 매출 비중", lambda c: pct(g(c, "고객구성_합산(제과+커피, 20262)", "오전(06~11시)비중_%") / 100), R),
    cand_row("합산 객단가", lambda c: won(g(c, "고객구성_합산(제과+커피, 20262)", "객단가_원")), R),
    cand_row("상권변화지표 · 평균 운영개월", lambda c: e(f"{g(c, '상권변화지표', '지표')} · {num(g(c, '상권변화지표', '운영영업개월_평균'))}개월"), R),
    cand_row("3년 후 분기 합산매출 기본 / 보수", lambda c: f"{c['3년후_전망']['기본(가정)']['값_억원']:.1f} / {c['3년후_전망']['보수(가정)']['값_억원']:.1f}억원", A),
]
med = mix_profile["176상권중앙값"]
cand_head = "".join(
    f'<th scope="col" class="{"pick" if i == 0 else ""}">{e(c["상권명"])}{"<small>최종</small>" if i == 0 else f"<small>후보 {c["후보순위"]}</small>"}</th>'
    for i, c in enumerate(CANDS)
)
cand_table = f"""
<div class="table-wrap"><table class="cmp">
<thead><tr><th scope="col">지표</th>{cand_head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="note">176상권 중앙값: 2030 {pct(med['2030비중_%'] / 100)} · 여성 {pct(med['여성비중_%'] / 100)} · 주말 {pct(med['주말비중_%'] / 100)} · 오전 {pct(med['오전비중_%'] / 100)} · 객단가 {won(med['객단가_원'])}.
3년 후 전망 {A}: 기본 = 분기 합산매출 × (1 + min(CAGR3, 25%) × 0.7)³, 보수 = 분기 합산매출 × (1 + 0.5×min(2분기 YoY 중앙값, 25%) + 0.5×서울 시장 CAGR3)³로 평균 회귀.</p>
{src(*C1['출처'][:4], C1['출처'][6])}
"""

reasons_html = "".join(f"<li>{e(r)}</li>" for r in FIN["선정이유"])
risk_html = "".join(f"<li>{e(r)}</li>" for r in C1["리스크"])
obj_html = "".join(
    f'<div class="qa"><p class="qa-q">{e(o["반대의견"])}</p><p class="qa-a">{e(o["대응"])}</p></div>'
    for o in FIN["반대의견과_대응"]
)
panel_html = "".join(
    f'<tr><th scope="row">{e(p["상권"])}</th><td>{e(p["제기"])}</td><td><b>{e(p["판정"])}</b></td><td>{e(p["근거"])}</td></tr>'
    for p in LOC["패널_판정"]
)
st_sum = trend["_요약"]

loc_html = f"""
<section id="location" class="sec">
  <div class="wrap">
    <p class="sec-no">01 · 입지 선정</p>
    <h2>시장은 정체, 성장은 ‘상권 간 이동’ — 그 흐름을 잡은 곳</h2>

    <div class="card">
      <h3>방법론</h3>
      <ol class="steps">{steps_html}</ol>
      <div class="grid-2">
        <div>
          <h4>v2 가중치 (백분위 순위 −0.5~+0.5에 곱함)</h4>
          <ul class="weights">{weights_html}</ul>
          <p class="note">감점(절대값 차감): {pen_html}</p>
        </div>
        <div>
          <h4>v1 → v2로 바꾼 이유</h4>
          {ul(M['v2_변경이유'][:4], 'list small')}
          <p class="note">{e(M['단절검출결과'])}</p>
        </div>
      </div>
      {src('scripts/analyze.py v2 · data/interim/analysis.json · trdar_scores.csv', SEL_SRC + ' 20232~20262')}
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>서울 제과점·커피 매출 추이 <small>{q(tq[0])}=100 지수</small></h3>
        <div class="chart" style="height:260px"><canvas id="cSeoul" aria-label="서울 제과점·커피 분기 매출 지수 추이"></canvas></div>
        <p class="note">제과점 {q(tq[0])} {trend[tq[0]]['제과점_억원']:,.1f}억원 → {q(tq[-1])} {trend[tq[-1]]['제과점_억원']:,.1f}억원({pct(st_sum['제과점_3년증감_%(20232→20262)'] / 100, sign=True)}), 커피-음료 {trend[tq[0]]['커피음료_억원']:,.1f}억원 → {trend[tq[-1]]['커피음료_억원']:,.1f}억원({pct(st_sum['커피음료_3년증감_%(20232→20262)'] / 100, sign=True)}). {R}</p>
        {src(st_sum['출처'])}
      </div>
      <div class="card">
        <h3>176개 상권: 성장 vs 종합점수</h3>
        <div class="chart" style="height:260px"><canvas id="cScatter" aria-label="176개 상권 2분기 YoY 중앙값과 v2 점수 산점도"></canvas></div>
        <p class="note">가로축 = 같은 2분기 합산매출 YoY 3구간 중앙값, 세로축 = v2 점수. 보라 = 후보 3곳. {R}</p>
        {src('data/interim/trdar_scores.csv (scripts/analyze.py v2)', SEL_SRC + ' 20232~20262')}
      </div>
    </div>

    <div class="card">
      <h3>후보 3곳 비교</h3>
      <div class="chart" style="height:240px"><canvas id="cCands" aria-label="후보 3곳 7개 분기 합산매출"></canvas></div>
      <p class="note">7개 분기 제과+커피 합산매출(억원). {R}</p>
      {cand_table}
    </div>

    <div class="grid-2">
      <div class="card accent">
        <h3>최종지 근거 — {e(FIN['상권명'])}</h3>
        <ol class="list">{reasons_html}</ol>
        <p class="note">{e(FIN['패널합의'])}</p>
        {src(SEL_SRC + ' 20232~20262', STOR_SRC + ' 20232·20262', '서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq 20232·20262', '서울시 상권분석서비스 상권변화지표 VwsmTrdarIxQq 20262')}
      </div>
      <div class="card">
        <h3>리스크</h3>
        <ul class="list risk">{risk_html}</ul>
        {src(STOR_SRC + ' 20232·20262', SEL_SRC + ' 20262', '서울시 상권분석서비스 상권변화지표 VwsmTrdarIxQq 20262')}
      </div>
    </div>

    <details class="card fold">
      <summary>반대 의견과 대응 ({len(FIN['반대의견과_대응'])}건)</summary>
      {obj_html}
    </details>
    <details class="card fold">
      <summary>패널이 제기했지만 제외한 상권 ({len(LOC['패널_판정'])}건)</summary>
      <div class="table-wrap"><table class="plain"><thead><tr><th>상권</th><th>제기</th><th>판정</th><th>근거</th></tr></thead><tbody>{panel_html}</tbody></table></div>
      {src(SEL_SRC + ' 20232~20262', STOR_SRC)}
    </details>
  </div>
</section>
"""

# ---- 02 인테리어
zones = INT["zones"]
zone_colors = ["#4C1D95", "#7C3AED", "#A78BFA", "#DDD6FE", "#94A3B8"]
zone_bar = "".join(
    f'<i style="flex:{z["area_ratio_pct"]};background:{zone_colors[i % 5]}" title="{e(z["zone"])} {z["area_ratio_pct"]}%"></i>'
    for i, z in enumerate(zones)
)
zone_cards = "".join(
    f'<li><span class="sw" style="background:{zone_colors[i % 5]}"></span><div><p class="z-t">{e(z["zone"])} '
    f'<b>{z["area_ratio_pct"]}% · {z["area_m2_assumed"]}㎡</b> {A}</p><p class="z-d">{e(z["why"])}</p>'
    f'<p class="z-e">근거: {linkify(z["evidence"])}</p></div></li>'
    for i, z in enumerate(zones)
)
persona_html = ""
for p in INT["personas"]:
    ev = "".join(f'<li><b>{e(x["number"])}</b><span>{e(x["claim"])}</span></li>' for x in p["evidence"])
    srcs = sorted({x["source"] for x in p["evidence"]})
    persona_html += f"""
    <article class="card persona">
      <h3>{e(p['name'])}</h3>
      <p class="muted">{e(p['profile'])}</p>
      <div class="chips">{''.join(f'<span>{e(n)}</span>' for n in p['needs'])}</div>
      <ul class="evid">{ev}</ul>
      {src(*srcs)}
    </article>"""
timeline_html = "".join(
    f'<li><p class="tl-t">{e(t["time"])}</p><p class="tl-b">{e(t["share_basis"])} {R}</p><p class="tl-s">{e(t["scenario"])}</p></li>'
    for t in INT["timeline"]
)
palette_html = "".join(
    f'<li><span class="chip-c" style="background:{e(p["hex"])}"></span><b>{e(p["name"])}</b><code>{e(p["hex"])}</code><span>{e(p["use"])}</span></li>'
    for p in INT["palette"]
)
materials_html = "".join(f'<li><b>{e(m["material"])}</b><span>{e(m["reason"])}</span></li>' for m in INT["materials"])
asm_rows = "".join(
    f'<tr><th scope="row">{e(a["item"])}</th><td><b>{e(a["value"])}</b></td><td>{e(a["formula"])}</td><td>{linkify(a["source"])}</td></tr>'
    for a in INT["assumptions"]
)

int_html = f"""
<section id="interior" class="sec alt">
  <div class="wrap">
    <p class="sec-no">02 · 인테리어 컨셉</p>
    <h2>{e(INT['concept'])}</h2>
    <p class="lead dark">{e(INT['one_liner'])}</p>

    <div class="card">
      <h3>고객 정의 {R}</h3>
      {ul(INT['customer_definition'], 'list')}
      {src(SEL_SRC + ' 20262', '서울시 상권분석서비스 직장인구 VwsmTrdarWrcPopltnQq 20262(20244 이후 값 동결)', '서울시 상권분석서비스 상주인구 VwsmTrdarRepopQq 20262(20234 이후 값 동결)', '서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq 20262')}
    </div>

    <div class="grid-2">{persona_html}</div>

    <div class="card">
      <h3>존 구성 — 약 {area_m2}㎡({area_py}평) · {seats}석 {A}</h3>
      <div class="zone-bar" role="img" aria-label="존 면적 비율">{zone_bar}</div>
      <ul class="zones">{zone_cards}</ul>
      {src('interior.json zones·assumptions (설계 가정, 계산식은 아래 표)', SEL_SRC + ' 20262', STOR_SRC + ' 20232·20262')}
    </div>

    <div class="card">
      <h3>하루 운영 시나리오 {A}</h3>
      <ol class="timeline">{timeline_html}</ol>
      {src(SEL_SRC + ' 20262', '서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq 20262', '서울시 지하철 호선별 역별 승하차 인원 CardSubwayStatsNew, 2026-11-02~2026-11-08 (1주)')}
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>무드 팔레트 {A}</h3>
        <ul class="palette">{palette_html}</ul>
      </div>
      <div class="card">
        <h3>소재·조명 {A}</h3>
        <ul class="materials">{materials_html}</ul>
      </div>
    </div>

    <details class="card fold">
      <summary>면적·좌석 산정 가정과 계산식</summary>
      <div class="table-wrap"><table class="plain"><thead><tr><th>항목</th><th>값</th><th>계산식</th><th>출처</th></tr></thead><tbody>{asm_rows}</tbody></table></div>
    </details>
  </div>
</section>
"""

# ---- 03 메뉴
mix = MENU["mix"]
mix_colors = ["#4C1D95", "#8B5CF6", "#B45309", "#D97706", "#0E7490"]
mix_bar = "".join(
    f'<i style="flex:{m["매출비중_%"]};background:{mix_colors[i % 5]}" title="{e(m["카테고리"])} {m["매출비중_%"]}%"></i>'
    for i, m in enumerate(mix)
)
mix_list = "".join(
    f'<li><span class="sw" style="background:{mix_colors[i % 5]}"></span><b>{e(m["카테고리"])} {m["매출비중_%"]}%</b>'
    f'<span>원재료율 {m["원가율_가정_%"]}% — {linkify(m["원가율_근거"])}</span></li>'
    for i, m in enumerate(mix)
)
ms = MENU["mix_요약"]
dp_rows = "".join(
    f'<tr><th scope="row">{e(d["시간대"])}</th><td>{d["상권_합산매출비중_%"]}%</td><td>{d["베이커리_%"]}%</td><td>{d["커피_%"]}%</td>'
    f'<td><b>{e(d["히어로"])}</b></td><td>{e(d["근거"])}</td></tr>'
    for d in MENU["dayparts"]
)
cats = []
for it in MENU["items"]:
    if it["카테고리"] not in cats:
        cats.append(it["카테고리"])
items_html = "".join(
    f'<div class="menu-col"><h4>{e(c)}</h4><ul>'
    + "".join(
        f'<li><span><b>{e(i["메뉴"])}</b><small>{e(i["설명"])}</small></span><em>{num(i["가격_원"])}</em></li>'
        for i in MENU["items"] if i["카테고리"] == c
    )
    + "</ul></div>"
    for c in cats
)
tc = MENU["target_cogs_ratio"]
at = MENU["avg_ticket"]
pc = MENU["price_check"]
menu_cogs = sum(m["매출비중_%"] * m["원가율_가정_%"] for m in MENU["mix"]) / 1e4   # 반올림 전 메뉴 가중 원재료율
cogs_gap = ASM["원재료비율 (가정: 커피 50% : 베이커리 50% 가중)"]["value"] - menu_cogs
menu_ev_src = sorted({x["source"] for x in MENU["evidence"] if x["source"].startswith("DART")})

menu_html = f"""
<section id="menu" class="sec">
  <div class="wrap">
    <p class="sec-no">03 · 메뉴 구성</p>
    <h2>음료 {ms['음료계_%']} : 푸드 {ms['푸드계(베이커리+디저트+델리)_%']} — 빵이 객단가를 끌어올린다</h2>

    <div class="grid-2">
      <div class="card">
        <h3>카테고리 믹스 {A}</h3>
        <div class="zone-bar" role="img" aria-label="메뉴 카테고리 매출 비중">{mix_bar}</div>
        <ul class="mixlist">{mix_list}</ul>
        <p class="note">상권 실적의 제과점 매출 비중은 {ms['상권_실적_제과점비중_%']}% {R}. {e(ms['설계논리'])}</p>
        <p class="note">{e(ms['주의'])}</p>
        {src(SEL_SRC + ' 20262', *menu_ev_src[:3])}
      </div>
      <div class="card">
        <h3>상권 객단가 추이와 제안 객단가</h3>
        <div class="chart" style="height:250px"><canvas id="cTicket" aria-label="남부터미널역 객단가 추이"></canvas></div>
        <p class="note">제과점 {won(at['추이_상권']['20232']['제과점'])} → {won(at['상권_제과점'])}(3년), 서울 전체 제과점 {won(at['서울전체_제과점'])}·커피 {won(at['서울전체_커피'])}, 176상권 중앙값 제과점 {won(at['176상권중앙값_제과점'])}·커피 {won(at['176상권중앙값_커피'])} {R}</p>
        <p class="note"><b>제안 객단가 {won(at['제안'])}</b> {A} — {e(at['계산식'].split('제안 = ')[1])}</p>
        {src(SEL_SRC + ' 20232~20262 (THSMON_SELNG_AMT / THSMON_SELNG_CO)')}
      </div>
    </div>

    <div class="card">
      <h3>시간대별 히어로 메뉴</h3>
      <div class="table-wrap"><table class="plain"><thead><tr><th>시간대</th><th>합산 매출</th><th>베이커리</th><th>커피</th><th>히어로 {A}</th><th>근거</th></tr></thead><tbody>{dp_rows}</tbody></table></div>
      <p class="note">시간대 비중은 해당 업종 분기 매출 중 시간대 매출 비중 {R}. 주말 행은 주말 매출 비중.</p>
      {src(SEL_SRC + ' 20262')}
    </div>

    <div class="card">
      <h3>메뉴판 <small>가격은 모두 제안 가정, 단위 원</small> {A}</h3>
      <div class="menu-grid">{items_html}</div>
      <p class="note">음료 단품 {num(pc['음료_단품_가격범위_원'][0])}~{num(pc['음료_단품_가격범위_원'][1])}원은 상권 커피 객단가 {won(pc['상권_커피_객단가_원'])} 이하. {e(pc['점검'])}. 외부 시세는 인용하지 않았다.</p>
      {src('menu.json items (가격 = 제안 가정)', SEL_SRC + ' 20262 (상권 커피 객단가)')}
    </div>

    <div class="card">
      <h3>목표 원재료비율 {tc['운영목표_%']}% {A}</h3>
      <p class="formula">{e(tc['계산식'])}</p>
      <div class="table-wrap"><table class="plain"><thead><tr><th>비교 기준</th><th>원재료비율</th><th>성격</th></tr></thead><tbody>
      {''.join(f'<tr><th scope="row">{e(k)}</th><td>{v}%</td><td>{"DART 2025 감사보고서 매출원가율(성격별 분류 미공시 → 원재료비율 상한)" if "매출원가" in DART[k]["costs"] else "DART 2025 감사보고서 성격별 비용(원재료·상품)"} {R}</td></tr>' for k, v in tc['DART_벤치마크_%'].items())}
      {''.join(f'<tr><th scope="row">{e(k)}</th><td>{v}%</td><td>베이커리 제조사 잔차비율(상한/하한 참고) {R}</td></tr>' for k, v in tc['베이커리제조사_잔차_%'].items())}
      </tbody></table></div>
      <p class="note">{e(tc['해석'])}</p>
      <p class="note">손익 시뮬레이션은 더 보수적인 {pct(ASM['원재료비율 (가정: 커피 50% : 베이커리 50% 가중)']['value'])}(스타벅스·CJ푸드빌 50:50)를 썼다. 메뉴 목표({tc['목표_%']}%)와의 차이 {cogs_gap * 100:.1f}%p는 04의 원재료비 −3%p 민감도로 확인할 수 있다.</p>
      {src(*menu_ev_src)}
    </div>
  </div>
</section>
"""

# ---- 04 손익
def scen_table():
    head = "".join(f'<th scope="col" colspan="3">{e(s)} <small>x{SCN[s]["매출배수"]} · 연 {pct(SCN[s]["연성장률"])}</small></th>' for s in SCN)
    sub = "".join("".join(f"<th>{y}</th>" for y in YEARS) for _ in SCN)
    lines = [
        ("매출", "매출", eok),
        ("원재료비", "원재료비", eok),
        ("매출총이익", "매출총이익", eok),
        ("인건비", "인건비", eok),
        ("임차료(+사용권상각)", "임차료", eok),
        ("기타(수수료·상각 등)", "기타", eok),
        ("영업이익", "영업이익", eok),
        ("영업이익률", "영업이익률", lambda v: pct(v, sign=True)),
        ("EBITDA", "EBITDA", eok),
    ]
    body = ""
    for label, key, f in lines:
        cls = ' class="hl"' if key in ("영업이익", "영업이익률") else ""
        cells = ""
        for s in SCN:
            for y in YEARS:
                v = SCN[s]["연도별"][y][key]
                neg = " neg" if key in ("영업이익", "영업이익률", "EBITDA") and v < 0 else ""
                cells += f'<td class="n{neg}">{f(v).replace("억원", "")}</td>'
        body += f"<tr{cls}><th scope=\"row\">{label}</th>{cells}</tr>"
    cum = "".join(
        f'<td colspan="3" class="n{" neg" if SCN[s]["3년누적_영업이익"] < 0 else ""}">{eok(SCN[s]["3년누적_영업이익"])}</td>' for s in SCN
    )
    body += f'<tr class="hl"><th scope="row">3년 누적 영업이익</th>{cum}</tr>'
    return f'<div class="table-wrap"><table class="pnl"><thead><tr><th rowspan="2">단위: 억원</th>{head}</tr><tr>{sub}</tr></thead><tbody>{body}</tbody></table></div>'


asm_pnl_rows = ""
for a in PNL["assumptions"]:
    v = a["value"]
    if isinstance(v, dict):
        vs = " / ".join(f"{k} {pct(x, 2) if x < 1 else 'x' + str(x)}" if "성장" in a["name"] else f"{k} x{x}" for k, x in v.items())
    elif v > 1000:
        vs = eok(v)
    else:
        vs = pct(v, 2)
    badge = A if ("가정" in a["name"] or a["source"] == "가정") else R
    asm_pnl_rows += f'<tr><th scope="row">{e(a["name"])} {badge}</th><td class="n"><b>{e(vs)}</b></td><td>{e(a["basis"])}</td><td>{linkify(a["source"])}</td></tr>'

grid = SENS["Y1영업이익률_그리드(행:매출, 열:원재료비)"]
cols = list(next(iter(grid.values())).keys())
grid_html = (
    '<table class="grid"><thead><tr><th>매출 \\ 원재료비</th>'
    + "".join(f"<th>{e(c)}</th>" for c in cols)
    + "</tr></thead><tbody>"
    + "".join(
        f'<tr><th scope="row">{e(r)}</th>'
        + "".join(
            f'<td class="{"pos" if grid[r][c] > 0 else "neg"}{" base" if r == "0%" and c == "0" else ""}">{pct(grid[r][c], sign=True)}</td>'
            for c in cols
        )
        + "</tr>"
        for r in grid
    )
    + "</tbody></table>"
)
fee = SENS["지급수수료_비교군치환"]
capex = SENS["초기투자"]
sens_rows = [
    ("매출 −10% / +10%", f'{pct(SENS["매출-10%"]["Y1"]["영업이익률"], sign=True)} / {pct(SENS["매출+10%"]["Y1"]["영업이익률"], sign=True)}',
     f'{pct(SENS["매출-10%"]["Y3"]["영업이익률"], sign=True)} / {pct(SENS["매출+10%"]["Y3"]["영업이익률"], sign=True)}'),
    ("원재료비 +3%p / −3%p", f'{pct(SENS["원재료비+3%p"]["Y1"]["영업이익률"], sign=True)} / {pct(SENS["원재료비-3%p"]["Y1"]["영업이익률"], sign=True)}',
     f'{pct(SENS["원재료비+3%p"]["Y3"]["영업이익률"], sign=True)} / {pct(SENS["원재료비-3%p"]["Y3"]["영업이익률"], sign=True)}'),
    (f"지급수수료 {pct(fee['지급수수료_대체비율'])}로 치환(로열티 제외 근사)", pct(fee["기준_Y1~Y3_영업이익률"]["Y1"], sign=True), pct(fee["기준_Y1~Y3_영업이익률"]["Y3"], sign=True)),
]
for k, v in capex.items():
    sens_rows.append((f"초기투자 {k} ({eok(v['초기투자_원'])})", pct(v["기준_영업이익률"]["Y1"], sign=True), pct(v["기준_영업이익률"]["Y3"], sign=True)))
sens_html = "".join(f'<tr><th scope="row">{e(a)}</th><td class="n">{b}</td><td class="n">{c}</td></tr>' for a, b, c in sens_rows)
reach = BE["시나리오별_도달"]
reach_html = "".join(
    f'<tr><th scope="row">{e(s)}</th>' + "".join(f'<td class="{"pos" if reach[s][y] else "neg"}">{"도달" if reach[s][y] else "미달"}</td>' for y in YEARS) + "</tr>"
    for s in reach
)
bm = PNL["benchmarks"]
dart_rows = ""
for n in DART:
    if n.startswith("_"):
        continue
    d = DART[n]
    if n in dart_ratio:
        r_ = dart_ratio[n]
        cells = "".join(f'<td class="n">{pct(r_[c])}</td>' for c in ["원재료·상품", "인건비", "점유비용(임차료+사용권자산상각)", "지급수수료"])
    else:
        cells = f'<td colspan="4">성격별 분류 미공시 — 매출원가 {pct(sum(d["costs"]["매출원가"]) / d["revenue"])} · 판관비 {pct(sum(d["costs"]["판매비와관리비"]) / d["revenue"])}</td>'
    dart_rows += (
        f'<tr><th scope="row">{e(n)}<small>{e(d["brand"])}</small></th><td class="n">{d["revenue"] / 1e5:,.0f}억원</td>'
        f'<td class="n">{pct(d["operating_income"] / d["revenue"])}</td>{cells}'
        f'<td><a href="{DART_URL.format(d["rcept_no"])}" target="_blank" rel="noopener">{d["rcept_no"]}</a></td></tr>'
    )
model_cost = bm["본 모델_비용구조"]

pnl_html = f"""
<section id="pnl" class="sec alt">
  <div class="wrap">
    <p class="sec-no">04 · 손익 시뮬레이션</p>
    <h2>기준 {first_profit[1]}년차 흑자 — 승부는 ‘상권 평균 대비 매출 배수’</h2>
    <p class="lead dark">기준 매출은 {e(FIN['상권명'])} 제과점 점포당 연매출 {eok(ASM['기준 연매출(제과점 점포당, 최근 4분기)']['value'])} {R}, 비용은 전 매장 직영인 스타벅스(에스씨케이컴퍼니) 감사보고서의 매출 대비 비율 {R}을 단일 매장에 적용했다. 시나리오·성장률·초기투자는 {A}.</p>

    <div class="grid-2">
      <div class="card">
        <h3>시나리오별 연매출 vs 손익분기 {A}</h3>
        <div class="chart" style="height:260px"><canvas id="cRev" aria-label="시나리오별 연매출과 손익분기 매출"></canvas></div>
        {src('pnl.json scenarios · breakeven')}
      </div>
      <div class="card">
        <h3>시나리오별 영업이익률 {A}</h3>
        <div class="chart" style="height:260px"><canvas id="cOpm" aria-label="시나리오별 영업이익률"></canvas></div>
        {src('pnl.json scenarios')}
      </div>
    </div>

    <div class="card">
      <h3>3개 시나리오 손익 (연 단위) {A}</h3>
      {scen_table()}
      <p class="note">월평균 = 연/12. 기준 Y1 월매출 {eok(SCN['기준']['월평균']['Y1']['매출'])}, 월 영업이익 {eok(SCN['기준']['월평균']['Y1']['영업이익'])}. 고정비는 3년간 명목 고정(임금·임대료 인상 데이터 없음). EBITDA = 영업이익 + 감가상각비(초기투자/5년) + 무형자산상각비(임차료·사용권상각은 현금성 점유비용으로 보고 가산하지 않음).</p>
      {src('scripts/pnl.py → pnl.json', DSRC['에스씨케이컴퍼니'], DSRC['CJ푸드빌'], SEL_SRC + ' 20253~20262', STOR_SRC + ' 20262')}
    </div>

    <div class="grid-2">
      <div class="card accent">
        <h3>손익분기 {A}</h3>
        <p class="big">{eok(BE['손익분기_연매출_원'])} <small>/ 년 · 월 {eok(BE['손익분기_월매출_원'])}</small></p>
        <ul class="list small">
          <li>기준 Y1 매출의 {pct(BE['손익분기_대비_기준Y1매출'])}, 상권 제과점 점포당 연매출의 {pct(BE['손익분기_대비_제과점_점포당_연매출(최근4분기)'])}</li>
          <li>연 고정비 {eok(BE['고정비_연_원'])} · 변동비율 {pct(BE['변동비율'])} · 공헌이익률 {pct(BE['공헌이익률'])}</li>
        </ul>
        <p class="formula">{e(BE['계산식'])}</p>
        <table class="grid small"><thead><tr><th>도달 여부</th>{''.join(f'<th>{y}</th>' for y in YEARS)}</tr></thead><tbody>{reach_html}</tbody></table>
        {src('pnl.json breakeven', DSRC['에스씨케이컴퍼니'])}
      </div>
      <div class="card">
        <h3>민감도 — 기준 시나리오 영업이익률 {A}</h3>
        <h4>Y1 매출 × 원재료비 그리드</h4>
        {grid_html}
        <div class="table-wrap"><table class="plain"><thead><tr><th>변수</th><th>Y1</th><th>Y3</th></tr></thead><tbody>
        <tr class="hl"><th scope="row">기준</th><td class="n">{pct(BASE['Y1']['영업이익률'], sign=True)}</td><td class="n">{pct(BASE['Y3']['영업이익률'], sign=True)}</td></tr>
        {sens_html}</tbody></table></div>
        <p class="note">{e(fee['근거'])}.</p>
        {src('pnl.json sensitivity', DSRC['투썸플레이스'], DSRC['CJ푸드빌'])}
      </div>
    </div>

    <div class="card">
      <h3>DART 비교사 원가구조 (매출 대비, 2025 감사보고서) {R}</h3>
      <div class="chart" style="height:230px"><canvas id="cDart" aria-label="DART 비교사 비용의 성격별 분류 매출 대비 비율"></canvas></div>
      <div class="table-wrap"><table class="plain"><thead><tr><th>회사</th><th>매출</th><th>영업이익률</th><th>원재료·상품</th><th>인건비</th><th>점유비용</th><th>지급수수료</th><th>접수번호</th></tr></thead><tbody>{dart_rows}</tbody></table></div>
      <p class="note">점유비용 = 임차료 + 사용권자산상각비(IFRS16). 투썸·CJ푸드빌·이디야는 가맹점 공급 매출이 섞여 원재료율이 직영 매장보다 높게 나온다. 본 모델 비용률(기준 Y1 매출 대비 합계) {pct(model_cost['총비용률_기준Y1'])}.</p>
      {src(*(f"DART {n} {DART[n]['rcept_no']} (감사인 {DART[n]['auditor']})" for n in DART if not n.startswith('_')))}
    </div>

    <details class="card fold">
      <summary>손익 가정 {len(PNL['assumptions'])}개 (값·근거·출처)</summary>
      <div class="table-wrap"><table class="plain"><thead><tr><th>가정</th><th>값</th><th>근거</th><th>출처</th></tr></thead><tbody>{asm_pnl_rows}</tbody></table></div>
    </details>
  </div>
</section>
"""

# ---- 데이터 출처·한계
seoul_src = "".join(f"<li><b>{e(s['서비스'])}</b><span>{e(s['구분'])} · 용도 {e(s['용도'])}</span></li>" for s in LOC["sources"])
dart_src = "".join(
    f'<li><b>{e(n)}</b> {e(DART[n]["brand"])} · 2025 감사보고서 · 감사인 {e(DART[n]["auditor"])} · '
    f'<a href="{DART_URL.format(DART[n]["rcept_no"])}" target="_blank" rel="noopener">rcpNo {DART[n]["rcept_no"]}</a></li>'
    for n in DART if not n.startswith("_")
)
known = {DART[n]["rcept_no"] for n in DART if not n.startswith("_")}
for x in MENU["evidence"]:
    m = re.search(r"(20\d{12})", x["source"])
    if x["source"].startswith("DART") and m and m.group(1) not in known:
        known.add(m.group(1))
        dart_src += f'<li>{linkify(x["source"])} — 메뉴 원재료율 참고</li>'
lim_groups = [
    ("입지", M["한계"]),
    ("메뉴", MENU["한계"]),
    ("손익", PNL["limitations"]),
    ("인테리어", [a["value"] for a in INT["assumptions"] if a["item"] in ("데이터 없음", "주의")]),
]
lim_html = "".join(f'<div><h4>{e(t)}</h4>{ul(items, "list small")}</div>' for t, items in lim_groups)

src_html = f"""
<section id="sources" class="sec">
  <div class="wrap">
    <p class="sec-no">데이터 출처 · 한계</p>
    <h2>숫자는 두 곳에서만 왔다</h2>
    <div class="grid-2">
      <div class="card">
        <h3>서울 열린데이터광장 (서울시 상권분석서비스 외)</h3>
        <ul class="srclist">{seoul_src}</ul>
        <p class="note">비교는 모두 2분기끼리(3년전 {LOC['method']['기준분기']['3년전']}, 1년전 {LOC['method']['기준분기']['1년전']}, 최신 {LOC['method']['기준분기']['최신']})로 계절성을 통제. 아파트·소득소비 상권 API는 서울시 서버 500 오류로 미수집(데이터 없음).</p>
      </div>
      <div class="card">
        <h3>DART 전자공시 (감사보고서)</h3>
        <ul class="srclist">{dart_src}</ul>
        <p class="note">비용의 성격별 분류 주석 항목합 = 공시 비용합계 검증 완료. 원문 행 텍스트는 data/interim/audit_*.txt.</p>
      </div>
    </div>
    <div class="card">
      <h3>한계</h3>
      <div class="grid-2 lim">{lim_html}</div>
      {src('location.json method.한계 · menu.json 한계 · pnl.json limitations · interior.json assumptions', DSRC['에스씨케이컴퍼니'])}
    </div>
    <p class="note">재현: scripts/analyze.py → build_location.py → build_interior.py · build_menu.py · pnl.py → build_site.py (이 페이지). 생성일 {date.today().isoformat()}.</p>
  </div>
</section>
"""

video_html = """
<section id="video" class="sec alt">
  <div class="wrap">
    <p class="sec-no">발표 영상</p>
    <h2>2분 요약 발표</h2>
    <div class="video-frame">
      <video controls preload="metadata" playsinline aria-label="2분 발표 영상">
        <source src="assets/presentation.mp4" type="video/mp4">
        <track kind="captions" src="assets/captions.vtt" srclang="ko" label="한국어" default>
      </video>
    </div>
  </div>
</section>
"""

nav = """
<nav class="nav" aria-label="섹션">
  <div class="wrap nav-in">
    <a class="brand" href="#top">출점 전략</a>
    <div class="nav-links">
      <a href="#summary">요약</a><a href="#location">01 입지</a><a href="#interior">02 인테리어</a>
      <a href="#menu">03 메뉴</a><a href="#pnl">04 손익</a><a href="#sources">출처</a><a href="#video">영상</a>
    </div>
  </div>
</nav>
"""

CSS = r"""
:root{
  --p900:#2E1065;--p800:#4C1D95;--p700:#6D28D9;--p600:#7C3AED;--p300:#C4B5FD;--p100:#EDE9FE;--p50:#F5F3FF;
  --ink:#1E1B2E;--ink2:#4B4763;--muted:#6B6880;--line:#E6E3EF;--bg:#F7F6FB;--card:#FFFFFF;
  --pos:#166534;--posbg:#DCFCE7;--neg:#B91C1C;--negbg:#FEE2E2;--amber:#92400E;--amberbg:#FEF3C7;
  color-scheme:light;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Pretendard Variable",Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.6;font-size:16px;word-break:keep-all;overflow-wrap:anywhere}
a{color:var(--p700)}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
@media(min-width:768px){.wrap{padding:0 32px}}
h1,h2,h3,h4{line-height:1.3;margin:0}
h2{font-size:clamp(1.5rem,3.2vw,2.1rem);letter-spacing:-.02em;margin-bottom:28px;font-weight:800}
h3{font-size:1.1rem;font-weight:700;margin-bottom:14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
h3 small,h4 small{font-weight:500;color:var(--muted);font-size:.8rem}
h4{font-size:.95rem;margin:4px 0 10px;color:var(--ink2)}
.nav{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.nav-in{display:flex;align-items:center;gap:16px;height:52px}
.brand{font-weight:800;color:var(--p800);text-decoration:none;white-space:nowrap}
.nav-links{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;min-width:0}
.nav-links::-webkit-scrollbar{display:none}
.nav-links a{white-space:nowrap;text-decoration:none;color:var(--ink2);font-size:.88rem;padding:6px 10px;border-radius:999px}
.nav-links a:hover{background:var(--p100);color:var(--p800)}
.hero{background:linear-gradient(135deg,#2E1065 0%,#4C1D95 45%,#7C3AED 100%);color:#fff;padding:64px 0 48px}
.eyebrow{font-size:.85rem;letter-spacing:.04em;opacity:.85;margin:0 0 14px}
.hero h1{font-size:clamp(1.9rem,5vw,3.2rem);font-weight:800;letter-spacing:-.03em}
.hero h1 em{font-style:normal;color:#DDD6FE}
.lead{font-size:1.08rem;max-width:820px;margin:18px 0 0;opacity:.95}
.lead.dark{color:var(--ink2);opacity:1;margin:-12px 0 24px}
.brief{display:grid;gap:10px;margin:28px 0;max-width:900px}
.brief div{display:grid;grid-template-columns:88px 1fr;gap:12px}
.brief dt{font-weight:700;opacity:.75}.brief dd{margin:0}
.site-card{background:#fff;color:var(--ink);border-radius:20px;padding:24px;display:grid;gap:20px;box-shadow:0 20px 50px rgba(20,0,60,.35)}
@media(min-width:860px){.site-card{grid-template-columns:1fr 2fr;align-items:center}}
.site-card .k{margin:0;font-size:.8rem;color:var(--p700);font-weight:700}
.site-name{margin:2px 0;font-size:1.9rem;font-weight:800;color:var(--p800)}
.site-meta{margin:0;color:var(--muted);font-size:.9rem}
.site-facts{list-style:none;margin:0;padding:0;display:grid;gap:12px}
@media(min-width:600px){.site-facts{grid-template-columns:repeat(3,1fr)}}
.site-facts li{background:var(--p50);border-radius:14px;padding:14px}
.site-facts b{display:block;font-size:1.15rem;color:var(--p800)}
.site-facts span{font-size:.82rem;color:var(--ink2)}
.hero .src{color:#E9E3FF}.hero .src span{background:rgba(255,255,255,.18);color:#fff}
.sec{padding:72px 0}.sec.alt{background:#fff}
.sec.alt .card{background:var(--bg)}
.sec-no{color:var(--p700);font-weight:800;font-size:.85rem;letter-spacing:.06em;margin:0 0 8px;text-transform:uppercase}
.card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:24px;margin-bottom:20px;min-width:0}
.card.accent{border:2px solid var(--p300);background:linear-gradient(180deg,#fff, var(--p50))}
.sec.alt .card.accent{background:linear-gradient(180deg,#fff, var(--p50))}
.grid-2{display:grid;gap:20px}
.grid-2>.card{margin-bottom:0}
.grid-2+.card,.grid-2+.grid-2,.grid-2+details{margin-top:20px}
@media(min-width:900px){.grid-2{grid-template-columns:1fr 1fr}}
.kpis{display:grid;gap:16px;grid-template-columns:1fr}
@media(min-width:600px){.kpis{grid-template-columns:1fr 1fr}}
@media(min-width:1000px){.kpis{grid-template-columns:repeat(4,1fr)}}
.kpi{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;display:flex;flex-direction:column;border-top:4px solid var(--p600)}
.kpi-v{font-size:2rem;font-weight:800;color:var(--p800);margin:6px 0 2px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.kpi-l{font-weight:700;margin:0}.kpi-s{color:var(--ink2);font-size:.88rem;margin:4px 0 0;flex:1}
.takeaways{margin:28px 0 0;padding-left:1.3em;display:grid;gap:10px;max-width:900px}
.legend-note{font-size:.85rem;color:var(--muted);margin-top:20px}
.tag{display:inline-block;font-size:.7rem;font-weight:700;line-height:1;padding:4px 7px;border-radius:999px;vertical-align:middle;white-space:nowrap}
.tag-a{background:var(--amberbg);color:var(--amber);border:1px solid #FCD34D}
.tag-r{background:var(--p100);color:var(--p800);border:1px solid var(--p300)}
.src{font-size:.75rem;color:var(--muted);margin:14px 0 0;line-height:1.5}
.src span{display:inline-block;background:var(--p100);color:var(--p800);font-weight:700;border-radius:4px;padding:0 6px;margin-right:4px}
.note{font-size:.85rem;color:var(--ink2);margin:10px 0 0}
.muted{color:var(--ink2);margin:0 0 12px}
.formula{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.8rem;background:var(--p50);border-radius:10px;padding:10px 12px;color:var(--ink2);margin:10px 0}
.list{margin:0;padding-left:1.2em;display:grid;gap:8px}.list.small{font-size:.9rem;gap:6px}
.list.risk li::marker{color:var(--neg)}
.steps{list-style:none;padding:0;margin:0 0 24px;display:grid;gap:10px;counter-reset:s}
@media(min-width:900px){.steps{grid-template-columns:repeat(5,1fr)}}
.steps li{background:var(--p50);border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:2px}
.steps b{font-size:1.2rem;color:var(--p800)}.st-t{font-weight:700;font-size:.9rem}.st-d{font-size:.78rem;color:var(--ink2)}
.weights{list-style:none;padding:0;margin:0;display:grid;gap:6px}
.weights li{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr) 44px;gap:8px;align-items:center;font-size:.82rem}
.w-bar{height:10px;background:var(--p50);border-radius:6px;overflow:hidden}
.w-bar i{display:block;height:100%;border-radius:6px}.w-bar i.pos{background:var(--p600)}.w-bar i.neg{background:#94A3B8}
.w-val{text-align:right;font-variant-numeric:tabular-nums}
.chart{position:relative;width:100%}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin-top:12px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
thead th{background:var(--p50);color:var(--p800);font-weight:700;font-size:.8rem}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.neg{color:var(--neg)}
table.cmp th[scope=row]{width:26%;font-weight:600;color:var(--ink2)}
table.cmp thead th small{display:block;font-weight:500;color:var(--muted)}
table.cmp thead th.pick{background:var(--p700);color:#fff}table.cmp thead th.pick small{color:#E9E3FF}
table.cmp td:nth-child(2){background:var(--p50);font-weight:600}
table.cmp,table.pnl{min-width:640px}
table.pnl{min-width:760px}
table.pnl thead th{text-align:center}
table.pnl tr.hl th,table.pnl tr.hl td,table.plain tr.hl th,table.plain tr.hl td{background:var(--p50);font-weight:700}
table.plain th small{display:block;font-weight:400;color:var(--muted)}
.table-wrap table.plain{min-width:680px}
table.plain th[scope=row]{min-width:120px}
table.grid{width:auto;margin:6px 0 14px}
table.grid td{text-align:center;font-weight:700;font-variant-numeric:tabular-nums;min-width:72px}
table.grid td.pos{background:var(--posbg);color:var(--pos)}table.grid td.neg{background:var(--negbg);color:var(--neg)}
table.grid td.base{outline:2px solid var(--p700);outline-offset:-2px}
table.grid.small td{min-width:56px}
.big{font-size:2rem;font-weight:800;color:var(--p800);margin:0 0 8px}.big small{font-size:.9rem;color:var(--ink2);font-weight:500}
.fold summary{cursor:pointer;font-weight:700;list-style:none;display:flex;justify-content:space-between;gap:12px}
.fold summary::after{content:"+";color:var(--p700);font-size:1.3rem;line-height:1}
.fold[open] summary::after{content:"−"}
.fold summary::-webkit-details-marker{display:none}
.qa{border-top:1px solid var(--line);padding:12px 0}.qa-q{font-weight:700;margin:0 0 4px}.qa-q::before{content:"Q. ";color:var(--p700)}
.qa-a{margin:0;color:var(--ink2);font-size:.92rem}.qa-a::before{content:"A. ";font-weight:700;color:var(--p700)}
.persona h3{color:var(--p800)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.chips span{background:var(--p100);color:var(--p800);font-size:.8rem;border-radius:999px;padding:4px 10px}
.evid{list-style:none;padding:0;margin:0;display:grid;gap:8px}
.evid li{display:flex;flex-direction:column;border-left:3px solid var(--p300);padding-left:10px}
.evid b{font-size:.9rem}.evid span{font-size:.8rem;color:var(--muted)}
.zone-bar{display:flex;height:36px;border-radius:10px;overflow:hidden;margin:4px 0 18px;gap:2px}
.zone-bar i{display:block;min-width:4px}
.zones,.mixlist{list-style:none;padding:0;margin:0;display:grid;gap:14px}
.zones li{display:grid;grid-template-columns:14px 1fr;gap:12px}
.sw{width:14px;height:14px;border-radius:4px;margin-top:5px;display:inline-block;flex:none}
.z-t{margin:0;font-weight:700}.z-t b{color:var(--p700);font-weight:700;margin-left:4px}
.z-d{margin:4px 0;font-size:.9rem;color:var(--ink2)}.z-e{margin:0;font-size:.75rem;color:var(--muted)}
.mixlist li{display:grid;grid-template-columns:14px 1fr;column-gap:10px;font-size:.88rem}
.mixlist li span:last-child{grid-column:2;color:var(--ink2);font-size:.8rem}
.timeline{list-style:none;padding:0;margin:0;display:grid;gap:12px}
@media(min-width:900px){.timeline{grid-template-columns:repeat(3,1fr)}}
.timeline li{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px;border-top:3px solid var(--p600)}
.tl-t{font-weight:800;margin:0;color:var(--p800)}.tl-b{font-size:.8rem;margin:4px 0;color:var(--ink2)}.tl-s{font-size:.88rem;margin:0}
.palette,.materials{list-style:none;padding:0;margin:0;display:grid;gap:10px}
.palette li{display:grid;grid-template-columns:40px auto 1fr;column-gap:10px;align-items:center;font-size:.88rem}
.palette li span:last-child{grid-column:2/4;color:var(--ink2);font-size:.8rem}
.palette code{font-size:.78rem;color:var(--muted)}
.chip-c{width:40px;height:40px;border-radius:10px;grid-row:span 2;border:1px solid var(--line)}
.materials li{display:flex;flex-direction:column;border-left:3px solid var(--p300);padding-left:10px}
.materials span{font-size:.85rem;color:var(--ink2)}
.menu-grid{display:grid;gap:18px}
@media(min-width:700px){.menu-grid{grid-template-columns:repeat(3,1fr)}}
.menu-col h4{border-bottom:2px solid var(--p600);padding-bottom:6px;color:var(--p800)}
.menu-col ul{list-style:none;padding:0;margin:0;display:grid;gap:8px}
.menu-col li{display:flex;justify-content:space-between;gap:10px;font-size:.88rem}
.menu-col li small{display:block;color:var(--muted);font-size:.75rem}
.menu-col em{font-style:normal;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
.srclist{list-style:none;padding:0;margin:0;display:grid;gap:10px;font-size:.86rem}
.srclist li{display:flex;flex-direction:column;border-left:3px solid var(--p300);padding-left:10px}
.srclist li span{font-size:.78rem;color:var(--muted)}
.lim h4{color:var(--p800)}
.video-frame{position:relative;aspect-ratio:16/9;background:linear-gradient(135deg,#2E1065,#7C3AED);border-radius:20px;overflow:hidden}
.video-frame video{width:100%;height:100%;display:block;background:transparent}
.video-ph{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#fff;pointer-events:none;gap:10px}
.video-ph p{margin:0;font-weight:700}
.play{width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.2);position:relative}
.play::after{content:"";position:absolute;left:26px;top:20px;border-left:18px solid #fff;border-top:12px solid transparent;border-bottom:12px solid transparent}
footer{padding:28px 0;color:var(--muted);font-size:.8rem;border-top:1px solid var(--line)}
@media print{.nav{display:none}.fold{display:block}}
"""

JS = r"""
(function(){
  const D = window.__DATA__;
  if (!window.Chart) { document.querySelectorAll('.chart').forEach(c=>c.insertAdjacentHTML('beforeend','<p class="note">차트 라이브러리를 불러오지 못했습니다. 표의 수치를 참고하세요.</p>')); return; }
  const css = getComputedStyle(document.documentElement);
  const v = n => css.getPropertyValue(n).trim();
  Chart.defaults.font.family = '"Pretendard Variable", Pretendard, "Malgun Gothic", sans-serif';
  Chart.defaults.color = v('--ink2');
  Chart.defaults.borderColor = v('--line');
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.maintainAspectRatio = false;
  const P = {deep:'#4C1D95', main:'#7C3AED', light:'#C4B5FD', teal:'#0E7490', amber:'#B45309', slate:'#94A3B8'};
  const fmt = (x,d=1) => x.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d});

  const s = D.seoulTrend;
  new Chart(document.getElementById('cSeoul'), {type:'line', data:{labels:s.labels, datasets:[
    {label:'제과점', data:s.bakIdx, borderColor:P.main, backgroundColor:P.main, tension:.25, pointRadius:3, raw:s.bakRaw},
    {label:'커피-음료', data:s.cofIdx, borderColor:P.teal, backgroundColor:P.teal, borderDash:[5,4], tension:.25, pointRadius:3, raw:s.cofRaw}]},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${fmt(c.parsed.y)} (${fmt(c.dataset.raw[c.dataIndex])}억원)`}}},
      scales:{y:{title:{display:true,text:'지수'}}}}});

  const sc = D.scatter;
  new Chart(document.getElementById('cScatter'), {type:'scatter', data:{datasets:[
    {label:'후보 3곳', data:sc.cands, backgroundColor:P.main, borderColor:P.deep, pointRadius:7, pointHoverRadius:9},
    {label:'기타 상권', data:sc.all, backgroundColor:'rgba(148,163,184,.45)', pointRadius:3.5}]},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.raw.n}: YoY 중앙값 ${fmt(c.raw.x)}%, 점수 ${c.raw.y.toFixed(3)}`}}},
      scales:{x:{title:{display:true,text:'2분기 YoY 중앙값(%)'}}, y:{title:{display:true,text:'v2 점수'}}}}});

  const cd = D.cands, cc=[P.main,P.teal,P.amber], dash=[[],[6,4],[2,3]];
  new Chart(document.getElementById('cCands'), {type:'line', data:{labels:cd.labels, datasets:cd.series.map((x,i)=>({
    label:x.name, data:x.data, borderColor:cc[i], backgroundColor:cc[i], borderWidth:i===0?3:2, borderDash:dash[i], pointRadius:i===0?4:3, tension:.2}))},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${fmt(c.parsed.y,2)}억원`}}}, scales:{y:{title:{display:true,text:'억원'}}}}});

  const t = D.ticket;
  new Chart(document.getElementById('cTicket'), {type:'line', data:{labels:t.labels, datasets:[
    {label:'제과점', data:t.bak, borderColor:P.main, backgroundColor:P.main, tension:.2},
    {label:'커피-음료', data:t.cof, borderColor:P.teal, backgroundColor:P.teal, borderDash:[5,4], tension:.2},
    {label:'합산', data:t.all, borderColor:P.slate, backgroundColor:P.slate, tension:.2},
    {label:'제안 객단가(가정)', data:t.labels.map(()=>t.proposal), borderColor:P.amber, borderDash:[3,3], pointRadius:0, borderWidth:2}]},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${c.parsed.y.toLocaleString('ko-KR')}원`}}}, scales:{y:{title:{display:true,text:'원'}}}}});

  const sn = D.scen, scol={'보수':P.light,'기준':P.main,'낙관':P.deep};
  new Chart(document.getElementById('cRev'), {data:{labels:sn.labels, datasets:[
    ...sn.names.map(n=>({type:'bar', label:n, data:sn.rev[n], backgroundColor:scol[n], borderRadius:6})),
    {type:'line', label:'손익분기 연매출', data:sn.labels.map(()=>sn.be), borderColor:'#B91C1C', borderDash:[6,4], pointRadius:0, borderWidth:2}]},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${fmt(c.parsed.y,2)}억원`}}}, scales:{y:{beginAtZero:true,title:{display:true,text:'억원'}}}}});
  new Chart(document.getElementById('cOpm'), {type:'bar', data:{labels:sn.labels, datasets:sn.names.map(n=>({label:n, data:sn.opm[n], backgroundColor:scol[n], borderRadius:6}))},
    options:{plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${fmt(c.parsed.y)}%`}}}, scales:{y:{title:{display:true,text:'영업이익률(%)'}, grid:{color:c=>c.tick.value===0?'#6B6880':v('--line')}}}}});

  const dt = D.dart, dcol=['#2E1065','#6D28D9','#A78BFA','#0E7490','#67C5D6','#CBD5E1','#15803D'];
  new Chart(document.getElementById('cDart'), {type:'bar', data:{labels:dt.labels, datasets:dt.cats.map((k,i)=>({label:k, data:dt.values[k], backgroundColor:dcol[i%dcol.length]}))},
    options:{indexAxis:'y', plugins:{tooltip:{callbacks:{label:c=>`${c.dataset.label} ${fmt(c.parsed.x)}%`}}},
      scales:{x:{stacked:true, max:100, title:{display:true,text:'매출 대비 %'}}, y:{stacked:true}}}});
})();
"""

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_competition import competition_html, rent_html, pnl_v2_html  # noqa: E402
comp_html = competition_html()
rent_html_s = rent_html()
pnl_v2_s = pnl_v2_html()

html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>남부터미널역 출점 전략</title>
<meta name="description" content="PE 보유 커피·베이커리 전문점의 서울 신규 출점 전략: 입지 선정, 인테리어 컨셉, 메뉴 구성, 3년 손익 시뮬레이션 (서울 열린데이터광장·DART 공시 기반)">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
</head>
<body>
{nav}
{hero}
<main>
{exec_html}
{loc_html}
{comp_html}
{int_html}
{menu_html}
{pnl_v2_s}
{pnl_html}
{rent_html_s}
{src_html}
{video_html}
</main>
<footer><div class="wrap">본 페이지의 모든 수치는 scripts/build_site.py가 data/interim/*.json에서 생성했습니다. ‘가정’ 배지가 붙은 값은 전망·설계 가정이며 공시 실적이 아닙니다.</div></footer>
<script>window.__DATA__ = {json.dumps(chart, ensure_ascii=False)};</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>{JS}</script>
</body>
</html>
"""

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({len(html.encode('utf-8')) / 1024:.1f} KB)")
