import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer

# 패키지 Import 예외 처리 강화
try:
    import google.generativeai as genai
except ImportError:
    st.error("google-generativeai 패키지가 설치되지 않았습니다.")

# 1. 설정 및 변환기
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)
BENEFIT_GU = ['은평구', '서대문구', '중랑구', '성북구', '강북구', '도봉구', '노원구', '동대문구', '강서구', '구로구', '금천구']

def convert_coords(row):
    try:
        lon, lat = transformer.transform(row['lon'], row['lat'])
        return pd.Series([lon, lat])
    except:
        return pd.Series([row['lon'], row['lat']])

st.set_page_config(page_title="서울 & 경기 리얼티 AI", layout="wide")
st.title("📊 역세권 활성화 & AI 상권 융합 분석")

API_KEY = '776274504662736c3132334e5a767861'

@st.cache_data(ttl=3600, show_spinner="데이터 융합 중...")
def load_real_data():
    TIMEOUT = 10
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/VwsmTrdarSelngQq/1/1000/"
    pop_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/VwsmTrdarFlpopQq/1/1000/"
    
    try:
        sales_res = requests.get(sales_url, timeout=TIMEOUT).json()
        raw_sales_df = pd.DataFrame(sales_res['VwsmTrdarSelngQq']['row'])
        
        pop_res = requests.get(pop_url, timeout=TIMEOUT).json()
        pop_df = pd.DataFrame(pop_res['VwsmTrdarFlpopQq']['row'])
        pop_df['TOT_FLPOP_CO'] = pd.to_numeric(pop_df['TOT_FLPOP_CO'], errors='coerce').fillna(0)
        pop_summary = pop_df.groupby('TRDAR_CD')['TOT_FLPOP_CO'].mean().reset_index()
        pop_summary.rename(columns={'TOT_FLPOP_CO': '유동인구'}, inplace=True)
    except Exception as e:
        st.warning(f"데이터 연동 지연으로 일부 기능이 제한될 수 있습니다. ({e})")
        return None

    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].copy()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    area_df = pd.read_csv(csv_path, encoding='cp949') if os.path.exists(csv_path) else pd.DataFrame()
    
    area_df.rename(columns={'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat', '상권_코드_명': '상권명', '자치구_명': 'GU_NM'}, inplace=True, errors='ignore')
    
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
    
    return merged_df

df = load_real_data()

if df is not None:
    with st.sidebar:
        st.header("🔍 분석 필터")
        benefit_only = st.toggle("✨ 역세권 수혜 지역만 보기", value=False)
        industry_filter = st.multiselect("업종", options=['커피-음료', '제과점'], default=['커피-음료', '제과점'])
        
        filtered_df = df[df['업종명'].isin(industry_filter)].copy()
        if benefit_only:
            filtered_df = filtered_df[filtered_df['is_benefit_zone']]
        
        if not filtered_df.empty:
            selected_district = st.selectbox("상권 선택", sorted(filtered_df['상권명'].unique()))
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
            st.metric("월 유동인구", f"{int(selected_data['유동인구']):,}명")
        else:
            selected_district = None

    if selected_district:
        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer('ColumnLayer', filtered_df, get_position='[lon, lat]', get_elevation='당월_매출액', elevation_scale=0.05, radius=200, get_fill_color='[255, 165, 0, 160]', pickable=True)],
            initial_view_state=pdk.ViewState(latitude=selected_data['lat'], longitude=selected_data['lon'], zoom=14, pitch=45)
        ))
        
        st.divider()
        st.subheader("🤖 융합 데이터 기반 AI 비즈니스 리포트")
        
        if st.button("AI 리포트 생성"):
            try:
                # 💡 핵심 수정: secrets 확인 로직 강화
                if "GEMINI_API_KEY" not in st.secrets:
                    st.error("Streamlit Secrets에 'GEMINI_API_KEY'가 설정되지 않았습니다.")
                else:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    with st.spinner('인구-매출 융합 분석 중...'):
                        prompt = f"""
                        서울시 창업 전문가로서 {selected_district}의 {selected_data['업종명']} 상권을 분석해줘.
                        - 매출: {int(selected_data['당월_매출액']):,}원 / 유동인구: {int(selected_data['유동인구']):,}명
                        - {selected_data['GU_NM']} 정책 반영 필수. 유동인구 대비 매출 효율성을 진단하고 전략을 세워줘.
                        """
                        response = model.generate_content(prompt)
                        st.info(response.text)
            except Exception as e:
                st.error(f"AI 호출 중 실제 에러 발생: {e}")

    st.dataframe(filtered_df[['상권명', 'GU_NM', '당월_매출액', '유동인구', 'is_benefit_zone']])
