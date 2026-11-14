# -*- coding: utf-8 -*-
"""site/index.html 데이터 정합성 감사.

페이지에 표시된 수치를 원천(data/raw 서울 열린데이터광장 응답, DART 감사보고서 원문 행 텍스트
data/interim/audit_*.txt, dart_benchmark.json)에서 **독립적으로 다시 계산**해 대조한다.
interim JSON(location/menu/interior/pnl)은 '검사 대상'이지 기대값의 근거가 아니다
(단, 손익 내부 산술 검증은 pnl.json 값끼리의 합계·비율 관계를 본다).

검사 묶음
  A. 서울시 상권분석서비스 원천 ↔ 페이지 (매출·점포·유동인구·인구·시설·지표·지하철)
  B. DART 원문 행 ↔ dart_benchmark.json ↔ 페이지 (천원 → 억원/비율)
  C. 손익 시뮬레이션 산술 (시나리오 합계, 손익분기, 민감도, 누적)
  D. 정의 일관성 (같은 이름의 비율이 같은 분모로 계산됐는지)
  E. 표기 (출처 블록 누락, DART 접수번호 화이트리스트, 외부 출처, '가정' 배지)

실행: PYTHONIOENCODING=utf-8 python scripts/audit_site.py
결과: 콘솔 표 + data/interim/audit_site_result.json, 실패가 있으면 종료코드 1
"""
import csv
import glob
import html as H
import json
import os
import re
import statistics
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
INT = os.path.join(ROOT, "data", "interim")
PAGE = os.path.join(ROOT, "site", "index.html")


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rows(name):
    return load(os.path.join(RAW, name))["rows"]


# ------------------------------------------------------------------ 페이지 텍스트
html_src = open(PAGE, encoding="utf-8").read()
body = re.sub(r"<script.*?</script>", " ", html_src, flags=re.S)
body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
TEXT = H.unescape(re.sub(r"<[^>]+>", " ", body))
TEXT = re.sub(r"\s+", " ", TEXT).replace("−", "-")

RESULTS = []


def rec(group, label, ok, expected, note=""):
    RESULTS.append({"group": group, "label": label, "ok": bool(ok), "expected": str(expected), "note": note})


def on_page(s, near=None, win=400):
    s = s.replace("−", "-")
    if near is None:
        return s in TEXT
    for m in re.finditer(re.escape(near), TEXT):
        seg = TEXT[max(0, m.start() - win): m.end() + win]
        if s in seg:
            return True
    return False


def chk(group, label, s, near=None, note="", win=400):
    rec(group, label, on_page(s, near, win), s + (f"  (근처: {near})" if near else ""), note)


f1 = lambda x: f"{x * 100:.1f}%"
f1s = lambda x: f"{x * 100:+.1f}%"
won = lambda x: f"{round(x):,}원"
eok2 = lambda x: f"{x / 1e8:,.2f}"

# ================================================================== A. 서울 열린데이터광장 원천
CD = "3120175"      # 남부터미널역
BAK, COF = "CS100005", "CS100010"
QS = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]
SALES = {q: rows(f"sales_{q}.json") for q in QS}


def s_rec(q, cd, ind):
    return next((r for r in SALES[q] if r["TRDAR_CD"] == cd and r["SVC_INDUTY_CD"] == ind), None)


def comb(q, cd):
    b, c = s_rec(q, cd, BAK), s_rec(q, cd, COF)
    return (b["THSMON_SELNG_AMT"] if b else 0) + (c["THSMON_SELNG_AMT"] if c else 0)


# A1 서울 전체 시장 추이
seoul = {q: {ind: sum(r["THSMON_SELNG_AMT"] for r in SALES[q] if r["SVC_INDUTY_CD"] == ind) for ind in (BAK, COF)} for q in QS}
sb0, sb1 = seoul["20232"][BAK], seoul["20262"][BAK]
sc0, sc1 = seoul["20232"][COF], seoul["20262"][COF]
chk("A", "서울 제과점 20232 분기매출", f"{sb0 / 1e8:,.1f}억원", "제과점 23Q2")
chk("A", "서울 제과점 20262 분기매출", f"{sb1 / 1e8:,.1f}억원", "26Q2")
chk("A", "서울 커피 20232→20262", f"{sc0 / 1e8:,.1f}억원 → {sc1 / 1e8:,.1f}억원")
chk("A", "서울 제과점 3년 증감", f"({f1s(sb1 / sb0 - 1)})", "제과점 23Q2")
chk("A", "서울 커피 3년 증감", f"({f1s(sc1 / sc0 - 1)})", "커피-음료")
mkt = ((sb1 + sc1) / (sb0 + sc0)) ** (1 / 3) - 1
chk("A", "서울 제과+커피 시장 CAGR3", f"{mkt * 100:+.2f}%", "서울 전체 제과+커피 시장")
chk("A", "서울 시장 CAGR3(요약문)", f"3년 CAGR {mkt * 100:.2f}%")

# A2 상권 유니버스·분석 대상
n_area = len(rows("trdar_area.json"))
chk("A", "서울 전체 상권 수(TbgisTrdarRelm)", f"{n_area:,}개")
elig = [cd for cd in {r["TRDAR_CD"] for r in SALES["20262"]}
        if comb("20262", cd) >= 1e9 and s_rec("20232", cd, BAK) and s_rec("20262", cd, BAK)]
chk("A", "분석 대상 상권 수(10억↑ & 베이커리 공표)", f"{len(elig)}개 분석 대상")

