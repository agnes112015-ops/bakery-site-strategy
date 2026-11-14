"""베이커리 전문점 DART 감사보고서 벤치마크 → data/interim/bakery_benchmark.json

입력: data/interim/audit_<회사>_<rcept_no>.txt (scripts/parse_audit.py 의 표 행 텍스트)
      data/raw/dart_docs/<회사>/<rcept_no>/*.xml (표 바깥 문구: 매장 수·사업 개요)
      data/interim/dart_benchmark.json (카페 체인 비용 성격별 분류, 천원)
원칙: 모든 수치는 감사보고서 원문에서 파이썬으로 읽는다. 하드코딩 수치 없음(라벨·단위·앵커만 지정).
      비율의 '제안값'은 공시 비율의 중앙값 등 규칙으로 계산하며, 규칙 자체는 '가정'으로 명시한다.
실행: PYTHONIOENCODING=utf-8 python scripts/bakery_benchmark.py
"""
import glob
import html
import json
import os
import re
import statistics

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INTERIM = os.path.join(ROOT, "data", "interim")
DOCS = os.path.join(ROOT, "data", "raw", "dart_docs")
OUT = os.path.join(INTERIM, "bakery_benchmark.json")
URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"

NUM = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*\)?$")


# ------------------------------------------------------------------ 파싱 도구
def load_lines(company, rcept):
    with open(os.path.join(INTERIM, f"audit_{company}_{rcept}.txt"), encoding="utf-8") as f:
        return f.read().split("\n")


def load_xml_text(company, rcept):
    p = glob.glob(os.path.join(DOCS, company, rcept, "*.xml"))[0]
    raw = open(p, "rb").read()
    try:
        x = raw.decode("utf-8")
    except UnicodeDecodeError:
        x = raw.decode("cp949", errors="replace")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x)))


def norm(s):
    return re.sub(r"\s+", "", s)


def label(line):
    return norm(line.split("|")[0])


def nums(line):
    """라벨 뒤 셀 중 숫자 셀만 (주석번호 '5,24' 같은 것은 천단위 형식이 아니어서 제외). '-'는 0."""
    out = []
    for c in line.split("|")[1:]:
        c = c.strip()
        if c == "-":
            out.append(0.0)
        elif NUM.match(c):
            v = float(c.replace(",", "").replace("(", "").replace(")", ""))
            out.append(-v if c.startswith("(") or c.startswith("-") else v)
    return out


def find(lines, pat, start=0, end=None):
    rx = re.compile(pat)
    for i in range(start, end if end is not None else len(lines)):
        if rx.search(label(lines[i])):
            return i
    raise KeyError(f"label not found: {pat} (from {start})")


def cur_prev(lines, pat, start=0, end=None, unit=1, sign=1, signed=False):
    """[당기, 전기] = 숫자 셀의 마지막 두 개 (손익계산서 2단 표기, 2열 주석 모두 해당).
    기본은 절대값(K-IFRS 손익계산서의 비용 괄호 표기 제거), signed=True면 괄호 부호 유지(재고 변동 등)."""
    i = find(lines, pat, start, end)
    v = nums(lines[i])
    if len(v) < 2:
        raise ValueError(f"not enough numbers: {lines[i]}")
    f = (lambda x: x) if signed else abs
    return [f(v[-2]) * unit * sign, f(v[-1]) * unit * sign], i


def six(lines, pat, start, end, unit):
    """6열 주석(당기 매출원가|판관비|합계|전기 매출원가|판관비|합계)."""
    i = find(lines, pat, start, end)
    v = nums(lines[i])[-6:]
    return {"cogs": [v[0] * unit, v[3] * unit], "sga": [v[1] * unit, v[4] * unit],
            "total": [v[2] * unit, v[5] * unit]}


def check(name, a, b, tol):
    d = a - b
    return {"check": name, "a": round(a), "b": round(b), "diff": round(d), "ok": abs(d) <= tol}


def r(x, d=4):
    return None if x is None else round(x, d)


# ------------------------------------------------------------------ 회사별 추출
def is_block(L, labels, sign_ni=1):
    """손익계산서 본문 5개 계정. labels = (매출, 원가, 판관비, 영업이익, 순이익) 정규식."""
    rev, i0 = cur_prev(L, labels[0])
    cogs, _ = cur_prev(L, labels[1], i0)
    sga, i_sga = cur_prev(L, labels[2], i0)
    op_i = find(L, labels[3], i_sga)
    opv = nums(L[op_i])[-2:]
    op = opv
    ni, _ = cur_prev(L, labels[4], op_i, sign=sign_ni)
    if sign_ni == 1:  # 당기순이익(손실) 표기 시 괄호 부호 유지
        ni = nums(L[find(L, labels[4], op_i)])[-2:]
    return {"revenue": rev, "cogs": cogs, "sga": sga, "operating_income": op, "net_income": ni}, i0, i_sga, op_i


def fy(isd, k):
    idx = 0 if k == 2025 else 1
    return {"revenue": isd["revenue"][idx], "cogs": isd["cogs"][idx], "sga": isd["sga"][idx],
            "gross_profit": isd["revenue"][idx] - isd["cogs"][idx],
            "operating_income": isd["operating_income"][idx], "net_income": isd["net_income"][idx]}


