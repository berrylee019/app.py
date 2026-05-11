import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer
import google.generativeai as genai

# 1. 변환기 및 정책 데이터 설정
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)

# 규제 완화 수혜 11개 자치구 (공공기여 50% -> 30% 완화 지역)
BENEFIT_GU = ['은평구', '서대문구', '중랑구', '성북구', '강북구', '도봉구', '노원구', '동대문구', '강서구', '구로구', '금천구']

def convert_coords(row):
    try:
        lon, lat = transformer.transform(row['lon'], row['lat'])
        return pd.Series([lon, lat])
    except:
        return pd.Series([row['lon'], row['lat']])

# 2. 페이지 설정
st.set_page_config(page_title="서울 & 경기 리얼티 AI - 정책 분석 센터", layout="wide")

st.title("📊 역세권 직주락 활성화 & AI 상권 분석")
st.caption("Seoul-Realty AI | 2026 서울시 정책(역세권 활성화 운영기준 개정) 반영 버전")

# API 및 서비스 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE = 'VwsmTrdarSelngQq'

@st.cache_data(ttl=3600)
def load_real_data():
    sales_url1 = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1/1000/"
    sales_url2 = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE}/1001/2000/"
    
    try:
        sales_res1 = requests.get(sales_url1).json()
        sales_res2 = requests.get(sales_url2).json()
        
        raw_df1 = pd.DataFrame(sales_res1[SERVICE]['row'])
        raw_df2 = pd.DataFrame(sales_res2[SERVICE]['row'])
        raw_sales_df = pd.concat([raw_df1, raw_df2], ignore_index=True)
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return None

    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].copy()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    
    try:
        # 자치구 정보를 포함하기 위해 엑셀/CSV 구조 확인 필요 (일반적으로 상권 코드 데이터에 자치구가 포함됨)
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except:
        area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # '자치구_명' 컬럼이 있다고 가정 (없을 경우 상권명에서 추출하거나 매핑 필요)
    area_df = area_df[['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값', '자치구_명']]
    area_df.rename(columns={'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat', '자치구_명': 'GU_NM'}, inplace=True)

    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    merged_df[['lon', 'lat']] = merged_df.apply(convert_coords, axis=1)
    
    merged_df['lat'] = pd.to_numeric(merged_df['lat'])
    merged_df['lon'] = pd.to_numeric(merged_df['lon'])
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'], errors='coerce').fillna(0)
    merged_df['상권명'] = merged_df['상권_코드_명']
    merged_df['업종명'] = merged_df['SVC_INDUTY_CD_NM']

    # 수혜 지역 여부 판단 로직
    merged_df['is_benefit_zone'] = merged_df['GU_NM'].isin(BENEFIT_GU)

    # 하남 미사 데이터 (하남은 서울 정책 직접 수혜지는 아니나 비교군으로 유지)
    misa_mock_data = pd.DataFrame({
        'TRDAR_CD': ['MISA01', 'MISA02'],
        'SVC_INDUTY_CD_NM': ['커피-음료', '제과점'],
        '상권명': ['미사역 중심상권', '망월천 수변공원'],
        'lon': [127.1925, 127.1890],
        'lat': [37.5610, 37.5640],
        '당월_매출액': [120000000, 95000000],
        'GU_NM': ['하남시'],
        'is_benefit_zone': False,
        '업종명': ['커피-음료', '제과점']
    })

    final_df = pd.concat([merged_df, misa_mock_data], ignore_index=True)
    return final_df

df = load_real_data()

