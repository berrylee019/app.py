import streamlit as st
import requests
import pandas as pd
import json

st.set_page_config(page_title="서울 리얼티 AI - 디버깅", layout="wide")

st.title("🔍 API 연결 상태 정밀 진단")

# 1. 인증키 (형님이 주신 키 그대로 적용)
API_KEY = '776274504662736c3132334e5a767861'
# 서비스명: 상권-추정매출 (대소문자 정확해야 함)
SERVICE = 'VwsmTrdarSelng' 

# 2. 진단 시작
st.subheader("1단계: API 호출 테스트")
url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/5/"
st.write(f"요청 URL: `{url}`")

try:
    response = requests.get(url)
    st.write(f"HTTP 상태 코드: `{response.status_code}`")
    
    # 응답 텍스트 전체 출력 (에러 메시지 확인용)
    raw_data = response.text
    st.subheader("2단계: 서버 응답 원문")
    st.code(raw_data)
    
    # JSON 파싱 시도
    data = response.json()
    
    if SERVICE in data:
        st.success("✅ 데이터 수집 성공!")
        df = pd.DataFrame(data[SERVICE]['row'])
        st.dataframe(df)
    elif "RESULT" in data:
        st.error(f"❌ 서울시 서버 에러 코드: {data['RESULT']['CODE']}")
        st.warning(f"메시지: {data['RESULT']['MESSAGE']}")
        
        if data['RESULT']['CODE'] == 'INFO-100':
            st.info("💡 팁: '인증키가 유효하지 않습니다'가 뜬다면, 발급 직후라 활성화에 10~20분 정도 걸릴 수 있습니다.")
        elif data['RESULT']['CODE'] == 'INFO-200':
            st.info("💡 팁: 해당 서비스명(VwsmTrdarSelng)에 오류가 있거나 데이터가 일시적으로 없는 상태입니다.")

except Exception as e:
    st.error(f"🔥 치명적 오류 발생: {e}")
