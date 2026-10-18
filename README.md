<!-- 생성: 2026-10-18 18:36 KST -->
# 팀 편성 웹 앱 (중간 과제)

작성자: 박신우

학생이 팀 프로젝트를 위한 팀을 스스로 편성하는 Streamlit 웹 앱이다. 학생은 팀에 지원하고 팀원은 찬성·거부로 받아들일지 정한다. 모집을 마감한 뒤 팀이 없는 학생은 AI(오픈라우터 무료 모델)가 배정안을 내고, 앱이 그 배정안을 규칙으로 검사한 뒤 관리자가 확정한다.

## 1. 배포 주소

https://team-formation-2026-10.streamlit.app/

## 2. PRD와 구현 계획의 위치

- PRD: [`PRD.md`](PRD.md)
- 구현 계획: [`IMPL-PLAN.md`](IMPL-PLAN.md) (5단계, 21개 과제. 단계마다 브랜치에서 만들고 확인한 뒤 `main`에 병합)
- DB 스키마: [`schema.sql`](schema.sql)
- 작업 중 사례 기록: [`docs/cases.md`](docs/cases.md)

## 3. 고른 해결 방법

모두 어려운 해결로 만들었다.

| 기능 | 해결 | 만든 방법 |
|---|---|---|
| 다른 사람의 변경 보기 | 어려운 해결 | `st.fragment(run_every=5)`로 학생 화면과 관리자 현황을 5초마다 그 부분만 다시 그림(`streamlit_app.py`의 `student_body`, `admin_status`) |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결 | 지원할 때 "들어간 뒤 남는 자리 수 < 아직 못 채운 필수 역할 수"이면 막음. 기획자·웹 프로그래머 자리는 서로 다른 학생으로 짝지어 셈(`rules.join_block_reason`, `rules.filled_required`) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결 | 마지막 찬성으로 전원이 찬성한 순간 팀 행을 잠그고(`SELECT … FOR UPDATE`) 정원·주 역할·필수 역할을 다시 검사함. 처리 순서는 투표가 끝난 순서(`service._vote`) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결 | `tf_members`의 `(team_id, slot_no)` 기본 키와 `student_id` 유일 제약으로 먼저 도착한 학생만 기록(`schema.sql`). 두 학생이 같은 순간 지원하는 시험으로 확인(`tests/test_service.py::test_two_students_apply_to_empty_team_at_once`) |
| AI 응답이 늦을 때 | 어려운 해결 | 응답을 별도 스레드에서 스트리밍으로 받고, 모델을 부른 때부터 0.5초마다 경과 시간을 재서 120초가 넘으면 연결을 끊고 다음 모델로 넘어감. 응답이 천천히 와도 120초에서 끊김(`ai_assign.call_model`, 시험 `test_call_model_total_timeout_cuts_slow_stream`) |
| 3차 모델까지 실패 | 어려운 해결 | 전수 탐색으로 다섯 가지 검사를 모두 통과하는 배정을 끝까지 찾음. 규칙을 지키는 배정이 없으면 AI를 부르지 않고 이유를 보여 줌(`solver.solve`, `solver.infeasible_reasons`) |
| AI 대기 중 화면 | 어려운 해결 | `assign_status`에 "n차 모델(모델 이름)의 응답을 기다리는 중 · n초 경과 / 120초"를 1초마다 갱신 |
| DB(Supabase) 일시정지 막기 | 어려운 해결 | GitHub Actions 예약 실행으로 매일 09:17 KST에 DB에 질의(`.github/workflows/keepalive.yml`, `scripts/keepalive.py`). 커밋을 만들지 않음 |

## 4. 쓴 모델 3개

1차 `nvidia/nemotron-3-super-120b-a12b:free`, 2차 `google/gemma-4-31b-it:free`, 3차 `nvidia/nemotron-3-ultra-550b-a55b:free`

무료 모델 자동 라우터(`openrouter/free`)는 쓰지 않았다.

## 5. 오픈라우터 AI 모델 호출 실패 사례

### 5-1. 2차 모델이 HTTP 429로 거절함
- 2026-10-18 18:01, 18:02, 18:36 KST에 2차 모델 `google/gemma-4-31b-it:free`를 앱의 AI 호출 코드(`ai_assign.run`)로 불렀는데, 세 번 모두 0.5~0.7초 만에 `HTTP 429 Provider returned error`로 거절됨. 앱은 이런 응답을 실패로 기록하고 다음 모델로 넘어간다
- 화면: [`img/ai-429.png`](img/ai-429.png) (18:36, `scripts/try_models.py`로 2차 모델을 부른 터미널)

### 5-2. 120초 안에 응답이 끝나지 않아 끊음
- 2026-10-18 18:02 KST, 후보로 시험한 `nvidia/nemotron-3.5-lightning:free`가 응답을 끝내지 못해 앱이 **120.1초에서 연결을 끊고** "시간 초과"로 처리함. 모델별 120초 전체 제한이 실제 모델에서 동작함을 확인한 사례
- 같은 시험에서 `thinkingmachines/inkling-small:free`는 HTTP 403("only available on agentic harnesses")으로 실패함. 결과는 [`docs/cases.md`](docs/cases.md) 5-1절에 기록함

