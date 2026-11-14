# -*- coding: utf-8 -*-
"""신규 직영 1호점(남부터미널역 상권) 3년 손익 시뮬레이션.

입력(공공·공시 데이터만):
  data/interim/location.json            최종 입지, 3년후 성장 가정
  data/raw/sales_<분기>.json            서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq
  data/raw/store_<분기>.json            서울시 상권분석서비스 점포 VwsmTrdarStorQq
  data/interim/dart_benchmark.json      DART 2025 감사보고서 비용의 성격별 분류(천원)
  data/interim/audit_에스씨케이컴퍼니_20260406003256.txt  유형자산 감가상각비·리스이자 (원문 행)
  data/raw/dart_docs/에스씨케이컴퍼니/20260406003256/*.xml  로열티·내용연수 주석 원문
출력: data/interim/pnl.json (utf-8)
실행: PYTHONIOENCODING=utf-8 python scripts/pnl.py
"""
import json
import os
import re
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"

SVC = "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq"
SVC_STORE = "서울시 상권분석서비스 점포 VwsmTrdarStorQq"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


loc = load(P("data", "interim", "location.json"))
bm = load(P("data", "interim", "dart_benchmark.json"))
final = loc["final"]
TRDAR = final["TRDAR_CD"]
cand = next(c for c in loc["candidates"] if c["TRDAR_CD"] == TRDAR)

# ---------------------------------------------------------------- 1. 매출 기준값
def rows(kind, q):
    d = load(P("data", "raw", f"{kind}_{q}.json"))
    return [r for r in d["rows"] if str(r["TRDAR_CD"]) == TRDAR]


def pick(rs, code, key):
    return float(next(r for r in rs if r["SVC_INDUTY_CD"] == code)[key])


BAK, COF = "CS100005", "CS100010"
last4 = ["20253", "20254", "20261", "20262"]
bak_q = {q: pick(rows("sales", q), BAK, "THSMON_SELNG_AMT") for q in last4}
cof_q = {q: pick(rows("sales", q), COF, "THSMON_SELNG_AMT") for q in last4}
st62 = rows("store", "20262")
st52 = rows("store", "20252")
bak_n62 = pick(st62, BAK, "SIMILR_INDUTY_STOR_CO")
cof_n62 = pick(st62, COF, "SIMILR_INDUTY_STOR_CO")
bak_n52 = pick(st52, BAK, "SIMILR_INDUTY_STOR_CO")

bak_4q = sum(bak_q.values())
cof_4q = sum(cof_q.values())
base_annual = bak_4q / bak_n62                       # 기준: 제과점 점포당 연매출(최근 4분기 합 / 20262 점포수)
ref = {
    "제과점_점포당_분기매출_20262_원": bak_q["20262"] / bak_n62,
    "커피_점포당_분기매출_20262_원": cof_q["20262"] / cof_n62,
    "합산_점포당_분기매출_20262_원": (bak_q["20262"] + cof_q["20262"]) / (bak_n62 + cof_n62),
    "제과점_점포당_연매출_4분기합/20262점포_원": base_annual,
    "제과점_점포당_연매출_4분기합/평균점포(20252·20262)_원": bak_4q / ((bak_n52 + bak_n62) / 2),
    "제과점_점포당_연매출_20262x4_원": bak_q["20262"] * 4 / bak_n62,
    "커피_점포당_연매출_4분기합/20262점포_원": cof_4q / cof_n62,
    "점포수_20262": {"제과점": bak_n62, "커피-음료": cof_n62},
    "점포수_20252": {"제과점": bak_n52},
    "분기매출_원": {"제과점": bak_q, "커피-음료": cof_q},
    "출처": f"{SVC} (CS100005·CS100010) 20253·20254·20261·20262, {SVC_STORE} 20252·20262 (SIMILR_INDUTY_STOR_CO), 상권 {final['상권명']} TRDAR_CD {TRDAR}",
}

proj = cand["3년후_전망"]
g = {
    "보수": proj["보수(가정)"]["적용성장률_%"] / 100,
    "기준": proj["기본(가정)"]["적용성장률_%"] / 100,
    "낙관": cand["지표"]["매출"]["합산_CAGR3_%"] / 100,
}
mult = {"보수": 0.8, "기준": 1.0, "낙관": 1.3}

