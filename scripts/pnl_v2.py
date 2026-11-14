# -*- coding: utf-8 -*-
"""신규 직영 1호점(남부터미널역) 3년 손익 v2 — 매출 기준을 '브랜드 직영 베이커리 매장 수준'으로 재보정.

v1(scripts/pnl.py → pnl.json)은 상권 '제과점 점포당 평균 매출'(개인 빵집 포함, 3.30억원/년)을 매출 기준으로 써서
기준 시나리오가 손익분기 미달이었다. v2는 공시·공공데이터 3개 방법으로 매출을 삼각검증하고
비용은 bakery_benchmark.json 의 '베이커리 직영 기준 비용 비율'로 바꾼다.

입력(읽기만):
  data/interim/location_v2.json      입지 재검증 결과(scripts/location_v2.py 먼저 실행)
  data/interim/location.json         성장률 가정(3년후_전망)
  data/interim/competition.json      500m 업소 면적·유형, 브랜드 서울 중앙 면적
  data/interim/bakery_benchmark.json DART 베이커리 벤치마크·proposed_cost_ratios
  data/interim/pnl.json              v1 결과(비교용)
  data/interim/menu.json, interior.json  객단가 제안·면적 산식(면적 정합성 체크용)
  data/interim/audit_보나비_20260403003616.txt  유형자산 변동표·보증금(초기투자 추정)
출력: data/interim/pnl_v2.json
실행: PYTHONIOENCODING=utf-8 python scripts/location_v2.py && PYTHONIOENCODING=utf-8 python scripts/pnl_v2.py
"""
import json
import os
import re
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
SVC = "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq"
SVC_ST = "서울시 상권분석서비스 점포 VwsmTrdarStorQq"
LIC = "서울시 제과점영업 인허가(LOCALDATA_072218)·휴게음식점 인허가(LOCALDATA_072405), competition.json 경유"


def load(*a):
    with open(P(*a), encoding="utf-8") as f:
        return json.load(f)


loc2 = load("data", "interim", "location_v2.json")
loc = load("data", "interim", "location.json")
comp = load("data", "interim", "competition.json")
bb = load("data", "interim", "bakery_benchmark.json")
v1 = load("data", "interim", "pnl.json")
menu = load("data", "interim", "menu.json")
interior = load("data", "interim", "interior.json")

TRDAR = loc2["final"]["TRDAR_CD"]
nb = next(r for r in loc2["candidates"] if r["TRDAR_CD"] == TRDAR)
nb_comp = next(c for c in comp["candidates"] if c["TRDAR_CD"] == TRDAR)
cand_v1 = next(c for c in loc["candidates"] if c["TRDAR_CD"] == TRDAR)
CO = bb["companies"]
src = lambda n: f"DART {n} 감사보고서 rcpNo {CO[n]['rcpNo']} ({DART.format(CO[n]['rcpNo'])})"

eok = lambda x: f"{x / 1e8:,.2f}억원"
A = []


def add(name, value, basis, source):
    A.append({"name": name, "value": value, "basis": basis, "source": source})


# =========================================================== 0. 포맷 면적(가정)
area_artisee = comp["brand_dictionary"]["트렌드/프리미엄"]["아티제"]["중앙면적_m2"]   # 108.4
AREA = 108.0
add("매장 면적 (가정)", AREA,
    f"아티제 서울 인허가 중앙 면적 {area_artisee}㎡를 반올림. 매출 앵커인 보나비(아티제) 점포당 매출과 같은 크기로 맞춤. "
    f"경쟁 지도상 남부터미널 500m 업소 평균 {nb_comp['평균면적_m2']['500m']}㎡, 직접 경쟁 아방베이커리 서초점 174.11㎡.",
    f"{LIC}")

# =========================================================== 1. 매출 삼각검증
mkt_bak = nb["제과점_연매출_최근4분기_원"]                     # 4개 분기 합(20253~20262)
n_similr = nb["점포_20262"]["SIMILR_INDUTY_STOR_CO"]
per_store_mkt = mkt_bak / n_similr

# 방법 A — DART 직영 브랜드 점포당 매출
bon = CO["보나비"]
bon_rev = bon["fy2025"]["revenue"]
bon_n = bon["stores"]["count"]
bon_ps = bon_rev / bon_n
bon_ps_area = bon_ps / area_artisee * AREA
ros = CO["로쏘"]
ros_ps = ros["fy2025"]["revenue"] / ros["stores"]["count"]
M_A = bon_ps_area

