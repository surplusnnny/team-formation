# 생성: 2026-10-18 17:14 KST
"""팀 편성 규칙(PRD 2장). DB와 화면을 모르는 순수 함수만 둔다."""
from __future__ import annotations

from dataclasses import dataclass

ROLES = ("기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자")
PLANNER = "기획자"
WEB = "웹 프로그래머"
REQUIRED = (PLANNER, WEB)
MIN_TEAM = 2
MAX_TEAM = 4


@dataclass(frozen=True)
class Student:
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...] = ()

    def can(self, role: str) -> bool:
        return self.main_role == role or role in self.sub_roles


def filled_required(members) -> int:
    """기획자 자리와 웹 프로그래머 자리에 서로 다른 팀원을 앉힐 수 있는 최대 수(0~2)."""
    planners = {i for i, m in enumerate(members) if m.can(PLANNER)}
    webs = {i for i, m in enumerate(members) if m.can(WEB)}
    if planners and webs:
        return 2 if len(planners | webs) >= 2 else 1
    return 1 if planners or webs else 0


def missing_required(members) -> int:
    return len(REQUIRED) - filled_required(members)


def join_block_reason(members, applicant) -> str | None:
    """지원자가 이 팀에 들어갈 수 없는 이유. 들어갈 수 있으면 None(PRD 3.1절 4~6, 3.3절)."""
    if len(members) >= MAX_TEAM:
        return "팀이 꽉 참"
    if any(m.main_role == applicant.main_role for m in members):
        return "같은 주 역할의 팀원이 있음"
    after = [*members, applicant]
    if MAX_TEAM - len(after) < missing_required(after):
        return "필수 포함 역할을 맡을 학생의 자리가 모자람"
    return None


def required_problem(members) -> str | None:
    if filled_required(members) == len(REQUIRED):
        return None
    no_planner = not any(m.can(PLANNER) for m in members)
    no_web = not any(m.can(WEB) for m in members)
    if no_planner and no_web:
        return "기획자와 웹 프로그래머를 맡을 학생이 없음"
    if no_planner:
        return "기획자를 맡을 학생이 없음"
    if no_web:
        return "웹 프로그래머를 맡을 학생이 없음"
    return "기획자와 웹 프로그래머를 서로 다른 학생이 맡을 수 없음"


def team_problems(team_no: int, members) -> list[str]:
    """확정할 팀 하나가 PRD 2.2절 규칙을 어기는 점."""
    problems = []
    if not MIN_TEAM <= len(members) <= MAX_TEAM:
        problems.append(f"팀{team_no} 인원 {len(members)}명(2~4명이어야 함)")
    counts: dict[str, int] = {}
    for m in members:
        counts[m.main_role] = counts.get(m.main_role, 0) + 1
    for role, n in counts.items():
        if n >= 2:
            problems.append(f"팀{team_no}에 주 역할 {role}이(가) 2명 이상")
    req = required_problem(members)
    if req:
        problems.append(f"팀{team_no}에 {req}")
    return problems


def validate_assignment(teams, unassigned, pairs) -> list[str]:
    """배정안 검사 다섯 가지(PRD 4.3절). 문제가 없으면 빈 목록."""
    problems: list[str] = []
    waiting = {s.student_no: s for s in unassigned}
    placed: dict[str, int] = {}
    for student_no, team_no in pairs:
        if student_no not in waiting:
            problems.append(f"팀이 없는 학생이 아닌 학번이 배정됨: {student_no}")
        elif team_no not in teams:
            problems.append(f"없는 팀 번호: 팀{team_no}")
        elif student_no in placed:
            problems.append(f"한 학생이 두 번 배정됨: {waiting[student_no].name}")
        else:
            placed[student_no] = team_no
    for s in unassigned:
        if s.student_no not in placed:
            problems.append(f"배정되지 않은 학생: {s.name}")
    final = {t: list(ms) for t, ms in teams.items()}
    for student_no, team_no in placed.items():
        final[team_no].append(waiting[student_no])
    for t in sorted(final):
        problems.extend(team_problems(t, final[t]))
    return problems
