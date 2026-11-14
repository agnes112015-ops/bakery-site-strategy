# -*- coding: utf-8 -*-
"""입지 재검증 v2 — 경쟁 지도(competition.json)를 반영해 남부터미널역 유지 여부를 판단한다.

입력(읽기만):
  data/interim/location.json     v1 후보·최종(점수, 시계열, 폐업률)
  data/interim/competition.json  인허가 기반 경쟁 지도(500m 업소, 프리미엄 최근접, 신규 진입)
  data/raw/sales_<분기>.json     서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq
  data/raw/store_<분기>.json     서울시 상권분석서비스 점포 VwsmTrdarStorQq
출력: data/interim/location_v2.json
실행: PYTHONIOENCODING=utf-8 python scripts/location_v2.py

핵심 수정: competition.json 의 '공식 점포수 5곳'은 VwsmTrdarStorQq 의 STOR_CO(일반점포)만 쓴 값.
          점포 총수는 SIMILR_INDUTY_STOR_CO = STOR_CO + FRC_STOR_CO(프랜차이즈) 이므로 남부터미널 제과점은 11곳
          (5 + 6 = 11, '원자료 불일치'가 아님). 점포당 매출은 11곳 기준으로 다시 계산한다.
"""
import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = lambda *a: os.path.join(ROOT, *a)
SVC = "서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq"
SVC_ST = "서울시 상권분석서비스 점포 VwsmTrdarStorQq"
LIC = "서울시 제과점영업 인허가(LOCALDATA_072218)·휴게음식점 인허가(LOCALDATA_072405) 영업 중, competition.json 경유"
BAK, COF = "CS100005", "CS100010"
Q4 = ["20253", "20254", "20261", "20262"]
QALL = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


loc = load(P("data", "interim", "location.json"))
comp = load(P("data", "interim", "competition.json"))
SALES = {q: load(P("data", "raw", f"sales_{q}.json"))["rows"] for q in QALL}
STORE = {q: load(P("data", "raw", f"store_{q}.json"))["rows"] for q in ["20232", "20242", "20252", "20262"]}


def sale(q, cd, ind=BAK):
    for r in SALES[q]:
        if str(r["TRDAR_CD"]) == cd and r["SVC_INDUTY_CD"] == ind:
            return float(r["THSMON_SELNG_AMT"])
    return None


def store(q, cd, ind=BAK):
    for r in STORE[q]:
        if str(r["TRDAR_CD"]) == cd and r["SVC_INDUTY_CD"] == ind:
            return {k: float(r[k]) for k in ("SIMILR_INDUTY_STOR_CO", "STOR_CO", "FRC_STOR_CO", "CLSBIZ_RT", "OPBIZ_RT")}
    return None


# 서울 평균 점포당 분기매출(제과점, 20262) — 분모를 SIMILR(일반+프랜차이즈)로 정정
bak_sales_62 = {str(r["TRDAR_CD"]): float(r["THSMON_SELNG_AMT"]) for r in SALES["20262"] if r["SVC_INDUTY_CD"] == BAK}
bak_store_62 = {str(r["TRDAR_CD"]): float(r["SIMILR_INDUTY_STOR_CO"]) for r in STORE["20262"] if r["SVC_INDUTY_CD"] == BAK}
common = [k for k in bak_sales_62 if k in bak_store_62 and bak_store_62[k] > 0]
seoul_per_store_q = sum(bak_sales_62[k] for k in common) / sum(bak_store_62[k] for k in common)
per_store_dist = sorted(bak_sales_62[k] / bak_store_62[k] for k in common)


def pctile(v, arr):
    return sum(1 for x in arr if x <= v) / len(arr)


comp_by = {c["TRDAR_CD"]: c for c in comp["candidates"]}
loc_by = {c["TRDAR_CD"]: c for c in loc["candidates"]}