# 방법 B — 상권 내 상위권(대형·트렌드 브랜드) 매장 추정
stores500 = nb_comp["stores_list"]
brand = [s for s in stores500 if s["유형"] in ("대형 프랜차이즈", "트렌드/프리미엄")]
area_all = sum(s["면적m2"] for s in stores500)
area_brand = sum(s["면적m2"] for s in brand)
brand_share = area_brand / area_all                              # 가정: 매출 비중 = 면적 비중
M_B_per_brand = mkt_bak * brand_share / len(brand)
M_B = M_B_per_brand / (area_brand / len(brand)) * AREA          # 108㎡ 환산

# 방법 C — 상권 추정매출 중 확보 가능 점유율
et = loc2["competition"]["프리미엄진입_전후검정"]
obs_inc = et["연환산_순증_원"]
SHARE_BASE = round(obs_inc / mkt_bak, 2)                         # 관측 순증 / 현재 연매출 ≈ 0.22
M_C = mkt_bak * SHARE_BASE

tri = {
    "단위": "원/년, 개점 전 기준기간(2025Q3~2026Q2) 수준. 시나리오 Y1은 여기에 1년 성장 적용",
    "방법A_DART_직영브랜드_점포당매출": {
        "값_원": M_A,
        "계산": f"보나비 2025 매출 {bon_rev:,}원 ÷ 매장 {bon_n}곳(아티제 67 + 쿠차라 10) = {bon_ps:,.0f}원/점 → 아티제 서울 중앙 면적 {area_artisee}㎡ 대비 {AREA}㎡ 환산 = {M_A:,.0f}원",
        "출처": src("보나비") + "; " + LIC,
        "참고_상한(채택안함)": {"로쏘(성심당) 점포당": ros_ps, "이유": "대전 본점(자가)·초대형 매장 포함 16곳 평균이라 신규 1호점 기준으로 비현실적. 출처 " + src("로쏘")},
        "해석": "서울 중심 임차 직영 베이커리카페 77곳의 실적 평균. 브랜드 인지가 이미 있는 회사 수준이라 신규 브랜드 1호점에는 '낙관'.",
    },
    "방법B_상권_상위권매장_추정": {
        "값_원": M_B,
        "계산": f"상권 제과점 연매출(최근 4분기) {mkt_bak:,.0f}원 × 대형·트렌드 브랜드 매출 비중(가정 = 500m 인허가 면적 비중 {area_brand:,.1f}/{area_all:,.1f}㎡ = {brand_share:.3f}) ÷ 브랜드 매장 {len(brand)}곳 = {M_B_per_brand:,.0f}원/점(평균 {area_brand / len(brand):.1f}㎡) → {AREA}㎡ 환산 {M_B:,.0f}원",
        "브랜드매장": [f"{s['상호']} {s['면적m2']}㎡" for s in brand],
        "출처": f"{SVC} 제과점 20253·20254·20261·20262 (TRDAR_CD {TRDAR}); {LIC}",
        "가정": "면적당 매출이 개인·브랜드 매장 모두 같다(브랜드 프리미엄 0). 500m 원과 상권 폴리곤 경계가 다름(근사).",
        "해석": "상권 평균 생산성만 반영한 '보수' — 브랜드 집객력이 전혀 없을 때의 매출.",
    },
    "방법C_상권매출_확보점유율": {
        "값_원": M_C,
        "계산": f"상권 제과점 연매출 {mkt_bak:,.0f}원 × 확보 점유율 {SHARE_BASE:.2f} (가정)",
        "점유율_근거": f"아방베이커리 서초점 등 3곳 진입(2025-11~2026-03) 뒤 상권 제과점 분기매출 {et['진입전_분기평균_원(20252·20253)']:,.0f} → {et['진입후_분기평균_원(20261·20262)']:,.0f}원, 연환산 순증 {obs_inc:,.0f}원 = 현재 연매출의 {obs_inc / mkt_bak:.3f}. 동분기 YoY {et['계절성_통제_동분기YoY(20252→20262)']:.3f} vs 서울 제과점시장 {et['서울_제과점시장_동분기YoY(20252→20262)']:.3f}. 같은 크기의 수요가 한 번 더 남아 있다고 보는 것은 '가정'.",
        "출처": f"{SVC} 제과점 20252·20253·20261·20262 (TRDAR_CD {TRDAR}); location.json seoul_trend",
        "해석": "관측된 '진입 1회분 시장 확대'를 신규 매장 매출로 쓴 중간값.",
    },
}
vals = {"A": M_A, "B": M_B, "C": M_C}
mid = st.median(vals.values())
tri["종합"] = {
    "보수_앵커": "B", "기준_앵커": "C (세 방법 중앙값)", "낙관_앵커": "A",
    "범위_원": [min(vals.values()), max(vals.values())], "중앙값_원": mid,
    "v1_기준(상권 점포당 평균, 4분기합/SIMILR 11)": per_store_mkt,
    "기준/v1": mid / per_store_mkt,
    "판단": "기준 매출은 방법 C(약 8억원)로 둔다. 개인 빵집 평균(3.3억원)의 약 2.4배이지만 보나비 직영 평균(12.7억원)의 63% 수준으로, 신규 브랜드 1호점에 브랜드 프리미엄을 절반 정도만 인정한 값이다.",
}
ANCHOR = {"보수": M_B, "기준": M_C, "낙관": M_A}

