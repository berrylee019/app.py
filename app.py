import streamlit as st
import requests
import pandas as pd

API_KEY = '776274504662736c3132334e5a767861'
# 서비스명을 '상권-유동인구'로 변경해서 테스트
TEST_SERVICE = 'VwsmTrdarFlpop' 

st.title("🚑 긴급 서버 상태 진단")

url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{TEST_SERVICE}/1/5/"
st.write(f"테스트 호출 URL: `{url}`")

try:
    response = requests.get(url)
    data = response.json()
    
    if TEST_SERVICE in data:
        st.success("✅ 유동인구 데이터는 정상입니다! '추정매출' 서버만 문제인 것으로 보입니다.")
        st.dataframe(pd.DataFrame(data[TEST_SERVICE]['row']))
    else:
        st.error(f"❌ 이 서비스도 에러가 납니다: {data.get('RESULT', {}).get('MESSAGE', '서버 응답 없음')}")
        st.info("이 경우 서울시 API 서버 전체가 현재 점검 중일 확률이 99%입니다.")
except Exception as e:
    st.error(f"연결 실패: {e}")
