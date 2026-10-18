# 생성: 2026-10-18 17:12 KST
"""비밀 값 읽기와 DB 연결 풀. 비밀 값은 절대 출력하지 않는다."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)


def get_secret(name: str) -> str | None:
    """.env(환경 변수)에서 먼저 찾고, 없으면 Streamlit Secrets에서 찾는다."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return value or None