add("시나리오 매출 앵커(기준기간 연매출)", {k: round(v) for k, v in ANCHOR.items()},
    "보수 = 방법B(상권 상위권 매장, 면적 환산), 기준 = 방법C(확보 점유율, 세 방법 중앙값), 낙관 = 방법A(보나비 점포당, 면적 환산). 산식은 revenue_triangulation.",
    f"{src('보나비')}; {SVC} 20253~20262; {LIC}")

proj = cand_v1["3년후_전망"]
g = {"보수": proj["보수(가정)"]["적용성장률_%"] / 100, "기준": proj["기본(가정)"]["적용성장률_%"] / 100,
     "낙관": cand_v1["지표"]["매출"]["합산_CAGR3_%"] / 100}
add("연 성장률 (가정, v1과 동일)", g, "v1과 같은 상권 성장률 가정. Y1 = 앵커 × (1+g), Y2·Y3 복리. 오픈 초기 램프업은 미반영(데이터 없음).",
    f"location.json 3년후_전망; {SVC} 20232→20262")

# =========================================================== 2. 비용 구조
pc = bb["proposed_cost_ratios"]
R = {
    "원재료": pc["원재료율"]["value"],
    "인건비": pc["인건비율"]["value"],
    "임차료": pc["임차료율(임차료+사용권자산상각비)"]["value"],
    "수수료": pc["수수료율(지급·카드·판매수수료)"]["value"],
    "광고판촉": pc["광고판촉비율"]["value"],
    "수도광열": pc["수도광열비율"]["value"],
    "소모품": pc["소모품비율"]["value"],
    "감가상각_벤치": pc["감가상각비율(유형, 사용권 제외)"]["value"],
}
# 기타 운영비(보험·수선·세금과공과 등) = 1 − 영업이익률 − 공시 8개 항목 (직영 4사 잔차 중앙값)
KEYS8 = ["원재료율", "인건비율", "임차료율(임차료+사용권자산상각비)", "감가상각비율(유형, 사용권 제외)",
         "수수료율(지급·카드·판매수수료)", "광고판촉비율", "수도광열비율", "소모품비율"]
resid = {}
for n in ("로쏘", "엘비엠", "보나비", "지에프에프지"):
    r = CO[n]["ratios"]["2025"]
    resid[n] = 1 - r["영업이익률"] - sum((r.get(k) or 0) for k in KEYS8)
R["기타운영"] = st.median(resid.values())

VAR = {"원재료": R["원재료"], "수수료": R["수수료"], "소모품": R["소모품"], "광고판촉": R["광고판촉"]}
FIXR = {"인건비": R["인건비"], "임차료": R["임차료"], "수도광열": R["수도광열"], "기타운영": R["기타운영"]}
var_ratio = sum(VAR.values())
DIRECT4 = ", ".join(src(n) for n in ("로쏘", "엘비엠", "보나비", "지에프에프지"))
for k, v in VAR.items():
    add(f"{k}비율 (변동비)", v, "bakery_benchmark.json proposed_cost_ratios — 직영 베이커리 4사 2025 중앙값(가정). 매출 연동.", DIRECT4)
