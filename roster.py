# 생성: 2026-10-18 17:14 KST
"""명단 CSV 읽기(PRD 5절). BOM이 붙은 UTF-8도 읽는다."""
from __future__ import annotations

import csv
import io

from rules import ROLES, Student

HEADER = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(ValueError):
    pass


def _clean(cell: str) -> str:
    return " ".join(cell.split())


def parse_roster(data: bytes) -> list[Student]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("UTF-8 CSV가 아님") from None
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [_clean(c) for c in rows[0]] != HEADER:
        raise RosterError("1행 – 머리글은 student_no,name,main_role,sub_roles 이어야 함")
    students: list[Student] = []
    seen: set[str] = set()
    for line_no, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != 4:
            raise RosterError(f"{line_no}행 – 열이 {len(row)}개임(4개여야 함)")
        student_no, name, main, subs = (_clean(c) for c in row)
        if not student_no or not name:
            raise RosterError(f"{line_no}행 – 학번이나 이름이 비었음")
        if student_no.lower() == "admin":
            raise RosterError(f"{line_no}행 – admin은 관리자 학번이라 쓸 수 없음")
        if student_no in seen:
            raise RosterError(f"{line_no}행 – 학번 중복: {student_no}")
        if main not in ROLES:
            raise RosterError(f"{line_no}행 – 모르는 주 역할: {main}")
        sub_roles = tuple(_clean(s) for s in subs.split(";") if _clean(s))
        for role in sub_roles:
            if role not in ROLES:
                raise RosterError(f"{line_no}행 – 모르는 보조 역할: {role}")
        if main in sub_roles:
            raise RosterError(f"{line_no}행 – 주 역할과 같은 보조 역할: {main}")
        if len(set(sub_roles)) != len(sub_roles):
            raise RosterError(f"{line_no}행 – 같은 보조 역할이 두 번 있음")
        if len(sub_roles) > 2:
            raise RosterError(f"{line_no}행 – 보조 역할이 3개 이상")
        seen.add(student_no)
        students.append(Student(student_no, name, main, sub_roles))
    if not students:
        raise RosterError("학생이 없음")
    return students
