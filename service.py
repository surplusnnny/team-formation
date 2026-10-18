# 생성: 2026-10-18 17:34 KST
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
