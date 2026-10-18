# 생성: 2026-10-18 18:00 KST
"""공고 부록의 연습 시나리오 3개를 서비스 함수로 재생한다. 동작마다 결과의 첫 단어를 확인한다."""
from dataclasses import dataclass

import pytest

import rules
import service
from conftest import load

pytestmark = pytest.mark.db


@dataclass
class Apply:
    who: str
    team: int
    expect: str
    reason: str = ""


@dataclass
class Vote:
    who: str
    applicant: str
    choice: str
    expect: str
    reason: str = ""


@dataclass
class Close:
    expect: str = "승인"


@dataclass
class Unassigned:
    names: tuple


def play(pool, csv, team_count, steps):
    load(pool, csv, team_count)
    for i, step in enumerate(steps, start=1):
        if isinstance(step, Unassigned):
            names = {s.name for s in service.load_state(pool).unassigned()}
            assert set(step.names) <= names, f"{i}번째: {names}"
            continue
        if isinstance(step, Apply):
            got = service.apply(pool, step.who, step.team)
        elif isinstance(step, Vote):
            got = service.vote(pool, step.who, step.applicant, step.choice)
        else:
            got = service.close(pool, "admin")
        assert got.kind == step.expect, f"{i}번째 동작 {step}: {got.text}"
        assert getattr(step, "reason", "") in got.text, f"{i}번째 동작 {step}: {got.text}"
    plan = service.plan_assignment(pool, "admin", None)  # AI 없이 앱의 자체 배정으로 확정 뒤 규칙을 확인
    assert plan.outcome.kind == "승인", plan.outcome.text
    assert service.confirm(pool, "admin", plan.pairs).kind == "승인"
    state = service.load_state(pool)
    assert state.unassigned() == []
    for team in state.teams:
        assert rules.team_problems(team.team_no, team.members) == [], team


EASY = [
    Apply("2026101", 1, "승인"), Apply("2026102", 2, "승인"), Apply("2026103", 3, "승인"),
    Apply("2026104", 1, "대기"), Vote("2026101", "2026104", "찬성", "승인"),
    Apply("2026105", 2, "대기"), Vote("2026102", "2026105", "찬성", "승인"),
    Apply("2026107", 1, "대기"), Vote("2026101", "2026107", "찬성", "대기"), Vote("2026104", "2026107", "거부", "거절"),
    Apply("2026106", 3, "대기"), Vote("2026103", "2026106", "찬성", "승인"),
    Close(),
    Unassigned(("학생7(FD;PT)", "학생8(TT;RW;PT)")),
]

MEDIUM = [
    Apply("2026201", 1, "승인"),
    Apply("2026205", 1, "대기"), Vote("2026201", "2026205", "찬성", "승인"),
    Apply("2026202", 1, "막힘", "같은 주 역할"),
    Apply("2026206", 2, "승인"),
    Apply("2026209", 2, "대기"), Vote("2026206", "2026209", "찬성", "승인"),
    Apply("2026210", 2, "대기"), Vote("2026206", "2026210", "찬성", "대기"), Vote("2026209", "2026210", "거부", "거절"),
    Apply("2026203", 3, "승인"), Apply("2026211", 4, "승인"),
    Apply("2026212", 4, "대기"), Apply("2026212", 3, "막힘", "결과를 기다리는 지원"),
    Close(),
    Unassigned(("학생3(PL;RW)", "학생11(RW)", "학생12(PT;RW;FD)")),
    Apply("2026202", 3, "막힘", "마감"),
]

HARD = [
    Apply("2026301", 1, "승인"),
    Apply("2026304", 1, "대기"), Vote("2026301", "2026304", "찬성", "승인"),
    Apply("2026307", 1, "대기"), Vote("2026301", "2026307", "찬성", "대기"), Vote("2026304", "2026307", "찬성", "승인"),
    Apply("2026302", 2, "승인"),
    Apply("2026308", 2, "대기"), Vote("2026302", "2026308", "찬성", "승인"),
    Apply("2026305", 2, "대기"), Apply("2026306", 2, "대기"),
    Vote("2026302", "2026305", "찬성", "대기"), Vote("2026308", "2026305", "찬성", "승인"),
    Vote("2026302", "2026306", "찬성", "대기"), Vote("2026308", "2026306", "찬성", "대기"),
    Vote("2026305", "2026306", "찬성", "거절", "승인 직전 검사"),
    Apply("2026311", 3, "승인"),
    Apply("2026315", 3, "대기"), Vote("2026311", "2026315", "찬성", "승인"),
    Apply("2026314", 3, "막힘", "필수 포함 역할"),
    Apply("2026310", 4, "승인"),
    Apply("2026313", 1, "대기"), Vote("2026301", "2026313", "찬성", "대기"),
    Close(),
    Unassigned(("학생10(TT;RW)", "학생13(RW;PT;FD)")),
]


def test_easy(pool):
    play(pool, "easy.csv", 3, EASY)


def test_medium(pool):
    play(pool, "medium.csv", 4, MEDIUM)


def test_hard(pool):
    play(pool, "hard.csv", 4, HARD)
