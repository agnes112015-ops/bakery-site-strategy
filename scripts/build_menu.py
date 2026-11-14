"""메뉴 전략(F&B 메뉴 전략가): 최종 입지(남부터미널역)의 매출 프로필과 DART 비교사 원가 구조로
커피·베이커리 메뉴 포트폴리오를 설계해 data/interim/menu.json 으로 저장한다.

- 입력: data/interim/location.json, data/interim/dart_benchmark.json, data/interim/trdar_scores.csv,
        data/raw/sales_<분기>.json (VwsmTrdarSelngQq), data/interim/audit_로쏘_*.txt / audit_엘비엠_*.txt (DART 감사보고서 원문 행)
- 수치는 모두 파일에서 계산. 메뉴 가격·카테고리 믹스·카테고리별 원가율은 '제안 가정'이며 근거 수치와 계산식을 함께 기록.
실행: PYTHONIOENCODING=utf-8 python scripts/build_menu.py
"""
import csv
import json
import os
import re
import statistics as st

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RAW = os.path.join(ROOT, "data", "raw")
INT = os.path.join(ROOT, "data", "interim")
SALES_Q = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]
QN, Q0 = "20262", "20232"
SRC_SALES = "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq (제과점 CS100005·커피-음료 CS100010)"
DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


loc = jload(os.path.join(INT, "location.json"))
dart = jload(os.path.join(INT, "dart_benchmark.json"))
CD = loc["final"]["TRDAR_CD"]
NAME = loc["final"]["상권명"]
prof = loc["final_profile"]["매출프로필_20262"]


def kind(r):
    n = r.get("SVC_INDUTY_CD_NM") or ""
    return "bak" if "제과" in n else ("cof" if "커피" in n else None)


# ---------------- 1. 객단가 (THSMON_SELNG_AMT / THSMON_SELNG_CO) ----------------
scores = list(csv.DictReader(open(os.path.join(INT, "trdar_scores.csv"), encoding="utf-8-sig")))
cds176 = {r["TRDAR_CD"] for r in scores}
ticket = {}          # q -> {bak, cof, all} for final 상권
seoul = {}           # q -> {bak, cof} 서울 전체
med176 = {}
for q in SALES_Q:
    rows = jload(os.path.join(RAW, f"sales_{q}.json"))["rows"]
    agg = {"bak": [0.0, 0.0], "cof": [0.0, 0.0]}
    per = {}
    for r in rows:
        k = kind(r)
        if not k:
            continue
        a, c = float(r["THSMON_SELNG_AMT"] or 0), float(r["THSMON_SELNG_CO"] or 0)
        agg[k][0] += a
        agg[k][1] += c
        per.setdefault(r["TRDAR_CD"], {})[k] = (a, c)
    seoul[q] = {k: agg[k][0] / agg[k][1] for k in agg}
    m = per.get(CD, {})
    ba, bc = m.get("bak", (0, 0))
    ca, cc = m.get("cof", (0, 0))
    ticket[q] = {"bak": ba / bc if bc else None, "cof": ca / cc if cc else None,
                 "all": (ba + ca) / (bc + cc) if (bc + cc) else None,
                 "bak_amt": ba, "bak_co": bc, "cof_amt": ca, "cof_co": cc}
    if q == QN:
        med176 = {k: st.median([v[k][0] / v[k][1] for cd, v in per.items()
                                if cd in cds176 and k in v and v[k][1] > 0]) for k in ("bak", "cof")}

tN, t0 = ticket[QN], ticket[Q0]
tk_bak_chg = tN["bak"] / t0["bak"] - 1
tk_cof_chg = tN["cof"] / t0["cof"] - 1

