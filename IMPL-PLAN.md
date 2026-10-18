<!-- 생성: 2026-10-18 17:00 KST -->
# 팀 편성 웹 앱 구현 계획서

> **실행자에게:** 이 계획은 `superpowers:executing-plans`로 **이 세션에서 직접** 실행한다. 단계(1~5단계)가 끝날 때마다 **멈추고**, 사용자가 "브라우저 확인 항목"을 확인한 뒤에 다음 단계로 넘어간다. 계획과 다르게 정해야 할 일이 생기면 정하기 전에 사용자에게 먼저 묻는다. 각 과제(Task)의 단계는 체크박스(`- [ ]`)로 따라간다.

**목표:** 학생이 지원과 투표로 팀을 꾸리고, 마감 뒤 남은 학생을 AI가 배정하며, 앱이 그 배정을 규칙으로 검사하는 Streamlit 웹 앱을 만들어 Streamlit Community Cloud에 배포한다.

**구조:** 규칙 판정(`rules.py`, `solver.py`, `roster.py`)은 DB와 화면을 모르는 순수 파이썬이다. `service.py`가 Postgres(Supabase) 트랜잭션 안에서 팀 행을 잠그고 규칙을 검사·기록하며, `streamlit_app.py`는 화면만 맡는다. AI 호출(`ai_assign.py`)은 모델마다 120초 전체 제한을 직접 재고 1·2·3차로 넘어간다.

**기술:** Python 3.12~3.13, Streamlit 1.66.0, psycopg 3.3.6 + psycopg-pool 3.3.3, bcrypt 5.0.0, httpx 0.28.1, python-dotenv 1.2.4, pytest 9.1.1

**근거 문서:** `PRD.md`(이 계획은 PRD의 절 번호를 따른다. 실행자는 이 계획과 PRD를 함께 읽는다)

## 전역 제약

- 화면 요소의 Streamlit `key`는 PRD 6.1절 표와 글자 하나까지 같아야 한다: `login_student_no`, `login_password`, `login_submit`, `whoami`, `result`, `team_{n}`, `apply_{n}`, `vote_yes_{학번}`, `vote_no_{학번}`, `admin_roster_file`, `admin_team_count`, `admin_start`, `admin_close`, `unassigned`, `admin_assign`, `assign_status`, `admin_confirm`
- `result` 안내는 `승인`, `대기`, `거절`, `막힘` 가운데 하나로 시작한다
- 테이블 이름은 모두 `tf_`로 시작한다
- `OPENROUTER_API_KEY`, `DATABASE_URL`, `ADMIN_PASSWORD`는 `.env`(로컬) 또는 Streamlit Secrets(배포)에서만 읽는다. 코드·화면·로그·커밋 어디에도 값을 쓰지 않는다. 확인할 때는 `있음`/`없음`만 출력한다
- 학생 비밀번호는 모두 `1234`, bcrypt(rounds=10) 해시로 저장한다
- 무료 모델 자동 라우터 `openrouter/free`는 쓰지 않는다
- 앱 코드에는 연습 시나리오의 이름·학번·순서에 맞춘 처리를 두지 않는다(시나리오는 `tests/`에만 둔다)
- 화면에 보이는 시각은 한국 시각(UTC+9)으로 바꾼다
- 새 파일 첫 줄(첫 줄이 정해진 파일은 둘째 줄)에 `생성: YYYY-MM-DD HH:MM KST` 주석을 단다. 시각은 `TZ=KST-9 date '+%Y-%m-%d %H:%M'`로 확인한다. JSON·CSV에는 달지 않는다
- 커밋 작성자는 `surplusnnny <291572747+surplusnnny@users.noreply.github.com>`(이 저장소에만 설정됨). 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- 2026-11-02 23:59 KST 뒤에는 저장소에 커밋하지 않는다
- 시험(`tests/`)의 DB 시험은 실제 Supabase의 `tf_` 데이터를 지우고 다시 만든다. 채점 기간(11/3~11/4)에는 DB 시험을 돌리지 않는다

## 검토 초점(시험이 따로 짚지 않으면 사람이 먼저 부딪힐 것)

1. 엑셀로 저장한 CSV(CRLF 줄바꿈, 끝의 빈 줄, BOM, 칸 안 공백 두 칸) → 그대로 읽혀야 함. Task 3의 `test_bom_crlf_and_spaces`가 짚음
2. 두 학생이 같은 순간 빈 팀에 지원 → 한 명만 승인, 다른 한 명은 대기. Task 9의 `test_two_students_apply_to_empty_team_at_once`가 짚음
3. 명단을 다시 올린 뒤에도 로그인해 있던 학생의 화면 → 오류 없이 "지금 명단에 없는 학번임"을 보여야 함. Task 10의 `test_student_session_after_roster_reset`이 짚음
4. AI가 학번을 숫자로, 팀 번호를 `"팀2"` 글자로 답함 → 읽어 들여야 함. Task 12의 `test_parse_pairs_accepts_loose_types`가 짚음
5. 배정안을 받은 뒤 명단을 다시 올리고 예전 배정안을 확정 → 막혀야 함. Task 15의 `test_confirm_rejects_stale_plan`이 짚음

---

## 파일 구조

| 파일 | 맡는 일 |
|---|---|
| `rules.py` | 역할 상수, `Student`, 필수 역할 짝짓기, 지원 막힘 이유, 팀 문제점, 배정안 5가지 검사 |
| `roster.py` | 명단 CSV 읽기(`utf-8-sig`, 공백 정리, 오류 행 안내) |
| `solver.py` | 전수 탐색 배정, 배정이 없을 때의 이유 |
| `db.py` | 비밀 값 읽기(`.env` → Streamlit Secrets), 연결 풀 만들기 |
| `service.py` | DB 트랜잭션 단위 동작: 관리자 계정, 로그인, 명단 올리기, 상태 읽기, 지원, 투표, 마감, 배정안 만들기, 확정, AI 기록 |
| `ai_assign.py` | 프롬프트, 오픈라우터 스트리밍 호출(모델별 120초 전체 제한), 응답 해석, 1·2·3차 넘김 |
| `streamlit_app.py` | 로그인, 학생 화면, 관리자 화면(key는 PRD 6.1절) |
| `schema.sql` | `tf_` 테이블과 제약 |
| `scripts/check_env.py` | 비밀 값 있음/없음, DB·오픈라우터 연결 확인(값은 출력하지 않음) |
| `scripts/apply_schema.py` | `schema.sql`을 DB에 적용 |
| `scripts/try_models.py` | 1·2·3차 모델 후보를 실제로 불러 보기 |
| `scripts/keepalive.py` | 매일 DB에 질의(GitHub Actions가 실행) |
| `.github/workflows/keepalive.yml` | 예약 실행 |
| `tests/` | `test_rules.py`, `test_roster.py`, `test_solver.py`, `test_ai_assign.py`, `test_service.py`, `test_scenarios.py`, `test_app.py`, `conftest.py`, `data/easy.csv`, `data/medium.csv`, `data/hard.csv` |
| `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.env.example`, `CLAUDE.md`, `README.md`, `docs/cases.md` | 설정과 문서 |

## 단계 개요

| 단계 | 브랜치 | 과제 | 끝나면 사용자가 확인할 것 |
|---|---|---|---|
| 1단계: 기반(환경, 규칙, DB, 로그인, 명단 올리기) | `stage-1` | Task 1~6 | 로그인, 명단 올리기, 빈 팀 표시 |
| 2단계: 지원, 투표, 마감, 자동 갱신 | `stage-2` | Task 7~10 | 쉬움 시나리오 1~5단계와 마감 |
| 3단계: 배정(탐색, AI, 확정) | `stage-3` | Task 11~16 | 연습 시나리오 3개를 끝까지 |
| 4단계: 배포와 DB 일시정지 막기 | `stage-4` | Task 17~19 | 배포 주소에서 쉬움 시나리오 |
| 5단계: 문서와 제출물 | `stage-5` | Task 20~21 | README, zip |

단계마다: 시작할 때 `main`에서 단계 브랜치를 만들고, 과제마다 시험이 통과하면 그 브랜치에 커밋한다. 단계가 끝나면 멈추고 확인 항목을 보고한다. 사용자가 확인을 마치면 `git merge --no-ff stage-N`으로 `main`에 합친다(4단계부터는 합친 뒤 `git push`).

---

# 1단계: 기반

### Task 1: 개발 환경, 비밀 값, 프로젝트 지침

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `.env.example`, `CLAUDE.md`, `docs/cases.md`, `scripts/check_env.py`, `db.py`(비밀 값 부분), `.claude/launch.json`(커밋하지 않음)

**Interfaces:**
- Produces: `db.get_secret(name: str) -> str | None`, `db.ENV_PATH: Path`

- [ ] **Step 1: 단계 브랜치 만들기**

```bash
git switch -c stage-1
```

- [ ] **Step 2: 의존성 파일**

`requirements.txt`(Streamlit Cloud가 읽음):
```text
# 생성: <KST 시각>
streamlit==1.66.0
psycopg[binary]==3.3.6
psycopg-pool==3.3.3
bcrypt==5.0.0
httpx==0.28.1
python-dotenv==1.2.4
```

`requirements-dev.txt`:
```text
# 생성: <KST 시각>
-r requirements.txt
pytest==9.1.1
```

`pytest.ini`:
```ini
# 생성: <KST 시각>
[pytest]
pythonpath = .
testpaths = tests
markers =
    db: 실제 DB(Supabase)를 쓰는 시험
```

- [ ] **Step 3: 가상 환경과 설치**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements-dev.txt
.venv\Scripts\python -c "import inspect, streamlit as st; print(st.__version__, 'form_submit_button key:', 'key' in inspect.signature(st.form_submit_button).parameters, 'container key:', 'key' in inspect.signature(st.container).parameters, 'fragment run_every:', 'run_every' in inspect.signature(st.fragment).parameters)"
```
Expected: `1.66.0 form_submit_button key: True container key: True fragment run_every: True`. 하나라도 `False`면 멈추고 사용자에게 알린다(key 지정 방법을 다시 정해야 함).

- [ ] **Step 4: `.env.example`과 `.env` 안내**

`.env.example`(커밋함, 값 없음):
```text
# 생성: <KST 시각>
# 이 파일을 .env 로 복사하고 값을 채운다. .env 는 커밋하지 않는다.
OPENROUTER_API_KEY="sk-or-v1-..."
DATABASE_URL="postgresql://postgres.<프로젝트ref>:<DB비밀번호>@aws-0-<지역>.pooler.supabase.com:6543/postgres"
ADMIN_PASSWORD="정한 관리자 비밀번호"
```

사용자에게 안내한다(사용자가 직접 함. 값은 채팅에 붙이지 않음):
1. **Supabase**: supabase.com에 로그인해 6장용 프로젝트가 있으면 그것을, 없으면 새 프로젝트 1개를 만든다(무료는 2개까지). 대시보드 위쪽 **Connect** → **Connection string** → **Transaction pooler**(포트 6543) 주소를 복사하고 `[YOUR-PASSWORD]`를 DB 비밀번호로 바꾼다. Streamlit Cloud는 IPv6 직결 주소(`db.<ref>.supabase.co`)에 붙지 못할 수 있으므로 풀러 주소를 쓴다
2. **OpenRouter**: openrouter.ai에 가입 → **Keys** → **Create Key** → `sk-or-v1-…` 복사
3. **관리자 비밀번호**: 직접 정한다(채점 기간에 바꾸면 안 됨)
4. 작업 폴더에서 `.env.example`을 `.env`로 복사해 메모장으로 세 값을 넣는다. 파일 이름이 `.env.txt`가 되지 않게 한다. `.env`를 두 번 눌러 열지 않는다

- [ ] **Step 5: `db.py`의 비밀 값 부분**

```python
# 생성: <KST 시각>
"""비밀 값 읽기와 DB 연결 풀. 비밀 값은 절대 출력하지 않는다."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH)


def get_secret(name: str) -> str | None:
    """.env(환경 변수)에서 먼저 찾고, 없으면 Streamlit Secrets에서 찾는다."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return value or None
