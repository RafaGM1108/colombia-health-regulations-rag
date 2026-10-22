"""Streamlit app. Run with ``make app``."""

import streamlit as st

from colombia_health_rag.utils.config import get_config

config = get_config()

st.set_page_config(page_title=config.project.name)
st.title(config.project.name)
st.info("Informational only; not legal or medical advice.")
st.write("Regulation search and cited answers are planned for a later phase.")
