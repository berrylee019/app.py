import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer
from google import genai  # 최신 라이브러리로 교체

# 변환기 설정
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)

def convert_coords(row):
    try:
        lon, lat = transformer.transform(row['lon'], row['lat'])
        return pd.Series([lon, lat])
    except:
        return pd.Series([row['lon'], row['lat']])

# 1. 페이지 설정
st.set_page_config(page_title="서울 리얼티 AI - 데이터 센터", layout="wide")

st.title("📊 서울시 상권 분석 & AI 컨설팅")
st.caption("Seoul-Realty AI | 2026 서울시 빅데이터 활용 경진대회 출품작")

API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelngQq'

@st.cache_data(ttl=3600)
def load_real_data():
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/100/"
    sales_res = requests.get(sales_url).json()
    raw_sales_df = pd.DataFrame(sales_res[SERVICE]['row'])

    # 커피전문점 OR 제과점 합집합 필터링 (최대 25개)
    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].head(25)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    
    try:
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except:
        area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    area_df = area_df[['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값']]
    area_df.rename(columns={'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat'}, inplace=True)

    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    merged_df[['lon', 'lat']] = merged_df.apply(convert_coords, axis=1)
    
    merged_df['lat'] = pd.to_numeric(merged_df['lat'])
    merged_df['lon'] = pd.to_numeric(merged_df['lon'])
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'], errors='coerce').fillna(0)
    merged_df['당월_매출건수'] = pd.to_numeric(merged_df['THSMON_SELNG_CO'], errors='coerce').fillna(0)
    merged_df['상권명'] = merged_df['상권_코드_명']
    merged_df['업종명'] = merged_df['SVC_INDUTY_CD_NM']

    return merged_df

df = load_real_data()

if df is not None and not df.empty:
    st.success(f"✅ 카페 & 베이커리 통합 데이터 분석 중! (분석 대상: {len(df)}개 상권)")
    
    with st.sidebar:
        st.header("🔍 분석 조건 설정")
        industry_filter = st.multiselect("업종 선택", options=df['업종명'].unique(), default=df['업종명'].unique())
        filtered_df = df[df['업종명'].isin(industry_filter)]
        
        if not filtered_df.empty:
            selected_district = st.selectbox("분석 상권 선택", filtered_df['상권명'].unique())
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")

    # 3D 지도
    st.pydeck_chart(pdk.Deck(
        layers=[pdk.Layer('ColumnLayer', filtered_df, get_position='[lon, lat]', get_elevation='당월_매출액', 
                          elevation_scale=0.00002, radius=500, get_fill_color='[255, 50, 50, 200]', pickable=True)],
        initial_view_state=pdk.ViewState(latitude=37.5665, longitude=126.9780, zoom=11, pitch=45),
        tooltip={"text": "상권명: {상권명}\n매출액: {당월_매출액}원"}
    ))
    
    st.subheader("📋 데이터 상세 보기")
    # 경고 해결: use_container_width=True를 width='stretch'로 변경
    st.dataframe(filtered_df[['상권명', '업종명', '당월_매출액', '당월_매출건수']], width='stretch')

    # 최신 AI 분석 로직
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    
    st.divider()
    st.subheader(f"🤖 AI 컨설턴트 분석")
    if st.button("AI 분석 리포트 생성"):
        with st.spinner('분석 중...'):
            prompt = f"{selected_district}의 {selected_data['업종명']} 상권 매출액 {selected_data['당월_매출액']}원을 기반으로 분석해줘."
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            st.write(response.text)
