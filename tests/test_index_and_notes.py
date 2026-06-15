"""0층(runs/index.json) + 2층(비평노트) 테스트."""

import json

from conftest import GOOD_CORE, GOOD_MAIN, make_design

import critique_notes
import run_index
from orchestrator import Orchestrator
from test_orchestrator_mock import MockLLM, fenced


# ------------------------------------------------------------ run_index

def test_record_run_appends(tmp_path):
    run_dir = tmp_path / "runs" / "20260611-1"
    run_dir.mkdir(parents=True)
    assert run_index.record_run(run_dir, {"run": "20260611-1", "ok": True})
    assert run_index.record_run(run_dir, {"run": "20260611-2", "ok": False})
    entries = run_index.load_index(tmp_path / "runs")
    assert len(entries) == 2
    assert entries[0]["run"] == "20260611-1"
    assert entries[1]["ok"] is False


def test_load_index_missing_or_corrupt(tmp_path):
    assert run_index.load_index(tmp_path) == []
    (tmp_path / "index.json").write_text("{broken", encoding="utf-8")
    assert run_index.load_index(tmp_path) == []


def test_orchestrator_writes_index_entry(tmp_path):
    llm = MockLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "runs" / "run1", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    entries = run_index.load_index(tmp_path / "runs")
    assert len(entries) == 1
    e = entries[0]
    assert e["run"] == "run1"
    assert e["ok"] is True
    assert e["idea"] == "tiny todo cli"
    assert e["calls"] == llm.call_count
    assert e["fixes"] == {"static": 0, "exec": 0}


def test_index_entry_on_abort(tmp_path):
    broken_main = GOOD_MAIN.replace("from core import add_item",
                                    "from core import add_item_nope")
    llm = MockLLM(
        critic=[json.dumps(make_design())],
        generator=[fenced(GOOD_CORE), fenced(broken_main), fenced(broken_main)],
    )
    orch = Orchestrator(llm, tmp_path / "runs" / "run1", skip_exec=True)
    assert orch.run("tiny todo cli") is False
    entries = run_index.load_index(tmp_path / "runs")
    assert len(entries) == 1
    assert entries[0]["ok"] is False
    assert entries[0]["fixes"]["static"] >= 1


# ------------------------------------------------------------ critique_notes

def test_record_and_load_notes(tmp_path):
    path = tmp_path / "notes.json"
    n = critique_notes.record_notes(
        "todo cli", [{"path": "main.py", "issues": ["usage message unclear",
                                                    "no error handling"]}],
        path=path)
    assert n == 2
    notes = critique_notes.load_notes(path)
    assert len(notes) == 2
    assert notes[0]["issue"] == "usage message unclear"
    assert notes[0]["idea"] == "todo cli"


def test_record_notes_never_raises(tmp_path):
    # 쓰기 불가능한 경로여도 예외 없이 0 반환
    bad = tmp_path / "no_dir" / "notes.json"
    assert critique_notes.record_notes("x", [{"path": "a.py",
                                              "issues": ["y"]}], path=bad) == 0


def test_find_relevant_by_overlap(tmp_path):
    path = tmp_path / "notes.json"
    critique_notes.record_notes(
        "csv markdown table cli",
        [{"path": "main.py", "issues": ["escape pipe characters in csv cells"]}],
        path=path)
    critique_notes.record_notes(
        "image resizer tool",
        [{"path": "resize.py", "issues": ["handle missing exif data"]}],
        path=path)
    found = critique_notes.find_relevant("csv to markdown converter", path=path)
    assert any("pipe" in n for n in found)
    assert not any("exif" in n for n in found)


def test_find_relevant_frequency_floor(tmp_path):
    path = tmp_path / "notes.json"
    # 주제가 전혀 안 겹쳐도 FREQ_FLOOR회 반복되면 보편 규칙으로 주입
    for _ in range(critique_notes.FREQ_FLOOR):
        critique_notes.record_notes(
            "zzz unrelated topic",
            [{"path": "a.py", "issues": ["validate inputs before processing"]}],
            path=path)
    found = critique_notes.find_relevant("qqq totally different", path=path)
    assert found == ["validate inputs before processing"]


def test_find_relevant_card_scope(tmp_path):
    """card 지정 시 같은 카드 노트만 본다 (타 카드·무카드 트집 누수 차단)."""
    path = tmp_path / "notes.json"
    critique_notes.record_notes(
        "battle sim", [{"path": "engine.py", "issues": ["fix turn order"]}],
        path=path, card="T-12")
    critique_notes.record_notes(
        "battle sim", [{"path": "x.py", "issues": ["unrelated card trifle"]}],
        path=path, card="T-99")
    critique_notes.record_notes(
        "battle sim", [{"path": "y.py", "issues": ["legacy no-card note"]}],
        path=path, card=None)
    found = critique_notes.find_relevant("battle sim", path=path, card="T-12")
    assert found == ["fix turn order"]                 # 같은 카드만
    # card 미지정이면 기존 동작(카드 무시, 키워드)
    allf = critique_notes.find_relevant("battle sim", path=path)
    assert "unrelated card trifle" in allf and "legacy no-card note" in allf


