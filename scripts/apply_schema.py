# 생성: 2026-10-18 17:15 KST
"""schema.sql 을 DB에 적용하고 tf_ 테이블 목록을 보여 준다. DB 주소는 출력하지 않는다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg

from db import get_secret

url = get_secret("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL: 없음")
sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
    conn.execute(sql)
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public' and table_name like 'tf\\_%' order by 1"
    ).fetchall()
print("tf_ 테이블:", ", ".join(r[0] for r in rows))
