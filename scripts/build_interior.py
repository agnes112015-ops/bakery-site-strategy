# -*- coding: utf-8 -*-
"""남부터미널역 매장 공간 컨셉(interior.json) 산출.
입력: data/interim/location.json (final_profile), data/raw/{sales_20262,store_20262,fclty_all,repop_all,wrcpop_all,flpop_20262,subway_202611*}.json
모든 수치는 서울 열린데이터광장 원천에서 계산. 면적·좌석은 '가정'으로 명시.
실행: PYTHONIOENCODING=utf-8 python scripts/build_interior.py
"""
import json, glob, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'data', 'raw')
INT = os.path.join(ROOT, 'data', 'interim')
C = '3120175'

def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)

loc = load(os.path.join(INT, 'location.json'))
fp = loc['final_profile']
cand = [c for c in loc['candidates'] if c['TRDAR_CD'] == C][0]

S_SALES = '서울시 상권분석서비스 추정매출 VwsmTrdarSelngQq (제과점 CS100005·커피-음료 CS100010), 20262'
S_STORE = '서울시 상권분석서비스 점포 VwsmTrdarStorQq, 20262'
S_STORE2 = '서울시 상권분석서비스 점포 VwsmTrdarStorQq, 20232·20262'
S_FLPOP = '서울시 상권분석서비스 길단위 유동인구 VwsmTrdarFlpopQq, 20262'
S_REPOP = '서울시 상권분석서비스 상주인구 VwsmTrdarRepopQq, 20262 (20234 이후 값 동결)'
S_WRC = '서울시 상권분석서비스 직장인구 VwsmTrdarWrcPopltnQq, 20262 (20244 이후 값 동결)'
S_FCL = '서울시 상권분석서비스 집객시설 VwsmTrdarFcltyQq, 20262'
S_SUB = '서울시 지하철 호선별 역별 승하차 인원 CardSubwayStatsNew, 2026-11-02~2026-11-08 (1주)'
S_IX = '서울시 상권분석서비스 상권변화지표 VwsmTrdarIxQq, 20262'
S_SC = '서울시 상권분석서비스 VwsmTrdarSelngQq 20262 기준 176개 분석상권 중앙값 (data/interim/location.json, scripts/analyze.py)'

# ---------- 원천 재계산 ----------
sales = {r['SVC_INDUTY_CD']: r for r in load(os.path.join(RAW, 'sales_20262.json'))['rows'] if r['TRDAR_CD'] == C}
bk, cf = sales['CS100005'], sales['CS100010']
store = {r['SVC_INDUTY_CD']: r for r in load(os.path.join(RAW, 'store_20262.json'))['rows'] if r['TRDAR_CD'] == C}
fcl = [r for r in load(os.path.join(RAW, 'fclty_all.json'))['rows'] if r['TRDAR_CD'] == C and r['STDR_YYQU_CD'] == '20262'][0]
rep = [r for r in load(os.path.join(RAW, 'repop_all.json'))['rows'] if r['TRDAR_CD'] == C and r['STDR_YYQU_CD'] == '20262'][0]
wrc = [r for r in load(os.path.join(RAW, 'wrcpop_all.json'))['rows'] if r['TRDAR_CD'] == C and r['STDR_YYQU_CD'] == '20262'][0]

sub = []
for f in sorted(glob.glob(os.path.join(RAW, 'subway_202611*.json'))):
    for r in load(f)['rows']:
        if '남부터미널' in r['SBWY_STNS_NM']:
            d = datetime.datetime.strptime(r['USE_YMD'], '%Y%m%d')
            sub.append((r['USE_YMD'], d.weekday(), int(r['GTON_TNOPE']) + int(r['GTOFF_TNOPE'])))
wkday = [v for _, w, v in sub if w < 5]
wkend = [v for _, w, v in sub if w >= 5]
sub_wd_avg = sum(wkday) / len(wkday)
sub_we_avg = sum(wkend) / len(wkend)
sub_we_ratio = sub_we_avg / sub_wd_avg

pct = lambda a, b: round(a / b * 100, 1)
bk_amt, cf_amt = bk['THSMON_SELNG_AMT'], cf['THSMON_SELNG_AMT']
bk_cnt, cf_cnt = bk['THSMON_SELNG_CO'], cf['THSMON_SELNG_CO']
bk_atv = bk_amt / bk_cnt
cf_atv = cf_amt / cf_cnt
bk_4060 = pct(bk['AGRDE_40_SELNG_AMT'] + bk['AGRDE_50_SELNG_AMT'] + bk['AGRDE_60_ABOVE_SELNG_AMT'], bk_amt)  # 총매출 대비
cf_3040 = pct(cf['AGRDE_30_SELNG_AMT'] + cf['AGRDE_40_SELNG_AMT'], cf_amt)  # 총매출 대비
wrc_rep_ratio = wrc['TOT_WRC_POPLTN_CO'] / rep['TOT_REPOP_CO']
wrc_2040 = int(wrc['AGRDE_20_WRC_POPLTN_CO'] + wrc['AGRDE_30_WRC_POPLTN_CO'] + wrc['AGRDE_40_WRC_POPLTN_CO'])

