import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

# 1. 페이지 설정
st.set_page_config(page_title="서울 리얼티 AI - 데이터 센터", layout="wide")

st.title("📊 서울시 상권 분석 & AI 컨설팅")
st.caption("Seoul-Realty AI | 2026 서울시 빅데이터 활용 경진대회 출품작")

# 2. 인증키 및 수정된 서비스명 적용
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelngQq'  # 알려주신 정답 서비스명 적용!

# 3. 실시간 데이터 수집 함수
@st.cache_data(ttl=3600)  # 1시간 동안 캐싱하여 속도 최적화
def load_real_data():
    # JSON 형식으로 상위 50개 데이터를 땡겨옵니다.
    url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/50/"
    
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if SERVICE in data:
            df = pd.DataFrame(data[SERVICE]['row'])
            
            # 지도 시각화를 위해 가상 좌표(lat, lon) 매핑 
            # (실제 상권 마스터 데이터와 결합하기 전 임시 좌표 부여)
            df['lat'] = 37.5665 + (pd.to_numeric(df['THSMON_SELNG_AMT']).rank(pct=True) - 0.5) * 0.1
            df['lon'] = 126.9780 + (pd.to_numeric(df['THSMON_SELNG_CO']).rank(pct=True) - 0.5) * 0.1
            
            # 주요 컬럼 한글화 및 타입 변환
            df['당월_매출액'] = pd.to_numeric(df['THSMON_SELNG_AMT'])
            df['당월_매출건수'] = pd.to_numeric(df['THSMON_SELNG_CO'])
            df['상권명'] = df['TRDAR_CD_NM']
            df['업종명'] = df['SVC_INDUTY_CD_NM']
            
            return df
        else:
            return None
    except Exception as e:
        return None

# 데이터 로드
df = load_real_data()

# 4. 화면 UI 및 시각화
if df is not None:
    st.success(f"✅ 서울시 실시간 상권 데이터 연동 성공! (총 {len(df)}개 데이터)")
    
    # 사이드바
    with st.sidebar:
        st.header("🔍 분석 조건 설정")
        selected_district = st.selectbox("분석할 상권을 선택하세요", df['상권명'].unique())
        selected_data = df[df['상권명'] == selected_district].iloc[0]
        
        st.divider()
        st.subheader(f"📌 {selected_district} 요약")
        st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
        st.metric("추정 매출건수", f"{int(selected_data['당월_매출건수']):,}건")

    # 3D 지도 레이어 설정
    layer = pdk.Layer(
        'ColumnLayer',
        df,
        get_position='[lon, lat]',
        get_elevation='당월_매출액',
        elevation_scale=0.00002,      # 👈 기존 0.0005에서 대폭 축소 (높이 낮춤)
        radius=1000,                  # 👈 기존 200에서 1000으로 변경 (기둥을 5배 굵게)
        get_fill_color='[255, 50, 50, 200]',  # 붉은색 기둥
        pickable=True,
        auto_highlight=True
    )

    view_state = pdk.ViewState(
        latitude=37.5665,
        longitude=126.9780,
        zoom=11,
        pitch=45
    )

    st.subheader("📍 서울시 실시간 상권 매출 현황 (3D Map)")
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "상권명: {상권명}\n업종: {업종명}\n매출액: {당월_매출액}원"}
    ))
    
    st.subheader("📋 데이터 상세 보기")
    st.dataframe(df[['상권명', '업종명', '당월_매출액', '당월_매출건수']], use_container_width=True)

else:
    st.error("😭 여전히 데이터를 불러올 수 없습니다. 서비스명 오탈자를 다시 확인해주세요.")
    st.info("임시 URL로 브라우저에서 직접 접속이 되는지 확인해보세요.")