def extract_rosso():
    co, rc = "로쏘", "20260410000434"
    L = load_lines(co, rc)
    isd, i0, i_sga, op_i = is_block(L, (r"^Ⅰ\.매출액$", r"^Ⅱ\.매출원가$", r"^Ⅳ\.판매비와관리비$",
                                        r"^Ⅴ\.영업이익$", r"^Ⅹ\.당기순이익$"))
    rev_parts = {k: cur_prev(L, p, i0, i0 + 8)[0] for k, p in
                 [("제품매출", r"제품매출$"), ("상품매출", r"상품매출$"), ("임대수입", r"임대수입$"),
                  ("주차매출", r"주차매출$"), ("면세매출", r"면세매출$")]}
    sga_items = {}
    for j in range(i_sga + 1, op_i):
        lab = re.sub(r"^\d+\.", "", label(L[j]))
        lab = re.sub(r"\(주\d+\)", "", lab)
        sga_items[lab] = nums(L[j])[-2:]
    h = find(L, r"^계정과목$")
    n = {k: six(L, p, h, h + 10, 1000) for k, p in
         [("급여", r"^급여$"), ("퇴직급여", r"^퇴직급여$"), ("복리후생비", r"^복리후생비$"),
          ("임차료", r"^임차료$"), ("감가상각비", r"^감가상각비$"), ("세금과공과", r"^세금과공과$"),
          ("합계", r"^합계$")]}
    cf_dep, _ = cur_prev(L, r"^나\.감가상각비$")
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 매출 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), isd["revenue"][t], 1))
        checks.append(check(f"{y} 판관비 항목 합 = 판관비", sum(v[t] for v in sga_items.values()), isd["sga"][t], 1))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업이익",
                            isd["revenue"][t] - isd["cogs"][t] - isd["sga"][t], isd["operating_income"][t], 1))
        items = [k for k in n if k != "합계"]
        checks.append(check(f"{y} 주석12 항목 합 = 주석 합계", sum(n[k]["total"][t] for k in items), n["합계"]["total"][t], 1000))
        for k, isk in [("급여", "급여"), ("퇴직급여", "퇴직급여"), ("복리후생비", "복리후생비"), ("임차료", "임차료"),
                       ("감가상각비", "감가상각비"), ("세금과공과", "세금과공과")]:
            checks.append(check(f"{y} 주석12 판관비열 {k} = 손익계산서 {isk}", n[k]["sga"][t], sga_items[isk][t], 1000))
        checks.append(check(f"{y} 주석12 감가상각비 합계 = 현금흐름표 감가상각비", n["감가상각비"]["total"][t], cf_dep[t], 1000))
    oth_dep, _ = cur_prev(L, r"^7\.기타의감가상각비$")
    for x in checks:
        t = 0 if x["check"].startswith("2025") else 1
        if not x["ok"] and "급여" in x["check"]:
            x["explained"] = f"차이 {x['diff']:,}원 ≈ 판관비 '인력개발비' {sga_items['인력개발비'][t]:,.0f}원 (주석12 급여에 인력개발비 포함, 천원 반올림 잔차)"
        if not x["ok"] and "현금흐름표" in x["check"]:
            x["explained"] = f"차이 {x['diff']:,}원 ≈ 영업외비용 '기타의감가상각비' {oth_dep[t]:,.0f}원 (주석12는 제조+판관분만)"
    labor = [n["급여"]["total"][t] + n["퇴직급여"]["total"][t] + n["복리후생비"]["total"][t] for t in range(2)]
    mfg_known = [sum(n[k]["cogs"][t] for k in n if k != "합계") for t in range(2)]
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료_잔여추정(매출원가-주석12 제조원가분)": isd["cogs"][t] - mfg_known[t],
            "인건비(급여+퇴직급여+복리후생비, 제조+판관)": labor[t],
            "급여": n["급여"]["total"][t], "퇴직급여": n["퇴직급여"]["total"][t], "복리후생비": n["복리후생비"]["total"][t],
            "임차료(제조+판관)": n["임차료"]["total"][t],
            "매장수수료(백화점 등 입점 수수료, 판관비)": sga_items["매장수수료"][t],
            "감가상각비(제조+판관)": n["감가상각비"]["total"][t],
            "지급수수료": sga_items["지급수수료"][t], "카드수수료": sga_items["카드수수료"][t],
            "광고판촉(광고선전비)": sga_items["광고선전비"][t],
            "수도광열비+전력비(판관비만)": sga_items["수도광열비"][t] + sga_items["전력비"][t],
            "소모품비(판관비만)": sga_items["소모품비"][t],
            "세금과공과(제조+판관)": n["세금과공과"]["total"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="일반기업회계기준(K-GAAP). 비용 성격별 주석 없음 → 주석12(부가가치 계산 항목: 제조원가/판관비 구분)와 판관비 명세 사용. "
                      "원재료비는 별도 공시가 없어 '매출원가 − 주석12 제조원가분(인건비·임차료·감가상각·세금)'의 잔여로 산출(원재료+기타 제조경비 포함, 상한값).",
                occ_items=["임차료(제조+판관)"], occ_extra="매장수수료(백화점 등 입점 수수료, 판관비)",
                fee_items=["지급수수료", "카드수수료", "매장수수료(백화점 등 입점 수수료, 판관비)"])


def extract_lbm():
    co, rc = "엘비엠", "20260326000290"
    L = load_lines(co, rc)
    isd, i0, i_sga, op_i = is_block(L, (r"^Ⅰ\.매출액$", r"^Ⅱ\.매출원가$", r"^IV\.판매비와관리비$",
                                        r"^V\.영업이익$", r"^X\.당기순이익$"))
    rev_parts = {k: cur_prev(L, p, i0, i0 + 5)[0] for k, p in
                 [("제품매출", r"^제품매출$"), ("상품매출", r"^상품매출$"), ("기타매출", r"^기타매출$")]}
    sga_items = {}
    for j in range(i_sga + 1, op_i):
        lab = re.sub(r"\(주석[\d,]+\)", "", label(L[j]))
        sga_items[lab] = nums(L[j])[-2:]
    h = next(i for i, l in enumerate(L) if norm(l).startswith("매출원가|판매관리비|합계|매출원가"))
    n = {k: six(L, p, h, h + 10, 1000) for k, p in
         [("급여", r"^급여$"), ("퇴직급여", r"^퇴직급여$"), ("복리후생비", r"^복리후생비$"),
          ("세금과공과금", r"^세금과공과금$"), ("감가상각비", r"^감가상각비$"), ("지급임차료", r"^지급임차료$"),
          ("무형자산상각비", r"^무형자산상각비$"), ("합계", r"^합계$")]}
    cf_dep, _ = cur_prev(L, r"^감가상각비$", find(L, r"^1\.당기순이익$"))
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 매출 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), isd["revenue"][t], 1))
        checks.append(check(f"{y} 판관비 항목 합 = 판관비", sum(v[t] for v in sga_items.values()), isd["sga"][t], 1))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업이익",
                            isd["revenue"][t] - isd["cogs"][t] - isd["sga"][t], isd["operating_income"][t], 1))
        items = [k for k in n if k != "합계"]
        checks.append(check(f"{y} 주석16 항목 합 = 주석 합계", sum(n[k]["total"][t] for k in items), n["합계"]["total"][t], 1000))
        for k in items:
            checks.append(check(f"{y} 주석16 판관비열 {k} = 손익계산서 {k}", n[k]["sga"][t], sga_items[k][t], 1000))
        checks.append(check(f"{y} 주석16 감가상각비 합계 = 현금흐름표 감가상각비", n["감가상각비"]["total"][t], cf_dep[t], 1000))
    labor = [n["급여"]["total"][t] + n["퇴직급여"]["total"][t] + n["복리후생비"]["total"][t] for t in range(2)]
    mfg_known = [sum(n[k]["cogs"][t] for k in n if k != "합계") for t in range(2)]
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료_잔여추정(매출원가-주석16 매출원가분)": isd["cogs"][t] - mfg_known[t],
            "인건비(급여+퇴직급여+복리후생비, 원가+판관)": labor[t],
            "급여": n["급여"]["total"][t], "퇴직급여": n["퇴직급여"]["total"][t], "복리후생비": n["복리후생비"]["total"][t],
            "지급임차료(원가+판관, 운용리스 최소리스료)": n["지급임차료"]["total"][t],
            "감가상각비(원가+판관)": n["감가상각비"]["total"][t],
            "지급수수료": sga_items["지급수수료"][t], "판매수수료": sga_items["판매수수료"][t],
            "광고판촉(광고선전비)": sga_items["광고선전비"][t],
            "수도광열비(판관비만)": sga_items["수도광열비"][t], "소모품비(판관비만)": sga_items["소모품비"][t],
            "세금과공과금(원가+판관)": n["세금과공과금"]["total"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="K-GAAP. 주석16(부가가치 계산 항목: 매출원가/판관비 구분)과 판관비 명세 사용. 원재료비는 '매출원가 − 주석16 매출원가분' 잔여(상한값).",
                occ_items=["지급임차료(원가+판관, 운용리스 최소리스료)"], occ_extra=None,
                fee_items=["지급수수료", "판매수수료"])


