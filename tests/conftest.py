# 생성: 2026-10-18 17:34 KST
from pathlib import Path

import pytest

import service
from db import get_secret, make_pool

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def pool():
    url = get_secret("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 없음")
    p = make_pool(url, max_size=4)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def load(pool, name, team_count):
    out = service.start_roster(pool, service.ADMIN_NO, (DATA / name).read_bytes(), team_count)
    assert out.kind == "승인", out.text


@pytest.fixture(autouse=True)
def _drop_fake_ai_logs(request):
    """시험이 남긴 가짜 AI 기록은 지운다(배포한 앱의 현황과 README 근거에 섞이지 않게)."""
    yield
    if "pool" in request.fixturenames:
        with request.getfixturevalue("pool").connection() as conn:
            conn.execute("delete from tf_ai_logs where model like '가짜/%%'")
