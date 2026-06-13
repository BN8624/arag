"""부분 합격 출하 + 31B 계약 중재 + 사용자 시점 총평 테스트 (콜 0, Docker 불필요).

실행 게이트 함수들을 orchestrator 네임스페이스에서 모킹해 게이트 분기만 검증한다.
"""

import json

import pytest
from conftest import GOOD_CORE, GOOD_MAIN, make_design
from test_orchestrator_mock import MockLLM, fenced

import orchestrator as om
import reviewer
import run_index

TEST_CODE = "def test_ok():\n    assert True\n"

# 단언 실패 없는 pytest 실패 로그 (중재 비대상 -> 곧장 부분 합격 경로)
LOG_PLAIN = """$ python -m pytest -q test_acceptance.py
(exit 1)
F........
some failure detail without the magic word
1 failed, 8 passed in 0.5s"""

# 단언 실패 로그 (중재 대상)
LOG_ASSERT = """$ python -m pytest -q test_acceptance.py
(exit 1)
test_acceptance.py:10: in test_total_format
E   AssertionError: assert '1' == '1.0'
1 failed, 8 passed in 0.5s"""

PYTEST_ISSUE = {"file": "(run)", "line": 0, "kind": "exec-fail",
                "message": "pytest failed (exit 1)"}


def _design_with_checks() -> dict:
    design = make_design()
    design["criteria_checks"] = [
        {"criterion": "c1", "command": "python main.py add x",
         "expect_substring": "x"},
        {"criterion": "c2", "command": "python main.py add y",
         "expect_substring": "y"},
    ]
    return design


def _mock_gates(monkeypatch, pytest_fn, criteria_results):
    # 게이트 함수들은 phase_gates 모듈 전역에서 호출된다 (orchestrator 분해)
    import phase_gates as pg
    monkeypatch.setattr(pg, "run_static_gate", lambda ws, design: [])
    monkeypatch.setattr(pg, "external_imports", lambda ws: set())
    monkeypatch.setattr(pg, "install_packages",
                        lambda deps, pkgs: (True, ""))
    monkeypatch.setattr(pg, "run_exec_gate",
                        lambda ws, sig, deps_dir=None: ([], "signal ok"))
    monkeypatch.setattr(pg, "run_pytest", pytest_fn)
    monkeypatch.setattr(pg, "run_criteria_checks",
                        lambda ws, checks, deps_dir=None: criteria_results)


def _events(run_dir):
    lines = (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ------------------------------------------------------------ 부분 합격 출하

def test_partial_pass_ships_with_open_criteria(tmp_path, monkeypatch):
    """성공 신호 OK + pytest 8/9 -> ABORT 대신 부분 합격으로 출하."""
    _mock_gates(monkeypatch,
                lambda ws, deps_dir=None: ([dict(PYTEST_ISSUE)], LOG_PLAIN),
                [{"criterion": "c1", "passed": True, "detail": "",
                  "output_tail": ""},
                 {"criterion": "c2", "passed": False, "detail": "missing",
                  "output_tail": ""}])
    llm = MockLLM(
        critic=[json.dumps(_design_with_checks()), fenced(TEST_CODE), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN), fenced(GOOD_MAIN),
                   "# readme"],
    )
    run_dir = tmp_path / "runs" / "run1"
    orch = om.Orchestrator(llm, run_dir)
    assert orch.run("tiny todo cli") is True
    assert orch.partial_pass is True

    kinds = [e["event"] for e in _events(run_dir)]
    assert "partial-pass" in kinds
    assert "aborted" not in kinds

    entry = run_index.load_index(tmp_path / "runs")[0]
    assert entry["ok"] is True
    assert entry["status"].startswith("OK (partial")
    # 떨어진 기준이 index에 남아 배치의 자동 improve 표적이 된다
    assert entry["failed_criteria"] == ["c2"]