rows = []
for cd, lc in loc_by.items():
    cc = comp_by[cd]
    s4 = sum(sale(q, cd) for q in Q4)
    c4 = sum(sale(q, cd, COF) for q in Q4)
    s7 = [sale(q, cd) for q in QALL]
    st62 = store("20262", cd)
    yoy = [s7[QALL.index(b)] / s7[QALL.index(a)] - 1 for a, b in (("20232", "20242"), ("20242", "20252"), ("20252", "20262"))]
    prem1k = [p for p in cc["프리미엄_최근접"] if p["거리m"] <= 1000]
    rows.append({
        "상권명": lc["상권명"], "TRDAR_CD": cd, "자치구": lc["자치구"], "행정동": lc["행정동"],
        "v2점수_순위": lc["순위"], "v2점수": lc["점수"],
        "제과점_연매출_최근4분기_원": s4,
        "커피_연매출_최근4분기_원": c4,
        "제과점_분기매출_7분기_원": dict(zip(QALL, s7)),
        "제과점_7분기_변동계수": st.pstdev(s7) / st.mean(s7),
        "제과점_2분기YoY_3구간": [round(x, 4) for x in yoy],
        "제과점_2분기YoY_중앙값": st.median(yoy),
        "점포_20262": st62,
        "점포당_분기매출_정정_원(SIMILR)": sale("20262", cd) / st62["SIMILR_INDUTY_STOR_CO"],
        "점포당_분기매출_competition값_원(STOR_CO만)": cc["상권분석서비스_점포당_분기매출_원"],
        "점포당_연매출_정정_원(4분기합/SIMILR)": s4 / st62["SIMILR_INDUTY_STOR_CO"],
        "점포당_분기매출_서울평균대비_배": (sale("20262", cd) / st62["SIMILR_INDUTY_STOR_CO"]) / seoul_per_store_q,
        "점포당_분기매출_서울상권_백분위": pctile(sale("20262", cd) / st62["SIMILR_INDUTY_STOR_CO"], per_store_dist),
        "인허가_500m_유형별": cc["counts_500m"],
        "인허가_500m_서울백분위": cc["500m업소수_서울1650상권_백분위"],
        "인허가_500m_평균면적_m2": cc["평균면적_m2"]["500m"],
        "최근3년_신규_500m": cc["new_entries_3y"]["500m_유형별"],
        "트렌드프리미엄_1km내": [f"{p['상호']}({p['거리m']}m)" for p in prem1k],
        "트렌드프리미엄_1km내_수": len(prem1k),
        "DART브랜드_최근접_m": cc["DART브랜드_최근접"][0]["거리m"] if cc["DART브랜드_최근접"] else None,
        "제과커피_4분기평균폐업률_%": lc["지표"]["점포"]["표본4분기_평균폐업률_%(제과+커피)"],
    })

# 스코어카드: 6개 기준 순위합(낮을수록 우위). 기준·방향은 분석자 지정 '가정'.
CRIT = [
    ("수요 규모: 제과점 연매출(최근 4분기)", "제과점_연매출_최근4분기_원", True),
    ("1곳당 몫: 점포당 분기매출(SIMILR 정정)", "점포당_분기매출_정정_원(SIMILR)", True),
    ("공급 밀도: 500m 인허가 업소수 서울 백분위", "인허가_500m_서울백분위", False),
    ("직접 경쟁: 1km 내 트렌드/프리미엄 수", "트렌드프리미엄_1km내_수", False),
    ("성장 안정성: 제과점 7분기 변동계수", "제과점_7분기_변동계수", False),
    ("생존 위험: 제과+커피 4분기 평균 폐업률", "제과커피_4분기평균폐업률_%", False),
]
score = {r["상권명"]: {} for r in rows}
for name, key, hi in CRIT:
    order = sorted(rows, key=lambda r: r[key], reverse=hi)
    for i, r in enumerate(order):
        score[r["상권명"]][name] = i + 1
for r in rows:
    r["스코어카드_순위"] = score[r["상권명"]]
    r["스코어카드_순위합"] = sum(score[r["상권명"]].values())
rows.sort(key=lambda r: r["스코어카드_순위합"])

# 남부터미널: 프리미엄 진입(아방베이커리 서초점 인허가 2025-11-21) 전후 상권 제과점 매출
nb = next(r for r in rows if r["TRDAR_CD"] == "3120175")
q = nb["제과점_분기매출_7분기_원"]
pre = (q["20252"] + q["20253"]) / 2
post = (q["20261"] + q["20262"]) / 2
entry_test = {
    "진입전_분기평균_원(20252·20253)": pre,
    "진입후_분기평균_원(20261·20262)": post,
    "분기_순증_원": post - pre,
    "연환산_순증_원": (post - pre) * 4,
    "순증률": post / pre - 1,
    "계절성_통제_동분기YoY(20252→20262)": q["20262"] / q["20252"] - 1,
    "서울_제과점시장_동분기YoY(20252→20262)": loc["seoul_trend"]["20262"]["제과점_억원"] / loc["seoul_trend"]["20252"]["제과점_억원"] - 1,
    "서울시장_대비_초과성장_pp": (q["20262"] / q["20252"] - 1) - (loc["seoul_trend"]["20262"]["제과점_억원"] / loc["seoul_trend"]["20252"]["제과점_억원"] - 1),
    "같은기간_제과점점포수(SIMILR)": {"20252": store("20252", "3120175")["SIMILR_INDUTY_STOR_CO"], "20262": nb["점포_20262"]["SIMILR_INDUTY_STOR_CO"]},
    "같은기간_반경내_신규인허가": ["아방베이커리 서초점 2025-11-21 174.11㎡ (트렌드/프리미엄)", "Be tween(비트윈) 2025-12-22 29.7㎡ (개인)", "빵드미쉘 2026-03-24 99.0㎡ (개인)"],
    "해석": "프리미엄 1곳+개인 2곳 진입 뒤 상권 제과점 매출이 분기 평균 2.0억원(+25.5%) 늘었다. 시장을 나눠 먹은 것이 아니라 키웠다 → 프리미엄 수요가 아직 덜 채워졌다는 근거. 단 2개 분기 관측이고 개별 매장 매출은 공공데이터에 없어 순증을 매장별로 나눌 수 없음(한계).",
    "출처": f"{SVC} 제과점 CS100005 20252·20253·20261·20262; {SVC_ST} 20252·20262; {LIC}",
}

