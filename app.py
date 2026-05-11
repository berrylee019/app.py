import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from pyproj import Transformer
import google.generativeai as genai

# 1. 변환기 및 정책 데이터 설정
transformer = Transformer.from_crs("epsg:5181", "epsg:4326", always_xy=True)

# 규제 완화 수혜 11개 자치구
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
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except:
        area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # 💡 1. 자치구 유추 로직 강화
    cols_to_use = ['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값']
    if '자치구_명' in area_df.columns:
        cols_to_use.append('자치구_명')
    
    area_df = area_df[cols_to_use].copy()
    
    rename_dict = {'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat', '상권_코드_명': '상권명'}
    if '자치구_명' in area_df.columns:
        rename_dict['자치구_명'] = 'GU_NM'
    else:
        area_df['GU_NM'] = "서울 지역" # 기본값
        
    area_df.rename(columns=rename_dict, inplace=True)

    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    merged_df[['lon', 'lat']] = merged_df.apply(convert_coords, axis=1)
    
    merged_df['lat'] = pd.to_numeric(merged_df['lat'])
    merged_df['lon'] = pd.to_numeric(merged_df['lon'])
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'], errors='coerce').fillna(0)
    merged_df['업종명'] = merged_df['SVC_INDUTY_CD_NM']

    # 💡 자치구 판단 로직 강화: 상권명에 자치구 이름이 포함된 경우까지 체크
    def check_benefit(row):
        target_text = str(row.get('GU_NM', '')) + " " + str(row.get('상권명', ''))
        short_benefit_list = [gu.replace('구', '') for gu in BENEFIT_GU]
        return any(gu in target_text for gu in short_benefit_list)

    merged_df['is_benefit_zone'] = merged_df.apply(check_benefit, axis=1)

    misa_mock_data = pd.DataFrame({
        'TRDAR_CD': ['MISA01', 'MISA02'],
        'SVC_INDUTY_CD_NM': ['커피-음료', '제과점'],
        '상권명': ['미사역 중심상권', '망월천 수변공원'],
        'lon': [127.1925, 127.1890],
        'lat': [37.5610, 37.5640],
        '당월_매출액': [120000000, 95000000],
        'GU_NM': ['하남시', '하남시'],
        'is_benefit_zone': [False, False],
        '업종명': ['커피-음료', '제과점']
    })

    final_df = pd.concat([merged_df, misa_mock_data], ignore_index=True)
    return final_df

df = load_real_data()

if df is not None and not df.empty:
    with st.sidebar:
        st.header("🔍 분석 및 정책 필터")
        
        benefit_only = st.toggle("✨ 역세권 활성화 수혜 지역만 보기", value=False, help="공공기여 완화가 적용되는 11개 자치구 상권만 필터링합니다.")
        industry_filter = st.multiselect("업종 선택", options=['커피-음료', '제과점'], default=['커피-음료', '제과점'])
        
        # 💡 2. 데이터 유무 체크 및 필터링 강화
        filtered_df = df[df['업종명'].isin(industry_filter)].copy()
        if benefit_only:
            filtered_df = filtered_df[filtered_df['is_benefit_zone'] == True]
        
        if not filtered_df.empty:
            sorted_districts = sorted(filtered_df['상권명'].unique())
            selected_district = st.selectbox("상세 분석 상권", sorted_districts)
            selected_data = filtered_df[filtered_df['상권명'] == selected_district].iloc[0]
            
            if selected_data['is_benefit_zone']:
                st.info(f"📍 **{selected_data['GU_NM']}**: 규제 완화 수혜 지역입니다.")
            
            st.metric("추정 매출액", f"{int(selected_data['당월_매출액']):,}원")
            
            def assign_color(row):
                if row['is_benefit_zone']:
                    return [255, 215, 0, 230] 
                return [255, 50, 50, 160] if row['업종명'] == '커피-음료' else [255, 165, 0, 160]
            filtered_df['color'] = filtered_df.apply(assign_color, axis=1)
        else:
            st.warning("⚠️ 해당 조건에 맞는 데이터가 없습니다.")
            selected_district = None

    # 지도 및 AI 리포트 출력 제어
    if selected_district:
        # 3. 3D 시각화
        initial_lat, initial_lon = selected_data['lat'], selected_data['lon']
        layer = pdk.Layer(
            'ColumnLayer', filtered_df, get_position='[lon, lat]',
            get_elevation='당월_매출액', elevation_scale=0.00005,
            radius=250, get_fill_color='color', pickable=True, auto_highlight=True
        )
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(latitude=initial_lat, longitude=initial_lon, zoom=12, pitch=45),
            tooltip={"text": "상권명: {상권명} ({GU_NM})\n매출액: {당월_매출액}원\n수혜구역: {is_benefit_zone}"}
        ))
        
        # 4. AI 컨설턴트
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.divider()
            st.subheader(f"🤖 정책 연계 AI 비즈니스 리포트")
            
            if st.button("AI 정책 분석 리포트 생성"):
                with st.spinner('전략 수립 중...'):
                    policy_context = (f"이 지역은 서울시 '역세권 활성화 사업'의 직접 수혜지인 {selected_data['GU_NM']}에 속합니다." 
                                     if selected_data['is_benefit_zone'] else "서울시 역세권 '직주락' 활성화 전략 기반입니다.")
                    prompt = f"상권 전문가로서 {selected_district}의 {selected_data['업종명']}(매출:{int(selected_data['당월_매출액']):,}원) 분석 리포트를 작성해줘. {policy_context}"
                    response = model.generate_content(prompt)
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(response.text)
        except Exception as e:
            st.error("AI 연결 확인이 필요합니다.")

        st.subheader("📋 데이터 상세 시트")
        st.dataframe(filtered_df[['상권명', 'GU_NM', '업종명', '당월_매출액', 'is_benefit_zone']], width='stretch')
    else:
        st.info("왼쪽 사이드바에서 상권을 선택하거나 필터를 조정해 주세요.")
else:
    st.error("데이터 로드 중입니다.")
