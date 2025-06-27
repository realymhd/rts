import streamlit as st
import pandas as pd
import sys
import os
import re
from pathlib import Path
from sqlalchemy import text

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_db_engine
from src.utils import get_ai_response, load_prompt

st.set_page_config(layout="wide")

st.title("💡 AI DB 애널리스트")
st.markdown("데이터베이스 전체 구조를 학습한 AI에게 자연어로 질문하여 복합적인 분석을 수행하고, 최종 보고서만 받아보세요.")

@st.cache_data(ttl="1h")
def get_database_context(_engine):
    """데이터베이스의 모든 테이블 스키마와 queries 폴더의 예제 SQL을 가져옵니다."""
    if _engine is None:
        return ""
        
    context_parts = []
    
    # 1. 모든 테이블의 DDL (CREATE TABLE) 문 가져오기
    try:
        with _engine.connect() as connection:
            table_names = pd.read_sql(text("SHOW TABLES;"), connection).iloc[:, 0].tolist()
            
            context_parts.append("### 데이터베이스 스키마 (DDL)")
            for table_name in table_names:
                ddl_query = text(f"SHOW CREATE TABLE `{table_name}`;")
                ddl = pd.read_sql(ddl_query, connection).iloc[0, 1]
                context_parts.append(ddl)
    except Exception as e:
        st.warning(f"DB 스키마를 가져오는 중 오류 발생: {e}")

    # 2. queries 폴더의 모든 SQL 파일 내용 가져오기
    try:
        query_files = list(Path("queries").rglob("*.sql"))
        if query_files:
            context_parts.append("\n### 모범 SQL 쿼리 예시")
            for file_path in query_files:
                context_parts.append(f"-- From: {file_path.name}\n{file_path.read_text()}")
    except Exception as e:
         st.warning(f"SQL 예시 파일을 읽는 중 오류 발생: {e}")

    return "\n\n".join(context_parts)

def get_sql_from_ai_response(response_generator):
    """스트리밍 응답에서 SQL 쿼리만 추출합니다."""
    full_response = "".join(list(response_generator))
    
    # 마크다운 코드 블록에서 SQL 추출
    match = re.search(r"```sql\n(.*?)\n```", full_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        # 코드 블록이 없는 경우, 전체 응답을 SQL로 가정
        return full_response.strip()

# --- 메인 페이지 ---
engine = get_db_engine()

if engine:
    # DB 컨텍스트는 백그라운드에서 로딩
    if 'db_context' not in st.session_state:
        st.session_state['db_context'] = get_database_context(engine)
    db_context = st.session_state.get('db_context')

    st.subheader("무엇이 궁금하신가요?")
    user_question = st.text_input("자연어로 질문을 입력하세요 (예: '주차별 리텐션이 가장 높은 유저 그룹의 특징은?')", key="user_question")

    if st.button("📈 분석 실행", key="run_analysis") and user_question and db_context:
        generated_sql = ""
        df = pd.DataFrame()
        max_retries = 2

        with st.spinner("AI가 질문을 분석하여 SQL 쿼리를 생성하는 중입니다..."):
            sql_prompt_template = load_prompt("prompts/db_analyst.txt")
            sql_prompt = sql_prompt_template.format(db_context=db_context, user_question=user_question)
            
            sql_response_generator = get_ai_response(sql_prompt)
            generated_sql = get_sql_from_ai_response(sql_response_generator)
        
        for attempt in range(max_retries):
            try:
                with st.spinner(f"생성된 쿼리 실행 중... (시도 {attempt + 1}/{max_retries})"):
                    query = text(generated_sql)
                    df = pd.read_sql(query, engine)
                
                # 성공 시 루프 탈출
                break

            except Exception as e:
                error_message = str(e)
                if attempt < max_retries - 1:
                    with st.spinner(f"쿼리 오류 발생. AI가 스스로 코드를 수정 후 재시도합니다..."):
                        corrector_prompt_template = load_prompt("prompts/sql_corrector.txt")
                        corrector_prompt = corrector_prompt_template.format(
                            user_question=user_question,
                            db_context=db_context,
                            faulty_sql=generated_sql,
                            error_message=error_message
                        )
                        correction_response_generator = get_ai_response(corrector_prompt)
                        generated_sql = get_sql_from_ai_response(correction_response_generator)
                else:
                    # 마지막 시도도 실패하면 최종 에러 메시지 표시
                    st.error(f"분석 중 오류가 발생했습니다: {error_message}")
                    with st.expander("오류가 발생한 최종 SQL 쿼리 보기"):
                        st.code(generated_sql, language='sql')
                    st.stop() # 분석 중단

        # 최종 보고서 생성
        with st.spinner("AI가 분석 결과를 바탕으로 최종 보고서를 작성하는 중입니다..."):
            report_prompt_template = load_prompt("prompts/final_analyst.txt")
            report_prompt = report_prompt_template.format(user_question=user_question, data_frame=df.to_markdown())
            
            report_generator = get_ai_response(report_prompt)
            
            st.subheader("🤖 AI 분석 보고서")
            st.write_stream(report_generator)

else:
    st.warning("데이터베이스에 연결할 수 없습니다. `.streamlit/secrets.toml` 설정을 확인해주세요.") 