for k in ("인건비", "임차료", "수도광열"):
    add(f"{k}비율 (고정비)", FIXR[k], "proposed_cost_ratios 값 × 기준 시나리오 Y1 매출 = 연 고정 금액. 임차료는 실제 임대 견적이 나오면 금액으로 교체.", DIRECT4)
add("기타운영비율 (고정비, 가정)", R["기타운영"],
    f"1 − 영업이익률 − 공시 8개 비용항목 비율의 직영 4사 잔차 중앙값. 각사 잔차 {({k: round(v, 4) for k, v in resid.items()})}. K-GAAP 3사는 원재료율이 상한값이라 잔차가 과소일 수 있음.",
    DIRECT4)

# 초기투자: 보나비 유형자산 변동표(천원)
txt = open(P("data", "interim", "audit_보나비_20260403003616.txt"), encoding="utf-8").read()
num = lambda s: float(s.replace(",", "").replace("(", "").replace(")", ""))
m_cost = re.search(r"^공구기구비품 \| ([\d,]+) \| ([\d,]+) \| \(([\d,]+)\) \| - \| - \| - \| ([\d,]+)$", txt, re.M)
m_dep = re.search(r"^공구기구비품 \| \([\d,]+\) \| - \| [\d,]+ \| - \| \(([\d,]+)\) \| - \|", txt, re.M)
m_dpst = re.search(r"^보증금 \| ([\d,]+) \| ([\d,]+) \|", txt, re.M)
equip_gross = num(m_cost.group(4)) * 1000          # 2025말 공구기구비품 취득원가
equip_dep = num(m_dep.group(1)) * 1000              # 2025 공구기구비품 감가상각비
deposit = (num(m_dpst.group(1)) + num(m_dpst.group(2))) * 1000
LIFE = 5
CAPEX = {
    "B_공구기구비품취득원가/매장수": equip_gross / bon_n,
    "A_공구기구비품상각비/매장수×5년": equip_dep / bon_n * LIFE,
}
capex = CAPEX["B_공구기구비품취득원가/매장수"]
deposit_ps = deposit / bon_n
dep = capex / LIFE
add("초기투자(인테리어·설비) (가정)", round(capex),
    f"보나비 2025말 공구기구비품 취득원가 {equip_gross:,.0f}원 ÷ {bon_n}개 매장(전 매장 임차·직영, 시설장치 계정 없음 → 인테리어 포함으로 판단). 상각 끝난 자산이 장부에 남아 있어 상한 성격 → 보수적으로 채택. 대안 A(연 상각비 {equip_dep:,.0f}원 ÷ 매장 × 5년) = {CAPEX['A_공구기구비품상각비/매장수×5년']:,.0f}원.",
    src("보나비") + " 유형자산 변동표")
add("임차보증금 (가정, 회수 가능 투자)", round(deposit_ps),
    f"보나비 2025말 보증금(유동 {num(m_dpst.group(1)):,.0f} + 비유동 {num(m_dpst.group(2)):,.0f}천원) ÷ {bon_n}개 매장. 비용 아님, 회수기간에는 별도 표시.",
    src("보나비") + " 금융자산 범주 주석")
add("내용연수 (가정)", LIFE, "보나비 원문에 공구기구비품 내용연수 표가 없음 → v1과 같은 5년 정액(스타벅스 회계정책 주석) 사용.",
    "DART 에스씨케이컴퍼니 rcpNo 20260406003256 회계정책; 가정")

# =========================================================== 3. 시뮬레이션
Y1_BASE = ANCHOR["기준"] * (1 + g["기준"])
FIX = {k: v * Y1_BASE for k, v in FIXR.items()}
FIX["감가상각비(초기투자/5년)"] = dep
fixed_total = sum(FIX.values())


def pnl_year(sales, mat=R["원재료"], fixed=None):
    fixed = FIX if fixed is None else fixed
    gp = sales * (1 - mat)
    other_d = {"지급수수료": sales * R["수수료"], "소모품비": sales * R["소모품"], "광고판촉비": sales * R["광고판촉"],
               "수도광열비": fixed["수도광열"], "기타비용": fixed["기타운영"], "무형자산상각비": 0.0,
               "감가상각비": fixed["감가상각비(초기투자/5년)"]}
    other = sum(other_d.values())
    op = gp - fixed["인건비"] - fixed["임차료"] - other
    return {"매출": sales, "원재료비": sales * mat, "매출총이익": gp, "매출총이익률": gp / sales,
            "인건비": fixed["인건비"], "임차료": fixed["임차료"], "기타": other, "기타_내역": other_d,
            "영업이익": op, "영업이익률": op / sales, "EBITDA": op + fixed["감가상각비(초기투자/5년)"]}