bk_n = store['CS100005']['SIMILR_INDUTY_STOR_CO']
cf_n = store['CS100010']['SIMILR_INDUTY_STOR_CO']

prof = fp['매출프로필_20262']
flp = fp['유동인구_20262']
comb = prof['합산']
med = cand['지표']['고객구성_합산(제과+커피, 20262)']['176상권중앙값']
STC = cand['지표']['점포']
b_pp, b_pp_med, b_pp_ch = STC['베이커리_점포당분기매출_억원'], STC['베이커리_점포당분기매출_176중앙값_억원'], STC['베이커리_점포당매출_3년변화율_%']
bk_n0, cf_n0 = int(STC['베이커리점포_3년전']), int(STC['커피점포_3년전'])
cf_clo = STC['커피_폐업률_%(20262)']
am_gap = round(comb['시간대비중_%']['06~11'] - med['오전비중_%'], 1)
IXC = cand['지표']['상권변화지표']
bt = prof['베이커리(제과점)']['시간대비중_%']
flp_we = round(flp['요일비중_%']['SAT'] + flp['요일비중_%']['SUN'], 1)
flp_late = round(flp['시간대비중_%']['21~24'] + flp['시간대비중_%']['00~06'], 1)
sales_late = round(comb['시간대비중_%']['21~24'] + comb['시간대비중_%']['00~06(잔차)'], 1)

# ---------- 면적·좌석 가정 ----------
DAYS_Q2 = 91          # 4~6월 일수
WEEKDAYS_Q2 = 65      # 2026년 2분기 평일 수(공휴일 미반영, 가정)
# 가정 A: 신규 매장 일 거래건수 = 상권 베이커리 점포당 평균 + 커피 점포당 평균 (복합매장이 두 업종 평균을 각각 확보)
bk_tx_store_day = bk_cnt / bk_n / DAYS_Q2
cf_tx_store_day = cf_cnt / cf_n / DAYS_Q2
tx_day = bk_tx_store_day + cf_tx_store_day
# 가정 B: 거래건수의 주중 비중 = 합산 매출의 주중 비중(81.4%)
tx_weekday = tx_day * DAYS_Q2 * comb['주중주말비중_%']['주중'] / 100 / WEEKDAYS_Q2
# 피크(11~14시, 3시간) 시간당 거래 — 시간대 비중은 합산 매출 비중을 거래 비중의 대리변수로 사용(가정)
peak_hr_tx = tx_weekday * comb['시간대비중_%']['11~14'] / 100 / 3
EATIN = 0.35   # 가정: 매장 내 취식 비율(오피스형 테이크아웃 상권)
PARTY = 1.5    # 가정: 거래 1건당 착석 인원
STAY = 0.6     # 가정: 평균 체류 0.6시간(36분)
OCC = 0.85     # 가정: 좌석 점유 효율(빈자리 손실)
seats = peak_hr_tx * EATIN * PARTY * STAY / OCC
seats_r = int(round(seats / 2.0) * 2)
SEAT_M2 = 1.6  # 가정: 좌석 1석당 객석 면적(통로 포함)
seat_area = seats_r * SEAT_M2
ZONES = [  # (존, 면적비중) — 가정
    ('베이크 오픈키친(생산·오븐 쇼)', 0.30),
    ('빵 진열·그랩앤고 계산대', 0.22),
    ('테이크아웃 커피바(모바일 픽업 선반 포함)', 0.13),
    ('좌석(창가 카운터석+2인 테이블)', 0.30),
    ('백오피스·창고·화장실', 0.05),
]
total_area = seat_area / 0.30
total_area_r = int(round(total_area / 5.0) * 5)

calc = {
    '베이커리_점포당_일거래': round(bk_tx_store_day, 1),
    '커피_점포당_일거래': round(cf_tx_store_day, 1),
    '신규매장_일거래_가정': round(tx_day, 1),
    '평일_일거래': round(tx_weekday, 1),
    '피크_시간당거래(11~14)': round(peak_hr_tx, 1),
    '필요좌석_계산값': round(seats, 1),
    '좌석_가정': seats_r,
    '좌석면적_m2': round(seat_area, 1),
    '총면적_계산값_m2': round(total_area, 1),
    '총면적_가정_m2': total_area_r,
    '총면적_가정_평': round(total_area_r / 3.3058, 1),
    '지하철_평일평균_승하차': round(sub_wd_avg),
    '지하철_주말평균_승하차': round(sub_we_avg),
    '지하철_주말/평일': round(sub_we_ratio, 3),
}

