# -*- coding: utf-8 -*-
"""상권 경쟁 분석 (베이커리 인허가 기반)

입력(읽기 전용):
  data/raw/license_bakery.json        서울시 제과점영업 인허가 LOCALDATA_072218 (영업 중)
  data/raw/license_cafe_bakery.json   서울시 휴게음식점 인허가 LOCALDATA_072405 (영업 중 & 베이커리성 상호/업태)
  data/raw/trdar_area.json            서울시 상권분석서비스 상권영역 TbgisTrdarRelm
  data/raw/sales_20262.json           서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq 20262
  data/raw/store_20262.json           서울시 상권분석서비스 점포 VwsmTrdarStorQq 20262
  data/interim/trdar_scores.csv       상권 점수(순위) - analyze.py 산출
  data/interim/location.json          후보 3곳
출력(신규):
  data/interim/competition.json

실행: PYTHONIOENCODING=utf-8 python scripts/competition.py
외부 라이브러리 없음(표준 라이브러리만).
"""
import csv
import json
import math
import os
import re
import statistics
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw")
INT = os.path.join(BASE, "data", "interim")
OUT = os.path.join(INT, "competition.json")

CUTOFF_3Y = "2023-11-14"      # 최근 3년 신규 진입 기준 (분석일 2026-11-14 기준 3년)
BUFFER_M = 500                # 배후권 반경
SALES_Q = "20262"
FINAL_CD = "3120175"

SRC_LIC_B = "서울 열린데이터광장 '서울시 제과점영업 인허가 정보'(LOCALDATA_072218), 영업 중 행만 수집"
SRC_LIC_C = "서울 열린데이터광장 '서울시 휴게음식점 인허가 정보'(LOCALDATA_072405), 영업 중 & 상호/업태에 베이커리·베이글·제과·빵 등 포함 행만 수집"
SRC_AREA = "서울 열린데이터광장 '서울시 상권분석서비스(영역-상권)'(TbgisTrdarRelm)"
SRC_SALES = f"서울 열린데이터광장 '서울시 상권분석서비스(추정매출-상권)'(VwsmTrdarSelngQq), 제과점(CS100005), {SALES_Q}"
SRC_STORE = f"서울 열린데이터광장 '서울시 상권분석서비스(점포-상권)'(VwsmTrdarStorQq), 제과점(CS100005), {SALES_Q}"


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["rows"]


def fnum(v):
    try:
        return float(str(v or "").replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------- 1. 업소 적재
def load_stores():
    out = []
    for fname, src in (("license_bakery", "제과점영업"), ("license_cafe_bakery", "휴게음식점")):
        for r in load_rows(os.path.join(RAW, fname + ".json")):
            x, y = fnum(r.get("X")), fnum(r.get("Y"))
            out.append({
                "name": (r.get("BPLCNM") or "").strip(),
                "date": r.get("APVPERMYMD") or "",
                "addr": (r.get("RDNWHLADDR") or r.get("SITEWHLADDR") or "").strip(),
                "jibun": (r.get("SITEWHLADDR") or "").strip(),
                "x": x, "y": y,
                "area": fnum(r.get("SITEAREA")),
                "license": src,
                "mgtno": r.get("MGTNO"),
            })
    # 두 인허가 목록 간 중복(같은 상호+같은 주소) 제거
    seen, dedup, dup = set(), [], 0
    for s in out:
        k = (re.sub(r"\W", "", s["name"]).upper(), re.sub(r"\s", "", s["addr"])[:30])
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        dedup.append(s)
    return dedup, len(out), dup


def gu_of(addr):
    m = re.search(r"서울특별시\s+(\S+구)", addr)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 2. 브랜드 사전
LEGAL = r"\(주\)|㈜|주식회사|유한회사|\(유\)|\(재\)"


def norm(name):
    n = re.sub(LEGAL, "", name)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", n).upper()


def first_token(name):
    t = re.split(r"[\s(\[]", re.sub(LEGAL, "", name).strip())[0]
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t).upper()