# ---------------------------------------------------------------- 2. DART 비율
def ratios(name):
    c = bm[name]
    rev = c["revenue"]
    r = {k: sum(v) / rev for k, v in c["costs"].items()}
    r["_영업이익률"] = c["operating_income"] / rev
    r["_매출_천원"] = rev
    return r


R = {n: ratios(n) for n in ["에스씨케이컴퍼니", "투썸플레이스", "CJ푸드빌", "이디야"]}
sck = R["에스씨케이컴퍼니"]
RC = {n: bm[n]["rcept_no"] for n in R}

# 감사보고서 원문 행에서 유형자산 감가상각비·리스부채 이자비용 파싱
audit_txt = open(P("data", "interim", "audit_에스씨케이컴퍼니_20260406003256.txt"), encoding="utf-8").read()


def num(s):
    return float(s.replace(",", "").replace("(", "-").replace(")", ""))


m_dep = re.search(r"유형자산감가상각비 \| ([\d,]+)", audit_txt)
sck_ppe_dep_won = num(m_dep.group(1))                       # 원 단위 (포괄손익/현금흐름 조정)
m_lease_int = re.search(r"리스부채 이자비용 \| ([\d,]+)", audit_txt)
sck_lease_int = num(m_lease_int.group(1))                   # 천원
m_ppe_cost = re.search(r"취득원가 \| 구축물 \|[^\n]*\n기타유형자산[^\n]*\n차량운반구[^\n]*\n건설중인자산[^\n]*\n합 계 \| [\d,]+ \| [\d,]+ \| \([\d,]+\) \| \([\d,]+\) \| - \| ([\d,]+)", audit_txt)
sck_ppe_gross = num(m_ppe_cost.group(1))                    # 천원, 당기말 유형자산 취득원가 합계
rev_sck_won = bm["에스씨케이컴퍼니"]["revenue"] * 1000
ppe_dep_ratio = sck_ppe_dep_won / rev_sck_won
intang_ratio = sck["유무형자산상각비"] - ppe_dep_ratio
lease_int_ratio = sck_lease_int / bm["에스씨케이컴퍼니"]["revenue"]
ppe_gross_ratio = sck_ppe_gross / bm["에스씨케이컴퍼니"]["revenue"]

# 로열티 주석 원문 확인
royalty_text = "데이터 없음"
for x in glob.glob(P("data", "raw", "dart_docs", "에스씨케이컴퍼니", "20260406003256", "*.xml")):
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", open(x, encoding="utf-8", errors="ignore").read()))
    m = re.search(r"\(4\) 상표 및 기술 사용 계약.{0,250}?로열티를 지급하고 있습니다\.", t)
    if m:
        royalty_text = m.group(0)
        break
m_life = re.search(r"5년 동안 정액법", "".join(open(x, encoding="utf-8", errors="ignore").read() for x in glob.glob(P("data", "raw", "dart_docs", "에스씨케이컴퍼니", "20260406003256", "*.xml"))))
USEFUL_LIFE = 5 if m_life else None

# 원재료비: 직영 커피(스타벅스)와 베이커리(뚜레쥬르 CJ푸드빌) 가중
W_BAKERY = 0.5
mat_cof = sck["원재료·상품"]
mat_bak = R["CJ푸드빌"]["원재료·상품"]
mat = (1 - W_BAKERY) * mat_cof + W_BAKERY * mat_bak
mat_alt_tw = (1 - W_BAKERY) * mat_cof + W_BAKERY * R["투썸플레이스"]["원재료·상품"]
mkt_bak_share = cand["지표"]["매출"]["베이커리매출_최신_억원"] / cand["지표"]["매출"]["합산매출_최신_억원"]
mat_mkt_w = (1 - mkt_bak_share) * mat_cof + mkt_bak_share * mat_bak

# 비용 구조 (매출 대비)
fee = sck["지급수수료"]
occ = sck["임차료"] + sck["사용권자산상각비"]
VAR = {"원재료비": mat, "지급수수료": fee, "소모품비": sck["소모품비"]}
FIX_RATIO = {"인건비": sck["인건비"], "임차료(임차료+사용권자산상각비)": occ,
             "수도광열비": sck["수도광열비"], "기타비용": sck["기타"],
             "무형자산상각비": intang_ratio}