```

- [ ] **Step 6: `scripts/check_env.py`**(값을 출력하지 않는 확인 도구)

```python
# 생성: <KST 시각>
"""비밀 값이 있는지와 연결이 되는지만 확인한다. 값은 출력하지 않는다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import psycopg

from db import get_secret

NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")

for name in NAMES:
    print(f"{name}: {'있음' if get_secret(name) else '없음'}")

url = get_secret("DATABASE_URL")
if url:
    try:
        with psycopg.connect(url, prepare_threshold=None, connect_timeout=15) as conn:
            conn.execute("select 1")
        print("DB 연결: 성공")
    except Exception as exc:
        print(f"DB 연결: 실패 ({type(exc).__name__})")

key = get_secret("OPENROUTER_API_KEY")
if key:
    try:
        resp = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=15)
        print(f"오픈라우터 키 확인: HTTP {resp.status_code}")
    except httpx.HTTPError as exc:
        print(f"오픈라우터 키 확인: 실패 ({type(exc).__name__})")
```

Run: `.venv\Scripts\python scripts\check_env.py`
Expected: 세 줄 모두 `있음`, `DB 연결: 성공`, `오픈라우터 키 확인: HTTP 200`. 아니면 사용자와 함께 `.env`를 고친다.

- [ ] **Step 7: `CLAUDE.md`, `docs/cases.md`, `.claude/launch.json`**

`CLAUDE.md`:
```markdown
# CLAUDE.md
<!-- 생성: <KST 시각> -->

중간 과제: 학생이 팀을 스스로 편성하는 Streamlit 앱. 요구는 `PRD.md`, 계획은 `IMPL-PLAN.md`.

## 실행
- 설치: `.venv\Scripts\python -m pip install -r requirements-dev.txt`
- 앱: `.venv\Scripts\python -m streamlit run streamlit_app.py`
- 시험: `.venv\Scripts\python -m pytest` (DB 시험은 실제 Supabase의 tf_ 데이터를 지움. 11/3~11/4에는 돌리지 않음)
- 비밀 값 확인: `.venv\Scripts\python scripts\check_env.py` (있음/없음만 출력)

## 반드시 지킬 것
- 화면 key는 PRD 6.1절 표 그대로. 이름을 바꾸거나 빼지 않는다. 한 화면에 같은 key는 하나
- result 안내는 승인/대기/거절/막힘 가운데 하나로 시작
- 키, DB 주소, 관리자 비밀번호를 출력·커밋하지 않는다. 확인은 있음/없음만
- 테이블은 tf_ 접두. 테이블·열·제약을 바꾸면 schema.sql도 같이 고친다
- 앱 코드에 연습 시나리오의 이름·학번에 맞춘 처리를 두지 않는다
- 화면 시각은 KST
- 2026-11-02 23:59 KST 뒤에는 커밋하지 않는다
- 사실을 보고할 때는 문장 끝 괄호에 확인한 방법을 적는다(예: "(pytest 23개 통과)")
```

`docs/cases.md`(README 5~7항의 근거를 작업하면서 모아 둠):
```markdown
<!-- 생성: <KST 시각> -->
# README 사례 기록

작업 중 생긴 일을 그때그때 적는다. README 7.1절 5~7항의 근거(화면 파일, 커밋, 시나리오 단계)로 쓴다.

## 5. AI 모델 호출 실패 사례

## 6. 클로드가 잘못 추론하거나 답한 사례

## 7. 앱의 문제점이나 개선 필요 사항
```

`.claude/launch.json`(내장 브라우저 미리보기용, `.gitignore`로 커밋 안 됨. JSON이라 생성 주석 없음):
```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "team-app",
      "runtimeExecutable": ".venv/Scripts/python.exe",
      "runtimeArgs": ["-m", "streamlit", "run", "streamlit_app.py", "--server.port", "8501", "--server.headless", "true"],
      "port": 8501
    }
  ]
}
```

- [ ] **Step 8: 커밋**

```bash
git add requirements.txt requirements-dev.txt pytest.ini .env.example CLAUDE.md docs/cases.md db.py scripts/check_env.py
git status --short   # .env 가 목록에 없어야 함
git commit -m "개발 환경, 비밀 값 읽기, 프로젝트 지침"
```

---

### Task 2: 팀 규칙 (`rules.py`)

**Files:**
- Create: `rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces: `ROLES`, `PLANNER`, `WEB`, `REQUIRED`, `MIN_TEAM=2`, `MAX_TEAM=4`, `Student(student_no, name, main_role, sub_roles: tuple)`, `Student.can(role) -> bool`, `filled_required(members) -> int`, `missing_required(members) -> int`, `join_block_reason(members, applicant) -> str | None`, `required_problem(members) -> str | None`, `team_problems(team_no, members) -> list[str]`, `validate_assignment(teams: dict[int, list[Student]], unassigned: list[Student], pairs: list[tuple[str, int]]) -> list[str]`

- [ ] **Step 1: 실패하는 시험 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_rules.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'rules'`)

- [ ] **Step 3: `rules.py` 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_rules.py -q`
Expected: 14 passed

- [ ] **Step 5: 커밋**

```bash
git add rules.py tests/test_rules.py
git commit -m "팀 규칙: 필수 역할 짝짓기, 지원 막힘 이유, 배정안 검사"
```

---

### Task 3: 명단 CSV 읽기 (`roster.py`)

**Files:**
- Create: `roster.py`, `tests/data/easy.csv`, `tests/data/medium.csv`, `tests/data/hard.csv`
- Test: `tests/test_roster.py`

**Interfaces:**
- Consumes: `rules.ROLES`, `rules.Student`
- Produces: `RosterError(ValueError)`, `parse_roster(data: bytes) -> list[Student]`

- [ ] **Step 1: 연습 명단 복사**(가상 학생 명단이므로 저장소에 둬도 됨)

```powershell
New-Item -ItemType Directory -Force tests\data | Out-Null
Copy-Item "$env:USERPROFILE\Downloads\쉬움.csv" tests\data\easy.csv
Copy-Item "$env:USERPROFILE\Downloads\중간.csv" tests\data\medium.csv
Copy-Item "$env:USERPROFILE\Downloads\어려움.csv" tests\data\hard.csv
```

- [ ] **Step 2: 실패하는 시험 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 3: 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_roster.py -q`
Expected: FAIL(`No module named 'roster'`)

- [ ] **Step 4: `roster.py` 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 5: 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_roster.py -q`
Expected: 13 passed

- [ ] **Step 6: 커밋**

```bash
git add roster.py tests/test_roster.py tests/data
git commit -m "명단 CSV 읽기: BOM, 공백 정리, 오류 행 안내"
```

---

### Task 4: 스키마와 DB 연결

**Files:**
- Create: `schema.sql`, `scripts/apply_schema.py`
- Modify: `db.py`(연결 풀 추가)

**Interfaces:**
- Produces: `db.make_pool(url: str, max_size: int = 5) -> ConnectionPool`(행은 dict로 받음, 준비된 문장 끔)

- [ ] **Step 1: `schema.sql` 작성**

```sql
-- 생성: <KST 시각>
-- 팀 편성 앱의 테이블. 6장 실습 테이블과 같은 DB에 있으므로 모두 tf_ 로 시작한다.
-- 앱(service.py)이 쓰는 테이블, 열, 제약과 같게 유지한다.

create table if not exists tf_students (
    id            bigint generated always as identity primary key,
    student_no    text    not null unique,
    name          text    not null,
    main_role     text    check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text    not null,               -- bcrypt 해시. 비밀번호 원문은 저장하지 않음
    is_admin      boolean not null default false,
    check (is_admin or main_role is not null)
);

create table if not exists tf_student_sub_roles (
    student_id bigint not null references tf_students (id) on delete cascade,
    role       text   not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    primary key (student_id, role)
);

create table if not exists tf_teams (
    id      bigint generated always as identity primary key,
    team_no int  not null unique check (team_no >= 1),
    name    text not null unique
);

-- (team_id, slot_no) 기본 키와 student_id 유일성이 "먼저 도착한 학생만 기록"과 "한 학생은 한 팀"을 DB에서 지킨다
create table if not exists tf_members (
    team_id    bigint      not null references tf_teams (id) on delete cascade,
    slot_no    int         not null check (slot_no between 1 and 4),
    student_id bigint      not null unique references tf_students (id) on delete cascade,
    joined_at  timestamptz not null default now(),
    primary key (team_id, slot_no)
);

create table if not exists tf_applications (
    id         bigint generated always as identity primary key,
    team_id    bigint      not null references tf_teams (id) on delete cascade,
    student_id bigint      not null references tf_students (id) on delete cascade,
    status     text        not null default '대기' check (status in ('대기', '승인', '거절')),
    reason     text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

-- 한 학생은 결과를 기다리는 지원을 하나만 가질 수 있다
create unique index if not exists tf_applications_one_pending
    on tf_applications (student_id) where status = '대기';

create table if not exists tf_votes (
    application_id bigint      not null references tf_applications (id) on delete cascade,
    voter_id       bigint      not null references tf_students (id) on delete cascade,
    vote           text        not null check (vote in ('찬성', '거부')),
    created_at     timestamptz not null default now(),
    primary key (application_id, voter_id)    -- 한 번 투표하면 바꿀 수 없음
);

create table if not exists tf_settings (
    key   text primary key,                    -- closed, last_keepalive
    value text not null
);

create table if not exists tf_ai_logs (
    id          bigint generated always as identity primary key,
    tier        int          not null,
    model       text         not null,
    outcome     text         not null,
    elapsed_sec numeric(6, 1) not null,
    detail      text,
    created_at  timestamptz  not null default now()
);

-- Supabase의 REST API(anon 키)로 이 테이블을 읽지 못하게 한다. 앱은 DB에 직접 접속하므로 영향이 없다
alter table tf_students          enable row level security;
alter table tf_student_sub_roles enable row level security;
alter table tf_teams             enable row level security;
alter table tf_members           enable row level security;
alter table tf_applications      enable row level security;
alter table tf_votes             enable row level security;
alter table tf_settings          enable row level security;
alter table tf_ai_logs           enable row level security;
```

- [ ] **Step 2: `scripts/apply_schema.py`**

```python
# 생성: <KST 시각>
"""schema.sql 을 DB에 적용하고 tf_ 테이블 목록을 보여 준다. DB 주소는 출력하지 않는다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg

from db import get_secret

url = get_secret("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL: 없음")
sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
with psycopg.connect(url, prepare_threshold=None, autocommit=True) as conn:
    conn.execute(sql)
    rows = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public' and table_name like 'tf\\_%' order by 1"
    ).fetchall()
print("tf_ 테이블:", ", ".join(r[0] for r in rows))
```

Run: `.venv\Scripts\python scripts\apply_schema.py`
Expected: `tf_ 테이블: tf_ai_logs, tf_applications, tf_members, tf_settings, tf_student_sub_roles, tf_students, tf_teams, tf_votes`

- [ ] **Step 3: `db.py`에 연결 풀 추가**(파일 끝에 덧붙임)

```python
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def make_pool(url: str, max_size: int = 5) -> ConnectionPool:
    """연결 풀. 앱은 이것을 한 번만 만들어 재사용한다(PRD 7.2절).
    prepare_threshold=None: Supabase 트랜잭션 모드 풀러와 맞추려고 준비된 문장을 끈다."""
    return ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        timeout=20,
        open=True,
        kwargs={"prepare_threshold": None, "row_factory": dict_row},
        check=ConnectionPool.check_connection,
    )
```
(`from psycopg...` 두 줄은 파일 위쪽 import 묶음으로 옮긴다.)

- [ ] **Step 4: 연결 확인**

Run: `.venv\Scripts\python -c "from db import make_pool, get_secret; p = make_pool(get_secret('DATABASE_URL')); print(p.connection().__enter__().execute('select count(*) as n from tf_students').fetchone()); p.close()"`
Expected: `{'n': 0}`

- [ ] **Step 5: 커밋**

```bash
git add schema.sql scripts/apply_schema.py db.py
git commit -m "tf_ 스키마와 DB 연결 풀"
```

---

### Task 5: 관리자 계정, 로그인, 명단 올리기, 상태 읽기 (`service.py` 1부)

**Files:**
- Create: `service.py`, `tests/conftest.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `rules.Student`, `roster.parse_roster`, `roster.RosterError`, `db.make_pool`, `db.get_secret`
- Produces:
  - `Outcome(kind: str, detail: str)`, `Outcome.text -> str`(`"승인: …"`)
  - `User(student_no: str, name: str, is_admin: bool)`
  - `TeamView(team_no, name, members: list[Student])`, `PendingView(app_id, team_no, applicant: Student, votes: dict[str, str])`
  - `State(closed, students: dict[str, Student], teams: list[TeamView], pending: list[PendingView])` + `team_no_of(no)`, `pending_of(no)`, `team_map() -> dict[int, list[Student]]`, `unassigned() -> list[Student]`
  - `ensure_admin(pool, password) -> None`, `login(pool, student_no, password) -> User | None`, `start_roster(pool, actor_no, data: bytes, team_count: int) -> Outcome`, `load_state(pool) -> State`
  - 내부 도우미(뒤 과제가 씀): `_row_student(row)`, `_student(conn, *, no=None, sid=None)`, `_members(conn, team_id) -> list[tuple[int, Student]]`, `_is_closed(conn)`, `_set_setting(conn, key, value)`, `_is_admin(conn, actor_no)`, `_add_member(conn, team_id, student_id)`, `_decide(conn, app_id, status, reason)`, `_lock_teams(conn)`

- [ ] **Step 1: `tests/conftest.py`**

```python
# 생성: <KST 시각>
from pathlib import Path

import pytest

import service
from db import get_secret, make_pool

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def pool():
    url = get_secret("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL 없음")
    p = make_pool(url, max_size=4)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def load(pool, name, team_count):
    out = service.start_roster(pool, service.ADMIN_NO, (DATA / name).read_bytes(), team_count)
    assert out.kind == "승인", out.text


@pytest.fixture(autouse=True)
def _drop_fake_ai_logs(request):
    """시험이 남긴 가짜 AI 기록은 지운다(배포한 앱의 현황과 README 근거에 섞이지 않게)."""
    yield
    if "pool" in request.fixturenames:
        with request.getfixturevalue("pool").connection() as conn:
            conn.execute("delete from tf_ai_logs where model like '가짜/%%'")
```

- [ ] **Step 2: 실패하는 시험 작성** (`tests/test_service.py`)

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 3: 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_service.py -q`
Expected: FAIL(`No module named 'service'`)

- [ ] **Step 4: `service.py` 1부 작성**

```python
# 생성: <KST 시각>
"""DB 트랜잭션 단위의 동작(PRD 3~5장). 화면(Streamlit)을 모른다.
지원·투표·마감·확정은 트랜잭션 하나 안에서 팀 행을 잠그고(FOR UPDATE) 검사한 뒤 기록한다."""
from __future__ import annotations

