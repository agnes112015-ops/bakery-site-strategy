"""입지 선정 종합(수석 컨설턴트): 3개 패널(성장 모멘텀 / 타깃 적합 / 리스크·경쟁) 결과를 원천 데이터로 재확인해
최종 후보 3곳과 최종 출점지 1곳을 확정하고 data/interim/location.json 으로 저장한다.

- 입력: data/interim/trdar_scores.csv, data/interim/analysis.json (scripts/analyze.py v2 결과), data/raw/*.json
- 모든 수치는 파일에서 계산해 넣는다(손 입력 없음). 문장 속 수치도 f-string 으로 데이터에서 채운다.
실행: PYTHONIOENCODING=utf-8 python scripts/build_location.py
"""
import csv
import glob
import json
import os
import statistics as st
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
INT = os.path.join(ROOT, "data", "interim")

SALES_Q = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]
STORE_Q = ["20232", "20242", "20252", "20262"]
QN, Q0, Q1 = "20262", "20232", "20252"

# ---- 수석 컨설턴트 판정: 최종 후보 (TRDAR_CD) ----
FINAL_CD = "3120175"                       # 남부터미널역
CANDIDATE_CDS = ["3120175", "3120093", "3120037"]  # 남부터미널역, 연희동, 동대문역사문화공원역
SUBWAY_MATCH = {"3120175": ["남부터미널(예술의전당)"], "3120037": ["동대문역사문화공원(DDP)"], "3120093": []}


