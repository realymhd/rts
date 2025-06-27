from pathlib import Path
import streamlit as st
import time
from openai import OpenAI

@st.cache_data
def load_query(query_path: str) -> str:
    """지정된 경로의 쿼리 파일을 읽어와 문자열로 반환합니다."""
    try:
        with open(query_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"쿼리 파일을 찾을 수 없습니다: {query_path}")
        return ""

@st.cache_data
def load_prompt(prompt_path: str) -> str:
    """지정된 경로의 프롬프트 파일을 읽어와 문자열로 반환합니다."""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        st.error(f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}")
        return None

def get_ai_response(prompt):
    """
    OpenAI 라이브러리를 사용하여 OpenRouter API를 호출하고 응답을 스트리밍으로 받아옵니다.
    """
    try:
        api_key = st.secrets["openrouter"]["api_key"]
        
        # OpenRouter는 OpenAI SDK와 호환됩니다.
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        
        stream = client.chat.completions.create(
            model="google/gemini-2.5-flash-preview-05-20",
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )

        # 스트리밍 응답을 처리하기 위한 제너레이터 함수
        def stream_generator():
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
                    time.sleep(0.01) # UI 렌더링을 위한 약간의 지연

        return stream_generator()

    except Exception as e:
        st.error(f"AI 응답을 가져오는 데 실패했습니다: {e}")
        return None 