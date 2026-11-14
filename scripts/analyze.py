"""상권 스코어링: 서울시 상권분석서비스(공공) 데이터만으로 '3년 뒤 성장할 베이커리·카페 상권'을 도출한다.
출력: data/interim/trdar_scores.csv, data/interim/analysis.json
"""
import csv
import json
import math
import os
import statistics as st
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW = os.path.join(ROOT, "data", "raw")
INT = os.path.join(ROOT, "data", "interim")
os.makedirs(INT, exist_ok=True)

Q0, Q1, QN = "20232", "20252", "20262"   # 3년 전 / 1년 전 / 최신 (모두 2분기 → 계절성 제거)
SALES_Q = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]


def load(name):
    with open(os.path.join(RAW, name + ".json"), encoding="utf-8") as f:
        return json.load(f)["rows"]


def is_bakery(r):
    return "제과" in (r.get("SVC_INDUTY_CD_NM") or "")


def is_coffee(r):
    return "커피" in (r.get("SVC_INDUTY_CD_NM") or "")


def num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def zs(values):
    """백분위 순위 점수(-0.5~+0.5): 극단값(기저효과)에 강건."""
    xs = sorted(v for v in values if v is not None)
    n = len(xs)
    if n < 2:
        return [None for _ in values]
    rank = {}
    for i, v in enumerate(xs):
        rank.setdefault(v, []).append(i)
    return [None if v is None else (st.mean(rank[v]) / (n - 1) - 0.5) for v in values]


CHANGES_V2 = [
    "성장 지표를 시작·끝점 CAGR/YoY에서 같은 2분기 YoY 3구간(23→24, 24→25, 25→26)의 중앙값과 플러스 구간 수로 교체: 한 분기 계단 점프가 CAGR을 지배하던 문제(쌍문·잠실·상봉 등) 완화.",
    "구조적 단절(한 분기 베이커리 +100% 초과 또는 커피 +60% 초과) -0.15, 점프비중(최대 단일분기 증가/3년 증가분) 0.6 이상 -0.10, 베이커리 7분기 CV 3% 미만(마스킹 의심) -0.10 감점.",
    "배후인구 증감률(0.10) 제거: 상주인구는 20234 이후, 직장인구는 20244 이후 전 상권 값이 동결돼 있어 데이터 갱신 시점 차이를 측정하는 지표였음.",
    "베이커리 점포당 분기매출 '수준'(0.12) 대신 3년 '변화율'(점포 3곳 이상만)로 교체: 소수 점포 집중·마스킹 상권 우대 방지.",
    "타깃 적합(제과+커피 합산 2030·여성·주말 비중 평균) 0.10, 객단가 0.05, 합산매출 규모 0.05 추가: 기존엔 제과점 2030 비중 하나뿐이었음.",
    "단일 분기 베이커리 폐업률(-0.08) 대신 표본 4개 분기 평균 폐업률(-0.07), 커피 점포 증감률(-0.06, 공급 포화), 평균 운영 영업개월(+0.07), 상권변화지표 '상권축소' -0.10 감점 추가.",
    "3년후 전망에 보수 시나리오 추가: 0.5×min(2분기 YoY 중앙값, 25%) + 0.5×서울 제과+커피 시장 3년 CAGR (가정, 평균 회귀).",
]


def cagr(a, b, years):
    if a <= 0 or b <= 0:
        return None
    return (b / a) ** (1 / years) - 1