def test_partial_pass_requires_threshold(tmp_path, monkeypatch):
    """통과율이 낮으면 (5/9 = 56%) 부분 합격 없이 그대로 ABORT."""
    log = LOG_PLAIN.replace("1 failed, 8 passed", "4 failed, 5 passed")
    _mock_gates(monkeypatch,
                lambda ws, deps_dir=None: ([dict(PYTEST_ISSUE)], log), [])
    llm = MockLLM(
        critic=[json.dumps(_design_with_checks()), fenced(TEST_CODE),
                json.dumps({"keywords": ["x"], "lesson": "y"})],  # 오답노트 1콜
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN), fenced(GOOD_MAIN)],
    )
    run_dir = tmp_path / "runs" / "run1"
    orch = om.Orchestrator(llm, run_dir)
    assert orch.run("tiny todo cli") is False
    assert "aborted" in [e["event"] for e in _events(run_dir)]


# ------------------------------------------------------------ 31B 계약 중재

def test_arbitration_blame_test_repairs_tests(tmp_path, monkeypatch):
    """단언 실패 반복 -> 31B 중재 'test 과잉' -> 시험지 수리 -> 그래도 안 되면 부분 합격."""
    _mock_gates(monkeypatch,
                lambda ws, deps_dir=None: ([dict(PYTEST_ISSUE)], LOG_ASSERT),
                [{"criterion": "c1", "passed": True, "detail": "",
                  "output_tail": ""}])
    arb = json.dumps({"blame": "test",
                      "instruction": "compare numbers with float(), not strings"})
    llm = MockLLM(
        critic=[json.dumps(_design_with_checks()), fenced(TEST_CODE),
                arb, fenced(TEST_CODE)],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN),
                   fenced(GOOD_MAIN), fenced(GOOD_MAIN), "# readme"],
    )
    run_dir = tmp_path / "runs" / "run1"
    orch = om.Orchestrator(llm, run_dir)
    assert orch.run("tiny todo cli") is True  # 부분 합격으로 생환

    events = _events(run_dir)
    arb_events = [e for e in events if e["event"] == "arbitration"]
    assert arb_events and arb_events[0]["blame"] == "test"
    kinds = [e["event"] for e in events]
    assert "tests-regen-written" in kinds
    assert "partial-pass" in kinds


def test_arbitration_blame_code_targeted_fix(tmp_path, monkeypatch):
    """중재 'code 위반' -> 지시 포함 표적 수정 -> 게이트 완전 통과."""
    calls = {"n": 0}

    def flaky_pytest(ws, deps_dir=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            return [dict(PYTEST_ISSUE)], LOG_ASSERT
        return [], "9 passed in 0.4s"

    _mock_gates(monkeypatch, flaky_pytest,
                [{"criterion": "c1", "passed": True, "detail": "",
                  "output_tail": ""}])
    arb = json.dumps({"blame": "code",
                      "instruction": "undefined categories must default to Hold"})
    llm = MockLLM(
        critic=[json.dumps(_design_with_checks()), fenced(TEST_CODE), arb],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN),
                   fenced(GOOD_MAIN), fenced(GOOD_MAIN), "# readme"],
    )
    run_dir = tmp_path / "runs" / "run1"
    orch = om.Orchestrator(llm, run_dir)
    assert orch.run("tiny todo cli") is True
    assert orch.partial_pass is False  # 완전 통과

    events = _events(run_dir)
    arb_events = [e for e in events if e["event"] == "arbitration"]
    assert arb_events and arb_events[0]["blame"] == "code"
    entry = run_index.load_index(tmp_path / "runs")[0]
    assert entry["status"] == "OK"
    assert entry["fixes"]["exec"] == 2  # 일반 수리 1 + 중재 수리 1


# ------------------------------------------------------------ 통과율 파서

def test_pytest_pass_rate(tmp_path):
    orch = om.Orchestrator(MockLLM([], []), tmp_path / "r", skip_exec=True)
    orch.last_exec_log = "no summary here"
    assert orch._pytest_pass_rate() is None
    orch.last_exec_log = "2 failed, 6 passed in 1s"
    assert orch._pytest_pass_rate() == pytest.approx(0.75)
    orch.last_exec_log = "9 passed in 0.2s"
    assert orch._pytest_pass_rate() == 1.0
    orch.last_exec_log = "3 failed in 0.2s"
    assert orch._pytest_pass_rate() == 0.0


