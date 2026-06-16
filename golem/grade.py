# golem 채점기 — 후보 JS(node main.js --scenario N) 출력을 골든과 정확일치 비교, 첫 불일치 보고
"""사용: python golem/grade.py <candidate_dir> [card_slug]
게임-중립 채점: 출력의 `key: value` 줄들을 평면 dict로 모아 카드 골든 dict와 정확일치.
(전투의 winner/turns/엔티티hp도, 2048의 score/cell도 같은 평면 dict로 표현된다.)
값은 원문 문자열로 비교 — 타입 안 따지고 정확일치. first_divergence(첫 불일치)는
드라이버가 자가수정 프롬프트에 넣는다."""

import json
import subprocess
import sys
from pathlib import Path

TIMEOUT = 30


def _run_scenario(cdir, n):
    """node main.js --scenario N 실행 → {key: value_str} 평면 dict. (dict, None) 또는 (None, err).
    모델 생성 코드라 Node 권한모델로 격리(파일쓰기·자식프로세스·워커·네이티브 차단) + stdin 차단."""
    try:
        r = subprocess.run(
            ["node", "--permission", "--allow-fs-read=*", "main.js", "--scenario", str(n)],
            cwd=cdir, capture_output=True, text=True, timeout=TIMEOUT,
            stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"scenario {n}: TIMEOUT ({TIMEOUT}s)"
    except FileNotFoundError as e:
        return None, f"scenario {n}: run error {e}"
    if r.returncode != 0:
        return None, f"scenario {n}: node exit {r.returncode}: {r.stderr.strip()[-300:]}"
    out = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out, None


def _diff_msg(sc, golden, got):
    for k, v in golden.items():
        if got.get(k) != v:
            return f"scenario {sc}: {k} = {got.get(k)!r} != {v!r}"
    extra = [k for k in got if k not in golden]
    if extra:
        return f"scenario {sc}: unexpected output keys {extra}"
    return f"scenario {sc}: mismatch got={got} exp={golden}"


def grade(cdir, scenarios):
    """scenarios = {N: {"input":..., "golden": {key: value_str}}}. 출력 dict가 골든 dict와 정확일치해야 PASS."""
    results = {}
    first = None
    allpass = True
    for sc in sorted(scenarios, key=int):
        golden = scenarios[sc]["golden"]
        got, err = _run_scenario(cdir, sc)
        if err:
            allpass = False
            results[sc] = {"pass": False, "error": err}
            if first is None:
                first = err
            continue
        ok = (got == golden)
        results[sc] = {"pass": ok, "got": got}
        if not ok:
            allpass = False
            if first is None:
                first = _diff_msg(sc, golden, got)
    return {"pass": allpass, "scenarios": results, "first_divergence": first}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python golem/grade.py <candidate_dir> [card_slug=tempo-combat]")
        raise SystemExit(2)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import game_bank
    slug = sys.argv[2] if len(sys.argv) > 2 else "tempo-combat"
    c = game_bank.get_card(slug)
    if c is None:
        print(f"카드 '{slug}' 없음 — bank_init.py로 적재 필요")
        raise SystemExit(2)
    res = grade(sys.argv[1], c["scenarios"])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    raise SystemExit(0 if res["pass"] else 1)