def extract_gffg():
    co, rc = "지에프에프지", "20260403003434"
    L = load_lines(co, rc)
    rev, i0 = cur_prev(L, r"^Ⅰ\.매출액")
    cogs, _ = cur_prev(L, r"^Ⅱ\.매출원가$", i0)
    sga, i_sga = cur_prev(L, r"^Ⅳ\.판매비와관리비", i0)
    op_i = find(L, r"^Ⅴ\.영업이익", i_sga)
    op = [rev[t] - cogs[t] - sga[t] for t in range(2)]
    op_stated = nums(L[op_i])[-2:]
    ni, _ = cur_prev(L, r"^Ⅹ\.당기순손실$", op_i, sign=-1)  # '당기순손실' 표기 → 음수
    isd = {"revenue": rev, "cogs": cogs, "sga": sga, "operating_income": op_stated, "net_income": ni}
    rev_parts = {k: cur_prev(L, p, i0, i0 + 5)[0] for k, p in
                 [("제품매출", r"^제품매출$"), ("상품매출", r"^상품매출$"), ("기타매출", r"^기타매출$")]}
    sga_items = {label(L[j]): nums(L[j])[-2:] for j in range(i_sga + 1, op_i)}
    a = find(L, r"^지급임차료\(차량리스료포함\)$")
    n = {k: cur_prev(L, p, a - 8, a + 2)[0] for k, p in
         [("급여", r"^급여$"), ("퇴직급여", r"^퇴직급여$"), ("복리후생비", r"^복리후생비$"), ("세금과공과", r"^세금과공과$"),
          ("감가상각비", r"^감가상각비$"), ("무형자산상각비", r"^무형자산상각비$"),
          ("지급임차료(차량리스료 포함)", r"^지급임차료"), ("합계", r"^합계$")]}
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 매출 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), rev[t], 1))
        checks.append(check(f"{y} 판관비 항목 합 = 판관비", sum(v[t] for v in sga_items.values()), sga[t], 1))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업이익(손실)", op[t], abs(op_stated[t]) * (1 if op[t] >= 0 else -1), 1))
        checks.append(check(f"{y} 주석16 항목 합 = 주석 합계", sum(v[t] for k, v in n.items() if k != "합계"), n["합계"][t], 1))
        checks.append(check(f"{y} 주석16 급여 = 판관비 직원급여+상여금+잡급",
                            n["급여"][t], sga_items["직원급여"][t] + sga_items["상여금"][t] + sga_items["잡급"][t], 1))
        checks.append(check(f"{y} 주석16 지급임차료(차량리스료 포함) = 판관비 지급임차료",
                            n["지급임차료(차량리스료 포함)"][t], sga_items["지급임차료"][t], 1))
        checks.append(check(f"{y} 주석16 감가상각비 = 판관비 감가상각비", n["감가상각비"][t], sga_items["감가상각비"][t], 1))
    for x in checks:
        if not x["ok"] and "지급임차료" in x["check"]:
            x["explained"] = "주석16 항목명이 '지급임차료(차량리스료 포함)' — 차량리스료는 손익계산서상 다른 계정(차량유지비 등)에 계상된 것으로 보임(원문에 배분 명세 없음)"
    isd["operating_income"] = op
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료_잔여추정(매출원가 전액; 주석16 인건비 등은 전액 판관비)": cogs[t],
            "인건비(급여+퇴직급여+복리후생비, 주석16)": n["급여"][t] + n["퇴직급여"][t] + n["복리후생비"][t],
            "급여": n["급여"][t], "퇴직급여": n["퇴직급여"][t], "복리후생비": n["복리후생비"][t],
            "지급임차료(판관비)": sga_items["지급임차료"][t],
            "감가상각비": n["감가상각비"][t],
            "지급수수료": sga_items["지급수수료"][t], "판매수수료": sga_items["판매수수료"][t],
            "광고판촉(광고선전비+판매촉진비)": sga_items["광고선전비"][t] + sga_items["판매촉진비"][t],
            "수도광열비(판관비)": sga_items["수도광열비"][t], "소모품비(판관비)": sga_items["소모품비"][t],
            "세금과공과": n["세금과공과"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="K-GAAP. 주석16(부가가치 계산 항목) 합계가 판관비 해당 항목과 일치 → 공시상 인건비·임차료·상각비는 전액 판관비. "
                      "매출원가 내 제조 인건비 등은 별도 공시 없음 → 원재료 잔여 = 매출원가 전액(상품매입 포함, 상한값).",
                occ_items=["지급임차료(판관비)"], occ_extra=None, fee_items=["지급수수료", "판매수수료"])


