"""Build video/presentation.mp4 (7 visual slides, Korean narration) from data/interim JSON.

All slide/chart/narration numbers are read from JSON at build time:
  location.json (+ location_v2.json if present), competition.json, interior.json, menu.json,
  pnl_v2.json if present else pnl.json, rent_gate.json (recomputed from the active P&L when its rows
  belong to a different P&L version, using rent_gate's own formula).
Pipeline: video/script.json -> slide HTML (Chart.js 4.4.1 + inline SVG) -> PNG (headless Edge/Chrome)
-> WAV (System.Speech 'Microsoft Heami Desktop') -> ffmpeg segments (audio + 0.6s) -> concat + captions.vtt
-> copy to site/assets/.
Run: PYTHONIOENCODING=utf-8 python scripts/make_video.py
"""
import html, json, os, re, shutil, subprocess, time, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "interim"
VID = ROOT / "video"
SLIDES, AUDIO, SEG = VID / "slides", VID / "audio", VID / "segments"
ASSETS = ROOT / "site" / "assets"
PAD, RATE = 0.6, 2
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"]
CHARTJS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
PURPLE, VIOLET = "#4C1D95", "#7C3AED"


def load(name):
    p = D / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- number helpers
def eok(w, nd=1):            # won -> 억 numeric string
    return f"{w / 1e8:.{nd}f}"


def won_kr(w):               # spoken: 8억 4천4백만
    m = round(w / 1e6); e, r = divmod(m, 100)
    s = f"{e}억" if e else ""
    if r:
        th, hu = divmod(r, 10)
        s += (" " if s else "") + (f"{th}천" if th else "") + (f"{hu}백" if hu else "") + "만"
    return s


def man(w):                  # won -> '874만'
    return f"{round(w / 1e4):,}만"


def pct(x, nd=1):
    return f"{x * 100:.{nd}f}"


def short(name):
    return re.split(r"[(（]", name)[0].strip()


# ---------------------------------------------------------------- data model
def gather():
    L1, L2, C = load("location.json"), load("location_v2.json"), load("competition.json")
    I, M, R = load("interior.json"), load("menu.json"), load("rent_gate.json")
    P = load("pnl_v2.json"); pnl_name = "pnl_v2.json"
    if P is None:
        P, pnl_name = load("pnl.json"), "pnl.json"
    g = {"pnl_name": pnl_name, "loc_v2": L2 is not None}
    c0 = L1["candidates"][0]; m = c0["지표"]["매출"]; pop = c0["지표"]["인구"]; st = c0["지표"]["점포"]
    fp = L1["final_profile"]
    g.update(site=c0["상권명"], gu=c0["자치구"], yoy=m["합산_2분기YoY_3구간_%(23→24,24→25,25→26)"],
             per_store_chg=st["베이커리_점포당매출_3년변화율_%"], flpop=pop["유동인구_증감률_%"],
             flpop_med=pop["유동인구_증감률_서울176상권중앙값_%"],
             q7=m["합산매출_7분기_억원"], bq7=m["베이커리매출_7분기_억원"],
             stores={q: v["베이커리"]["유사업종점포"] for q, v in fp["점포_표본4분기"].items()})
    # candidates: prefer location_v2 (corrected), else location.json + competition.json
    cands = []
    if L2:
        for c in L2["candidates"]:
            cands.append({"name": c["상권명"], "bakery_yr": c["제과점_연매출_최근4분기_원"],
                          "per_store_q": c["점포당_분기매출_정정_원(SIMILR)"], "types": c["인허가_500m_유형별"]})
        g["n_criteria"] = len(L2["scorecard_기준"])
        gate_txt = " ".join(L2["verdict"]["조건(출점 게이트)"])
        mm = re.search(r"(\d+)억원 이상", gate_txt)
        g["q3_gate_eok"] = mm.group(1) if mm else None
    else:
        comp = {c["상권명"]: c for c in C["candidates"]}
        for c in L1["candidates"]:
            cands.append({"name": c["상권명"], "bakery_yr": c["지표"]["매출"]["베이커리매출_최신_억원"] * 4e8,
                          "per_store_q": c["지표"]["점포"]["베이커리_점포당분기매출_억원"] * 1e8,
                          "types": comp[c["상권명"]]["counts_500m"]})
        g["n_criteria"], g["q3_gate_eok"] = None, None
    g["cands"] = cands
    jam = next(p for p in L1["패널_판정"] if "잠실" in p["상권"])
    g["jamsil"] = re.search(r"연율 (-?\d+\.?\d*)%", jam["근거"]).group(1)
    g["comp_src"] = "location_v2.json(정정)" if L2 else "competition.json"
    # interior
    g.update(concept=I["concept"], zones=I["zones"], palette=I["palette"],
             materials=[short(x["material"]) for x in I["materials"]],
             area_interior=I["meta"]["계산값"]["총면적_가정_m2"])
    area_p = next((a["value"] for a in P["assumptions"] if a["name"].startswith("매장 면적")), None)
    g["area"] = area_p or g["area_interior"]
    # menu
    g.update(mix=M["mix"], food=M["mix_요약"]["푸드계(베이커리+디저트+델리)_%"], drink=M["mix_요약"]["음료계_%"],
             ticket=M["avg_ticket"], cogs=M["target_cogs_ratio"]["운영목표_%"], items=M["items"])
    # P&L
    sc = P["scenarios"]; be = P["breakeven"]
    g["scen"] = {k: {"rev": v["연도별"]["Y1"]["매출"], "opm": v["연도별"]["Y1"]["영업이익률"],
                     "op": v["연도별"]["Y1"]["영업이익"]} for k, v in sc.items()}
    g["be_yr"], g["be_mo"] = be["손익분기_연매출_원"], be["손익분기_월매출_원"]
    b1 = sc["기준"]["연도별"]["Y1"]
    rent_rows = [r for r in R["rows"] if r["시나리오"] == "기준" and r["연도"] == "Y1"] if R else []
    if rent_rows and abs(rent_rows[0]["매출"] - b1["매출"]) / b1["매출"] < 0.01:
        g["rent_ceiling"], g["rent_model"], g["rent_src"] = (rent_rows[0]["손익분기_월임대료상한"],
                                                            rent_rows[0]["모델_월임차료"], "rent_gate.json")
    else:   # rent_gate.json formula applied to the active P&L
        g["rent_ceiling"] = (b1["임차료"] + b1["영업이익"]) / 12
        g["rent_model"] = b1["임차료"] / 12
        g["rent_src"] = f"rent_gate.json 산식 × {pnl_name}"
    return g


