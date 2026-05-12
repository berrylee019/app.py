import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer
import google.generativeai as genai

# 1. 변환기 및 정책 데이터 설정
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)
BENEFIT_GU = ['은평구', '서대문구', '중랑구', '성북구', '강북구', '도봉구', '노원구', '동대문구', '강서구', '구로구', '금천구']

def convert_coords(row):
    try:
        # csv에서 읽어온 컬럼명이 다를 수 있으므로 안전하게 처리
        lon = row.get('lon', row.get('엑스좌표_값', 0))
        lat = row.get('lat', row.get('와이좌표_값', 0))
        new_lon, new_lat = transformer.transform(lon, lat)
        return pd.Series([new_lon, new_lat])
    except:
        return pd.Series([row.get('lon', 0), row.get('lat', 0)])

# 2. 페이지 설정
st.set_page_config(page_title="서울 상권 융합분석 AI", layout="wide")
st.title("📊 비즈니스 큐브(Biz-Cube) AI")
st.caption("Biz-Cube AI | 위치+인구+매출+정책 데이터 결합 버전")

# API 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE_SALES = 'VwsmTrdarSelngQq'
SERVICE_POP = 'VwsmTrdarFlpopQq'

@st.cache_data(ttl=3600, show_spinner="서울시 공공데이터 및 인구 데이터 융합 중...")
def load_real_data():
    TIMEOUT = 10
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE_SALES}/1/1000/"
    pop_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE_POP}/1/1000/"
    
    try:
        # A. 매출 데이터 로드
        sales_res = requests.get(sales_url, timeout=TIMEOUT).json()
        if SERVICE_SALES not in sales_res: raise ValueError("매출 API 응답 이상")
        raw_sales_df = pd.DataFrame(sales_res[SERVICE_SALES]['row'])
        
        # B. 유동인구 데이터 로드
        pop_res = requests.get(pop_url, timeout=TIMEOUT).json()
        if SERVICE_POP not in pop_res:
            pop_summary = pd.DataFrame(columns=['TRDAR_CD', '유동인구'])
        else:
            pop_df = pd.DataFrame(pop_res[SERVICE_POP]['row'])
            pop_df['TOT_FLPOP_CO'] = pd.to_numeric(pop_df['TOT_FLPOP_CO'], errors='coerce').fillna(0)
            pop_summary = pop_df.groupby('TRDAR_CD')['TOT_FLPOP_CO'].mean().reset_index()
            pop_summary.rename(columns={'TOT_FLPOP_CO': '유동인구'}, inplace=True)
            
    except Exception as e:
        st.error(f"실시간 데이터 로드 실패: {e}")
        return pd.DataFrame() # 빈 데이터프레임 반환하여 앱 중단 방지

    # 업종 필터
    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].copy()

    # 위치 데이터 로드
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    try:
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except:
        try:
            area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
        except:
            area_df = pd.DataFrame(columns=['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값', '자치구_명'])

    # 컬럼 정리 및 병합
    area_df.rename(columns={'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat', '상권_코드_명': '상권명', '자치구_명': 'GU_NM'}, inplace=True, errors='ignore')
    if 'GU_NM' not in area_df.columns: area_df['GU_NM'] = "서울 지역"

    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    pop_summary['TRDAR_CD'] = pop_summary['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    merged_df = pd.merge(merged_df, pop_summary, on='TRDAR_CD', how='left')
    
    merged_df[['lon', 'lat']] = merged_df.apply(convert_coords, axis=1)
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'], errors='coerce').fillna(0)
    merged_df['유동인구'] = merged_df['유동인구'].fillna(0)
    merged_df['업종명'] = merged_df['SVC_INDUTY_CD_NM']

    def check_benefit(row):
        target_text = str(row.get('GU_NM', '')) + " " + str(row.get('상권명', ''))
        return any(gu.replace('구', '') in target_text for gu in BENEFIT_GU)
    merged_df['is_benefit_zone'] = merged_df.apply(check_benefit, axis=1)

    # 하남 가상 데이터 (컬럼 구조 완전 일치)
    misa_mock = pd.DataFrame({
        'TRDAR_CD': ['MISA01'], '상권명': ['미사역 중심상권'], 'GU_NM': ['하남시'],
        'lon': [127.1925], 'lat': [37.5610], '당월_매출액': [120000000], '유동인구': [45000],
        'is_benefit_zone': [False], '업종명': ['커피-음료'], 'SVC_INDUTY_CD_NM': ['커피-음료']
    })

    return pd.concat([merged_df, misa_mock], ignore_index=True)

df = load_real_data()

if df is not None and not df.empty:
    with st.sidebar:
        st.header("🔍 분석 및 정책 필터")
        benefit_only = st.toggle("✨ 역세권 수혜 지역만 보기", value=False)
        industry_filter = st.multiselect("업종 선택", options=['커피-음료', '제과점'], default=['커피-음료', '제과점'])
        
        filtered_df = df[df['업종명'].isin(industry_filter)].copy()
        if benefit_only:
            filtered_df = filtered_df[filtered_df['is_benefit_zone'] == True]
        
        if not filtered_df.empty:
            selected_district = st.selectbox("상세 분석 상권", sorted(filtered_df['상권명'].unique()))
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
            st.metric("월 평균 유동인구", f"{int(selected_data['유동인구']):,}명", delta="인구 데이터 결합")
            
            def assign_color(row):
                if row['is_benefit_zone']: return [255, 215, 0, 230] 
                return [255, 50, 50, 160] if row['업종명'] == '커피-음료' else [255, 165, 0, 160]
            filtered_df['color'] = filtered_df.apply(assign_color, axis=1)
        else:
            selected_district = None

    if selected_district:
        # 3. 3D 시각화
        initial_lat, initial_lon = selected_data['lat'], selected_data['lon']
        layer = pdk.Layer(
            'ColumnLayer', filtered_df, get_position='[lon, lat]',
            get_elevation='당월_매출액', elevation_scale=0.00005,
            radius=250, get_fill_color='color', pickable=True, auto_highlight=True
        )
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(latitude=initial_lat, longitude=initial_lon, zoom=12, pitch=45),
            tooltip={"text": "상권명: {상권명} ({GU_NM})\n매출액: {당월_매출액}원\n유동인구: {유동인구}명\n수혜구역: {is_benefit_zone}"}
        ))
        
        st.divider()
        st.subheader(" 융합 데이터 기반 AI 비즈니스 리포트")
        if st.button("AI 융합 분석 리포트 생성"):
            if "GEMINI_API_KEY" not in st.secrets:
                st.error("Secrets에 GEMINI_API_KEY가 없습니다.")
            else:
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    with st.spinner('인구-매출 융합 분석 중...'):
                        prompt = f"{selected_district} {selected_data['업종명']} 분석. 매출 {int(selected_data['당월_매출액'])}원, 유동인구 {int(selected_data['유동인구'])}명. 역세권 정책 기반 전략 제안."
                        response = model.generate_content(prompt)
                        st.chat_message("assistant", avatar="🤖").markdown(response.text)
                except Exception as e:
                    st.error(f"AI 호출 실패: {e}")

        st.subheader("📋 데이터 상세 시트")
        # KeyError 방지를 위해 존재하는 컬럼만 선택
        target_cols = ['상권명', 'GU_NM', '업종명', '당월_매출액', '유동인구', 'is_benefit_zone']
        safe_cols = [c for c in target_cols if c in filtered_df.columns]
        st.dataframe(filtered_df[safe_cols], width='stretch')
else:
    st.error("데이터 로드 중입니다. 잠시만 기다려 주세요.")
