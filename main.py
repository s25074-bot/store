import math
import pandas as pd
import plotly.express as px
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 제목 표시
# ==========================================
st.set_page_config(page_title="편의점 & 카페 지도 시각화", layout="wide")
st.title("🏪 편의점 & ☕ 카페 위치 지도 탐색기")


# ==========================================
# 2. 하버사인(Haversine) 거리 계산 함수
# 두 지점의 위도, 경도를 받아 거리를 계산 (단위: km)
# ==========================================
def calculate_haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # 지구 반지름 (km)

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ==========================================
# 3. 데이터 불러오기 및 전처리 (캐싱 적용)
# ==========================================
@st.cache_data
def load_data():
    # 파일명 우선순위 적용 (store.csv -> store_filtered.csv)
    try:
        df = pd.read_csv("store.csv")
    except FileNotFoundError:
        try:
            df = pd.read_csv("store_filtered.csv")
        except FileNotFoundError:
            st.error(
                "데이터 파일을 찾을 수 없습니다. 'store.csv' 또는 'store_filtered.csv' 파일을 확인해 주세요."
            )
            return pd.DataFrame()

    # 필수 컬럼 존재 여부 확인
    required_cols = ["상호명", "위도", "경도", "상권업종소분류명", "시도명"]
    for col in required_cols:
        if col not in df.columns:
            st.error(f"데이터에 '{col}' 열이 존재하지 않습니다.")
            return pd.DataFrame()

    # 1) 편의점과 카페만 필터링
    df = df[df["상권업종소분류명"].isin(["편의점", "카페"])].copy()

    # 2) 위도, 경도를 숫자형으로 변환 (숫자가 아닌 값은 NaN 처리)
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")

    # 3) 위도/경도가 비어있는 결측치(NaN) 제거
    df = df.dropna(subset=["위도", "경도"])

    return df


df_raw = load_data()

# 데이터가 비어있으면 진행 중단
if df_raw.empty:
    st.stop()


# ==========================================
# 4. 사이드바 - 지역(시/도) 선택 필터
# ==========================================
st.sidebar.header("🔍 검색 및 필터 설정")

# 시도명 목록 추출 및 선택 박스 생성
sido_list = sorted(df_raw["시도명"].dropna().unique())
selected_sido = st.sidebar.selectbox("지역(시/도) 선택", sido_list)

# 선택한 지역 데이터만 필터링
df_filtered = df_raw[df_raw["시도명"] == selected_sido].copy()


# ==========================================
# 5. 사이드바 - 반경 검색 (심화 기능)
# ==========================================
st.sidebar.markdown("---")
use_radius_search = st.sidebar.checkbox("반경 검색 사용하기")

search_info_text = ""
center_lat, center_lon = None, None

if use_radius_search:
    st.sidebar.subheader("📍 반경 검색 설정")

    if not df_filtered.empty:
        # 드롭다운에 매장명과 업종을 함께 표시하여 식별 용이하게 설정
        df_filtered["매장표시명"] = (
            df_filtered["상호명"] + " (" + df_filtered["상권업종소분류명"] + ")"
        )
        store_options = df_filtered["매장표시명"].tolist()

        selected_store_name = st.sidebar.selectbox("기준 매장 선택", store_options)
        radius_km = st.sidebar.slider("검색 반경 (km)", 0.5, 10.0, 1.0, step=0.5)

        # 선택한 기준 매장의 좌표 가져오기
        selected_row = df_filtered[
            df_filtered["매장표시명"] == selected_store_name
        ].iloc[0]
        center_lat = selected_row["위도"]
        center_lon = selected_row["경도"]

        # 하버사인 공식을 적용하여 각 매장까지의 거리 계산
        df_filtered["거리_km"] = df_filtered.apply(
            lambda row: calculate_haversine(
                center_lat, center_lon, row["위도"], row["경도"]
            ),
            axis=1,
        )

        # 설정한 반경 내의 매장만 남아있도록 필터링
        df_filtered = df_filtered[df_filtered["거리_km"] <= radius_km]
        search_info_text = f"기준 매장 반경 {radius_km} km 이내"


# ==========================================
# 6. 메인 화면 - 지표 카드(st.metric) 표시
# ==========================================
st.subheader(f"📊 {selected_sido} 매장 현황")

if search_info_text:
    st.caption(f"📌 {search_info_text}")

# 편의점 / 카페 / 전체 개수 집계
cvs_count = len(df_filtered[df_filtered["상권업종소분류명"] == "편의점"])
cafe_count = len(df_filtered[df_filtered["상권업종소분류명"] == "카페"])
total_count = len(df_filtered)

# Metric 카드를 3개 컬럼으로 배치
col1, col2, col3 = st.columns(3)
col1.metric("편의점 수", f"{cvs_count:,} 개")
col2.metric("카페 수", f"{cafe_count:,} 개")
col3.metric("전체 매장 수", f"{total_count:,} 개")

st.markdown("---")


# ==========================================
# 7. 메인 화면 - Plotly 지도 시각화
# ==========================================
if df_filtered.empty:
    st.warning("⚠️ 선택한 조건에 해당하는 매장이 하나도 없습니다.")
else:
    # 매장별 색상 지정 (편의점: 파란색, 카페: 주황색)
    color_map = {"편의점": "blue", "카페": "orange"}

    # Plotly 버전에 따른 최신(scatter_map) 및 구버전(scatter_mapbox) 호환 분기 처리
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(
            df_filtered,
            lat="위도",
            lon="경도",
            color="상권업종소분류명",
            color_discrete_map=color_map,
            hover_name="상호명",
            hover_data={"상권업종소분류명": True, "위도": False, "경도": False},
            zoom=11 if not use_radius_search else 13,
            center=(
                {"lat": center_lat, "lon": center_lon}
                if use_radius_search and center_lat
                else None
            ),
            map_style="open-street-map",
            height=600,
        )
    else:
        fig = px.scatter_mapbox(
            df_filtered,
            lat="위도",
            lon="경도",
            color="상권업종소분류명",
            color_discrete_map=color_map,
            hover_name="상호명",
            hover_data={"상권업종소분류명": True, "위도": False, "경도": False},
            zoom=11 if not use_radius_search else 13,
            center=(
                {"lat": center_lat, "lon": center_lon}
                if use_radius_search and center_lat
                else None
            ),
            mapbox_style="open-street-map",
            height=600,
        )

    # 레이아웃 여백 조정
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})

    # Streamlit 지도 출력
    st.plotly_chart(fig, use_container_width=True)