# ---------------- 2. DART 원재료 비율 ----------------
def raw_ratio(name):
    d = dart[name]
    if "원재료·상품" in d["costs"]:
        mat = sum(d["costs"]["원재료·상품"])
        basis = "비용의 성격별 분류 '원재료·상품'(재고변동 포함) ÷ 매출액"
    else:
        mat = sum(d["costs"]["매출원가"])
        basis = "매출원가 ÷ 매출액 (성격별 분류 미공시 → 매출원가 전체, 원재료비율 상한)"
    return {"회사": name, "브랜드": d["brand"], "rcept_no": d["rcept_no"], "매출액_천원": d["revenue"],
            "원재료_천원": mat, "비율_%": round(100 * mat / d["revenue"], 1), "산식": basis,
            "url": DART_URL.format(d["rcept_no"])}


dart_ratios = {n: raw_ratio(n) for n in ["에스씨케이컴퍼니", "투썸플레이스", "CJ푸드빌", "이디야"]}


def audit_residual(fname, rev_pat, cogs_pat, tot_pat):
    """직영 베이커리 감사보고서: (매출원가 − 매출원가에 배부된 주요 비용 합계) ÷ 매출액 = 원재료+기타제조경비 상한."""
    txt = open(os.path.join(INT, fname), encoding="utf-8").read()
    n = lambda s: float(s.replace(",", ""))
    rev = n(re.search(rev_pat, txt).group(1))            # 원
    cogs = n(re.search(cogs_pat, txt).group(1))          # 원
    mfg = n(re.search(tot_pat, txt).group(1)) * 1000     # 천원 → 원
    rno = re.search(r"_(\d{14})\.txt$", fname).group(1)
    return {"매출액_원": rev, "매출원가_원": cogs, "매출원가중_인건비등_원": mfg,
            "잔차비율_%": round(100 * (cogs - mfg) / rev, 1), "매출원가율_%": round(100 * cogs / rev, 1),
            "rcept_no": rno, "url": DART_URL.format(rno)}


rosso = audit_residual("audit_로쏘_20260410000434.txt", r"Ⅰ\.매출액 \|  \| ([\d,]+)", r"Ⅱ\.매출원가 \|  \| ([\d,]+)",
                       r"제조원가 \| 판매비와 관리비 \| 합 계[\s\S]*?합 계 \| ([\d,]+)")
lbm = audit_residual("audit_엘비엠_20260326000290.txt", r"Ⅰ\. 매출액 \|  \| ([\d,]+)", r"Ⅱ\. 매출원가 \|  \| ([\d,]+)",
                     r"매출원가 \| 판매관리비 \| 합 계[\s\S]*?합 계 \| ([\d,]+)")

# ---------------- 3. 카테고리 믹스·원가율 (제안 가정) ----------------
area_bak_share = tN["bak_amt"] / (tN["bak_amt"] + tN["cof_amt"])
sbx, tws, cjf = (dart_ratios[n]["비율_%"] for n in ["에스씨케이컴퍼니", "투썸플레이스", "CJ푸드빌"])
mix = [
    {"카테고리": "커피", "매출비중_%": 38, "원가율_가정_%": sbx,
     "원가율_근거": f"스타벅스(에스씨케이컴퍼니, 전 매장 직영) 원재료·상품 비율 {sbx}% 적용"},
    {"카테고리": "음료(논커피)", "매출비중_%": 10, "원가율_가정_%": sbx,
     "원가율_근거": f"음료 카테고리 동일하게 스타벅스 {sbx}% 적용(공공데이터상 커피/논커피 구분 매출 데이터 없음)"},
    {"카테고리": "베이커리", "매출비중_%": 32, "원가율_가정_%": rosso["잔차비율_%"],
     "원가율_근거": f"베이커리 제조·판매사 로쏘 주식회사 감사보고서 (매출원가−매출원가 배부 인건비 등)/매출 = {rosso['잔차비율_%']}% (원재료+기타제조경비 상한, 보수적 적용). 참고 하한: 엘비엠 {lbm['잔차비율_%']}%"},
    {"카테고리": "디저트", "매출비중_%": 10, "원가율_가정_%": rosso["잔차비율_%"],
     "원가율_근거": f"베이커리와 같은 제조 라인 → 로쏘 잔차비율 {rosso['잔차비율_%']}% 적용"},
    {"카테고리": "델리", "매출비중_%": 10, "원가율_가정_%": cjf,
     "원가율_근거": f"샌드위치 등 육가공·유제품 원재료 비중이 커 상한값인 CJ푸드빌 원재료·상품 비율 {cjf}% 적용(가맹 도매 포함으로 점포 원가보다 높게 잡힘)"},
]
assert sum(m["매출비중_%"] for m in mix) == 100
food_share = sum(m["매출비중_%"] for m in mix if m["카테고리"] in ("베이커리", "디저트", "델리")) / 100
bev_share = 1 - food_share
for m in mix:
    m["상권_실적_대비"] = (f"상권 베이커리(제과점) 매출 비중 {round(100*area_bak_share,1)}% vs 커피-음료 {round(100*(1-area_bak_share),1)}% ({SRC_SALES}, {QN})")
