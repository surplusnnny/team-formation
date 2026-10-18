# 생성: 2026-10-18 18:00 KST
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
