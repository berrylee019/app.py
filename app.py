import streamlit as st
import requests
import pandas as pd
import numpy as np

# 1. 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelng'

st.set_page_config(page_title="서울 리얼티 AI - 개발 모드", layout="wide")
st.title("🏙️ 서울 리얼티 AI (데이터 로딩 모드)")

# 2. 가상 데이터 생성 함수 (서버 장애 대비용)
def get_dummy_data():
    data = {
        '상권명': ['강남역', '홍대입구역', '명동거리', '가로수길', '이태원'],
        '업종명': ['한식음식점', '커피-음료', '의류소매', '양식음식점', '일식음식점'],
        '당월_매출액': [150000000, 120000000, 200000000, 95000000, 80000000],
        '당월_매출건수': [5000, 8000, 3000, 2500, 1800],
        '매력도_점수': [95.5, 92.1, 88.4, 85.0, 79.2]
    }
    return pd.DataFrame(data)

# 3. 데이터 로드 로직 (API 호출 시도 -> 실패 시 가상 데이터)
@st.cache_data(ttl=60)
def load_data():
    url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/100/"
    try:
        response = requests.get(url, timeout=3) # 3초 안에 응답 없으면 패스
        data = response.json()
        if SERVICE in data:
            df = pd.DataFrame(data[SERVICE]['row'])
            # 실제 데이터 컬럼명 매핑 (나중에 서버 살아나면 바로 적용되게)
            return df.rename(columns={'TRDAR_CD_NM': '상권명', 'SVC_INDUTY_CD_NM': '업종명', 'THSMON_SELNG_AMT': '당월_매출액'})
        else:
            return None
    except:
        return None

# --- 메인 실행부 ---
df = load_data()

if df is not None:
    st.success("✅ 서울시 실시간 데이터 연동 성공!")
else:
    st.warning("⚠️ 서울시 API 서버 점검 중입니다. 개발용 가상 데이터를 로드합니다.")
    df = get_dummy_data()

st.dataframe(df, use_container_width=True)

# 4. 시각화 미리 맛보기 (지도 대신 간단한 차트)
st.subheader("📊 상권별 매출액 비교 (샘플)")
st.bar_chart(df.set_index('상권명')['당월_매출액'])
