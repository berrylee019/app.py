import streamlit as st
import pandas as pd
import pydeck as pdk

# 1. 페이지 설정
st.set_page_config(page_title="서울 리얼티 AI - 데이터 센터", layout="wide", initial_sidebar_state="expanded")

st.title("📊 서울시 상권 분석 & AI 컨설팅")
st.caption("Seoul-Realty AI | 2026 서울시 빅데이터 활용 경진대회 출품작")

# 2. 가상 데이터 생성 (위도, 경도 추가)
def get_dummy_data():
    data = {
        '상권명': ['강남역', '홍대입구역', '명동거리', '가로수길', '이태원'],
        '업종명': ['한식음식점', '커피-음료', '의류소매', '양식음식점', '일식음식점'],
        '당월_매출액': [150000000, 120000000, 200000000, 95000000, 80000000],
        '매력도_점수': [95.5, 92.1, 88.4, 85.0, 79.2],
        # 서울 주요 상권 좌표
        'lat': [37.4979, 37.5565, 37.5634, 37.5204, 37.5345],
        'lon': [127.0276, 126.9244, 126.9860, 127.0230, 126.9942]
    }
    return pd.DataFrame(data)

df = get_dummy_data()

# 3. 사이드바 구성
with st.sidebar:
    st.header("🔍 분석 조건 설정")
    selected_district = st.selectbox("분석할 상권을 선택하세요", df['상권명'].unique())
    selected_data = df[df['상권명'] == selected_district].iloc[0]
    
    st.divider()
    st.subheader(f"📌 {selected_district} 분석 요약")
    st.metric("추정 매출액", f"{selected_data['당월_매출액']:,}원")
    st.metric("상권 매력도", f"{selected_data['매력도_점수']}점")

# 4. 메인 화면 - 3D 지도 시각화
st.subheader("📍 서울시 주요 상권 매력도 (3D Map)")
st.info("기둥의 높이는 '당월 매출액'을, 색상의 붉은 정도는 '매력도 점수'를 나타냅니다.")

# Pydeck을 이용한 3D 지도 레이어 설정
layer = pdk.Layer(
    'ColumnLayer', # 3D 기둥 레이어
    df,
    get_position='[lon, lat]',
    get_elevation='당월_매출액', # 기둥 높이
    elevation_scale=0.005,      # 높이 스케일 조절
    radius=150,                 # 기둥 반경
    get_fill_color='[매력도_점수 * 2.5, 50, 150, 200]', # 색상 (매력도가 높을수록 붉어짐)
    pickable=True,              # 마우스 오버 시 툴팁 표시 여부
    auto_highlight=True
)

# 지도 중심점 설정 (서울 중심)
view_state = pdk.ViewState(
    latitude=37.53,
    longitude=126.98,
    zoom=11,
    pitch=45, # 지도 기울기 (3D 효과)
    bearing=0
)

# 지도 렌더링
st.pydeck_chart(pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip={"text": "상권명: {상권명}\n업종: {업종명}\n매출액: {당월_매출액}원"}
))

# 5. 하단 데이터 테이블
st.subheader("📋 전체 상권 데이터 데이터프레임")
st.dataframe(df, use_container_width=True)