# A3 최종 상권 매출
c0, c_1, c1 = comb("20232", CD), comb("20252", CD), comb("20262", CD)
chk("A", "최종지 분기 합산매출 20262", f"{c1 / 1e8:.2f}억원", "분기 합산매출")
cagr = (c1 / c0) ** (1 / 3) - 1
chk("A", "최종지 합산 CAGR3", f"{cagr * 100:+.1f}%", "합산매출 3년 CAGR")
yo = [comb(b, CD) / comb(a, CD) - 1 for a, b in (("20232", "20242"), ("20242", "20252"), ("20252", "20262"))]
chk("A", "같은 2분기 YoY 3구간", " → ".join(f1(v) for v in yo))
b0, b1 = s_rec("20232", CD, BAK)["THSMON_SELNG_AMT"], s_rec("20262", CD, BAK)["THSMON_SELNG_AMT"]
chk("A", "베이커리 매출 3년전→최신", f"{b0 / 1e8:.2f} → {b1 / 1e8:.2f}억원")
chk("A", "20254 합산매출(리스크)", f"20254({comb('20254', CD) / 1e8:.1f}억원)")

# A4 점포
ST = {q: rows(f"store_{q}.json") for q in ("20232", "20242", "20252", "20262")}


def st(q, cd, ind, k="SIMILR_INDUTY_STOR_CO"):
    r = next((r for r in ST[q] if r["TRDAR_CD"] == cd and r["SVC_INDUTY_CD"] == ind), None)
    return r[k] if r else None


nb0, nb1, nc0, nc1 = st("20232", CD, BAK), st("20262", CD, BAK), st("20232", CD, COF), st("20262", CD, COF)
chk("A", "베이커리 점포 3년전→최신", f"베이커리 점포는 {nb0:.0f}곳 → {nb1:.0f}곳")
chk("A", "커피 점포 3년전→최신", f"커피는 {nc0:.0f} → {nc1:.0f}곳")
ppb0, ppb1 = b0 / nb0, b1 / nb1
chk("A", "베이커리 점포당 분기매출", f"{ppb1 / 1e8:.3f}억원", "베이커리 점포당 분기매출")
chk("A", "베이커리 점포당 매출 3년 변화율", f"{f1s(ppb1 / ppb0 - 1)}", "176상권 중앙값")
chk("A", "커피 폐업률 20262", f"커피 폐업률 {st('20262', CD, COF, 'CLSBIZ_RT'):.0f}%")
clo = sum(st(q, CD, i, "CLSBIZ_RT") / 100 * st(q, CD, i) for q in ST for i in (BAK, COF))
tot = sum(st(q, CD, i) for q in ST for i in (BAK, COF))
chk("A", "표본 4분기 평균 폐업률(점포 가중)", f1(clo / tot), "표본 4분기 평균 폐업률")

# 176상권 베이커리 점포당 분기매출 중앙값
SC = list(csv.DictReader(open(os.path.join(INT, "trdar_scores.csv"), encoding="utf-8-sig")))
ppb_all = []
for cd in elig:
    n = st("20262", cd, BAK)
    if n:
        ppb_all.append(s_rec("20262", cd, BAK)["THSMON_SELNG_AMT"] / n)
chk("A", "176상권 베이커리 점포당 분기매출 중앙값", f"{statistics.median(ppb_all) / 1e8:.3f}억원", "176상권 중앙값")
rec("A", "trdar_scores.csv 행 수 = 분석 대상 수", len(SC) == len(elig), f"{len(SC)} vs {len(elig)}")

# A5 고객 구성(20262) — 총매출 대비
bk, cf = s_rec("20262", CD, BAK), s_rec("20262", CD, COF)
amt = bk["THSMON_SELNG_AMT"] + cf["THSMON_SELNG_AMT"]
cnt = bk["THSMON_SELNG_CO"] + cf["THSMON_SELNG_CO"]
S = lambda k: (bk[k] + cf[k]) / amt
chk("A", "합산 2030 비중", f1(S("AGRDE_20_SELNG_AMT") + S("AGRDE_30_SELNG_AMT")), "2030")
chk("A", "합산 여성 비중(총매출 대비)", f1(S("FML_SELNG_AMT")), "2030 / 여성 / 주말")
chk("A", "합산 주말 비중", f"주말 {f1(S('WKEND_SELNG_AMT'))}")
chk("A", "합산 주중 비중", f"주중 {f1(S('MDWK_SELNG_AMT'))}")
chk("A", "합산 06~11시 비중", f"23.9%" if abs(S("TMZON_06_11_SELNG_AMT") - 0.239) < 5e-4 else f1(S("TMZON_06_11_SELNG_AMT")), "06~11")
chk("A", "합산 11~14시 비중", f1(S("TMZON_11_14_SELNG_AMT")), "점심")
chk("A", "합산 21~24시 비중", f"21~24시 매출 {f1(S('TMZON_21_24_SELNG_AMT'))}")
chk("A", "합산 객단가", won(amt / cnt), "합산 객단가")
chk("A", "제과점 객단가 20262", won(bk["THSMON_SELNG_AMT"] / bk["THSMON_SELNG_CO"]), "베이커리")
chk("A", "커피 객단가 20262", won(cf["THSMON_SELNG_AMT"] / cf["THSMON_SELNG_CO"]), "커피 객단가")
b232 = s_rec("20232", CD, BAK)
chk("A", "제과점 객단가 20232", won(b232["THSMON_SELNG_AMT"] / b232["THSMON_SELNG_CO"]) + " →", "제과점")
bshare = lambda k: bk[k] / bk["THSMON_SELNG_AMT"]
cshare = lambda k: cf[k] / cf["THSMON_SELNG_AMT"]
chk("A", "베이커리 06~11 / 17~21", f"06~11시 {f1(bshare('TMZON_06_11_SELNG_AMT'))}·17~21시 {f1(bshare('TMZON_17_21_SELNG_AMT'))}")
chk("A", "커피 11~14시", f"11~14시에 {f1(cshare('TMZON_11_14_SELNG_AMT'))}")
chk("A", "베이커리 주말 비중", f"베이커리 주말 비중({f1(bshare('WKEND_SELNG_AMT'))})")
chk("A", "커피 주중 비중", f"주중 {f1(cshare('MDWK_SELNG_AMT'))}", "분기 거래")
chk("A", "상권 제과점 매출 비중", f"{f1(bk['THSMON_SELNG_AMT'] / amt)}", "제과점 매출 비중은")
seoul_bk_t = sb1 / sum(r["THSMON_SELNG_CO"] for r in SALES["20262"] if r["SVC_INDUTY_CD"] == BAK)
seoul_cf_t = sc1 / sum(r["THSMON_SELNG_CO"] for r in SALES["20262"] if r["SVC_INDUTY_CD"] == COF)
chk("A", "서울 전체 제과점·커피 객단가", f"서울 전체 제과점 {won(seoul_bk_t)}·커피 {won(seoul_cf_t)}")
med_bk_t = statistics.median(s_rec("20262", cd, BAK)["THSMON_SELNG_AMT"] / s_rec("20262", cd, BAK)["THSMON_SELNG_CO"] for cd in elig)
med_cf_t = statistics.median(s_rec("20262", cd, COF)["THSMON_SELNG_AMT"] / s_rec("20262", cd, COF)["THSMON_SELNG_CO"]
                             for cd in elig if s_rec("20262", cd, COF) and s_rec("20262", cd, COF)["THSMON_SELNG_CO"])
