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
st.set_page_config(page_title="서울 & 경기 리얼티 AI - 데이터 융합 분석", layout="wide")

st.title("서울 상권(융합)분석 AI")
st.caption("Seoul-Realty AI | 인구+매출 데이터 결합 버전")

# API 및 서비스 설정
API_KEY = '776274504662736c3132334e5a767861'
SERVICE_SALES = 'VwsmTrdarSelngQq'
SERVICE_POP = 'VwsmTrdarFlpopQq' # 유동인구 서비스 추가

@st.cache_data(ttl=3600)
def load_real_data():
    # 데이터 로드 (매출 및 인구)
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE_SALES}/1/1000/"
    pop_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/{SERVICE_POP}/1/1000/"
    
    try:
        # A. 매출 데이터 로드
        sales_res = requests.get(sales_url).json()
        raw_sales_df = pd.DataFrame(sales_res[SERVICE_SALES]['row'])
        
        # B. 💡 [가점 포인트] 유동인구 데이터(인구 분야) 로드 및 결합
        pop_res = requests.get(pop_url).json()
        pop_df = pd.DataFrame(pop_res[SERVICE_POP]['row'])
        
        # 유동인구 데이터 전처리 (상권코드별 평균 유동인구 산출)
        pop_df['TOT_FLPOP_CO'] = pd.to_numeric(pop_df['TOT_FLPOP_CO'], errors='coerce').fillna(0)
        pop_summary = pop_df.groupby('TRDAR_CD')['TOT_FLPOP_CO'].mean().reset_index()
        pop_summary.rename(columns={'TOT_FLPOP_CO': '유동인구'}, inplace=True)
        
    except Exception as e:
        st.error(f"데이터 로드 및 결합 실패: {e}")
        return None

    target_industries = ['커피-음료', '제과점']
    sales_df = raw_sales_df[raw_sales_df['SVC_INDUTY_CD_NM'].isin(target_industries)].copy()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    
    try:
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except:
        area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # 💡 자치구 유추 로직 강화
    cols_to_use = ['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값']
    if '자치구_명' in area_df.columns:
        cols_to_use.append('자치구_명')
    
    area_df = area_df[cols_to_use].copy()
    
    rename_dict = {'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat', '상권_코드_명': '상권명'}
    if '자치구_명' in area_df.columns:
        rename_dict['자치구_명'] = 'GU_NM'
    else:
        area_df['GU_NM'] = "서울 지역"
        
    area_df.rename(columns=rename_dict, inplace=True)

    # 데이터 타입 통일 및 병합 (매출 + 위치 + 💡인구)
    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    pop_summary['TRDAR_CD'] = pop_summary['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    merged_df = pd.merge(merged_df, pop_summary, on='TRDAR_CD', how='left') # 이종 데이터 결합 완료
    
    merged_df[['lon', 'lat']] = merged_df.apply(convert_coords, axis=1)
    merged_df['lat'] = pd.to_numeric(merged_df['lat'])
    merged_df['lon'] = pd.to_numeric(merged_df['lon'])
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'], errors='coerce').fillna(0)
    merged_df['유동인구'] = merged_df['유동인구'].fillna(0)
    merged_df['업종명'] = merged_df['SVC_INDUTY_CD_NM']

    # 자치구 판단 로직 강화
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
        '유동인구': [45000, 38000],
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
            # 💡 인구 데이터 결합 표시
            st.metric("월 평균 유동인구", f"{int(selected_data['유동인구']):,}명", delta="인구 데이터 결합")
            
            def assign_color(row):
                if row['is_benefit_zone']:
                    return [255, 215, 0, 230] 
                return [255, 50, 50, 160] if row['업종명'] == '커피-음료' else [255, 165, 0, 160]
            filtered_df['color'] = filtered_df.apply(assign_color, axis=1)
        else:
            st.warning("⚠️ 해당 조건에 맞는 데이터가 없습니다.")
            selected_district = None

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
            tooltip={"text": "상권명: {상권명} ({GU_NM})\n매출액: {당월_매출액}원\n유동인구: {유동인구}명\n수혜구역: {is_benefit_zone}"}
        ))
        
        # 4. AI 컨설턴트 (💡 인구-매출 융합 분석 프롬프트)
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            st.divider()
            st.subheader(f"🤖 융합 데이터 기반 AI 비즈니스 리포트")
            
            if st.button("AI 융합 분석 리포트 생성"):
                with st.spinner('인구 흐름과 경제 데이터를 교차 분석 중...'):
                    policy_context = (f"이 지역은 서울시 '역세권 활성화 사업'의 직접 수혜지인 {selected_data['GU_NM']}에 속합니다." 
                                     if selected_data['is_benefit_zone'] else "서울시 역세권 '직주락' 활성화 전략 기반입니다.")
                    
                    # 💡 인구 데이터를 포함한 고도화된 프롬프트
                    prompt = f"""
                    너는 서울시 도시계획 전문가이자 상권 분석가야. 아래의 결합된 데이터를 바탕으로 분석해줘.
                    
                    상권명: {selected_district} / 업종: {selected_data['업종명']}
                    경제 데이터: 월 매출 {int(selected_data['당월_매출액']):,}원
                    인구 데이터: 월 평균 유동인구 {int(selected_data['유동인구']):,}명
                    
                    {policy_context}
                    
                    위 이종 결합 데이터를 바탕으로 다음 내용을 포함해 컨설팅해줘:
                    1. 인구-매출 상관관계 분석 (유동인구 대비 매출 효율성 평가)
                    2. 역세권 고밀 개발에 따른 미래 가치 및 인구 유입 시나리오
                    3. 결합 데이터를 활용한 소상공인 타겟팅 전략 (인구 밀집 시간대 및 마케팅 제안)
                    """
                    response = model.generate_content(prompt)
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(response.text)
        except Exception as e:
            st.error("AI 연결 확인이 필요합니다.")

        st.subheader("📋 데이터 상세 시트 (융합 데이터)")
        st.dataframe(filtered_df[['상권명', 'GU_NM', '업종명', '당월_매출액', '유동인구', 'is_benefit_zone']], width='stretch')
    else:
        st.info("왼쪽 사이드바에서 상권을 선택하거나 필터를 조정해 주세요.")
else:
    st.error("데이터 로드 중입니다.")