from dataclasses import dataclass, field

import bcrypt
from psycopg import errors

import rules
from roster import RosterError, parse_roster
from rules import Student

ADMIN_NO = "admin"
STUDENT_PASSWORD = "1234"
MAX_TEAMS = 10


@dataclass(frozen=True)
class Outcome:
    kind: str  # 승인, 대기, 거절, 막힘
    detail: str

    @property
    def text(self) -> str:
        return f"{self.kind}: {self.detail}"


@dataclass(frozen=True)
class User:
    student_no: str
    name: str
    is_admin: bool


@dataclass
class TeamView:
    team_no: int
    name: str
    members: list[Student]


@dataclass
class PendingView:
    app_id: int
    team_no: int
    applicant: Student
    votes: dict[str, str]  # 투표한 팀원의 학번 → 찬성/거부


@dataclass
class State:
    closed: bool
    students: dict[str, Student]
    teams: list[TeamView]
    pending: list[PendingView]

    def team_no_of(self, student_no: str) -> int | None:
        for team in self.teams:
            if any(m.student_no == student_no for m in team.members):
                return team.team_no
        return None

    def pending_of(self, student_no: str) -> PendingView | None:
        return next((p for p in self.pending if p.applicant.student_no == student_no), None)

    def team_map(self) -> dict[int, list[Student]]:
        return {t.team_no: list(t.members) for t in self.teams}

    def unassigned(self) -> list[Student]:
        placed = {m.student_no for t in self.teams for m in t.members}
        return [s for no, s in sorted(self.students.items()) if no not in placed]


# ---------- 비밀번호 ----------

def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def _check(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


# ---------- 내부 도우미(연결 안에서 씀) ----------

SUBS_SQL = "coalesce((select array_agg(r.role order by r.role) from tf_student_sub_roles r where r.student_id = s.id), array[]::text[]) as subs"
STUDENT_SQL = f"select s.id, s.student_no, s.name, s.main_role, s.is_admin, {SUBS_SQL} from tf_students s where s.{{col}} = %s"
STUDENTS_SQL = f"select s.id, s.student_no, s.name, s.main_role, {SUBS_SQL} from tf_students s where not s.is_admin order by s.student_no"
MEMBER_SQL = f"""select s.id, s.student_no, s.name, s.main_role, {SUBS_SQL}
from tf_members m join tf_students s on s.id = m.student_id where m.team_id = %s order by m.slot_no"""

STATE_SQL = """
select json_build_object(
  'closed', coalesce((select value = 'true' from tf_settings where key = 'closed'), false),
  'students', coalesce((select json_agg(json_build_object(
        'id', s.id, 'no', s.student_no, 'name', s.name, 'main', s.main_role,
        'subs', coalesce((select json_agg(r.role order by r.role) from tf_student_sub_roles r where r.student_id = s.id), '[]'::json))
      order by s.student_no) from tf_students s where not s.is_admin), '[]'::json),
  'teams', coalesce((select json_agg(json_build_object('id', t.id, 'no', t.team_no, 'name', t.name) order by t.team_no)
      from tf_teams t), '[]'::json),
  'members', coalesce((select json_agg(json_build_object('team_id', m.team_id, 'student_id', m.student_id)
      order by m.team_id, m.slot_no) from tf_members m), '[]'::json),
  'pending', coalesce((select json_agg(json_build_object('id', a.id, 'team_id', a.team_id, 'student_id', a.student_id)
      order by a.created_at, a.id) from tf_applications a where a.status = '대기'), '[]'::json),
  'votes', coalesce((select json_agg(json_build_object('app_id', v.application_id, 'voter_id', v.voter_id, 'vote', v.vote))
      from tf_votes v join tf_applications a on a.id = v.application_id where a.status = '대기'), '[]'::json)
) as state
"""


def _row_student(r) -> Student:
    return Student(r["student_no"], r["name"], r["main_role"], tuple(r["subs"]))


def _student(conn, *, no: str | None = None, sid: int | None = None):
    col, value = ("student_no", no) if no is not None else ("id", sid)
    return conn.execute(STUDENT_SQL.format(col=col), (value,)).fetchone()


def _members(conn, team_id: int) -> list[tuple[int, Student]]:
    return [(r["id"], _row_student(r)) for r in conn.execute(MEMBER_SQL, (team_id,)).fetchall()]


def _is_closed(conn) -> bool:
    row = conn.execute("select value from tf_settings where key = 'closed'").fetchone()
    return bool(row) and row["value"] == "true"


def _set_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "insert into tf_settings (key, value) values (%s, %s) on conflict (key) do update set value = excluded.value",
        (key, value),
    )


def _is_admin(conn, actor_no: str) -> bool:
    row = conn.execute("select is_admin from tf_students where student_no = %s", (actor_no,)).fetchone()
    return bool(row and row["is_admin"])


def _add_member(conn, team_id: int, student_id: int) -> None:
    """비어 있는 가장 작은 자리 번호에 넣는다. 자리가 없거나 이미 팀이 있으면 DB 제약 오류가 난다."""
    conn.execute(
        """insert into tf_members (team_id, slot_no, student_id)
           select %s::bigint, min(n), %s::bigint from generate_series(1, 4) as n
           where n not in (select slot_no from tf_members where team_id = %s)""",
        (team_id, student_id, team_id),
    )


def _decide(conn, app_id: int, status: str, reason: str) -> None:
    conn.execute(
        "update tf_applications set status = %s, reason = %s, decided_at = now() where id = %s",
        (status, reason, app_id),
    )


def _lock_teams(conn) -> None:
    conn.execute("select id from tf_teams order by team_no for update")


NOT_ADMIN = Outcome("막힘", "관리자만 할 수 있음")


# ---------- 관리자 계정과 로그인 ----------

def ensure_admin(pool, password: str | None) -> None:
    """앱이 시작할 때 ADMIN_PASSWORD로 admin 계정을 만들거나 비밀번호 해시를 갱신한다."""
    if not password:
        raise ValueError("ADMIN_PASSWORD 없음")
    with pool.connection() as conn:
        row = conn.execute("select id, password_hash from tf_students where student_no = %s", (ADMIN_NO,)).fetchone()
        if row is None:
            conn.execute(
                """insert into tf_students (student_no, name, main_role, password_hash, is_admin)
                   values (%s, '관리자', null, %s, true) on conflict (student_no) do nothing""",
                (ADMIN_NO, _hash(password)),
            )
        elif not _check(password, row["password_hash"]):
            conn.execute(
                "update tf_students set password_hash = %s, is_admin = true where id = %s",
                (_hash(password), row["id"]),
            )


def login(pool, student_no: str, password: str) -> User | None:
    student_no = (student_no or "").strip()
    if not student_no or not password:
        return None
    with pool.connection() as conn:
        row = conn.execute(
            "select student_no, name, password_hash, is_admin from tf_students where student_no = %s",
            (student_no,),
        ).fetchone()
    if row and _check(password, row["password_hash"]):
        return User(row["student_no"], row["name"], row["is_admin"])
    return None


# ---------- 명단 올리기와 상태 ----------

def start_roster(pool, actor_no: str, data: bytes, team_count: int) -> Outcome:
    try:
        students = parse_roster(data)
    except RosterError as exc:
        return Outcome("막힘", str(exc))
    if not 1 <= team_count <= MAX_TEAMS:
        return Outcome("막힘", f"팀 수는 1~{MAX_TEAMS}이어야 함")
    hashes = [_hash(STUDENT_PASSWORD) for _ in students]
    with pool.connection() as conn, conn.transaction():
        if not _is_admin(conn, actor_no):
            return NOT_ADMIN
        _lock_teams(conn)
        conn.execute("delete from tf_votes")
        conn.execute("delete from tf_applications")
        conn.execute("delete from tf_members")
        conn.execute("delete from tf_teams")
        conn.execute("delete from tf_students where not is_admin")  # 보조 역할은 on delete cascade로 지워짐
        rows = conn.execute(
            """insert into tf_students (student_no, name, main_role, password_hash)
               select * from unnest(%s::text[], %s::text[], %s::text[], %s::text[])
               returning id, student_no""",
            ([s.student_no for s in students], [s.name for s in students], [s.main_role for s in students], hashes),
        ).fetchall()
        ids = {r["student_no"]: r["id"] for r in rows}
        sub_ids = [ids[s.student_no] for s in students for _ in s.sub_roles]
        sub_roles = [role for s in students for role in s.sub_roles]
        conn.execute(
            "insert into tf_student_sub_roles (student_id, role) select * from unnest(%s::bigint[], %s::text[])",
            (sub_ids, sub_roles),
        )
        conn.execute(
            "insert into tf_teams (team_no, name) select n, '팀' || n from generate_series(1, %s) as n",
            (team_count,),
        )
        _set_setting(conn, "closed", "false")
    return Outcome("승인", f"학생 {len(students)}명, 팀 {team_count}개로 처음 상태를 만듦")


def load_state(pool) -> State:
    """화면 한 번을 그리는 데 필요한 상태를 질의 한 번으로 읽는다."""
    with pool.connection() as conn:
        raw = conn.execute(STATE_SQL).fetchone()["state"]
    by_id = {s["id"]: Student(s["no"], s["name"], s["main"], tuple(s["subs"])) for s in raw["students"]}
    teams = {t["id"]: TeamView(t["no"], t["name"], []) for t in raw["teams"]}
    for m in raw["members"]:
        teams[m["team_id"]].members.append(by_id[m["student_id"]])
    votes: dict[int, dict[str, str]] = {}
    for v in raw["votes"]:
        if v["voter_id"] in by_id:
            votes.setdefault(v["app_id"], {})[by_id[v["voter_id"]].student_no] = v["vote"]
    pending = [
        PendingView(a["id"], teams[a["team_id"]].team_no, by_id[a["student_id"]], votes.get(a["id"], {}))
        for a in raw["pending"]
    ]
    return State(
        closed=raw["closed"],
        students={s.student_no: s for s in by_id.values()},
        teams=sorted(teams.values(), key=lambda t: t.team_no),
        pending=pending,
    )
```

- [ ] **Step 5: 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_service.py -q`
Expected: 7 passed

- [ ] **Step 6: 커밋**

```bash
git add service.py tests/conftest.py tests/test_service.py
git commit -m "서비스 1부: 관리자 계정, 로그인, 명단 올리기, 상태 읽기"
```

---

### Task 6: 화면 1부 — 로그인, 머리, 관리자 명단 올리기, 학생 팀 목록(읽기 전용)

**Files:**
- Create: `streamlit_app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `service.*`(Task 5), `db.get_secret`, `db.make_pool`
- Produces: 화면 함수 `get_pool()`, `set_result(text)`, `show_result()`, `roles_text(s)`, `team_card(team, my_team)`, `login_page(pool)`, `header(user)`, `student_body(pool, me_no)`(fragment), `admin_page(pool, user)`, `admin_status(pool)`(fragment), `main()`. Task 10·15에서 같은 파일을 넓힌다

- [ ] **Step 1: 실패하는 화면 시험 작성** (`tests/test_app.py`)

```python
# 생성: <KST 시각>
import pytest
from streamlit.testing.v1 import AppTest

from conftest import load
from db import get_secret

pytestmark = pytest.mark.db


def new_app():
    at = AppTest.from_file("streamlit_app.py", default_timeout=60)
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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv\Scripts\python -m pytest tests/test_app.py -q`
Expected: FAIL(`streamlit_app.py` 없음)

- [ ] **Step 3: `streamlit_app.py` 1부 작성**

```python
# 생성: <KST 시각>
"""팀 편성 웹 앱(Streamlit). 화면 요소의 key는 PRD 6.1절(공고 2.7절) 표를 그대로 따른다."""
from __future__ import annotations

from datetime import timedelta, timezone

import streamlit as st

import service
from db import get_secret, make_pool

KST = timezone(timedelta(hours=9))
REFRESH_SEC = 5
KIND_STYLE = {"승인": st.success, "대기": st.info, "거절": st.warning, "막힘": st.error}

st.set_page_config(page_title="팀 편성", page_icon="👥", layout="wide")


@st.cache_resource(show_spinner="DB에 연결하는 중")
def get_pool():
    pool = make_pool(get_secret("DATABASE_URL"))
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    return pool


def set_result(text: str) -> None:
    st.session_state["result"] = text


def show_result() -> None:
    """단추를 누른 결과 안내. 자동으로 다시 그려도 마지막 안내가 남는다."""
    with st.container(key="result"):
        text = st.session_state.get("result")
        if text:
            KIND_STYLE.get(text.split(":", 1)[0], st.write)(text)


def roles_text(s) -> str:
    subs = ", ".join(s.sub_roles) or "없음"
    return f"주 역할 {s.main_role} · 보조 역할 {subs}"


def team_card(team, my_team) -> None:
    mark = " · 내 팀" if team.team_no == my_team else ""
    st.markdown(f"#### {team.name}{mark}")
    st.caption(f"{len(team.members)}/4명")
    if team.members:
        for m in team.members:
            st.markdown(f"- **{m.name}** · {roles_text(m)}")
    else:
        st.caption("팀원 없음")


