# 생성: 2026-10-18 18:00 KST
import json
import time

import httpx
import pytest

import ai_assign
from ai_assign import AIEmpty, AIFormatError, AIHttpError, AITimeout, call_model, parse_pairs, run
from rules import Student, validate_assignment


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
    assert all(m.endswith(":free") and not m.startswith("openrouter/") for m in ai_assign.MODELS)