# 대형 프랜차이즈 - 표기 변형 포함(데이터에서 확인된 변형)
MAJOR = {
    "파리바게뜨": ["파리바게뜨", "파리바게트", "파리바겟뜨", "빠리바게뜨", "PARISBAGUETTE", "파리바게뜨"],
    "뚜레쥬르": ["뚜레쥬르", "뚜레주르", "TOUSLESJOURS"],
    "파리크라상(SPC)": ["파리크라상", "PARISCROISSANT"],
}
# 트렌드/프리미엄 - DART 감사보고서로 운영 실체가 확인된 브랜드(시드)
SEED_PREMIUM = {
    "런던베이글뮤지엄": {"pat": ["런던베이글", "LONDONBAGEL"],
                   "근거": "DART 감사보고서 (주)엘비엠 rcpNo 20260326000290"},
    "노티드": {"pat": ["노티드", "KNOTTED"],
            "근거": "DART 감사보고서 (주)지에프에프지 rcpNo 20260403003434"},
    "성심당": {"pat": ["성심당"],
            "근거": "DART 감사보고서 (주)로쏘 rcpNo 20260410000434 (본점 외 15개점)"},
    "아티제": {"pat": ["아티제", "ARTISEE", "보나비"],
            "근거": "DART 감사보고서 (주)보나비 rcpNo 20260403003616"},
}
# 간식빵(노점·테이크아웃 간식류) - 베이커리 경쟁 집계에서 제외
SNACK = re.compile(r"붕어빵|잉어빵|땅콩빵|계란빵|호두과자|국화빵|델리만쥬|와플|떡방|십원빵|대추빵")
# 브랜드 키가 될 수 없는 일반명사/장소/운영사 토큰(가정: 상호 첫 단어가 이것이면 브랜드로 보지 않음)
GENERIC = {"베이커리", "카페", "브레드", "블랑제리", "케이크", "케익", "베이크", "파티세리", "파티스리", "메종",
           "빵굽는", "빵이", "행복한", "스위트", "쉐프", "르빵", "베어", "BREAD", "그레인", "온더", "종로", "쌀빵",
           "오사카", "베이글카페", "특별한", "더현대서울", "이마트", "현대그린푸드", "코레일유통", "더", "THE",
           "빵", "제과점", "과자점", "프랑스", "서울", "뉴욕", "파리", "동네", "우리", "베이커리코너", "주식회사", "유한회사", "BAKERY", "CAFE"}
# 베이커리 본업이 아닌 다점포(도넛·아이스크림·커피·급식/유통 운영사) - 프리미엄 판정에서만 제외
NON_BAKERY_CORE = {"던킨", "던킨도너츠", "크리스피크림", "크리스피크림도넛", "배스킨라빈스", "팀홀튼", "브라이언스커피",
                   "엔제리너스", "빽다방", "마호가니", "코스트코홀세일베이커리", "신세계푸드", "현대그린푸드", "오설록",
                   "퀸즈베리도넛하우스", "올드페리도넛", "오도넛", "러셀도넛"}
MERGE_SUFFIX = ["제과점", "베이커리", "도너츠", "도넛", "카페", "과자점"]
# 대형마트·SSM 인스토어 입점(면적이 커도 프리미엄 포맷 아님) - 프리미엄 판정에서만 사용
MART = re.compile(r"홈플러스|이마트|롯데마트|코스트코|롯데슈퍼|GS더프레시|하나로마트")
PLACE_STEMS = set()           # main()에서 상권영역 자치구·행정동 이름으로 채움
MULTI_MIN = 3                 # 기타 다점포 기준: 상호 앞부분 동일 3개 이상
PREMIUM_AREA_X = 2.0          # 가정: 중앙 면적이 서울 베이커리 중앙값의 2배 이상 = 대형(프리미엄) 포맷


def match_major(nn):
    for b, pats in MAJOR.items():
        if any(p in nn for p in pats):
            return b
    return None


def match_seed(nn):
    for b, d in SEED_PREMIUM.items():
        if any(p in nn for p in d["pat"]):
            if b == "성심당" and "성심병원" in nn:
                continue
            return b
    return None