blended = round(sum(m["매출비중_%"] * m["원가율_가정_%"] for m in mix) / 100, 1)

# ---------------- 4. 제안 객단가 (가정) ----------------
# 음료·푸드 매출 비중을 상권 커피·제과점 객단가에 매칭한 '매출가중 조화평균' = 총매출/총건수와 동일한 구조
proposed_raw = 1 / (bev_share / tN["cof"] + food_share / tN["bak"])
proposed = int(round(proposed_raw, -2))

# ---------------- 5. 시간대·고객 프로필 ----------------
bk, cf, al = prof["베이커리(제과점)"], prof["커피-음료"], prof["합산"]
tz = ["06~11", "11~14", "14~17", "17~21", "21~24"]

dayparts = [
    {"시간대": "06~11 출근길", "상권_합산매출비중_%": al["시간대비중_%"]["06~11"],
     "베이커리_%": bk["시간대비중_%"]["06~11"], "커피_%": cf["시간대비중_%"]["06~11"],
     "히어로": "모닝 세트(아메리카노 + 소금버터롤 또는 크루아상)",
     "운영": "07시 오픈, 계산대 앞 그랩앤고 진열, 전일 예약 픽업",
     "근거": "베이커리 매출의 오전 비중과 커피 오전 비중이 모두 20%대 → 커피+빵 결합 구매 유도"},
    {"시간대": "11~14 점심", "상권_합산매출비중_%": al["시간대비중_%"]["11~14"],
     "베이커리_%": bk["시간대비중_%"]["11~14"], "커피_%": cf["시간대비중_%"]["11~14"],
     "히어로": "델리 샌드위치 + 커피 런치 콤보, 식후 아이스 아메리카노",
     "운영": "샌드위치 사전 제조·포장, 커피 바 2라인 운영으로 피크 대기 단축",
     "근거": f"커피 매출의 최대 피크(직장인구 {int(loc['candidates'][0]['지표']['인구']['직장인구']):,}명, 주중 비중 {al['주중주말비중_%']['주중']}%) → 식사 대용 델리로 객단가 상향"},
    {"시간대": "14~17 오후", "상권_합산매출비중_%": al["시간대비중_%"]["14~17"],
     "베이커리_%": bk["시간대비중_%"]["14~17"], "커피_%": cf["시간대비중_%"]["14~17"],
     "히어로": "조각 치즈케이크·휘낭시에 + 논커피 음료(말차라떼·밀크티)",
     "운영": "디저트 쇼케이스 전면 배치, 사무실 단체 주문(박스) 대응",
     "근거": "베이커리 비중이 커피보다 높은 시간대 → 디저트·논커피로 커피 외 수요 흡수"},
    {"시간대": "17~21 퇴근길", "상권_합산매출비중_%": al["시간대비중_%"]["17~21"],
     "베이커리_%": bk["시간대비중_%"]["17~21"], "커피_%": cf["시간대비중_%"]["17~21"],
     "히어로": "테이크아웃 식사빵(우유식빵·캄파뉴) — 17시 2차 굽기",
     "운영": "17시 식사빵 2차 출고, 내일 아침용 묶음 판매",
     "근거": f"베이커리 매출의 {bk['시간대비중_%']['17~21']}%가 이 시간대(커피는 {cf['시간대비중_%']['17~21']}%) → 매장 매출을 저녁까지 끌고 가는 빵 수요"},
    {"시간대": "21~24 심야", "상권_합산매출비중_%": al["시간대비중_%"]["21~24"],
     "베이커리_%": bk["시간대비중_%"]["21~24"], "커피_%": cf["시간대비중_%"]["21~24"],
     "히어로": "없음(21시 마감 제안)",
     "운영": "잔여 빵은 마감 전 세트화, 심야 영업 없음",
     "근거": "합산 매출 비중이 한 자릿수 초반 → 인건비 대비 실익 낮음(가정)"},
    {"시간대": "주말", "상권_합산매출비중_%": al["주중주말비중_%"]["주말"],
     "베이커리_%": bk["주중주말비중_%"]["주말"], "커피_%": cf["주중주말비중_%"]["주말"],
     "히어로": "홀케이크·선물용 구움과자 박스(예약제)",
     "운영": "주말은 예약 픽업 위주, 좌석 회전보다 테이크아웃",
     "근거": f"베이커리 주말 비중({bk['주중주말비중_%']['주말']}%)이 커피({cf['주중주말비중_%']['주말']}%)보다 높고 베이커리 구매 60대 이상 비중 {bk['연령비중_%']['60대이상']}% → 가족·선물 수요"},
]

