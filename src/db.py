import streamlit as st
from sqlalchemy import create_engine

@st.cache_resource(ttl="1h")
def get_db_engine():
    """
    데이터베이스 연결을 위한 SQLAlchemy 엔진을 생성하고 캐싱합니다.
    Streamlit의 st.cache_resource를 사용하여 앱 전체에서 단일 연결을 유지합니다.
    """
    try:
        db_creds = st.secrets["database"]
        engine = create_engine(
            f"mysql+pymysql://{db_creds['user']}:{db_creds['password']}@{db_creds['host']}:{db_creds['port']}/{db_creds['dbname']}"
        )
        return engine
    except Exception as e:
        st.error(f"데이터베이스 연결에 실패했습니다: {e}")
        st.warning("'.streamlit/secrets.toml' 파일의 연결 정보를 확인해주세요.")
        return None 