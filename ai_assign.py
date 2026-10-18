# 생성: 2026-10-18 18:00 KST
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
# 오픈라우터 무료 텍스트 생성 모델 3개를 직접 정해 차례로 부른다(무료 모델 자동 라우터는 쓰지 않음)
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
