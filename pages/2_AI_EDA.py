import streamlit as st
import pandas as pd
import sys
import os
import re
import uuid
import json
from pathlib import Path
from sqlalchemy import text, inspect

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_db_engine
from src.utils import get_ai_response, load_prompt

st.set_page_config(layout="wide", page_title="AI EDA")
st.title("💡 AI DB EDA")

HISTORY_CACHE_FILE = ".history_cache.json"

# --- 히스토리 파일 I/O 함수 ---
def save_threads_to_disk(threads):
    """스레드 목록을 로컬 JSON 파일에 저장합니다."""
    try:
        with open(HISTORY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(threads, f, indent=2, ensure_ascii=False)
    except IOError as e:
        st.error(f"히스토리를 저장하는데 실패했습니다: {e}")

def load_threads_from_disk():
    """로컬 JSON 파일에서 스레드 목록을 불러옵니다."""
    if not os.path.exists(HISTORY_CACHE_FILE):
        return []
    try:
        with open(HISTORY_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        # 파일이 손상되었거나 비어있을 경우, 빈 목록을 반환
        return []

# --- 유틸리티 함수 ---
def truncate_text(text, max_length=35):
    return (text[:max_length] + '...') if len(text) > max_length else text

def format_conversation_history(messages):
    history = []
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        history.append(f"{role}:\n{msg['content']}")
    return "\n\n".join(history)

# --- AI 및 DB 관련 함수 ---
@st.cache_data(ttl="1h", show_spinner=False)
def get_database_context(_engine):
    if _engine is None: return ""
    context_parts = []
    inspector = inspect(_engine)
    table_names = inspector.get_table_names()
    context_parts.append("### 데이터베이스 스키마 (DDL)")
    with _engine.connect() as connection:
        for table_name in table_names:
            try:
                query = text(f"SHOW CREATE TABLE `{table_name}`")
                ddl = pd.read_sql(query, connection).iloc[0, 1]
                context_parts.append(ddl)
            except Exception as e:
                st.warning(f"DDL for table `{table_name}` could not be retrieved: {e}")
    try:
        query_files = list(Path("queries").rglob("*.sql"))
        if query_files:
            context_parts.append("\n### 모범 SQL 쿼리 예시")
            for file_path in query_files:
                context_parts.append(f"-- From: {file_path.name}\n{file_path.read_text()}")
    except Exception: pass
    return "\n\n".join(context_parts)

def get_sql_from_ai_response(response_generator):
    full_response = "".join(list(response_generator))
    match = re.search(r"```sql\n(.*?)\n```", full_response, re.DOTALL)
    return match.group(1).strip() if match else full_response.strip()

@st.cache_resource(show_spinner=False)
def get_db_context_cached(_engine):
    return get_database_context(_engine)

def run_analysis_pipeline(prompt, engine, user_question, db_context):
    generated_sql = get_sql_from_ai_response(get_ai_response(prompt))
    for attempt in range(2):
        try:
            df = pd.read_sql(text(generated_sql), engine)
            report_prompt = load_prompt("prompts/final_analyst.txt").format(user_question=user_question, data_frame=df.to_markdown())
            full_report = "".join(list(get_ai_response(report_prompt)))
            return full_report
        except Exception as e:
            if attempt < 1:
                corrector_prompt = load_prompt("prompts/sql_corrector.txt").format(user_question=user_question, db_context=db_context, faulty_sql=generated_sql, error_message=str(e))
                generated_sql = get_sql_from_ai_response(get_ai_response(corrector_prompt))
            else:
                st.error(f"분석 실패: {e}")
                st.code(generated_sql, language='sql')
                st.stop()
    return None

# --- 세션 상태 관리 함수 (스레드 기반, 파일 I/O 추가) ---
def get_analysis_threads():
    if "analysis_threads" not in st.session_state:
        st.session_state.analysis_threads = load_threads_from_disk()
    return st.session_state.analysis_threads

def get_one_thread(thread_id):
    return next((t for t in get_analysis_threads() if t["id"] == thread_id), None)

def create_new_thread(question, report):
    threads = get_analysis_threads()
    new_thread = {
        "id": str(uuid.uuid4()),
        "title": truncate_text(question),
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": report}
        ]
    }
    threads.insert(0, new_thread)
    st.session_state.analysis_threads = threads
    save_threads_to_disk(threads)
    return new_thread["id"]

def add_message_to_thread(thread_id, role, content):
    threads = get_analysis_threads()
    thread = next((t for t in threads if t["id"] == thread_id), None)
    if thread:
        thread["messages"].append({"role": role, "content": content})
        save_threads_to_disk(threads)

def delete_thread(thread_id):
    threads = get_analysis_threads()
    st.session_state.analysis_threads = [t for t in threads if t["id"] != thread_id]
    save_threads_to_disk(st.session_state.analysis_threads)
    if st.session_state.get("selected_thread_id") == thread_id:
        st.session_state.current_view = "new_analysis"
        st.session_state.selected_thread_id = None

def clear_all_threads():
    st.session_state.analysis_threads = []
    save_threads_to_disk([])

# --- 메인 로직 ---
engine = get_db_engine()
if not engine:
    st.warning("데이터베이스에 연결할 수 없습니다.")
    st.stop()

db_context = get_db_context_cached(engine)

# 세션 상태 초기화
if 'current_view' not in st.session_state:
    st.session_state.current_view = "new_analysis"
if 'selected_thread_id' not in st.session_state:
    st.session_state.selected_thread_id = None

# --- 사이드바 ---
with st.sidebar:
    st.markdown("""
    <style>
    div[data-testid="stSidebar"] div[data-testid="stButton"] > button {
        white-space: nowrap;
    }
    </style>
    """, unsafe_allow_html=True)

    st.header("분석 관리")
    
    def go_to_new_analysis():
        st.session_state.current_view = "new_analysis"
        st.session_state.selected_thread_id = None

    st.button("✨ 새 분석 시작하기", on_click=go_to_new_analysis, use_container_width=True)
    st.subheader("분석 히스토리")
    
    threads = get_analysis_threads()

    def set_current_thread(thread_id):
        st.session_state.current_view = 'view_thread'
        st.session_state.selected_thread_id = thread_id

    for thread in threads:
        col1, col2 = st.columns([5, 1])
        with col1:
            col1.button(
                thread["title"], 
                key=f"view_{thread['id']}", 
                on_click=set_current_thread, 
                args=(thread['id'],),
                use_container_width=True
            )
        with col2:
            col2.button(
                "🗑️", 
                key=f"delete_{thread['id']}", 
                on_click=delete_thread, 
                args=(thread['id'],),
                help="이 스레드 삭제",
                use_container_width=True
            )

    if threads and st.button("🗑️ 모든 히스토리 삭제", use_container_width=True, type="primary"):
        clear_all_threads()
        go_to_new_analysis()
        st.rerun()

# --- 메인 화면 ---
if st.session_state.current_view == "view_thread" and st.session_state.selected_thread_id:
    thread = get_one_thread(st.session_state.selected_thread_id)
    if thread:
        # 대화 내용 출력
        for message in thread["messages"]:
            with st.chat_message(message["role"], avatar="❓" if message["role"] == "user" else "🤖"):
                st.markdown(message["content"])

        # 추가 질문 입력
        if follow_up_question := st.chat_input("이 분석에 대해 추가 질문하기"):
            add_message_to_thread(thread["id"], "user", follow_up_question)
            st.rerun()

        # 마지막 메시지가 사용자 질문이면 AI 답변 생성
        if thread["messages"] and thread["messages"][-1]["role"] == "user":
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("AI가 추가 분석을 진행중입니다..."):
                    last_user_question = thread["messages"][-1]["content"]
                    history = format_conversation_history(thread["messages"][:-1])
                    prompt = load_prompt("prompts/follow_up.txt").format(
                        db_context=db_context,
                        conversation_history=history,
                        follow_up_question=last_user_question
                    )
                    report = run_analysis_pipeline(prompt, engine, last_user_question, db_context)
                    if report:
                        add_message_to_thread(thread["id"], "assistant", report)
                        st.rerun()
    else: # 스레드가 삭제된 경우 등
        go_to_new_analysis()
        st.rerun()

elif st.session_state.current_view == "new_analysis":
    st.info("AI 애널리스트에게 분석을 요청하고 싶은 내용을 자연어로 질문해주세요. 새로운 분석은 히스토리에 자동으로 저장됩니다.")
    user_question = st.text_input("무엇이 궁금하신가요?", placeholder="예: 주차별 리텐션이 가장 높은 유저 그룹의 특징은?")
    
    if st.button("📈 분석 실행", key="run_analysis") and user_question:
        with st.spinner("AI가 첫번째 분석을 시작합니다..."):
            prompt = load_prompt("prompts/db_analyst.txt").format(db_context=db_context, user_question=user_question)
            report = run_analysis_pipeline(prompt, engine, user_question, db_context)
            if report:
                new_thread_id = create_new_thread(user_question, report)
                st.session_state.selected_thread_id = new_thread_id
                st.session_state.current_view = 'view_thread'
                st.rerun()
