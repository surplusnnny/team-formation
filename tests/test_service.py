# 생성: 2026-10-18 17:34 KST
import pytest

import service
from conftest import DATA, load
from db import get_secret

pytestmark = pytest.mark.db


def test_admin_login_and_wrong_password(pool):
    assert service.login(pool, "admin", get_secret("ADMIN_PASSWORD")).is_admin
    assert service.login(pool, "admin", "틀린비밀번호") is None


def test_admin_password_is_refreshed_from_secret(pool):
    real = get_secret("ADMIN_PASSWORD")
    try:
        service.ensure_admin(pool, "시험용-임시-비밀번호")
        assert service.login(pool, "admin", "시험용-임시-비밀번호") is not None
        assert service.login(pool, "admin", real) is None
    finally:
        service.ensure_admin(pool, real)
    assert service.login(pool, "admin", real) is not None


def test_start_roster_creates_students_and_empty_teams(pool):
    load(pool, "easy.csv", 3)
    state = service.load_state(pool)
    assert len(state.students) == 8
    assert [t.name for t in state.teams] == ["팀1", "팀2", "팀3"]
    assert all(t.members == [] for t in state.teams)
    assert state.closed is False
    s1 = state.students["2026101"]
    assert (s1.name, s1.main_role, s1.sub_roles) == ("학생1(PL;RW)", "기획자", ("보고서 작성자",))
    assert len(state.unassigned()) == 8


def test_student_login_uses_1234(pool):
    load(pool, "easy.csv", 3)
    user = service.login(pool, "2026101", "1234")
    assert user == service.User("2026101", "학생1(PL;RW)", False)
    assert service.login(pool, "2026101", "0000") is None
    assert service.login(pool, "2026101", "") is None


def test_start_roster_keeps_admin_and_replaces_students(pool):
    load(pool, "easy.csv", 3)
    load(pool, "medium.csv", 4)
    state = service.load_state(pool)
    assert len(state.students) == 12 and len(state.teams) == 4
    assert service.login(pool, "admin", get_secret("ADMIN_PASSWORD")) is not None
    assert service.login(pool, "2026101", "1234") is None


def test_start_roster_rejects_bad_input(pool):
    assert service.start_roster(pool, "admin", b"no,name\n", 3).text.startswith("막힘: 1행")
    data = (DATA / "easy.csv").read_bytes()
    assert service.start_roster(pool, "admin", data, 0).text == "막힘: 팀 수는 1~10이어야 함"


def test_student_cannot_start_roster(pool):
    load(pool, "easy.csv", 3)
    out = service.start_roster(pool, "2026101", (DATA / "easy.csv").read_bytes(), 3)
    assert out.text == "막힘: 관리자만 할 수 있음"
