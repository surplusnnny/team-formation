# CLAUDE.md
<!-- 생성: 2026-10-18 17:12 KST -->

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