def payback(ebitdas, inv, growth):
    """누적 EBITDA가 투자액을 넘는 시점(년). Y3 이후는 Y3 EBITDA를 g로 연장(가정). 10년 내 미회수 시 None."""
    cum, prev = 0.0, 0.0
    e = list(ebitdas)
    while len(e) < 10:
        e.append(e[-1] * (1 + growth))
    for i, x in enumerate(e):
        if x <= 0:
            cum += x
            continue
        if cum + x >= inv:
            return round(i + (inv - cum) / x, 2)
        cum += x
    return None


def scenario(name, scale=1.0, mat=R["원재료"], fixed=None):
    out = {"매출앵커_원": ANCHOR[name], "매출배수": ANCHOR[name] / ANCHOR["기준"], "연성장률": g[name], "연도별": {}, "월평균": {}}
    cum = cum_e = 0
    for y in (1, 2, 3):
        s = ANCHOR[name] * (1 + g[name]) ** y * scale
        r = pnl_year(s, mat, fixed)
        out["연도별"][f"Y{y}"] = r
        out["월평균"][f"Y{y}"] = {k: (v / 12 if isinstance(v, (int, float)) and not k.endswith("률") else v) for k, v in r.items() if k != "기타_내역"}
        cum += r["영업이익"]
        cum_e += r["EBITDA"]
    out["3년누적_영업이익"] = cum
    out["3년누적_EBITDA"] = cum_e
    out["초기투자_회수(3년누적EBITDA/초기투자)"] = cum_e / capex
    eb = [out["연도별"][f"Y{y}"]["EBITDA"] for y in (1, 2, 3)]
    out["회수기간_년(초기투자)"] = payback(eb, capex, g[name])
    out["회수기간_년(초기투자+보증금)"] = payback(eb, capex + deposit_ps, g[name])
    return out


scen = {n: scenario(n) for n in ("보수", "기준", "낙관")}
be = fixed_total / (1 - var_ratio)
breakeven = {
    "손익분기_연매출_원": be, "손익분기_월매출_원": be / 12,
    "손익분기_대비_기준Y1매출": be / Y1_BASE,
    "손익분기_대비_상권_제과점_점포당_연매출(최근4분기/SIMILR)": be / per_store_mkt,
    "손익분기_대비_보나비_점포당매출(면적환산)": be / M_A,
    "고정비_연_원": fixed_total, "고정비_내역": FIX, "변동비율": var_ratio, "공헌이익률": 1 - var_ratio,
    "시나리오별_도달": {n: {f"Y{y}": scen[n]["연도별"][f"Y{y}"]["매출"] >= be for y in (1, 2, 3)} for n in scen},
    "계산식": "손익분기 매출 = 연 고정비 ÷ (1 − 변동비율). 고정비 = 기준 Y1 매출 × (인건비+임차료+수도광열+기타운영 비율) + 초기투자/5년; 변동비율 = 원재료+수수료+소모품+광고판촉",
}

# =========================================================== 4. 민감도
def op_rates(s):
    return {f"Y{y}": {"영업이익": s["연도별"][f"Y{y}"]["영업이익"], "영업이익률": s["연도별"][f"Y{y}"]["영업이익률"]} for y in (1, 2, 3)}


sens = {"기준_영업이익": {f"Y{y}": scen["기준"]["연도별"][f"Y{y}"]["영업이익"] for y in (1, 2, 3)}}
for lab, sc in (("매출-10%", 0.9), ("매출+10%", 1.1), ("매출-20%", 0.8)):
    sens[lab] = op_rates(scenario("기준", scale=sc))
for lab, d in (("원재료비-3%p", -0.03), ("원재료비+3%p", 0.03)):
    sens[lab] = op_rates(scenario("기준", mat=R["원재료"] + d))
grid = {}
for sl, sc in (("-10%", 0.9), ("0%", 1.0), ("+10%", 1.1)):
    grid[sl] = {ml: scenario("기준", scale=sc, mat=R["원재료"] + d)["연도별"]["Y1"]["영업이익률"]
                for ml, d in (("-3%p", -0.03), ("0", 0.0), ("+3%p", 0.03))}