def test_record_impl_note_from_failure(tmp_path):
    """실행 실패 증거 -> 31B 진단 -> 카드-스코프 구현노트 저장, 구현 주입에 잡힘."""
    path = tmp_path / "notes.json"

    class FakeLLM:
        def generate(self, role, prompt):
            return ('{"keywords": ["turn", "counter"], "note": "increment the '
                    'turn counter after end-of-turn effects, not before"}')

    e = critique_notes.record_impl_note(
        FakeLLM(), "battle sim", "golden mismatch: turns expected 23 got 25",
        card="T-12", path=path)
    assert e and e["card"] == "T-12" and "counter" in e["issue"]
    found = critique_notes.find_relevant("battle sim turn counter",
                                         path=path, card="T-12")
    assert any("counter" in n for n in found)


def test_record_impl_note_rejects_dummy(tmp_path):
    """빈/더미 진단은 저장 안 함 (풀 오염 방지)."""
    path = tmp_path / "notes.json"

    class DummyLLM:
        def generate(self, role, prompt):
            return '{"keywords": [], "note": "n/a"}'

    assert critique_notes.record_impl_note(
        DummyLLM(), "x", "evidence", card="T-1", path=path) is None
    assert not path.exists() or critique_notes.load_notes(path) == []


def test_frequent_candidates(tmp_path):
    path = tmp_path / "notes.json"
    for _ in range(5):
        critique_notes.record_notes(
            "any", [{"path": "a.py", "issues": ["Use CliRunner for click"]}],
            path=path)
    critique_notes.record_notes(
        "any", [{"path": "b.py", "issues": ["rare nitpick"]}], path=path)
    cands = critique_notes.frequent_candidates(min_count=5, path=path)
    assert cands == [(5, "Use CliRunner for click")]


def test_surviving_critique_recorded(tmp_path):
    """비평 수정이 게이트를 통과하면 비평노트에 수확된다."""
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
    orch = Orchestrator(llm, tmp_path / "runs" / "r", critique_rounds=2,
                        skip_exec=True)
    assert orch.run("tiny todo cli") is True
    notes = critique_notes.load_notes()  # conftest가 tmp로 격리해둠
    assert len(notes) == 1
    assert notes[0]["issue"] == "usage message unclear"


def test_rolled_back_critique_not_recorded(tmp_path):
    """게이트를 깬 비평 수정은 트집 -> 기록하지 않는다."""
    broken_revision = GOOD_MAIN.replace("from core import add_item",
                                        "from core import add_item_gone")
    critique = json.dumps({
        "verdict": "revise",
        "files": [{"path": "main.py", "issues": ["rename things"]}],
    })
    llm = MockLLM(
        critic=[json.dumps(make_design()), critique],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN),
                   fenced(broken_revision), fenced(broken_revision)],
    )
    orch = Orchestrator(llm, tmp_path / "runs" / "r", critique_rounds=2,
                        skip_exec=True)
    assert orch.run("tiny todo cli") is True
    assert critique_notes.load_notes() == []


def test_notes_injected_into_implement_prompt(tmp_path):
    """저장된 비평노트가 구현 프롬프트에 들어간다."""
    critique_notes.record_notes(
        "todo cli list",
        [{"path": "main.py", "issues": ["print confirmation for every action"]}])

    class SpyLLM(MockLLM):
        def __init__(self, critic, generator):
            super().__init__(critic, generator)
            self.prompts: list[str] = []

        def generate(self, role, prompt, temperature=None):
            if role == "generator":
                self.prompts.append(prompt)
            return super().generate(role, prompt, temperature)

    llm = SpyLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "runs" / "r", skip_exec=True)
    assert orch.run("tiny todo cli") is True
    assert all("print confirmation for every action" in p for p in llm.prompts)


def test_cold_mode_disables_note_injection(tmp_path, monkeypatch):
    """cold mode: 오답노트/비평노트가 프롬프트에 주입되지 않는다 (수확은 별개)."""
    import phase_design

    # 매칭될 비평노트를 미리 저장 (conftest가 tmp로 격리) - warm이면 주입될 것
    critique_notes.record_notes(
        "todo cli list",
        [{"path": "main.py", "issues": ["print confirmation for every action"]}])

    # cold는 lessons 검색에 닿기 전에 단락돼야 한다 - 호출되면 잡는다
    called = {"lessons": False}
    real = phase_design.find_relevant_entries

    def spy_lessons(*a, **k):
        called["lessons"] = True
        return real(*a, **k)

    monkeypatch.setattr(phase_design, "find_relevant_entries", spy_lessons)

    class SpyLLM(MockLLM):
        def __init__(self, critic, generator):
            super().__init__(critic, generator)
            self.gen_prompts: list[str] = []

        def generate(self, role, prompt, temperature=None):
            if role == "generator":
                self.gen_prompts.append(prompt)
            return super().generate(role, prompt, temperature)

    llm = SpyLLM(
        critic=[json.dumps(make_design()), "LGTM"],
        generator=[fenced(GOOD_CORE), fenced(GOOD_MAIN)],
    )
    orch = Orchestrator(llm, tmp_path / "runs" / "r", skip_exec=True,
                        notes_enabled=False)
    assert orch.mode == "cold"
    assert orch.run("tiny todo cli") is True

    # 비평노트가 구현 프롬프트에 안 들어갔다
    assert all("print confirmation for every action" not in p
               for p in llm.gen_prompts)
    # 오답노트 검색 자체가 호출되지 않았다 (cold 단락)
    assert called["lessons"] is False
    # 두 store 모두 notes-disabled 로깅
    events = [json.loads(line) for line in
              (tmp_path / "runs" / "r" / "events.jsonl").read_text(
                  encoding="utf-8").splitlines()]
    disabled = {e["store"] for e in events if e["event"] == "notes-disabled"}
    assert disabled == {"lessons", "critique_notes"}
