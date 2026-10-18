# 생성: 2026-10-18 18:17 KST
"""매일 한 번 DB에 질의해 Supabase 무료 프로젝트가 일시정지되지 않게 한다(GitHub Actions가 실행).
DB 주소는 출력하지 않는다. 커밋을 만들지 않는다."""
import os
import sys

import psycopg

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL: 없음")
with psycopg.connect(url, prepare_threshold=None, connect_timeout=30) as conn:
    conn.execute(
        """insert into tf_settings (key, value) values ('last_keepalive', now()::text)
           on conflict (key) do update set value = excluded.value"""
    )
    students = conn.execute("select count(*) from tf_students").fetchone()[0]
print(f"keepalive 성공: tf_students 행 {students}개")