P = "제안 가정(외부 시세 미인용; 상권 객단가 기준 설계)"
items = [
    # 커피
    {"카테고리": "커피", "메뉴": "아메리카노", "설명": "기본 블렌드, 모닝 세트·런치 콤보의 베이스", "가격_원": 4300, "가격근거": P},
    {"카테고리": "커피", "메뉴": "카페라떼", "설명": "우유 라떼, 30대 직장인 주력", "가격_원": 4900, "가격근거": P},
    {"카테고리": "커피", "메뉴": "콜드브루", "설명": "점심 피크 대기 단축용 사전 추출", "가격_원": 4900, "가격근거": P},
    {"카테고리": "커피", "메뉴": "시그니처 흑임자 크림라떼", "설명": "매장 시그니처, 디저트 동반 구매용", "가격_원": 5800, "가격근거": P},
    # 음료
    {"카테고리": "음료(논커피)", "메뉴": "말차 라떼", "설명": "오후 시간대 논커피 대표", "가격_원": 5500, "가격근거": P},
    {"카테고리": "음료(논커피)", "메뉴": "얼그레이 밀크티", "설명": "디저트 페어링용", "가격_원": 5500, "가격근거": P},
    {"카테고리": "음료(논커피)", "메뉴": "제철 과일 에이드", "설명": "계절 한정, 주말·오후 수요", "가격_원": 5800, "가격근거": P},
    # 베이커리
    {"카테고리": "베이커리", "메뉴": "소금버터롤", "설명": "출근길 그랩앤고 히어로, 하루 3회 굽기", "가격_원": 3200, "가격근거": P},
    {"카테고리": "베이커리", "메뉴": "버터 크루아상", "설명": "모닝 세트 선택지", "가격_원": 4200, "가격근거": P},
    {"카테고리": "베이커리", "메뉴": "우유식빵(1봉)", "설명": "퇴근길 테이크아웃 식사빵, 17시 2차 출고", "가격_원": 5800, "가격근거": P},
    {"카테고리": "베이커리", "메뉴": "통밀 캄파뉴", "설명": "40~60대 식사빵 수요, 반 개 판매 병행", "가격_원": 7500, "가격근거": P},
    # 디저트
    {"카테고리": "디저트", "메뉴": "바스크 치즈케이크(조각)", "설명": "오후 히어로 디저트", "가격_원": 6500, "가격근거": P},
    {"카테고리": "디저트", "메뉴": "휘낭시에 3종", "설명": "선물 박스 구성용 구움과자", "가격_원": 3000, "가격근거": P},
    {"카테고리": "디저트", "메뉴": "시즌 홀케이크(예약)", "설명": "주말·기념일 예약 픽업", "가격_원": 32000, "가격근거": P},
    # 델리
    {"카테고리": "델리", "메뉴": "잠봉뵈르 샌드위치", "설명": "자사 바게트 사용, 점심 대표", "가격_원": 8500, "가격근거": P},
    {"카테고리": "델리", "메뉴": "에그 샐러드 샌드위치", "설명": "식빵 활용, 오전·점심 겸용", "가격_원": 6900, "가격근거": P},
    {"카테고리": "델리", "메뉴": "오늘의 수프 + 캄파뉴", "설명": "점심 식사 대용, 쌀쌀한 계절 강화", "가격_원": 9500, "가격근거": P},
    # 세트
    {"카테고리": "세트", "메뉴": "모닝 세트(아메리카노+소금버터롤)", "설명": "06~11시 한정", "가격_원": 6900, "가격근거": P},
    {"카테고리": "세트", "메뉴": "런치 콤보(샌드위치+아메리카노)", "설명": "11~14시 한정", "가격_원": 11500, "가격근거": P},
]