# ---------------------------------------------------------------- narration
def build_script(g):
    y = g["yoy"]; q = sorted(g["stores"]); s0, s1 = g["stores"][q[0]], g["stores"][q[-1]]
    bq = g["bq7"]; c = {x["name"]: x for x in g["cands"]}
    site, yeon = c[g["site"]], next(x for x in g["cands"] if x["name"] == "연희동")
    ratio = round(site["bakery_yr"] / yeon["bakery_yr"])
    t = site["types"]; prem = t["트렌드/프리미엄"]; tot = t["합계"]
    sb, sp, so = g["scen"]["기준"], g["scen"]["보수"], g["scen"]["낙관"]
    tk = g["ticket"]; tq = sorted(tk["추이_상권"])
    ceil, model = g["rent_ceiling"], g["rent_model"]
    rent_line = (f"모델 임차료 {man(model)} 원보다 낮아 임대료 협상이 필수입니다." if ceil < model
                 else f"모델 임차료 {man(model)} 원 대비 여유는 {man(ceil - model)} 원뿐입니다.")
    crit = f"{g['n_criteria']}개 기준 비교에서" if g["n_criteria"] else "종합 비교에서"
    gate3 = f"제과점 분기매출 {g['q3_gate_eok']}억 원 유지 확인" if g["q3_gate_eok"] else "3분기 데이터 재검증"
    big_zones = sorted(g["zones"], key=lambda z: -z["area_ratio_pct"])
    S = [
        dict(slide=1, title=f"결론: 1호점은 {g['gu']} {g['site']}",
             narration=f"결론부터 말씀드립니다. 1호점은 {g['gu']} {g['site']}입니다. 빵 수요가 공급보다 빠르게 늘고 있기 때문입니다. "
                       f"매출 증가율은 {y[-1]}%까지 가속했고, 베이커리 점포당 매출은 3년간 {round(g['per_store_chg'])}%, 유동인구는 {round(g['flpop'])}% 늘었습니다."),
        dict(slide=2, title="왜 3년 뒤 성장 상권인가",
             narration=f"같은 2분기 기준 매출 증가율이 {y[0]}%, {y[1]}%, {y[2]}%로 3년 연속 빨라졌습니다. "
                       f"베이커리 점포는 {s0:.0f}곳에서 {s1:.0f}곳으로 줄었는데, 매출은 {bq[q[0]]}억에서 {bq[q[-1]]}억 원으로 늘었습니다."),
        dict(slide=3, title="후보 3곳 비교와 잠실 제외",
             narration=f"후보 세 곳 {crit} {g['site']}이 1위입니다. 제과점 연매출 약 {round(site['bakery_yr'] / 1e8)}억 원으로 연희동의 {ratio}배입니다. "
                       f"잠실은 데이터 단절 뒤 매출이 줄어 제외했고, 반경 500미터 베이커리 {tot}곳 중 프리미엄은 {prem}곳뿐입니다."),
        dict(slide=4, title=f"인테리어 컨셉: {short(g['concept'])}",
             narration=f"컨셉은 {short(g['concept'])}. 출근길엔 3분 그랩앤고, 퇴근길엔 갓 구운 빵입니다. "
                       f"{short(big_zones[0]['zone'])}과 {short(big_zones[1]['zone'])}을 각각 {big_zones[0]['area_ratio_pct']}%로 가장 크게 두고, "
                       f"면적은 손익 가정에 맞춰 {g['area']:.0f}제곱미터로 잡습니다."),
        dict(slide=5, title="메뉴 구성: 베이커리 주도형",
             narration=f"메뉴는 푸드 {g['food']}, 음료 {g['drink']}의 베이커리 주도형입니다. "
                       f"상권 빵 객단가는 3년간 {tk['추이_상권'][tq[0]]['제과점']:,}원에서 {tk['추이_상권'][tq[-1]]['제과점']:,}원으로 올랐고, "
                       f"목표 객단가는 {tk['제안']:,}원, 원가율은 {g['cogs']}%로 잡았습니다."),
        dict(slide=6, title="손익 시뮬레이션과 임대료 게이트",
             narration=f"손익은 모두 가정입니다. 기준 시나리오 첫해 매출 {won_kr(sb['rev'])} 원은 "
                       f"손익분기 {won_kr(g['be_yr'])} 원을 {'겨우 넘고' if sb['rev'] >= g['be_yr'] else '밑돌고'}, 영업이익률은 {pct(sb['opm'])}%입니다. "
                       f"그래서 월 임대료 상한 {man(ceil)} 원이 출점 게이트입니다. {rent_line}"),
        dict(slide=7, title="데이터 출처와 다음 단계",
             narration=f"수치는 모두 서울 열린데이터광장과 DART 감사보고서에서 가져왔습니다. 다음 단계는 세 가지입니다. "
                       f"월 {man(ceil)} 원 이하 매물 확보, {g['area']:.0f}제곱미터 기준 인테리어 견적, 그리고 {gate3} 후 출점 결정입니다."),
    ]
    return S