def logout() -> None:
    for k in ("user", "result", "plan"):
        st.session_state.pop(k, None)


def login_page(pool) -> None:
    st.title("팀 편성")
    show_result()
    with st.form("login_form"):
        student_no = st.text_input("학번", key="login_student_no")
        password = st.text_input("비밀번호", type="password", key="login_password")
        submitted = st.form_submit_button("로그인", key="login_submit")
    if submitted:
        user = service.login(pool, student_no, password)
        if user is None:
            set_result("막힘: 학번 또는 비밀번호가 틀림")
        else:
            st.session_state["user"] = user
            st.session_state.pop("result", None)
        st.rerun()


def header(user) -> None:
    left, right = st.columns([5, 1])
    with left:
        with st.container(key="whoami"):
            role = "관리자" if user.is_admin else "학생"
            st.markdown(f"**{user.name}** ({user.student_no}) · {role}")
    right.button("로그아웃", key="logout", on_click=logout)
    st.caption(f"화면은 {REFRESH_SEC}초마다 저절로 바뀜")


@st.fragment(run_every=REFRESH_SEC)
def student_body(pool, me_no: str) -> None:
    state = service.load_state(pool)
    show_result()
    me = state.students.get(me_no)
    if me is None:
        st.warning("지금 명단에 없는 학번임. 로그아웃한 뒤 다시 로그인")
        return
    my_team = state.team_no_of(me_no)
    st.markdown(f"**내 팀: 팀{my_team}**" if my_team else "**아직 팀이 없음**")
    st.subheader("팀 목록")
    if not state.teams:
        st.caption("아직 팀이 없음. 관리자가 명단을 올려야 함")
        return
    cols = st.columns(min(4, len(state.teams)))
    for i, team in enumerate(state.teams):
        with cols[i % len(cols)]:
            with st.container(key=f"team_{team.team_no}", border=True):
                team_card(team, my_team)
                st.button(f"{team.name}에 지원", key=f"apply_{team.team_no}", disabled=True)


def admin_page(pool, user) -> None:
    show_result()
    st.subheader("1. 명단 올리기")
    roster = st.file_uploader("명단 CSV (UTF-8)", type=["csv"], key="admin_roster_file")
    team_count = st.number_input(
        "팀 수", min_value=1, max_value=service.MAX_TEAMS, value=3, step=1, key="admin_team_count"
    )
    if st.button("명단으로 처음 상태 만들기", key="admin_start"):
        if roster is None:
            set_result("막힘: 명단 CSV를 먼저 올려야 함")
        else:
            outcome = service.start_roster(pool, user.student_no, roster.getvalue(), int(team_count))
            set_result(outcome.text)
            if outcome.kind == "승인":
                st.session_state.pop("plan", None)
        st.rerun()

    st.subheader("2. 마감과 배정")
    close_col, assign_col, confirm_col = st.columns(3)
    close_col.button("모집 마감", key="admin_close")
    assign_col.button("AI 배정", key="admin_assign")
    confirm_col.button("배정안 확정", key="admin_confirm")
    st.container(key="assign_status", border=True).caption("AI 배정을 누르면 진행 상황과 배정안이 여기에 나옴")

    st.subheader("3. 현황")
    admin_status(pool)


@st.fragment(run_every=REFRESH_SEC)
def admin_status(pool) -> None:
    state = service.load_state(pool)
    st.markdown("모집 상태: **마감됨**" if state.closed else "모집 상태: **모집 중**")
    with st.container(key="unassigned", border=True):
        st.markdown("**팀이 없는 학생**")
        names = [s.name for s in state.unassigned()]
        st.write(", ".join(names) if names else "없음")
    if state.teams:
        cols = st.columns(min(4, len(state.teams)))
        for i, team in enumerate(state.teams):
            with cols[i % len(cols)]:
                with st.container(key=f"team_{team.team_no}", border=True):
                    team_card(team, None)


def main() -> None:
    missing = [n for n in ("DATABASE_URL", "ADMIN_PASSWORD") if not get_secret(n)]
    if missing:
        st.error("설정 값이 없음: " + ", ".join(missing))
        st.stop()
    try:
        pool = get_pool()
    except Exception as exc:  # 연결 문자열이 들어갈 수 있는 예외 메시지는 보여 주지 않는다
        st.error(f"DB에 연결하지 못함 ({type(exc).__name__})")
        st.stop()
    user = st.session_state.get("user")
    if user is None:
        login_page(pool)
        return
    header(user)
    if user.is_admin:
        admin_page(pool, user)
    else:
        student_body(pool, user.student_no)


main()
```

- [ ] **Step 4: 통과 확인**

Run: `.venv\Scripts\python -m pytest tests/test_app.py -q`
Expected: 4 passed

- [ ] **Step 5: 전체 시험과 커밋**

Run: `.venv\Scripts\python -m pytest -q` → Expected: 38 passed

```bash
git add streamlit_app.py tests/test_app.py
git commit -m "화면 1부: 로그인, 관리자 명단 올리기, 학생 팀 목록"
```

- [ ] **Step 6: 앱을 띄워 직접 확인하고 1단계 보고 후 멈춤**

내장 브라우저 미리보기(`.claude/launch.json`의 `team-app`)로 앱을 연다. DOM에 key가 있는지 확인한다(Streamlit은 key를 `st-key-<key>` 클래스로 붙임):
```js
['login_student_no','login_password','login_submit'].map(k => k + ':' + !!document.querySelector('.st-key-' + k))
```

**1단계 브라우저 확인 항목(사용자가 확인)**
1. 첫 화면에 학번, 비밀번호 입력칸과 로그인 단추가 보인다
2. `2026101` / `9999`로 로그인하면 `막힘: 학번 또는 비밀번호가 틀림`이 보이고 들어가지지 않는다
3. `admin`과 관리자 비밀번호로 로그인하면 위에 `관리자 (admin) · 관리자`가 보인다
4. `쉬움.csv`를 올리고 팀 수 3으로 `명단으로 처음 상태 만들기`를 누르면 `승인: 학생 8명, 팀 3개로 처음 상태를 만듦`
5. 현황의 "팀이 없는 학생"에 8명의 이름이 보이고, 팀1~팀3이 비어 있다
6. 로그아웃 후 `2026101` / `1234`로 로그인하면 팀1~팀3 카드와 `아직 팀이 없음`이 보인다(지원 단추는 아직 비활성)
7. 팀 수에 0을 넣을 수 없고(1~10), 명단 없이 단추를 누르면 `막힘: 명단 CSV를 먼저 올려야 함`

사용자가 확인을 마치면 `git switch main && git merge --no-ff stage-1 -m "1단계: 기반"`.

---

# 2단계: 지원, 투표, 마감, 자동 갱신

### Task 7: 지원 (`service.apply`)

**Files:**
- Modify: `service.py`(끝에 추가)
- Test: `tests/test_service.py`(끝에 추가)

**Interfaces:**
- Produces: `apply(pool, student_no: str, team_no: int) -> Outcome`

- [ ] **Step 1: 브랜치**: `git switch -c stage-2`

- [ ] **Step 2: 실패하는 시험 추가**

```python
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
```

- [ ] **Step 3: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k apply` → FAIL(`has no attribute 'apply'`)

- [ ] **Step 4: `apply` 작성**

```python
# ---------- 지원과 투표 ----------

def apply(pool, student_no: str, team_no: int) -> Outcome:
    try:
        with pool.connection() as conn, conn.transaction():
            return _apply(conn, student_no, team_no)
    except errors.IntegrityError:
        return Outcome("막힘", "다른 요청이 먼저 처리됨. 화면을 보고 다시 시도")


def _apply(conn, student_no: str, team_no: int) -> Outcome:
    team = conn.execute("select id from tf_teams where team_no = %s for update", (team_no,)).fetchone()
    if team is None:
        return Outcome("막힘", f"팀{team_no}이(가) 없음")
    if _is_closed(conn):
        return Outcome("막힘", "모집이 마감됨")
    me = _student(conn, no=student_no)
    if me is None or me["is_admin"]:
        return Outcome("막힘", "학생만 지원할 수 있음")
    if conn.execute("select 1 from tf_members where student_id = %s", (me["id"],)).fetchone():
        return Outcome("막힘", "이미 팀이 있음")
    if conn.execute(
        "select 1 from tf_applications where student_id = %s and status = '대기'", (me["id"],)
    ).fetchone():
        return Outcome("막힘", "결과를 기다리는 지원이 있음")
    members = _members(conn, team["id"])
    reason = rules.join_block_reason([s for _, s in members], _row_student(me))
    if reason:
        return Outcome("막힘", reason)
    if not members:
        _add_member(conn, team["id"], me["id"])
        conn.execute(
            """insert into tf_applications (team_id, student_id, status, reason, decided_at)
               values (%s, %s, '승인', '빈 팀에 바로 들어감', now())""",
            (team["id"], me["id"]),
        )
        return Outcome("승인", f"팀{team_no}에 들어감")
    conn.execute("insert into tf_applications (team_id, student_id) values (%s, %s)", (team["id"], me["id"]))
    return Outcome("대기", f"팀{team_no} 팀원 {len(members)}명의 투표를 기다림")
```

- [ ] **Step 5: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k apply` → 3 passed

- [ ] **Step 6: 커밋**: `git add service.py tests/test_service.py && git commit -m "지원: 빈 팀 바로 승인, 대기, 막힘 이유"`

---

### Task 8: 투표와 승인 직전 검사 (`service.vote`)

**Files:**
- Modify: `service.py`, `tests/test_service.py`

**Interfaces:**
- Produces: `vote(pool, voter_no: str, applicant_no: str, choice: str) -> Outcome`(`choice`는 `"찬성"` 또는 `"거부"`)

- [ ] **Step 1: 실패하는 시험 추가**

```python
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
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k vote` → FAIL

- [ ] **Step 3: `vote` 작성**

```python
def vote(pool, voter_no: str, applicant_no: str, choice: str) -> Outcome:
    if choice not in ("찬성", "거부"):
        raise ValueError(choice)
    try:
        with pool.connection() as conn, conn.transaction():
            return _vote(conn, voter_no, applicant_no, choice)
    except errors.UniqueViolation:
        return Outcome("막힘", "이미 투표함")
    except errors.IntegrityError:
        return Outcome("막힘", "다른 요청이 먼저 처리됨. 화면을 보고 다시 시도")


def _vote(conn, voter_no: str, applicant_no: str, choice: str) -> Outcome:
    found = conn.execute(
        """select a.id, a.team_id from tf_applications a join tf_students s on s.id = a.student_id
           where s.student_no = %s and a.status = '대기'""",
        (applicant_no,),
    ).fetchone()
    if found is None:
        return Outcome("막힘", "대기 중인 지원이 없음")
    team = conn.execute("select id, team_no from tf_teams where id = %s for update", (found["team_id"],)).fetchone()
    app = conn.execute(
        "select id, student_id, status from tf_applications where id = %s for update", (found["id"],)
    ).fetchone()
    if app["status"] != "대기":
        return Outcome(app["status"], "이미 결과가 나온 지원")
    if _is_closed(conn):
        return Outcome("막힘", "모집이 마감됨")
    members = _members(conn, team["id"])
    voter_id = next((sid for sid, s in members if s.student_no == voter_no), None)
    if voter_id is None:
        return Outcome("막힘", "이 팀의 팀원만 투표할 수 있음")
    prev = conn.execute(
        "select vote from tf_votes where application_id = %s and voter_id = %s", (app["id"], voter_id)
    ).fetchone()
    if prev:
        return Outcome("막힘", f"이미 투표함(내 투표: {prev['vote']})")
    conn.execute(
        "insert into tf_votes (application_id, voter_id, vote) values (%s, %s, %s)", (app["id"], voter_id, choice)
    )
    if choice == "거부":
        _decide(conn, app["id"], "거절", "팀원이 거부함")
        return Outcome("거절", "팀원이 거부함")
    yes = {
        r["voter_id"]
        for r in conn.execute(
            "select voter_id from tf_votes where application_id = %s and vote = '찬성'", (app["id"],)
        ).fetchall()
    }
    member_ids = {sid for sid, _ in members}
    if not member_ids <= yes:
        return Outcome("대기", f"찬성 {len(member_ids & yes)}/{len(member_ids)}명")
    applicant = _row_student(_student(conn, sid=app["student_id"]))
    reason = rules.join_block_reason([s for _, s in members], applicant)  # 승인 직전 검사(PRD 3.3절)
    if reason:
        _decide(conn, app["id"], "거절", f"승인 직전 검사 – {reason}")
        return Outcome("거절", f"승인 직전 검사 – {reason}")
    _add_member(conn, team["id"], app["student_id"])
    _decide(conn, app["id"], "승인", "팀원 모두 찬성")
    return Outcome("승인", f"{applicant.name}이(가) 팀{team['team_no']}에 들어감")
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k vote` → 3 passed

- [ ] **Step 5: 커밋**: `git add service.py tests/test_service.py && git commit -m "투표: 전원 찬성 승인, 거부 즉시 거절, 승인 직전 재검사"`

---

### Task 9: 모집 마감과 동시 지원 (`service.close`)

**Files:**
- Modify: `service.py`, `tests/test_service.py`

**Interfaces:**
- Produces: `close(pool, actor_no: str) -> Outcome`

- [ ] **Step 1: 실패하는 시험 추가**

```python
import threading


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
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k "close or at_once"` → FAIL

- [ ] **Step 3: `close` 작성**

```python
# ---------- 마감 ----------