# ---------------------------------------------------------------- 3. 시뮬레이션
Y1_BASE = base_annual * (1 + g["기준"])          # 기준 시나리오 1년차 매출 (고정비 앵커)
CAPEX = {
    "A_감가상각비역산": ppe_dep_ratio * Y1_BASE * USEFUL_LIFE,
    "B_유형자산취득원가/매출": ppe_gross_ratio * Y1_BASE,
}
capex = CAPEX["A_감가상각비역산"]
dep = capex / USEFUL_LIFE
FIX = {k: v * Y1_BASE for k, v in FIX_RATIO.items()}
FIX["감가상각비(초기투자/5년)"] = dep
fixed_total = sum(FIX.values())
var_ratio = sum(VAR.values())


def pnl_year(sales, mat_r=mat, fixed=None):
    fixed = FIX if fixed is None else fixed
    gp = sales * (1 - mat_r)
    labor = fixed["인건비"]
    rent = fixed["임차료(임차료+사용권자산상각비)"]
    other = (sales * (fee + sck["소모품비"]) + fixed["수도광열비"] + fixed["기타비용"]
             + fixed["무형자산상각비"] + fixed["감가상각비(초기투자/5년)"])
    op = gp - labor - rent - other
    return {
        "매출": sales, "원재료비": sales * mat_r, "매출총이익": gp, "매출총이익률": gp / sales,
        "인건비": labor, "임차료": rent,
        "기타": other,
        "기타_내역": {"지급수수료": sales * fee, "소모품비": sales * sck["소모품비"],
                    "수도광열비": fixed["수도광열비"], "기타비용": fixed["기타비용"],
                    "무형자산상각비": fixed["무형자산상각비"], "감가상각비": fixed["감가상각비(초기투자/5년)"]},
        "영업이익": op, "영업이익률": op / sales,
        # EBITDA = 영업이익 + 감가상각비(초기투자/5년) + 무형자산상각비. 임차료·사용권자산상각비는 현금성 점유비용으로 보고 가산하지 않음
        "EBITDA": op + fixed["감가상각비(초기투자/5년)"] + fixed["무형자산상각비"],
    }


def scenario(name, scale=1.0, mat_r=mat):
    out = {"매출배수": mult[name], "연성장률": g[name], "연도별": {}, "월평균": {}}
    cum = 0
    cum_ebitda = 0
    for y in (1, 2, 3):
        s = base_annual * mult[name] * (1 + g[name]) ** y * scale
        r = pnl_year(s, mat_r)
        out["연도별"][f"Y{y}"] = r
        out["월평균"][f"Y{y}"] = {k: (v / 12 if isinstance(v, (int, float)) and not k.endswith("률") else v)
                              for k, v in r.items() if k != "기타_내역"}
        cum += r["영업이익"]
        cum_ebitda += r["EBITDA"]
    out["3년누적_영업이익"] = cum
    out["3년누적_EBITDA"] = cum_ebitda
    out["초기투자_회수(3년누적EBITDA/초기투자)"] = cum_ebitda / capex
    return out


scen = {n: scenario(n) for n in ("보수", "기준", "낙관")}

be_sales = fixed_total / (1 - var_ratio)
breakeven = {
    "손익분기_연매출_원": be_sales,
    "손익분기_월매출_원": be_sales / 12,
    "손익분기_대비_기준Y1매출": be_sales / Y1_BASE,
    "손익분기_대비_제과점_점포당_연매출(최근4분기)": be_sales / base_annual,
    "고정비_연_원": fixed_total, "변동비율": var_ratio, "공헌이익률": 1 - var_ratio,
    "시나리오별_도달": {n: {f"Y{y}": scen[n]["연도별"][f"Y{y}"]["매출"] >= be_sales for y in (1, 2, 3)} for n in scen},
    "계산식": "손익분기 매출 = 연 고정비 ÷ (1 − 변동비율). 고정비 = 기준 시나리오 Y1 매출 × (인건비+임차료+사용권자산상각비+수도광열비+기타비용+무형자산상각비 비율) + 초기투자/5년; 변동비율 = 원재료비(가중) + 지급수수료 + 소모품비",
}

