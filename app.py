import streamlit as st
import requests
import pandas as pd

# 페이지 설정
st.set_page_config(page_title="서울 리얼티 AI - 데이터 센터", layout="wide")

st.title("📊 서울시 상권 매출 데이터 실시간 수집기")
st.info("서울시 열린데이터광장 API를 통해 상권-추정매출 데이터를 1초 만에 수집합니다.")

# 1. 인증키 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelng'

# 2. 데이터 수집 함수 (캐싱 적용으로 속도 업!)
@st.cache_data(ttl=3600) # 1시간 동안 데이터 유지
def fetch_seoul_sales():
    # 테스트를 위해 상위 100개 데이터만 먼저 긁어옵니다.
    url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/100/"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if SERVICE in data:
            df = pd.DataFrame(data[SERVICE]['row'])
            # 보기 편하게 컬럼명 한글화 (주요 항목)
            rename_dict = {
                'TRDAR_CD_NM': '상권명',
                'SVC_INDUTY_CD_NM': '업종명',
                'THSMON_SELNG_AMT': '당월_매출액',
                'THSMON_SELNG_CO': '당월_매출건수',
                'STDR_QU_CD': '분기'
            }
            return df.rename(columns=rename_dict)
        else:
            return None
    except Exception as e:
        st.error(f"API 연결 실패: {e}")
        return None

# 3. 화면 UI 구성
if st.button('🚀 데이터 새로고침'):
    st.cache_data.clear()
    st.rerun()

with st.spinner('서울시 데이터를 가져오는 중...'):
    df = fetch_seoul_sales()

if df is not None:
    st.success(f"총 {len(df)}개의 최신 상권 데이터를 성공적으로 불러왔습니다.")
    
    # 데이터 출력 (검색 및 필터링 가능)
    st.dataframe(df, use_container_width=True)
    
    # 간단한 요약 통계
    col1, col2 = st.columns(2)
    with col1:
        st.metric("최고 매출액 상권", df.loc[df['당월_매출액'].idxmax(), '상권명'])
    with col2:
        avg_sales = int(df['당월_매출액'].mean())
        st.metric("평균 매출액", f"{avg_sales:,}원")
else:
    st.warning("데이터를 불러올 수 없습니다. API 키나 네트워크 상태를 확인해주세요.")

st.divider()
st.caption("Seoul-Realty AI | 2026 서울시 빅데이터 활용 경진대회 출품 준비 중")