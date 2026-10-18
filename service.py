# 생성: 2026-10-18 17:34 KST
"""DB 트랜잭션 단위의 동작(PRD 3~5장). 화면(Streamlit)을 모른다.
지원·투표·마감·확정은 트랜잭션 하나 안에서 팀 행을 잠그고(FOR UPDATE) 검사한 뒤 기록한다."""
from __future__ import annotations

from dataclasses import dataclass, field

import bcrypt
from psycopg import errors

import ai_assign
import rules
import solver
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
