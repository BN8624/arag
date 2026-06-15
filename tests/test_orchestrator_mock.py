"""모의 LLM으로 루프 배관을 통째로 검증 (API 키·Docker 불필요)."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design

from orchestrator import Orchestrator


class MockLLM:
    """역할별 응답 큐. 순서대로 꺼내 쓴다."""

    def __init__(self, critic: list[str], generator: list[str]):
        self.queues = {"critic": list(critic), "generator": list(generator)}
        self.call_count = 0
        self.max_calls = None

    def generate(self, role, prompt, temperature=None):
        self.call_count += 1
        assert self.queues[role], f"unexpected extra {role} call:\n{prompt[:200]}"
        return self.queues[role].pop(0)


def fenced(code: str) -> str:
    return f"```python\n{code}```"


def test_happy_path_lgtm(tmp_path):
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    workspace = tmp_path / "run" / "workspace"
    assert (workspace / "main.py").exists()
    assert (workspace / "core.py").exists()
    assert (tmp_path / "run" / "REPORT.md").exists()
    assert llm.queues == {"critic": [], "generator": []}  # 큐 전부 소진


def test_static_failure_then_self_fix(tmp_path):
    broken_main = GOOD_MAIN.replace("from core import add_item",
                                    "from core import add_item_nope")
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(broken_main), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    text = (tmp_path / "run" / "workspace" / "main.py").read_text(encoding="utf-8")
    assert "add_item_nope" not in text


def test_no_progress_aborts(tmp_path):
    broken_main = GOOD_MAIN.replace("from core import add_item",
                                    "from core import add_item_nope")
    # 같은 깨진 파일만 반복 반환 -> 진전 없음 감지로 K를 안 채우고 중단해야 함
    llm = MockLLM(
        critic=[json.dumps(make_design())],
        generator=[fenced(GOOD_CORE), fenced(broken_main), fenced(broken_main)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is False
    report = (tmp_path / "run" / "REPORT.md").read_text(encoding="utf-8")
    assert "ABORTED" in report


def test_critique_revision_applied(tmp_path):
    revised_main = GOOD_MAIN.replace("usage: python main.py add <text>",
                                     "usage: main.py add <text> (see README)")
    critique = json.dumps({
        "verdict": "revise",
        "files": [{"path": "main.py", "issues": ["usage message unclear"]}],
    })
    llm = MockLLM(
        critic=[json.dumps(make_design()), critique, "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN), fenced(revised_main)],
    )
    orch = Orchestrator(llm, tmp_path / "run", critique_rounds=2, skip_exec=True)
    assert orch.run("tiny todo cli") is True
    text = (tmp_path / "run" / "workspace" / "main.py").read_text(encoding="utf-8")
    assert "see README" in text


def test_breaking_revision_rolls_back(tmp_path):
    broken_revision = GOOD_MAIN.replace("from core import add_item",
                                        "from core import add_item_gone")
    critique = json.dumps({
        "verdict": "revise",
        "files": [{"path": "main.py", "issues": ["rename things"]}],
    })
    llm = MockLLM(
        critic=[json.dumps(make_design()), critique],
        # 수정본도, 그 뒤의 자가수정 시도도 똑같이 깨진 파일 -> 진전 없음 -> rollback
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN),
                   fenced(broken_revision), fenced(broken_revision)],
    )
    orch = Orchestrator(llm, tmp_path / "run", critique_rounds=2, skip_exec=True)
    assert orch.run("tiny todo cli") is True  # rollback 후 마지막 통과본으로 완료
    text = (tmp_path / "run" / "workspace" / "main.py").read_text(encoding="utf-8")
    assert "add_item_gone" not in text  # 깨진 수정본이 남아 있으면 안 됨


def test_design_retry_on_invalid(tmp_path):
    bad_design = dict(make_design())
    bad_design["dependencies"] = {"main.py": [], "core.py": []}  # 간선 없음 -> 거부
    llm = MockLLM(
        critic=[json.dumps(bad_design), json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "run", skip_exec=True)
    assert orch.run("tiny todo cli") is True


def test_infra_failure_skips_lesson(tmp_path, monkeypatch):
    """인프라 장애(API 5xx 소진)는 오답노트를 안 남긴다 — 설계 풀 오염 방지."""
    import orchestrator as om
    called = []
    monkeypatch.setattr(om, "record_lesson", lambda *a, **k: called.append(1))
    orch = Orchestrator(MockLLM(critic=[], generator=[]),
                        tmp_path / "run", skip_exec=True)
    orch.infra_error = True
    orch._record_failure("idea", "API call failed after 4 retries: 500 INTERNAL")
    assert called == []  # 인프라 실패 → record_lesson 호출 안 됨


def test_model_failure_records_lesson(tmp_path, monkeypatch):
    """모델·설계 실패는 오답노트를 남긴다(인프라 아님)."""
    import orchestrator as om
    called = []
    monkeypatch.setattr(om, "record_lesson",
                        lambda *a, **k: called.append(1) or
                        {"keywords": ["k"], "lesson": "do X"})
    orch = Orchestrator(MockLLM(critic=[], generator=[]),
                        tmp_path / "run", skip_exec=True)
    orch.infra_error = False
    orch.design = make_design()
    orch._record_failure("idea", "gates not passed after self-fix budget")
    assert called == [1]  # 능력 실패 → record_lesson 호출됨