sens["Y1영업이익률_그리드(행:매출, 열:원재료비)"] = grid
# 임차료: 보나비 점포당 실제 점유비용(금액)으로 교체
bon_rent_ps = CO["보나비"]["ratios"]["2025"]["임차료율(임차료+사용권자산상각비)"] * bon_ps
fx = dict(FIX); fx["임차료"] = bon_rent_ps
sens["임차료_보나비점포당금액"] = {"임차료_원": bon_rent_ps, "근거": src("보나비") + " 임차료+사용권자산상각비 ÷ 77점",
                            **op_rates(scenario("기준", fixed=fx))}
sens["초기투자"] = {}
for lab, cx in (("B_취득원가(채택)", CAPEX["B_공구기구비품취득원가/매장수"]), ("A_상각비역산", CAPEX["A_공구기구비품상각비/매장수×5년"])):
    fx = dict(FIX); fx["감가상각비(초기투자/5년)"] = cx / LIFE
    s = scenario("기준", fixed=fx)
    eb = [s["연도별"][f"Y{y}"]["EBITDA"] for y in (1, 2, 3)]
    sens["초기투자"][lab] = {"초기투자_원": cx, "연감가상각비_원": cx / LIFE,
                         "기준_영업이익률": {f"Y{y}": s["연도별"][f"Y{y}"]["영업이익률"] for y in (1, 2, 3)},
                         "회수기간_년": payback(eb, cx, g["기준"])}

# 카페(v1) 비용 구조와 비교 — 같은 v2 기준 매출에 v1 비율 적용
v1s = v1["benchmarks"]["본 모델_비용구조"]
v1_var = sum(v1s["변동"].values())
v1_fix = sum(v1s["고정(기준Y1 매출 대비)"].values()) + v1s["감가상각(기준Y1 대비)"]
v2_fix_ratio = fixed_total / Y1_BASE
cost_compare = {
    "설명": "같은 v2 기준 Y1 매출에 v1(스타벅스 중심 카페) 비용 구조와 v2(직영 베이커리) 비용 구조를 각각 적용",
    "v1_카페구조": {"변동비율": v1_var, "고정비율(기준Y1 대비)": v1_fix, "Y1_영업이익률": 1 - v1_var - v1_fix,
                 "출처": "data/interim/pnl.json benchmarks['본 모델_비용구조'] (DART 에스씨케이컴퍼니 20260406003256·CJ푸드빌 20260403002488)"},
    "v2_베이커리직영구조": {"변동비율": var_ratio, "고정비율(기준Y1 대비)": v2_fix_ratio, "Y1_영업이익률": scen["기준"]["연도별"]["Y1"]["영업이익률"],
                     "출처": "bakery_benchmark.json proposed_cost_ratios + 보나비 초기투자"},
    "항목별": {
        "원재료": {"v2_베이커리": R["원재료"], "스타벅스": bb["cafe_chains"]["에스씨케이컴퍼니"]["원재료율"], "투썸": bb["cafe_chains"]["투썸플레이스"]["원재료율"], "v1_가중": v1s["변동"]["원재료비"]},
        "인건비": {"v2_베이커리": R["인건비"], "스타벅스": bb["cafe_chains"]["에스씨케이컴퍼니"]["인건비율"], "투썸": bb["cafe_chains"]["투썸플레이스"]["인건비율"]},
        "임차료": {"v2_베이커리": R["임차료"], "스타벅스": bb["cafe_chains"]["에스씨케이컴퍼니"]["임차료율(임차료+사용권자산상각비)"], "투썸": bb["cafe_chains"]["투썸플레이스"]["임차료율(임차료+사용권자산상각비)"]},
        "지급수수료": {"v2_베이커리": R["수수료"], "v1_스타벅스(로열티 포함)": v1s["변동"]["지급수수료"]},
    },
    "해석": "베이커리 직영은 원재료가 카페(스타벅스)보다 높고 지급수수료(로열티 없음)가 낮다. 인건비는 제조 인력 때문에 스타벅스와 같은 30%대.",
}

# 면적 정합성: interior.json 좌석·면적 산식을 v2 매출에 적용
ticket = menu["avg_ticket"]["제안"]
ic = interior["meta"]["계산값"]
area_check = {}
for n in scen:
    s = scen[n]["연도별"]["Y1"]["매출"]
    tx = s / 365 / ticket
    area_check[n] = {"일거래_건": tx, "필요면적_m2(interior 산식 비례)": ic["총면적_계산값_m2"] * tx / ic["신규매장_일거래_가정"]}
