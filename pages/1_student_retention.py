import streamlit as st
import pandas as pd
from sqlalchemy import text
import openai
import json
from datetime import datetime, timedelta
import plotly.graph_objects as go
import sys
import os

# --- Path Setup ---
# 프로젝트 루트 디렉토리를 Python 경로에 추가하여 'src' 모듈을 찾을 수 있도록 함
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.db import get_db_engine
    from src.utils import load_query, load_prompt
except ImportError as e:
    st.error(f"필요한 모듈을 가져오는 데 실패했습니다: {e}. 파일 경로와 의존성을 확인해주세요.")
    st.stop()


# --- Data Loading ---
@st.cache_data(ttl="1h")
def load_retention_data(_engine):
    """
    데이터베이스에서 '가입일 기준' 리텐션 데이터를 로드합니다.
    'queries/1_student_retention.sql' 파일에서 SQL 쿼리를 가져옵니다.
    """
    if _engine is None:
        return pd.DataFrame()
    
    query_string = load_query("queries/1_student_retention.sql")
    if not query_string:
        st.error("리텐션 분석 쿼리를 불러오는데 실패했습니다.")
        return pd.DataFrame()
        
    query = text(query_string)
    
    with _engine.connect() as connection:
        df = pd.read_sql(query, connection)
    
    if 'cohort_week' in df.columns and not df.empty:
        df['cohort_week'] = pd.to_datetime(df['cohort_week']).dt.strftime('%Y-%m-%d')
        
    return df

# --- Plotting (from features/retention/plot.py) ---
def create_retention_table_figure(df: pd.DataFrame):
    """
    주어진 데이터프레임으로 조건부 서식이 적용된 Plotly 테이블 Figure를 생성합니다.
    """
    if df.empty:
        return go.Figure()

    week_columns = [col for col in df.columns if col.startswith('Week')]
    
    header_values = list(df.columns)
    if 'cohort_week' in header_values:
        header_values[header_values.index('cohort_week')] = '기준일'
    if 'cohort_size' in header_values:
        header_values[header_values.index('cohort_size')] = '제출 학생 수'

    fig = go.Figure(data=go.Table(
        header=dict(
            values=header_values,
            fill_color='paleturquoise',
            align='center',
            font_size=12
        ),
        cells=dict(
            values=[df[col] for col in df.columns],
            fill_color=[
                'lavender', 'lightgrey',
                *([df[col].apply(lambda x: f'rgba(0, 128, 0, {x/100})' if pd.notna(x) else 'white') for col in week_columns])
            ],
            align='center',
            font_size=12,
            height=30
        )
    ))
    fig.update_layout(margin=dict(l=10, r=10, b=10, t=10), height=len(df) * 30 + 60)
    return fig

# --- AI Analysis ---
CACHE_FILE = ".ai_cache.json"

@st.cache_data(ttl="1h")
def get_ai_analysis(df_as_string: str):
    """
    OpenRouter를 통해 리텐션 데이터 분석을 요청하고 결과를 반환합니다.
    'prompts/1_retention_analysis.txt' 파일에서 시스템 프롬프트를 가져옵니다.
    """
    try:
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=st.secrets["openrouter"]["api_key"],
        )
        
        system_prompt = load_prompt("prompts/1_retention_analysis.txt")
        if not system_prompt:
            st.error("AI 분석 프롬프트를 불러오는데 실패했습니다.")
            return "AI 분석 프롬프트를 불러오는데 실패했습니다."

        response = client.chat.completions.create(
            model=st.secrets.get("openrouter", {}).get("model", "google/gemini-2.5-flash-preview-05-20"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Here is the retention data (up to Week 8):\n\n{df_as_string}"},
            ],
            stream=False,
        )
        return response.choices[0].message.content
    except KeyError as e:
        st.error(f"'{str(e)}' 키를 찾을 수 없습니다. '.streamlit/secrets.toml' 파일을 확인해주세요.")
        return f"AI 분석 설정 오류: {e}"
    except Exception as e:
        return f"AI 분석 중 오류가 발생했습니다: {e}"

