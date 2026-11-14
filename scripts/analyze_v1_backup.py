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

    # 점수: 성장성(50) + 수요 기반(30) + 경쟁 여력(20)
    feats = {
        "합산매출_CAGR3": 0.25, "합산매출_YoY": 0.15, "베이커리_CAGR3": 0.10,
        "유동인구_증감률": 0.12, "배후인구_증감률": 0.10, "베이커리_2030비중": 0.08,
        "베이커리_점포당분기매출": 0.12, "베이커리_폐업률": -0.08,
    }
    Z = {k: zs([r[k] for r in elig]) for k in feats}
    for i, r in enumerate(elig):
        r["점수"] = round(sum(w * (Z[k][i] if Z[k][i] is not None else 0) for k, w in feats.items()), 4)
        g = r["합산매출_CAGR3"] or 0
        damp = min(g, 0.25) * 0.7  # 보수적 외삽: 과거 CAGR의 70%, 상한 25%
        r["3년후_합산매출_전망"] = r["합산매출_최신"] * (1 + damp) ** 3
        r["전망_적용성장률"] = damp
    elig.sort(key=lambda r: r["점수"], reverse=True)
    for i, r in enumerate(elig, 1):
        r["순위"] = i

    keys = list(elig[0].keys())
    with open(os.path.join(INT, "trdar_scores.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(elig)

    # 서울 전체 추세 (베이커리·커피 합계)
    seoul = {q: {"bak": sum(s[q]["bak"] for s in sales.values() if q in s),
                 "cof": sum(s[q]["cof"] for s in sales.values() if q in s)} for q in SALES_Q}
    out = {"universe": len(rows), "eligible": len(elig), "size_cut": cut, "weights": feats,
           "seoul_trend": seoul, "top20": elig[:20]}
    with open(os.path.join(INT, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("universe", len(rows), "eligible", len(elig), "cut", round(cut))
    print("seoul", {q: (round(v['bak'] / 1e8), round(v['cof'] / 1e8)) for q, v in seoul.items()}, "(억원)")
    for r in elig[:15]:
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