area_check["주석"] = (f"interior.json 은 일 {ic['신규매장_일거래_가정']}건(상권 평균 거래) 기준 {ic['총면적_가정_m2']}㎡. 같은 산식(좌석∝피크 거래)으로 v2 매출을 소화하려면 위 면적 필요. "
                      f"객단가 = menu.json 제안 {ticket}원(가정). 결론: 55㎡ 안은 v2 매출과 맞지 않음 → 면적 재산정 필요.")

# =========================================================== 5. 비교·출력
v1b = v1["scenarios"]["기준"]["연도별"]["Y1"]
changes = [
    {"항목": "매출 기준", "v1": f"상권 제과점 점포당 평균 {eok(v1['assumptions'][0]['value'])}/년(개인 빵집 포함, 분모 SIMILR 11)",
     "v2": f"삼각검증 중앙값 {eok(M_C)}/년(방법C), 범위 {eok(min(vals.values()))}~{eok(max(vals.values()))}", "이유": "100㎡+ 브랜드 직영 포맷은 상권 평균(500m 평균 69.7㎡, 개인 67%)과 다름"},
    {"항목": "시나리오 정의", "v1": "평균 × 0.8 / 1.0 / 1.3 (근거 없는 배수)", "v2": "보수=방법B, 기준=방법C, 낙관=방법A — 각 앵커가 데이터 산식"},
    {"항목": "기준 Y1 매출", "v1": eok(v1b["매출"]), "v2": eok(scen["기준"]["연도별"]["Y1"]["매출"])},
    {"항목": "기준 Y1 영업이익률", "v1": f"{v1b['영업이익률'] * 100:.1f}%", "v2": f"{scen['기준']['연도별']['Y1']['영업이익률'] * 100:.1f}%"},
    {"항목": "손익분기 연매출", "v1": eok(v1["breakeven"]["손익분기_연매출_원"]), "v2": eok(be), "이유": "고정비가 매출 수준에 비례해 커짐(인건비·임차료 금액 증가) + 초기투자 상향"},
    {"항목": "원가 구조", "v1": "스타벅스 비율 + 원재료 커피·CJ푸드빌 50:50 가중(변동 47.1%)", "v2": f"직영 베이커리 4사 중앙값(변동 {var_ratio * 100:.1f}%, 인건비 {R['인건비'] * 100:.1f}%, 임차 {R['임차료'] * 100:.1f}%)"},
    {"항목": "지급수수료", "v1": "스타벅스 11.8%(SBI 로열티 포함)", "v2": f"{R['수수료'] * 100:.2f}%(로열티 없는 자체 브랜드 직영 4사)"},
    {"항목": "초기투자", "v1": f"{eok(v1['capex']['후보']['A_감가상각비역산'])} (스타벅스 상각비 역산)", "v2": f"{eok(capex)} (보나비 공구기구비품 취득원가/77점) + 보증금 {eok(deposit_ps)}"},
    {"항목": "기타운영비", "v1": "스타벅스 '기타'", "v2": f"직영 4사 잔차 중앙값 {R['기타운영'] * 100:.2f}%"},
    {"항목": "점포수 정정", "v1": "SIMILR 11 사용(정상)", "v2": "competition.json 의 STOR_CO 5곳 기준 192.1백만원/분기는 오류 → SIMILR 11 기준 87.3백만원 유지"},
]

limitations = [
    "매출 3개 방법 모두 매장 단위 실측이 아님. 방법A는 회사 전체 매출/매장 수(본사·도매 매출 포함 가능), 방법B는 면적당 매출 동일 가정, 방법C는 2개 분기 관측 순증을 점유율로 쓴 가정.",
    "보나비 77곳에는 병원·사옥 구내 매장이 섞여 있어 가두점 매출과 다를 수 있음. 엘비엠·지에프에프지·CJ푸드빌은 매장 수 미공시로 점포당 매출 산출 불가(공시 공백).",
    "비용 비율은 회사 전체(본사 인력·관리비 포함) 기준 → 매장 4-wall 손익보다 비용이 높게 잡힘(보수적). 본사 공통비 배부는 별도로 넣지 않음.",
    "로쏘·엘비엠·지에프에프지 원재료율은 매출원가 잔여(상한). 기타운영비 잔차는 그만큼 과소일 수 있음.",
    "초기투자는 보나비 장부상 취득원가/매장 수(상각 끝난 자산 포함 → 상한 성격). 실제 인테리어 견적·권리금은 데이터 없음.",
    "임대료 공공데이터 없음. 임차료 11.1%는 비율 가정이며, 보나비 점포당 금액으로 바꾸면 손실 폭이 커짐(sensitivity 참조).",
    "고정비를 기준 Y1 매출 × 비율로 잡아, 보수 시나리오에서도 같은 인력·임대 규모를 유지한다고 가정(인력 축소 대응 미반영).",
    "오픈 초기 램프업, 임금·임대료 인상, 법인세·이자는 미반영. 회수기간의 Y4 이후는 Y3 EBITDA를 성장률로 연장한 가정.",
]