# ---------- 산출물 ----------
out = {
    'meta': {
        '상권': '남부터미널역 (TRDAR_CD 3120175, 서초구 서초1동, 발달상권)',
        '입력': 'data/interim/location.json final_profile + data/raw 원천',
        '스크립트': 'scripts/build_interior.py',
        '원칙': '수치는 서울 열린데이터광장 원천만 사용. 면적·좌석·존 비율·운영시간·소재·컬러는 설계 가정이며 근거 수치와 계산식을 함께 기록.',
        '계산값': calc,
    },
    'concept': '플랫폼 베이크하우스 (Platform Bakehouse)',
    'one_liner': '출근길엔 3분 안에 빵과 커피를 집어 가고, 퇴근길엔 오늘 구운 빵을 장바구니에 담아 가는 역세권 베이커리 주도형 복합 매장 — 좌석보다 오븐과 동선이 주인공.',
    'customer_definition': [
        f"주중형: 합산 매출 주중 {comb['주중주말비중_%']['주중']}%(176상권 중앙값 주말 {med['주말비중_%']}% 대비 주말 {comb['주중주말비중_%']['주말']}%), 직장인구 {int(wrc['TOT_WRC_POPLTN_CO']):,}명이 상주인구 {int(rep['TOT_REPOP_CO']):,}명의 {wrc_rep_ratio:.1f}배.",
        f"아침형: 합산 06~11시 매출 {comb['시간대비중_%']['06~11']}%(176상권 중앙값 {med['오전비중_%']}%), 유동인구도 06~11시가 {flp['시간대비중_%']['06~11']}%로 최다 시간대.",
        f"이중 고객층: 커피는 남성 {prof['커피-음료']['성별비중_%']['남성']}%·30대 {prof['커피-음료']['연령비중_%']['30대']}%의 점심(11~14시 {prof['커피-음료']['시간대비중_%']['11~14']}%) 수요, 베이커리는 여성 {prof['베이커리(제과점)']['성별비중_%']['여성']}%·40대 이상 {bk_4060}%의 퇴근길(17~21시 {prof['베이커리(제과점)']['시간대비중_%']['17~21']}%) 수요.",
        f"객단가: 베이커리 {bk_atv:,.0f}원 vs 커피 {cf_atv:,.0f}원, 합산 {comb['객단가_원']:,}원(176상권 중앙값 {med['객단가_원']:,}원) — 가격은 상권 수준에서 시작하고 객단가는 빵 동반구매로 올린다.",
        f"심야 미수익화: 유동인구 21~06시 {flp_late}%인데 합산 매출은 {sales_late}% — 심야 영업 연장은 비권장.",
        "비중 정의: 성별·연령 비중은 모두 해당 업종 분기 총매출 대비. 성별·연령 미상(법인카드 등) 매출이 있어 남+여, 연령대 합이 100%가 되지 않는다.",
    ],
    'personas': [
        {
            'name': '페르소나 A — 출근·점심 그랩앤고 오피스 워커',
            'profile': '30~40대 직장인(남녀 혼합, 커피 결제는 남성 우위), 평일 08시 전후 출근길·12시 점심 직후 방문, 1인 테이크아웃 중심',
            'needs': ['3분 이내 결제·픽업', '모바일 선주문 픽업 선반', '커피+샌드위치/크루아상 세트', '점심 직후 짧은 대기 동선'],
            'evidence': [
                {'claim': '상권 고객 기반은 상주보다 직장인구', 'number': f"직장인구 {int(wrc['TOT_WRC_POPLTN_CO']):,}명 / 상주인구 {int(rep['TOT_REPOP_CO']):,}명 = {wrc_rep_ratio:.1f}배; 직장인구 20~40대 {wrc_2040:,}명({pct(wrc_2040, wrc['TOT_WRC_POPLTN_CO'])}%)", 'source': f'{S_WRC}; {S_REPOP}'},
                {'claim': '커피 매출은 점심·아침에 집중', 'number': f"커피 11~14시 {prof['커피-음료']['시간대비중_%']['11~14']}%, 06~11시 {prof['커피-음료']['시간대비중_%']['06~11']}% (합 {round(prof['커피-음료']['시간대비중_%']['11~14'] + prof['커피-음료']['시간대비중_%']['06~11'], 1)}%)", 'source': S_SALES},
                {'claim': '커피 결제 고객은 30~40대·남성 우위', 'number': f"커피 30대 {prof['커피-음료']['연령비중_%']['30대']}%, 30~40대 {cf_3040}%, 남성 {prof['커피-음료']['성별비중_%']['남성']}%", 'source': S_SALES},
                {'claim': '커피는 저단가 고빈도 구매', 'number': f"커피 객단가 {cf_atv:,.0f}원, 분기 거래 {int(cf_cnt):,}건, 주중 {prof['커피-음료']['주중주말비중_%']['주중']}%", 'source': S_SALES},
                {'claim': '역 이용은 평일 집중', 'number': f"남부터미널(예술의전당)역 승하차 평일 평균 {sub_wd_avg:,.0f}명/일, 주말 평균 {sub_we_avg:,.0f}명/일(평일의 {sub_we_ratio*100:.0f}%)", 'source': S_SUB},
            ],
        },
        {
            'name': '페르소나 B — 퇴근길·외출길 빵 장보기 고객',
            'profile': '40~60대 이상 여성 중심, 퇴근길(17~21시) 또는 오전 장보기·병원/관공서 방문 겸 들러 식빵·과자빵을 2~3개 이상 담아 가는 고객. 상권 내 슈퍼마켓 0곳이라 빵이 저녁 장바구니 역할.',
            'needs': ['오후 2차 굽기로 퇴근 시간대 갓 구운 빵', '식사빵·식빵 중심 진열과 넉넉한 포장', '고령 고객도 읽기 쉬운 가격표·넓은 통로', '짧은 대기용 소형 벤치'],
            'evidence': [
                {'claim': '베이커리 결제는 여성·40대 이상 비중이 높음', 'number': f"베이커리 여성 {prof['베이커리(제과점)']['성별비중_%']['여성']}%(커피 {prof['커피-음료']['성별비중_%']['여성']}%), 40대 이상 {bk_4060}%, 60대 이상 {prof['베이커리(제과점)']['연령비중_%']['60대이상']}%(커피 {prof['커피-음료']['연령비중_%']['60대이상']}%)", 'source': S_SALES},
                {'claim': '베이커리는 퇴근 시간대 비중이 커피의 2배', 'number': f"17~21시 베이커리 {prof['베이커리(제과점)']['시간대비중_%']['17~21']}% vs 커피 {prof['커피-음료']['시간대비중_%']['17~21']}%", 'source': S_SALES},
                {'claim': '베이커리 객단가는 커피보다 높아 복수 구매 성격', 'number': f"베이커리 객단가 {bk_atv:,.0f}원 vs 커피 {cf_atv:,.0f}원", 'source': S_SALES},
                {'claim': '상권 내 장보기 대체 시설 부재, 방문 목적 시설 존재', 'number': f"슈퍼마켓 {int(fcl['SUPMK_CO'])}곳, 종합병원 {int(fcl['GNRL_HSPTL_CO'])}곳, 관공서 {int(fcl['PBLOFC_CO'])}곳, 은행 {int(fcl['BANK_CO'])}곳, 집객시설 총 {int(fcl['VIATR_FCLTY_CO'])}곳", 'source': S_FCL},
                {'claim': '베이커리 공급은 줄고 점포당 수요는 큼', 'number': f"베이커리 점포 {int(bk_n)}곳(3년전 {bk_n0}곳), 점포당 분기매출 {b_pp:.3f}억원(176 중앙값 {b_pp_med:.3f}억원)", 'source': f'{S_STORE2}; {S_SALES}'},
            ],
        },
    ],
    'zones': [
        {'zone': ZONES[0][0], 'area_ratio_pct': 30, 'area_m2_assumed': round(total_area_r * 0.30, 1),
         'why': f'베이커리 주도 포맷. 점포당 베이커리 매출이 176상권 중앙값의 {b_pp / b_pp_med:.1f}배로 생산 능력이 매출 상한이 되므로 오븐·작업대 면적을 최우선 확보. 유리벽 오픈키친으로 굽는 모습을 출입구 쪽에 노출해 커피 {int(cf_n)}곳 사이에서 시각적 차별화.',
         'evidence': f'베이커리 점포당 분기매출 {b_pp:.3f}억원 vs 중앙값 {b_pp_med:.3f}억원 ({S_STORE}; {S_SALES}); 커피 점포 {cf_n0}→{int(cf_n)}곳 ({S_STORE2})'},
        {'zone': ZONES[1][0], 'area_ratio_pct': 22, 'area_m2_assumed': round(total_area_r * 0.22, 1),
         'why': f'오전(06~11시) 합산 매출 비중이 중앙값보다 {am_gap}%p 높고, 베이커리는 시간대가 06~11/11~14/14~17/17~21에 고르게 분산 → 입구 정면 진열대와 셀프 트레이 2레인 계산대로 체류 없이 회전.',
         'evidence': f"합산 06~11시 {comb['시간대비중_%']['06~11']}% vs 중앙값 {med['오전비중_%']}%; 베이커리 시간대 {bt['06~11']}/{bt['11~14']}/{bt['14~17']}/{bt['17~21']}% ({S_SALES}; {S_SC})"},
        {'zone': ZONES[2][0], 'area_ratio_pct': 13, 'area_m2_assumed': round(total_area_r * 0.13, 1),
         'why': f'커피는 11~14시에 {prof['커피-음료']['시간대비중_%']['11~14']}% 집중 → 점심 피크용 별도 커피 픽업 카운터와 모바일 선주문 선반. 커피 단독 경쟁은 포화이므로 면적은 최소, 빵 동반구매 동선 끝에 배치.',
         'evidence': f"커피 11~14시 {prof['커피-음료']['시간대비중_%']['11~14']}%, 커피 폐업률 20262 {cf_clo:.0f}% ({S_SALES}; {S_STORE})"},
        {'zone': ZONES[3][0], 'area_ratio_pct': 30, 'area_m2_assumed': round(total_area_r * 0.30, 1),
         'why': f"주말 비중이 낮고({comb['주중주말비중_%']['주말']}%) 객단가가 낮은({comb['객단가_원']:,}원) 오피스형 상권이라 대형 체류 좌석은 비효율. 평일 피크 시간당 거래 기반 계산값으로 {seats_r}석만 확보하고, 창가 1인 카운터석 6석 + 2인 테이블 2개(4석)로 구성, 2인 테이블은 붙여 오후(14~17시) 소규모 미팅에 대응.",
         'evidence': f"합산 주말 {comb['주중주말비중_%']['주말']}% vs 중앙값 {med['주말비중_%']}%; 객단가 {comb['객단가_원']:,}원 vs {med['객단가_원']:,}원; 합산 14~17시 {comb['시간대비중_%']['14~17']}% ({S_SALES}; {S_SC}); 좌석 계산은 assumptions 참조"},
        {'zone': ZONES[4][0], 'area_ratio_pct': 5, 'area_m2_assumed': round(total_area_r * 0.05, 1),
         'why': '반죽·원재료 보관은 오픈키친 내 냉장 설비로 상당 부분 흡수, 백오피스는 최소화(가정).',
         'evidence': '데이터 없음(설계 가정)'},
    ],
    'timeline': [
        {'time': '06:30~11:00 출근·아침', 'share_basis': f"합산 매출 {comb['시간대비중_%']['06~11']}%, 유동인구 {flp['시간대비중_%']['06~11']}%(최다)",
         'scenario': '06:30 오픈(가정), 1차 굽기 완료 상태로 시작. 그랩앤고 진열대에 크루아상·샌드위치·커피 세트 집중, 계산대 2레인 + 모바일 픽업 선반 가동, 좌석은 창가 카운터석만 개방 느낌으로 조명 밝게.', 'source': f'{S_SALES}; {S_FLPOP}'},
        {'time': '11:00~14:00 점심 피크', 'share_basis': f"합산 매출 {comb['시간대비중_%']['11~14']}%(최대), 커피 {prof['커피-음료']['시간대비중_%']['11~14']}%",
         'scenario': '커피바 인력 최대 배치, 점심 후 커피+디저트빵 세트. 2차 굽기는 13시 전후 시작해 퇴근 시간대 대비. 좌석 회전 우선(카운터석·2인석).', 'source': S_SALES},
        {'time': '14:00~17:00 오후 미팅·간식', 'share_basis': f"합산 매출 {comb['시간대비중_%']['14~17']}%, 베이커리 {prof['베이커리(제과점)']['시간대비중_%']['14~17']}%",
         'scenario': '2인 테이블 결합 배치로 체류 고객 수용. 조명 색온도를 낮추고 디저트·조각케이크 진열 강화, 오븐 쇼(갓 나온 빵 알림)로 오후 객 유입.', 'source': S_SALES},
        {'time': '17:00~21:00 퇴근길 빵 장보기', 'share_basis': f"베이커리 매출 {prof['베이커리(제과점)']['시간대비중_%']['17~21']}% (커피 {prof['커피-음료']['시간대비중_%']['17~21']}%)",
         'scenario': '2차 굽기 빵을 입구 진열대로 전진 배치, 식빵·식사빵·묶음 포장 중심. 커피바는 축소 운영하고 계산 인력을 빵 계산대로 전환.', 'source': S_SALES},
        {'time': '21:00 마감', 'share_basis': f"합산 21~24시 매출 {comb['시간대비중_%']['21~24']}% vs 유동인구 21~24시 {flp['시간대비중_%']['21~24']}%",
         'scenario': '21시 마감(가정). 유동인구는 남지만 결제로 이어지지 않아 심야 연장 비권장. 마감 30분 전 당일빵 묶음 판매로 폐기 최소화.', 'source': f'{S_SALES}; {S_FLPOP}'},
        {'time': '주말', 'share_basis': f"합산 매출 주말 {comb['주중주말비중_%']['주말']}%, 유동인구 토·일 {flp_we}%, 지하철 주말 평균 = 평일의 {sub_we_ratio*100:.0f}%",
         'scenario': f'평일 대비 축소 인력·생산량(가정). 유동인구 비중({flp_we}%)보다 매출 비중이 낮아 주말 잠재수요가 미흡수 상태 — 주말 한정 브런치 빵 세트로 테스트 후 확대 판단.', 'source': f'{S_SALES}; {S_FLPOP}; {S_SUB}'},
    ],
    'palette': [
        {'name': '크러스트 브라운', 'hex': '#8B5A2B', 'use': '오픈키친 벽·진열대 하부 — 굽는 빵의 색을 공간 주조색으로'},
        {'name': '밀가루 아이보리', 'hex': '#F4EDE1', 'use': '벽·천장 바탕 — 아침 시간대 밝고 깨끗한 인상'},
        {'name': '플랫폼 차콜', 'hex': '#2F3237', 'use': '카운터·사인·금속 프레임 — 역/터미널 인프라 모티프'},
        {'name': '시그널 오렌지', 'hex': '#E0702E', 'use': '갓 구운 빵 알림 사인·픽업 선반 포인트 — 동선 유도'},
        {'name': '세이지 그린', 'hex': '#8FA58A', 'use': '좌석존 패브릭·식물 — 오후 체류 구역의 이완감'},
    ],
    'materials': [
        {'material': '테라조(밝은 아이보리 베이스) 바닥', 'reason': '아침·점심 피크 고회전 동선의 내구성과 청소 용이성'},
        {'material': '오크 원목 진열대·카운터석 상판', 'reason': '빵과 어울리는 따뜻한 질감, 40~60대 고객에게 친숙한 톤'},
        {'material': '유리 파티션 오픈키친 + 스테인리스 작업대', 'reason': '굽는 과정 노출로 커피 단독 매장과 차별화, 위생 신뢰'},
        {'material': '차콜 분체도장 철재 프레임·사인', 'reason': '역세권 인프라(플랫폼) 모티프, 그랩앤고 동선 사인 가독성'},
        {'material': '조명: 아침 4000K 고조도 → 14시 이후 3000K 웜 디밍, 진열대 고연색(CRI 90+) 스팟', 'reason': '시간대별 시나리오(회전→체류→퇴근 장보기)에 맞춘 무드 전환, 빵 색감 표현'},
    ],
    'assumptions': [
        {'item': '신규 매장 일 거래건수', 'value': f"{calc['신규매장_일거래_가정']}건/일",
         'formula': f"베이커리 분기거래 {int(bk_cnt):,}건 ÷ 점포 {int(bk_n)}곳 ÷ {DAYS_Q2}일 ({calc['베이커리_점포당_일거래']}) + 커피 분기거래 {int(cf_cnt):,}건 ÷ 점포 {int(cf_n)}곳 ÷ {DAYS_Q2}일 ({calc['커피_점포당_일거래']})",
         'basis': '가정: 복합매장이 두 업종의 점포당 평균 거래를 각각 확보', 'source': f'{S_SALES}; {S_STORE}'},
        {'item': '평일 일 거래건수', 'value': f"{calc['평일_일거래']}건/일",
         'formula': f"일 거래 × {DAYS_Q2}일 × 주중 매출비중 {comb['주중주말비중_%']['주중']}% ÷ 평일 {WEEKDAYS_Q2}일",
         'basis': '가정: 거래건수 주중 비중 = 매출 주중 비중, 2분기 평일 65일(공휴일 미반영)', 'source': S_SALES},
        {'item': '평일 피크 시간당 거래(11~14시)', 'value': f"{calc['피크_시간당거래(11~14)']}건/시간",
         'formula': f"평일 일 거래 × 11~14시 매출비중 {comb['시간대비중_%']['11~14']}% ÷ 3시간",
         'basis': '가정: 시간대 거래 비중 = 시간대 매출 비중', 'source': S_SALES},
        {'item': '좌석 수', 'value': f"{seats_r}석 (계산값 {calc['필요좌석_계산값']}석)",
         'formula': f"피크 시간당 거래 × 매장취식률 {EATIN} × 거래당 인원 {PARTY} × 체류 {STAY}시간 ÷ 점유효율 {OCC}",
         'basis': '가정: 매장취식 35%·1.5인·36분 체류·점유효율 85% — 오피스형 테이크아웃 상권 전제, 공공데이터 없음', 'source': '설계 가정(입력 거래 수치는 VwsmTrdarSelngQq 20262)'},
        {'item': '총 면적', 'value': f"{total_area_r}㎡ (약 {calc['총면적_가정_평']}평)",
         'formula': f"좌석 {seats_r}석 × 1석당 {SEAT_M2}㎡ = {calc['좌석면적_m2']}㎡ ÷ 좌석존 비중 30% = {calc['총면적_계산값_m2']}㎡ → 5㎡ 단위 반올림",
         'basis': '가정: 1석당 1.6㎡(통로 포함), 존 비율은 zones 참조. 임대료 공공데이터 없음 → 면적별 임차료는 손익 단계에서 DART 매출 대비 임차료 비율로 추정', 'source': '설계 가정'},
        {'item': '좌석·면적 민감도', 'value': '; '.join(f"취식률 {int(e*100)}% → {peak_hr_tx*e*PARTY*STAY/OCC:.1f}석·{peak_hr_tx*e*PARTY*STAY/OCC*SEAT_M2/0.30:.0f}㎡" for e in (0.25, 0.35, 0.50)),
         'formula': '좌석 = 피크 시간당 거래 × 취식률 × 1.5인 × 0.6시간 ÷ 0.85; 면적 = 좌석 × 1.6㎡ ÷ 0.30',
         'basis': '가정: 매장취식률이 좌석·면적의 최대 변수. 55㎡는 피크 수요 기준 최소 규모이며, 실제 임차 가능 면적과 임대료(데이터 없음)에 따라 조정', 'source': '설계 가정'},
        {'item': '존 면적 비율', 'value': '오픈키친 30 / 진열·계산 22 / 커피바 13 / 좌석 30 / 백오피스 5 (%)',
         'formula': '정성 배분(zones.why의 근거 수치 기반)', 'basis': '가정', 'source': '설계 가정'},
        {'item': '운영시간', 'value': '06:30~21:00 (주 7일, 주말 축소 인력)',
         'formula': f"06~11시 합산매출 {comb['시간대비중_%']['06~11']}% 확보 + 21~24시 {comb['시간대비중_%']['21~24']}%·00~06시 {comb['시간대비중_%']['00~06(잔차)']}%는 제외",
         'basis': '가정', 'source': S_SALES},
        {'item': '주의', 'value': '상주·직장인구는 원천에서 값이 동결(상주 20234 이후, 직장 20244 이후)돼 규모 비교용으로만 사용, 증감 판단에는 미사용',
         'formula': '-', 'basis': 'location.json method.한계', 'source': f'{S_REPOP}; {S_WRC}'},
        {'item': '데이터 없음', 'value': '임대료, 실제 점포 면적·좌석 수 벤치마크, 아파트·소득소비 데이터(서울시 API 500 오류로 미수집)',
         'formula': '-', 'basis': '지어내지 않음', 'source': 'location.json method.한계'},
    ],
    'evidence': [],
}