# ------------------------------------------------------------ 출제 규칙 강화

def test_tests_prompt_forbids_exact_output_match():
    from prompts import arbitrate_prompt, tests_prompt
    p = tests_prompt(make_design())
    assert "ENTIRE stdout" in p
    assert "pytest.approx" in p
    d = make_design()
    a = arbitrate_prompt(d, TEST_CODE, LOG_ASSERT)
    assert '"blame"' in a and "over-specifies" in a


# ------------------------------------------------------------ 효율 개선 (6차 후반)

def test_implement_prompt_slices_context_to_deps():
    """구현 프롬프트는 직접 의존 파일만 컨텍스트로 받는다 (thinking 비용 절감)."""
    from prompts import implement_prompt
    design = make_design()
    design["files"].append({"path": "extra.py", "role": "unrelated",
                            "interfaces": []})
    design["dependencies"]["extra.py"] = []
    written = {"core.py": "CORE_CODE_MARKER", "extra.py": "EXTRA_CODE_MARKER"}
    p = implement_prompt(design, "main.py", written)  # main은 core만 import
    assert "CORE_CODE_MARKER" in p
    assert "EXTRA_CODE_MARKER" not in p


def test_context_files_target_plus_neighbors(tmp_path):
    orch = om.Orchestrator(MockLLM([], []), tmp_path / "r", skip_exec=True)
    design = make_design()
    design["files"].append({"path": "extra.py", "role": "unrelated",
                            "interfaces": []})
    design["dependencies"]["extra.py"] = []
    orch.design = design
    for name in ("main.py", "core.py", "extra.py"):
        (orch.workspace / name).write_text(f"# {name}", encoding="utf-8")
    ctx = orch._context_files("core.py")  # core를 부르는 main 포함, extra 제외
    assert set(ctx) == {"core.py", "main.py"}
    # 지도에 없는 표적은 안전하게 전체 반환
    assert set(orch._context_files("(run)")) == {"main.py", "core.py", "extra.py"}


def test_resume_retry_dir(tmp_path):
    run = tmp_path / "r1"
    run.mkdir()
    assert om.resume_retry_dir(run) is None  # 설계 전에 죽음 -> 처음부터
    (run / "design.json").write_text("{}", encoding="utf-8")
    assert om.resume_retry_dir(run) == run   # 설계는 멀쩡 -> 재사용


def test_infra_error_flagged(tmp_path):
    class DownLLM:
        call_count = 0
        max_calls = None

        def generate(self, role, prompt, temperature=None):
            raise RuntimeError("API call failed after 4 retries: 503")

    orch = om.Orchestrator(DownLLM(), tmp_path / "r", skip_exec=True)
    assert orch.run("idea") is False
    assert orch.infra_error is True  # main()이 이걸 보고 재도전을 생략


def test_improve_fallback_keeps_old_design(tmp_path):
    """31B가 설계 재출력에 실패해도 changes만 멀쩡하면 기존 설계로 진행."""
    from test_improve import _make_prev_run
    prev = _make_prev_run(tmp_path)
    plan_without_design = json.dumps({
        "changes": [{"path": "core.py", "instructions": ["add a docstring"]}]})
    llm = MockLLM(critic=[plan_without_design, "LGTM"],
                  generator=[fenced(GOOD_CORE)])
    run_dir = tmp_path / "runs" / "imp1"
    orch = om.Orchestrator(llm, run_dir, skip_exec=True,
                           improve_from=prev, feedback="문서화 개선")
    assert orch.run("todo cli") is True
    kinds = [e["event"] for e in _events(run_dir)]
    assert "improve-design-fallback" in kinds
    assert "aborted" not in kinds


# ------------------------------------------------------------ 녹음·재생 (replay)

def test_llm_recording(tmp_path):
    from llm import LLMClient
    client = LLMClient.__new__(LLMClient)  # __init__ 우회 (SDK·키 불필요)
    client.record_path = tmp_path / "llm_calls.jsonl"
    client._record("critic", "gemma-4-31b-it", "P" * 1000, "the response")
    client._record("generator", "gemma-4-26b-a4b-it", "q", "second")
    lines = client.record_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["role"] == "critic"
    assert first["prompt_chars"] == 1000      # 다이어트 효과 측정용
    assert len(first["prompt_head"]) == 300   # prompt는 머리만
    assert first["response"] == "the response"  # response는 전문 (재생용)