def main():
    area = {r["TRDAR_CD"]: r for r in load("trdar_area")}
    ix = {r["TRDAR_CD"]: r for r in load("trdar_ix_20262")}

    # 매출: 상권 × 분기 × 업종
    sales = defaultdict(lambda: defaultdict(lambda: {"bak": 0.0, "cof": 0.0, "bak_cnt": 0.0, "cof_cnt": 0.0}))
    profile = {}  # 최신 분기 베이커리 매출 프로필
    combo = {}    # 최신 분기 제과+커피 합산 고객 구성
    for q in SALES_Q:
        for r in load(f"sales_{q}"):
            c = sales[r["TRDAR_CD"]][q]
            amt, cnt = num(r["THSMON_SELNG_AMT"]), num(r["THSMON_SELNG_CO"])
            if is_bakery(r):
                c["bak"] += amt; c["bak_cnt"] += cnt
                if q == QN:
                    profile[r["TRDAR_CD"]] = r
            elif is_coffee(r):
                c["cof"] += amt; c["cof_cnt"] += cnt
            if q == QN and (is_bakery(r) or is_coffee(r)):
                m = combo.setdefault(r["TRDAR_CD"], {"amt": 0.0, "cnt": 0.0, "a20": 0.0, "a30": 0.0,
                                                     "fml": 0.0, "wk": 0.0, "t0611": 0.0})
                m["amt"] += amt; m["cnt"] += cnt
                m["a20"] += num(r.get("AGRDE_20_SELNG_AMT")); m["a30"] += num(r.get("AGRDE_30_SELNG_AMT"))
                m["fml"] += num(r.get("FML_SELNG_AMT")); m["wk"] += num(r.get("WKEND_SELNG_AMT"))
                m["t0611"] += num(r.get("TMZON_06_11_SELNG_AMT"))

    # 점포
    stores = defaultdict(dict)
    for q in ["20232", "20242", "20252", "20262"]:
        for r in load(f"store_{q}"):
            k = "bak" if is_bakery(r) else "cof"
            stores[r["TRDAR_CD"]][(q, k)] = r

    # 유동인구
    flpop = defaultdict(dict)
    for q in ["20232", "20242", "20252", "20262"]:
        for r in load(f"flpop_{q}"):
            flpop[r["TRDAR_CD"]][q] = r

    def by_q(name, field):
        d = defaultdict(dict)
        for r in load(name):
            d[r["TRDAR_CD"]][r["STDR_YYQU_CD"]] = r
        return d

    repop = by_q("repop_all", "TOT_REPOP_CO")
    wrc = by_q("wrcpop_all", "TOT_WRC_POPLTN_CO")
    fcl = by_q("fclty_all", "")

    def latest(d, upto=QN):
        qs = sorted(q for q in d if q <= upto)
        return d[qs[-1]] if qs else None, (qs[-1] if qs else None)

    def at_or_before(d, q):
        qs = sorted(x for x in d if x <= q)
        return d[qs[-1]] if qs else None

    rows = []
    for cd, a in area.items():
        s = sales.get(cd, {})
        bN, b0, b1 = s.get(QN, {}).get("bak", 0), s.get(Q0, {}).get("bak", 0), s.get(Q1, {}).get("bak", 0)
        cN, c0, c1 = s.get(QN, {}).get("cof", 0), s.get(Q0, {}).get("cof", 0), s.get(Q1, {}).get("cof", 0)
        tN, t0, t1 = bN + cN, b0 + c0, b1 + c1
        stN = stores[cd].get((QN, "bak"), {})
        st0 = stores[cd].get((Q0, "bak"), {})
        cstN = stores[cd].get((QN, "cof"), {})
        nb_N, nb_0 = num(stN.get("SIMILR_INDUTY_STOR_CO")), num(st0.get("SIMILR_INDUTY_STOR_CO"))
        nc_N = num(cstN.get("SIMILR_INDUTY_STOR_CO"))
        fN, f0 = num(flpop[cd].get(QN, {}).get("TOT_FLPOP_CO")), num(flpop[cd].get(Q0, {}).get("TOT_FLPOP_CO"))
        rN, r0 = at_or_before(repop.get(cd, {}), QN), at_or_before(repop.get(cd, {}), Q0)
        wN, w0 = at_or_before(wrc.get(cd, {}), QN), at_or_before(wrc.get(cd, {}), Q0)
        fc = at_or_before(fcl.get(cd, {}), QN) or {}
        p = profile.get(cd, {})
        bak_amt = num(p.get("THSMON_SELNG_AMT"))
        share = lambda k: (num(p.get(k)) / bak_amt) if bak_amt else None  # noqa: E731
        rows.append({
            "TRDAR_CD": cd, "상권명": a["TRDAR_CD_NM"], "상권구분": a["TRDAR_SE_CD_NM"],
            "자치구": a["SIGNGU_CD_NM"], "행정동": a["ADSTRD_CD_NM"],
            "X": num(a["XCNTS_VALUE"]), "Y": num(a["YDNTS_VALUE"]), "면적_m2": num(a["RELM_AR"]),
            "베이커리매출_최신": bN, "베이커리매출_3년전": b0, "커피매출_최신": cN, "커피매출_3년전": c0,
            "합산매출_최신": tN, "합산매출_3년전": t0, "합산매출_1년전": t1,
            "합산매출_CAGR3": cagr(t0, tN, 3), "베이커리_CAGR3": cagr(b0, bN, 3),
            "합산매출_YoY": (tN / t1 - 1) if t1 > 0 else None,
            "베이커리점포_최신": nb_N, "베이커리점포_3년전": nb_0, "커피점포_최신": nc_N,
            "베이커리_점포당분기매출": (bN / nb_N) if nb_N else None,
            "베이커리_개업률": num(stN.get("OPBIZ_RT")), "베이커리_폐업률": num(stN.get("CLSBIZ_RT")),
            "유동인구_최신": fN, "유동인구_3년전": f0, "유동인구_증감률": (fN / f0 - 1) if f0 else None,
            "상주인구_최신": num((rN or {}).get("TOT_REPOP_CO")), "상주인구_3년전": num((r0 or {}).get("TOT_REPOP_CO")),
            "직장인구_최신": num((wN or {}).get("TOT_WRC_POPLTN_CO")), "직장인구_3년전": num((w0 or {}).get("TOT_WRC_POPLTN_CO")),
            "상주인구_기준분기": (rN or {}).get("STDR_YYQU_CD"), "직장인구_기준분기": (wN or {}).get("STDR_YYQU_CD"),
            "집객시설수": num(fc.get("VIATR_FCLTY_CO")), "지하철역수": num(fc.get("SUBWAY_STATN_CO")),
            "대학수": num(fc.get("UNIV_CO")),
            "상권변화지표": ix.get(cd, {}).get("TRDAR_CHNGE_IX_NM"),
            "운영영업개월": num(ix.get(cd, {}).get("OPR_SALE_MT_AVRG")), "폐업영업개월": num(ix.get(cd, {}).get("CLS_SALE_MT_AVRG")),
            "베이커리_2030비중": (lambda x, y: (x + y) if x is not None else None)(share("AGRDE_20_SELNG_AMT"), share("AGRDE_30_SELNG_AMT") or 0),
            "베이커리_여성비중": share("FML_SELNG_AMT"), "베이커리_주말비중": share("WKEND_SELNG_AMT"),
            "베이커리_오전비중": share("TMZON_06_11_SELNG_AMT"),
        })

    # ---- v2 추가 지표: 7개 분기 시계열 기반 지속성·단절 판별, 합산 고객구성, 안정성 ----
    Q2S = ["20232", "20242", "20252", "20262"]  # 같은 2분기끼리 비교
    store_qs = ["20232", "20242", "20252", "20262"]
    for r in rows:
        cd = r["TRDAR_CD"]
        s = sales.get(cd, {})
        tser = [s.get(q, {}).get("bak", 0) + s.get(q, {}).get("cof", 0) for q in SALES_Q]
        bser = [s.get(q, {}).get("bak", 0) for q in SALES_Q]
        cser = [s.get(q, {}).get("cof", 0) for q in SALES_Q]
        r["합산매출_7분기"] = tser
        r["베이커리매출_7분기"] = bser
        r["커피매출_7분기"] = cser
        t2 = [s.get(q, {}).get("bak", 0) + s.get(q, {}).get("cof", 0) for q in Q2S]
        b2 = [s.get(q, {}).get("bak", 0) for q in Q2S]
        yoy = [(t2[i + 1] / t2[i] - 1) if t2[i] > 0 and t2[i + 1] > 0 else None for i in range(3)]
        byoy = [(b2[i + 1] / b2[i] - 1) if b2[i] > 0 and b2[i + 1] > 0 else None for i in range(3)]
        r["합산_2분기YoY_3구간"] = yoy
        r["합산_2분기YoY_중앙값"] = st.median(yoy) if all(v is not None for v in yoy) else None
        r["합산_플러스구간수"] = sum(1 for v in yoy if v is not None and v > 0)
        r["베이커리_2분기YoY_중앙값"] = st.median(byoy) if all(v is not None for v in byoy) else None
        # 최대 단일 분기 증가가 3년 증가분에서 차지하는 비중 (0.6 이상 = 계단형)
        inc = [tser[i + 1] - tser[i] for i in range(len(tser) - 1)]
        tot = tser[-1] - tser[0]
        r["점프비중"] = (max(inc) / tot) if tot > 0 else None
        # 구조적 단절: 한 분기에 베이커리 +100% 초과 또는 커피 +60% 초과 (직전 분기 > 0)
        brk = []
        for i in range(len(SALES_Q) - 1):
            if bser[i] > 0 and bser[i + 1] / bser[i] - 1 > 1.0:
                brk.append(f"베이커리 {SALES_Q[i]}→{SALES_Q[i+1]} +{100*(bser[i+1]/bser[i]-1):.0f}%")
            if cser[i] > 0 and cser[i + 1] / cser[i] - 1 > 0.6:
                brk.append(f"커피 {SALES_Q[i]}→{SALES_Q[i+1]} +{100*(cser[i+1]/cser[i]-1):.0f}%")
        r["단절내역"] = brk
        r["단절플래그"] = 1 if brk else 0
        # 마스킹/고정값 의심: 베이커리 7분기 변동계수 3% 미만
        bpos = [v for v in bser if v > 0]
        cv = (st.pstdev(bpos) / st.mean(bpos)) if len(bpos) >= 5 else None
        r["베이커리_7분기CV"] = cv
        r["마스킹의심"] = 1 if (cv is not None and cv < 0.03) else 0
        # 합산(제과+커피) 고객 구성·객단가 (최신 분기)
        rec = combo.get(cd)
        if rec and rec["amt"] > 0:
            r["합산_2030비중"] = (rec["a20"] + rec["a30"]) / rec["amt"]
            r["합산_여성비중"] = rec["fml"] / rec["amt"]
            r["합산_주말비중"] = rec["wk"] / rec["amt"]
            r["합산_오전비중"] = rec["t0611"] / rec["amt"]
            r["합산_객단가"] = rec["amt"] / rec["cnt"] if rec["cnt"] else None
            r["타깃적합"] = (r["합산_2030비중"] + r["합산_여성비중"] + r["합산_주말비중"]) / 3
        else:
            for k in ["합산_2030비중", "합산_여성비중", "합산_주말비중", "합산_오전비중", "합산_객단가", "타깃적합"]:
                r[k] = None
        # 베이커리 점포당 매출 변화 (3년전 점포 ≥3 곳일 때만)
        nb0, nbN = r["베이커리점포_3년전"], r["베이커리점포_최신"]
        b0, bN = r["베이커리매출_3년전"], r["베이커리매출_최신"]
        r["베이커리_점포당매출_변화율"] = ((bN / nbN) / (b0 / nb0) - 1) if (nb0 >= 3 and nbN >= 3 and b0 > 0 and bN > 0) else None
        # 커피 점포 증감률 (공급 증가 = 경쟁 심화)
        nc0 = num(stores[cd].get(("20232", "cof"), {}).get("SIMILR_INDUTY_STOR_CO"))
        r["커피점포_3년전"] = nc0
        r["커피점포_증감률"] = (r["커피점포_최신"] / nc0 - 1) if nc0 else None
        # 표본 4개 분기 평균 폐업률 (제과+커피 점포 가중)
        cl, tot_s = 0.0, 0.0
        for q in store_qs:
            for k in ("bak", "cof"):
                srow = stores[cd].get((q, k), {})
                cl += num(srow.get("CLSBIZ_STOR_CO"))
                tot_s += num(srow.get("SIMILR_INDUTY_STOR_CO"))
        r["4분기평균_폐업률"] = (cl / tot_s) if tot_s else None
        r["상권축소"] = 1 if r["상권변화지표"] == "상권축소" else 0

    for r in rows:
        r["상주인구_증감률"] = (r["상주인구_최신"] / r["상주인구_3년전"] - 1) if r["상주인구_3년전"] else None
        r["직장인구_증감률"] = (r["직장인구_최신"] / r["직장인구_3년전"] - 1) if r["직장인구_3년전"] else None
        r["배후인구_증감률"] = ((r["상주인구_최신"] + r["직장인구_최신"]) / (r["상주인구_3년전"] + r["직장인구_3년전"]) - 1) \
            if (r["상주인구_3년전"] + r["직장인구_3년전"]) else None

    # 규모 필터: 최신 합산매출 상위 40% & 3년 전 매출 존재 (작은 기저 효과 배제)
    # 규모 필터: 분기 합산매출 10억 이상 & 베이커리 매출이 3년 전·최신 모두 공표된 상권 (소규모 기저효과 배제)
    cut = 1e9
    elig = [r for r in rows if r["합산매출_최신"] >= cut and r["합산매출_3년전"] > 0
            and r["베이커리매출_최신"] > 0 and r["베이커리매출_3년전"] > 0]

    # v1 점수(기록 보존): 시작·끝점 CAGR 중심
    feats_v1 = {
        "합산매출_CAGR3": 0.25, "합산매출_YoY": 0.15, "베이커리_CAGR3": 0.10,
        "유동인구_증감률": 0.12, "배후인구_증감률": 0.10, "베이커리_2030비중": 0.08,
        "베이커리_점포당분기매출": 0.12, "베이커리_폐업률": -0.08,
    }
    Z1 = {k: zs([r[k] for r in elig]) for k in feats_v1}
    for i, r in enumerate(elig):
        r["점수_v1"] = round(sum(w * (Z1[k][i] if Z1[k][i] is not None else 0) for k, w in feats_v1.items()), 4)
    for i, r in enumerate(sorted(elig, key=lambda r: r["점수_v1"], reverse=True), 1):
        r["순위_v1"] = i

    # v2 점수 (3개 패널 검토 반영, 변경 이유는 CHANGES_V2 참조)
    #  성장 지속성 0.50 + 수요·타깃 0.20 + 안정·경쟁 0.20 + 규모·객단가 0.10, 단절·계단·마스킹·상권축소 감점
    feats = {
        "합산_2분기YoY_중앙값": 0.25, "합산_플러스구간수": 0.10, "베이커리_2분기YoY_중앙값": 0.08,
        "베이커리_점포당매출_변화율": 0.07,
        "유동인구_증감률": 0.10, "타깃적합": 0.10,
        "운영영업개월": 0.07, "커피점포_증감률": -0.06, "4분기평균_폐업률": -0.07,
        "합산매출_최신": 0.05, "합산_객단가": 0.05,
    }
    penalties = {"단절플래그": 0.15, "마스킹의심": 0.10, "상권축소": 0.10}
    Z = {k: zs([r[k] for r in elig]) for k in feats}
    for i, r in enumerate(elig):
        base = sum(w * (Z[k][i] if Z[k][i] is not None else 0) for k, w in feats.items())
        pen = sum(p for k, p in penalties.items() if r[k])
        pen += 0.10 if (r["점프비중"] is not None and r["점프비중"] >= 0.6) else 0
        r["감점"] = round(pen, 4)
        r["점수"] = round(base - pen, 4)
        # 기존 전망(v1 가정): 과거 CAGR의 70%, 상한 25%
        g = r["합산매출_CAGR3"] or 0
        damp = min(g, 0.25) * 0.7
        r["3년후_합산매출_전망"] = r["합산매출_최신"] * (1 + damp) ** 3
        r["전망_적용성장률"] = damp
    elig.sort(key=lambda r: r["점수"], reverse=True)
    for i, r in enumerate(elig, 1):
        r["순위"] = i

    # 서울 전체 추세 (베이커리·커피 합계)
    seoul = {q: {"bak": sum(s[q]["bak"] for s in sales.values() if q in s),
                 "cof": sum(s[q]["cof"] for s in sales.values() if q in s)} for q in SALES_Q}
    seoul_cagr = cagr(seoul[Q0]["bak"] + seoul[Q0]["cof"], seoul[QN]["bak"] + seoul[QN]["cof"], 3)
    # 보수 전망(v2 가정): 성장률 = 0.5×min(같은분기 YoY 중앙값, 25%) + 0.5×서울 시장 3년 CAGR (평균 회귀)
    for r in elig:
        m = r["합산_2분기YoY_중앙값"]
        g2 = 0.5 * min(m if m is not None else 0, 0.25) + 0.5 * seoul_cagr
        r["전망_보수_적용성장률"] = g2
        r["3년후_합산매출_전망_보수"] = r["합산매출_최신"] * (1 + g2) ** 3

    keys = list(elig[0].keys())
    with open(os.path.join(INT, "trdar_scores.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(elig)

    out = {"version": "v2", "universe": len(rows), "eligible": len(elig), "size_cut": cut, "weights": feats,
           "penalties": dict(penalties, **{"점프비중>=0.6": 0.10}), "weights_v1": feats_v1,
           "changes_v2": CHANGES_V2, "seoul_market_cagr3": seoul_cagr,
           "seoul_trend": seoul, "top20": elig[:20]}
    with open(os.path.join(INT, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("universe", len(rows), "eligible", len(elig), "cut", round(cut))
    print("seoul", {q: (round(v['bak'] / 1e8), round(v['cof'] / 1e8)) for q, v in seoul.items()}, "(억원)")
    print("seoul market CAGR3 %.2f%%" % (100 * seoul_cagr))
    for r in elig[:30]:
        print(r["순위"], "(v1 %d)" % r["순위_v1"], r["상권명"], r["자치구"], r["상권구분"], "점수", r["점수"], "감점", r["감점"],
              "YoY3", [None if v is None else round(100 * v, 1) for v in r["합산_2분기YoY_3구간"]],
              "점프", None if r["점프비중"] is None else round(r["점프비중"], 2), r["단절내역"][:2])
    for r in elig[:0]:
        print(r["순위"], r["상권명"], r["자치구"], r["상권구분"], "점수", r["점수"],
              "합산 %.0f억" % (r["합산매출_최신"] / 1e8),
              "CAGR %.1f%%" % (100 * (r["합산매출_CAGR3"] or 0)), "YoY %.1f%%" % (100 * (r["합산매출_YoY"] or 0)),
              "빵CAGR %s" % (None if r["베이커리_CAGR3"] is None else round(100 * r["베이커리_CAGR3"], 1)),
              "유동 %s" % (None if r["유동인구_증감률"] is None else round(100 * r["유동인구_증감률"], 1)),
              "배후 %s" % (None if r["배후인구_증감률"] is None else round(100 * r["배후인구_증감률"], 1)),
              "빵점포", int(r["베이커리점포_최신"]), "점포당 %.2f억" % ((r["베이커리_점포당분기매출"] or 0) / 1e8),
              r["상권변화지표"])


if __name__ == "__main__":
    main()