if df is not None and not df.empty:
    with st.sidebar:
        st.header("🔍 분석 및 정책 필터")
        
        # 신규 기능: 역세권 수혜 구역 필터 토글
        benefit_only = st.toggle("✨ 역세권 활성화 수혜 지역만 보기", value=False, help="공공기여 비율 완화(50%->30%)가 적용되는 11개 자치구 상권만 필터링합니다.")
        
        industry_filter = st.multiselect("업종 선택", options=['커피-음료', '제과점'], default=['커피-음료', '제과점'])
        
        # 필터링 적용
        filtered_df = df[df['업종명'].isin(industry_filter)].copy()
        if benefit_only:
            filtered_df = filtered_df[filtered_df['is_benefit_zone'] == True]
        
        # 색상 지정 로직 (수혜 지역은 황금색 테두리 효과를 위해 색상 차별화 가능)
        def assign_color(row):
            if row['is_benefit_zone']:
                return [255, 215, 0, 230]  # 수혜 지역은 황금색(Gold)
            return [255, 50, 50, 160] if row['업종명'] == '커피-음료' else [255, 165, 0, 160]
            
        filtered_df['color'] = filtered_df.apply(assign_color, axis=1)
        
        if not filtered_df.empty:
            sorted_districts = sorted(filtered_df['상권명'].unique())
            selected_district = st.selectbox("상세 분석 상권", sorted_districts)
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            
            # 수혜 지역 뱃지 표시
            if selected_data['is_benefit_zone']:
                st.info(f"📍 **{selected_data['GU_NM']}**: 규제 완화 수혜 지역입니다.")
            
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
        else:
            st.warning("조건에 맞는 데이터가 없습니다.")

    # 3. 3D 시각화
    initial_lat = selected_data['lat'] if not filtered_df.empty else 37.5665
    initial_lon = selected_data['lon'] if not filtered_df.empty else 126.9780

    layer = pdk.Layer(
        'ColumnLayer', 
        filtered_df, 
        get_position='[lon, lat]', 
        get_elevation='당월_매출액', 
        elevation_scale=0.00005, 
        radius=250, 
        get_fill_color='color',
        pickable=True,
        auto_highlight=True
    )
    
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=initial_lat, longitude=initial_lon, zoom=12, pitch=45),
        tooltip={"text": "상권명: {상권명} ({GU_NM})\n매출액: {당월_매출액}원\n수혜구역: {is_benefit_zone}"}
    ))
    
    # 4. AI 컨설턴트 (정책 맞춤형 프롬프트 튜닝)
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        st.divider()
        st.subheader(f"🤖 정책 연계 AI 비즈니스 리포트")
        
        if not filtered_df.empty and st.button("AI 정책 분석 리포트 생성"):
            with st.spinner('서울시 최신 정책과 매출 데이터를 결합 분석 중...'):
                # 정책 맞춤형 프롬프트 설계
                policy_context = ""
                if selected_data['is_benefit_zone']:
                    policy_context = (
                        f"이 지역은 서울시 '역세권 활성화 사업'의 직접 수혜지인 {selected_data['GU_NM']}에 속해 있습니다. "
                        "공공기여 비율이 30%로 낮아지고 고밀 개발이 예상되므로, 인구 밀도 급증에 대비한 전략을 포함해줘."
                    )
                else:
                    policy_context = "서울시 전역 역세권 용도지역 상향 및 '직주락' 활성화 전략을 바탕으로 전략을 세워줘."

                prompt = f"""
                너는 서울시 도시계획 전문가이자 상권 분석가야.
                상권명: {selected_district} / 업종: {selected_data['업종명']} / 월 매출: {int(selected_data['당월_매출액']):,}원
                
                {policy_context}
                
                위 데이터를 바탕으로 다음 내용을 포함해 '짧고 강렬하게' 컨설팅해줘:
                1. 상권 현황 진단
                2. 역세권 고밀 개발에 따른 미래 가치 및 기회 요인
                3. 소상공인을 위한 실전 대응 전략 (메뉴, 마케팅, 공간 활용 등)
                """
                
                response = model.generate_content(prompt)
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(response.text)
                    
    except Exception as e:
        st.error("AI 연결 확인이 필요합니다. (API Key 설정 등)")

    st.subheader("📋 데이터 상세 시트")
    st.dataframe(filtered_df[['상권명', 'GU_NM', '업종명', '당월_매출액', 'is_benefit_zone']], width='stretch')

else:
    st.error("데이터 로드 중입니다. 잠시만 기다려주세요.")
