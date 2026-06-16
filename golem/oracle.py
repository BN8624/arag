# golem A-오라클 — JS 레퍼런스 구현을 돌려 골든(정답 트레이스)을 생성한다 (game/ 의존 없음)
"""A 방식: 정답 레퍼런스(누가 짰든 — Claude가 새로 짠 JS든, 검증된 솔루션이든)를 node로
돌려 시나리오별 winner/turns/final_hp를 뽑아 골든으로 삼는다. game/(파이썬 레퍼런스)에
묶이지 않으므로 처음 보는 게임 아이디어에도 오라클을 만들 수 있다.

grade._run_scenario를 그대로 재사용 — 채점 러너와 골든 러너가 같은 파서를 쓰니 정합성 보장.
final_hp 순서/키는 출력 그대로(엔티티 등록순)."""

import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import grade as grader  # noqa: E402  (_run_scenario 재사용)


def _write_files(d, files):
    for name, body in files.items():
        p = Path(d) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def golden_from_reference(ref_files, scenario_ids):
    """레퍼런스 JS impl({file: content})을 임시 디렉토리에 풀어 시나리오별 골든을 생성.
    반환: {str(n): {key: value_str}} — 출력 그대로의 평면 dict(채점기와 같은 파서). node 에러 시 RuntimeError."""
    out = {}
    with tempfile.TemporaryDirectory(prefix="golem_oracle_") as d:
        _write_files(d, ref_files)
        for n in scenario_ids:
            got, err = grader._run_scenario(d, str(n))
            if err:
                raise RuntimeError(f"reference failed on scenario {n}: {err}")
            out[str(n)] = got
    return out


if __name__ == "__main__":
    # 점검: <ref_dir> <N..> 의 골든을 찍는다 (키 안 씀)
    import json
    if len(sys.argv) < 2:
        print("usage: python golem/oracle.py <ref_dir> [scenario_ids...]")
        raise SystemExit(2)
    ref_dir = Path(sys.argv[1])
    ids = sys.argv[2:] or ["1", "2", "3", "4"]
    files = {p.name: p.read_text(encoding="utf-8") for p in ref_dir.glob("*.js")}
    print(json.dumps(golden_from_reference(files, ids), ensure_ascii=False, indent=2))
