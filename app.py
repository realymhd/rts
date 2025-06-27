import streamlit as st

st.set_page_config(
    page_title="메인 대시보드",
    page_icon="👋",
    layout="wide"
)

st.title("👋 안녕하세요! 분석 대시보드에 오신 것을 환영합니다.")

st.sidebar.success("분석할 대시보드를 위에서 선택해주세요.")

st.markdown(
    """
    이 대시보드는 유저들의 서비스 사용 패턴을 분석하기 위한 다양한 기능을 제공합니다.

    ### 현재 제공되는 기능
    - **학습지 리텐션 분석**: 주차별 학생들의 제출 리텐션을 코호트 분석을 통해 확인합니다.
    
    ### 앞으로 추가될 기능
    - 챗봇 사용량 분석
    - 마타 패들렛 사용량 분석
    - 기타 등등...
    """
) 