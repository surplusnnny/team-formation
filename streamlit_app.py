# 생성: 2026-10-18 17:34 KST
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
