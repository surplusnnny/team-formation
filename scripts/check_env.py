# 생성: 2026-10-18 17:12 KST
"""비밀 값이 있는지와 연결이 되는지만 확인한다. 값은 출력하지 않는다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import psycopg

from db import get_secret

NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")

for name in NAMES:
    print(f"{name}: {'있음' if get_secret(name) else '없음'}")

url = get_secret("DATABASE_URL")
if url:
    try:
        with psycopg.connect(url, prepare_threshold=None, connect_timeout=15) as conn:
            conn.execute("select 1")
        print("DB 연결: 성공")
    except Exception as exc:
        print(f"DB 연결: 실패 ({type(exc).__name__})")

key = get_secret("OPENROUTER_API_KEY")
if key:
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        print(f"오픈라우터 키 확인: HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        print(f"오픈라우터 키 확인: 실패 ({type(exc).__name__})")