def close(pool, actor_no: str) -> Outcome:
    with pool.connection() as conn, conn.transaction():
        if not _is_admin(conn, actor_no):
            return NOT_ADMIN
        _lock_teams(conn)
        if _is_closed(conn):
            return Outcome("막힘", "이미 마감됨")
        _set_setting(conn, "closed", "true")
        rejected = conn.execute(
            """update tf_applications set status = '거절', reason = '모집 마감', decided_at = now()
               where status = '대기' returning id"""
        ).fetchall()
        removed = conn.execute(
            """delete from tf_members where team_id in
               (select team_id from tf_members group by team_id having count(*) = 1) returning student_id"""
        ).fetchall()
    return Outcome("승인", f"모집을 마감함 (대기 지원 {len(rejected)}건 거절, 팀에서 빠진 학생 {len(removed)}명)")
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q` → 15 passed

- [ ] **Step 5: 커밋**: `git add service.py tests/test_service.py && git commit -m "모집 마감: 대기 거절, 1명뿐인 팀 해체, 동시 지원 시험"`

---

### Task 10: 화면 2부 — 지원·투표 단추, 자동 갱신, 마감 단추

**Files:**
- Modify: `streamlit_app.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `service.apply`, `service.vote`, `service.close`
- Produces: 콜백 `do_apply(pool, me_no, team_no)`, `do_vote(pool, me_no, applicant_no, choice)`, 화면 함수 `incoming_section(pool, state, me_no, my_team)`, `teams_section(pool, state, me_no, my_team, locked)`

- [ ] **Step 1: 실패하는 화면 시험 추가**

```python
import service


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
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_app.py -q` → 새 시험 4개 FAIL

- [ ] **Step 3: `streamlit_app.py`의 `student_body`를 바꾸고 콜백과 두 영역 추가**

`student_body`를 아래로 바꾼다:
```python
def do_apply(pool, me_no: str, team_no: int) -> None:
    set_result(service.apply(pool, me_no, team_no).text)


def do_vote(pool, me_no: str, applicant_no: str, choice: str) -> None:
    set_result(service.vote(pool, me_no, applicant_no, choice).text)


@st.fragment(run_every=REFRESH_SEC)
def student_body(pool, me_no: str) -> None:
    """학생 화면. fragment라서 5초마다 이 부분만 다시 그린다(다른 사람의 변경 보기)."""
    state = service.load_state(pool)
    show_result()
    me = state.students.get(me_no)
    if me is None:
        st.warning("지금 명단에 없는 학번임. 로그아웃한 뒤 다시 로그인")
        return
    my_team = state.team_no_of(me_no)
    my_pending = state.pending_of(me_no)
    if my_team:
        st.markdown(f"**내 팀: 팀{my_team}**")
    elif my_pending:
        st.markdown(f"**팀{my_pending.team_no} 지원 결과를 기다리는 중**")
    else:
        st.markdown("**아직 팀이 없음**")
    if state.closed:
        st.info("모집이 마감됨. 지원과 투표를 할 수 없음")
    locked = state.closed or my_team is not None or my_pending is not None  # PRD 6.4절: 비활성 조건
    if my_team is not None:
        incoming_section(pool, state, me_no, my_team)
    teams_section(pool, state, me_no, my_team, locked)


def incoming_section(pool, state, me_no: str, my_team: int) -> None:
    st.subheader("내 팀에 들어온 지원")
    incoming = [p for p in state.pending if p.team_no == my_team]
    if not incoming:
        st.caption("대기 중인 지원이 없음")
        return
    member_count = len(state.team_map()[my_team])
    for p in incoming:
        yes = sum(1 for v in p.votes.values() if v == "찬성")
        info, yes_col, no_col = st.columns([4, 1, 1])
        info.markdown(f"**{p.applicant.name}** · {roles_text(p.applicant)} · 찬성 {yes}/{member_count}명")
        mine = p.votes.get(me_no)
        if mine:
            yes_col.markdown(f"내 투표: {mine}")
            continue
        no = p.applicant.student_no
        yes_col.button("찬성", key=f"vote_yes_{no}", on_click=do_vote, args=(pool, me_no, no, "찬성"), disabled=state.closed)
        no_col.button("거부", key=f"vote_no_{no}", on_click=do_vote, args=(pool, me_no, no, "거부"), disabled=state.closed)


def teams_section(pool, state, me_no: str, my_team, locked: bool) -> None:
    st.subheader("팀 목록")
    if not state.teams:
        st.caption("아직 팀이 없음. 관리자가 명단을 올려야 함")
        return
    cols = st.columns(min(4, len(state.teams)))
    for i, team in enumerate(state.teams):
        with cols[i % len(cols)]:
            with st.container(key=f"team_{team.team_no}", border=True):
                team_card(team, my_team)
                waiting = [p.applicant.name for p in state.pending if p.team_no == team.team_no]
                if waiting:
                    st.caption("대기 중인 지원: " + ", ".join(waiting))
                st.button(
                    f"{team.name}에 지원",
                    key=f"apply_{team.team_no}",
                    disabled=locked,
                    on_click=do_apply,
                    args=(pool, me_no, team.team_no),
                )
```

`admin_page`의 마감 단추 줄 `close_col.button("모집 마감", key="admin_close")`를 아래로 바꾼다:
```python
    if close_col.button("모집 마감", key="admin_close"):
        outcome = service.close(pool, user.student_no)
        set_result(outcome.text)
        if outcome.kind == "승인":
            st.session_state.pop("plan", None)
        st.rerun()
```

`admin_status`의 팀 카드 안(`team_card(team, None)` 다음 줄)에 대기 중인 지원을 보여 준다:
```python
                    waiting = [p.applicant.name for p in state.pending if p.team_no == team.team_no]
                    if waiting:
                        st.caption("대기 중인 지원: " + ", ".join(waiting))
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest -q` → 50 passed

- [ ] **Step 5: 커밋**: `git add streamlit_app.py tests/test_app.py && git commit -m "화면 2부: 지원·투표 단추, 5초 자동 갱신, 마감"`

- [ ] **Step 6: 앱을 띄워 직접 확인하고 2단계 보고 후 멈춤**

내장 브라우저에서 학생 창과 관리자 창을 탭 두 개로 열어 확인한다. 한 탭에서 지원하면 다른 탭에 5초 안에 나타나는지 본다.

**2단계 브라우저 확인 항목(사용자가 확인, 쉬움 시나리오 부록 1)**
1. 관리자로 `쉬움.csv`, 팀 3으로 처음 상태를 만든다
2. 학생1→팀1, 학생2→팀2, 학생3→팀3 지원: 셋 다 `승인`
3. 학생4가 팀1에 지원 → `대기`. 학생1 창에서 새로 고치지 않아도 5초 안에 `내 팀에 들어온 지원`에 학생4가 나타나고, `찬성`을 누르면 `승인`
4. 학생5→팀2, 학생2 찬성 → `승인`
5. 학생7→팀1 지원 → `대기`. 학생1 찬성 → `대기: 찬성 1/2명`, 학생1 화면에 `내 투표: 찬성`. 학생4 거부 → `거절: 팀원이 거부함`
6. 학생6→팀3, 학생3 찬성 → `승인`
7. 팀이 있는 학생의 화면에서 지원 단추가 모두 비활성이다
8. 관리자가 `모집 마감` → `승인: 모집을 마감함 (대기 지원 0건 거절, 팀에서 빠진 학생 0명)`, 팀이 없는 학생에 학생7, 학생8
9. 마감 뒤 학생7 화면에 `모집이 마감됨`이 보이고 지원 단추가 비활성이다

확인을 마치면 `git switch main && git merge --no-ff stage-2 -m "2단계: 지원, 투표, 마감"`.

---

# 3단계: 배정

### Task 11: 전수 탐색 배정 (`solver.py`)

**Files:**
- Create: `solver.py`
- Test: `tests/test_solver.py`

**Interfaces:**
- Consumes: `rules.*`
- Produces: `solve(teams: dict[int, list[Student]], unassigned: list[Student]) -> list[tuple[str, int]] | None`, `infeasible_reasons(teams, unassigned) -> list[str]`

- [ ] **Step 1: 브랜치**: `git switch -c stage-3`

- [ ] **Step 2: 실패하는 시험 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 3: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_solver.py -q` → FAIL

- [ ] **Step 4: `solver.py` 작성**

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 5: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_solver.py -q` → 6 passed

- [ ] **Step 6: 커밋**: `git add solver.py tests/test_solver.py && git commit -m "전수 탐색 배정과 배정이 없을 때의 이유"`

---

### Task 12: AI 호출 (`ai_assign.py`)

**Files:**
- Create: `ai_assign.py`
- Test: `tests/test_ai_assign.py`

**Interfaces:**
- Consumes: `rules.Student`
- Produces: `MODELS: tuple[str, str, str]`, `TIMEOUT_SEC = 120.0`, `Attempt(tier, model, outcome, elapsed, detail)`, `AIError`과 하위 `AITimeout`, `AIHttpError`, `AIEmpty`, `AIFormatError`(각 `outcome` 속성), `build_prompt(teams, unassigned) -> str`, `parse_pairs(text) -> list[tuple[str, int]]`, `call_model(model, prompt, api_key, timeout=TIMEOUT_SEC, on_tick=None, transport=None, tick_sec=0.5) -> str`, `run(teams, unassigned, validate, api_key, on_progress=None, log=None, models=None, timeout=TIMEOUT_SEC, transport=None) -> tuple[list | None, list[Attempt]]`(`models=None`이면 부를 때의 `MODELS`)

- [ ] **Step 1: 실패하는 시험 작성**

```python
# 생성: <KST 시각>
import json
import time

import httpx
import pytest

import ai_assign
from ai_assign import AIEmpty, AIFormatError, AIHttpError, AITimeout, call_model, parse_pairs, run
from rules import Student


def sse(text: str) -> bytes:
    chunk = {"choices": [{"delta": {"content": text}}]}
    return f": OPENROUTER PROCESSING\n\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\ndata: [DONE]\n\n".encode()


def transport_for(handler):
    return httpx.MockTransport(handler)


def test_parse_pairs_with_code_fence():
    text = '설명\n```json\n{"assignments": [{"student_no": "2026107", "team_no": 1}]}\n```'
    assert parse_pairs(text) == [("2026107", 1)]


def test_parse_pairs_accepts_loose_types():
    text = '{"assignments": [{"student_no": 2026107, "team_no": "팀2"}, {"student_no": "2026108", "team_no": 3.0}]}'
    assert parse_pairs(text) == [("2026107", 2), ("2026108", 3)]


@pytest.mark.parametrize("text", ["배정할 수 없습니다", '{"result": []}', '{"assignments": [{"student_no": "1"}]}', "{broken"])
def test_parse_pairs_rejects(text):
    with pytest.raises(AIFormatError):
        parse_pairs(text)


def test_call_model_reads_stream():
    t = transport_for(lambda req: httpx.Response(200, content=sse("안녕")))
    assert call_model("m", "p", "key", transport=t) == "안녕"


def test_call_model_http_error():
    t = transport_for(lambda req: httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}}))
    with pytest.raises(AIHttpError, match="HTTP 429 Rate limit exceeded"):
        call_model("m", "p", "key", transport=t)


def test_call_model_empty():
    t = transport_for(lambda req: httpx.Response(200, content=b"data: [DONE]\n\n"))
    with pytest.raises(AIEmpty):
        call_model("m", "p", "key", transport=t)


class SlowStream(httpx.SyncByteStream):
    """응답이 시작은 되지만 천천히 오는 경우(시작까지만 재는 시간 제한으로는 못 끊음)."""

    def __iter__(self):
        yield b": OPENROUTER PROCESSING\n\n"
        time.sleep(3)
        yield b'data: {"choices":[{"delta":{"content":"late"}}]}\n\n'


def test_call_model_total_timeout_cuts_slow_stream():
    t = transport_for(lambda req: httpx.Response(200, stream=SlowStream()))
    ticks = []
    start = time.monotonic()
    with pytest.raises(AITimeout):
        call_model("m", "p", "key", timeout=1.0, on_tick=ticks.append, transport=t, tick_sec=0.2)
    assert time.monotonic() - start < 2.0
    assert ticks


def S(no, main, *subs):
    return Student(no, f"가상{no}", main, tuple(subs))


TEAMS = {1: [S("1", "기획자"), S("2", "웹 프로그래머")], 2: [S("3", "기획자"), S("4", "웹 프로그래머")]}
WAITING = [S("5", "테스터")]


def test_run_falls_through_to_third_model():
    def handler(req):
        model = json.loads(req.content)["model"]
        if model == "a":
            return httpx.Response(429, json={"error": {"message": "busy"}})
        if model == "b":
            return httpx.Response(200, content=sse('{"assignments": [{"student_no": "9", "team_no": 1}]}'))
        return httpx.Response(200, content=sse('{"assignments": [{"student_no": "5", "team_no": 2}]}'))

    logged, progress = [], []
    from rules import validate_assignment

    pairs, attempts = run(
        TEAMS, WAITING, validate=lambda p: validate_assignment(TEAMS, WAITING, p), api_key="key",
        on_progress=lambda tier, model, elapsed: progress.append(tier), log=logged.append,
        models=("a", "b", "c"), transport=transport_for(handler),
    )
    assert pairs == [("5", 2)]
    assert [a.outcome for a in attempts] == ["HTTP 오류", "검사 불통과", "성공"]
    assert logged == attempts
    assert progress[:1] == [1] and 3 in progress


def test_run_returns_none_when_all_fail():
    t = transport_for(lambda req: httpx.Response(200, content=b"data: [DONE]\n\n"))
    pairs, attempts = run(TEAMS, WAITING, validate=lambda p: [], api_key="key", models=("a", "b", "c"), transport=t)
    assert pairs is None and [a.outcome for a in attempts] == ["빈 응답"] * 3


def test_prompt_lists_teams_and_waiting_students():
    prompt = ai_assign.build_prompt(TEAMS, WAITING)
    assert "팀2 (2명)" in prompt and "5 가상5" in prompt and '"assignments"' in prompt


def test_models_do_not_use_auto_router():
    assert len(ai_assign.MODELS) == 3
    assert all(m.endswith(":free") and m != "openrouter/free" for m in ai_assign.MODELS)
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_ai_assign.py -q` → FAIL

