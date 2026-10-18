# 생성: 2026-10-18 17:34 KST
import threading

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


def test_apply_to_empty_team_is_approved_at_once(pool):
    load(pool, "easy.csv", 3)
    assert service.apply(pool, "2026101", 1).text == "승인: 팀1에 들어감"
    assert service.load_state(pool).team_no_of("2026101") == 1


def test_apply_to_team_with_members_waits(pool):
    load(pool, "easy.csv", 3)
    service.apply(pool, "2026101", 1)
    out = service.apply(pool, "2026104", 1)
    assert out.text == "대기: 팀1 팀원 1명의 투표를 기다림"
    assert service.load_state(pool).pending_of("2026104").team_no == 1


def test_apply_blocks(pool):
    load(pool, "easy.csv", 3)
    service.apply(pool, "2026101", 1)
    assert service.apply(pool, "2026102", 1).text == "막힘: 같은 주 역할의 팀원이 있음"
    assert service.apply(pool, "2026101", 2).text == "막힘: 이미 팀이 있음"
    service.apply(pool, "2026104", 1)
    assert service.apply(pool, "2026104", 2).text == "막힘: 결과를 기다리는 지원이 있음"
    assert service.apply(pool, "2026105", 9).text == "막힘: 팀9이(가) 없음"
    assert service.apply(pool, "admin", 2).text == "막힘: 학생만 지원할 수 있음"


def test_all_yes_approves_and_one_no_rejects(pool):
    load(pool, "easy.csv", 3)
    service.apply(pool, "2026101", 1)
    service.apply(pool, "2026104", 1)
    assert service.vote(pool, "2026101", "2026104", "찬성").text == "승인: 학생4(WP;FD)이(가) 팀1에 들어감"
    service.apply(pool, "2026107", 1)
    assert service.vote(pool, "2026101", "2026107", "찬성").text == "대기: 찬성 1/2명"
    assert service.vote(pool, "2026104", "2026107", "거부").text == "거절: 팀원이 거부함"
    assert service.load_state(pool).pending_of("2026107") is None


def test_vote_rules(pool):
    load(pool, "easy.csv", 3)
    service.apply(pool, "2026101", 1)
    service.apply(pool, "2026104", 1)
    assert service.vote(pool, "2026102", "2026104", "찬성").text == "막힘: 이 팀의 팀원만 투표할 수 있음"
    assert service.vote(pool, "2026101", "2026105", "찬성").text == "막힘: 대기 중인 지원이 없음"
    service.apply(pool, "2026102", 2)
    service.apply(pool, "2026105", 2)
    service.apply(pool, "2026108", 2)
    assert service.vote(pool, "2026102", "2026105", "찬성").kind == "승인"
    assert service.vote(pool, "2026102", "2026108", "찬성").text == "대기: 찬성 1/2명"
    assert service.vote(pool, "2026102", "2026108", "거부").text == "막힘: 이미 투표함(내 투표: 찬성)"


def test_member_who_joined_later_also_votes(pool):
    load(pool, "hard.csv", 4)
    service.apply(pool, "2026302", 2)
    service.apply(pool, "2026308", 2)
    service.vote(pool, "2026302", "2026308", "찬성")
    service.apply(pool, "2026305", 2)
    service.apply(pool, "2026306", 2)
    assert service.vote(pool, "2026302", "2026305", "찬성").kind == "대기"
    assert service.vote(pool, "2026308", "2026305", "찬성").kind == "승인"
    # 학생5가 팀원이 되었으므로 학생6의 지원에는 세 명이 투표한다
    assert service.vote(pool, "2026302", "2026306", "찬성").text == "대기: 찬성 1/3명"
    assert service.vote(pool, "2026308", "2026306", "찬성").text == "대기: 찬성 2/3명"
    out = service.vote(pool, "2026305", "2026306", "찬성")
    assert out.text == "거절: 승인 직전 검사 – 같은 주 역할의 팀원이 있음"


def test_close_rejects_pending_and_removes_lonely_members(pool):
    load(pool, "medium.csv", 4)
    service.apply(pool, "2026203", 3)
    service.apply(pool, "2026211", 4)
    service.apply(pool, "2026212", 4)
    assert service.close(pool, "2026201").text == "막힘: 관리자만 할 수 있음"
    assert service.close(pool, "admin").text == "승인: 모집을 마감함 (대기 지원 1건 거절, 팀에서 빠진 학생 2명)"
    state = service.load_state(pool)
    assert state.closed and state.pending == []
    assert {"학생3(PL;RW)", "학생11(RW)", "학생12(PT;RW;FD)"} <= {s.name for s in state.unassigned()}
    assert service.close(pool, "admin").text == "막힘: 이미 마감됨"
    assert service.apply(pool, "2026202", 3).text == "막힘: 모집이 마감됨"


def test_two_students_apply_to_empty_team_at_once(pool):
    load(pool, "easy.csv", 3)
    barrier = threading.Barrier(2)
    results = {}

    def go(no):
        barrier.wait()
        results[no] = service.apply(pool, no, 1).kind

    threads = [threading.Thread(target=go, args=(no,)) for no in ("2026101", "2026104")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results.values()) == ["대기", "승인"]
    assert len(service.load_state(pool).team_map()[1]) == 1