# 가격 설계 점검: 음료 단품 가격 ≤ 상권 커피 객단가, 세트 가격 ≈ 제안 객단가 범위
bev_prices = [i["가격_원"] for i in items if i["카테고리"] in ("커피", "음료(논커피)")]
price_check = {
    "음료_단품_가격범위_원": [min(bev_prices), max(bev_prices)],
    "상권_커피_객단가_원": round(tN["cof"]),
    "점검": "음료 단품 최고가가 상권 커피 객단가 이하 → 1잔 구매 시 상권 평균 결제액 수준, 빵 동반 시 제안 객단가로 상향",
    "모닝세트_대비_제안객단가_%": round(100 * 6900 / proposed, 1),
}
assert max(bev_prices) <= tN["cof"] + 100

# ---------------- 6. 근거 ----------------
s = lambda q: f"{SRC_SALES}, {q}"
dsrc = lambda n: (f"DART {dart_ratios[n]['회사']} 2025 감사보고서 "
                  + ("손익계산서 매출원가(성격별 분류 미공시)" if "매출원가" in dart[n]["costs"] else "비용의 성격별 분류")
                  + f", rcept_no {dart_ratios[n]['rcept_no']} ({dart_ratios[n]['url']})")
evidence = [
    {"claim": f"{NAME} 제과점 객단가(분기 매출금액/매출건수)", "number": f"{round(tN['bak']):,}원", "source": s(QN)},
    {"claim": f"{NAME} 커피-음료 객단가", "number": f"{round(tN['cof']):,}원", "source": s(QN)},
    {"claim": f"{NAME} 제과점+커피 합산 객단가", "number": f"{round(tN['all']):,}원", "source": s(QN)},
    {"claim": f"{NAME} 제과점 객단가 3년 변화({Q0}→{QN})", "number": f"{round(t0['bak']):,}원 → {round(tN['bak']):,}원 ({round(100*tk_bak_chg,1)}%)", "source": s(f"{Q0}·{QN}")},
    {"claim": f"{NAME} 커피 객단가 3년 변화({Q0}→{QN})", "number": f"{round(t0['cof']):,}원 → {round(tN['cof']):,}원 ({round(100*tk_cof_chg,1)}%)", "source": s(f"{Q0}·{QN}")},
    {"claim": "서울 전체 제과점 / 커피 객단가", "number": f"{round(seoul[QN]['bak']):,}원 / {round(seoul[QN]['cof']):,}원", "source": s(QN) + " 서울 전체 합계"},
    {"claim": "분석 176개 상권 객단가 중앙값 제과점 / 커피", "number": f"{round(med176['bak']):,}원 / {round(med176['cof']):,}원", "source": s(QN) + " (data/interim/trdar_scores.csv 176개 상권)"},
    {"claim": f"{NAME} 매출 중 제과점 비중", "number": f"{round(100*area_bak_share,1)}%", "source": s(QN)},
    {"claim": "베이커리 시간대 비중 06~11 / 17~21", "number": f"{bk['시간대비중_%']['06~11']}% / {bk['시간대비중_%']['17~21']}%", "source": s(QN)},
    {"claim": "커피 11~14시 매출 비중", "number": f"{cf['시간대비중_%']['11~14']}%", "source": s(QN)},
    {"claim": "베이커리 여성 매출 비중 / 커피 남성 매출 비중", "number": f"{bk['성별비중_%']['여성']}% / {cf['성별비중_%']['남성']}% (총매출 대비)", "source": s(QN)},
    {"claim": "주말 매출 비중 베이커리 / 커피", "number": f"{bk['주중주말비중_%']['주말']}% / {cf['주중주말비중_%']['주말']}%", "source": s(QN)},
    {"claim": "베이커리 매출 60대 이상 비중 / 커피 30대 비중", "number": f"{bk['연령비중_%']['60대이상']}% / {cf['연령비중_%']['30대']}%", "source": s(QN)},
    {"claim": "스타벅스(직영) 원재료·상품 ÷ 매출", "number": f"{sbx}%", "source": dsrc("에스씨케이컴퍼니")},
    {"claim": "투썸플레이스 원재료·상품 ÷ 매출(가맹 공급 포함)", "number": f"{tws}%", "source": dsrc("투썸플레이스")},
    {"claim": "CJ푸드빌(뚜레쥬르 등) 원재료·상품 ÷ 매출(가맹 공급 포함)", "number": f"{cjf}%", "source": dsrc("CJ푸드빌")},
    {"claim": "이디야 매출원가 ÷ 매출(성격별 분류 미공시, 상한)", "number": f"{dart_ratios['이디야']['비율_%']}%", "source": dsrc("이디야")},
    {"claim": "로쏘 주식회사(베이커리 제조·판매) (매출원가−매출원가 배부 인건비·임차료·감가상각 등) ÷ 매출", "number": f"{rosso['잔차비율_%']}% (매출원가율 {rosso['매출원가율_%']}%)", "source": f"DART 로쏘 2025 감사보고서, rcept_no {rosso['rcept_no']} ({rosso['url']})"},
    {"claim": "엘비엠(베이커리 제조·판매) 같은 산식", "number": f"{lbm['잔차비율_%']}% (매출원가율 {lbm['매출원가율_%']}%)", "source": f"DART 엘비엠 2025 감사보고서, rcept_no {lbm['rcept_no']} ({lbm['url']})"},
]