- [ ] **Step 3: `ai_assign.py` 작성**

```python
# 생성: <KST 시각>
"""오픈라우터 AI 배정(PRD 4.2절 4~6, 4.6절).
1·2·3차 모델을 차례로 부르고, 모델마다 부른 때부터 응답을 다 받을 때까지 120초가 넘으면 끊는다.
응답은 별도 스레드에서 스트리밍으로 받고, 부른 쪽은 0.5초마다 경과 시간을 확인해 진행 안내를 갱신한다."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass

import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# 오픈라우터 무료 텍스트 생성 모델. openrouter/free(자동 라우터)는 쓰지 않는다. Task 13에서 실제로 불러 보고 확정
MODELS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
)
TIMEOUT_SEC = 120.0
MAX_TOKENS = 8000

SYSTEM = "너는 대학 팀 프로젝트의 팀 편성 도우미다. 규칙을 모두 지키는 배정안을 JSON 하나로만 답한다."


class AIError(Exception):
    outcome = "오류"


class AITimeout(AIError):
    outcome = "시간 초과"


class AIHttpError(AIError):
    outcome = "HTTP 오류"


class AIEmpty(AIError):
    outcome = "빈 응답"


class AIFormatError(AIError):
    outcome = "형식 오류"


@dataclass
class Attempt:
    tier: int
    model: str
    outcome: str  # 성공, 시간 초과, HTTP 오류, 빈 응답, 형식 오류, 검사 불통과, 오류
    elapsed: float
    detail: str = ""


def _describe(s) -> str:
    subs = ", ".join(s.sub_roles) or "없음"
    return f"{s.student_no} {s.name} [주 역할: {s.main_role} / 보조 역할: {subs}]"


def build_prompt(teams, unassigned) -> str:
    lines = [
        "아래 규칙을 모두 지키도록 '팀이 없는 학생'만 팀에 배정하라. 이미 팀에 있는 학생은 옮기지 않는다.",
        "",
        "규칙:",
        "1. 팀이 없는 학생은 빠짐없이, 정확히 한 팀에 배정한다.",
        "2. 배정한 뒤 모든 팀의 인원은 2명 이상 4명 이하이다(빈 팀 없음).",
        "3. 한 팀 안에 주 역할이 같은 학생이 2명 이상이면 안 된다.",
        "4. 모든 팀에는 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다. 주 역할이나 보조 역할로 맡을 수 있다.",
        "",
        "지금 팀:",
    ]
    for t in sorted(teams):
        members = teams[t]
        lines.append(f"- 팀{t} ({len(members)}명)")
        lines.extend(f"  - {_describe(m)}" for m in members)
    lines += ["", "팀이 없는 학생:"]
    lines.extend(f"- {_describe(s)}" for s in unassigned)
    lines += [
        "",
        "설명 없이 아래 형식의 JSON 하나만 출력하라. team_no는 숫자다.",
        '{"assignments": [{"student_no": "학번", "team_no": 1}]}',
    ]
    return "\n".join(lines)


def parse_pairs(text: str) -> list[tuple[str, int]]:
    cleaned = re.sub(r"```(?:json)?", "", text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise AIFormatError("JSON이 없음")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIFormatError(f"JSON 해석 실패: {exc.msg}") from None
    items = data.get("assignments") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise AIFormatError("assignments 목록이 없음")
    pairs = []
    for item in items:
        if not isinstance(item, dict):
            raise AIFormatError("배정 항목의 형식이 틀림")
        student_no = str(item.get("student_no", "")).strip()
        team = item.get("team_no")
        if isinstance(team, str):
            digits = re.findall(r"\d+", team)
            team = int(digits[0]) if digits else None
        elif isinstance(team, float) and team.is_integer():
            team = int(team)
        if not student_no or isinstance(team, bool) or not isinstance(team, int):
            raise AIFormatError("학번이나 팀 번호가 빠짐")
        pairs.append((student_no, team))
    return pairs


def _error_message(raw: bytes) -> str:
    try:
        message = json.loads(raw).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        message = raw.decode("utf-8", "replace")
    return " ".join(str(message).split())[:200]


def _read_stream(resp, cancel: threading.Event) -> str:
    parts = []
    for line in resp.iter_lines():
        if cancel.is_set():
            break
        if not line.startswith("data:"):
            continue  # 빈 줄과 ': OPENROUTER PROCESSING' 같은 주석 줄
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        if "error" in chunk:
            raise AIHttpError(f"스트림 오류 {_error_message(json.dumps(chunk).encode())}")
        for choice in chunk.get("choices", []):
            piece = (choice.get("delta") or {}).get("content")
            if piece:
                parts.append(piece)
    text = "".join(parts).strip()
    if not text:
        raise AIEmpty("내용이 없는 응답")
    return text


def call_model(model, prompt, api_key, timeout=TIMEOUT_SEC, on_tick=None, transport=None, tick_sec=0.5) -> str:
    """모델 하나를 부른다. 부른 때부터 응답을 다 받을 때까지 timeout초가 넘으면 AITimeout."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "reasoning": {"effort": "low"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "X-Title": "team-formation"}
    box: dict = {}
    done, cancel = threading.Event(), threading.Event()

    def worker():
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), transport=transport) as client:
                box["client"] = client
                with client.stream("POST", API_URL, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        raise AIHttpError(f"HTTP {resp.status_code} {_error_message(resp.read())}".strip())
                    box["text"] = _read_stream(resp, cancel)
        except BaseException as exc:  # 스레드 밖으로 넘겨 부른 쪽에서 처리
            box["error"] = exc
        finally:
            done.set()

    start = time.monotonic()
    threading.Thread(target=worker, daemon=True).start()
    while not done.wait(tick_sec):
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            cancel.set()
            client = box.get("client")
            if client is not None:
                client.close()  # 받던 스트림을 끊는다
            raise AITimeout(f"{timeout:.0f}초 안에 응답을 다 받지 못함")
        if on_tick:
            on_tick(elapsed)
    if time.monotonic() - start > timeout:
        raise AITimeout(f"{timeout:.0f}초 안에 응답을 다 받지 못함")
    error = box.get("error")
    if isinstance(error, AIError):
        raise error
    if isinstance(error, httpx.HTTPError):
        raise AIHttpError(f"연결 오류 {type(error).__name__}")
    if error is not None:
        raise AIError(type(error).__name__)
    return box["text"]


def run(teams, unassigned, validate, api_key, on_progress=None, log=None, models=None, timeout=TIMEOUT_SEC, transport=None):
    """1·2·3차 모델을 차례로 부른다. 검사를 통과한 배정안과 시도 기록을 돌려준다. 모두 실패하면 (None, 기록).
    models=None이면 부를 때의 MODELS를 쓴다(시험에서 MODELS를 바꿔 끼울 수 있게)."""
    models = MODELS if models is None else models
    prompt = build_prompt(teams, unassigned)
    attempts: list[Attempt] = []
    for tier, model in enumerate(models, start=1):
        if on_progress:
            on_progress(tier, model, 0.0)
        tick = (lambda e, t=tier, m=model: on_progress(t, m, e)) if on_progress else None
        start = time.monotonic()
        pairs, outcome, detail = None, "성공", ""
        try:
            pairs = parse_pairs(call_model(model, prompt, api_key, timeout=timeout, on_tick=tick, transport=transport))
            problems = validate(pairs)
            if problems:
                pairs, outcome, detail = None, "검사 불통과", "; ".join(problems[:3])
        except AIError as exc:
            outcome, detail = exc.outcome, str(exc)
        attempt = Attempt(tier, model, outcome, round(time.monotonic() - start, 1), detail)
        attempts.append(attempt)
        if log:
            try:
                log(attempt)
            except Exception:
                pass  # 기록 실패가 배정을 막지 않게 함
        if pairs is not None:
            return pairs, attempts
    return None, attempts
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_ai_assign.py -q` → 14 passed

- [ ] **Step 5: 커밋**: `git add ai_assign.py tests/test_ai_assign.py && git commit -m "AI 호출: 모델별 120초 전체 제한, 스트리밍, 1·2·3차 넘김"`

---

### Task 13: 모델 후보를 실제로 불러 보고 확정

**Files:**
- Create: `scripts/try_models.py`
- Modify: `ai_assign.py`의 `MODELS`(필요할 때만)

- [ ] **Step 1: `scripts/try_models.py`**(무료 한도를 아끼려고 후보마다 1번만 부름)

```python
# 생성: <KST 시각>
"""모델 후보를 쉬움 시나리오 마감 직후 상태로 한 번씩 불러 본다. 키는 출력하지 않는다.
사용: python scripts/try_models.py [모델 ...]  (없으면 ai_assign.MODELS)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_assign
from db import get_secret
from roster import parse_roster
from rules import validate_assignment

students = {s.student_no: s for s in parse_roster((ROOT / "tests/data/easy.csv").read_bytes())}
teams = {1: [students["2026101"], students["2026104"]], 2: [students["2026102"], students["2026105"]], 3: [students["2026103"], students["2026106"]]}
waiting = [students["2026107"], students["2026108"]]
models = tuple(sys.argv[1:]) or ai_assign.MODELS
key = get_secret("OPENROUTER_API_KEY")
if not key:
    sys.exit("OPENROUTER_API_KEY: 없음")
for model in models:
    pairs, attempts = ai_assign.run(teams, waiting, lambda p: validate_assignment(teams, waiting, p), key, models=(model,))
    a = attempts[0]
    print(f"{model}: {a.outcome} ({a.elapsed}초) {a.detail}")
```

- [ ] **Step 2: 실행**

Run: `.venv\Scripts\python scripts\try_models.py`
Expected: 세 모델의 결과 줄. `성공`이 아닌 모델이 있으면 사용자에게 결과를 보여 주고, 3장 목록(`curl -s https://openrouter.ai/api/v1/models`의 `:free` 모델)에서 대체 후보를 골라 `try_models.py <후보>`로 다시 불러 본 뒤, **바꿀 모델을 사용자에게 확인받고** `MODELS`를 고친다. 실패 결과는 `docs/cases.md`의 5절에 시각, 모델, 사유와 함께 적는다(README 5항 근거).

- [ ] **Step 3: 커밋**: `git add scripts/try_models.py ai_assign.py docs/cases.md && git commit -m "AI 모델 후보 시험 도구와 1·2·3차 모델 확정"`

---

### Task 14: 배정안 만들기, 확정, AI 기록 (`service.py` 3부)

**Files:**
- Modify: `service.py`, `tests/test_service.py`

**Interfaces:**
- Consumes: `solver.solve`, `solver.infeasible_reasons`, `ai_assign.run`, `ai_assign.Attempt`, `rules.validate_assignment`, `rules.team_problems`
- Produces: `AssignPlan(outcome, pairs, source, attempts, reasons)`, `plan_assignment(pool, actor_no, api_key, on_progress=None, runner=None) -> AssignPlan`(`runner=None`이면 `ai_assign.run`), `confirm(pool, actor_no, pairs) -> Outcome`, `log_ai(pool, attempt) -> None`, `recent_ai_logs(pool, limit=10) -> list[dict]`

- [ ] **Step 1: 실패하는 시험 추가**