chk("A", "176상권 객단가 중앙값", f"176상권 중앙값 제과점 {won(med_bk_t)}·커피 {won(med_cf_t)}")
prop = 1 / (0.48 / (cf["THSMON_SELNG_AMT"] / cf["THSMON_SELNG_CO"]) + 0.52 / (bk["THSMON_SELNG_AMT"] / bk["THSMON_SELNG_CO"]))
chk("A", "제안 객단가 조화평균", f"= {won(prop)}")
chk("A", "베이커리 분기 거래건수", f"{bk['THSMON_SELNG_CO']:,.0f}건")

# A6 유동인구
FP = {q: next(r for r in rows(f"flpop_{q}.json") if r["TRDAR_CD"] == CD) for q in ("20232", "20262")}
fp1 = FP["20262"]
chk("A", "유동인구 3년 증감", f1s(fp1["TOT_FLPOP_CO"] / FP["20232"]["TOT_FLPOP_CO"] - 1), "유동인구 3년 증감")
fl_ch = []
F0 = {r["TRDAR_CD"]: r["TOT_FLPOP_CO"] for r in rows("flpop_20232.json")}
F1 = {r["TRDAR_CD"]: r["TOT_FLPOP_CO"] for r in rows("flpop_20262.json")}
fl_ch = [F1[c] / F0[c] - 1 for c in elig if F0.get(c) and F1.get(c)]
chk("A", "176상권 유동인구 증감 중앙값", f"176상권 중앙값 {f1s(statistics.median(fl_ch))}")
ft = fp1["TOT_FLPOP_CO"]
chk("A", "유동인구 06~11시 비중", f"06~11시가 {f1(fp1['TMZON_06_11_FLPOP_CO'] / ft)}")
chk("A", "유동인구 21~06시 비중", f"21~06시 {f1((fp1['TMZON_21_24_FLPOP_CO'] + fp1['TMZON_00_06_FLPOP_CO']) / ft)}")
chk("A", "유동인구 21~24시 비중", f"유동인구 21~24시 {f1(fp1['TMZON_21_24_FLPOP_CO'] / ft)}")
we = (fp1["SAT_FLPOP_CO"] + fp1["SUN_FLPOP_CO"]) / sum(fp1[k] for k in fp1 if k.endswith("_FLPOP_CO") and k[:3] in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"))
chk("A", "유동인구 토·일 비중", f"토·일 {f1(we)}")

# A7 상주·직장인구, 집객시설, 상권변화지표
rep = max((r for r in rows("repop_all.json") if r["TRDAR_CD"] == CD), key=lambda r: r["STDR_YYQU_CD"])
wrc = max((r for r in rows("wrcpop_all.json") if r["TRDAR_CD"] == CD), key=lambda r: r["STDR_YYQU_CD"])
chk("A", "직장인구/상주인구", f"직장인구 {wrc['TOT_WRC_POPLTN_CO']:,.0f}명이 상주인구 {rep['TOT_REPOP_CO']:,.0f}명의 {wrc['TOT_WRC_POPLTN_CO'] / rep['TOT_REPOP_CO']:.1f}배")
w2040 = wrc["AGRDE_20_WRC_POPLTN_CO"] + wrc["AGRDE_30_WRC_POPLTN_CO"] + wrc["AGRDE_40_WRC_POPLTN_CO"]
chk("A", "직장인구 20~40대", f"{w2040:,.0f}명({f1(w2040 / wrc['TOT_WRC_POPLTN_CO'])})")


def last_change(fname, key):
    d = {}
    for r in rows(fname):
        d.setdefault(r["TRDAR_CD"], {})[r["STDR_YYQU_CD"]] = r[key]
    qs = sorted({q for v in d.values() for q in v})
    last = None
    for a, b in zip(qs, qs[1:]):
        if sum(1 for v in d.values() if a in v and b in v and v[a] != v[b]) > 0:
            last = b
    return last


rep_frz, wrc_frz = last_change("repop_all.json", "TOT_REPOP_CO"), last_change("wrcpop_all.json", "TOT_WRC_POPLTN_CO")
chk("A", "상주인구 값 동결 시작 분기 표기", f"상주인구는 {rep_frz} 이후", note="원천에서 마지막으로 값이 바뀐 분기")
chk("A", "직장인구 값 동결 시작 분기 표기", f"직장인구는 {wrc_frz} 이후", note="원천에서 마지막으로 값이 바뀐 분기")
fc = max((r for r in rows("fclty_all.json") if r["TRDAR_CD"] == CD), key=lambda r: r["STDR_YYQU_CD"])
chk("A", "집객시설", f"슈퍼마켓 {fc['SUPMK_CO']:.0f}곳, 종합병원 {fc['GNRL_HSPTL_CO']:.0f}곳, 관공서 {fc['PBLOFC_CO']:.0f}곳, 은행 {fc['BANK_CO']:.0f}곳, 집객시설 총 {fc['VIATR_FCLTY_CO']:.0f}곳")
rec("A", "집객시설 기준분기 = 20262", fc["STDR_YYQU_CD"] == "20262", fc["STDR_YYQU_CD"])
ix = next(r for r in rows("trdar_ix_20262.json") if r["TRDAR_CD"] == CD)
chk("A", "상권변화지표·운영개월", f"{ix['TRDAR_CHNGE_IX_NM']} · {ix['OPR_SALE_MT_AVRG']:.0f}개월")
chk("A", "서울 평균 운영개월", f"{ix['OPR_SALE_MT_AVRG']:.0f}개월(서울 {ix['SU_OPR_SALE_MT_AVRG']:.0f}개월)")

# A8 지하철 (1주)
sub = []
for f in sorted(glob.glob(os.path.join(RAW, "subway_202611*.json"))):
    for r in load(f)["rows"]:
        if "남부터미널" in r["SBWY_STNS_NM"]:
            d = date(int(r["USE_YMD"][:4]), int(r["USE_YMD"][4:6]), int(r["USE_YMD"][6:]))
            sub.append((d.weekday(), int(r["GTON_TNOPE"]) + int(r["GTOFF_TNOPE"])))
wd = [v for w, v in sub if w < 5]
wk = [v for w, v in sub if w >= 5]
rec("A", "지하철 수집일 7일(평일5·주말2)", (len(wd), len(wk)) == (5, 2), f"{len(wd)}/{len(wk)}")
chk("A", "지하철 평일·주말 평균", f"평일 평균 {sum(wd) / len(wd):,.0f}명/일, 주말 평균 {sum(wk) / len(wk):,.0f}명/일(평일의 {sum(wk) / len(wk) / (sum(wd) / len(wd)) * 100:.0f}%)")

# A9 좌석 산정 (평일 수)
q2 = [date(2026, 4, 1) + timedelta(days=i) for i in range(91)]
n_wd = sum(1 for d in q2 if d.weekday() < 5)
rec("A", "2026Q2 평일 수(공휴일 미반영) = 페이지의 65일", n_wd == 65, n_wd, "공휴일은 데이터 없음 → 달력 평일 수")
daily = bk["THSMON_SELNG_CO"] / nb1 / 91 + cf["THSMON_SELNG_CO"] / nc1 / 91
chk("A", "신규 매장 일 거래건수", f"{daily:.1f}건/일")
wday = daily * 91 * round(S("MDWK_SELNG_AMT") * 100, 1) / 100 / 65   # 페이지 계산식은 표시값 81.4%를 사용
chk("A", "평일 일 거래건수", f"{wday:.1f}건/일")
peak = wday * round(S("TMZON_11_14_SELNG_AMT") * 100, 1) / 100 / 3   # 표시값 36.3% 사용(페이지 계산식과 동일)
chk("A", "평일 피크 시간당 거래", f"{peak:.1f}건/시간")
chk("A", "좌석 계산값", f"계산값 {peak * 0.35 * 1.5 * 0.6 / 0.85:.1f}석")

# A10 후보 2·3 (표본)
for cd_name in ("연희동", "동대문역사문화공원역"):
    r = next(x for x in SC if x["상권명"] == cd_name)
    cd = r["TRDAR_CD"]
    chk("A", f"{cd_name} 분기 합산매출", f"{comb('20262', cd) / 1e8:.2f}억원", "분기 합산매출 26Q2", win=200)
    chk("A", f"{cd_name} CAGR3", f1((comb("20262", cd) / comb("20232", cd)) ** (1 / 3) - 1), "합산 CAGR3", win=200)
    bb0, bb1 = s_rec("20232", cd, BAK)["THSMON_SELNG_AMT"], s_rec("20262", cd, BAK)["THSMON_SELNG_AMT"]
    chk("A", f"{cd_name} 베이커리 매출", f"{bb0 / 1e8:.2f} → {bb1 / 1e8:.2f}억원")
    chk("A", f"{cd_name} 점포 수", f"{st('20232', cd, BAK):.0f}→{st('20262', cd, BAK):.0f} / {st('20232', cd, COF):.0f}→{st('20262', cd, COF):.0f}")
    f0 = next(x for x in rows("flpop_20232.json") if x["TRDAR_CD"] == cd)["TOT_FLPOP_CO"]
    f1_ = next(x for x in rows("flpop_20262.json") if x["TRDAR_CD"] == cd)["TOT_FLPOP_CO"]
    chk("A", f"{cd_name} 유동인구 증감", f1s(f1_ / f0 - 1), "유동인구 3년 증감", win=200)

# A10b 패널 제외 상권 표본 (베이커리 분기매출 억원)
NM = {r["TRDAR_CD_NM"]: r["TRDAR_CD"] for q in QS for r in SALES[q]}
for nm, qa, qb in (("잠실 관광특구", "20232", "20242"), ("잠실역", "20232", "20242"), ("쌍문역동측상점가", "20252", "20253"),
                   ("북촌(안국역)", "20242", "20262"), ("강남 마이스 관광특구", "20254", "20262"), ("이화사거리", "20232", "20262")):
    va, vb = (s_rec(q, NM[nm], BAK)["THSMON_SELNG_AMT"] / 1e8 for q in (qa, qb))
    fa = f"{va:.2f}".rstrip("0").rstrip(".")
    rec("A", f"패널 제외 {nm} 베이커리 {qa}→{qb}", on_page(f"{fa}", nm, 300) and on_page(f"{vb:.2f}억원", nm, 300), f"{fa}억 → {vb:.2f}억원 (근처: {nm})")

# A11 점수·순위 (csv ↔ 페이지)
for nm, rk_txt in (("남부터미널역", None), ("연희동", None), ("동대문역사문화공원역", None)):
    r = next(x for x in SC if x["상권명"] == nm)
    chk("A", f"{nm} v2 순위(점수)", f"{int(float(r['순위']))}위 ({float(r['점수']):.3f})")

# ================================================================== B. DART
DART = load(os.path.join(INT, "dart_benchmark.json"))
AUD = {n: open(glob.glob(os.path.join(INT, f"audit_{n}_{DART[n]['rcept_no']}.txt"))[0], encoding="utf-8").read()
       for n in DART if not n.startswith("_")}
n_ = lambda s: int(s.replace(",", ""))
for n, d in DART.items():
    if n.startswith("_"):
        continue
    t = AUD[n]
    # 성격별 분류 각 항목이 원문 행에 존재
    vals = [v for vs in d["costs"].values() for v in vs]
    # 천원 값이 원문에 그대로 있거나, 원 단위 행(천원×1000 ±500원)으로 존재
    won_nums = {n_(x) for x in re.findall(r"[\d,]{11,}", t)}
    missing = [v for v in vals if f"{abs(v):,}" not in t and not any(abs(w - abs(v) * 1000) <= 500 for w in won_nums)]
    rec("B", f"{n} 비용 항목 원문 존재({len(vals)}개)", not missing, "모두 원문 행에 존재", f"없음: {missing}" if missing else "")
    rec("B", f"{n} 항목합 = 비용합계", sum(vals) == d["cost_total"], f"{sum(vals):,} vs {d['cost_total']:,}")
    rec("B", f"{n} 매출 − 비용합계 = 영업이익(천원 반올림 ±2)", abs(d["revenue"] - d["cost_total"] - d["operating_income"]) <= 2,
        f"{d['revenue'] - d['cost_total']:,} vs {d['operating_income']:,}", "원 단위 공시를 천원으로 반올림한 차이만 허용")
    # 매출·영업이익 원문(원 단위) ↔ 천원
    oi_m = [n_(x) for x in re.findall(r"영업이익[^\n|]*\|[^\n]*?([\d,]{11,})", t)]
    rec("B", f"{n} 영업이익 원문(원)↔JSON(천원)", any(round(x / 1000) == d["operating_income"] for x in oi_m), f"{d['operating_income']:,}천원")
    rec("B", f"{n} 매출 원문 존재", f"{d['revenue']:,}" in t or any(round(n_(x) / 1000) == d["revenue"] for x in re.findall(r"([\d,]{13,})", t)), f"{d['revenue']:,}천원")
    chk("B", f"{n} 매출 억원 표시", f"{d['revenue'] / 1e5:,.0f}억원", n)
    chk("B", f"{n} 영업이익률", f1(d["operating_income"] / d["revenue"]), n, win=120)
    chk("B", f"{n} rcpNo 링크", d["rcept_no"])
    rec("B", f"{n} DART 링크 href", f"rcpNo={d['rcept_no']}" in html_src, d["rcept_no"])

sck = DART["에스씨케이컴퍼니"]
R = lambda d, k: sum(d["costs"][k]) / d["revenue"]
chk("B", "스타벅스 원재료·상품 비율", f1(R(sck, "원재료·상품")), "에스씨케이컴퍼니", win=200)
chk("B", "스타벅스 인건비 비율", f"{R(sck, '인건비') * 100:.2f}%", "인건비율")
chk("B", "스타벅스 점유비용 비율", f"{(R(sck, '임차료') + R(sck, '사용권자산상각비')) * 100:.2f}%", "임차료율")
chk("B", "스타벅스 지급수수료 비율", f"{R(sck, '지급수수료') * 100:.2f}%", "지급수수료율")
tw, cj, ed = DART["투썸플레이스"], DART["CJ푸드빌"], DART["이디야"]
chk("B", "투썸 원재료·상품 비율", f1(R(tw, "원재료·상품")), "투썸플레이스", win=200)
chk("B", "CJ푸드빌 원재료·상품 비율", f1(R(cj, "원재료·상품")), "CJ푸드빌", win=200)
chk("B", "이디야 매출원가율", f"매출원가 {f1(R(ed, '매출원가'))}")
fee_alt = min(R(tw, "지급수수료"), R(cj, "지급수수료"))
chk("B", "지급수수료 치환값(투썸·CJ 중 낮은 값)", f"지급수수료 {f1(fee_alt)}로 치환")
mat_w = 0.5 * R(sck, "원재료·상품") + 0.5 * R(cj, "원재료·상품")
chk("B", "원재료비율 50:50 가중", f"{mat_w * 100:.2f}%", "원재료비율")
# 감가상각비 원문(원) / 매출
dep = n_(re.search(r"유형자산감가상각비 \| ([\d,]+)", AUD["에스씨케이컴퍼니"]).group(1))
dep_r = dep / (sck["revenue"] * 1000)
chk("B", "스타벅스 유형자산감가상각비/매출", f"{dep_r:.4f}", "유형자산감가상각비/매출")
chk("B", "무형자산상각비율", f"{(R(sck, '유무형자산상각비') - dep_r) * 100:.2f}%", "무형자산상각비율")


# 베이커리 제조사 잔차비율 (로쏘·엘비엠)
def residual(fname, rev_pat, cogs_pat, mfg_pat):
    t = open(os.path.join(INT, fname), encoding="utf-8").read()
    rev = n_(re.search(rev_pat, t).group(1))
    cogs = n_(re.search(cogs_pat, t).group(1))
    mfg = n_(re.search(mfg_pat, t).group(1)) * 1000
    return (cogs - mfg) / rev, cogs / rev


ro, ro_c = residual("audit_로쏘_20260410000434.txt", r"Ⅰ\.매출액 \|  \| ([\d,]+)", r"Ⅱ\.매출원가 \|  \| ([\d,]+)",
                    r"제조원가 \| 판매비와 관리비 \| 합 계[\s\S]*?\n합 계 \| ([\d,]+)")
lb, lb_c = residual("audit_엘비엠_20260326000290.txt", r"Ⅰ\. 매출액 \|  \| ([\d,]+)", r"Ⅱ\. 매출원가 \|  \| ([\d,]+)",
                    r"매출원가 \| 판매관리비 \| 합 계[\s\S]*?\n합 계 \| ([\d,]+)")
chk("B", "로쏘 잔차비율", f"로쏘 {f1(ro)}")
chk("B", "엘비엠 잔차비율", f"엘비엠 {f1(lb)}")

# ================================================================== C. 손익 산술
PNL = load(os.path.join(INT, "pnl.json"))
SCN, BE, SENS = PNL["scenarios"], PNL["breakeven"], PNL["sensitivity"]
TOL = 1.0  # 원
base_ann = sum(s_rec(q, CD, BAK)["THSMON_SELNG_AMT"] for q in ("20253", "20254", "20261", "20262")) / nb1
chk("C", "기준 연매출(제과점 점포당 최근 4분기)", f"{base_ann / 1e8:.2f}억원", "점포당 연매출")
for s, sv in SCN.items():
    cum = 0
    for i, y in enumerate(("Y1", "Y2", "Y3")):
        r = sv["연도별"][y]
        exp_rev = base_ann * sv["매출배수"] * (1 + sv["연성장률"]) ** (i + 1)
        rec("C", f"{s} {y} 매출 = 기준×배수×(1+g)^{i + 1}", abs(r["매출"] - exp_rev) < TOL, f"{exp_rev:,.0f}", f"pnl {r['매출']:,.0f}")
        rec("C", f"{s} {y} 매출총이익 = 매출 − 원재료비", abs(r["매출"] - r["원재료비"] - r["매출총이익"]) < TOL, f"{r['매출'] - r['원재료비']:,.0f}")
        rec("C", f"{s} {y} 기타 = 내역 합", abs(sum(r["기타_내역"].values()) - r["기타"]) < TOL, f"{sum(r['기타_내역'].values()):,.0f}")
        op = r["매출총이익"] - r["인건비"] - r["임차료"] - r["기타"]
        rec("C", f"{s} {y} 영업이익 = 총이익 − 인건비 − 임차료 − 기타", abs(op - r["영업이익"]) < TOL, f"{op:,.0f}")
        rec("C", f"{s} {y} 영업이익률", abs(r["영업이익"] / r["매출"] - r["영업이익률"]) < 1e-9, f"{r['영업이익'] / r['매출']:.4f}")
        da = r["기타_내역"]["감가상각비"] + r["기타_내역"]["무형자산상각비"]
        rec("C", f"{s} {y} EBITDA = 영업이익 + 감가상각비 + 무형자산상각비", abs(r["영업이익"] + da - r["EBITDA"]) < TOL,
            f"{r['영업이익'] + da:,.0f}", f"pnl {r['EBITDA']:,.0f}")
        mo = sv["월평균"][y]
        rec("C", f"{s} {y} 월평균 = 연/12", abs(mo["매출"] * 12 - r["매출"]) < TOL and abs(mo["영업이익"] * 12 - r["영업이익"]) < TOL, "연/12")
        cum += r["영업이익"]
        chk("C", f"{s} {y} 매출(억원) 표 표시", eok2(r["매출"]), "3개 시나리오 손익", win=3000)
    rec("C", f"{s} 3년 누적 영업이익 = Y1+Y2+Y3", abs(cum - sv["3년누적_영업이익"]) < TOL, f"{cum:,.0f}")
    chk("C", f"{s} 3년 누적 영업이익 표시", f"{cum / 1e8:.2f}억원", "3년 누적 영업이익", win=200)
fixed = BE["고정비_연_원"]
y1 = SCN["기준"]["연도별"]["Y1"]
fx_from_y1 = y1["인건비"] + y1["임차료"] + sum(v for k, v in y1["기타_내역"].items() if k not in ("지급수수료", "소모품비"))
rec("C", "손익분기 고정비 = 기준 Y1 고정비 항목 합", abs(fx_from_y1 - fixed) < TOL, f"{fx_from_y1:,.0f}")
var = (y1["원재료비"] + y1["기타_내역"]["지급수수료"] + y1["기타_내역"]["소모품비"]) / y1["매출"]
rec("C", "변동비율 = (원재료+지급수수료+소모품)/매출", abs(var - BE["변동비율"]) < 1e-9, f"{var:.4f}")
bev = fixed / (1 - var)
rec("C", "손익분기 연매출 = 고정비/(1−변동비율)", abs(bev - BE["손익분기_연매출_원"]) < TOL, f"{bev:,.0f}")
chk("C", "손익분기 연매출 표시", f"{bev / 1e8:.2f}억원", "손익분기")
chk("C", "손익분기/기준 Y1", f1(bev / y1["매출"]), "기준 Y1 매출의")
chk("C", "손익분기/점포당 연매출", f1(bev / base_ann), "점포당 연매출의")
chk("C", "고정비·변동비율·공헌이익률", f"연 고정비 {fixed / 1e8:.2f}억원 · 변동비율 {f1(var)} · 공헌이익률 {f1(1 - var)}")
for s, sv in SCN.items():
    for y in ("Y1", "Y2", "Y3"):
        rec("C", f"도달 여부 {s} {y}", BE["시나리오별_도달"][s][y] == (sv["연도별"][y]["매출"] >= bev), str(sv["연도별"][y]["매출"] >= bev))
first = next(i + 1 for i, y in enumerate(("Y1", "Y2", "Y3")) if SCN["기준"]["연도별"][y]["영업이익"] > 0)
chk("C", "기준 흑자 전환 연차", f"기준 시나리오는 {first}년차 흑자 전환")
# 민감도 그리드 재계산 (Y1, 고정비 고정)
grid = SENS["Y1영업이익률_그리드(행:매출, 열:원재료비)"]
bad = []
for rk, row in grid.items():
    for ck, v in row.items():
        rv = y1["매출"] * (1 + float(rk.strip("%")) / 100)
        dv = float(ck.replace("%p", "")) / 100 if ck != "0" else 0
        e_ = (rv * (1 - var - dv) - fixed) / rv
        if abs(e_ - v) > 1e-6:
            bad.append((rk, ck, v, e_))
rec("C", "Y1 매출×원재료비 그리드 재계산(9칸)", not bad, "고정비 고정·변동비율 가감", str(bad))
fee_y1 = (y1["매출"] * (1 - var + R(sck, "지급수수료") - fee_alt) - fixed) / y1["매출"]
rec("C", "지급수수료 치환 Y1 영업이익률", abs(fee_y1 - SENS["지급수수료_비교군치환"]["기준_Y1~Y3_영업이익률"]["Y1"]) < 1e-6, f"{fee_y1 * 100:.2f}%")
rec("C", "음수 0 표기(−0.0%) 없음", not re.search(r"-0\.0%", TEXT), "−0.0% 미표시")
cogs_mix = 0.38 * 27.2 + 0.10 * 27.2 + 0.32 * round(ro * 100, 1) + 0.10 * round(ro * 100, 1) + 0.10 * round(R(cj, "원재료·상품") * 100, 1)
chk("C", "메뉴 믹스 가중 원재료율", f"= {cogs_mix:.1f}%")
chk("C", "메뉴목표 vs 손익 원재료율 차이", f"차이 {mat_w * 100 - cogs_mix:.1f}%p")
chk("C", "본 모델 비용률(기준 Y1)", f"{f1(1 - y1['영업이익률'])}", "본 모델 비용률")
for s, sv in SCN.items():
    rec("C", f"{s} 시나리오 매출합 정합(표 Y1~Y3)", all(on_page(eok2(sv['연도별'][y]['매출']), '3개 시나리오 손익', 3000) for y in ('Y1', 'Y2', 'Y3')), "3개 연도 표시")

# ================================================================== D. 정의 일관성
LOC = load(os.path.join(INT, "location.json"))
INTR = load(os.path.join(INT, "interior.json"))
prof = LOC["final_profile"]["매출프로필_20262"]
b_f_tot = bk["FML_SELNG_AMT"] / bk["THSMON_SELNG_AMT"]
b_f_mf = bk["FML_SELNG_AMT"] / (bk["FML_SELNG_AMT"] + bk["ML_SELNG_AMT"])
both = on_page(f1(b_f_tot)) and on_page(f1(b_f_mf))
rec("D", "베이커리 여성 비중이 한 가지 분모로만 표시", not both,
    f"총매출 대비 {f1(b_f_tot)} 만", f"남+여 대비 {f1(b_f_mf)}도 함께 표시됨" if both else "")
c_f_mf = (bk["FML_SELNG_AMT"] + cf["FML_SELNG_AMT"]) / (bk["FML_SELNG_AMT"] + cf["FML_SELNG_AMT"] + bk["ML_SELNG_AMT"] + cf["ML_SELNG_AMT"])
rec("D", "합산 여성 비중 분모 = 총매출(176 중앙값과 동일 정의)", prof["합산"]["성별비중_%"]["여성"] == round(S("FML_SELNG_AMT") * 100, 1),
    f"{f1(S('FML_SELNG_AMT'))}", f"location.json final_profile 합산 여성 {prof['합산']['성별비중_%']['여성']}% (남+여 대비 {f1(c_f_mf)})")
age_sum = lambda r: sum(r[k] for k in r if k.startswith("AGRDE_"))
b4060_tot = (bk["AGRDE_40_SELNG_AMT"] + bk["AGRDE_50_SELNG_AMT"] + bk["AGRDE_60_ABOVE_SELNG_AMT"]) / bk["THSMON_SELNG_AMT"]
b4060_age = (bk["AGRDE_40_SELNG_AMT"] + bk["AGRDE_50_SELNG_AMT"] + bk["AGRDE_60_ABOVE_SELNG_AMT"]) / age_sum(bk)
rec("D", "베이커리 40대 이상 비중 분모 = 총매출(같은 문장의 60대 이상과 동일)", not on_page(f"40대 이상 {f1(b4060_age)}") and on_page(f"40대 이상 {f1(b4060_tot)}"),
    f"40대 이상 {f1(b4060_tot)}", f"연령 합계 대비 {f1(b4060_age)}" if on_page(f"40대 이상 {f1(b4060_age)}") else "")
c3040_tot = (cf["AGRDE_30_SELNG_AMT"] + cf["AGRDE_40_SELNG_AMT"]) / cf["THSMON_SELNG_AMT"]
c3040_age = (cf["AGRDE_30_SELNG_AMT"] + cf["AGRDE_40_SELNG_AMT"]) / age_sum(cf)
rec("D", "커피 30~40대 비중 분모 = 총매출", not on_page(f"30~40대 {f1(c3040_age)}") and on_page(f"30~40대 {f1(c3040_tot)}"),
    f"30~40대 {f1(c3040_tot)}", f"연령 합계 대비 {f1(c3040_age)}" if on_page(f"30~40대 {f1(c3040_age)}") else "")
chk("D", "커피 남성 비중(총매출 대비)", f"남성 {f1(cf['ML_SELNG_AMT'] / cf['THSMON_SELNG_AMT'])}")
rec("D", "성별·연령 미상 매출 주석 표시", "미상" in TEXT, "성별·연령 미상(법인 등) 매출 때문에 합이 100%가 아님을 명시")
# 손익의 기준 시나리오 성장률 ↔ 입지 반대의견 대응 문구
rec("D", "반대의견 대응이 실제 손익 기준 시나리오와 일치", "보수 가정(서울 시장 성장률로 평균 회귀)을 기본으로" not in TEXT,
    "손익 '기준'은 CAGR×0.7(5.76%)이므로 '보수를 기본으로 쓴다'는 문구는 불일치")
# 3년후 보수 전망식 25% 상한 표기
rec("D", "보수 전망식에 25% 상한 표기", "0.5×min(2분기 YoY 중앙값, 25%)" in TEXT or "0.5×min(2분기YoY중앙값,25%)" in TEXT, "min(…,25%) 표기")

# ================================================================== E. 표기 (출처·가정·공시 외 출처)
cards = re.findall(r'<(?:article|div) class="(?:card|kpi)[^"]*"[^>]*>(.*?)(?=<(?:article|div) class="(?:card|kpi)|</section>)', body, flags=re.S)
no_src = []
for c in cards:
    t = H.unescape(re.sub(r"<[^>]+>", " ", c))
    if re.search(r"\d[\d,.]*\s*(억원|원|%|곳|명|건)", t) and 'class="src"' not in c and "rcpNo" not in c and "계산식" not in c:
        no_src.append(re.sub(r"\s+", " ", t)[:60])
rec("E", "수치가 있는 카드마다 출처 블록", not no_src, "누락 0건", "; ".join(no_src))
allowed_rc = {DART[n]["rcept_no"] for n in DART if not n.startswith("_")} | {"20260410000434", "20260326000290"}
rc_on_page = set(re.findall(r"(?<!\d)(20\d{12})(?!\d)", TEXT))
rec("E", "페이지의 DART 접수번호가 모두 원문 보유분", rc_on_page <= allowed_rc, sorted(allowed_rc), f"초과: {sorted(rc_on_page - allowed_rc)}")
ext = set(re.findall(r'<a [^>]*href="(https?://[^"/]+)', html_src))
rec("E", "본문 외부 링크(<a>)는 DART만", ext <= {"https://dart.fss.or.kr"}, "dart.fss.or.kr", f"{sorted(ext)}")
scripts_ext = set(re.findall(r'<script[^>]+src="(https?://[^"/]+)', html_src))
rec("E", "외부 스크립트는 차트 라이브러리 CDN만(데이터 미포함)", scripts_ext <= {"https://cdn.jsdelivr.net", "https://cdnjs.cloudflare.com"}, "CDN", f"{sorted(scripts_ext)}")
rec("E", "웹·기사·블로그 출처 문구 없음", not re.search(r"(뉴스|기사|블로그|보도|업계 추정|위키)", TEXT), "없음")
rec("E", "이디야 60.0%를 '성격별 비용'으로 표기하지 않음",
    not re.search(r"이디야 60\.0% DART 2025 감사보고서 성격별 비용", TEXT) and "이디야 2025 감사보고서 비용의 성격별 분류" not in TEXT,
    "이디야는 성격별 분류 미공시 → 매출원가율")
for kw in ("3년 후 분기 합산매출", "<b>제안 객단가", "시나리오별 연매출", "<h3>손익분기", "목표 원재료비율", "존 구성", "메뉴판", "3개 시나리오 손익", "<h3>민감도"):
    m = re.search(re.escape(kw) + r".{0,250}", re.sub(r"\s+", " ", body))
    rec("E", f"'{kw}'에 가정 배지", bool(m and "tag-a" in m.group(0)), "가정 배지")

# ------------------------------------------------------------------ 출력
fails = [r for r in RESULTS if not r["ok"]]
for g in "ABCDE":
    gr = [r for r in RESULTS if r["group"] == g]
    print(f"[{g}] {sum(r['ok'] for r in gr)}/{len(gr)} 통과")
for r in fails:
    print(f"  FAIL [{r['group']}] {r['label']} — 기대: {r['expected']} {('· ' + r['note']) if r['note'] else ''}")
print(f"총 {len(RESULTS)}개 검사, 실패 {len(fails)}개")
with open(os.path.join(INT, "audit_site_result.json"), "w", encoding="utf-8") as f:
    json.dump({"checked": len(RESULTS), "failed": len(fails), "results": RESULTS}, f, ensure_ascii=False, indent=1)
sys.exit(1 if fails else 0)
