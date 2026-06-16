# trace-diff 오라클 테스트 (콜0): 파싱·최초발산·규칙범주·게이트배선·골든값 비노출 (결정27)

import types

import phase_gates
import trace_diff


GOLDEN = """\
turn=1 actor=hero1 action=shock_bolt | hero1=85 hero2=140 enemy1=160 enemy2=40
turn=2 actor=enemy2 action=ignite | hero1=68 hero2=140 enemy1=160 enemy2=40
turn=3 actor=hero1 action=venom | hero1=65 hero2=140 enemy1=160 enemy2=19
turn=4 actor=enemy2 action=frost | hero1=49 hero2=140 enemy1=160 enemy2=0
turn=5 actor=hero2 action=charge | hero1=49 hero2=140 enemy1=160 enemy2=0
"""


def _swap(line_idx: int, old: str, new: str) -> str:
    lines = GOLDEN.splitlines()
    lines[line_idx] = lines[line_idx].replace(old, new)
    return "\n".join(lines)


# ---- parse_trace ----

def test_parse_basic():
    rows = trace_diff.parse_trace(GOLDEN)
    assert len(rows) == 5
    assert rows[0] == {"turn": 1, "actor": "hero1", "action": "shock_bolt",
                       "state": {"hero1": "85", "hero2": "140",
                                 "enemy1": "160", "enemy2": "40"}}


def test_parse_skips_garbage():
    assert trace_diff.parse_trace("쓰레기\n\nWinner: hero\n") == []


# ---- first_divergence ----

def test_identical_no_divergence():
    assert trace_diff.first_divergence(GOLDEN, GOLDEN) is None


def test_actor_divergence_is_scheduler():
    d = trace_diff.first_divergence(_swap(2, "actor=hero1", "actor=hero2"), GOLDEN)
    assert d["turn"] == 3 and d["kind"] == "actor"
    assert "스케줄러" in d["category"]


def test_action_divergence_is_combo():
    d = trace_diff.first_divergence(_swap(2, "action=venom", "action=combo_strike"),
                                    GOLDEN)
    assert d["turn"] == 3 and d["kind"] == "action"
    assert "콤보" in d["category"] or "로테이션" in d["category"]


def test_freeze_divergence_is_freeze():
    d = trace_diff.first_divergence(_swap(3, "action=frost", "action=frozen"), GOLDEN)
    assert d["kind"] == "freeze" and "빙결" in d["category"]


def test_state_divergence_is_damage_or_status():
    d = trace_diff.first_divergence(_swap(4, "hero1=49", "hero1=40"), GOLDEN)
    assert d["turn"] == 5 and d["kind"] == "state"
    assert "피해식" in d["category"] or "상태틱" in d["category"]


def test_missing_model_trace():
    d = trace_diff.first_divergence("", GOLDEN)
    assert d["kind"] == "missing"


def test_length_divergence_when_prefix_matches():
    short = "\n".join(GOLDEN.splitlines()[:3])
    d = trace_diff.first_divergence(short, GOLDEN)
    assert d["kind"] == "length"


def test_empty_golden_returns_none():
    assert trace_diff.first_divergence(GOLDEN, "") is None


# ---- 골든 정답값 비노출(공정성, 결정27) ----

def test_hint_never_leaks_golden_values():
    # 모델이 turn3 actor를 hero2로 틀림. 골든 정답(hero1)·골든 hp가 힌트에 없어야 한다.
    d = trace_diff.first_divergence(_swap(2, "actor=hero1", "actor=hero2"), GOLDEN)
    hint = trace_diff.hint_text(d)
    assert "hero2" in hint              # 모델 자기 값은 보여줌(허용)
    assert "actor=hero1" not in hint    # 골든 정답 actor는 비노출
    assert "65" not in hint             # 골든 hp 수치 비노출


# ---- 게이트 배선: _add_trace_hint ----

def _fake_self(tmp_path, golden_dir):
    ns = types.SimpleNamespace()
    ns.golden_from = golden_dir
    ns.workspace = tmp_path
    ns.deps_dir = tmp_path / "deps"
    ns._packages = []
    ns.design = {"entrypoint": "main.py"}
    ns.log = lambda *a, **k: None
    ns._say = lambda *a, **k: None
    return ns


def _golden_dir(tmp_path):
    gdir = tmp_path / "frozen" / "golden_traces"
    gdir.mkdir(parents=True)
    (gdir / "scen1.txt").write_text(GOLDEN, encoding="utf-8")
    return tmp_path / "frozen"


def test_add_trace_hint_no_golden_dir_noop(tmp_path):
    ns = _fake_self(tmp_path, tmp_path / "nonexistent")
    issues = [{"file": "(run)", "message": "golden output mismatch"}]
    assert phase_gates.GatesPhase._add_trace_hint(ns, issues) == issues


def test_add_trace_hint_skips_non_golden_failure(tmp_path, monkeypatch):
    ns = _fake_self(tmp_path, _golden_dir(tmp_path))
    issues = [{"file": "(run)", "message": "success-signal command timed out"}]
    # 크래시/타임아웃엔 트레이스 안 돌려야 함(호출되면 실패)
    monkeypatch.setattr(phase_gates, "run_turn_trace",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("불러선 안 됨")))
    assert phase_gates.GatesPhase._add_trace_hint(ns, issues) == issues


def test_add_trace_hint_appends_on_divergence(tmp_path, monkeypatch):
    ns = _fake_self(tmp_path, _golden_dir(tmp_path))
    issues = [{"file": "(run)", "message": "golden output mismatch — fix these"}]
    monkeypatch.setattr(phase_gates, "run_turn_trace",
                        lambda *a, **k: _swap(2, "actor=hero1", "actor=hero2"))
    out = phase_gates.GatesPhase._add_trace_hint(ns, issues)
    assert len(out) == len(issues) + 1
    assert out[-1]["kind"] == "trace-hint"
    assert "[TRACE]" in out[-1]["message"]


def test_add_trace_hint_noop_when_trace_matches(tmp_path, monkeypatch):
    ns = _fake_self(tmp_path, _golden_dir(tmp_path))
    issues = [{"file": "(run)", "message": "golden output mismatch"}]
    monkeypatch.setattr(phase_gates, "run_turn_trace", lambda *a, **k: GOLDEN)
    # 트레이스가 골든과 일치(다른 시나리오 실패) → 힌트 없이 원본 유지
    assert phase_gates.GatesPhase._add_trace_hint(ns, issues) == issues