def build_dictionary(stores, seoul_med_area):
    # (a) 대형/시드 우선 부여
    rest = []
    for s in stores:
        nn = norm(s["name"])
        if SNACK.search(s["name"]):
            s["brand"], s["type"] = None, "간식빵(제외)"
            continue
        b = match_major(nn)
        if b:
            s["brand"], s["type"] = b, "대형 프랜차이즈"
            continue
        b = match_seed(nn)
        if b:
            s["brand"], s["type"] = b, "트렌드/프리미엄"
            continue
        rest.append(s)
    # (b) 상호 첫 단어(법인표기·기호 제거) 빈도로 다점포 브랜드 키 후보
    #     - 지명 토큰(자치구·행정동 이름에서 '구/동/숫자' 뗀 어간, 예: '연희')은 브랜드가 아니므로 제외
    #     - 첫 단어에 지점명이 붙은 경우(예: '아우어베이커리용산아이파크몰점')는 '...점'으로 끝날 때만 기존 키 접두 매칭
    #     - 업태 접미어만 다른 키는 병합(예: 나폴레옹제과점/나폴레옹베이커리→나폴레옹, 크리스피크림도넛→크리스피크림)
    tok = Counter(first_token(s["name"]) for s in rest)
    keys = {k for k, v in tok.items() if v >= 2 and len(k) >= 2 and k not in GENERIC and k not in PLACE_STEMS}
    canon = {}
    for k in keys:
        base = k
        for suf in MERGE_SUFFIX:
            if k.endswith(suf) and k[: -len(suf)] in keys:
                base = k[: -len(suf)]
                break
        canon[k] = base
    groups = defaultdict(list)
    for s in rest:
        ft = first_token(s["name"])
        if ft in keys:
            groups[canon[ft]].append(s)
        elif ft.endswith("점"):
            cand = [k for k in keys if ft.startswith(k) and len(k) >= 3]
            if cand:
                groups[canon[max(cand, key=len)]].append(s)
    brands = {}
    for k, v in groups.items():
        if len(v) < MULTI_MIN:
            continue
        areas = [s["area"] for s in v if s["area"]]
        med = statistics.median(areas) if areas else None
        new = sum(1 for s in v if s["date"] >= CUTOFF_3Y)
        mart = sum(1 for s in v if MART.search(s["addr"] + s["name"])) / len(v)
        premium = (med is not None and med >= PREMIUM_AREA_X * seoul_med_area and new >= 1
                   and k not in NON_BAKERY_CORE and mart < 0.5)
        brands[k] = {"stores": v, "n": len(v), "median_area": med, "new3y": new, "premium": premium,
                     "mart_share": mart}
    for k, d in brands.items():
        t = "트렌드/프리미엄" if d["premium"] else "기타 다점포"
        for s in d["stores"]:
            s["brand"], s["type"] = k, t
    for s in rest:
        if "type" not in s:
            s["brand"], s["type"] = None, "개인/독립"

    def stats(lst):
        areas = [s["area"] for s in lst if s["area"]]
        return {"서울_업소수": len(lst),
                "최근3년_신규": sum(1 for s in lst if s["date"] >= CUTOFF_3Y),
                "중앙면적_m2": round(statistics.median(areas), 1) if areas else None,
                "예시상호": [s["name"] for s in lst[:3]]}

    dic = {"대형 프랜차이즈": {}, "트렌드/프리미엄": {}, "기타 다점포": {}}
    by_brand = defaultdict(list)
    for s in stores:
        if s.get("brand"):
            by_brand[s["brand"]].append(s)
    for b, pats in MAJOR.items():
        dic["대형 프랜차이즈"][b] = {"표기변형_패턴": pats, **stats(by_brand.get(b, []))}
    for b, d in SEED_PREMIUM.items():
        dic["트렌드/프리미엄"][b] = {"표기변형_패턴": d["pat"], "편입근거": d["근거"], **stats(by_brand.get(b, []))}
    for k, d in sorted(brands.items(), key=lambda kv: -kv[1]["n"]):
        if d["premium"]:
            dic["트렌드/프리미엄"][k] = {
                "표기변형_패턴": [k + "*(상호 앞부분)"],
                "편입근거": (f"서울 인허가 {d['n']}곳(다점포), 중앙면적 {d['median_area']:.0f}㎡ ≥ 서울 중앙값×{PREMIUM_AREA_X:g}"
                         f"({PREMIUM_AREA_X * seoul_med_area:.0f}㎡), 최근 3년 신규 {d['new3y']}곳, 대형마트 입점비중 {d['mart_share']:.0%}"),
                **stats(d["stores"])}
        else:
            dic["기타 다점포"][k] = {**stats(d["stores"]), "대형마트_입점비중": round(d["mart_share"], 2)}
    return dic


# ---------------------------------------------------------------- 3. 거리
def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


TYPES = ["대형 프랜차이즈", "트렌드/프리미엄", "기타 다점포", "개인/독립"]


