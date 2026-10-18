# 생성: 2026-10-18 17:14 KST
from pathlib import Path

import pytest

from roster import RosterError, parse_roster

DATA = Path(__file__).parent / "data"
HEAD = "student_no,name,main_role,sub_roles\r\n"


def test_bom_crlf_and_spaces():
    text = (
        "﻿" + HEAD
        + "2026001, 가나다 , 기획자 , 보고서  작성자\r\n"
        + "2026002, 라마바 , 웹  프로그래머 ,\r\n"
        + "2026003, 사아자 , 테스터 , 기획자 ; 발표자\r\n"
        + "\r\n"
    )
    students = parse_roster(text.encode("utf-8"))
    assert [(s.student_no, s.name, s.main_role, s.sub_roles) for s in students] == [
        ("2026001", "가나다", "기획자", ("보고서 작성자",)),
        ("2026002", "라마바", "웹 프로그래머", ()),
        ("2026003", "사아자", "테스터", ("기획자", "발표자")),
    ]


@pytest.mark.parametrize("name, count", [("easy.csv", 8), ("medium.csv", 12), ("hard.csv", 16)])
def test_practice_rosters(name, count):
    assert len(parse_roster((DATA / name).read_bytes())) == count


@pytest.mark.parametrize(
    "line, message",
    [
        ("2026001,가나다,기획자", "2행 – 열이 3개임(4개여야 함)"),
        ("2026001,가나다,요리사,", "2행 – 모르는 주 역할: 요리사"),
        ("2026001,가나다,기획자,요리사", "2행 – 모르는 보조 역할: 요리사"),
        ("2026001,가나다,기획자,기획자", "2행 – 주 역할과 같은 보조 역할: 기획자"),
        ("2026001,가나다,기획자,테스터;발표자;웹 프로그래머", "2행 – 보조 역할이 3개 이상"),
        (",가나다,기획자,", "2행 – 학번이나 이름이 비었음"),
        ("admin,가나다,기획자,", "2행 – admin은 관리자 학번이라 쓸 수 없음"),
    ],
)
def test_bad_rows(line, message):
    with pytest.raises(RosterError) as err:
        parse_roster((HEAD + line + "\r\n").encode("utf-8"))
    assert str(err.value) == message


def test_duplicate_student_no():
    data = (HEAD + "2026001,가,기획자,\r\n2026001,나,테스터,\r\n").encode("utf-8")
    with pytest.raises(RosterError, match="3행 – 학번 중복: 2026001"):
        parse_roster(data)


def test_bad_header_and_empty():
    with pytest.raises(RosterError, match="1행 – 머리글"):
        parse_roster("no,name\r\n".encode("utf-8"))
    with pytest.raises(RosterError, match="학생이 없음"):
        parse_roster(HEAD.encode("utf-8"))
