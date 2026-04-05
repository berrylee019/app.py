import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer
import google.generativeai as genai # 다시 안정적인 구형 라이브러리 방식으로 복구

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

# API 및 서비스 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelngQq'

@st.cache_data(ttl=3600)
def load_real_data():
    # 💡 수정 포인트 1: 데이터를 1,000개로 늘려서 제과점 데이터도 안정적으로 확보합니다.
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/1000/"
    try:
        sales_res = requests.get(sales_url).json()
        raw_sales_df = pd.DataFrame(sales_res[SERVICE]['row'])
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None

    # 커피전문점 OR 제과점 합집합 필터링
    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)]

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
        
        # 💡 수정 포인트 2: 선택지에 '커피-음료'와 '제과점'을 명시적으로 고정해 둡니다.
        target_industries = ['커피-음료', '제과점']
        industry_filter = st.multiselect("업종 선택", options=target_industries, default=target_industries)
        
        filtered_df = df[df['업종명'].isin(industry_filter)]
        
        if not filtered_df.empty:
            selected_district = st.selectbox("분석 상권 선택", filtered_df['상권명'].unique())
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
        else:
            st.warning("선택한 업종에 대한 데이터가 존재하지 않습니다.")

    # 3D 지도
    layer = pdk.Layer(
        'ColumnLayer', 
        filtered_df, 
        get_position='[lon, lat]', 
        get_elevation='당월_매출액', 
        elevation_scale=0.00002, 
        radius=500, 
        get_fill_color='[255, 50, 50, 200]', 
        pickable=True,
        auto_highlight=True
    )
    
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=37.5665, longitude=126.9780, zoom=11, pitch=45),
        tooltip={"text": "상권명: {상권명}\n업종: {업종명}\n매출액: {당월_매출액}원"}
    ))
    
    st.subheader("📋 데이터 상세 보기")
    # 최신 규격 반영: width='stretch'
    st.dataframe(filtered_df[['상권명', '업종명', '당월_매출액', '당월_매출건수']], width='stretch')

    # AI 설정
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"]) # Secrets의 이름과 맞춤
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        st.divider()
        st.subheader(f"🤖 AI 컨설턴트 분석")
        
        if not filtered_df.empty and st.button("AI 분석 리포트 생성"):
            with st.spinner('전략을 세우는 중...'):
                prompt = f"{selected_district}의 {selected_data['업종명']} 업종 매출 {int(selected_data['당월_매출액']):,}원을 바탕으로 짧고 강렬한 사업 전략을 제안해줘."
                response = model.generate_content(prompt)
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(response.text)
    except Exception as e:
        st.error(f"AI 설정 오류: Secrets에 'GEMINI_API_KEY'가 있는지 확인해주세요.")

else:
    st.error("데이터를 불러올 수 없습니다. API 서버 상태를 확인해주세요.")