## 6. 클로드가 잘못된 추론이나 답변을 한 사례와 알아챈 방법

### 6-1. 화면 시험 파일의 경로를 잘못 적음
- 클로드가 구현 계획서 Task 6에 화면 시험을 `AppTest.from_file("streamlit_app.py")`로 적음(커밋 `d9bb12e`의 `IMPL-PLAN.md`). 클로드는 이 경로가 작업 폴더 기준이라고 추론했으나, Streamlit의 AppTest는 **시험 파일이 있는 `tests/` 폴더 기준**으로 경로를 찾음
- 알아챈 방법: 앱을 만든 뒤에도 시험 4개가 모두 `AppTest script not found at …\tests\streamlit_app.py`로 실패해서, 오류 메시지의 경로를 읽고 알아챔. "실패하는 시험" 단계에서 시험이 실패한 이유도 사실은 "앱이 없음"이 아니라 "경로가 틀림"이었음. `../streamlit_app.py`로 고치고, 앱 파일을 잠시 치워 시험이 올바른 이유로 실패하는지 다시 확인함
- 근거: 커밋 `d9bb12e`의 `IMPL-PLAN.md`(틀린 경로)와 커밋 `fdafb3b`의 `tests/test_app.py`(고친 경로)

### 6-2. Supabase 화면 안내가 실제 화면과 달랐음
- DB 주소를 받는 방법을 안내하면서 클로드가 "Project Settings → Database에서 비밀번호를 바꾼다"고 답함. 실제 Supabase 화면의 Project Settings에는 비밀번호 칸이 없었고, Database 메뉴의 Settings로 옮겨져 있었음
- 알아챈 방법: 작성자가 Project Settings 화면을 캡처해 "아무것도 없다"고 보여 줌. 클로드가 확인하지 않은 예전 화면 구성을 사실처럼 말한 것임

## 7. 앱에서 발견한 문제점이나 개선 필요 사항

화면: [`img/easy-step6-status.jpg`](img/easy-step6-status.jpg) (부록 1 쉬움 시나리오 6단계에서 배정을 확정한 뒤 관리자 화면의 현황)

### 7-1. 보조 역할이 명단 CSV와 다른 순서로 보임
- 부록 1(쉬움) 6단계 뒤 팀2의 **학생8(TT;RW;PT)**이 "보조 역할 발표자, 보고서 작성자"로 보임. CSV에는 `보고서 작성자;발표자` 순서로 적혀 있음
- 원인: `tf_student_sub_roles`에 순서 열이 없어, 읽을 때 역할 이름순으로 정렬함. 고치려면 순서 열을 더해야 함

### 7-2. AI 배정이 1분 넘게 걸림
- 같은 화면의 "최근 AI 호출 기록"에서 1차 모델이 83.5초(부록 3 어려움 15단계, 8명 배정)와 54.8초(부록 1 쉬움 6단계, 2명 배정) 걸림. 그동안 관리자는 기다려야 하고, 현황(팀 목록, 팀이 없는 학생)도 갱신되지 않음
- 개선 방향: 시험에서 6.4초로 가장 빨랐던 `nemotron-3-ultra`를 1차로 올리거나, AI 호출을 배경 작업으로 돌려 현황이 계속 갱신되게 함

### 7-3. AI 호출 기록의 경과 시간이 `54.8000`처럼 보임
- 같은 화면에서 경과(초) 칸이 소수 넷째 자리까지 보임. 표로 그릴 때 소수 한 자리로 맞추지 않았기 때문임

## 실행 방법(로컬)

1. `python -m venv .venv` → `.venv\Scripts\python -m pip install -r requirements-dev.txt`
2. `.env.example`을 `.env`로 복사해 `OPENROUTER_API_KEY`, `DATABASE_URL`(Supabase Transaction pooler 주소), `ADMIN_PASSWORD`를 채움
3. `.venv\Scripts\python scripts\apply_schema.py` (tf_ 테이블 생성)
4. `.venv\Scripts\python -m streamlit run streamlit_app.py`
5. 시험: `.venv\Scripts\python -m pytest` (단위 시험, 서비스 시험, 화면 시험, 연습 시나리오 3개 재현. DB 시험은 실제 DB의 tf_ 데이터를 지움)

## 파일 구성

| 파일 | 맡는 일 |
|---|---|
| `streamlit_app.py` | 화면(로그인, 학생 화면, 관리자 화면). key는 공고 2.7절 표 그대로 |
| `service.py` | DB 트랜잭션 단위 동작: 로그인, 명단 올리기, 지원, 투표, 마감, 배정안, 확정 |
| `rules.py` | 팀 규칙과 배정안 다섯 가지 검사 |
| `solver.py` | 전수 탐색 배정과 배정이 없을 때의 이유 |
| `ai_assign.py` | 오픈라우터 1·2·3차 호출, 모델별 120초 제한 |
| `roster.py` | 명단 CSV 읽기(BOM, 공백 정리) |
| `db.py` | 비밀 값 읽기와 DB 연결 풀(한 번만 만들어 재사용) |
