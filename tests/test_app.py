# 생성: 2026-10-18 17:34 KST
import pytest
from streamlit.testing.v1 import AppTest

from conftest import load
from db import get_secret

pytestmark = pytest.mark.db


def new_app():
    at = AppTest.from_file("../streamlit_app.py", default_timeout=60)
    at.run()
    return at


def login(at, no, password):
    at.text_input(key="login_student_no").input(no)
    at.text_input(key="login_password").input(password)
    at.button(key="login_submit").click()
    at.run()


def keys(at, kind):
    return {w.key for w in getattr(at, kind)}


def texts(at):
    return " ".join(str(x.value) for kind in ("markdown", "success", "info", "warning", "error") for x in getattr(at, kind))


def test_login_page_has_keys():
    at = new_app()
    assert {"login_student_no", "login_password"} <= keys(at, "text_input")
    assert "login_submit" in keys(at, "button")


def test_wrong_password_is_blocked(pool):
    load(pool, "easy.csv", 3)
    at = new_app()
    login(at, "2026101", "9999")
    assert "막힘: 학번 또는 비밀번호가 틀림" in texts(at)
    assert "apply_1" not in keys(at, "button")


def test_admin_sees_admin_controls(pool):
    at = new_app()
    login(at, "admin", get_secret("ADMIN_PASSWORD"))
    assert {"admin_start", "admin_close", "admin_assign", "admin_confirm"} <= keys(at, "button")
    assert "admin_team_count" in keys(at, "number_input")


def test_student_sees_teams_and_no_admin_controls(pool):
    load(pool, "easy.csv", 3)
    at = new_app()
    login(at, "2026101", "1234")
    assert {"apply_1", "apply_2", "apply_3"} <= keys(at, "button")
    assert "admin_start" not in keys(at, "button")
    assert "학생1(PL;RW)" in texts(at)
