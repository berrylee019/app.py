import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os

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
    # 1. 상권 매출 데이터 가져오기 (25개)
    sales_url = f"http://openapi.seoul.go.kr:8088/{API_KEY}/json/VwsmTrdarSelngQq/1/25/"
    sales_res = requests.get(sales_url).json()
    sales_df = pd.DataFrame(sales_res['VwsmTrdarSelngQq']['row'])

    # 2. 좌표 데이터 가져오기 (CSV)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_dir, 'commercial_area.csv')
    
    # [수정] 인코딩 에러 방어 로직
    try:
        # 1. 엑셀/공공데이터의 표준인 CP949로 먼저 시도
        area_df = pd.read_csv(csv_path, encoding='cp949')
    except UnicodeDecodeError:
        try:
            # 2. 실패 시 전통적인 한국어 인코딩인 EUC-KR로 시도
            area_df = pd.read_csv(csv_path, encoding='euc-kr')
        except UnicodeDecodeError:
            # 3. 그것도 안 되면 BOM이 포함된 UTF-8로 최종 시도
            area_df = pd.read_csv(csv_path, encoding='utf-8-sig')
            
    # 상권코드 컬럼명 맞춰서 merge (이하 동일)
    area_df = area_df[['상권_코드', '상권_코드_명', '엑스좌표_값', '와이좌표_값']]
    area_df.rename(columns={'상권_코드': 'TRDAR_CD', '엑스좌표_값': 'lon', '와이좌표_값': 'lat'}, inplace=True)

    # 🚨 [핵심 해결책] 두 데이터의 상권코드 타입을 '문자열'로 완벽 통일
    sales_df['TRDAR_CD'] = sales_df['TRDAR_CD'].astype(str)
    area_df['TRDAR_CD'] = area_df['TRDAR_CD'].astype(str)
    
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')

    
    # 3. 필요한 컬럼만 추출 (상권코드, 중심점 위도, 중심점 경도)
    # 서울시 상권영역 데이터의 좌표 컬럼명은 보통 X_CNTS, Y_CNTS (또는 TRDAR_CD_LMT 등)로 되어 있습니다.
    # 여기서는 표준적인 위경도 컬럼명을 가정하고 작성했습니다.
    area_df = area_df[['TRDAR_CD', 'TRDAR_CD_NM', 'X_CNTS', 'Y_CNTS']]
    area_df.rename(columns={'X_CNTS': 'lon', 'Y_CNTS': 'lat'}, inplace=True)
    
    # 4. 판다스 Merge (상권코드를 기준으로 두 데이터 결합)
    # 매출 데이터의 'TRDAR_CD'와 영역 데이터의 'TRDAR_CD'가 같은 것끼리 묶어줍니다.
    merged_df = pd.merge(sales_df, area_df, on='TRDAR_CD', how='inner')
    
    # 숫자로 변환
    merged_df['lat'] = pd.to_numeric(merged_df['lat'])
    merged_df['lon'] = pd.to_numeric(merged_df['lon'])
    merged_df['당월_매출액'] = pd.to_numeric(merged_df['THSMON_SELNG_AMT'])
    merged_df['상권명'] = merged_df['TRDAR_CD_NM']
    
    return merged_df

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
        radius=500,                  # 👈 기존 200에서 500으로 변경 (기둥을 2.5배 굵게)
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
    
import google.generativeai as genai

# 1. 제미나이 API 설정 (형님의 API 키를 입력하세요)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-2.5-flash')

# 2. AI 분석 리포트 생성 함수
def get_ai_consulting(sangkwon, industry, sales, count):
    # 평균 객단가 계산
    avg_price = sales / count if count > 0 else 0
    
    # AI에게 던질 프롬프트 (페르소나 부여)
    prompt = f"""
    당신은 서울시 소상공인을 위한 20년 경력의 전문 상권 분석 컨설턴트입니다.
    다음 데이터를 바탕으로 '의뢰인님'에게 조언하듯 친절하면서도 날카로운 분석 보고서를 작성해주세요.
    
    [데이터 정보]
    - 상권명: {sangkwon}
    - 업종: {industry}
    - 당월 매출액: {int(sales):,}원
    - 당월 매출건수: {int(count):,}건
    - 추정 객단가: {int(avg_price):,}원
    
    [보고서 포함 내용]
    1. 현재 매출 규모에 대한 냉정한 평가
    2. 객단가 기반의 타겟 고객층 분석
    3. 이 상권에서 성공하기 위한 핵심 전략 1가지
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "⚠️ AI 컨설턴트가 잠시 외출 중입니다. (API 키 확인 필요)"

# 3. Streamlit 메인 화면 하단에 보고서 배치
st.divider()
st.subheader(f"🤖 AI 컨설턴트의 '{selected_district}' 분석 리포트")

with st.spinner('AI가 데이터를 분석하여 전략을 세우고 있습니다...'):
    # 선택된 상권의 실시간 데이터를 기반으로 AI 호출
    report = get_ai_consulting(
        selected_data['상권명'], 
        selected_data['업종명'], 
        selected_data['당월_매출액'], 
        selected_data['당월_매출건수']
    )
    
    # AI 채팅창 스타일로 출력
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(report)
