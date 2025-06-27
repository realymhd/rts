from pathlib import Path
import streamlit as st

@st.cache_data
def load_query(query_path: str) -> str:
    """지정된 경로의 쿼리 파일을 읽어와 문자열로 반환합니다."""
    try:
        return Path(query_path).read_text()
    except FileNotFoundError:
        st.error(f"쿼리 파일을 찾을 수 없습니다: {query_path}")
        return ""

@st.cache_data
def load_prompt(prompt_path: str) -> str:
    """지정된 경로의 프롬프트 파일을 읽어와 문자열로 반환합니다."""
    try:
        return Path(prompt_path).read_text()
    except FileNotFoundError:
        st.error(f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
        return "" 