out = {
    "상권": {"상권명": NAME, "TRDAR_CD": CD, "기준분기": QN},
    "mix": mix,
    "mix_요약": {"음료계_%": round(100 * bev_share), "푸드계(베이커리+디저트+델리)_%": round(100 * food_share),
                "상권_실적_제과점비중_%": round(100 * area_bak_share, 1),
                "설계논리": "상권은 커피 매출이 압도적이지만 커피 점포가 49→55곳으로 늘어 포화, 베이커리는 점포가 13→11곳으로 줄면서 매출이 늘어 점포당 매출 +53.1%(location.json) → 푸드계 비중을 상권 실적보다 높인 베이커리 주도 포맷(가정).",
                "주의": "공공데이터는 제과점/커피-음료 두 업종만 구분 → 커피·논커피, 베이커리·디저트·델리 세부 비중은 데이터 없음, 전부 가정"},
    "dayparts": dayparts,
    "items": items,
    "price_check": price_check,
    "target_cogs_ratio": {
        "목표_%": blended,
        "운영목표_%": 32,
        "계산식": "Σ(카테고리 매출비중 × 카테고리 원가율 가정) = " + " + ".join(f"{m['매출비중_%']}%×{m['원가율_가정_%']}%" for m in mix) + f" = {blended}%",
        "DART_벤치마크_%": {n: v["비율_%"] for n, v in dart_ratios.items()},
        "베이커리제조사_잔차_%": {"로쏘": rosso["잔차비율_%"], "엘비엠": lbm["잔차비율_%"]},
        "해석": f"직영 커피 중심 스타벅스 {sbx}%보다 높고, 가맹 공급 매출이 섞인 투썸 {tws}%·CJ푸드빌 {cjf}%보다 낮은 범위. 베이커리 비중이 높아 스타벅스보다 원가가 높게 설계됨. 투썸·CJ는 가맹점에 원재료를 공급한 매출·원가가 포함돼 단일 직영점 원가율로 그대로 쓰기 어려움.",
        "주의": "로쏘·엘비엠 잔차비율은 원재료 외 기타 제조경비가 섞인 상한값. 카테고리별 실제 원가는 레시피 확정 후 검증 필요(가정).",
    },
    "avg_ticket": {
        "상권_제과점": round(tN["bak"]),
        "상권_커피": round(tN["cof"]),
        "상권_합산": round(tN["all"]),
        "서울전체_제과점": round(seoul[QN]["bak"]),
        "서울전체_커피": round(seoul[QN]["cof"]),
        "176상권중앙값_제과점": round(med176["bak"]),
        "176상권중앙값_커피": round(med176["cof"]),
        "추이_상권": {q: {"제과점": round(v["bak"]) if v["bak"] else None, "커피": round(v["cof"]) if v["cof"] else None,
                       "합산": round(v["all"]) if v["all"] else None} for q, v in ticket.items()},
        "제안": proposed,
        "제안_구분": "가정",
        "계산식": (f"상권 객단가 = THSMON_SELNG_AMT / THSMON_SELNG_CO ({QN}): 제과점 {tN['bak_amt']:,.0f}/{tN['bak_co']:,.0f} = {tN['bak']:,.0f}원, "
                  f"커피 {tN['cof_amt']:,.0f}/{tN['cof_co']:,.0f} = {tN['cof']:,.0f}원. "
                  f"제안 = 1 / (음료계 비중 {bev_share:.2f} / 커피 객단가 {tN['cof']:,.0f} + 푸드계 비중 {food_share:.2f} / 제과점 객단가 {tN['bak']:,.0f}) "
                  f"= {proposed_raw:,.0f}원 → 100원 반올림 {proposed:,}원 (매출가중 조화평균: 목표 믹스대로 팔릴 때 결제 1건당 평균액)"),
        "근거": f"상권 합산 객단가 {round(tN['all']):,}원은 커피 비중이 높아 낮게 잡힘. 푸드계 비중을 {round(100*food_share)}%로 높이면 같은 상권 단가 구조에서 {proposed:,}원. 상권 제과점 객단가가 3년간 {round(100*tk_bak_chg,1)}% 올라 빵 가격 수용성은 확인되나, 프리미엄 가격 추가 인상분은 반영하지 않음(오픈 후 검증).",
    },
    "evidence": evidence,
    "한계": [
        "추정매출은 카드 결제 기반 추정치로 1건에 여러 품목이 포함될 수 있음(품목 단가 아님).",
        "공공데이터에 품목·카테고리별 매출, 메뉴 가격 데이터 없음 → 메뉴 가격과 세부 믹스는 모두 제안 가정.",
        "DART 원재료비율은 회사 전체(가맹 공급·상품 판매 포함) 기준으로 단일 매장 원가와 다를 수 있음.",
    ],
    "스크립트": "scripts/build_menu.py",
}
with open(os.path.join(INT, "menu.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps({"ticket": out["avg_ticket"], "cogs": out["target_cogs_ratio"], "rosso": rosso, "lbm": lbm}, ensure_ascii=False, indent=1))
