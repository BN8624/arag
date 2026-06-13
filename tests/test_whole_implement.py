"""통짜(한 콜에 전체 파일) 구현 테스트 (콜0 mock)."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design

from orchestrator import Orchestrator
from prompts import extract_files
from test_orchestrator_mock import MockLLM


def _whole_response(files: dict[str, str]) -> str:
    """파일들을 통짜 응답 형식(파일별 펜스 블록 + 첫줄 # 경로)으로 합친다."""
    blocks = []
    for path, body in files.items():
        blocks.append(f"```python\n# {path}\n{body}```")
    return "\n\n".join(blocks)


def test_extract_files_parses_multiple_blocks():
    text = _whole_response({"core.py": GOOD_CORE, "main.py": GOOD_MAIN})
    out = extract_files(text)
    assert set(out) == {"core.py", "main.py"}
    assert out["core.py"].startswith("# core.py")
    assert "def add_item" in out["core.py"]
    assert "def main" in out["main.py"]


def test_extract_files_ignores_blocks_without_path_comment():
    text = "```python\nprint('no path comment')\n```"
    assert extract_files(text) == {}


def test_whole_implement_writes_all_files(tmp_path):
    whole = _whole_response({"core.py": GOOD_CORE, "main.py": GOOD_MAIN})
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[whole],  # 단 한 번의 generator 콜로 전체
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True, whole=True)
    assert orch.run("tiny todo cli") is True
    ws = tmp_path / "run" / "workspace"
    assert (ws / "core.py").exists() and (ws / "main.py").exists()
    # generator 큐가 1콜로 소진됐다 = 파일별 분해 안 함
    assert llm.queues["generator"] == []


def test_whole_implement_retries_then_aborts_on_missing(tmp_path):
    # core.py만 주고 main.py 누락 → 2회 시도 후 abort
    half = _whole_response({"core.py": GOOD_CORE})
    llm = MockLLM(
        critic=[json.dumps(make_design())],
        generator=[half, half],  # 두 번 다 누락
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True, whole=True)
    assert orch.run("tiny todo cli") is False