```python
def fake_runner(pairs_from_ai, outcome="성공"):
    calls = []

    def runner(teams, waiting, validate, api_key, on_progress=None, log=None):
        calls.append(len(waiting))
        attempt = service.ai_assign.Attempt(1, "가짜/모델:free", outcome, 0.1, "")
        if log:
            log(attempt)
        return (pairs_from_ai, [attempt]) if outcome == "성공" else (None, [attempt])

    runner.calls = calls
    return runner


def finish_easy(pool):
    load(pool, "easy.csv", 3)
    for no, team in (("2026101", 1), ("2026102", 2), ("2026103", 3), ("2026104", 1), ("2026105", 2), ("2026106", 3)):
        service.apply(pool, no, team)
    for voter, applicant in (("2026101", "2026104"), ("2026102", "2026105"), ("2026103", "2026106")):
        service.vote(pool, voter, applicant, "찬성")


def test_plan_requires_close_and_admin(pool):
    finish_easy(pool)
    assert service.plan_assignment(pool, "admin", "key").outcome.text == "막힘: 모집 마감 전에는 배정할 수 없음"
    service.close(pool, "admin")
    assert service.plan_assignment(pool, "2026101", "key").outcome.text == "막힘: 관리자만 할 수 있음"


def test_plan_uses_ai_answer_then_confirm(pool):
    finish_easy(pool)
    service.close(pool, "admin")
    runner = fake_runner([("2026107", 2), ("2026108", 1)])
    plan = service.plan_assignment(pool, "admin", "key", runner=runner)
    assert plan.outcome.kind == "승인" and plan.source.startswith("1차 모델")
    assert service.recent_ai_logs(pool)[0]["model"] == "가짜/모델:free"
    assert service.confirm(pool, "admin", plan.pairs).text == "승인: 배정안을 확정함 (2명)"
    assert service.load_state(pool).unassigned() == []


def test_plan_falls_back_to_solver_when_ai_fails(pool):
    finish_easy(pool)
    service.close(pool, "admin")
    plan = service.plan_assignment(pool, "admin", "key", runner=fake_runner(None, outcome="시간 초과"))
    assert plan.source == "앱이 스스로 배정함"
    assert [a.outcome for a in plan.attempts] == ["시간 초과"]
    assert service.confirm(pool, "admin", plan.pairs).kind == "승인"


def test_no_valid_assignment_skips_ai(pool):
    csv = "student_no,name,main_role,sub_roles\n9000001,가상1,기획자,\n9000002,가상2,테스터,\n9000003,가상3,발표자,\n9000004,가상4,보고서 작성자,\n"
    assert service.start_roster(pool, "admin", csv.encode("utf-8-sig"), 2).kind == "승인"
    service.close(pool, "admin")
    runner = fake_runner([])
    plan = service.plan_assignment(pool, "admin", "key", runner=runner)
    assert plan.outcome.text == "막힘: 규칙을 지키는 배정이 없음"
    assert runner.calls == []
    assert any("웹 프로그래머를 맡을 학생이 없음" in r for r in plan.reasons)


def test_confirm_rejects_stale_plan(pool):
    finish_easy(pool)
    service.close(pool, "admin")
    plan = service.plan_assignment(pool, "admin", None)
    load(pool, "easy.csv", 3)
    assert service.confirm(pool, "admin", plan.pairs).text == "막힘: 모집 마감 전에는 확정할 수 없음"
    assert service.confirm(pool, "admin", []).text == "막힘: 확정할 배정안이 없음"


def test_nothing_to_assign(pool):
    finish_easy(pool)
    service.close(pool, "admin")
    plan = service.plan_assignment(pool, "admin", None)
    service.confirm(pool, "admin", plan.pairs)
    assert service.plan_assignment(pool, "admin", None).outcome.text == "막힘: 배정할 학생이 없음"
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q -k "plan or confirm or assign"` → FAIL

- [ ] **Step 3: `service.py`에 추가**

파일 위쪽 import에 `import ai_assign`, `import solver`를 더하고, 끝에 아래를 붙인다:
```python
# ---------- 배정 ----------

@dataclass
class AssignPlan:
    outcome: Outcome
    pairs: list[tuple[str, int]] = field(default_factory=list)
    source: str = ""
    attempts: list = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def plan_assignment(pool, actor_no: str, api_key: str | None, on_progress=None, runner=None) -> AssignPlan:
    """배정안을 만든다(PRD 4.2절). 확정은 confirm()이 따로 한다."""
    runner = runner or ai_assign.run
    with pool.connection() as conn:
        if not _is_admin(conn, actor_no):
            return AssignPlan(NOT_ADMIN)
    state = load_state(pool)
    if not state.closed:
        return AssignPlan(Outcome("막힘", "모집 마감 전에는 배정할 수 없음"))
    teams, waiting = state.team_map(), state.unassigned()
    if not waiting and not any(rules.team_problems(t, ms) for t, ms in teams.items()):
        return AssignPlan(Outcome("막힘", "배정할 학생이 없음"))
    fallback = solver.solve(teams, waiting)
    if fallback is None:  # 규칙을 지키는 배정이 없으면 AI를 부르지 않는다(PRD 4.2절 3)
        return AssignPlan(Outcome("막힘", "규칙을 지키는 배정이 없음"), reasons=solver.infeasible_reasons(teams, waiting))
    attempts: list = []
    if waiting and api_key:
        pairs, attempts = runner(
            teams,
            waiting,
            validate=lambda p: rules.validate_assignment(teams, waiting, p),
            api_key=api_key,
            on_progress=on_progress,
            log=lambda attempt: log_ai(pool, attempt),
        )
        if pairs is not None:
            win = attempts[-1]
            source = f"{win.tier}차 모델 {win.model}"
            return AssignPlan(Outcome("승인", f"배정안을 만듦 – {source}"), pairs, source, attempts)
    source = "앱이 스스로 배정함" if api_key else "앱이 스스로 배정함 (OPENROUTER_API_KEY 없음)"
    return AssignPlan(Outcome("승인", f"배정안을 만듦 – {source}"), fallback, source, attempts)


def confirm(pool, actor_no: str, pairs) -> Outcome:
    """배정안을 지금 DB 상태로 다시 검사한 뒤 저장한다(PRD 4.2절 9)."""
    if not pairs:
        return Outcome("막힘", "확정할 배정안이 없음")
    try:
        with pool.connection() as conn, conn.transaction():
            if not _is_admin(conn, actor_no):
                return NOT_ADMIN
            _lock_teams(conn)
            if not _is_closed(conn):
                return Outcome("막힘", "모집 마감 전에는 확정할 수 없음")
            team_ids = {r["team_no"]: r["id"] for r in conn.execute("select id, team_no from tf_teams").fetchall()}
            teams = {no: [s for _, s in _members(conn, tid)] for no, tid in team_ids.items()}
            placed = {s.student_no for ms in teams.values() for s in ms}
            rows = conn.execute(STUDENTS_SQL).fetchall()
            ids = {r["student_no"]: r["id"] for r in rows}
            waiting = [_row_student(r) for r in rows if r["student_no"] not in placed]
            problems = rules.validate_assignment(teams, waiting, pairs)
            if problems:
                return Outcome("막힘", "배정안이 지금 상태와 맞지 않음 – " + "; ".join(problems[:3]))
            for student_no, team_no in pairs:
                _add_member(conn, team_ids[team_no], ids[student_no])
    except errors.IntegrityError:
        return Outcome("막힘", "확정하는 중 충돌이 남. AI 배정을 다시 누름")
    return Outcome("승인", f"배정안을 확정함 ({len(pairs)}명)")


def log_ai(pool, attempt) -> None:
    with pool.connection() as conn:
        conn.execute(
            "insert into tf_ai_logs (tier, model, outcome, elapsed_sec, detail) values (%s, %s, %s, %s, %s)",
            (attempt.tier, attempt.model, attempt.outcome, attempt.elapsed, attempt.detail),
        )


def recent_ai_logs(pool, limit: int = 10) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(
            "select tier, model, outcome, elapsed_sec, detail, created_at from tf_ai_logs order by id desc limit %s",
            (limit,),
        ).fetchall()
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_service.py -q` → 21 passed

- [ ] **Step 5: 커밋**: `git add service.py tests/test_service.py && git commit -m "배정안 만들기(전수 탐색 먼저, AI 다음, 자체 배정 마지막)와 확정"`

---

### Task 15: 화면 3부 — AI 배정 진행 안내, 배정안 표, 확정, AI 기록

**Files:**
- Modify: `streamlit_app.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `service.plan_assignment`, `service.confirm`, `service.recent_ai_logs`, `ai_assign.TIMEOUT_SEC`
- Produces: `render_plan(plan, state)`

- [ ] **Step 1: 실패하는 화면 시험 추가**

```python
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
```

- [ ] **Step 2: 실패 확인**: `.venv\Scripts\python -m pytest tests/test_app.py -q -k assign` → FAIL

- [ ] **Step 3: `streamlit_app.py` 바꾸기**

import에 `import ai_assign`을 더한다. `admin_page`의 "2. 마감과 배정" 부분(마감 단추 처리 뒤부터 `st.subheader("3. 현황")` 앞까지)을 아래로 바꾼다:
```python
    assign_clicked = assign_col.button("AI 배정", key="admin_assign")
    confirm_clicked = confirm_col.button("배정안 확정", key="admin_confirm")
    status_box = st.container(key="assign_status", border=True)
    if assign_clicked:
        with status_box:
            line = st.empty()
        line.info("규칙을 지키는 배정이 있는지 확인하는 중")

        def progress(tier, model, elapsed):
            line.info(f"{tier}차 모델({model})의 응답을 기다리는 중 · {elapsed:.0f}초 경과 / {ai_assign.TIMEOUT_SEC:.0f}초")

        plan = service.plan_assignment(pool, user.student_no, get_secret("OPENROUTER_API_KEY"), on_progress=progress)
        st.session_state["plan"] = plan
        set_result(plan.outcome.text)
        st.rerun()
    if confirm_clicked:
        plan = st.session_state.get("plan")
        outcome = service.confirm(pool, user.student_no, plan.pairs if plan else [])
        set_result(outcome.text)
        if outcome.kind == "승인":
            st.session_state.pop("plan", None)
        st.rerun()
    with status_box:
        render_plan(st.session_state.get("plan"), service.load_state(pool))
```
(Task 6의 `assign_col.button(...)`, `confirm_col.button(...)`, `st.container(key="assign_status"...)` 세 줄은 지운다.)

`render_plan`을 추가한다:
```python
def render_plan(plan, state) -> None:
    if plan is None:
        st.caption("AI 배정을 누르면 진행 상황과 배정안이 여기에 나옴")
        return
    if plan.reasons:  # PRD 4.2절 3: 규칙을 지키는 배정이 없음과 그 이유
        st.error("규칙을 지키는 배정이 없음")
        for reason in plan.reasons:
            st.markdown(f"- {reason}")
        return
    if plan.outcome.kind != "승인":
        st.warning(plan.outcome.text)
        return
    for a in plan.attempts:
        detail = f" – {a.detail}" if a.detail else ""
        st.markdown(f"- {a.tier}차 모델 `{a.model}`: {a.outcome} ({a.elapsed:.0f}초){detail}")
    st.success(f"배정안 출처: {plan.source}")
    rows = []
    for student_no, team_no in plan.pairs:
        s = state.students.get(student_no)
        if s:
            rows.append({"이름": s.name, "주 역할": s.main_role, "보조 역할": ", ".join(s.sub_roles) or "없음", "배정된 팀": f"팀{team_no}"})
    st.table(rows)
```

`admin_status` 끝에 AI 호출 기록을 더한다:
```python
    logs = service.recent_ai_logs(pool)
    if logs:
        st.markdown("**최근 AI 호출 기록**")
        st.table([
            {
                "시각(KST)": r["created_at"].astimezone(KST).strftime("%m-%d %H:%M:%S"),
                "차수": f"{r['tier']}차",
                "모델": r["model"],
                "결과": r["outcome"],
                "경과(초)": float(r["elapsed_sec"]),
                "사유": r["detail"] or "",
            }
            for r in logs
        ])