# ---------------------------------------------------------------- slide HTML
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1920px;height:1080px;overflow:hidden}
body{font-family:'Pretendard','Malgun Gothic',sans-serif;background:#F5F3FF;color:#1F1235;position:relative}
.bar{position:absolute;left:0;top:0;width:1920px;height:16px;background:linear-gradient(90deg,#4C1D95,#7C3AED)}
.wrap{padding:70px 110px 0}
.kicker{font-size:28px;font-weight:700;color:#7C3AED;letter-spacing:1px}
h1{font-size:68px;font-weight:800;line-height:1.15;margin:10px 0 34px;color:#2E1065}
.row{display:flex;gap:32px}
.card{background:#fff;border-radius:26px;box-shadow:0 10px 36px rgba(76,29,149,.12);padding:28px 34px;position:relative}
.card h3{font-size:32px;font-weight:700;color:#4C1D95;margin-bottom:12px}
.tag{position:absolute;top:22px;right:26px;font-size:22px;font-weight:700;color:#fff;background:#7C3AED;border-radius:999px;padding:5px 16px}
.tag.g{background:#E0702E}
.stat .n{font-size:96px;font-weight:800;color:#4C1D95;line-height:1.1}
.stat .l{font-size:30px;color:#4B4560;margin-top:8px}
.note{font-size:26px;color:#4B4560;line-height:1.45}
.chip{display:inline-block;font-size:26px;background:#EDE9FE;color:#4C1D95;border-radius:14px;padding:10px 18px;margin:6px 8px 0 0;font-weight:600}
.chip.x{background:#FEE2E2;color:#991B1B}
.foot{position:absolute;left:110px;right:110px;bottom:30px;display:flex;justify-content:space-between;font-size:22px;color:#7C6FA0}
canvas{display:block}
"""

JS_COMMON = """
Chart.defaults.animation=false;Chart.defaults.responsive=false;Chart.defaults.devicePixelRatio=1;
Chart.defaults.font.family="'Pretendard','Malgun Gothic',sans-serif";Chart.defaults.font.size=24;Chart.defaults.color='#3B3355';
Chart.register({id:'vals',afterDatasetsDraw(ch){const c=ch.ctx;ch.data.datasets.forEach((ds,i)=>{if(!ds.vals)return;
 const meta=ch.getDatasetMeta(i);meta.data.forEach((el,j)=>{const t=ds.vals[j];if(t==null)return;c.save();
 c.font="700 26px 'Pretendard','Malgun Gothic'";c.fillStyle=ds.valColor||'#2E1065';c.textAlign='center';
 const p=el.tooltipPosition();const hz=ch.options.indexAxis==='y';
 if(hz){c.textAlign='left';c.fillText(t,p.x+12,p.y+9);}else{c.fillText(t,p.x,p.y-14);}c.restore();});});}});
Chart.register({id:'hline',afterDraw(ch){const o=ch.options.plugins.hline;if(!o)return;const sc=ch.scales[o.axis||'y'];
 const c=ch.ctx,a=ch.chartArea;c.save();c.strokeStyle=o.color||'#E0702E';c.lineWidth=4;c.setLineDash([12,8]);c.beginPath();
 if(o.axis==='x'){const x=sc.getPixelForValue(o.value);c.moveTo(x,a.top);c.lineTo(x,a.bottom);}else{const y=sc.getPixelForValue(o.value);c.moveTo(a.left,y);c.lineTo(a.right,y);}
 c.stroke();c.setLineDash([]);c.font="700 24px 'Pretendard','Malgun Gothic'";c.fillStyle=o.color||'#E0702E';
 if(o.axis==='x'){c.textAlign='left';c.fillText(o.label,sc.getPixelForValue(o.value)+10,a.top+24);}else{c.textAlign='left';c.fillText(o.label,a.left+8,sc.getPixelForValue(o.value)-10);}c.restore();}});
"""


def canvas(cid, w, h):
    return f'<canvas id="{cid}" width="{w}" height="{h}"></canvas>'


def page(s, total, body, charts):
    js = "".join(f"new Chart(document.getElementById('{cid}'),{json.dumps(cfg, ensure_ascii=False)});"
                 for cid, cfg in charts)
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">'
            f'<script src="{CHARTJS}"></script><style>{CSS}</style></head><body>'
            f'<div class="bar"></div><div class="wrap"><div class="kicker">{s["slide"]:02d} / {total:02d} · 베이커리 1호점 출점 제안</div>'
            f'<h1>{html.escape(s["title"])}</h1>{body}</div>'
            '<div class="foot"><span>출처: 서울 열린데이터광장 상권분석서비스 · DART 감사보고서</span><span>전망·계획 수치는 가정</span></div>'
            f'<script>{JS_COMMON}document.fonts.ready.then(()=>{{{js}}});</script></body></html>')


def qlab(q):
    return f"{q[2:4]}Q{q[4]}"


def bar_cfg(labels, datasets, **opt):
    o = {"plugins": {"legend": {"display": len(datasets) > 1, "position": "top"}},
         "scales": {"x": {"grid": {"display": False}}, "y": {"grid": {"color": "#EEE"}}}}
    o.update(opt)
    return {"type": "bar", "data": {"labels": labels, "datasets": datasets}, "options": o}


# ---- inline SVG illustrations (concept only)
ICONS = {
    "cup": '<path d="M20 30h44l-5 46H25z" fill="#F4EDE1" stroke="#2F3237" stroke-width="4"/><path d="M64 40c12 0 12 20 0 20" fill="none" stroke="#2F3237" stroke-width="4"/><path d="M32 22c0-6 6-6 6-12M44 22c0-6 6-6 6-12" stroke="#8B5A2B" stroke-width="4" fill="none" stroke-linecap="round"/>',
    "croissant": '<path d="M10 62C18 30 74 30 82 62C70 50 22 50 10 62z" fill="#D9A15B" stroke="#8B5A2B" stroke-width="4"/><path d="M30 44l6 14M46 40v16M62 44l-6 14" stroke="#8B5A2B" stroke-width="4" stroke-linecap="round"/>',
    "roll": '<ellipse cx="46" cy="52" rx="34" ry="20" fill="#E3B26E" stroke="#8B5A2B" stroke-width="4"/><circle cx="34" cy="46" r="2.5" fill="#fff"/><circle cx="48" cy="42" r="2.5" fill="#fff"/><circle cx="58" cy="50" r="2.5" fill="#fff"/><circle cx="42" cy="56" r="2.5" fill="#fff"/>',
    "loaf": '<path d="M14 74V44c0-18 64-18 64 0v30z" fill="#E8C48A" stroke="#8B5A2B" stroke-width="4"/><path d="M14 44c0-10 14-16 22-12M46 30c10-4 24 2 26 12" fill="none" stroke="#8B5A2B" stroke-width="3"/>',
    "sandwich": '<path d="M10 40L46 18L82 40z" fill="#E8C48A" stroke="#8B5A2B" stroke-width="4"/><path d="M12 44h68" stroke="#8FA58A" stroke-width="7"/><path d="M12 52h68" stroke="#E07A7A" stroke-width="6"/><path d="M10 58h72v10H10z" fill="#E8C48A" stroke="#8B5A2B" stroke-width="4"/>',
    "cake": '<path d="M14 72V42L78 30v42z" fill="#F6D9A8" stroke="#8B5A2B" stroke-width="4"/><path d="M14 42L78 30" stroke="#5B3A1E" stroke-width="8"/>',
}
HERO = [("아메리카노", "cup"), ("소금버터롤", "roll"), ("버터 크루아상", "croissant"),
        ("우유식빵", "loaf"), ("잠봉뵈르", "sandwich"), ("치즈케이크", "cake")]


def icon(k, size=92):
    return f'<svg width="{size}" height="{size}" viewBox="0 0 92 92">{ICONS[k]}</svg>'


def floorplan(g, W=900, H=470):
    zones = g["zones"]; pal = [p["hex"] for p in g["palette"]]
    back = [z for z in zones if any(k in z["zone"] for k in ("오픈키친", "백오피스"))]
    front = [z for z in zones if z not in back]
    out = [f'<svg width="{W}" height="{H + 60}" viewBox="0 0 {W} {H + 60}">',
           f'<rect x="2" y="2" width="{W - 4}" height="{H}" rx="10" fill="#fff" stroke="#2F3237" stroke-width="6"/>']
    tot = sum(z["area_ratio_pct"] for z in zones); y = 2; ci = 0
    for row in (back, front):
        rs = sum(z["area_ratio_pct"] for z in row); rh = H * rs / tot; x = 2
        for z in row:
            w = (W - 4) * z["area_ratio_pct"] / rs; col = pal[ci % len(pal)]; ci += 1
            dark = col in ("#2F3237", "#8B5A2B")
            fc = "#fff" if dark else "#2E1065"
            out.append(f'<rect x="{x + 6}" y="{y + 6}" width="{w - 12}" height="{rh - 12}" rx="8" fill="{col}" opacity=".9"/>')
            out.append(f'<text x="{x + w / 2}" y="{y + rh / 2 - 6}" text-anchor="middle" font-size="{26 if w > 200 else 20}" font-weight="700" fill="{fc}">{html.escape(short(z["zone"]) if w > 200 else short(z["zone"]).split("·")[0])}</text>')
            out.append(f'<text x="{x + w / 2}" y="{y + rh / 2 + 28}" text-anchor="middle" font-size="24" fill="{fc}">{z["area_ratio_pct"]}%</text>')
            x += w
        y += rh
    out.append(f'<path d="M{W / 2 - 60} {H + 2}h120" stroke="#E0702E" stroke-width="10"/><text x="{W / 2}" y="{H + 44}" text-anchor="middle" font-size="24" font-weight="700" fill="#E0702E">입구 · 역 방향 동선 ↑</text></svg>')
    return "".join(out)


def build_slides(g, S):
    out = {}
    q7 = g["q7"]; qs = sorted(q7)
    # 1 -----------------------------------------------------------
    y = g["yoy"]
    stats = [(f"+{y[-1]}%", "합산 매출 YoY (가속)"), (f"+{g['per_store_chg']}%", "베이커리 점포당 매출 3년"),
             (f"+{g['flpop']}%", f"유동인구 3년 (서울 중앙값 {g['flpop_med']}%)")]
    body = ('<div class="row">' + "".join(f'<div class="card stat" style="flex:1"><div class="n">{n}</div><div class="l">{l}</div></div>' for n, l in stats) + "</div>"
            f'<div class="card" style="margin-top:30px"><h3>{g["site"]} 제과+커피 분기 매출 (억원)</h3>{canvas("c1", 1620, 330)}</div>')
    out[1] = (body, [("c1", {"type": "line", "data": {"labels": [qlab(q) for q in qs], "datasets": [{
        "data": [q7[q] for q in qs], "borderColor": VIOLET, "backgroundColor": "rgba(124,58,237,.15)", "fill": True,
        "borderWidth": 6, "pointRadius": 8, "pointBackgroundColor": PURPLE, "tension": .3, "vals": [f"{q7[q]}" for q in qs]}]},
        "options": {"plugins": {"legend": {"display": False}}, "layout": {"padding": {"top": 30}},
                    "scales": {"x": {"grid": {"display": False}}, "y": {"min": 20, "grid": {"color": "#EEE"}}}}})])
    # 2 -----------------------------------------------------------
    st = g["stores"]; sq = sorted(st); bq = g["bq7"]
    yl = ["23→24", "24→25", "25→26"]
    body = ('<div class="row">'
            f'<div class="card" style="flex:1"><h3>2분기 합산매출 YoY (%) — 3년 연속 가속</h3>{canvas("c2a", 800, 600)}</div>'
            f'<div class="card" style="flex:1"><h3>베이커리 점포 ↓ vs 매출 ↑</h3>{canvas("c2b", 800, 600)}</div></div>')
    out[2] = (body, [
        ("c2a", bar_cfg(yl, [{"data": y, "backgroundColor": ["#C4B5FD", "#8B5CF6", PURPLE], "borderRadius": 10,
                              "vals": [f"{v}%" for v in y]}], layout={"padding": {"top": 40}})),
        ("c2b", {"type": "bar", "data": {"labels": [qlab(q) for q in sq], "datasets": [
            {"type": "bar", "label": "베이커리 점포수(곳)", "data": [st[q] for q in sq], "backgroundColor": "#C4B5FD",
             "borderRadius": 10, "yAxisID": "y", "vals": [f"{st[q]:.0f}곳" for q in sq]},
            {"type": "line", "label": "베이커리 분기매출(억)", "data": [bq[q] for q in sq], "borderColor": "#E0702E",
             "borderWidth": 6, "pointRadius": 9, "pointBackgroundColor": "#E0702E", "yAxisID": "y2",
             "vals": [f"{bq[q]}억" for q in sq], "valColor": "#B4501A"}]},
            "options": {"layout": {"padding": {"top": 40}}, "plugins": {"legend": {"position": "bottom"}},
                        "scales": {"x": {"grid": {"display": False}}, "y": {"min": 0, "max": 28, "grid": {"color": "#EEE"}},
                                   "y2": {"position": "right", "min": 0, "max": 11, "grid": {"display": False}}}}})])
    # 3 -----------------------------------------------------------
    cs = g["cands"]; names = [c["name"].replace("동대문역사문화공원역", "동대문역사문화공원") for c in cs]
    types = ["대형 프랜차이즈", "트렌드/프리미엄", "기타 다점포", "개인/독립"]
    tcol = [PURPLE, "#E0702E", "#A78BFA", "#DDD6FE"]
    body = ('<div class="row">'
            f'<div class="card" style="flex:1"><h3>제과점 연매출 (억원, 최근 4분기)</h3>{canvas("c3a", 760, 520)}</div>'
            f'<div class="card" style="flex:1.15"><h3>반경 500m 베이커리 구성 (곳)</h3>{canvas("c3b", 880, 520)}</div></div>'
            f'<div style="margin-top:22px"><span class="chip x">✕ 잠실 관광특구 — 한 분기 데이터 단절, 이후 연율 {g["jamsil"]}% → 제외</span>'
            f'<span class="chip">출처: {g["comp_src"]}</span></div>')
    out[3] = (body, [
        ("c3a", bar_cfg(names, [{"data": [round(c["bakery_yr"] / 1e8, 1) for c in cs],
                                 "backgroundColor": [PURPLE if c["name"] == g["site"] else "#C4B5FD" for c in cs],
                                 "borderRadius": 10, "vals": [f"{c['bakery_yr'] / 1e8:.1f}억" for c in cs]}],
                        layout={"padding": {"top": 40}})),
        ("c3b", {"type": "bar", "data": {"labels": names, "datasets": [
            {"label": t, "data": [c["types"].get(t, 0) for c in cs], "backgroundColor": tcol[i]} for i, t in enumerate(types)]},
            "options": {"indexAxis": "y", "plugins": {"legend": {"position": "bottom", "labels": {"font": {"size": 22}}}},
                        "scales": {"x": {"stacked": True, "grid": {"color": "#EEE"}}, "y": {"stacked": True, "grid": {"display": False}}}}})])
    # 4 -----------------------------------------------------------
    sw = "".join(f'<div style="flex:1;text-align:center"><div style="height:110px;border-radius:14px;background:{p["hex"]};border:2px solid #ddd"></div>'
                 f'<div style="font-size:19px;font-weight:700;margin-top:8px;white-space:nowrap">{html.escape(p["name"])}</div><div style="font-size:18px;color:#6B6480">{p["hex"]}</div></div>'
                 for p in g["palette"])
    mats = "".join(f'<span class="chip">{html.escape(m)}</span>' for m in g["materials"][:4])
    area_note = (f'면적 {g["area"]:.0f}㎡ (손익 가정) · interior.json {g["area_interior"]}㎡안은 재산정 필요'
                 if g["area"] != g["area_interior"] else f'면적 {g["area"]}㎡ (가정)')
    body = ('<div class="row">'
            f'<div class="card" style="flex:1.1"><span class="tag g">컨셉 일러스트</span><h3>평면 존 구성 (면적 비율)</h3>{floorplan(g)}</div>'
            f'<div class="card" style="flex:1"><span class="tag g">컨셉 일러스트</span><h3>무드보드</h3><div style="display:flex;gap:14px">{sw}</div>'
            f'<div style="margin-top:22px">{mats}</div><div class="note" style="margin-top:22px">출근길 3분 그랩앤고 · 퇴근길 갓 구운 빵<br>{area_note}</div></div></div>')
    out[4] = (body, [])
    # 5 -----------------------------------------------------------
    mix = g["mix"]; tk = g["ticket"]; tq = sorted(tk["추이_상권"])
    items = {i["메뉴"]: i for i in g["items"]}
    cards = ""
    for key, ic in HERO:
        it = next((v for k, v in items.items() if key in k), None)
        if it:
            cards += (f'<div style="flex:1;text-align:center;background:#FAF7F2;border-radius:18px;padding:12px 6px">{icon(ic)}'
                      f'<div style="font-size:22px;font-weight:700">{html.escape(short(it["메뉴"]))}</div><div style="font-size:22px;color:#7C3AED">{it["가격_원"]:,}원</div></div>')
    body = ('<div class="row">'
            f'<div class="card" style="flex:0 0 520px"><span class="tag">가정</span><h3>매출 믹스 (%)</h3>{canvas("c5a", 450, 400)}</div>'
            f'<div class="card" style="flex:1"><h3>상권 객단가 추이 (원) · 목표 {tk["제안"]:,}원</h3>{canvas("c5b", 1000, 400)}</div></div>'
            f'<div class="card" style="margin-top:24px;padding:18px 24px"><span class="tag g">컨셉 일러스트</span><div style="display:flex;gap:14px;margin-top:6px">{cards}</div></div>')
    out[5] = (body, [
        ("c5a", {"type": "doughnut", "data": {"labels": [m["카테고리"] for m in mix], "datasets": [{
            "data": [m["매출비중_%"] for m in mix], "backgroundColor": [PURPLE, "#A78BFA", "#8B5A2B", "#E0702E", "#8FA58A"]}]},
            "options": {"cutout": "55%", "plugins": {"legend": {"position": "right", "labels": {"font": {"size": 22}}}}}}),
        ("c5b", {"type": "line", "data": {"labels": [qlab(q) for q in tq], "datasets": [
            {"label": k, "data": [tk["추이_상권"][q][k] for q in tq], "borderColor": col, "borderWidth": 5, "pointRadius": 6,
             "pointBackgroundColor": col} for k, col in (("제과점", "#8B5A2B"), ("합산", VIOLET), ("커피", "#A78BFA"))]},
            "options": {"plugins": {"legend": {"position": "bottom"},
                                    "hline": {"value": tk["제안"], "label": f"목표 {tk['제안']:,}원 (가정)"}},
                        "scales": {"x": {"grid": {"display": False}}, "y": {"min": 4000, "grid": {"color": "#EEE"}}}}})])
    # 6 -----------------------------------------------------------
    sc = g["scen"]; order = ["보수", "기준", "낙관"]
    ceil, model = g["rent_ceiling"], g["rent_model"]
    body = ('<div class="row">'
            f'<div class="card" style="flex:0 0 940px"><span class="tag">가정</span><h3>시나리오별 Y1 매출 (억원) · 영업이익률</h3>{canvas("c6a", 870, 560)}</div>'
            f'<div class="card" style="flex:1"><span class="tag">가정</span><h3>임대료 게이트 (월, 만원)</h3>{canvas("c6b", 640, 400)}'
            f'<div class="note" style="margin-top:14px">기준 Y1 손익분기 월 임대료 상한 <b>{man(ceil)}원</b><br>모델 임차료 {man(model)}원 · 실제 매물이 상한 초과 시 출점 보류'
            f'<br><span style="font-size:20px;color:#7C6FA0">{g["pnl_name"]} · {g["rent_src"]}</span></div></div></div>')
    out[6] = (body, [
        ("c6a", bar_cfg(order, [{"data": [round(sc[k]["rev"] / 1e8, 2) for k in order],
                                 "backgroundColor": ["#C4B5FD", PURPLE, "#8B5CF6"], "borderRadius": 10,
                                 "vals": [f"{sc[k]['rev'] / 1e8:.2f}억 · {pct(sc[k]['opm'])}%" for k in order]}],
                        layout={"padding": {"top": 40}},
                        plugins={"legend": {"display": False},
                                 "hline": {"value": round(g["be_yr"] / 1e8, 2), "label": f"손익분기 {g['be_yr'] / 1e8:.2f}억"}})),
        ("c6b", {"type": "bar", "data": {"labels": ["월 임대료 상한", "모델 임차료"], "datasets": [{
            "data": [round(ceil / 1e4), round(model / 1e4)], "backgroundColor": ["#E0702E", PURPLE], "borderRadius": 10,
            "vals": [man(ceil), man(model)]}]},
            "options": {"indexAxis": "y", "layout": {"padding": {"right": 110}}, "plugins": {"legend": {"display": False}},
                        "scales": {"x": {"min": 0, "grid": {"color": "#EEE"}}, "y": {"grid": {"display": False}}}}})])
    # 7 -----------------------------------------------------------
    db = '<svg width="80" height="80" viewBox="0 0 80 80"><ellipse cx="40" cy="18" rx="28" ry="10" fill="#7C3AED"/><path d="M12 18v44c0 6 56 6 56 0V18" fill="#C4B5FD" stroke="#7C3AED" stroke-width="4"/><path d="M12 40c0 6 56 6 56 0" fill="none" stroke="#7C3AED" stroke-width="4"/></svg>'
    doc = '<svg width="80" height="80" viewBox="0 0 80 80"><path d="M18 8h32l14 14v50H18z" fill="#fff" stroke="#4C1D95" stroke-width="4"/><path d="M28 34h26M28 46h26M28 58h18" stroke="#7C3AED" stroke-width="5"/></svg>'
    steps = [f"월 {man(ceil)}원 이하 매물 확보", f"{g['area']:.0f}㎡ 기준 인테리어 견적",
             f"2026년 3분기 데이터 게이트" + (f" (제과점 분기 {g['q3_gate_eok']}억 이상)" if g["q3_gate_eok"] else "")]
    body = ('<div class="row">'
            f'<div class="card" style="flex:1;display:flex;gap:24px;align-items:center">{db}<div><h3>서울 열린데이터광장</h3><div class="note">상권분석서비스 매출·점포·유동인구, 인허가</div></div></div>'
            f'<div class="card" style="flex:1;display:flex;gap:24px;align-items:center">{doc}<div><h3>DART 감사보고서</h3><div class="note">직영 베이커리·카페 비용구조, 점포당 매출</div></div></div></div>'
            '<div class="row" style="margin-top:34px">' +
            "".join(f'<div class="card" style="flex:1;border-top:12px solid {VIOLET}"><div style="font-size:72px;font-weight:800;color:#C4B5FD">{i + 1}</div>'
                    f'<div style="font-size:36px;font-weight:700">{html.escape(t)}</div></div>' for i, t in enumerate(steps)) + "</div>")
    out[7] = (body, [])
    return out


# ---------------------------------------------------------------- render / audio / video
def render_png(browser, html_path, png_path):
    prof = VID / f"_profile_{png_path.stem}"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={prof}",
                    "--virtual-time-budget=8000", "--run-all-compositor-stages-before-draw",
                    "--window-size=1920,1080", f"--screenshot={png_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=180)
    for _ in range(240):   # msedge.exe may return before the PNG is written
        if png_path.exists() and png_path.stat().st_size > 0:
            time.sleep(0.5); shutil.rmtree(prof, ignore_errors=True); return
        time.sleep(0.25)
    raise RuntimeError(f"screenshot not written: {png_path}")


def tts_all(slides):
    ps = ["Add-Type -AssemblyName System.Speech", "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
          "$s.SelectVoice('Microsoft Heami Desktop')", f"$s.Rate = {RATE}"]
    for s in slides:
        txt, wav = AUDIO / f"{s['slide']:02d}.txt", AUDIO / f"{s['slide']:02d}.wav"
        txt.write_text(s["narration"], encoding="utf-8")
        ps += [f"$s.SetOutputToWaveFile('{wav}')", f"$s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8))"]
    ps.append("$s.Dispose()")
    f = AUDIO / "tts.ps1"; f.write_text("\n".join(ps), encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(f)], check=True)


def wav_len(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def ts(t):
    h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def main():
    g = gather()
    S = build_script(g)
    print("P&L:", g["pnl_name"], "| location_v2:", g["loc_v2"], "| rent:", g["rent_src"])
    for d in (SLIDES, AUDIO, SEG):
        shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
    vis = build_slides(g, S)
    for s in S:
        s["bullets"] = []   # slides are visual; narration carries the detail
    (VID / "script.json").write_text(json.dumps(S, ensure_ascii=False, indent=2), encoding="utf-8")
    browser = next(b for b in BROWSERS if os.path.exists(b))
    for s in S:
        n = f"{s['slide']:02d}"; body, charts = vis[s["slide"]]
        (SLIDES / f"{n}.html").write_text(page(s, len(S), body, charts), encoding="utf-8")
        render_png(browser, SLIDES / f"{n}.html", SLIDES / f"{n}.png")
    tts_all(S)
    vtt, t0, concat = ["WEBVTT", ""], 0.0, []
    for s in S:
        n = f"{s['slide']:02d}"; alen = wav_len(AUDIO / f"{n}.wav"); dur = alen + PAD; seg = SEG / f"{n}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", str(SLIDES / f"{n}.png"),
                        "-i", str(AUDIO / f"{n}.wav"), "-af", f"apad=pad_dur={PAD}", "-t", f"{dur:.3f}",
                        "-vf", "scale=1920:1080,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
                        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(seg)], check=True)
        concat.append(f"file '{seg.as_posix()}'")
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", s["narration"]) if x.strip()]
        tot = sum(len(x) for x in sents); t = t0
        for x in sents:
            d = alen * len(x) / tot; vtt += [f"{ts(t)} --> {ts(t + d)}", x, ""]; t += d
        t0 += dur
    (SEG / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    mp4 = VID / "presentation.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(SEG / "list.txt"),
                    "-c", "copy", "-movflags", "+faststart", str(mp4)], check=True)
    (VID / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
    ASSETS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mp4, ASSETS / "presentation.mp4"); shutil.copyfile(VID / "captions.vtt", ASSETS / "captions.vtt")
    print(f"done: {mp4} expected {t0:.1f}s")


if __name__ == "__main__":
    main()