# 민감도 (기준 시나리오)
sens = {"기준_영업이익": {f"Y{y}": scen["기준"]["연도별"][f"Y{y}"]["영업이익"] for y in (1, 2, 3)}}
for lab, sc in (("매출-10%", 0.9), ("매출+10%", 1.1)):
    s = scenario("기준", scale=sc)
    sens[lab] = {f"Y{y}": {"영업이익": s["연도별"][f"Y{y}"]["영업이익"], "영업이익률": s["연도별"][f"Y{y}"]["영업이익률"]} for y in (1, 2, 3)}
for lab, d in (("원재료비-3%p", -0.03), ("원재료비+3%p", 0.03)):
    s = scenario("기준", mat_r=mat + d)
    sens[lab] = {f"Y{y}": {"영업이익": s["연도별"][f"Y{y}"]["영업이익"], "영업이익률": s["연도별"][f"Y{y}"]["영업이익률"]} for y in (1, 2, 3)}
# 매출 x 원재료 2차원 (Y1 영업이익률)
grid = {}
for sl, sc in (("-10%", 0.9), ("0%", 1.0), ("+10%", 1.1)):
    grid[sl] = {}
    for ml, d in (("-3%p", -0.03), ("0", 0.0), ("+3%p", 0.03)):
        grid[sl][ml] = scenario("기준", scale=sc, mat_r=mat + d)["연도별"]["Y1"]["영업이익률"]
sens["Y1영업이익률_그리드(행:매출, 열:원재료비)"] = grid
# 지급수수료 대체(로열티 제외 근사) 민감도
fee_alt = min(R["투썸플레이스"]["지급수수료"], R["CJ푸드빌"]["지급수수료"])
fee_delta = fee - fee_alt
sens["지급수수료_비교군치환"] = {
    "지급수수료_대체비율": fee_alt,
    "근거": "투썸플레이스·CJ푸드빌 지급수수료/매출 중 낮은 값(로열티 지급 주석 없음). 스타벅스 11.8%와의 차이를 로열티 몫의 대리치로 본 경우",
    "기준_Y1~Y3_영업이익률": {f"Y{y}": scen["기준"]["연도별"][f"Y{y}"]["영업이익률"] + fee_delta for y in (1, 2, 3)},
}
# 초기투자 민감도
sens["초기투자"] = {}
for lab, cx in (("A_감가상각비역산", CAPEX["A_감가상각비역산"]), ("B_유형자산취득원가/매출", CAPEX["B_유형자산취득원가/매출"]),
                ("A×2(사용자입력 예시)", CAPEX["A_감가상각비역산"] * 2)):
    d2 = cx / USEFUL_LIFE
    fx = dict(FIX)
    fx["감가상각비(초기투자/5년)"] = d2
    ops = [pnl_year(scen["기준"]["연도별"][f"Y{y}"]["매출"], fixed=fx) for y in (1, 2, 3)]
    sens["초기투자"][lab] = {
        "초기투자_원": cx, "연감가상각비_원": d2,
        "기준_영업이익률": {f"Y{y}": ops[y - 1]["영업이익률"] for y in (1, 2, 3)},
        "기준_3년누적EBITDA/초기투자": sum(o["EBITDA"] for o in ops) / cx,
    }

# ---------------------------------------------------------------- 4. assumptions
def src_dart(n):
    return f"DART 2025 감사보고서 {n} rcept_no {RC[n]} ({DART_URL.format(RC[n])})"