verdict = {
    "결론": "남부터미널역(TRDAR_CD 3120175) 최종 입지 유지. 단 '대형 프리미엄 포맷(100㎡ 이상) + 아방베이커리와 다른 포지션'을 조건으로 건다.",
    "이유": [
        f"후보 3곳 스코어카드(6개 기준 순위합) 1위: 남부터미널 {nb['스코어카드_순위합']} vs " + ", ".join(f"{r['상권명']} {r['스코어카드_순위합']}" for r in rows if r is not nb) + ".",
        f"수요 규모 최대: 제과점 연매출(최근 4분기) {nb['제과점_연매출_최근4분기_원']/1e8:.2f}억원 — 동대문역사문화공원역 {next(r for r in rows if r['TRDAR_CD']=='3120037')['제과점_연매출_최근4분기_원']/1e8:.2f}억, 연희동 {next(r for r in rows if r['TRDAR_CD']=='3120093')['제과점_연매출_최근4분기_원']/1e8:.2f}억 ({SVC} 20253~20262).",
        f"공급은 서울 평균 수준: 500m 인허가 업소 12곳(서울 백분위 {nb['인허가_500m_서울백분위']}), 이 중 개인/독립 8곳·평균 69.7㎡ — 100㎡ 이상 브랜드 매장과 직접 겹치는 곳은 아방베이커리 서초점 1곳뿐.",
        f"첫 프리미엄 진입 뒤 시장이 커졌다: 진입 전후 분기 제과점 매출 {pre/1e8:.2f}억 → {post/1e8:.2f}억원(+{(post/pre-1)*100:.1f}%). 경쟁자가 수요를 증명한 신호로 읽는다.",
        "DART로 실체가 확인되는 트렌드 브랜드(런던베이글뮤지엄·노티드·성심당·아티제)는 1km 안에 없음(최근접 아티제 뱅뱅사거리점 1,166m).",
    ],
    "바꾸지_않는_이유(대안 검토)": {
        "동대문역사문화공원역": "정정 후 점포당 분기매출은 0.99억원으로 남부터미널(0.87억)보다 약간 높지만, 500m 업소 24곳(백분위 0.927)·1km 내 트렌드/프리미엄 2곳(롤링핀 DDP 212m, 아티제 신라성우빌딩 691m)·제과점 매출 변동이 커(20261 7.18억 → 20262 9.91억, 한 분기 +38%) 1호점 리스크가 더 크다.",
        "연희동": "트렌드 브랜드 공백은 가장 크지만 제과점 시장이 연 11.6억원으로 남부터미널의 1/3, 점포당 분기매출 0.16억원(서울 평균 미만), 개인 빵집 21곳 밀집, 4분기 평균 폐업률 7.0% — 대형 직영 포맷의 매출 기반이 부족.",
    },
    "조건(출점 게이트)": [
        "포맷: 매장 면적 약 90~110㎡(손익 가정 108㎡ = 아티제 서울 인허가 중앙 면적). interior.json 의 55㎡ 그랩앤고 안은 상권 평균 거래(일 194.9건) 기준이라 v2 기준 매출(일 약 320건)을 소화하지 못함 → 같은 산식으로 약 88㎡ 필요, 인테리어 면적 재산정 필요(pnl_v2.json area_check).",
        "비용 게이트: 기준 매출(Y1 약 8.4억원)이 손익분기(약 8.2억원)를 겨우 넘으므로 임차료는 연 0.94억원(월 약 780만원, 매출의 11.1%) 이하, 설비 투자는 4.5억원 이하로 계약해야 한다(pnl_v2.json).",
        "포지션: 아방베이커리 서초점(서리풀길 3, 174㎡)과 같은 '대형 베이커리'로 정면 승부하지 말고 오전 그랩앤고 + 퇴근길 식사빵(제과점 06~11시 22.1%, 17~21시 26.0%)으로 시간대를 나눈다.",
        "데이터 게이트: 2026년 3분기 공표분에서 제과점 분기매출이 진입 후 수준(9억원 이상)을 유지하는지 확인 — 순증이 일회성이면 기준 매출을 보수로 낮춘다.",
        "모니터링: 500m 안 두 번째 트렌드/프리미엄 인허가가 나오면 낙관 시나리오 폐기.",
    ],
    "정정_사항": "competition.json 의 '공식 점포수 5곳 / 점포당 192.1백만원 / 서울 평균 4.1배 / 원자료 불일치'는 VwsmTrdarStorQq STOR_CO(일반점포)만 분모로 쓴 오류. SIMILR_INDUTY_STOR_CO(일반 5 + 프랜차이즈 6 = 11곳) 기준 점포당 분기매출은 "
                f"{nb['점포당_분기매출_정정_원(SIMILR)']/1e6:.1f}백만원, 서울 평균 {seoul_per_store_q/1e6:.1f}백만원의 {nb['점포당_분기매출_서울평균대비_배']:.2f}배(서울 상권 백분위 {nb['점포당_분기매출_서울상권_백분위']:.3f}). 결론(1곳당 몫이 큰 상권)은 유지되나 배수는 4.1배 → {nb['점포당_분기매출_서울평균대비_배']:.1f}배로 낮아짐.",
}

