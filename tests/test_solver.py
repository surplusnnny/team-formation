# 생성: 2026-10-18 18:00 KST
import time

from rules import Student, validate_assignment
from solver import infeasible_reasons, solve

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def S(no, main, *subs):
    return Student(no, f"가상{no}", main, tuple(subs))


def test_needs_sub_roles_to_solve():
    # 부록 3 마감 직후와 같은 모양: 빈 팀이 하나 있고 보조 역할을 써야만 풀림
    teams = {
        1: [S("1", PL, RW), S("4", WP, PL), S("7", FD, PT, TT)],
        2: [S("2", PL, PT), S("8", FD, TT), S("5", WP, FD)],
        3: [S("11", TT, PT), S("15", PT, FD)],
        4: [],
    }
    waiting = [S("3", PL, TT), S("6", WP, RW), S("9", FD, WP), S("10", TT, RW),
               S("12", TT, PL), S("13", RW, PT, FD), S("14", RW, TT), S("16", PT)]
    pairs = solve(teams, waiting)
    assert pairs is not None
    assert validate_assignment(teams, waiting, pairs) == []


def test_no_solution_and_reason():
    teams = {1: [S("1", PL)], 2: []}
    waiting = [S("2", TT), S("3", PT)]
    assert solve(teams, waiting) is None
    assert "팀1에 웹 프로그래머를 맡을 학생이 없음" in infeasible_reasons(teams, waiting)


def test_seat_and_headcount_reasons():
    teams = {1: [S("1", PL), S("2", WP), S("3", FD), S("4", TT)]}
    assert "남는 자리 0개보다 팀이 없는 학생 1명이 많음" in infeasible_reasons(teams, [S("5", RW)])
    teams = {1: [], 2: []}
    assert "2명이 안 되는 팀을 채우려면 4명이 필요한데 팀이 없는 학생은 3명임" in infeasible_reasons(
        teams, [S("1", PL), S("2", WP), S("3", TT, PL)]
    )


def test_fallback_reason():
    # 팀마다 웹 프로그래머 후보는 있지만 같은 한 사람이라 두 팀을 함께 채울 수 없음
    teams = {1: [S("1", PL)], 2: [S("2", PL)]}
    waiting = [S("3", WP), S("4", TT)]
    assert solve(teams, waiting) is None
    assert infeasible_reasons(teams, waiting) == ["인원, 주 역할, 필수 포함 역할을 함께 만족하는 조합이 없음"]


def test_eight_students_into_four_empty_teams_is_fast():
    waiting = [S("1", PL), S("2", WP), S("3", PL), S("4", WP), S("5", TT, PL), S("6", FD, WP), S("7", RW, PL), S("8", PT, WP)]
    teams = {1: [], 2: [], 3: [], 4: []}
    start = time.monotonic()
    pairs = solve(teams, waiting)
    assert time.monotonic() - start < 2
    assert validate_assignment(teams, waiting, pairs) == []


def test_nothing_to_assign_but_teams_valid():
    teams = {1: [S("1", PL), S("2", WP)]}
    assert solve(teams, []) == []