out = {
    "meta": {"상권": loc2["final"]["상권명"], "TRDAR_CD": TRDAR, "자치구": loc2["final"]["자치구"], "단위": "원(KRW), 비율은 소수",
             "기간": "개점 후 3년(Y1~Y3) 연 단위 + 월평균(연/12)", "스크립트": "scripts/pnl_v2.py (선행: scripts/location_v2.py)",
             "버전": "v2 — 매출 기준 브랜드 직영 수준 재보정", "매장면적_가정_m2": AREA},
    "assumptions": A,
    "revenue_reference": {
        "상권_제과점_연매출_최근4분기_원": mkt_bak, "상권_커피_연매출_최근4분기_원": nb["커피_연매출_최근4분기_원"],
        "제과점_점포수_20262(SIMILR)": n_similr, "제과점_점포당_연매출_원": per_store_mkt,
        "보나비_점포당매출_원": bon_ps, "로쏘_점포당매출_원": ros_ps,
        "출처": f"{SVC} 20253~20262, {SVC_ST} 20262 (TRDAR_CD {TRDAR}); {src('보나비')}; {src('로쏘')}",
    },
    "revenue_triangulation": tri,
    "scenarios": scen,
    "breakeven": breakeven,
    "sensitivity": sens,
    "capex": {"채택": "B_공구기구비품취득원가/매장수", "후보": CAPEX, "내용연수": LIFE, "임차보증금_원": deposit_ps,
              "총_초기자금_원(설비+보증금)": capex + deposit_ps, "출처": src("보나비")},
    "cost_compare_vs_cafe": cost_compare,
    "area_check": area_check,
    "benchmarks": {"proposed_cost_ratios": {k: v["value"] for k, v in pc.items() if isinstance(v, dict) and "value" in v},
                   "직영4사_기타운영비_잔차": resid,
                   "비교표": bb["comparison_table"]},
    "changes_vs_v1": changes,
    "limitations": limitations,
}
with open(P("data", "interim", "pnl_v2.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# ---- 요약
print("앵커 A/B/C:", eok(M_A), eok(M_B), eok(M_C), "| v1 평균", eok(per_store_mkt), "| share", SHARE_BASE, "brand_share", round(brand_share, 3))
print("변동비율", round(var_ratio, 4), "고정비", eok(fixed_total), FIX, "기타운영", round(R["기타운영"], 4))
print("capex B", eok(capex), "A", eok(CAPEX["A_공구기구비품상각비/매장수×5년"]), "보증금", eok(deposit_ps))
for n, s in scen.items():
    for y in ("Y1", "Y2", "Y3"):
        r = s["연도별"][y]
        print(n, y, "매출", eok(r["매출"]), "OP", eok(r["영업이익"]), f"{r['영업이익률'] * 100:.1f}%", "EBITDA", eok(r["EBITDA"]))
    print("  회수(설비)", s["회수기간_년(초기투자)"], "회수(+보증금)", s["회수기간_년(초기투자+보증금)"])
print("BEP", eok(be), f"x{be / Y1_BASE:.3f} of 기준Y1")
print("임차 보나비 금액", eok(bon_rent_ps), sens["임차료_보나비점포당금액"]["Y1"])
print("capex A", sens["초기투자"]["A_상각비역산"])
print("cafe compare", cost_compare["v1_카페구조"]["Y1_영업이익률"], cost_compare["v2_베이커리직영구조"]["Y1_영업이익률"])
print("area", {k: round(v["필요면적_m2(interior 산식 비례)"], 1) for k, v in area_check.items() if k != "주석"})