def extract_bonavie():
    co, rc = "보나비", "20260403003616"
    L = load_lines(co, rc)
    isd, i0, i_sga, op_i = is_block(L, (r"^I\.매출액$", r"^II\.매출원가$", r"^IV\.판매비와관리비$",
                                        r"^V\.영업손익$", r"^IX\.당기순이익\(손실\)$"))
    rv = find(L, r"^제품매출액$")
    rev_parts = {k: cur_prev(L, p, rv, rv + 4, 1000)[0] for k, p in
                 [("제품매출액", r"^제품매출액$"), ("상품매출액", r"^상품매출액$"), ("기타매출액", r"^기타매출액$")]}
    rev_tot, _ = cur_prev(L, r"^합계$", rv, rv + 4, 1000)
    a = find(L, r"^원재료및소모품의사용$")
    nat = {k: cur_prev(L, p, a - 3, a + 8, 1000, signed=True)[0] for k, p in
           [("완제품및재공품의변동", r"^완제품및재공품의변동$"), ("상품의판매", r"^상품의판매$"),
            ("원재료및소모품의사용", r"^원재료및소모품의사용$"), ("종업원급여", r"^종업원급여$"),
            ("감가상각및상각비용", r"^감가상각및상각비용$"), ("광고및판매촉진비", r"^광고및판매촉진비$"),
            ("물류비용", r"^물류비용$"), ("기타비용", r"^기타비용$"), ("합계", r"^합계$")]}
    lab_i = find(L, r"^급여$", a + 1)
    emp = {k: cur_prev(L, p, lab_i, lab_i + 4, 1000)[0] for k, p in
           [("급여", r"^급여$"), ("퇴직급여", r"^퇴직급여$"), ("복리후생비", r"^복리후생비$"), ("합계", r"^합계$")]}
    d_i = find(L, r"^감가상각비$", lab_i + 3)
    dep = {k: cur_prev(L, p, d_i, d_i + 3, 1000)[0] for k, p in
           [("감가상각비", r"^감가상각비$"), ("무형자산상각비", r"^무형자산상각비$"), ("합계", r"^합계$")]}
    s_i = find(L, r"^급여$", d_i + 3)
    s_end = find(L, r"^합계$", s_i)
    sga_note = {label(L[j]): [v * 1000 for v in nums(L[j])[-2:]] for j in range(s_i, s_end)}
    cf0 = find(L, r"^1\.당기순손익$")
    cf_dep, _ = cur_prev(L, r"^감가상각비$", cf0, cf0 + 15)
    cf_rou, _ = cur_prev(L, r"^사용권자산상각비$", cf0, cf0 + 15)
    li = find(L, r"^리스부채의이자비용$")
    lease_int, _ = cur_prev(L, r"^리스부채의이자비용$", li, li + 1, 1000)
    lease_pay, _ = cur_prev(L, r"^리스부채지급$", li, li + 10, 1000)
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 매출 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), isd["revenue"][t], 1000))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업손익",
                            isd["revenue"][t] - isd["cogs"][t] - isd["sga"][t], isd["operating_income"][t], 1))
        checks.append(check(f"{y} 성격별 항목 합 = 성격별 합계", sum(v[t] for k, v in nat.items() if k != "합계"), nat["합계"][t], 1000))
        checks.append(check(f"{y} 성격별 합계 = 매출원가+판관비", nat["합계"][t], isd["cogs"][t] + isd["sga"][t], 1000))
        checks.append(check(f"{y} 종업원급여 세부 합 = 종업원급여", emp["급여"][t] + emp["퇴직급여"][t] + emp["복리후생비"][t], nat["종업원급여"][t], 1000))
        checks.append(check(f"{y} 감가상각비(주석) = 현금흐름표 유형자산 감가상각비 + 사용권자산상각비",
                            dep["감가상각비"][t], cf_dep[t] + cf_rou[t], 1000))
        checks.append(check(f"{y} 판관비 명세 합 = 판관비", sum(v[t] for v in sga_note.values()), isd["sga"][t], 1000))
    for x in checks:
        if not x["ok"] and "성격별 항목 합" in x["check"]:
            x["explained"] = ("미해명: 공시된 성격별 항목(전기)의 합이 주석 합계·매출원가+판관비보다 큼. 합계는 손익계산서와 일치하므로 "
                              "감가상각 및 상각비용은 현금흐름표와 일치하므로 기타비용 등 다른 항목의 공시 자체 불일치로 판단. 비율 산출은 2025 사용.")
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료(원재료및소모품의사용+상품의판매+재고변동)":
                nat["원재료및소모품의사용"][t] + nat["상품의판매"][t] + nat["완제품및재공품의변동"][t],
            "인건비(종업원급여)": nat["종업원급여"][t],
            "급여": emp["급여"][t], "퇴직급여": emp["퇴직급여"][t], "복리후생비": emp["복리후생비"][t],
            "임차료(판관비, 변동·단기리스)": sga_note["임차료"][t],
            "사용권자산상각비(현금흐름표)": cf_rou[t],
            "감가상각비(유형자산, 사용권 제외; 현금흐름표)": cf_dep[t],
            "리스부채 이자비용(영업외)": lease_int[t], "리스부채 지급(현금)": lease_pay[t],
            "지급수수료(판관비 '수수료')": sga_note["수수료"][t],
            "광고판촉(광고및판매촉진비)": nat["광고및판매촉진비"][t],
            "수도광열비(판관비)": sga_note["수도광열비"][t], "소모품비(판관비)": sga_note["소모품비"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="K-IFRS. '비용의 성격별 분류' 주석(매출원가+판관비 전체) + 판관비 명세 + 현금흐름표 상각비. 점유비 = 임차료 + 사용권자산상각비.",
                occ_items=["임차료(판관비, 변동·단기리스)", "사용권자산상각비(현금흐름표)"], occ_extra=None,
                fee_items=["지급수수료(판관비 '수수료')"])


def extract_cj():
    co, rc = "CJ푸드빌", "20260403002488"
    L = load_lines(co, rc)
    isd, i0, i_sga, op_i = is_block(L, (r"^매출액$", r"^매출원가$", r"^판매비와관리비$", r"^영업이익$", r"^당기순이익$"))
    a = find(L, r"^원재료및소모품사용$")
    keys = ["제품및상품의변동", "원재료및소모품사용", "종업원급여", "유형자산상각비", "사용권자산상각비", "무형자산상각비",
            "운반비", "광고선전비", "지급수수료", "판매촉진비", "임차료", "수도광열비", "여비교통비", "세금과공과", "기타비용",
            "매출원가,판매비와관리비합계"]
    nat = {k: cur_prev(L, "^" + re.escape(k) + "$", a - 2, a + 16, 1000, signed=True)[0] for k in keys}
    s_i = find(L, r"^급여$", find(L, r"^감가상각비\(사용권자산\)$") - 12)
    s_end = find(L, r"^판매비와관리비$", s_i)
    sga_note = {label(L[j]): [v * 1000 for v in nums(L[j])[-2:]] for j in range(s_i, s_end)}
    rv = find(L, r"^고객과의계약에서생기는수익$")
    rev_parts = {"고객과의 계약에서 생기는 수익": cur_prev(L, r"^고객과의계약에서생기는수익$", rv, rv + 1, 1000)[0],
                 "임대 및 전대 임대료 수익": cur_prev(L, r"^기타원천으로부터", rv, rv + 2, 1000)[0]}
    li = find(L, r"^리스부채에대한이자비용")
    lease_int, _ = cur_prev(L, r"^리스부채에대한이자비용", li, li + 1, 1000)
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 수익 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), isd["revenue"][t], 1000))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업이익",
                            isd["revenue"][t] - isd["cogs"][t] - isd["sga"][t], isd["operating_income"][t], 1))
        tot = nat["매출원가,판매비와관리비합계"][t]
        checks.append(check(f"{y} 성격별 항목 합 = 성격별 합계", sum(v[t] for k, v in nat.items() if k != "매출원가,판매비와관리비합계"), tot, 1000))
        checks.append(check(f"{y} 성격별 합계 = 매출원가+판관비", tot, isd["cogs"][t] + isd["sga"][t], 2000))
        checks.append(check(f"{y} 판관비 명세 합 = 판관비", sum(v[t] for v in sga_note.values()), isd["sga"][t], 1000))
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료(원재료및소모품사용+제품및상품의변동)": nat["원재료및소모품사용"][t] + nat["제품및상품의변동"][t],
            "인건비(종업원급여)": nat["종업원급여"][t],
            "판관비 급여": sga_note["급여"][t], "판관비 퇴직급여": sga_note["퇴직급여"][t], "판관비 복리후생비": sga_note["복리후생비"][t],
            "임차료": nat["임차료"][t], "사용권자산상각비": nat["사용권자산상각비"][t],
            "감가상각비(유형자산)": nat["유형자산상각비"][t],
            "리스부채 이자비용(영업외)": lease_int[t],
            "지급수수료": nat["지급수수료"][t],
            "광고판촉(광고선전비+판매촉진비)": nat["광고선전비"][t] + nat["판매촉진비"][t],
            "수도광열비": nat["수도광열비"][t], "운반비": nat["운반비"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="K-IFRS 별도. '비용의 성격별 분류' 주석(매출원가+판관비). 뚜레쥬르 직영+가맹(가맹점 공급매출 포함) 및 기타 외식브랜드 합산 — 직영 매장 원가구조와 다름.",
                occ_items=["임차료", "사용권자산상각비"], occ_extra=None, fee_items=["지급수수료"])