def count_types(lst):
    c = Counter(s["type"] for s in lst)
    d = {t: c.get(t, 0) for t in TYPES}
    d["합계"] = sum(d.values())
    return d


def main():
    stores, n_raw, n_dup = load_stores()
    areas_all = [s["area"] for s in stores if s["area"] and s["area"] > 0 and not SNACK.search(s["name"])]
    seoul_med_area = statistics.median(areas_all)
    trdar = {r["TRDAR_CD"]: r for r in load_rows(os.path.join(RAW, "trdar_area.json"))}
    for r in trdar.values():
        for nm in (r["SIGNGU_CD_NM"], r["ADSTRD_CD_NM"]):
            stem = re.sub(r"[0-9·.]*(구|동|가|로)$", "", re.sub(r"\d+가?동$|동$", "", nm))
            if len(stem) >= 2:
                PLACE_STEMS.add(stem.upper())
                PLACE_STEMS.add((stem + "동").upper())
    dic = build_dictionary(stores, seoul_med_area)
    geo = [s for s in stores if s["x"] and s["y"]]
    comp = [s for s in geo if s["type"] != "간식빵(제외)"]

    for r in trdar.values():
        r["_c"] = (float(r["XCNTS_VALUE"]), float(r["YDNTS_VALUE"]))
        r["_r"] = math.sqrt(float(r["RELM_AR"]) / math.pi)

    # ---------- 좌표계 검증
    # (a) 모든 업소의 최근접 상권 중심의 자치구 == 업소 주소 자치구 비율
    centers = list(trdar.values())
    match = tot = 0
    nn_d = []
    for s in geo:
        g = gu_of(s["addr"]) or gu_of(s["jibun"])
        if not g:
            continue
        best = min(centers, key=lambda r: dist(r["_c"], (s["x"], s["y"])))
        nn_d.append(dist(best["_c"], (s["x"], s["y"])))
        tot += 1
        match += best["SIGNGU_CD_NM"] == g
    # (b) 주소 키워드로 특정 상권 근처 업소 거리 확인
    probes = [
        ("3120175", r"서초동", r"남부순환로|서초중앙로|반포대로|효령로"),
        ("3120093", r"연희동", r"연희로|연희맛로|증가로|성산로"),
        ("3120037", r"광희동|을지로6가|을지로7가|신당동", r"을지로|장충단로|퇴계로|마장로"),
        ("3120023", r"명동|태평로|북창동|소공동|무교동|다동", r"세종대로|을지로|소공로|무교로|남대문로"),
        ("3120052", r"성수동", r"아차산로|연무장|성수이로|성수일로"),
    ]
    probe_out = []
    for cd, dong, road in probes:
        t = trdar[cd]
        ds = sorted(dist(t["_c"], (s["x"], s["y"])) for s in geo
                    if re.search(dong, s["addr"] + s["jibun"]) and re.search(road, s["addr"]))
        probe_out.append({"상권": t["TRDAR_CD_NM"], "TRDAR_CD": cd, "주소조건": f"{dong} & {road}",
                          "업소수": len(ds),
                          "중심거리_중앙값_m": round(statistics.median(ds)) if ds else None,
                          "1km이내_비율": round(sum(d <= 1000 for d in ds) / len(ds), 3) if ds else None,
                          "최소_최대_m": [round(ds[0]), round(ds[-1])] if ds else None})
    coord_check = {
        "결론": None,
        "인허가_좌표_예시": [geo[0]["x"], geo[0]["y"]],
        "상권중심_좌표_예시": list(trdar[FINAL_CD]["_c"]),
        "최근접상권_자치구일치율": round(match / tot, 4),
        "최근접상권_거리_중앙값_m": round(statistics.median(nn_d)),
        "검사업소수": tot,
        "주소기반_교차확인": probe_out,
        "좌표없는업소": len(stores) - len(geo),
    }
    ok = coord_check["최근접상권_자치구일치율"] >= 0.9 and all(
        p["중심거리_중앙값_m"] is not None and p["중심거리_중앙값_m"] < 1000 for p in probe_out)
    coord_check["결론"] = (
        "동일 좌표계(중부원점 TM 계열, m 단위)로 판단 - 변환 없이 유클리드 거리 사용. 근거: 최근접 상권 자치구 일치율과 "
        "주소 키워드 업소의 상권 중심 거리 중앙값이 1km 미만" if ok else
        "좌표계 불일치 의심 - 주소 기반 매칭 필요")

    # ---------- 매출·점포 (상권분석서비스)
    sales = {r["TRDAR_CD"]: float(r["THSMON_SELNG_AMT"] or 0)
             for r in load_rows(os.path.join(RAW, f"sales_{SALES_Q}.json")) if r["SVC_INDUTY_CD"] == "CS100005"}
    storq = {r["TRDAR_CD"]: r for r in load_rows(os.path.join(RAW, f"store_{SALES_Q}.json"))
             if r["SVC_INDUTY_CD"] == "CS100005"}

    # ---------- 서울 기준 밀도: 전 1,650개 상권의 등가원 내 업소 밀도(개/㎢)
    dens_all, dens500_all = [], []
    for t in centers:
        c = t["_c"]
        n_in = n5 = 0
        for s in comp:
            d = dist(c, (s["x"], s["y"]))
            if d <= t["_r"]:
                n_in += 1
            if d <= BUFFER_M:
                n5 += 1
        dens_all.append(n_in / (float(t["RELM_AR"]) / 1e6))
        dens500_all.append(n5)
    seoul_dens_med = statistics.median(dens_all)
    dens_sorted = sorted(dens_all)
    five_sorted = sorted(dens500_all)

    def pctl(sorted_vals, v):
        return round(sum(1 for x in sorted_vals if x <= v) / len(sorted_vals), 3)
    seoul_dens_mean = statistics.mean(dens_all)
    seoul_500_med = statistics.median(dens500_all)
    seoul_500_mean = statistics.mean(dens500_all)
    tot_sales = sum(sales.values())
    tot_storq = sum(float(r["STOR_CO"] or 0) for r in storq.values())

    # ---------- 대상: 후보 3곳 + 점수 상위 30
    with open(os.path.join(INT, "location.json"), encoding="utf-8") as f:
        cand_cds = [c["TRDAR_CD"] for c in json.load(f)["candidates"]]
    with open(os.path.join(INT, "trdar_scores.csv"), encoding="utf-8-sig") as f:
        sc = list(csv.DictReader(f))
    rank = {r["TRDAR_CD"]: int(r["순위"]) for r in sc}
    top30 = [r["TRDAR_CD"] for r in sorted(sc, key=lambda r: int(r["순위"]))[:30]]

    def profile(cd, full):
        t = trdar[cd]
        c, rad = t["_c"], t["_r"]
        withd = sorted(((dist(c, (s["x"], s["y"])), s) for s in comp), key=lambda z: z[0])
        in_r = [s for d, s in withd if d <= rad]
        in_5 = [s for d, s in withd if d <= BUFFER_M]
        areas = [s["area"] for s in in_r if s["area"]]
        areas5 = [s["area"] for s in in_5 if s["area"]]
        sale = sales.get(cd)
        sq = storq.get(cd, {})
        circle_km2 = float(t["RELM_AR"]) / 1e6
        dens = len(in_r) / circle_km2
        p = {
            "상권명": t["TRDAR_CD_NM"], "TRDAR_CD": cd, "자치구": t["SIGNGU_CD_NM"], "행정동": t["ADSTRD_CD_NM"],
            "점수순위": rank.get(cd), "radius_m": round(rad),
            "counts_in_trdar": count_types(in_r),
            "counts_500m": count_types(in_5),
            "new_entries_3y": {"반경내": sum(s["date"] >= CUTOFF_3Y for s in in_r),
                               "500m": sum(s["date"] >= CUTOFF_3Y for s in in_5),
                               "500m_유형별": count_types([s for s in in_5 if s["date"] >= CUTOFF_3Y])},
            "평균면적_m2": {"반경내": round(statistics.mean(areas), 1) if areas else None,
                        "500m": round(statistics.mean(areas5), 1) if areas5 else None},
            "베이커리매출_분기_원": sale,
            "베이커리1곳당_분기매출_원": round(sale / len(in_r)) if sale and in_r else None,
            "상권분석서비스_제과점_점포수": fnum(sq.get("STOR_CO")),
            "상권분석서비스_제과점_프랜차이즈점포수": fnum(sq.get("FRC_STOR_CO")),
            "상권분석서비스_점포당_분기매출_원": round(sale / fnum(sq.get("STOR_CO"))) if sale and fnum(sq.get("STOR_CO")) else None,
            "밀도_개per㎢": round(dens, 1),
            "밀도_서울평균대비_배": round(dens / seoul_dens_mean, 2),
            "밀도_서울1650상권_백분위": pctl(dens_sorted, dens),
            "500m업소수_서울평균대비_배": round(len(in_5) / seoul_500_mean, 2),
            "500m업소수_서울1650상권_백분위": pctl(five_sorted, len(in_5)),
            "베이커리1곳당_분기매출_500m기준_원": round(sale / len(in_5)) if sale and in_5 else None,
            "상권분석서비스_제과점_유사업종점포수": fnum(sq.get("SIMILR_INDUTY_STOR_CO")),
            "브랜드별_500m": dict(Counter(s["brand"] for s in in_5 if s["type"] in ("대형 프랜차이즈", "트렌드/프리미엄")).most_common()),
        }
        if full:
            p["stores_list"] = [{"상호": s["name"], "유형": s["type"], "브랜드": s["brand"], "인허가일": s["date"],
                                 "거리m": round(d), "반경내": d <= rad, "면적m2": s["area"], "주소": s["addr"],
                                 "인허가구분": s["license"]}
                                for d, s in withd if d <= BUFFER_M][:30]
            p["프리미엄_최근접"] = [{"상호": s["name"], "브랜드": s["brand"], "거리m": round(d), "주소": s["addr"]}
                               for d, s in withd if s["type"] == "트렌드/프리미엄"][:5]
            p["DART브랜드_최근접"] = [{"상호": s["name"], "브랜드": s["brand"], "거리m": round(d), "주소": s["addr"]}
                                 for d, s in withd if s["brand"] in SEED_PREMIUM][:5]
        return p

    candidates = [profile(cd, True) for cd in cand_cds]
    top30_summary = []
    for cd in top30:
        p = profile(cd, False)
        top30_summary.append(p)
    # 상위 30 내 상대 순위
    def pct_rank(vals, v):
        return round(sum(x <= v for x in vals) / len(vals), 2)
    pb_vals = [p["베이커리1곳당_분기매출_원"] or 0 for p in top30_summary]
    for p in candidates:
        p["상위30내_1곳당매출_백분위"] = pct_rank(pb_vals, p["베이커리1곳당_분기매출_원"] or 0)

    # 서울 전체 집계
    type_cnt = count_types(comp)
    seoul_totals = {
        "인허가_원자료행": n_raw, "중복제거": n_dup, "업소수(중복제거)": len(stores),
        "간식빵_제외": sum(1 for s in stores if s["type"] == "간식빵(제외)"),
        "경쟁집계대상_좌표보유": len(comp),
        "유형별": type_cnt,
        "유형별_비중": {k: round(v / type_cnt["합계"], 3) for k, v in type_cnt.items() if k != "합계"},
        "최근3년_신규": sum(s["date"] >= CUTOFF_3Y for s in comp),
        "면적_중앙값_m2": round(seoul_med_area, 1),
        "상권등가원_밀도_중앙값_개per㎢": round(seoul_dens_med, 1),
        "상권등가원_밀도_평균_개per㎢": round(seoul_dens_mean, 1),
        "상권중심500m_업소수_중앙값": seoul_500_med,
        "상권중심500m_업소수_평균": round(seoul_500_mean, 1),
        f"제과점_추정매출_합계_{SALES_Q}_원": tot_sales,
        f"제과점_점포수_합계_{SALES_Q}": tot_storq,
        "제과점_점포당_분기매출_원(상권분석서비스)": round(tot_sales / tot_storq) if tot_storq else None,
        "주석": "상권 합계는 관광특구와 발달상권 영역 중복으로 이중계상 가능. 밀도 기준값은 1,650개 상권의 등가원 기준.",
    }

    # ---------- 시사점(결론 우선)
    f = candidates[0]
    c500, cin = f["counts_500m"], f["counts_in_trdar"]
    br = f["브랜드별_500m"]
    prem_dart = f["DART브랜드_최근접"]
    others = candidates[1:]
    seoul_ps = seoul_totals["제과점_점포당_분기매출_원(상권분석서비스)"]
    pn = next((x for x in f["stores_list"] if x["유형"] == "트렌드/프리미엄"), None)

    def mb(v):
        return f"{(v or 0) / 1e6:,.1f}백만원"

    implications = [
        (f"[결론] 남부터미널역은 '프리미엄 공백이 대부분 남아 있으나 첫 경쟁자가 막 들어온' 상권. 500m 내 베이커리 {c500['합계']}곳 = "
         f"파리바게뜨 {br.get('파리바게뜨', 0)}·뚜레쥬르 {br.get('뚜레쥬르', 0)}·파리크라상 {br.get('파리크라상(SPC)', 0)}, "
         f"트렌드/프리미엄 {c500['트렌드/프리미엄']}"
         + (f"({pn['상호']}, {pn['거리m']}m, {pn['면적m2']:.0f}㎡, 인허가 {pn['인허가일']})" if pn else "")
         + f", 기타 다점포 {c500['기타 다점포']}, 개인/독립 {c500['개인/독립']}. DART로 확인되는 트렌드 브랜드(런던베이글뮤지엄·노티드·성심당·아티제) 최근접 매장은 "
         + (", ".join(f"{p['상호']} {p['거리m']}m" for p in prem_dart[:2]) if prem_dart else "없음")
         + " → 1km 안에 트렌드 브랜드 없음. 대형 프리미엄 포맷(100㎡+)으로 들어가면 직접 경쟁은 1곳."),
        (f"[수요 대비 공급] 상권 제과점 분기매출 {mb(f['베이커리매출_분기_원'])}({SALES_Q}) / 상권분석서비스 공식 점포수 {f['상권분석서비스_제과점_점포수']:.0f}곳 = "
         f"점포당 {mb(f['상권분석서비스_점포당_분기매출_원'])}, 서울 평균 {mb(seoul_ps)}의 {(f['상권분석서비스_점포당_분기매출_원'] or 0) / seoul_ps:.1f}배. "
         f"인허가 기준 분모로 바꾸면 반경 {f['radius_m']}m 내 {cin['합계']}곳 → {mb(f['베이커리1곳당_분기매출_원'])}, 500m 내 {c500['합계']}곳 → "
         f"{mb(f['베이커리1곳당_분기매출_500m기준_원'])}. 500m 업소수는 서울 평균의 {f['500m업소수_서울평균대비_배']}배(백분위 {f['500m업소수_서울1650상권_백분위']}) "
         f"→ 공급은 평균 수준인데 매출이 커 1곳당 몫이 큰 '고매출·보통밀도' 상권. 분모 선택에 따라 값이 2~4배 달라지므로 손익에는 범위로 써야 함."),
        (f"[진입 동학] 최근 3년(인허가일 ≥ {CUTOFF_3Y}) 500m 내 신규 {f['new_entries_3y']['500m']}곳 "
         f"(대형 {f['new_entries_3y']['500m_유형별']['대형 프랜차이즈']}, 프리미엄 {f['new_entries_3y']['500m_유형별']['트렌드/프리미엄']}, "
         f"개인 {f['new_entries_3y']['500m_유형별']['개인/독립']}) - 대형 프랜차이즈의 신규 출점은 없고 진입은 개인·프리미엄 위주."),
    ]
    for o in others:
        ob = o["브랜드별_500m"]
        implications.append(
            f"[후보 비교] {o['상권명']}: 500m 내 {o['counts_500m']['합계']}곳(대형 {o['counts_500m']['대형 프랜차이즈']}, "
            f"프리미엄 {o['counts_500m']['트렌드/프리미엄']}, 기타 다점포 {o['counts_500m']['기타 다점포']}, 개인 {o['counts_500m']['개인/독립']}; "
            f"서울 백분위 {o['500m업소수_서울1650상권_백분위']}), 공식 점포당 분기매출 {mb(o['상권분석서비스_점포당_분기매출_원'])}, "
            f"3년 신규 {o['new_entries_3y']['500m']}곳, 대형·프리미엄 브랜드 {ob if ob else '없음'} → 남부터미널보다 밀도 높고 1곳당 매출 낮음.")
    implications.append(
        f"[손익 보정 시사] 남부터미널 500m 내 업소의 {c500['개인/독립'] / c500['합계']:.0%}가 개인/독립이고 평균 면적 {f['평균면적_m2']['500m']}㎡. "
        f"상권 '점포당 평균 매출'은 소형 개인 빵집이 섞인 값이라 100㎡+ 브랜드 직영점 매출의 하한으로만 쓰고, 기준 매출은 DART 감사보고서의 매장당 매출(엘비엠·지에프에프지·보나비 등)로 재보정 필요.")

    sources = [
        {"구분": "서울 열린데이터광장", "서비스": SRC_LIC_B, "기준일": "수집 시점 영업 중(분석일 2026-11-14)"},
        {"구분": "서울 열린데이터광장", "서비스": SRC_LIC_C, "기준일": "수집 시점 영업 중(분석일 2026-11-14)"},
        {"구분": "서울 열린데이터광장", "서비스": SRC_AREA, "용도": "상권 중심좌표·면적(등가원 반경)"},
        {"구분": "서울 열린데이터광장", "서비스": SRC_SALES, "용도": "베이커리 1곳당 분기매출 분자"},
        {"구분": "서울 열린데이터광장", "서비스": SRC_STORE, "용도": "공식 점포수 교차확인"},
        {"구분": "DART", "서비스": "(주)엘비엠 감사보고서", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260326000290"},
        {"구분": "DART", "서비스": "(주)지에프에프지 감사보고서", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260403003434"},
        {"구분": "DART", "서비스": "(주)로쏘 감사보고서", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260410000434"},
        {"구분": "DART", "서비스": "(주)보나비 감사보고서", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260403003616"},
        {"구분": "내부산출", "서비스": "data/interim/trdar_scores.csv(순위), data/interim/location.json(후보)"},
    ]
    method = {
        "요약": "인허가 업소 좌표를 상권 중심(TbgisTrdarRelm)과 같은 TM 좌표계로 확인한 뒤, 상권 면적의 등가원 반경 r=sqrt(면적/π)와 "
              "중심 500m 배후권 안 업소를 유형별로 집계.",
        "업소모집단": "제과점영업 인허가(영업 중) + 휴게음식점 인허가 중 베이커리성 상호(영업 중). 상호+도로명주소 앞 30자 동일 시 중복 제거. "
                 "붕어빵·땅콩빵·계란빵·호두과자·와플 등 간식빵은 경쟁 집계에서 제외.",
        "유형분류": {
            "대형 프랜차이즈": "파리바게뜨·뚜레쥬르(표기 변형 패턴) + SPC 파리크라상",
            "트렌드/프리미엄": "(1) DART 감사보고서로 운영 실체가 확인된 런던베이글뮤지엄·노티드·성심당·아티제, "
                          f"(2) 데이터 규칙: 상호 앞부분 동일 {MULTI_MIN}곳 이상 & 중앙 면적 ≥ 서울 베이커리 중앙값×{PREMIUM_AREA_X:g} "
                          "& 최근 3년 신규 1곳 이상 & 베이커리 본업(도넛·커피·아이스크림·급식/유통 운영사 제외). 규칙의 임계값은 '가정'.",
            "기타 다점포": f"상호 첫 단어(법인표기 제거)가 같은 업소 {MULTI_MIN}곳 이상(일반명사 토큰 제외), 위 두 유형 아님",
            "개인/독립": "그 외",
        },
        "최근3년신규": f"인허가일(APVPERMYMD) ≥ {CUTOFF_3Y}. 인허가일은 명의변경·재인허가 시 갱신될 수 있어 실제 개점일보다 늦을 수 있음(한계).",
        "1곳당매출": f"상권 제과점 추정매출({SALES_Q}) / 등가원 반경 내 인허가 업소 수. 추정매출은 상권 폴리곤 기준, 업소 수는 등가원 기준이라 경계 불일치 있음(근사).",
        "밀도": "등가원 내 업소수/상권면적(㎢)을 1,650개 상권 전체 분포의 중앙값과 비교. 500m 업소수도 동일하게 비교.",
        "가정": [f"프리미엄 포맷 임계값 = 서울 중앙 면적×{PREMIUM_AREA_X:g}",
                 "상권 경계는 폴리곤이 없어 등가원으로 근사",
                 "일반명사 토큰 목록(GENERIC)과 비베이커리 본업 목록(NON_BAKERY_CORE)은 분석자 지정"],
        "스크립트": "scripts/competition.py",
    }
    out = {"method": method, "coord_check": coord_check, "brand_dictionary": dic, "candidates": candidates,
           "top30_summary": top30_summary, "seoul_totals": seoul_totals, "implications": implications,
           "sources": sources}
    with open(OUT, "w", encoding="utf-8") as fo:
        json.dump(out, fo, ensure_ascii=False, indent=1)
    print(json.dumps(coord_check, ensure_ascii=False, indent=1))
    print("\n".join(implications))


if __name__ == "__main__":
    main()