def load(name):
    with open(os.path.join(RAW, name + ".json"), encoding="utf-8") as f:
        return json.load(f)["rows"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def eok(v, nd=1):
    return None if v is None else round(v / 1e8, nd)


def pct(v, nd=1):
    return None if v is None else round(100 * v, nd)


def kind(r):
    n = r.get("SVC_INDUTY_CD_NM") or ""
    return "bak" if "제과" in n else ("cof" if "커피" in n else None)


# ---------------- 데이터 로드 ----------------
with open(os.path.join(INT, "analysis.json"), encoding="utf-8") as f:
    ana = json.load(f)
rows = list(csv.DictReader(open(os.path.join(INT, "trdar_scores.csv"), encoding="utf-8-sig")))
by_cd = {r["TRDAR_CD"]: r for r in rows}
by_nm = {r["상권명"]: r for r in rows}
v1rows = list(csv.DictReader(open(os.path.join(INT, "trdar_scores_v1.csv"), encoding="utf-8-sig"))) \
    if os.path.exists(os.path.join(INT, "trdar_scores_v1.csv")) else []


def F(r, k):
    v = r.get(k)
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return v


def L(r, k):
    return json.loads(r[k].replace("None", "null").replace("'", '"'))


sales = defaultdict(dict)   # cd -> q -> kind -> row
for q in SALES_Q:
    for r in load(f"sales_{q}"):
        k = kind(r)
        if k:
            sales[r["TRDAR_CD"]].setdefault(q, {})[k] = r
stores = defaultdict(dict)
for q in STORE_Q:
    for r in load(f"store_{q}"):
        k = kind(r)
        if k:
            stores[r["TRDAR_CD"]].setdefault(q, {})[k] = r
flpop = defaultdict(dict)
for q in STORE_Q:
    for r in load(f"flpop_{q}"):
        flpop[r["TRDAR_CD"]][q] = r
ix = {r["TRDAR_CD"]: r for r in load("trdar_ix_20262")}
area = {r["TRDAR_CD"]: r for r in load("trdar_area")}
fcl_q = defaultdict(dict)
for r in load("fclty_all"):
    fcl_q[r["TRDAR_CD"]][r["STDR_YYQU_CD"]] = r
repop_q = defaultdict(dict)
for r in load("repop_all"):
    repop_q[r["TRDAR_CD"]][r["STDR_YYQU_CD"]] = r
wrc_q = defaultdict(dict)
for r in load("wrcpop_all"):
    wrc_q[r["TRDAR_CD"]][r["STDR_YYQU_CD"]] = r

subway_week = defaultdict(float)
subway_days = set()
for fp in sorted(glob.glob(os.path.join(RAW, "subway_202611*.json"))):
    with open(fp, encoding="utf-8") as f:
        d = json.load(f)
    subway_days.add(d.get("date"))
    for r in d["rows"]:
        subway_week[(r["SBWY_ROUT_LN_NM"], r["SBWY_STNS_NM"])] += float(r["GTON_TNOPE"]) + float(r["GTOFF_TNOPE"])

# 176개 상권 중앙값 (비교 기준)
def med(k):
    xs = [F(r, k) for r in rows if isinstance(F(r, k), float)]
    return st.median(xs) if xs else None


MED = {k: med(k) for k in ["유동인구_증감률", "합산_2030비중", "합산_여성비중", "합산_주말비중", "합산_오전비중",
                           "합산_객단가", "베이커리_점포당분기매출", "운영영업개월", "합산_2분기YoY_중앙값", "타깃적합"]}
SEOUL_OPR = num(ix[FINAL_CD]["SU_OPR_SALE_MT_AVRG"])

SRC = {
    "sales": "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq (제과점 CS100005·커피-음료 CS100010), 20232·20242·20252·20253·20254·20261·20262",
    "store": "서울시 상권분석서비스 점포 VwsmTrdarStorQq, 20232·20242·20252·20262",
    "flpop": "서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq, 20232·20242·20252·20262",
    "repop": "서울시 상권분석서비스 상주인구 VwsmTrdarRepopQq (전 분기)",
    "wrc": "서울시 상권분석서비스 직장인구 VwsmTrdarWrcPopltnQq (전 분기)",
    "fclty": "서울시 상권분석서비스 집객시설 VwsmTrdarFcltyQq (최신 공표분기)",
    "ix": "서울시 상권분석서비스 상권변화지표 VwsmTrdarIxQq, 20262",
    "area": "서울시 상권분석서비스 상권영역 TbgisTrdarRelm",
    "subway": "서울시 지하철 호선별 역별 승하차 인원 CardSubwayStatsNew, 2026-11-02~2026-11-08 (1주)",
}


def latest_q(d, upto=QN):
    qs = sorted(q for q in d if q <= upto)
    return (d[qs[-1]], qs[-1]) if qs else ({}, None)


def first_q_change(d):
    """값이 마지막으로 바뀐 분기 (이후 동결 여부 확인용)."""
    qs = sorted(d)
    return qs


# ---------------- 상권 지표 묶음 ----------------
def indicators(cd):
    r = by_cd[cd]
    fc, fc_q = latest_q(fcl_q[cd])
    rp, rp_q = latest_q(repop_q[cd])
    wp, wp_q = latest_q(wrc_q[cd])
    t7, b7, c7 = L(r, "합산매출_7분기"), L(r, "베이커리매출_7분기"), L(r, "커피매출_7분기")
    sN = stores[cd].get(QN, {})
    s0 = stores[cd].get(Q0, {})
    sb, sc = sN.get("bak", {}), sN.get("cof", {})
    stations = SUBWAY_MATCH.get(cd, [])
    sub = {f"{ln} {nm}": int(v) for (ln, nm), v in subway_week.items() if nm in stations}
    return {
        "매출": {
            "합산매출_최신_억원": eok(F(r, "합산매출_최신"), 2), "합산매출_3년전_억원": eok(F(r, "합산매출_3년전"), 2),
            "합산매출_1년전_억원": eok(F(r, "합산매출_1년전"), 2),
            "베이커리매출_최신_억원": eok(F(r, "베이커리매출_최신"), 2), "베이커리매출_3년전_억원": eok(F(r, "베이커리매출_3년전"), 2),
            "커피매출_최신_억원": eok(F(r, "커피매출_최신"), 2), "커피매출_3년전_억원": eok(F(r, "커피매출_3년전"), 2),
            "합산_CAGR3_%": pct(F(r, "합산매출_CAGR3")), "베이커리_CAGR3_%": pct(F(r, "베이커리_CAGR3")),
            "합산_YoY_%(20252→20262)": pct(F(r, "합산매출_YoY")),
            "합산_2분기YoY_3구간_%(23→24,24→25,25→26)": [pct(v) for v in L(r, "합산_2분기YoY_3구간")],
            "합산_2분기YoY_중앙값_%": pct(F(r, "합산_2분기YoY_중앙값")),
            "플러스구간수": int(F(r, "합산_플러스구간수")),
            "점프비중(최대 단일분기 증가/3년 증가분)": None if F(r, "점프비중") is None else round(F(r, "점프비중"), 2),
            "구조적단절": L(r, "단절내역") or "없음",
            "합산매출_7분기_억원": dict(zip(SALES_Q, [eok(v, 2) for v in t7])),
            "베이커리매출_7분기_억원": dict(zip(SALES_Q, [eok(v, 2) for v in b7])),
            "커피매출_7분기_억원": dict(zip(SALES_Q, [eok(v, 2) for v in c7])),
            "출처": SRC["sales"],
        },
        "인구": {
            "유동인구_최신": F(r, "유동인구_최신"), "유동인구_3년전": F(r, "유동인구_3년전"),
            "유동인구_증감률_%": pct(F(r, "유동인구_증감률")),
            "유동인구_증감률_서울176상권중앙값_%": pct(MED["유동인구_증감률"]),
            "상주인구": num(rp.get("TOT_REPOP_CO")), "상주인구_기준분기": rp_q,
            "상주인구_증감률_%": pct(F(r, "상주인구_증감률")),
            "직장인구": num(wp.get("TOT_WRC_POPLTN_CO")), "직장인구_기준분기": wp_q,
            "직장인구_증감률_%": pct(F(r, "직장인구_증감률")),
            "주의": "상주·직장인구는 원천에서 일정 분기 이후 값이 동결돼 있어 증감률은 참고용(점수 미반영)",
            "출처": [SRC["flpop"], SRC["repop"], SRC["wrc"]],
        },
        "점포": {
            "베이커리점포_최신": num(sb.get("SIMILR_INDUTY_STOR_CO")), "베이커리점포_3년전": num(s0.get("bak", {}).get("SIMILR_INDUTY_STOR_CO")),
            "베이커리_프랜차이즈_최신": num(sb.get("FRC_STOR_CO")),
            "커피점포_최신": num(sc.get("SIMILR_INDUTY_STOR_CO")), "커피점포_3년전": num(s0.get("cof", {}).get("SIMILR_INDUTY_STOR_CO")),
            "커피_프랜차이즈_최신": num(sc.get("FRC_STOR_CO")),
            "베이커리_점포당분기매출_억원": eok(F(r, "베이커리_점포당분기매출"), 3),
            "베이커리_점포당분기매출_176중앙값_억원": eok(MED["베이커리_점포당분기매출"], 3),
            "베이커리_점포당매출_3년변화율_%": pct(F(r, "베이커리_점포당매출_변화율")),
            "베이커리_개업률_%(20262)": num(sb.get("OPBIZ_RT")), "베이커리_폐업률_%(20262)": num(sb.get("CLSBIZ_RT")),
            "커피_개업률_%(20262)": num(sc.get("OPBIZ_RT")), "커피_폐업률_%(20262)": num(sc.get("CLSBIZ_RT")),
            "표본4분기_평균폐업률_%(제과+커피)": pct(F(r, "4분기평균_폐업률"), 2),
            "출처": [SRC["store"], SRC["sales"]],
        },
        "고객구성_합산(제과+커피, 20262)": {
            "2030비중_%": pct(F(r, "합산_2030비중")), "여성비중_%": pct(F(r, "합산_여성비중")),
            "주말비중_%": pct(F(r, "합산_주말비중")), "오전(06~11시)비중_%": pct(F(r, "합산_오전비중")),
            "객단가_원": None if F(r, "합산_객단가") is None else round(F(r, "합산_객단가")),
            "176상권중앙값": {"2030비중_%": pct(MED["합산_2030비중"]), "여성비중_%": pct(MED["합산_여성비중"]),
                          "주말비중_%": pct(MED["합산_주말비중"]), "오전비중_%": pct(MED["합산_오전비중"]),
                          "객단가_원": round(MED["합산_객단가"])},
            "베이커리만": {"2030비중_%": pct(F(r, "베이커리_2030비중")), "여성비중_%": pct(F(r, "베이커리_여성비중")),
                       "주말비중_%": pct(F(r, "베이커리_주말비중")), "오전비중_%": pct(F(r, "베이커리_오전비중"))},
            "출처": SRC["sales"] + " (20262)",
        },
        "시설": {"집객시설수": num(fc.get("VIATR_FCLTY_CO")), "지하철역수(상권경계 내)": num(fc.get("SUBWAY_STATN_CO")),
               "버스정거장수": num(fc.get("BUS_STTN_CO")), "대학수": num(fc.get("UNIV_CO")), "기준분기": fc_q,
               "지하철_주간승하차(1주)": sub if sub else "데이터 없음(상권명과 일치하는 역 없음)",
               "출처": [SRC["fclty"], SRC["subway"]]},
        "상권변화지표": {"지표": ix[cd]["TRDAR_CHNGE_IX_NM"], "코드": ix[cd]["TRDAR_CHNGE_IX"],
                   "운영영업개월_평균": num(ix[cd]["OPR_SALE_MT_AVRG"]), "폐업영업개월_평균": num(ix[cd]["CLS_SALE_MT_AVRG"]),
                   "서울_운영영업개월_평균": num(ix[cd]["SU_OPR_SALE_MT_AVRG"]), "서울_폐업영업개월_평균": num(ix[cd]["SU_CLS_SALE_MT_AVRG"]),
                   "출처": SRC["ix"]},
    }


def forecast(cd):
    r = by_cd[cd]
    return {
        "기본(가정)": {"값_억원": eok(F(r, "3년후_합산매출_전망"), 1), "적용성장률_%": pct(F(r, "전망_적용성장률"), 2),
                    "가정": "분기 합산매출(20262) × (1 + min(합산 CAGR3, 25%) × 0.7)^3",
                    "근거": f"합산 CAGR3 {pct(F(r, '합산매출_CAGR3'))}% (VwsmTrdarSelngQq 20232→20262)"},
        "보수(가정)": {"값_억원": eok(F(r, "3년후_합산매출_전망_보수"), 1), "적용성장률_%": pct(F(r, "전망_보수_적용성장률"), 2),
                    "가정": "분기 합산매출(20262) × (1 + 0.5×min(2분기 YoY 중앙값, 25%) + 0.5×서울 시장 CAGR3)^3 — 서울 시장 성장률로 평균 회귀",
                    "근거": f"2분기 YoY 중앙값 {pct(F(r, '합산_2분기YoY_중앙값'))}%, 서울 제과+커피 시장 CAGR3 {pct(ana['seoul_market_cagr3'], 2)}% (VwsmTrdarSelngQq 20232→20262 합계)"},
        "주의": "분기 매출 기준 전망이며 실제 출점 매장 매출이 아님. 2026년 3분기 이후 공표분으로 재검증 필요.",
    }


# ---------------- 후보 문장 (수치는 모두 데이터에서) ----------------
def g(cd, k):
    return F(by_cd[cd], k)


def b7(cd):
    return L(by_cd[cd], "베이커리매출_7분기")


def t7(cd):
    return L(by_cd[cd], "합산매출_7분기")


def yo(cd):
    return [pct(v) for v in L(by_cd[cd], "합산_2분기YoY_3구간")]


def nstore(cd, q, k):
    return num(stores[cd].get(q, {}).get(k, {}).get("SIMILR_INDUTY_STOR_CO"))


def per_store(cd, q):
    s = sales[cd].get(q, {}).get("bak")
    n = nstore(cd, q, "bak")
    return (s["THSMON_SELNG_AMT"] / n) if (s and n) else None


def reasons_risks(cd):
    r = by_cd[cd]
    y = yo(cd)
    if cd == "3120175":
        reasons = [
            f"같은 2분기 합산매출 YoY 3구간이 모두 플러스이면서 가속: {y[0]}% → {y[1]}% → {y[2]}% (3년 CAGR {pct(g(cd,'합산매출_CAGR3'))}%).",
            f"7개 분기 합산매출 {[eok(v,1) for v in t7(cd)]}억원, 점프비중 {round(g(cd,'점프비중'),2)}로 계단형이 아닌 누적형 성장이며 구조적 단절·마스킹 신호 없음.",
            f"베이커리 매출 {eok(b7(cd)[0],2)}억 → {eok(b7(cd)[-1],2)}억원으로 늘었는데 베이커리 점포는 {nstore(cd,Q0,'bak'):.0f} → {nstore(cd,QN,'bak'):.0f}곳으로 줄어 점포당 분기매출이 {eok(per_store(cd,Q0),2)}억 → {eok(per_store(cd,QN),2)}억원(+{pct(g(cd,'베이커리_점포당매출_변화율'))}%)으로 상승: 공급이 아닌 수요 주도 성장.",
            f"유동인구 {pct(g(cd,'유동인구_증감률'))}%로 176개 상권 중앙값({pct(MED['유동인구_증감률'])}%)을 거슬렀고, 시간대·연령 구성이 거의 같아 측정 변경보다 실증가로 판단.",
            f"평균 운영 영업개월 {num(ix[cd]['OPR_SALE_MT_AVRG']):.0f}개월(서울 {SEOUL_OPR:.0f}개월)로 기존 점포 생존력이 높음. v2 점수 {g(cd,'순위'):.0f}위(v1 {g(cd,'순위_v1'):.0f}위), 성장·리스크 두 패널이 공통 1위로 선정.",
        ]
        risks = [
            f"상권변화지표 '{ix[cd]['TRDAR_CHNGE_IX_NM']}': 성숙 상권이라 신규 진입은 기존 점포 점유율을 가져와야 함.",
            f"커피 점포 {nstore(cd,Q0,'cof'):.0f} → {nstore(cd,QN,'cof'):.0f}곳 증가, 20262 커피 폐업률 {num(stores[cd][QN]['cof']['CLSBIZ_RT']):.0f}%: 커피 단독 포맷은 포화.",
            f"합산 고객 구성이 오피스형: 주말 {pct(g(cd,'합산_주말비중'))}%(중앙값 {pct(MED['합산_주말비중'])}%), 2030 {pct(g(cd,'합산_2030비중'))}%(중앙값 {pct(MED['합산_2030비중'])}%), 객단가 {g(cd,'합산_객단가'):,.0f}원(중앙값 {MED['합산_객단가']:,.0f}원) — 프리미엄 가격 수용성은 미검증.",
            f"25→26 YoY {y[2]}%는 1개 분기 결과이고, 20254({eok(t7(cd)[4],1)}억원)처럼 분기 중 하락한 적이 있음.",
            "임대료 공공데이터 없음 → 서초권 임차료는 DART 매출 대비 비율로만 추정(데이터 없음).",
        ]
    elif cd == "3120093":
        reasons = [
            f"v2 점수 {g(cd,'순위'):.0f}위(v1 {g(cd,'순위_v1'):.0f}위). 같은 2분기 YoY 3구간 {y[0]}%, {y[1]}%, {y[2]}%로 모두 플러스, 단절 없음(점프비중 {round(g(cd,'점프비중'),2)}).",
            f"상권변화지표 '{ix[cd]['TRDAR_CHNGE_IX_NM']}' — 후보 중 유일하게 확장 국면.",
            f"타깃 적합도 최상위권: 합산 2030 {pct(g(cd,'합산_2030비중'))}%, 여성 {pct(g(cd,'합산_여성비중'))}%, 주말 {pct(g(cd,'합산_주말비중'))}%, 객단가 {g(cd,'합산_객단가'):,.0f}원(모두 176개 중앙값 초과).",
            f"베이커리 {nstore(cd,QN,'bak'):.0f}곳 중 프랜차이즈 {num(stores[cd][QN]['bak']['FRC_STOR_CO']):.0f}곳으로 개인 베이커리 중심 — 브랜드 플래그십 차별화 여지. 베이커리 점포당 매출 3년 +{pct(g(cd,'베이커리_점포당매출_변화율'))}%.",
            f"유동인구 {pct(g(cd,'유동인구_증감률'))}% 증가(시간대·연령 구성 거의 동일).",
        ]
        risks = [
            f"합산 3년 CAGR {pct(g(cd,'합산매출_CAGR3'))}%로 성장 속도는 완만, 20253 이후 {eok(t7(cd)[4],1)}억 → {eok(t7(cd)[-1],1)}억원으로 정체.",
            f"베이커리 매출 규모가 작음({eok(b7(cd)[-1],2)}억원, 점포당 {eok(per_store(cd,QN),3)}억원 vs 176 중앙값 {eok(MED['베이커리_점포당분기매출'],3)}억원) — 매출의 대부분이 커피.",
            f"표본 4개 분기 평균 폐업률 {pct(g(cd,'4분기평균_폐업률'),1)}%, 20262 커피 폐업률 {num(stores[cd][QN]['cof']['CLSBIZ_RT']):.0f}%로 회전이 큼.",
            f"오전(06~11시) 매출 비중 {pct(g(cd,'합산_오전비중'))}%로 출근길 수요가 약하고, 상권 내 지하철역 {num(latest_q(fcl_q[cd])[0].get('SUBWAY_STATN_CO')):.0f}개.",
        ]
    else:  # 3120037 동대문역사문화공원역
        reasons = [
            f"v2 점수 {g(cd,'순위'):.0f}위(v1 {g(cd,'순위_v1'):.0f}위), 리스크 패널 2위. 구조적 단절·마스킹 플래그 없음.",
            f"같은 2분기 YoY {y[0]}%, {y[1]}%, {y[2]}%, 3년 CAGR {pct(g(cd,'합산매출_CAGR3'))}%.",
            f"베이커리 매출 {eok(b7(cd)[0],2)}억 → {eok(b7(cd)[-1],2)}억원, 점포당 {eok(per_store(cd,Q0),2)}억 → {eok(per_store(cd,QN),2)}억원(+{pct(g(cd,'베이커리_점포당매출_변화율'))}%), 결제건수도 함께 증가.",
            f"베이커리 프랜차이즈 {num(stores[cd][Q0]['bak']['FRC_STOR_CO']):.0f} → {num(stores[cd][QN]['bak']['FRC_STOR_CO']):.0f}곳: 독립·전문점이 살아남는 구조.",
            f"집객시설 {num(latest_q(fcl_q[cd])[0].get('VIATR_FCLTY_CO')):.0f}개, 상권 내 지하철역 {num(latest_q(fcl_q[cd])[0].get('SUBWAY_STATN_CO')):.0f}개, 타깃적합 {pct(g(cd,'타깃적합'))}(중앙값 {pct(MED['타깃적합'])}).",
        ]
        fl = flpop[cd]
        risks = [
            f"점프비중 {round(g(cd,'점프비중'),2)}(v2 감점): 20253 {eok(t7(cd)[3],1)}억 → 20261 {eok(t7(cd)[5],1)}억원으로 분기 변동이 큼.",
            f"유동인구 20252 {fl['20252']['TOT_FLPOP_CO']:,.0f} → 20262 {fl['20262']['TOT_FLPOP_CO']:,.0f}명({pct(fl['20262']['TOT_FLPOP_CO']/fl['20252']['TOT_FLPOP_CO']-1)}%).",
            f"커피 점포 {nstore(cd,QN,'cof'):.0f}곳으로 공급이 촘촘하고 객단가 {g(cd,'합산_객단가'):,.0f}원(중앙값 {MED['합산_객단가']:,.0f}원).",
            f"상권변화지표 '{ix[cd]['TRDAR_CHNGE_IX_NM']}', 도매·패션 상권 특성상 야간·관광 수요가 섞여 객층이 일관되지 않음(관광 비중 분리 데이터 없음).",
        ]
    return reasons, risks


candidates = []
for i, cd in enumerate(CANDIDATE_CDS, 1):
    r = by_cd[cd]
    reasons, risks = reasons_risks(cd)
    candidates.append({
        "후보순위": i, "상권명": r["상권명"], "TRDAR_CD": cd, "자치구": r["자치구"], "행정동": r["행정동"],
        "상권구분": r["상권구분"], "면적_m2": F(r, "면적_m2"),
        "순위": int(F(r, "순위")), "점수": F(r, "점수"), "감점": F(r, "감점"),
        "순위_v1": int(F(r, "순위_v1")), "점수_v1": F(r, "점수_v1"),
        "지표": indicators(cd),
        "3년후_전망": forecast(cd),
        "선정이유": reasons, "리스크": risks,
        "출처": list(SRC.values()) + ["data/interim/trdar_scores.csv (scripts/analyze.py v2)"],
    })

# ---------------- 패널 이견 판정 (원천 재확인) ----------------
def post_break(cd, qa="20242"):
    t = dict(zip(SALES_Q, t7(cd)))
    return (t[QN] / t[qa]) ** (1 / 2) - 1 if t[qa] else None


def nm2cd(nm):
    return by_nm[nm]["TRDAR_CD"]


def _pr(k):
    vals = [F(r, k) if isinstance(F(r, k), float) else None for r in rows]
    xs = sorted(v for v in vals if v is not None)
    n = len(xs)
    pos = {}
    for i, v in enumerate(xs):
        pos.setdefault(v, []).append(i)
    return {r["TRDAR_CD"]: (None if v is None else st.mean(pos[v]) / (n - 1) - 0.5) for r, v in zip(rows, vals)}


PR = {k: _pr(k) for k in ana["weights"]}


def contrib_diff(a, b, top=3):
    d = []
    for k, w in ana["weights"].items():
        za, zb = PR[k][a] or 0, PR[k][b] or 0
        d.append((round(w * (za - zb), 3), k))
    d.sort(reverse=True)
    return ", ".join(f"{k} {v:+.3f}" for v, k in d[:top]) + " / 남부터미널역이 앞선 항목: " +         ", ".join(f"{k} {-v:+.3f}" for v, k in sorted(d)[:top])


adjud = []
cd = nm2cd("잠실 관광특구")
adjud.append({"상권": "잠실 관광특구", "제기": "타깃 패널 최종 1위", "판정": "후보 제외",
              "근거": f"베이커리 매출 20232 {eok(b7(cd)[0],2)}억 → 20242 {eok(b7(cd)[1],2)}억원(한 분기 단절), 같은 기간 베이커리 점포 {nstore(cd,'20232','bak'):.0f} → {nstore(cd,'20242','bak'):.0f}곳 감소. "
                    f"인접 잠실역도 같은 분기 {eok(b7(nm2cd('잠실역'))[0],2)}억 → {eok(b7(nm2cd('잠실역'))[1],2)}억원 동시 급증(영역 중복 의심). 단절 이후 20242→20262 합산 연율 {pct(post_break(cd))}%, 최근 YoY {pct(g(cd,'합산매출_YoY'))}%. "
                    f"'3년 뒤 성장' 기준에 불합격(v2 {g(cd,'순위'):.0f}위). 타깃·규모(객단가 {g(cd,'합산_객단가'):,.0f}원, 2030 {pct(g(cd,'합산_2030비중'))}%)는 우수해 2호점 이후 플래그십 검토 대상으로 보류."})
cd = nm2cd("쌍문역동측상점가")
adjud.append({"상권": "쌍문역동측상점가", "제기": "v1 1위", "판정": "제외",
              "근거": f"베이커리 20252 {eok(b7(cd)[2],2)}억 → 20253 {eok(b7(cd)[3],2)}억원 한 분기 단절, 베이커리 점포 {nstore(cd,Q0,'bak'):.0f} → {nstore(cd,QN,'bak'):.0f}곳 감소, 점포당 {eok(g(cd,'베이커리_점포당분기매출'),2)}억원(176 중앙값 {eok(MED['베이커리_점포당분기매출'],3)}억원). v2 {g(cd,'순위'):.0f}위."})
cd = nm2cd("북창동(시청역_6번)")
adjud.append({"상권": "북창동(시청역_6번)", "제기": "성장 패널 2위", "판정": "후보 제외",
              "근거": f"YoY 3구간 {yo(cd)}%로 모두 플러스이나 베이커리 20232 {eok(b7(cd)[0],2)}억 → 20242 {eok(b7(cd)[1],2)}억원 단절(점포 {nstore(cd,'20232','bak'):.0f} → {nstore(cd,'20242','bak'):.0f}곳 개업 기저효과). "
                    f"유동인구 {pct(g(cd,'유동인구_증감률'))}%, 주말 비중 {pct(g(cd,'합산_주말비중'))}%로 오피스 점심 편중. v2 {g(cd,'순위'):.0f}위."})
cd = nm2cd("종로3가역")
adjud.append({"상권": "종로3가역", "제기": "성장 패널 3위", "판정": "후보 제외(관찰 대상)",
              "근거": f"YoY 3구간 {yo(cd)}% 모두 플러스이나 점프비중 {round(g(cd,'점프비중'),2)}, 20253~20261 3분기 연속 하락({eok(t7(cd)[3],1)} → {eok(t7(cd)[5],1)}억원) 후 반등. "
                    f"베이커리 {eok(b7(cd)[0],2)}억 → {eok(b7(cd)[-1],2)}억원 정체, 베이커리 점포당 {eok(g(cd,'베이커리_점포당분기매출'),3)}억원(중앙값 미만). 커피 중심 성장이라 베이커리 복합 포맷에 불리. v2 {g(cd,'순위'):.0f}위."})
cd = nm2cd("합정역")
adjud.append({"상권": "합정역", "제기": "타깃 패널 2위", "판정": "후보 제외(관찰 대상)",
              "근거": f"YoY 3구간 {yo(cd)}%로 들쭉날쭉, 점프비중 {round(g(cd,'점프비중'),2)}. 베이커리 최근 3분기 {eok(b7(cd)[4],2)} → {eok(b7(cd)[5],2)} → {eok(b7(cd)[6],2)}억원 상승은 긍정적이나 유동인구 {pct(g(cd,'유동인구_증감률'))}%. v2 {g(cd,'순위'):.0f}위. 2026년 3·4분기 지속 시 재검토."})
cd = nm2cd("북촌(안국역)")
adjud.append({"상권": "북촌(안국역)", "제기": "타깃 패널 3위", "판정": "제외",
              "근거": f"베이커리 20242 {eok(b7(cd)[1],2)}억 → 20262 {eok(b7(cd)[-1],2)}억원 하락, 최근 YoY {pct(g(cd,'합산매출_YoY'))}%, 20232→20242 베이커리 단절. v2 {g(cd,'순위'):.0f}위."})
cd = nm2cd("여의도역(여의도)")
adjud.append({"상권": "여의도역(여의도)", "제기": "리스크 패널 3위", "판정": "후보 제외",
              "근거": f"베이커리 CAGR3 {pct(g(cd,'베이커리_CAGR3'))}%로 정체, 주말 비중 {pct(g(cd,'합산_주말비중'))}%, 커피 점포 {nstore(cd,QN,'cof'):.0f}곳 포화. v1 점수의 배후인구 가점은 직장인구 동결 데이터 효과. v2 {g(cd,'순위'):.0f}위."})
cd = nm2cd("이화사거리")
adjud.append({"상권": "이화사거리", "제기": "v2 점수 1위", "판정": "후보 제외(수석 판단으로 점수 순위 조정)",
              "근거": f"합산매출 {eok(g(cd,'합산매출_최신'),1)}억원으로 후보 규모 미달 수준이고 베이커리 점포 {nstore(cd,QN,'bak'):.0f}곳, 베이커리 매출 {eok(b7(cd)[0],2)} → {eok(b7(cd)[-1],2)}억원 감소(성장은 커피뿐). "
                    f"유동인구 {pct(g(cd,'유동인구_증감률'))}%는 시간대·연령 구성이 그대로인 채 급증해 길단위 추정 변경 의심(성장 패널 지적)."})
cd = nm2cd("서울시청")
adjud.append({"상권": "서울시청", "제기": "v2 점수 4위", "판정": "후보 제외",
              "근거": f"YoY 3구간 {yo(cd)}%로 성장이 25→26 한 구간에 집중, 베이커리 점포 {nstore(cd,QN,'bak'):.0f}곳(소수 점포 의존), 2030 비중 {pct(g(cd,'합산_2030비중'))}%로 타깃 부적합."})
cd = nm2cd("강남 마이스 관광특구")
adjud.append({"상권": "강남 마이스 관광특구", "제기": "v2 점수 5위", "판정": "제외",
              "근거": f"점프비중 {round(g(cd,'점프비중'),2)}, 베이커리 20254 {eok(b7(cd)[4],2)}억 → 20262 {eok(b7(cd)[-1],2)}억원 급감, 관광특구로 코엑스 상권과 영역 중복."})
cd = nm2cd("삼전역 1번")
adjud.append({"상권": "삼전역 1번", "제기": "v2 점수 6위", "판정": "제외",
              "근거": f"YoY 3구간 {yo(cd)}%(첫 구간 마이너스), 합산매출 {eok(g(cd,'합산매출_최신'),1)}억원 소규모, 상권변화지표 '{ix[cd]['TRDAR_CHNGE_IX_NM']}'."})
cd = nm2cd("연희동")
adjud.append({"상권": "연희동 vs 남부터미널역", "제기": "v2 점수는 연희동(2위)이 남부터미널역(3위)보다 높음", "판정": "최종은 남부터미널역",
              "근거": f"점수 차 {round(g(cd,'점수')-g(FINAL_CD,'점수'),3)}. 연희동이 앞선 항목(가중 기여 차): {contrib_diff(cd, FINAL_CD)}. 핵심인 베이커리 수요에서 남부터미널역이 우위: 베이커리 매출 {eok(b7(FINAL_CD)[-1],2)}억 vs {eok(b7(cd)[-1],2)}억원, "
                    f"점포당 {eok(per_store(FINAL_CD,QN),3)}억 vs {eok(per_store(cd,QN),3)}억원, 합산 CAGR3 {pct(g(FINAL_CD,'합산매출_CAGR3'))}% vs {pct(g(cd,'합산매출_CAGR3'))}%, 4분기 평균 폐업률 {pct(g(FINAL_CD,'4분기평균_폐업률'),1)}% vs {pct(g(cd,'4분기평균_폐업률'),1)}%."})

# ---------------- 최종 ----------------
fr = by_cd[FINAL_CD]
y = yo(FINAL_CD)
final = {
    "상권명": fr["상권명"], "TRDAR_CD": FINAL_CD, "자치구": fr["자치구"], "행정동": fr["행정동"], "상권구분": fr["상권구분"],
    "선정이유": [
        f"{fr['자치구']} {fr['상권명']}은 같은 2분기 합산매출 YoY가 {y[0]}% → {y[1]}% → {y[2]}%로 3년 연속 플러스이면서 가속하는, 구조적 단절이 없는 누적형 성장 상권이다(VwsmTrdarSelngQq 20232~20262).",
        f"베이커리 점포가 {nstore(FINAL_CD,Q0,'bak'):.0f}곳에서 {nstore(FINAL_CD,QN,'bak'):.0f}곳으로 줄었는데 베이커리 매출은 {eok(b7(FINAL_CD)[0],2)}억에서 {eok(b7(FINAL_CD)[-1],2)}억원으로 늘어, 점포당 매출이 {pct(g(FINAL_CD,'베이커리_점포당매출_변화율'))}% 오른 수요 초과 상권이다(VwsmTrdarStorQq·SelngQq).",
        f"유동인구는 {pct(g(FINAL_CD,'유동인구_증감률'))}% 늘어 서울 176개 분석 상권 중앙값({pct(MED['유동인구_증감률'])}%)과 반대로 움직였다(VwsmTrdarFlpopQq 20232→20262).",
        f"평균 운영 영업개월 {num(ix[FINAL_CD]['OPR_SALE_MT_AVRG']):.0f}개월(서울 {SEOUL_OPR:.0f}개월)로 폐업 위험이 낮고, 성장 모멘텀·리스크 두 패널이 독립적으로 1위로 꼽았으며 개선된 v2 스코어에서도 단절·감점이 없는 상위 상권이다.",
        f"커피 매출은 11~14시에 {pct(sales[FINAL_CD][QN]['cof']['TMZON_11_14_SELNG_AMT']/sales[FINAL_CD][QN]['cof']['THSMON_SELNG_AMT'])}% 몰리는 반면 베이커리는 06~11시 {pct(sales[FINAL_CD][QN]['bak']['TMZON_06_11_SELNG_AMT']/sales[FINAL_CD][QN]['bak']['THSMON_SELNG_AMT'])}%·17~21시 {pct(sales[FINAL_CD][QN]['bak']['TMZON_17_21_SELNG_AMT']/sales[FINAL_CD][QN]['bak']['THSMON_SELNG_AMT'])}%로 분산돼 복합 매장이 시간대를 메우기 좋고, 3년 후 분기 합산매출은 기본 가정 {eok(g(FINAL_CD,'3년후_합산매출_전망'),1)}억원, 보수 가정 {eok(g(FINAL_CD,'3년후_합산매출_전망_보수'),1)}억원이다(가정).",
    ],
    "반대의견과_대응": [
        {"반대의견": "타깃 패널: 잠실 관광특구가 규모·객단가·2030 비중에서 플래그십에 더 적합하다.",
         "대응": f"잠실은 20232→20242 베이커리 한 분기 단절(점포 감소 동반)로 CAGR이 부풀었고 단절 이후 연율 {pct(post_break(nm2cd('잠실 관광특구')))}%로 감소 중. '3년 뒤 성장' 과제에 맞지 않아 1호점에서 제외, 브랜드 인지 확보 후 2호점 플래그십 후보로 보류."},
        {"반대의견": f"남부터미널역은 오피스형 상권(주말 {pct(g(FINAL_CD,'합산_주말비중'))}%, 2030 {pct(g(FINAL_CD,'합산_2030비중'))}%, 객단가 {g(FINAL_CD,'합산_객단가'):,.0f}원)이라 프리미엄 타깃과 어긋난다.",
         "대응": f"베이커리 오전(06~11시) 매출 비중 {pct(g(FINAL_CD,'베이커리_오전비중'))}%·여성 비중 {pct(g(FINAL_CD,'베이커리_여성비중'))}%를 겨냥해 출근길 그랩앤고 + 테이크아웃 빵 중심으로 설계하고, 메뉴 가격은 상권 객단가 수준에서 시작(프리미엄 가격 수용성은 오픈 후 검증)."},
        {"반대의견": f"커피 점포가 {nstore(FINAL_CD,Q0,'cof'):.0f} → {nstore(FINAL_CD,QN,'cof'):.0f}곳으로 늘어 커피 경쟁이 포화다.",
         "대응": "커피 단독이 아닌 베이커리 주도 포맷으로 차별화(베이커리는 점포 감소·점포당 매출 상승 구간). 커피는 베이커리 동반 구매 중심으로 구성."},
        {"반대의견": f"25→26 YoY {y[2]}%는 한 분기 결과일 수 있고 상권변화지표가 '{ix[FINAL_CD]['TRDAR_CHNGE_IX_NM']}'이다.",
         "대응": f"손익 시뮬레이션은 보수(서울 시장 성장률로 평균 회귀, 연 {pct(g(FINAL_CD,"전망_보수_적용성장률"), 2)}%)·기준(CAGR3×0.7)·낙관 3개 시나리오를 함께 제시해 보수 시나리오의 손실 폭을 확인하고, 2026년 3분기 공표 후 재검증을 출점 게이트로 둔다."},
        {"반대의견": "서초권 임대료가 높을 수 있다.",
         "대응": "임대료 공공데이터가 없어 상권 간 비교 불가(데이터 없음). 손익에서는 DART 감사보고서의 매출 대비 임차료 비율로만 추정하고 민감도 분석으로 보완."},
    ],
    "패널합의": "성장 모멘텀 패널 1위, 리스크·경쟁 패널 1위, 타깃 적합 패널은 후보 외(잠실 관광특구 지지)",
}

# ---------------- 최종 상권 프로필 ----------------
def share_block(rec):
    amt = rec["THSMON_SELNG_AMT"]
    tm = {"06~11": rec["TMZON_06_11_SELNG_AMT"], "11~14": rec["TMZON_11_14_SELNG_AMT"], "14~17": rec["TMZON_14_17_SELNG_AMT"],
          "17~21": rec["TMZON_17_21_SELNG_AMT"], "21~24": rec["TMZON_21_24_SELNG_AMT"]}
    tm_res = amt - sum(tm.values())
    ag = {"10대": rec["AGRDE_10_SELNG_AMT"], "20대": rec["AGRDE_20_SELNG_AMT"], "30대": rec["AGRDE_30_SELNG_AMT"],
          "40대": rec["AGRDE_40_SELNG_AMT"], "50대": rec["AGRDE_50_SELNG_AMT"], "60대이상": rec["AGRDE_60_ABOVE_SELNG_AMT"]}
    sx = rec["ML_SELNG_AMT"] + rec["FML_SELNG_AMT"]
    return {
        "분기매출_억원": eok(amt, 2), "매출건수": rec["THSMON_SELNG_CO"], "객단가_원": round(amt / rec["THSMON_SELNG_CO"]) if rec["THSMON_SELNG_CO"] else None,
        "시간대비중_%": dict({k: pct(v / amt) for k, v in tm.items()},
                         **{"00~06(잔차)": pct(tm_res / amt)}),
        "시간대_주석": "API 응답에 00~06시 필드가 없어 6구간 중 00~06은 총매출-5구간 합계의 잔차로 계산",
        "연령비중_%": {k: pct(v / amt) for k, v in ag.items()},
        "성별비중_%": {"남성": pct(rec["ML_SELNG_AMT"] / amt), "여성": pct(rec["FML_SELNG_AMT"] / amt)} if sx else None,
        "성별_주석": "성별·연령 비중은 모두 총매출(THSMON_SELNG_AMT) 대비 — 176상권 중앙값·점수(analyze.py)와 같은 정의. 법인·미상 매출이 있어 남+여, 연령대 합은 100% 미만",
        "주중주말비중_%": {"주중": pct(rec["MDWK_SELNG_AMT"] / amt), "주말": pct(rec["WKEND_SELNG_AMT"] / amt)},
    }


def sum_rec(a, b):
    return {k: (a[k] + b[k]) if isinstance(a[k], float) else a[k] for k in a}


sN = sales[FINAL_CD][QN]
prof_sales = {"베이커리(제과점)": share_block(sN["bak"]), "커피-음료": share_block(sN["cof"]),
              "합산": share_block(sum_rec(sN["bak"], sN["cof"]))}
series = {}
for q in SALES_Q:
    d = sales[FINAL_CD].get(q, {})
    bk, cf = d.get("bak"), d.get("cof")
    series[q] = {"베이커리_억원": eok(bk["THSMON_SELNG_AMT"], 2) if bk else None, "베이커리_건수": bk["THSMON_SELNG_CO"] if bk else None,
                 "커피_억원": eok(cf["THSMON_SELNG_AMT"], 2) if cf else None, "커피_건수": cf["THSMON_SELNG_CO"] if cf else None,
                 "합산_억원": eok((bk["THSMON_SELNG_AMT"] if bk else 0) + (cf["THSMON_SELNG_AMT"] if cf else 0), 2)}
store_ts = {}
for q in STORE_Q:
    d = stores[FINAL_CD].get(q, {})
    store_ts[q] = {k2: {"유사업종점포": num(v.get("SIMILR_INDUTY_STOR_CO")), "일반점포": num(v.get("STOR_CO")),
                        "프랜차이즈": num(v.get("FRC_STOR_CO")), "개업률_%": num(v.get("OPBIZ_RT")), "개업점포": num(v.get("OPBIZ_STOR_CO")),
                        "폐업률_%": num(v.get("CLSBIZ_RT")), "폐업점포": num(v.get("CLSBIZ_STOR_CO"))}
                   for k2, v in (("베이커리", d.get("bak", {})), ("커피", d.get("cof", {})))}
fp = flpop[FINAL_CD][QN]
ft = fp["TOT_FLPOP_CO"]
fl_prof = {
    "기준분기": QN, "총유동인구": ft,
    "시간대비중_%": {k.replace("TMZON_", "").replace("_FLPOP_CO", "").replace("_", "~"): pct(fp[k] / ft) for k in fp if k.startswith("TMZON_")},
    "연령비중_%": {k.replace("AGRDE_", "").replace("_FLPOP_CO", "").replace("60_ABOVE", "60이상"): pct(fp[k] / ft) for k in fp if k.startswith("AGRDE_")},
    "성별비중_%": {"남성": pct(fp["ML_FLPOP_CO"] / ft), "여성": pct(fp["FML_FLPOP_CO"] / ft)},
    "요일비중_%": {k.replace("_FLPOP_CO", ""): pct(fp[k] / ft) for k in ["MON_FLPOP_CO", "TUES_FLPOP_CO", "WED_FLPOP_CO", "THUR_FLPOP_CO", "FRI_FLPOP_CO", "SAT_FLPOP_CO", "SUN_FLPOP_CO"]},
    "분기별_총유동인구": {q: flpop[FINAL_CD][q]["TOT_FLPOP_CO"] for q in STORE_Q if q in flpop[FINAL_CD]},
    "출처": SRC["flpop"],
}
final_profile = {
    "상권명": fr["상권명"], "TRDAR_CD": FINAL_CD,
    "매출프로필_20262": prof_sales, "매출프로필_출처": SRC["sales"] + " — sales_20262.json",
    "분기시계열_7분기": series, "시계열_출처": SRC["sales"],
    "점포_표본4분기": store_ts, "점포_출처": SRC["store"],
    "유동인구_20262": fl_prof,
    "상권영역": {"면적_m2": num(area[FINAL_CD]["RELM_AR"]), "X": num(area[FINAL_CD]["XCNTS_VALUE"]), "Y": num(area[FINAL_CD]["YDNTS_VALUE"]),
              "좌표계": "TbgisTrdarRelm 제공 좌표(XCNTS/YDNTS)", "출처": SRC["area"]},
}

# ---------------- method / seoul_trend ----------------
st_q = ana["seoul_trend"]
seoul_trend = {q: {"제과점_억원": eok(v["bak"], 1), "커피음료_억원": eok(v["cof"], 1), "합산_억원": eok(v["bak"] + v["cof"], 1)} for q, v in st_q.items()}
seoul_trend["_요약"] = {
    "제과점_3년증감_%(20232→20262)": pct(st_q[QN]["bak"] / st_q[Q0]["bak"] - 1),
    "커피음료_3년증감_%(20232→20262)": pct(st_q[QN]["cof"] / st_q[Q0]["cof"] - 1),
    "합산_CAGR3_%": pct(ana["seoul_market_cagr3"], 2),
    "해석": "서울 전체 시장은 정체 → 상권별 성장은 대부분 상권 간 점유율 이동. 개별 상권의 한 분기 수백% 급증은 추정·편입 효과일 가능성 높음.",
    "출처": SRC["sales"] + " — 서울 전체 상권 합계(scripts/analyze.py)",
}

n_brk = sum(1 for r in rows if F(r, "단절플래그") == 1)
n_brk30 = sum(1 for r in rows if F(r, "단절플래그") == 1 and int(F(r, "순위_v1")) <= 30)
method = {
    "설명": "서울시 상권분석서비스 공공데이터로 1,650개 상권 중 커피·베이커리 매출 규모 요건을 충족한 상권을 점수화(v2)하고, 성장 모멘텀·타깃 적합·리스크/경쟁 3개 패널의 정성 검토와 원천 시계열 재확인을 거쳐 후보 3곳과 최종 1곳을 확정.",
    "필터": f"분기 합산매출(제과점+커피-음료, 20262) 10억원 이상 & 베이커리 매출이 20232·20262 모두 공표 → {ana['eligible']}개 상권 (전체 {ana['universe']}개)",
    "기준분기": {"3년전": Q0, "1년전": Q1, "최신": QN, "시계열": SALES_Q, "점포·유동인구 표본": STORE_Q,
             "주석": "비교는 모두 2분기끼리(계절성 통제). 20232~20262 사이 7개 분기 매출로 지속성 판별"},
    "가중치_v2": ana["weights"], "감점_v2": ana["penalties"], "가중치_v1(폐기)": ana["weights_v1"],
    "점수방식": "각 지표를 176개 상권 내 백분위 순위(-0.5~+0.5)로 바꾼 뒤 가중합, 감점은 절대값 차감. 결측은 0(중앙값) 처리.",
    "v2_변경이유": ana["changes_v2"],
    "단절검출결과": f"176개 중 {n_brk}개 상권, v1 상위 30개 중 {n_brk30}개에서 한 분기 구조적 단절(베이커리 +100% 초과 또는 커피 +60% 초과 QoQ) 검출",
    "최종판정_원칙": "v2 점수 상위권을 출발점으로 하되 (1) 베이커리 수요 실체(매출·점포당 매출 추세), (2) 3개 패널 합의, (3) 측정 노이즈(유동인구 급증 시 구성 불변 등) 여부를 원천 데이터로 재확인해 수석이 조정. 조정 내역은 '패널_판정' 참조.",
    "한계": [
        "임대료 공공데이터 없음 → 상권 간 비용 차이 비교 불가. 임차료는 DART 감사보고서 매출 대비 비율로만 추정.",
        "아파트·소득소비 상권 API는 서울시 서버 500 오류로 미수집(데이터 없음).",
        "상주인구는 20234 이후, 직장인구는 20244 이후 값이 동결돼(원천에서 마지막으로 값이 바뀐 분기 기준) 배후인구 증감은 점수에서 제외(참고 표시만).",
        "추정매출은 카드 결제 기반 추정치로 소수 점포 상권은 마스킹·고정값 가능성이 있음(마스킹 의심 감점으로 일부 보정).",
        "관광특구는 발달상권과 영역이 중복될 수 있어 같은 매출이 두 번 집계될 수 있음.",
        "지하철 승하차는 2026-11-02~08 1주치만 수집(과거분 API 미제공) → 추세 분석 불가. 상권 내 지하철역 수는 경계 안만 집계.",
        "3년후 전망은 과거 성장률 외삽 '가정'이며 실제 신규 매장 매출이 아님.",
    ],
    "스크립트": ["scripts/analyze.py (v2 스코어링; v1 백업 scripts/analyze_v1_backup.py, data/interim/trdar_scores_v1.csv)",
              "scripts/build_location.py (본 파일 생성)"],
}

sources = [{"구분": "서울 열린데이터광장", "서비스": v, "용도": k} for k, v in SRC.items()] + [
    {"구분": "가공", "서비스": "data/interim/trdar_scores.csv, data/interim/analysis.json", "용도": "scripts/analyze.py v2 산출"},
]

out = {"method": method, "seoul_trend": seoul_trend, "candidates": candidates, "패널_판정": adjud,
       "final": final, "final_profile": final_profile, "sources": sources}
with open(os.path.join(INT, "location.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("saved data/interim/location.json")
for c in candidates:
    print(c["후보순위"], c["상권명"], c["TRDAR_CD"], "v2", c["순위"], c["점수"], "v1", c["순위_v1"])
print("FINAL", final["상권명"])
for s in final["선정이유"]:
    print(" -", s)
for a in adjud:
    print("*", a["상권"], a["판정"], "|", a["근거"][:160])
