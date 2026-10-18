# 생성: 2026-10-18 17:12 KST
"""비밀 값 읽기와 DB 연결 풀. 비밀 값은 절대 출력하지 않는다."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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


def make_pool(url: str, max_size: int = 5) -> ConnectionPool:
    """연결 풀. 앱은 이것을 한 번만 만들어 재사용한다(PRD 7.2절).
    prepare_threshold=None: Supabase 트랜잭션 모드 풀러와 맞추려고 준비된 문장을 끈다."""
    return ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        timeout=20,
        open=True,
        kwargs={"prepare_threshold": None, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
    )