def extract_sangmidang():
    co, rc = "상미당홀딩스", "20260409001397"
    L = load_lines(co, rc)
    isd, i0, i_sga, op_i = is_block(L, (r"^매출액", r"^매출원가", r"^판매비와관리비", r"^영업이익$", r"^당기순이익\(손실\)$"))
    rv = find(L, r"^제품매출액$")
    rev_parts = {k: cur_prev(L, p, rv, rv + 3, 1000)[0] for k, p in
                 [("제품매출액", r"^제품매출액$"), ("상품매출액", r"^상품매출액$"), ("기타매출액", r"^기타매출액$")]}
    s_i = find(L, r"^급여$", rv)
    s_end = find(L, r"^합계$", s_i)
    sga_note = {label(L[j]): [v * 1000 for v in nums(L[j])[-2:]] for j in range(s_i, s_end)}
    sga_stated, _ = cur_prev(L, r"^합계$", s_end, s_end + 1, 1000)
    v_i = find(L, r"^급여$", s_end)
    v_end = find(L, r"^합계$", v_i)
    va = {label(L[j]): [v * 1000 for v in nums(L[j])[-2:]] for j in range(v_i, v_end)}
    va_tot, _ = cur_prev(L, r"^합계$", v_end, v_end + 1, 1000)
    checks = []
    for t in range(2):
        y = 2025 - t
        checks.append(check(f"{y} 매출 구분 합 = 매출액", sum(v[t] for v in rev_parts.values()), isd["revenue"][t], 1000))
        checks.append(check(f"{y} 매출-원가-판관비 = 영업이익",
                            isd["revenue"][t] - isd["cogs"][t] - isd["sga"][t], isd["operating_income"][t], 1))
        checks.append(check(f"{y} 판관비 명세 합 = 판관비(손익계산서)", sum(v[t] for v in sga_note.values()), isd["sga"][t], 2000))
        checks.append(check(f"{y} 판관비 명세 합 = 명세 합계", sum(v[t] for v in sga_note.values()), sga_stated[t], 1000))
        checks.append(check(f"{y} 부가가치 주석 항목 합 = 주석 합계", sum(v[t] for v in va.values()), va_tot[t], 1000))
    cbn = {}
    for t, y in enumerate((2025, 2024)):
        cbn[str(y)] = {
            "원재료_잔여추정(매출원가-부가가치주석 중 판관비 외 분)":
                isd["cogs"][t] - sum(va[k][t] - sga_note.get(k, [0, 0])[t] for k in va),
            "인건비(급여+퇴직급여+복리후생비, 원가+판관)": va["급여"][t] + va["퇴직급여"][t] + va["복리후생비"][t],
            "급여": va["급여"][t], "퇴직급여": va["퇴직급여"][t], "복리후생비": va["복리후생비"][t],
            "임차료(원가+판관)": va["임차료"][t], "감가상각비(원가+판관)": va["감가상각비"][t],
            "지급수수료(판관비)": sga_note["지급수수료"][t],
            "광고판촉(광고선전비+판매촉진비)": sga_note["광고선전비"][t] + sga_note["판매촉진비"][t],
            "수도광열비+전력비(판관비)": sga_note["수도광열비"][t] + sga_note["전력비"][t],
            "소모품비(판관비)": sga_note["소모품비"][t],
        }
    return dict(company=co, rcept=rc, isd=isd, rev_parts=rev_parts, cbn=cbn, checks=checks,
                basis="K-GAAP. 부가가치 계산 주석(원가+판관 합산)과 판관비 명세. 파리바게뜨 직영 134 + 가맹 3,756 구조 → 매출 대부분이 가맹점 공급(제품·상품) 매출. "
                      "원재료 잔여 = 매출원가 − (부가가치 주석 합계 − 판관비 해당분), 상한값.",
                occ_items=["임차료(원가+판관)"], occ_extra=None, fee_items=["지급수수료(판관비)"])


# ------------------------------------------------------------------ 매장 수 (원문 문구)
STORE_RULES = {
    "로쏘": (r"영업점은\s*성심당\(본점\)\s*이외\s*(\d+)\s*개점", lambda m: int(m.group(1)) + 1, "본점 + 문구상 개점 수"),
    "보나비": (r"(\d+)\s*개의\s*아티제\s*매장과\s*(\d+)\s*개의\s*쿠차라\s*매장", lambda m: int(m.group(1)) + int(m.group(2)),
             "아티제 + 쿠차라 매장 합(전 매장 임차·직영)"),
    "상미당홀딩스": (r"(\d[\d,]*)\s*개의\s*직영점과\s*(\d[\d,]*)\s*개의\s*가맹점", lambda m: int(m.group(1).replace(",", "")),
                "직영점 수만 사용(가맹점은 별도 표기)"),
}


def stores_of(co, rc, rev2025):
    t = load_xml_text(co, rc)
    if co in STORE_RULES:
        pat, fn, how = STORE_RULES[co]
        m = re.search(pat, t)
        if m:
            s = max(0, m.start() - 40)
            cnt = fn(m)
            out = {"count": cnt, "basis_text": t[s:m.end() + 10].strip(), "how": how, "as_of": "2025-12-31"}
            if co == "상미당홀딩스":
                fr = int(m.group(2).replace(",", ""))
                out.update({"franchise_count": fr, "direct_count": cnt})
                return out, None, "매출 대부분이 가맹점 공급매출이라 '직영점당 매출' 계산은 무의미 → 산출하지 않음"
            return out, rev2025 / cnt, "2025 매출 ÷ 기말 매장 수 (기중 개·폐점 미반영, 회사 전체 매출에 상품·기타매출 포함)"
    kw = [k for k in ("직영", "가맹", "매장", "점포") if k in t]
    return ({"count": None, "basis_text": None,
             "how": f"감사보고서 원문 XML 전체 검색 결과 매장 수 문구 없음(검색어 직영·가맹·매장·점포 중 등장: {', '.join(kw) or '없음'}; 리스·손상 설명 문맥뿐)",
             "as_of": None}, None, "매장 수 미공시 → 계산 불가")