```

- [ ] **Step 4: 통과 확인**: `.venv\Scripts\python -m pytest -q` → 모두 통과

- [ ] **Step 5: 커밋**: `git add streamlit_app.py tests/test_app.py && git commit -m "화면 3부: AI 배정 진행 안내, 배정안 표, 확정, AI 기록"`

---

### Task 16: 연습 시나리오 3개 재현 시험

**Files:**
- Create: `tests/test_scenarios.py`

- [ ] **Step 1: 시험 작성**(공고 부록 1~3의 단계를 동작마다 적음. 시나리오는 시험에만 둔다)

```python
# 생성: <KST 시각>
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
```

- [ ] **Step 2: 통과 확인**: `.venv\Scripts\python -m pytest tests/test_scenarios.py -q` → 3 passed. 실패하면 `superpowers:systematic-debugging`으로 원인을 찾는다(시험의 기대 결과를 앱에 맞춰 고치지 않는다. 기대 결과는 공고 부록이 정본)

- [ ] **Step 3: 전체 시험과 커밋**: `.venv\Scripts\python -m pytest -q` → 모두 통과. `git add tests/test_scenarios.py && git commit -m "연습 시나리오 3개 재현 시험"`

- [ ] **Step 4: 앱을 띄워 직접 확인하고 3단계 보고 후 멈춤**

**3단계 브라우저 확인 항목(사용자가 확인, 실제 AI 호출 포함)**
1. 쉬움 시나리오(부록 1)를 2단계 확인처럼 끝까지 하고 `AI 배정`을 누르면 `assign_status`에 `1차 모델(…)의 응답을 기다리는 중 · n초 경과 / 120초`가 바뀌며 보인다
2. 끝나면 시도 기록(차수, 모델, 결과, 걸린 초)과 배정안 표(이름, 주 역할, 보조 역할, 배정된 팀)가 보인다
3. `배정안 확정` → `승인: 배정안을 확정함 (2명)`, 팀이 없는 학생이 `없음`
4. 중간 시나리오(부록 2) 1~11단계: 3단계 `막힘`(같은 주 역할), 6단계 `거절`, 8단계 팀4는 `대기`이고 팀3 지원 단추는 비활성, 9단계 마감 뒤 학생3·학생11·학생12가 팀이 없는 학생에 보임, 10단계 학생2의 지원 단추 비활성
5. 어려움 시나리오(부록 3) 1~15단계: 6단계 둘 다 `대기`, 8단계 마지막 찬성에서 `거절: 승인 직전 검사 – 같은 주 역할의 팀원이 있음`, 11단계 `막힘: 필수 포함 역할을 맡을 학생의 자리가 모자람`, 15단계 배정 확정 뒤 모든 팀이 규칙을 지킴
6. 현황의 "최근 AI 호출 기록" 시각이 한국 시각이다
7. AI 실패(시간 초과, 429, 검사 불통과 등)가 한 번이라도 나오면 그 화면을 캡처해 `img/`에 저장한다(README 5항 근거). 캡처 파일 이름과 상황을 `docs/cases.md`에 적는다

확인을 마치면 `git switch main && git merge --no-ff stage-3 -m "3단계: 배정"`.

---

# 4단계: 배포와 DB 일시정지 막기

### Task 17: 깃허브 비공개 저장소

- [ ] **Step 1: 브랜치**: `git switch -c stage-4`
- [ ] **Step 2: 올리기 전 비밀 값 검사**

```powershell
git ls-files | Select-String -Pattern '\.env$|secrets\.toml'      # 아무것도 나오지 않아야 함
git log -p --all | Select-String -Pattern 'sk-or-v1-[A-Za-z0-9]{8}|pooler\.supabase\.com:\d+/postgres\?|postgresql://postgres\.[a-z0-9]+:[^@\s<]+@' | Measure-Object | Select-Object -ExpandProperty Count   # 0 이어야 함
```
`.env.example`의 자리 표시 값(`<DB비밀번호>`)은 걸리지 않는다. 0이 아니면 멈추고 사용자에게 알린다.

- [ ] **Step 3: 저장소 만들기**(사용자에게 이름을 확인받은 뒤. 기본 `team-formation`)

```bash
gh repo create team-formation --private --source=. --remote=origin
git push -u origin main
```

### Task 18: Streamlit Community Cloud 배포(사용자가 화면에서 함)

사용자에게 다음 절차를 안내한다(비밀 값 입력과 계정 설정은 사용자가 직접 함):
1. share.streamlit.io에 깃허브 계정으로 로그인
2. **Workspace settings → Linked accounts → GitHub의 Private access 옆 "Connect here"**로 비공개 저장소 읽기 허락
3. **Create app → Deploy a public app from GitHub**: Repository `surplusnnny/team-formation`, Branch `main`, Main file path `streamlit_app.py`, App URL은 원하는 이름
4. **Advanced settings → Secrets**에 `.env`의 세 값을 `이름 = "값"` 꼴로 붙여 넣는다(자동 완성된 예전 값은 지움)
   ```toml
   OPENROUTER_API_KEY = "…"
   DATABASE_URL = "…"
   ADMIN_PASSWORD = "…"
   ```
5. 배포가 끝나면 앱의 **Settings → Sharing → Who can view this app → This app is public and searchable → Save changes**
6. 배포 주소를 알려 준다

그 뒤 확인: 로그인하지 않은 브라우저(내장 브라우저의 새 탭)로 배포 주소를 열어 로그인 화면이 보이는지, `.st-key-login_student_no` 등 key가 있는지 본다.

### Task 19: DB 일시정지 막기(GitHub Actions 예약 실행)

**Files:**
- Create: `scripts/keepalive.py`, `.github/workflows/keepalive.yml`

- [ ] **Step 1: `scripts/keepalive.py`**

```python
# 생성: <KST 시각>
"""매일 한 번 DB에 질의해 Supabase 무료 프로젝트가 일시정지되지 않게 한다(GitHub Actions가 실행).
DB 주소는 출력하지 않는다. 커밋을 만들지 않는다."""
import os
import sys

import psycopg

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL: 없음")
with psycopg.connect(url, prepare_threshold=None, connect_timeout=30) as conn:
    conn.execute(
        """insert into tf_settings (key, value) values ('last_keepalive', now()::text)
           on conflict (key) do update set value = excluded.value"""
    )
    students = conn.execute("select count(*) from tf_students").fetchone()[0]
print(f"keepalive 성공: tf_students 행 {students}개")
```

- [ ] **Step 2: `.github/workflows/keepalive.yml`**

```yaml
# 생성: <KST 시각>
name: DB keepalive
on:
  schedule:
    - cron: "17 0 * * *"   # 매일 00:17 UTC = 09:17 KST
  workflow_dispatch:
jobs:
  ping:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "psycopg[binary]==3.3.6"
      - run: python scripts/keepalive.py
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

- [ ] **Step 3: 저장소 Secret 넣기**(값을 화면에 내지 않고 파이프로 넘김)

```powershell
.venv\Scripts\python -c "from dotenv import dotenv_values; print(dotenv_values('.env')['DATABASE_URL'], end='')" | gh secret set DATABASE_URL
gh secret list
```
Expected: 목록에 `DATABASE_URL`

- [ ] **Step 4: 커밋, 병합, 수동 실행으로 확인**

```bash
git add scripts/keepalive.py .github/workflows/keepalive.yml
git commit -m "DB 일시정지 막기: 매일 예약 질의"
git switch main && git merge --no-ff stage-4 -m "4단계: 배포와 DB 일시정지 막기" && git push
gh workflow run keepalive.yml
gh run list --workflow keepalive.yml --limit 1
```
Expected: 몇 분 안에 `completed success`. 실행 기록의 로그에 `keepalive 성공`

- [ ] **Step 5: 4단계 보고 후 멈춤**

**4단계 브라우저 확인 항목(사용자가 확인)**
1. 시크릿 창으로 배포 주소를 열면 로그인 화면이 보인다
2. 배포 주소에서 쉬움 시나리오(부록 1)를 처음부터 끝까지 해 본다(학생 창은 브라우저 창이나 시크릿 창을 여러 개 써서 동시에 띄움)
3. 화면이 몇 초씩 느리지 않다(지원 단추를 누른 뒤 결과가 3초 안에 나옴)
4. GitHub 저장소의 Actions 탭에 `DB keepalive`가 성공으로 보인다
5. 배포한 앱 화면 어디에도 키나 DB 주소가 보이지 않는다

---

# 5단계: 문서와 제출물

### Task 20: README.md

**Files:**
- Create: `README.md`, `img/*.png`
- Modify: `docs/cases.md`

- [ ] **Step 1: 브랜치**: `git switch -c stage-5`
- [ ] **Step 2: 근거 모으기** — `docs/cases.md`에 모아 둔 사례마다 근거가 실제로 있는지 확인한다(화면 파일이 `img/`에 있는지, 커밋 번호가 `git log`에 있는지, 시나리오 단계가 맞는지). 근거가 없는 사례는 README에 넣지 않는다(꾸며 낸 사례는 정직성 20번 위반)
- [ ] **Step 3: `README.md` 작성**(공고 7.1절 양식)

```markdown
<!-- 생성: <KST 시각> -->
# 팀 편성 웹 앱

작성자: <사용자가 정함>

## 1. 배포 주소
<배포 주소>

## 2. PRD와 구현 계획의 위치
- PRD: `PRD.md`
- 구현 계획: `IMPL-PLAN.md`
- DB 스키마: `schema.sql`

## 3. 고른 해결 방법
| 기능 | 해결 | 만든 방법 |
|---|---|---|
| 다른 사람의 변경 보기 | 어려운 해결 | `st.fragment(run_every=5)`로 학생 화면과 관리자 현황을 5초마다 다시 그림 |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결 | 지원할 때 남는 자리 수와 못 채운 필수 역할 수를 비교해 막음(`rules.join_block_reason`) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결 | 마지막 찬성 때 팀 행을 잠그고 규칙을 다시 검사(`service._vote`) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결 | `tf_members`의 `(team_id, slot_no)` 기본 키와 `student_id` 유일성(`schema.sql`) |
| AI 응답이 늦을 때 | 어려운 해결 | 응답을 별도 스레드에서 스트리밍으로 받고, 모델마다 부른 때부터 120초가 넘으면 끊음(`ai_assign.call_model`) |
| 3차 모델까지 실패 | 어려운 해결 | 전수 탐색으로 다섯 가지 검사를 모두 통과하는 배정을 찾음(`solver.solve`) |
| AI 대기 중 화면 | 어려운 해결 | `assign_status`에 몇 차 모델을 몇 초째 기다리는지 보여 줌 |
| DB 일시정지 막기 | 어려운 해결 | GitHub Actions 예약 실행으로 매일 09:17 KST에 DB 질의(`.github/workflows/keepalive.yml`) |

## 4. 쓴 모델 3개
1차 `<모델>`, 2차 `<모델>`, 3차 `<모델>`

## 5. 오픈라우터 AI 모델 호출 실패 사례
<docs/cases.md 5절에서 근거가 있는 것. 화면 img/…png>

## 6. 클로드가 잘못된 추론이나 답변을 한 사례와 알아챈 방법
<docs/cases.md 6절에서 근거(화면이나 커밋)가 있는 것>

## 7. 앱에서 발견한 문제점이나 개선 필요 사항
<docs/cases.md 7절. 연습 시나리오의 단계와 화면 img/…png>

## 실행 방법(로컬)
1. `python -m venv .venv` → `.venv\Scripts\python -m pip install -r requirements-dev.txt`
2. `.env.example`을 `.env`로 복사해 값을 채움
3. `.venv\Scripts\python scripts\apply_schema.py`
4. `.venv\Scripts\python -m streamlit run streamlit_app.py`
5. 시험: `.venv\Scripts\python -m pytest`
```
`<…>` 자리는 사용자 확인을 거쳐 실제 값과 근거로 채운다. 작성자 이름은 사용자에게 묻는다(자기 이름은 적어도 됨). 학번은 README에 쓰지 않는다.

- [ ] **Step 4: 커밋, 병합, 푸시**

```bash
git add README.md img docs/cases.md
git commit -m "README: 7.1절 양식과 사례 근거"
git switch main && git merge --no-ff stage-5 -m "5단계: 문서" && git push
```

### Task 21: 제출물 점검과 압축 파일

- [ ] **Step 1: 최종 점검**

```powershell
.venv\Scripts\python -m pytest -q                       # 모두 통과(채점 기간 전에만)
git status --short                                        # 비어 있어야 함
git log -1 --format="%H %cd"                               # 마지막 커밋이 11/2 23:59 KST 이전
```
`schema.sql`이 앱이 쓰는 테이블·열·제약과 같은지 `service.py`의 SQL과 대조해 다르면 사용자에게 알린다.

- [ ] **Step 2: 압축 파일**(커밋한 파일만. 파일 이름의 학번은 사용자에게 묻는다)

```powershell
git archive --format=zip -o <학번>.zip HEAD
.venv\Scripts\python -c "import zipfile,sys; n=zipfile.ZipFile(sys.argv[1]).namelist(); print('파일', len(n), '개'); print('.env 있음' if any(x.split('/')[-1]=='.env' for x in n) else '.env 없음')" <학번>.zip
```
Expected: `.env 없음`. zip은 `.gitignore`(`*.zip`)로 커밋되지 않는다.

- [ ] **Step 3: 제출 안내**(사용자가 함)
1. e-class 제출 칸: 깃허브 저장소 주소, 배포 주소, 관리자 비밀번호를 직접 적고 `<학번>.zip`을 첨부
2. 마감(11/2 23:59) 뒤에는 커밋하지 않음
3. **11/3(화) 09:00까지** 저장소를 공개로 바꿈: `gh repo edit surplusnnny/team-formation --visibility public --accept-visibility-change-consequences`
4. 11/3~11/4에는 관리자 비밀번호를 바꾸지 않고, DB 시험(`pytest`)을 돌리지 않음. 무료 모델 하루 한도 가운데 30번 이상을 남겨 둠
5. Supabase에서 일시정지 예고 메일이 오면 대시보드에서 프로젝트를 열어 둠

---

## PRD 대응표

| PRD | 과제 |
|---|---|
| 1.4 고른 해결 방법 | 다른 사람의 변경 보기: Task 10 / 필수 역할 자리: Task 2, 7 / 승인 직전 재검사: Task 8 / DB 유일성: Task 4, 9 / 120초 제한: Task 12 / 자체 배정: Task 11, 14 / 대기 안내: Task 15 / 일시정지 막기: Task 19 |
| 2.2~2.3 팀 규칙, 자리 계산 | Task 2 |
| 3.1 지원 | Task 7, 10 |
| 3.2~3.3 투표, 승인 직전 검사 | Task 8, 10 |
| 3.4~3.5 한 학생의 지원, 막힘과 거절 | Task 7, 8 |
| 3.6 동시성 | Task 4, 7, 9 |
| 4.1 마감 | Task 9, 10 |
| 4.2~4.5 배정, 검사, 탐색, 이유 | Task 2, 11, 14, 15 |
| 4.6 AI 호출 | Task 12, 13, 14 |
| 5 명단 올리기 | Task 3, 5, 6 |
| 6 화면과 key | Task 6, 10, 15 |
| 7 데이터 | Task 4, 5 |
| 8 키 관리와 보안 | Task 1, 4, 6, 17 |
| 9 배포와 일시정지 | Task 17, 18, 19 |
| 10 완료 기준 | 1~2: Task 16 / 3: Task 6, 10, 18 / 4: Task 10 / 5~6: Task 12, 14 / 7: Task 14, 15 / 8: Task 5, 6 / 9: Task 17 / 10: Task 4, 21 / 11: Task 20 |
| 11 시험 | Task 2~16 |
| 12 제출물 | Task 20, 21 |