def manage_ai_analysis_cache(table_df: pd.DataFrame):
    """AI 분석 및 캐시 관련 UI와 로직을 관리합니다."""
    with st.container(height=350, border=True):
        cached_analysis = None
        try:
            with open(CACHE_FILE, "r") as f:
                cached_analysis = json.load(f)
                cached_analysis['timestamp'] = datetime.fromisoformat(cached_analysis['timestamp'])
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        is_button_disabled = False
        if cached_analysis:
            time_since_click = datetime.now() - cached_analysis['timestamp']
            if time_since_click < timedelta(days=1):
                is_button_disabled = True
                time_remaining = timedelta(days=1) - time_since_click
                hours, remainder = divmod(time_remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                st.info(f"AI 분석은 24시간마다 가능합니다. (다음 분석까지 {hours}시간 {minutes}분 남음)", icon="⏳")

        if st.button("AI에게 데이터 분석 요청하기", disabled=is_button_disabled, use_container_width=True):
            with st.spinner("AI가 데이터를 분석하고 있습니다. 잠시만 기다려주세요..."):
                df_string = table_df.to_markdown(index=False)
                analysis_result = get_ai_analysis(df_string)
                with open(CACHE_FILE, "w") as f:
                    json.dump({"timestamp": datetime.now().isoformat(), "result": analysis_result}, f)
            st.rerun()

        if cached_analysis and (datetime.now() - cached_analysis['timestamp'] < timedelta(days=1)):
            st.markdown(cached_analysis['result'])

# --- Main Dashboard Page (from features/retention/page.py) ---
def show_retention_dashboard():
    """학습지 리텐션 대시보드 페이지를 렌더링합니다."""
    st.set_page_config(page_title="학생 학습지 리텐션 대시보드", layout="wide")
    
    st.title("학생 학습지 리텐션 대시보드 (Weekly Retention)")
    
    # --- 상단 레이아웃: 가이드 및 AI 분석 ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("💡 대시보드 활용 가이드")
        with st.container(height=350, border=True):
            st.markdown("""
                기준일(Day0)에 학습지를 제출한 학생들이 Day7N(WeekN)에도 학습지를 제출하는가?
                
                - **`기준일`**: 학생들이 처음으로 학습지를 제출한 Day0입니다. 이들이 하나의 코호트가 됩니다.
                - **`제출 학생 수`**: 기준일에 처음 활동을 시작한 총 학생 수입니다.
                - **`Week 1` ~ `Week 8`**: N주차에 다시 돌아와 학습지를 푼 학생의 비율(%)입니다. **색이 진할수록 유지율이 높습니다.**

                ---
                
                #### 🚀 활용하기
                1.  **가로로 읽기 (행 분석):** 특정 그룹의 유지율이 시간이 지남에 따라 어떻게 변하는지 확인
            """)
    
    with col2:
        st.subheader("🤖 AI 애널리스트(Gemini 2.5 Flash)")
        ai_container = st.empty()

    # --- 데이터 로딩 ---
    engine = get_db_engine()
    retention_df = load_retention_data(engine)

    # --- 데이터가 있을 경우에만 UI 렌더링 ---
    if not retention_df.empty:
        st.markdown("---")
        
        # --- 정렬 컨트롤 ---
        sort_cols = st.columns(2)
        with sort_cols[0]:
            sort_by = st.selectbox(
                "정렬 기준:",
                options=['cohort_week', 'cohort_size'],
                format_func=lambda x: {'cohort_week': '기준일', 'cohort_size': '제출 학생 수'}.get(x, x),
                index=0,
                key='sort_by'
            )
        with sort_cols[1]:
            sort_order_str = st.selectbox(
                "정렬 순서:",
                options=['내림차순', '오름차순'],
                index=0,
                key='sort_order'
            )
        
        sort_ascending = (sort_order_str == '오름차순')
        sorted_df = retention_df.sort_values(by=sort_by, ascending=sort_ascending)

        table_df = sorted_df
        
        with ai_container:
             manage_ai_analysis_cache(table_df)

        fig = create_retention_table_figure(table_df)
        st.plotly_chart(fig, use_container_width=True)

    elif engine is not None:
        st.info("표시할 데이터가 없거나, 데이터 로딩에 실패했습니다.")


if __name__ == "__main__":
    show_retention_dashboard() 