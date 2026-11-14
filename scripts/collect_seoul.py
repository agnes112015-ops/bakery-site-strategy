"""서울 열린데이터광장 상권분석 서비스 수집 → data/raw/*.json
대상 업종: 제과점, 커피-음료 (서비스 업종명 기준 필터)."""
import json
import os
import sys

from seoul_api import fetch_all

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
os.makedirs(OUT, exist_ok=True)

ID = ["STDR_YYQU_CD", "TRDAR_SE_CD_NM", "TRDAR_CD", "TRDAR_CD_NM"]
IND = ["SVC_INDUTY_CD", "SVC_INDUTY_CD_NM"]
TARGET = lambda r: any(k in (r.get("SVC_INDUTY_CD_NM") or "") for k in ("제과", "커피"))  # noqa: E731

SALES_Q = ["20232", "20242", "20252", "20253", "20254", "20261", "20262"]
STORE_Q = ["20232", "20242", "20252", "20262"]
FLPOP_Q = ["20232", "20242", "20252", "20262"]


def save(name, payload):
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print("saved", name, len(payload.get("rows", [])), "rows", flush=True)


def done(name):
    return os.path.exists(os.path.join(OUT, name + ".json"))


def job(name, service, params=None, keep=None, flt=None):
    if done(name):
        print("skip", name, flush=True)
        return
    total, rows = fetch_all(service, params, keep, flt)
    save(name, {"service": service, "params": params, "api_total": total, "rows": rows})


SALES_KEEP = ID + IND + [
    "THSMON_SELNG_AMT", "THSMON_SELNG_CO", "MDWK_SELNG_AMT", "WKEND_SELNG_AMT",
    "TMZON_06_11_SELNG_AMT", "TMZON_11_14_SELNG_AMT", "TMZON_14_17_SELNG_AMT", "TMZON_17_21_SELNG_AMT", "TMZON_21_24_SELNG_AMT",
    "ML_SELNG_AMT", "FML_SELNG_AMT",
    "AGRDE_10_SELNG_AMT", "AGRDE_20_SELNG_AMT", "AGRDE_30_SELNG_AMT", "AGRDE_40_SELNG_AMT", "AGRDE_50_SELNG_AMT", "AGRDE_60_ABOVE_SELNG_AMT"]

if __name__ == "__main__":
    job("trdar_area", "TbgisTrdarRelm")
    job("trdar_ix_20262", "VwsmTrdarIxQq", ["20262"])
    for q in FLPOP_Q:
        job(f"flpop_{q}", "VwsmTrdarFlpopQq", [q])
    for q in SALES_Q:
        job(f"sales_{q}", "VwsmTrdarSelngQq", [q], SALES_KEEP, TARGET)
    for q in STORE_Q:
        job(f"store_{q}", "VwsmTrdarStorQq", [q], None, TARGET)
    job("repop_all", "VwsmTrdarRepopQq", None,
        ID + ["TOT_REPOP_CO", "AGRDE_20_REPOP_CO", "AGRDE_30_REPOP_CO", "AGRDE_40_REPOP_CO", "TOT_HSHLD_CO", "APT_HSHLD_CO"])
    job("wrcpop_all", "VwsmTrdarWrcPopltnQq", None,
        ID + ["TOT_WRC_POPLTN_CO", "AGRDE_20_WRC_POPLTN_CO", "AGRDE_30_WRC_POPLTN_CO", "AGRDE_40_WRC_POPLTN_CO"])
    job("fclty_all", "VwsmTrdarFcltyQq", None,
        ID + ["VIATR_FCLTY_CO", "UNIV_CO", "SUBWAY_STATN_CO", "BUS_STTN_CO", "SUPMK_CO", "THEAT_CO", "GNRL_HSPTL_CO", "PBLOFC_CO", "BANK_CO"])
    print("ALL DONE", flush=True)
