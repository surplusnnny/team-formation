# 생성: 2026-10-18 17:14 KST
from rules import (
    Student,
    filled_required,
    join_block_reason,
    team_problems,
    validate_assignment,
)

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def S(no, main, *subs):
    return Student(no, f"가상{no}", main, tuple(subs))


def test_one_student_fills_only_one_required_role():
    assert filled_required([S("1", PL, WP)]) == 1


def test_two_students_fill_both_required_roles():
    assert filled_required([S("1", PL), S("2", TT, WP)]) == 2


def test_single_candidate_for_both_counts_once():
    assert filled_required([S("1", PL, WP), S("2", TT)]) == 1


def test_no_required_role():
    assert filled_required([S("1", TT), S("2", PT)]) == 0


def test_sub_role_can_fill_required_role():
    assert filled_required([S("1", TT, PL), S("2", FD, WP)]) == 2


def test_full_team_blocks():
    members = [S("1", PL), S("2", WP), S("3", FD), S("4", TT)]
    assert join_block_reason(members, S("9", RW)) == "팀이 꽉 참"


def test_same_main_role_blocks():
    assert join_block_reason([S("1", PL)], S("2", PL, TT)) == "같은 주 역할의 팀원이 있음"


def test_required_seat_shortage_blocks():
    # 테스터와 발표자만 있는 팀에 보고서 작성자가 지원하면 남는 1자리로 2개를 못 채움(PRD 2.3절 예)
    assert join_block_reason([S("1", TT), S("2", PT)], S("3", RW)) == "필수 포함 역할을 맡을 학생의 자리가 모자람"


def test_applicant_who_fills_a_required_role_is_not_blocked():
    assert join_block_reason([S("1", TT), S("2", PT)], S("3", RW, WP)) is None


def test_empty_team_accepts_anyone():
    assert join_block_reason([], S("1", RW)) is None


def test_team_problems_reports_size_duplicate_and_required():
    problems = team_problems(3, [S("1", TT), S("2", TT), S("3", PT), S("4", RW), S("5", FD)])
    assert "팀3 인원 5명(2~4명이어야 함)" in problems
    assert "팀3에 주 역할 테스터이(가) 2명 이상" in problems
    assert "팀3에 기획자와 웹 프로그래머를 맡을 학생이 없음" in problems


def test_team_problems_ok():
    assert team_problems(1, [S("1", PL), S("2", WP)]) == []


TEAMS = {1: [S("1", PL), S("2", WP)], 2: [S("3", PL)], 3: []}
WAITING = [S("4", WP), S("5", PL), S("6", WP, RW)]


def test_validate_assignment_passes():
    assert validate_assignment(TEAMS, WAITING, [("4", 2), ("5", 3), ("6", 3)]) == []


def test_validate_assignment_finds_each_problem():
    problems = validate_assignment(TEAMS, WAITING, [("4", 2), ("4", 3), ("1", 3), ("5", 9)])
    assert "한 학생이 두 번 배정됨: 가상4" in problems
    assert "팀이 없는 학생이 아닌 학번이 배정됨: 1" in problems
    assert "없는 팀 번호: 팀9" in problems
    assert "배정되지 않은 학생: 가상6" in problems
    assert "팀3 인원 0명(2~4명이어야 함)" in problems
