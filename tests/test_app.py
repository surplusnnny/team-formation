# 생성: 2026-10-18 17:34 KST
import pytest
from streamlit.testing.v1 import AppTest

import service
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


def test_student_apply_and_vote_buttons(pool):
    load(pool, "easy.csv", 3)
    at = new_app()
    login(at, "2026104", "1234")
    service.apply(pool, "2026101", 1)
    at.button(key="apply_1").click()
    at.run()
    assert "대기: 팀1 팀원 1명의 투표를 기다림" in texts(at)
    assert at.button(key="apply_2").disabled  # 결과를 기다리는 지원이 있으면 비활성

    voter = new_app()
    login(voter, "2026101", "1234")
    assert "vote_yes_2026104" in keys(voter, "button")
    voter.button(key="vote_yes_2026104").click()
    voter.run()
    assert "승인: 학생4(WP;FD)이(가) 팀1에 들어감" in texts(voter)
    assert "vote_yes_2026104" not in keys(voter, "button")


def test_my_vote_is_shown_instead_of_buttons(pool):
    load(pool, "easy.csv", 3)
    service.apply(pool, "2026101", 1)
    service.apply(pool, "2026104", 1)
    service.vote(pool, "2026101", "2026104", "찬성")
    service.apply(pool, "2026107", 1)
    service.vote(pool, "2026101", "2026107", "찬성")
    at = new_app()
    login(at, "2026101", "1234")
    assert "내 투표: 찬성" in texts(at)
    assert "vote_yes_2026107" not in keys(at, "button")
    other = new_app()
    login(other, "2026104", "1234")
    assert {"vote_yes_2026107", "vote_no_2026107"} <= keys(other, "button")


def test_admin_close_button(pool):
    load(pool, "easy.csv", 3)
    at = new_app()
    login(at, "admin", get_secret("ADMIN_PASSWORD"))
    at.button(key="admin_close").click()
    at.run()
    assert "승인: 모집을 마감함" in texts(at)


def test_student_session_after_roster_reset(pool):
    load(pool, "easy.csv", 3)
    at = new_app()
    login(at, "2026101", "1234")
    load(pool, "medium.csv", 4)
    at.run()
    assert "지금 명단에 없는 학번임" in texts(at)
    assert not at.exception


def test_admin_assign_and_confirm_without_ai(pool, monkeypatch):
    monkeypatch.setattr(service.ai_assign, "MODELS", ())  # 시험에서는 AI를 부르지 않음 → 앱의 자체 배정
    load(pool, "easy.csv", 3)
    service.close(pool, "admin")  # 팀원이 없으므로 8명 모두 배정 대상
    at = new_app()
    login(at, "admin", get_secret("ADMIN_PASSWORD"))
    at.button(key="admin_assign").click()
    at.run()
    assert "승인: 배정안을 만듦 – 앱이 스스로 배정함" in texts(at)
    at.button(key="admin_confirm").click()
    at.run()
    assert "승인: 배정안을 확정함 (8명)" in texts(at)


def test_admin_sees_no_valid_assignment(pool):
    csv = "student_no,name,main_role,sub_roles\n9000001,가상1,기획자,\n9000002,가상2,테스터,\n"
    service.start_roster(pool, "admin", csv.encode("utf-8"), 1)
    service.close(pool, "admin")
    at = new_app()
    login(at, "admin", get_secret("ADMIN_PASSWORD"))
    at.button(key="admin_assign").click()
    at.run()
    assert "규칙을 지키는 배정이 없음" in texts(at)
    assert "팀1에 웹 프로그래머를 맡을 학생이 없음" in texts(at)