final = dict(loc["final"])
final["v2_유지여부"] = "유지"
final["v2_조건"] = verdict["조건(출점 게이트)"]

out = {
    "meta": {"스크립트": "scripts/location_v2.py", "기준분기": "20262 (연매출은 20253~20262 4개 분기 합)",
             "입력": ["data/interim/location.json", "data/interim/competition.json", "data/raw/sales_*.json", "data/raw/store_*.json"],
             "서울평균_점포당_분기매출_원(SIMILR 정정)": seoul_per_store_q,
             "서울평균_산출": f"{SVC} 제과점 20262 매출 합 ÷ {SVC_ST} 20262 SIMILR_INDUTY_STOR_CO 합, 두 자료 모두 있는 {len(common)}개 상권 (관광특구·발달상권 영역 중복으로 이중계상 가능)"},
    "verdict": verdict,
    "final": final,
    "candidates": rows,
    "scorecard_기준": [{"기준": n, "지표키": k, "높을수록_우위": h} for n, k, h in CRIT],
    "scorecard_주석": "6개 기준 동일 가중 순위합(가정). 점수(v2) 순위는 참고로만 표기: 연희동 2위·남부터미널 3위·동대문 7위.",
    "competition": {
        "요약": comp["implications"],
        "남부터미널_500m_업소": [{k: s[k] for k in ("상호", "유형", "인허가일", "거리m", "면적m2")} for s in comp_by["3120175"]["stores_list"]],
        "프리미엄진입_전후검정": entry_test,
        "좌표계": comp["coord_check"]["결론"],
        "출처": LIC,
    },
    "sources": [
        {"구분": "서울 열린데이터광장", "서비스": f"{SVC} 제과점 CS100005·커피-음료 CS100010", "기준분기": QALL},
        {"구분": "서울 열린데이터광장", "서비스": f"{SVC_ST} (SIMILR_INDUTY_STOR_CO·STOR_CO·FRC_STOR_CO)", "기준분기": ["20232", "20242", "20252", "20262"]},
        {"구분": "서울 열린데이터광장", "서비스": LIC, "기준일": "수집 시점 영업 중(분석일 2026-11-14)"},
        {"구분": "내부산출", "서비스": "data/interim/location.json(v2 점수·폐업률), data/interim/competition.json(경쟁 지도)"},
    ],
}
with open(P("data", "interim", "location_v2.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("서울 평균 점포당 분기매출(SIMILR):", round(seoul_per_store_q / 1e6, 1), "백만원")
for r in rows:
    print(r["상권명"], "순위합", r["스코어카드_순위합"], r["스코어카드_순위"],
          "연매출", round(r["제과점_연매출_최근4분기_원"] / 1e8, 2), "점포당q", round(r["점포당_분기매출_정정_원(SIMILR)"] / 1e6, 1),
          "배", round(r["점포당_분기매출_서울평균대비_배"], 2), "CV", round(r["제과점_7분기_변동계수"], 3), "1km프리미엄", r["트렌드프리미엄_1km내"])
print(json.dumps(entry_test, ensure_ascii=False)[:400])