A = []
add = lambda name, value, basis, source: A.append({"name": name, "value": value, "basis": basis, "source": source})
add("기준 연매출(제과점 점포당, 최근 4분기)", round(base_annual), "제과점 추정매출 20253~20262 4개 분기 합 ÷ 20262 제과점 유사업종점포수(11). 베이커리 주도 복합 매장은 제과점 업종으로 분류된다는 가정. 4분기 합으로 계절성 제거.", ref["출처"])
add("시나리오 매출 배수 (가정)", mult, "보수 x0.8 / 기준 x1.0 / 낙관 x1.3 — 상권 제과점 점포당 평균 대비 신규 1호점 매출 수준. 근거 데이터 없음(가정).", "가정")
add("연 성장률 (가정)", g, "보수 = location.json 보수 전망 적용성장률(0.5×min(2분기YoY중앙값,25%)+0.5×서울시장 CAGR3); 기준 = 기본 전망(합산 CAGR3×0.7); 낙관 = 합산 CAGR3 8.2% 그대로. Y1은 기준기간(2025Q3~2026Q2) 대비 1년 성장 적용.", f"location.json 3년후_전망; {SVC} 20232→20262")
add("원재료비율 (가정: 커피 50% : 베이커리 50% 가중)", mat, f"스타벅스(에스씨케이) {mat_cof:.4f} × 0.5 + CJ푸드빌(뚜레쥬르) {mat_bak:.4f} × 0.5. 베이커리 주도 포맷이라 상권 실적 베이커리 비중({mkt_bak_share:.3f})보다 높게 50%로 둠. 비교: 투썸 가중 시 {mat_alt_tw:.4f}, 상권 비중 가중 시 {mat_mkt_w:.4f}.", f"{src_dart('에스씨케이컴퍼니')}; {src_dart('CJ푸드빌')}; {src_dart('투썸플레이스')}")
add("인건비율", sck["인건비"], "스타벅스 종업원 관련 원가/매출 (전 매장 직영 구조). 고정비로 처리(기준 Y1 매출 기준 금액 고정).", src_dart("에스씨케이컴퍼니"))
add("임차료율(임차료+사용권자산상각비)", occ, f"임차료 {sck['임차료']:.4f} + 사용권자산상각비 {sck['사용권자산상각비']:.4f}. IFRS16상 리스료가 상각비로 분리되므로 합산해 점유비용으로 봄. 리스부채 이자 {lease_int_ratio:.4f}는 영업외라 제외. 임대료 공공데이터 없음.", src_dart("에스씨케이컴퍼니"))
add("지급수수료율", fee, "스타벅스 지급수수료/매출 그대로 사용. 감사보고서 주석 30(4)에 SBI Nevada와 상표·기술 라이센스 계약으로 '순매출액의 일정율' 로열티 지급이 확인되나 요율·금액 미공시 → 자체 브랜드 조정 불가, 그대로 두고 한계로 명시(비교군 치환 민감도 별도).", src_dart("에스씨케이컴퍼니") + " 주석 30(4)")
add("소모품비율", sck["소모품비"], "변동비", src_dart("에스씨케이컴퍼니"))
add("수도광열비율", sck["수도광열비"], "고정비", src_dart("에스씨케이컴퍼니"))
add("기타비용율", sck["기타"], "고정비(운반비·판촉비 등 포함)", src_dart("에스씨케이컴퍼니"))
add("무형자산상각비율", intang_ratio, "유무형자산상각비 − 유형자산감가상각비. 프랜차이즈권 상각(스타벅스 고유)이 포함될 수 있으나 분리 불가 → 보수적으로 포함.", src_dart("에스씨케이컴퍼니"))
add("초기투자(인테리어·설비) (역산 가정)", round(capex), f"스타벅스 유형자산감가상각비/매출 {ppe_dep_ratio:.4f} × 내용연수 {USEFUL_LIFE}년(정액법, 회계정책 주석) × 기준 Y1 매출. 정상상태에서 매장당 연 감가상각비×내용연수≈설비 취득원가라는 가정. 대안 B(유형자산 취득원가 합계/매출 {ppe_gross_ratio:.4f}) = {CAPEX['B_유형자산취득원가/매출']:,.0f}원. 실제 견적은 사용자 입력 필요.", src_dart("에스씨케이컴퍼니") + " 유형자산 변동표·회계정책 2-2-5")
add("고정비 증가율 (가정)", 0.0, "3년간 명목 고정 — 임대료 인상·임금 상승 공공데이터 없음(데이터 없음). 매출 성장분이 그대로 영업레버리지로 반영됨.", "가정")

benchmarks = {}
for n, r in R.items():
    benchmarks[n] = {
        "brand": bm[n]["brand"], "rcept_no": RC[n], "url": DART_URL.format(RC[n]),
        "매출_천원": r["_매출_천원"], "영업이익률": r["_영업이익률"],
        "비용비율": {k: v for k, v in r.items() if not k.startswith("_")},
    }
