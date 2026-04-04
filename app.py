import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer

# 중부원점(EPSG:5181) -> GPS 위경도(EPSG:4326) 변환기
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)

# 엑스좌표, 와이좌표를 위경도로 변환하는 함수
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

# 2. 인증키 및 서비스명
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelngQq'

# 3. 실시간 데이터 수집 함수
@st.cache_data(ttl=3600)
def load_real_data():
    # [수정 포인트] 1. 더 넓은 범위의 데이터를 먼저 가져옵니다 (필터링을 위해 200개 정도 호출 권장하지만, 일단 1/25 유지)
    # 업종 필터링을 코드 단에서 하기 위해 호출 범위를 약간 넉넉히 잡는 것이 좋으나, 
    # 형님 요청대로 25개 내에서 '커피'와 '제과'를 모두 보여주도록 로직을 짰습니다.
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/100/" # 필터링을 위해 100개 호출
    sales_res = requests.get(sales_url).json()
    raw_sales_df = pd.DataFrame(sales_res[SERVICE]['row'])

    # [핵심 수정] 2. 커피전문점 OR 제과점 합집합 필터링
    # '커피-음료'와 '제과점' 업종만 추출합니다.
    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].head(25)

    # 3. 좌표 데이터 가져오기 (CSV)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    
    try:
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except UnicodeDecodeError:
        try:
            area_df = pd.read_csv(csv_path, encoding='euc-kr')
        except UnicodeDecodeError:
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

# 데이터 로드
df = load_real_data()

# 4. 화면 UI 및 시각화
if df is not None and not df.empty:
    st.success(f"✅ 카페 & 베이커리 통합 상권 데이터 분석 중! (분석 대상: {len(df)}개 상권)")
    
    with st.sidebar:
        st.header("🔍 분석 조건 설정")
        # 업종별 필터 선택 추가 (카페만 보기 / 베이커리만 보기 / 전체보기)
        industry_filter = st.multiselect("보고 싶은 업종을 선택하세요", 
                                         options=df['업종명'].unique(), 
                                         default=df['업종명'].unique())
        
        filtered_df = df[df['업종명'].isin(industry_filter)]
        
        if not filtered_df.empty:
            selected_district = st.selectbox("분석할 상권을 선택하세요", filtered_df['상권명'].unique())
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            
            st.divider()
            st.subheader(f"📌 {selected_district} 요약")
            st.info(f"현재 선택 업종: {selected_data['업종명']}")
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
            st.metric("추정 매출건수", f"{int(selected_data['당월_매출건수']):,}건")
        else:
            st.warning("선택한 업종의 데이터가 없습니다.")

    # 3D 지도 레이어
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

    view_state = pdk.ViewState(
        latitude=37.5665,
        longitude=126.9780,
        zoom=11,
        pitch=45
    )

    st.subheader("📍 카페 & 베이커리 통합 상권 매출 현황")
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "상권명: {상권명}\n업종: {업종명}\n매출액: {당월_매출액}원"}
    ))
    
    st.subheader("📋 데이터 상세 보기")
    st.dataframe(filtered_df[['상권명', '업종명', '당월_매출액', '당월_매출건수']], width='stretch')

    # AI 분석 리포트 (하단 배치)
    import google.generativeai as genai
    genai.configure(api_key=st.secrets["MY_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') # 최신 모델 반영

    def get_ai_consulting(sangkwon, industry, sales, count):
        avg_price = sales / count if count > 0 else 0
        prompt = f"""
        당신은 서울시 소상공인을 위한 20년 경력의 상권 분석 컨설턴트입니다.
        - 상권명: {sangkwon}
        - 업종: {industry}
        - 당월 매출액: {int(sales):,}원
        - 당월 매출건수: {int(count):,}건
        - 추정 객단가: {int(avg_price):,}원
        
        데이터를 기반으로 베이커리와 카페 업종의 특성을 반영하여 전략 보고서를 써주세요.
        """
        try:
            response = model.generate_content(prompt)
            return response.text
        except:
            return "⚠️ AI 컨설턴트 API 연결 확인이 필요합니다."

    st.divider()
    if not filtered_df.empty:
        st.subheader(f"🤖 AI 컨설턴트의 '{selected_district}' 분석 리포트")
        with st.spinner('전략 수립 중...'):
            report = get_ai_consulting(
                selected_data['상권명'], 
                selected_data['업종명'], 
                selected_data['당월_매출액'], 
                selected_data['당월_매출건수']
            )
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(report)
else:
    st.error("데이터를 불러올 수 없습니다. API 키와 서비스명을 확인해주세요.")