E = out['evidence']
def ev(claim, number, source):
    E.append({'claim': claim, 'number': number, 'source': source})

ev('주중 중심 상권', f"합산 매출 주중 {comb['주중주말비중_%']['주중']}% / 주말 {comb['주중주말비중_%']['주말']}% (176상권 주말 중앙값 {med['주말비중_%']}%)", f'{S_SALES}; {S_SC}')
ev('아침 수요가 강함', f"합산 06~11시 {comb['시간대비중_%']['06~11']}% (중앙값 {med['오전비중_%']}%), 유동인구 06~11시 {flp['시간대비중_%']['06~11']}%", f'{S_SALES}; {S_SC}; {S_FLPOP}')
ev('점심 피크는 커피', f"커피 11~14시 {prof['커피-음료']['시간대비중_%']['11~14']}%, 합산 11~14시 {comb['시간대비중_%']['11~14']}%", S_SALES)
ev('퇴근 시간대는 베이커리', f"베이커리 17~21시 {prof['베이커리(제과점)']['시간대비중_%']['17~21']}% vs 커피 {prof['커피-음료']['시간대비중_%']['17~21']}%", S_SALES)
ev('베이커리 고객은 여성·중장년', f"베이커리 여성 {prof['베이커리(제과점)']['성별비중_%']['여성']}%, 40대 이상 {bk_4060}%, 60대 이상 {prof['베이커리(제과점)']['연령비중_%']['60대이상']}%", S_SALES)
ev('커피 고객은 30~40대·남성 우위', f"커피 30~40대 {cf_3040}%, 남성 {prof['커피-음료']['성별비중_%']['남성']}%", S_SALES)
ev('객단가', f"베이커리 {bk_atv:,.0f}원, 커피 {cf_atv:,.0f}원, 합산 {comb['객단가_원']:,}원 (중앙값 {med['객단가_원']:,}원)", f'{S_SALES}; {S_SC}')
ev('2030 비중은 중앙값 이하', f"합산 2030 {cand['지표']['고객구성_합산(제과+커피, 20262)']['2030비중_%']}% (중앙값 {med['2030비중_%']}%)", f'{S_SALES}; {S_SC}')
ev('직장인구 > 상주인구', f"직장 {int(wrc['TOT_WRC_POPLTN_CO']):,}명 vs 상주 {int(rep['TOT_REPOP_CO']):,}명 ({wrc_rep_ratio:.1f}배), 상주 가구 {int(rep['TOT_HSHLD_CO']):,}·아파트 가구 {int(rep['APT_HSHLD_CO'])}", f'{S_WRC}; {S_REPOP}')
ev('유동인구 규모·성장', f"20262 유동인구 {int(flp['총유동인구']):,}명, 20232 대비 +{cand['지표']['인구']['유동인구_증감률_%']}% (176상권 중앙값 {cand['지표']['인구']['유동인구_증감률_서울176상권중앙값_%']}%)", S_FLPOP + ' (20232·20262)')
ev('유동인구 구성', f"30~40대 {round(flp['연령비중_%']['30'] + flp['연령비중_%']['40'], 1)}%, 여성 {flp['성별비중_%']['여성']}%, 토·일 {flp_we}%", S_FLPOP)
ev('심야 유동은 매출로 전환 안 됨', f"유동인구 21~06시 {flp_late}% vs 합산 매출 21~06시 {sales_late}%", f'{S_FLPOP}; {S_SALES}')
ev('지하철 수요 평일 집중', f"남부터미널(예술의전당)역 일 승하차 평일 평균 {sub_wd_avg:,.0f}명, 주말 평균 {sub_we_avg:,.0f}명, 주간 합계 {sum(v for *_, v in sub):,}명", S_SUB)
ev('집객시설 구성', f"집객시설 {int(fcl['VIATR_FCLTY_CO'])}곳: 버스정거장 {int(fcl['BUS_STTN_CO'])}, 은행 {int(fcl['BANK_CO'])}, 종합병원 {int(fcl['GNRL_HSPTL_CO'])}, 관공서 {int(fcl['PBLOFC_CO'])}, 지하철역 {int(fcl['SUBWAY_STATN_CO'])}, 슈퍼마켓 {int(fcl['SUPMK_CO'])}, 극장 {int(fcl['THEAT_CO'])}, 대학 {int(fcl['UNIV_CO'])}", S_FCL)
ev('베이커리 공급 감소·점포당 수요 증가', f"베이커리 점포 {bk_n0}→{int(bk_n)}곳, 점포당 분기매출 {b_pp:.3f}억원(3년 {b_pp_ch:+.1f}%, 176 중앙값 {b_pp_med:.3f}억원)", f'{S_STORE2}; {S_SALES}')
ev('커피 공급 포화', f"커피 점포 {cf_n0}→{int(cf_n)}곳(프랜차이즈 {int(store['CS100010']['FRC_STOR_CO'])}), 20262 폐업률 {store['CS100010']['CLSBIZ_RT']:.0f}%", S_STORE2)
ev('성숙 상권(생존력 높음)', f"상권변화지표 {IXC['지표']}({IXC['코드']}), 운영 영업개월 평균 {IXC['운영영업개월_평균']:.0f}개월(서울 {IXC['서울_운영영업개월_평균']:.0f}개월)", S_IX)
ev('좌석·면적 산정(가정)', f"평일 피크 시간당 {calc['피크_시간당거래(11~14)']}건 → {seats_r}석, 총 {total_area_r}㎡(약 {calc['총면적_가정_평']}평)", '가정 — 계산식은 assumptions 참조, 입력은 VwsmTrdarSelngQq·VwsmTrdarStorQq 20262')

with open(os.path.join(INT, 'interior.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps(calc, ensure_ascii=False, indent=1))
print('subway', sub)