benchmarks["에스씨케이컴퍼니"]["보조"] = {
    "유형자산감가상각비율": ppe_dep_ratio, "무형자산상각비율": intang_ratio,
    "리스부채이자/매출": lease_int_ratio, "유형자산취득원가합계/매출": ppe_gross_ratio,
    "유형자산_내용연수": USEFUL_LIFE, "로열티_주석원문": royalty_text,
}
benchmarks["본 모델_비용구조"] = {"변동": VAR, "고정(기준Y1 매출 대비)": FIX_RATIO, "감가상각(기준Y1 대비)": dep / Y1_BASE,
                             "총비용률_기준Y1": var_ratio + sum(FIX_RATIO.values()) + dep / Y1_BASE}

limitations = [
    "점포당 추정매출은 카드결제 기반 상권 평균이며 실제 신규 매장 매출이 아님. 제과점 점포수 11곳 소수 표본(마스킹·고정값 가능성).",
    "기준 매출은 제과점 업종 점포당 평균만 사용(베이커리 주도 복합 매장 가정). 커피 단독 점포당 연매출은 참고값으로만 제시.",
    "비용 비율은 회사 전체(본사 관리비 포함) 감사보고서 수치로 매장 단위 손익과 다름. 1개 매장 회사는 본사비 부담률이 더 클 수 있음.",
    "원재료비 비교군(CJ푸드빌·투썸)은 가맹점 공급 상품 매출이 섞여 원재료율이 직영 매장보다 높게 나올 수 있음 → 베이커리 쪽 원재료비는 보수적(상한)일 가능성.",
    "스타벅스 지급수수료(11.8%)에 로열티가 포함됨을 주석으로 확인했으나 요율 미공시로 분리 불가 → 자체 브랜드엔 비용 과대일 수 있음(비교군 치환 민감도 참고).",
    "임대료 공공데이터 없음: 서초권 실제 임차료와 다를 수 있음. 리스부채 이자(매출의 0.42%)는 영업이익 아래라 제외.",
    "초기투자는 공공·공시 데이터가 없어 DART 감가상각비로 역산한 가정치이며 인테리어 견적·보증금·권리금은 포함하지 않음(사용자 입력 필요).",
    "오픈 초기 매출 램프업, 임금·임대료 인상, 법인세·이자 등 영업외 항목은 데이터 없음으로 반영하지 않음.",
    "고정비를 기준 시나리오 Y1 매출 × 스타벅스 비율로 잡았으므로 기준 시나리오의 손익분기 판단은 비율 구조에 좌우됨.",
]

out = {
    "meta": {"상권": final["상권명"], "TRDAR_CD": TRDAR, "자치구": final["자치구"], "단위": "원(KRW), 비율은 소수",
             "기간": "개점 후 3년(Y1~Y3) 연 단위 + 월평균(연/12)", "스크립트": "scripts/pnl.py"},
    "assumptions": A,
    "revenue_reference": ref,
    "scenarios": scen,
    "breakeven": breakeven,
    "sensitivity": sens,
    "capex": {"채택": "A_감가상각비역산", "후보": CAPEX, "내용연수": USEFUL_LIFE},
    "benchmarks": benchmarks,
    "limitations": limitations,
}
with open(P("data", "interim", "pnl.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

# 요약 출력
eok = lambda x: f"{x / 1e8:,.2f}억"
print("기준 연매출(제과점 점포당):", eok(base_annual), "| 참고 커피 점포당:", eok(ref["커피_점포당_연매출_4분기합/20262점포_원"]))
print(f"원재료 {mat:.4f} 지급수수료 {fee:.4f} 인건비 {sck['인건비']:.4f} 임차 {occ:.4f} 변동비율 {var_ratio:.4f}")
print("초기투자 A", eok(CAPEX['A_감가상각비역산']), "B", eok(CAPEX['B_유형자산취득원가/매출']))
for n, s in scen.items():
    for y in ("Y1", "Y2", "Y3"):
        r = s["연도별"][y]
        print(n, y, "매출", eok(r["매출"]), "GP", eok(r["매출총이익"]), "인건", eok(r["인건비"]), "임차", eok(r["임차료"]),
              "기타", eok(r["기타"]), "OP", eok(r["영업이익"]), f"{r['영업이익률']*100:.1f}%")
print("BEP", eok(be_sales), f"x{be_sales / Y1_BASE:.3f} of 기준Y1")
print(json.dumps({k: v for k, v in sens.items() if k in ("매출-10%", "매출+10%", "원재료비-3%p", "원재료비+3%p", "지급수수료_비교군치환")}, ensure_ascii=False))
print("royalty:", royalty_text[:120])
