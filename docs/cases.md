<!-- 생성: 2026-10-18 17:12 KST -->
# README 사례 기록

작업 중 생긴 일을 그때그때 적는다. README 7.1절 5~7항의 근거(화면 파일, 커밋, 시나리오 단계)로 쓴다.

## 5. AI 모델 호출 실패 사례

### 5-1. 모델 후보 시험에서 나온 실패 (2026-10-18 18:01~18:04 KST, scripts/try_models.py)
쉬움 시나리오 마감 직후 상태(팀1~3에 2명씩, 학생7·학생8이 팀 없음)를 보내 모델마다 한 번씩 부름
- `google/gemma-4-31b-it:free`: HTTP 429 "Provider returned error"(0.5초), 다시 불러도 429(0.6초) → 앱은 이런 경우 다음 모델로 넘어감
- `google/gemma-4-26b-a4b-it:free`: HTTP 429(0.7초)
- `nvidia/nemotron-3.5-lightning:free`: **120.1초에서 끊고 시간 초과로 처리**(모델별 120초 전체 제한이 실제 모델에서 동작함)
- `thinkingmachines/inkling-small:free`: HTTP 403 "only available on agentic harnesses"
- 성공: `nvidia/nemotron-3-ultra-550b-a55b:free` 6.4초, `nvidia/nemotron-3-super-120b-a12b:free` 34.7초, `dots-studio/dots-3-note-preview:free` 40.7초
- 결정: 사용자가 계획서의 1·2·3차(super → gemma-4-31b → ultra)를 그대로 쓰기로 함
- 화면 근거: 3단계 확인 때 앱의 "최근 AI 호출 기록"과 assign_status를 캡처해 img/ 에 둘 것

## 6. 클로드가 잘못 추론하거나 답한 사례

### 6-1. 화면 시험 파일의 경로를 잘못 적음 (2026-10-18, Task 6)
- 무엇: 클로드가 구현 계획서(IMPL-PLAN.md Task 6)에 `AppTest.from_file("streamlit_app.py")`라고 적음. 클로드는 이 경로가 작업 폴더 기준이라고 여겼으나, Streamlit의 AppTest는 **시험 파일이 있는 폴더(tests/) 기준**으로 경로를 찾음
- 결과: 앱을 만들기 전의 "실패하는 시험" 단계에서 시험이 실패했는데, 실패 이유가 "앱이 없음"이 아니라 "경로가 틀림"이었음. 앱을 만든 뒤에도 4개 시험이 모두 `AppTest script not found at ...\tests\streamlit_app.py`로 실패
- 알아챈 방법: 앱을 만든 뒤에도 같은 오류가 나서 오류 메시지의 경로(`tests\streamlit_app.py`)를 읽고 알아챔. `../streamlit_app.py`로 고친 뒤 앱 파일을 잠시 치워 시험이 올바른 이유로 실패하는지 다시 확인함
- 근거: 커밋 fdafb3b (tests/test_app.py)

## 7. 앱의 문제점이나 개선 필요 사항
