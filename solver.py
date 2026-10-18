# 생성: 2026-10-18 18:00 KST
"""앱의 자체 배정(PRD 4.4절): 모든 경우를 따져 규칙을 지키는 배정을 끝까지 찾는다."""
from __future__ import annotations

from rules import MAX_TEAM, MIN_TEAM, REQUIRED, missing_required, team_problems


def solve(teams, unassigned):
    """규칙을 모두 지키는 배정 [(학번, 팀 번호), …]. 없으면 None."""
    team_nos = sorted(teams)
    current = {t: list(teams[t]) for t in team_nos}

    def fits(t, s):
        members = current[t]
        return len(members) < MAX_TEAM and all(m.main_role != s.main_role for m in members)

    order = sorted(unassigned, key=lambda s: sum(fits(t, s) for t in team_nos))  # 갈 곳이 적은 학생부터
    pairs: list[tuple[str, int]] = []

    def dfs(i: int) -> bool:
        left = len(order) - i
        if sum(max(0, MIN_TEAM - len(current[t])) for t in team_nos) > left:
            return False
        if any(MAX_TEAM - len(current[t]) < missing_required(current[t]) for t in team_nos):
            return False
        if i == len(order):
            return all(not team_problems(t, current[t]) for t in team_nos)
        s = order[i]
        tried_empty = False
        for t in team_nos:
            if not fits(t, s):
                continue
            if not current[t]:  # 빈 팀끼리는 서로 같으므로 하나만 해 본다
                if tried_empty:
                    continue
                tried_empty = True
            current[t].append(s)
            pairs.append((s.student_no, t))
            if dfs(i + 1):
                return True
            current[t].pop()
            pairs.pop()
        return False

    return list(pairs) if dfs(0) else None


def infeasible_reasons(teams, unassigned) -> list[str]:
    """규칙을 지키는 배정이 없을 때 보여 줄 이유(PRD 4.5절)."""
    reasons: list[str] = []
    n = len(unassigned)
    seats = sum(MAX_TEAM - len(ms) for ms in teams.values())
    if n > seats:
        reasons.append(f"남는 자리 {seats}개보다 팀이 없는 학생 {n}명이 많음")
    need = sum(max(0, MIN_TEAM - len(ms)) for ms in teams.values())
    if n < need:
        reasons.append(f"2명이 안 되는 팀을 채우려면 {need}명이 필요한데 팀이 없는 학생은 {n}명임")
    for t in sorted(teams):
        members = teams[t]
        mains = {m.main_role for m in members}
        joinable = [s for s in unassigned if s.main_role not in mains]
        for role in REQUIRED:
            if not any(m.can(role) for m in members) and not any(s.can(role) for s in joinable):
                reasons.append(f"팀{t}에 {role}를 맡을 학생이 없음")
        if MAX_TEAM - len(members) < missing_required(members):
            reasons.append(f"팀{t}에 필수 포함 역할을 채울 자리가 모자람")
    return reasons or ["인원, 주 역할, 필수 포함 역할을 함께 만족하는 조합이 없음"]