def test_llm_recording_tokens_and_finish_reason(tmp_path):
    """콜당 토큰·finish_reason이 녹음된다 (출력한도·분산성 잘림 관측용)."""
    from llm import LLMClient
    client = LLMClient.__new__(LLMClient)
    client.record_path = tmp_path / "llm_calls.jsonl"
    client._record("generator", "gemma-4-26b-a4b-it", "p", "code",
                   tokens={"input": 50, "output": 8000, "thinking": 0},
                   finish_reason="FinishReason.MAX_TOKENS")
    rec = json.loads(client.record_path.read_text(encoding="utf-8").splitlines()[0])
    assert rec["tokens"] == {"input": 50, "output": 8000, "thinking": 0}
    assert rec["finish_reason"] == "FinishReason.MAX_TOKENS"


def test_llm_recording_disabled_by_default(tmp_path):
    from llm import LLMClient
    client = LLMClient.__new__(LLMClient)
    client.record_path = None
    client._record("critic", "m", "p", "r")  # 경로 없으면 조용히 무시


def test_replay_llm_replays_in_order(tmp_path):
    from llm import ReplayExhausted, ReplayLLM
    record = tmp_path / "llm_calls.jsonl"
    entries = [
        {"role": "critic", "response": "design json"},
        {"role": "generator", "response": "file one"},
        {"role": "generator", "response": "file two"},
        {"role": "critic", "response": "LGTM"},
    ]
    record.write_text("\n".join(json.dumps(e) for e in entries),
                      encoding="utf-8")
    llm = ReplayLLM(record)
    assert llm.generate("critic", "any prompt") == "design json"
    assert llm.generate("generator", "x") == "file one"
    assert llm.generate("generator", "x") == "file two"
    assert llm.generate("critic", "x") == "LGTM"
    assert llm.call_count == 4
    with pytest.raises(ReplayExhausted):
        llm.generate("critic", "one too many")


# ------------------------------------------------------------ 사용자 시점 총평

class FakeCritic:
    def __init__(self, replies):
        self.replies = list(replies)

    def generate(self, role, prompt, temperature=None):
        assert role == "critic"
        self.prompt = prompt
        return self.replies.pop(0)


def _mk_run_dir(tmp_path):
    run_dir = tmp_path / "runs" / "r1"
    (run_dir / "workspace").mkdir(parents=True)
    (run_dir / "workspace" / "README.md").write_text("# tool\nusage...",
                                                     encoding="utf-8")
    (run_dir / "design.json").write_text(
        json.dumps({"acceptance_criteria": ["adds an item"]}),
        encoding="utf-8")
    return run_dir


def test_user_review_suggest(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    llm = FakeCritic([json.dumps({"verdict": "SUGGEST",
                                  "feedback": "합계 요약 출력을 추가하라"})])
    fb = reviewer.user_review(llm, run_dir, "todo cli")
    assert fb == "합계 요약 출력을 추가하라"
    marker = json.loads(reviewer.review_marker(run_dir).read_text(encoding="utf-8"))
    assert marker["verdict"] == "SUGGEST"
    # 블랙박스 원칙: 프롬프트에 README는 있어도 소스 코드는 없다
    assert "# tool" in llm.prompt
    assert "NOT seen the source code" in llm.prompt


def test_user_review_nochange(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    llm = FakeCritic([json.dumps({"verdict": "NOCHANGE", "feedback": ""})])
    assert reviewer.user_review(llm, run_dir, "todo cli") is None
    assert reviewer.review_marker(run_dir).exists()  # NOCHANGE도 마커 기록


def test_user_review_unparseable_treated_as_nochange(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    llm = FakeCritic(["garbage", "more garbage"])
    assert reviewer.user_review(llm, run_dir, "todo cli") is None
    marker = json.loads(reviewer.review_marker(run_dir).read_text(encoding="utf-8"))
    assert marker["verdict"] == "NOCHANGE"