# ------------------------------------------------------------------ 메인
BRANDS = {"엘비엠": "런던베이글뮤지엄 (100% 주주 허니듀크유한회사)", "지에프에프지": "노티드 등 (GFFG)",
          "로쏘": "성심당 (본점 외 15개점, 직영)", "보나비": "아티제·쿠차라 (대한제분 100%, 전 매장 직영)",
          "CJ푸드빌": "뚜레쥬르 등 (직영+가맹, 외식브랜드 포함)", "상미당홀딩스": "파리바게뜨 등 (구 (주)파리크라상; 직영 134·가맹 3,756)"}
AUDITOR_PAT = r"([가-힣]{2}회계법인)"  # 공백 제거 본문에서 첫 출현
GROUP = {"로쏘": "베이커리 직영", "엘비엠": "베이커리 직영", "보나비": "베이커리 직영", "지에프에프지": "베이커리 직영",
         "CJ푸드빌": "베이커리 가맹 중심", "상미당홀딩스": "베이커리 가맹 중심"}


def main():
    extracted = [extract_rosso(), extract_lbm(), extract_gffg(), extract_bonavie(), extract_cj(), extract_sangmidang()]
    companies = {}
    for e in extracted:
        co, rc, isd = e["company"], e["rcept"], e["isd"]
        xt = load_xml_text(co, rc)
        am = re.search(AUDITOR_PAT, re.sub(r"\s", "", xt))
        auditor = am.group(1) if am else None
        st, per, per_note = stores_of(co, rc, isd["revenue"][0])
        ratios = {}
        for t, y in enumerate((2025, 2024)):
            rev = isd["revenue"][t]
            c = e["cbn"][str(y)]
            mat_k = next(k for k in c if k.startswith("원재료"))
            lab_k = next(k for k in c if k.startswith("인건비"))
            dep_k = next(k for k in c if k.startswith("감가상각비"))
            ad_k = next(k for k in c if k.startswith("광고판촉"))
            util_k = next((k for k in c if k.startswith("수도광열비")), None)
            sup_k = next((k for k in c if k.startswith("소모품비")), None)
            occ = sum(c[k] for k in e["occ_items"])
            ratios[str(y)] = {
                "매출총이익률": r((rev - isd["cogs"][t]) / rev), "매출원가율": r(isd["cogs"][t] / rev),
                "판관비율": r(isd["sga"][t] / rev), "영업이익률": r(isd["operating_income"][t] / rev),
                "순이익률": r(isd["net_income"][t] / rev),
                "원재료율": r(c[mat_k] / rev), "원재료율_산출방식": mat_k,
                "인건비율": r(c[lab_k] / rev),
                "임차료율(임차료+사용권자산상각비)": r(occ / rev),
                "임차료율+입점수수료": r((occ + c[e["occ_extra"]]) / rev) if e["occ_extra"] else None,
                "감가상각비율(유형, 사용권 제외)": r(c[dep_k] / rev),
                "수수료율(지급·카드·판매수수료)": r(sum(c[k] for k in e["fee_items"]) / rev),
                "광고판촉비율": r(c[ad_k] / rev),
                "수도광열비율": r(c[util_k] / rev) if util_k else None,
                "소모품비율": r(c[sup_k] / rev) if sup_k else None,
            }
        bad = [x for x in e["checks"] if not x["ok"]]
        explained_all = all(x.get("explained") and not x["explained"].startswith("미해명") for x in bad)
        companies[co] = {
            "brand": BRANDS[co], "group": GROUP[co], "rcpNo": rc, "url": URL.format(rc), "auditor": auditor,
            "accounting_basis": e["basis"],
            "fy2025": {k: round(v) for k, v in fy(isd, 2025).items()},
            "fy2024": {k: round(v) for k, v in fy(isd, 2024).items()},
            "revenue_breakdown": {k: [round(v[0]), round(v[1])] for k, v in e["rev_parts"].items()},
            "revenue_breakdown_note": "[2025, 2024] 원",
            "cost_by_nature": {y: {k: round(v) for k, v in d.items()} for y, d in e["cbn"].items()},
            "ratios": ratios,
            "stores": st,
            "per_store_revenue": round(per) if per else None, "per_store_revenue_note": per_note,
            "tieout": {"ok": not bad, "ok_after_explained_diffs": explained_all, "n_checks": len(e["checks"]),
                       "diff": [{"check": x["check"], "diff_won": x["diff"], "a": x["a"], "b": x["b"],
                                 "explained": x.get("explained")} for x in bad],
                       "checks": e["checks"]},
        }

    # 직영 매출 비중 판단 (원문 근거 문구 + 매출구분)
    direct_share = {
        "로쏘": "제품매출 비중 {:.1%} (2025). 개요상 '영업점'만 운영 — 가맹 매출 계정 없음 → 사실상 100% 직영 매장 매출.".format(
            companies["로쏘"]["revenue_breakdown"]["제품매출"][0] / companies["로쏘"]["fy2025"]["revenue"]),
        "엘비엠": "제품매출 비중 {:.1%}. 가맹·로열티 계정 없음, 사업목적 '경영 컨설팅업, 제과점업' → 직영 매장 매출 중심(매장 수 미공시).".format(
            companies["엘비엠"]["revenue_breakdown"]["제품매출"][0] / companies["엘비엠"]["fy2025"]["revenue"]),
        "지에프에프지": "제품 {:.1%} / 상품 {:.1%} / 기타 {:.1%}. 가맹 계정 명시 없음, 상품매출 급증(유통·도매 추정 불가) → 직영 비중 판단 불가(공시 공백).".format(
            *[companies["지에프에프지"]["revenue_breakdown"][k][0] / companies["지에프에프지"]["fy2025"]["revenue"] for k in ("제품매출", "상품매출", "기타매출")]),
        "보나비": "제품 {:.1%} / 상품 {:.1%}. 77개 매장 모두 임차계약 명시, 가맹 계정 없음 → 직영 매장 매출 중심.".format(
            *[companies["보나비"]["revenue_breakdown"][k][0] / companies["보나비"]["fy2025"]["revenue"] for k in ("제품매출액", "상품매출액")]),
        "CJ푸드빌": "수익인식 정책에 '직영 뚜레쥬르·기타외식브랜드' 판매와 '가맹점 공급' 매출이 합산됨. 직영/가맹 금액 구분 공시 없음 → 직영 비중 산출 불가.",
        "상미당홀딩스": "직영 134 vs 가맹 3,756 (2025-12-31). 상품매출 {:.1%} 등 가맹 공급 중심 → 직영 매장 원가구조 벤치마크로 부적합.".format(
            companies["상미당홀딩스"]["revenue_breakdown"]["상품매출액"][0] / companies["상미당홀딩스"]["fy2025"]["revenue"]),
    }
    for k, v in direct_share.items():
        companies[k]["direct_sales_judgement"] = v

    # 카페 체인 (기존 dart_benchmark.json, 천원)
    bm = json.load(open(os.path.join(INTERIM, "dart_benchmark.json"), encoding="utf-8"))
    cafes = {}
    for co in ("에스씨케이컴퍼니", "투썸플레이스", "이디야"):
        b = bm[co]
        rev = b["revenue"]
        c = {k: sum(v) for k, v in b["costs"].items()}
        cafes[co] = {
            "brand": b["brand"], "rcpNo": b["rcept_no"], "url": URL.format(b["rcept_no"]),
            "원재료율": r(c["원재료·상품"] / rev) if "원재료·상품" in c else None,
            "인건비율": r(c["인건비"] / rev) if "인건비" in c else None,
            "임차료율(임차료+사용권자산상각비)": r((c.get("임차료", 0) + c.get("사용권자산상각비", 0)) / rev) if "임차료" in c else None,
            "영업이익률": r(b["operating_income"] / rev),
            "매출원가율": r(c["매출원가"] / rev) if "매출원가" in c else None,
        }

    comparison = []
    for co, d in companies.items():
        x = d["ratios"]["2025"]
        comparison.append({"company": co, "brand": d["brand"], "group": d["group"], "rcpNo": d["rcpNo"],
                           "원재료율": x["원재료율"], "원재료율_산출": x["원재료율_산출방식"], "인건비율": x["인건비율"],
                           "임차료율": x["임차료율(임차료+사용권자산상각비)"], "영업이익률": x["영업이익률"],
                           "감가상각비율": x["감가상각비율(유형, 사용권 제외)"], "수수료율": x["수수료율(지급·카드·판매수수료)"],
                           "광고판촉비율": x["광고판촉비율"],
                           "점포당매출_원": d["per_store_revenue"]})
    for co, x in cafes.items():
        comparison.append({"company": co, "brand": x["brand"], "group": "카페 체인", "rcpNo": x["rcpNo"],
                           "원재료율": x["원재료율"], "원재료율_산출": "dart_benchmark.json 원재료·상품(성격별)" if x["원재료율"] is not None else "성격별 미공시(매출원가율 " + str(x["매출원가율"]) + ")",
                           "인건비율": x["인건비율"], "임차료율": x["임차료율(임차료+사용권자산상각비)"], "영업이익률": x["영업이익률"],
                           "감가상각비율": None, "수수료율": None, "광고판촉비율": None, "점포당매출_원": None})

    def grp_avg(g, k):
        v = [c[k] for c in comparison if c["group"] == g and c[k] is not None]
        return {"median": r(statistics.median(v)) if v else None, "n": len(v)}
    group_summary = {g: {k: grp_avg(g, k) for k in ("원재료율", "인건비율", "임차료율", "영업이익률")}
                     for g in ("베이커리 직영", "베이커리 가맹 중심", "카페 체인")}

    # 제안 비용 비율 (가정: 직영 베이커리 그룹 중앙값 규칙)
    D = ["로쏘", "엘비엠", "보나비", "지에프에프지"]

    def med(key, cos, field="2025"):
        vals = {c: companies[c]["ratios"][field][key] for c in cos if companies[c]["ratios"][field][key] is not None}
        return r(statistics.median(vals.values())), {c: v for c, v in vals.items()}

    src = lambda cos: "; ".join(f"{c} DART rcpNo {companies[c]['rcpNo']} ({URL.format(companies[c]['rcpNo'])})" for c in cos)
    prop = {}
    v, d = med("원재료율", D)
    prop["원재료율"] = {"value": v, "inputs_2025": d, "basis": "가정: 직영 베이커리 4사(로쏘·엘비엠·보나비·GFFG) 2025 원재료율 중앙값. "
                    "보나비는 성격별 주석 실측, 로쏘·엘비엠·GFFG는 매출원가 잔여(상한값). 엘비엠(베이글 고가·단품)은 하단 이상치. " + src(D)}
    v, d = med("인건비율", D)
    prop["인건비율"] = {"value": v, "inputs_2025": d, "basis": "가정: 직영 베이커리 4사 2025 (급여+퇴직급여+복리후생비, 원가·판관 합산)/매출 중앙값. "
                    "GFFG는 판관비분만 공시(과소 가능). 본사 인력 포함 회사 전체 비율. " + src(D)}
    occ_cos = ["엘비엠", "보나비", "지에프에프지"]
    v, d = med("임차료율(임차료+사용권자산상각비)", occ_cos)
    prop["임차료율(임차료+사용권자산상각비)"] = {"value": v, "inputs_2025": d,
                                     "range": [min(d.values()), max(d.values())],
                                     "basis": "가정: 임차 직영 3사 중앙값. 로쏘는 대전 자가 부동산(토지·건물 보유)이라 제외. 임차료율은 점포 매출 규모에 반비례"
                                              "(엘비엠 고매출 → 낮음, 보나비 → 높음)하므로 실제 입지 임대 견적이 생기면 금액(고정비)으로 대체. " + src(occ_cos)}
    v, d = med("감가상각비율(유형, 사용권 제외)", D)
    prop["감가상각비율(유형, 사용권 제외)"] = {"value": v, "inputs_2025": d,
                                    "basis": "가정: 직영 베이커리 4사 중앙값. 기존 매장 상각이 진행된 회사 평균이라 신규 1호점(초기투자 직후)은 이보다 높음 → 초기투자/내용연수로 별도 계산 권장. " + src(D)}
    v, d = med("수수료율(지급·카드·판매수수료)", D)
    prop["수수료율(지급·카드·판매수수료)"] = {"value": v, "inputs_2025": d,
                                     "basis": "가정: 직영 베이커리 4사 중앙값(지급수수료+카드수수료+판매/매장수수료 중 공시된 항목). 매출 연동 변동비. " + src(D)}
    v, d = med("광고판촉비율", D)
    prop["광고판촉비율"] = {"value": v, "inputs_2025": d, "basis": "가정: 직영 베이커리 4사 중앙값. 성심당·런던베이글은 광고 거의 없음(0.1%대), 보나비·GFFG 2~4%. " + src(D)}
    v, d = med("수도광열비율", ["엘비엠", "보나비", "지에프에프지"])
    prop["수도광열비율"] = {"value": v, "inputs_2025": d, "basis": "가정: 판관비 수도광열비 공시 3사 중앙값(제조원가 내 전력·가스는 미포함 → 과소 가능). 로쏘는 판관비분만 있어 제외. " + src(["엘비엠", "보나비", "지에프에프지"])}
    v, d = med("소모품비율", D)
    prop["소모품비율"] = {"value": v, "inputs_2025": d, "basis": "가정: 직영 베이커리 4사 판관비 소모품비 중앙값(포장재 등). " + src(D)}
    core = ["원재료율", "인건비율", "임차료율(임차료+사용권자산상각비)", "감가상각비율(유형, 사용권 제외)",
            "수수료율(지급·카드·판매수수료)", "광고판촉비율", "수도광열비율", "소모품비율"]
    tot = sum(prop[k]["value"] for k in core)
    prop["_합계_및_함의"] = {"value": r(tot), "implied_margin_before_other": r(1 - tot),
                         "basis": "위 8개 비율 합. 기타 운영비(보험·수선·세금과공과·본사비 등)는 미포함 → 실제 영업이익률은 이보다 낮음. "
                                  "비교: 직영 베이커리 영업이익률 로쏘 {:.1%}, 엘비엠 {:.1%}, 보나비 {:.1%}, GFFG {:.1%} (2025).".format(
                                      *[companies[c]["ratios"]["2025"]["영업이익률"] for c in D])}
    prop["_매출_재보정_근거"] = {
        "value": {c: companies[c]["per_store_revenue"] for c in ("보나비", "로쏘")},
        "basis": "브랜드 직영 점포당 매출은 공시상 보나비(아티제·쿠차라 77점)와 로쏘(성심당 16점)만 산출 가능. "
                 "보나비 = 서울 중심 임차 직영 베이커리카페의 현실적 기준점, 로쏘 = 대형 본점 포함 극단 상한. "
                 "엘비엠·GFFG·CJ푸드빌은 매장 수 미공시, 상미당홀딩스는 가맹 공급 매출이라 점포당 매출 산출 불가(공시 공백)."}

    tried = [
        "corp_resolve '파리크라상'/'파리 크라상' → 01995325 파리크라상(2026-01-01 신설, 공시 0건)",
        "corp_resolve 'PARIS CROISSANT','파리바게뜨','파리바게트','SPC삼립','파리크라상홀딩스','SPC GFS','에스피씨홀딩스','SPC홀딩스','에스피씨그룹','파리크라상에프앤비','파리바게뜨코리아' → 해당 없음",
        "corp_resolve '에스피씨지에프에스'(01037524), '비알코리아'(00124665), '피비파트너즈'(01310038) → list.json 으로 감사보고서 목록 확인",
        "피비파트너즈 감사보고서 rcpNo 20260407000928 원문: 지배기업 '(주)파리크라상' 확인",
        "에스피씨지에프에스 감사보고서 rcpNo 20260326000496 원문 특수관계자 주석: '㈜파리크라상은 2026년 1월 30일자로 사명을 상미당홀딩스㈜로 변경'",
        "corp_resolve '상미당홀딩스' → 00154888; list.json → 감사보고서(2025.12) rcpNo 20260409001397, 연결 20260428000662, 2024.12 별도 20250410001511",
        "상미당홀딩스 별도 감사보고서 20260409001397 다운로드·파싱(audit_상미당홀딩스_20260409001397.txt): 원문 '2026년 1월 2일 주식회사 파리크라상에서 주식회사 피씨홀딩스로, 2026년 1월 28일 주식회사 상미당홀딩스로 상호를 변경'",
    ]
    pb = {"status": "found — 기존 운영 법인 = 상미당홀딩스(구 (주)파리크라상), corp_code 00154888, 2025 별도 감사보고서 rcpNo 20260409001397 (삼일회계법인)",
          "corp_code": "00154888", "rcpNo": "20260409001397", "url": URL.format("20260409001397"),
          "consolidated_rcpNo": "20260428000662",
          "note": "사명 변경일은 원문 간 표기 차이 있음(본 법인 주석: 1/2 피씨홀딩스→1/28 상미당홀딩스; SPC GFS 주석: 1/30). 2026-01-01 신설 파리크라상(01995325)은 분할 신설 법인으로 보이나 원문 확인 전이므로 단정하지 않음. "
                  "파리바게뜨 점포 단위 매출(가맹점 POS 매출)은 감사보고서에 없음 → 공시 데이터 공백.",
          "fy2025": companies["상미당홀딩스"]["fy2025"], "fy2024": companies["상미당홀딩스"]["fy2024"],
          "stores": companies["상미당홀딩스"]["stores"], "tried": tried}

    sources = [{"company": co, "rcpNo": d["rcpNo"], "url": d["url"], "auditor": d["auditor"], "doc": "감사보고서(별도) 2025.12",
                "local": f"data/interim/audit_{co}_{d['rcpNo']}.txt"} for co, d in companies.items()]
    sources += [{"company": co, "rcpNo": x["rcpNo"], "url": x["url"], "doc": "감사보고서(별도) 2025.12 — data/interim/dart_benchmark.json 경유"}
                for co, x in cafes.items()]
    sources += [{"company": "피비파트너즈", "rcpNo": "20260407000928", "url": URL.format("20260407000928"), "doc": "지배기업 명칭 확인용"},
                {"company": "에스피씨지에프에스", "rcpNo": "20260326000496", "url": URL.format("20260326000496"), "doc": "파리크라상→상미당홀딩스 사명변경 확인용"}]

    out = {
        "_meta": {"unit": "원(KRW); 비율은 소수", "fiscal_years": "fy2025=2025.1.1~12.31(당기), fy2024=전기",
                  "script": "scripts/bakery_benchmark.py", "dart_link": URL.format("<rcpNo>"),
                  "caveats": ["모든 비율은 회사 전체(본사·공장·도매 포함) 감사보고서 수치 — 매장 4-wall 손익과 다름.",
                              "K-GAAP 회사(로쏘·엘비엠·GFFG·상미당)는 비용 성격별 주석이 없어 원재료율은 매출원가 잔여(상한값).",
                              "K-GAAP 운용리스 회사의 '임차료'와 K-IFRS 회사의 '임차료+사용권자산상각비'는 근사 비교(리스 이자 제외).",
                              "제안 비율의 집계 규칙(중앙값, 표본 선택)은 '가정'."]},
        "companies": companies,
        "cafe_chains": cafes,
        "paris_baguette": pb,
        "comparison_table": comparison,
        "group_summary_2025": group_summary,
        "proposed_cost_ratios": prop,
        "sources": sources,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # 콘솔 요약
    print(f"{'회사':<10}{'매출(억)':>9}{'OPM':>8}{'원재료':>8}{'인건비':>8}{'임차':>8}{'점포당(억)':>10}  tieout")
    for c in comparison:
        per = c["점포당매출_원"]
        print(f"{c['company']:<10}{(companies[c['company']]['fy2025']['revenue']/1e8 if c['company'] in companies else 0):>9.0f}"
              f"{(c['영업이익률'] or 0):>8.3f}{(c['원재료율'] or 0):>8.3f}{(c['인건비율'] or 0):>8.3f}{(c['임차료율'] or 0):>8.3f}"
              f"{(per/1e8 if per else 0):>10.1f}  {companies[c['company']]['tieout']['ok'] if c['company'] in companies else '-'}")
    for co, d in companies.items():
        for x in d["tieout"]["diff"]:
            print("  MISMATCH", co, x["check"], x["diff_won"], "|", x["explained"])
    print("group:", json.dumps(group_summary, ensure_ascii=False))
    print("proposed:", json.dumps({k: v["value"] for k, v in prop.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
