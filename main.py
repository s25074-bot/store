import math
import pandas as pd
import plotly.express as px
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 제목 표시
# ==========================================
st.set_page_config(page_title="동별 편의점 & 카페 지도", layout="wide")
st.title("🏪 동별 편의점 & ☕ 카페 위치 지도 탐색기")


# ==========================================
# 2. 하버사인(Haversine) 거리 계산 함수 (km 단위)
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
# 3. 데이터 불러오기 및 전처리
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
            return pd.DataFrame(), None

    # 필수 컬럼 존재 여부 확인
    required_cols = ["상호명", "위도", "경도", "상권업종소분류명", "시도명"]
    for col in required_cols:
        if col not in df.columns:
            st.error(f"데이터에 '{col}' 열이 존재하지 않습니다.")
            return pd.DataFrame(), None

    # '동' 관련 열 자동 인식 (행정동명, 법정동명, 동명, 읍면동명 순)
    dong_col = None
    possible_dong_cols = ["행정동명", "법정동명", "동명", "읍면동명"]
    for col in possible_dong_cols:
        if col in df.columns:
            dong_col = col
            break

    if not dong_col:
        st.error(
            "데이터에서 '동' 정보를 담은 열(행정동명, 법정동명, 동명 등)을 찾을 수 없습니다."
        )
        return pd.DataFrame(), None

    # 1) 편의점과 카페만 필터링
    df = df[df["상권업종소분류명"].isin(["편의점", "카페"])].copy()

    # 2) 위도, 경도를 숫자형으로 변환 (숫자가 아닌 값은 NaN 처리)
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")

    # 3) 위도/경도/동 이름이 비어있는 결측치 제거
    df = df.dropna(subset=["위도", "경도", dong_col])

    return df, dong_col


df_raw, DONG_COL = load_data()

# 데이터가 비어있으면 진행 중단
if df_raw.empty or not DONG_COL:
    st.stop()


# ==========================================
# 4. 사이드바 - 지역(시/도 & 동) 선택 필터
# ==========================================
st.sidebar.header("🔍 지역 선택")

# 1) 시/도 선택
sido_list = sorted(df_raw["시도명"].dropna().unique())
selected_sido = st.sidebar.selectbox("1. 시/도 선택", sido_list)

# 선택한 시/도의 데이터만 1차 필터링
df_sido = df_raw[df_raw["시도명"] == selected_sido].copy()

# 2) 동 선택 ("전체" 옵션 포함)
dong_list = ["전체"] + sorted(df_sido[DONG_COL].dropna().unique())
selected_dong = st.sidebar.selectbox("2. 동 선택", dong_list)

# 선택한 동에 따라 2차 필터링
if selected_dong == "전체":
    df_filtered = df_sido.copy()
    region_title = f"{selected_sido} (전체 동)"
else:
    df_filtered = df_sido[df_sido[DONG_COL] == selected_dong].copy()
    region_title = f"{selected_sido} {selected_dong}"


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
        # 매장 식별을 위한 표시용 이름 생성
        df_filtered["매장표시명"] = (
            df_filtered["상호명"]
            + " ("
            + df_filtered[DONG_COL]
            + " / "
            + df_filtered["상권업종소분류명"]
            + ")"
        )
        store_options = df_filtered["매장표시명"].tolist()

        selected_store_name = st.sidebar.selectbox("기준 매장 선택", store_options)
        radius_km = st.sidebar.slider("검색 반경 (km)", 0.5, 10.0, 1.0, step=0.5)

        # 선택한 기준 매장 좌표 추출
        selected_row = df_filtered[
            df_filtered["매장표시명"] == selected_store_name
        ].iloc[0]
        center_lat = selected_row["위도"]
        center_lon = selected_row["경도"]

        # 하버사인 거리 계산 후 반경 내 매장만 필터링
        df_filtered["거리_km"] = df_filtered.apply(
            lambda row: calculate_haversine(
                center_lat, center_lon, row["위도"], row["경도"]
            ),
            axis=1,
        )

        df_filtered = df_filtered[df_filtered["거리_km"] <= radius_km]
        search_info_text = f"기준 매장 반경 {radius_km} km 이내"


# ==========================================
# 6. 메인 화면 - 지표 카드(st.metric) 표시
# ==========================================
st.subheader(f"📊 {region_title} 매장 현황")

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
    color_map = {"편의점": "blue", "카페": "orange"}

    # 마우스 오버 시 표시할 정보 설정 (매장명, 동이름, 업종)
    hover_data = {
        DONG_COL: True,
        "상권업종소분류명": True,
        "위도": False,
        "경도": False,
    }

    # 줌 레벨 조정 (동 단위로 선택했을 때 더 가깝게 확대)
    default_zoom = 13 if selected_dong != "전체" else 11
    zoom_level = 14 if use_radius_search else default_zoom

    # Plotly 버전 호환 처리 (px.scatter_map vs px.scatter_mapbox)
    if hasattr(px, "scatter_map"):
        fig = px.scatter_map(
            df_filtered,
            lat="위도",
            lon="경도",
            color="상권업종소분류명",
            color_discrete_map=color_map,
            hover_name="상호명",
            hover_data=hover_data,
            zoom=zoom_level,
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
            hover_data=hover_data,
            zoom=zoom_level,
            center=(
                {"lat": center_lat, "lon": center_lon}
                if use_radius_search and center_lat
                else None
            ),
            mapbox_style="open-street-map",
            height=600,
        )

    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    st.plotly_chart(fig, use_container_width=True)
