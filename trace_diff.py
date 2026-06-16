# 모델 턴트레이스 vs 골든을 비교해 최초 발산 턴·규칙범주를 뽑는 콜0 진단기 (결정27)
"""trace-diff 오라클의 핵심: all-or-nothing 최종상태 불일치를 '몇 턴째 어느 규칙이
갈렸나'로 국소화한다. 게이트가 아니라 자가수정 *피드백*용 — 통과/실패 판정은 안 바꾼다.

트레이스 한 줄 포맷(game/combat._turn_line과 동일, 모델 main.py --trace도 이걸 따름):
  turn=N actor=ID action=ACTION | id=hp id=hp ...

힌트 강도(결정27) = 위치+범주: 발산 턴 + 모델이 한 행동 + 어느 규칙 범주가 의심되나까지.
**골든의 정답 수치(올바른 actor/hp/turn)는 노출하지 않는다** — 답 떠먹이기 방지, 공정성 유지.
"""

import re

_LINE = re.compile(
    r"turn=(\d+)\s+actor=(\S+)\s+action=(\S+)\s*\|\s*(.*)$")


def parse_trace(text: str) -> list[dict]:
    """트레이스 텍스트 → [{turn, actor, action, state:{id:hp}}]. 파싱 안 되는 줄은 건너뛴다."""
    rows: list[dict] = []
    for line in (text or "").splitlines():
        m = _LINE.match(line.strip())
        if not m:
            continue
        turn, actor, action, state_str = m.groups()
        state: dict[str, str] = {}
        for tok in state_str.split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                state[k] = v
        rows.append({"turn": int(turn), "actor": actor,
                     "action": action, "state": state})
    return rows


def _category(g: dict, m: dict) -> tuple[str, str]:
    """골든 턴 g vs 모델 턴 m이 어떻게 다른지 → (발산종류, 규칙범주 한국어)."""
    if g["actor"] != m["actor"]:
        return ("actor", "템포 턴 스케줄러 — 우선순위(spd→hp→등록순서) 또는 게이지 이월(-=100, 0리셋 아님)")
    if g["action"] != m["action"]:
        gf, mf = g["action"] == "frozen", m["action"] == "frozen"
        if gf != mf:
            return ("freeze", "빙결 처리 — 다음 행동 1회 스킵 + gauge=0 + last_skill=None, 화상 매트릭스")
        return ("action", "스킬 로테이션/콤보 사슬 — last_skill 기억·끊김(피격/빙결시 None), 로테이션 인덱스")
    if g["state"] != m["state"]:
        return ("state", "피해식 또는 상태틱 — dmg=max(1,atk+base-def)·감전×1.25·화상(턴시작5%)·중독(턴끝8*stacks)·HP클램프(0에서멈춤)")
    return ("none", "")


def first_divergence(model_text: str, golden_text: str) -> dict | None:
    """모델 vs 골든 트레이스의 최초 발산. 동일하면 None.

    반환 {turn, kind, category, model_actor, model_action, note}.
    kind ∈ actor/action/freeze/state/length. 모델 자기 값만 담고 골든 정답값은 안 담는다.
    """
    g = parse_trace(golden_text)
    m = parse_trace(model_text)
    if not g:                       # 골든이 비면 비교 불가(상위에서 폴백)
        return None
    if not m:                       # 모델 트레이스를 못 뽑음 → 트레이스 자체가 빠진 신호
        return {"turn": 0, "kind": "missing", "category":
                "main.py --trace가 턴별 트레이스를 출력하지 않음(포맷 'turn=N actor=ID action=X | id=hp ...')",
                "model_actor": "", "model_action": "", "note":
                "최종상태는 틀렸는데 트레이스도 비었다. --trace 출력을 먼저 구현하라."}
    n = min(len(g), len(m))
    for i in range(n):
        kind, cat = _category(g[i], m[i])
        if kind != "none":
            return {"turn": g[i]["turn"], "kind": kind, "category": cat,
                    "model_actor": m[i]["actor"], "model_action": m[i]["action"],
                    "note": ""}
    # 앞부분은 전부 같은데 길이가 다르다 = 한쪽이 더 일찍/늦게 끝남
    if len(g) != len(m):
        endkind = "your sim ended EARLIER" if len(m) < len(g) else "your sim ran LONGER"
        return {"turn": (m[-1]["turn"] if m else 0), "kind": "length",
                "category": "전투 종료/턴 카운팅 — turns=행동 차례 횟수(빙결스킵도 +1), "
                            "한쪽 팀 전멸 시 종료·사망판정 타이밍",
                "model_actor": "", "model_action": "",
                "note": f"앞 {n}턴은 골든과 일치하나 {endkind} (golden {len(g)}턴 vs yours {len(m)}턴)."}
    return None


def hint_text(div: dict) -> str:
    """first_divergence 결과 → 자가수정 프롬프트에 넣을 힌트(위치+범주, 골든값 비노출)."""
    if not div:
        return ""
    if div["kind"] == "missing":
        return ("[TRACE] " + div["category"] + " " + div["note"])
    if div["kind"] == "length":
        return (f"[TRACE] 시뮬레이션 궤적이 골든과 길이가 다르다. {div['note']} "
                f"의심 규칙: {div['category']}.")
    where = f"턴 {div['turn']}"
    did = ""
    if div["model_actor"]:
        did = f" (네 트레이스에선 actor={div['model_actor']}, action={div['model_action']})"
    return (f"[TRACE] 시뮬레이션이 골든과 처음 갈라지는 지점: {where}{did}. "
            f"이 턴 결과가 골든과 다르다 — 의심 규칙: {div['category']}. "
            f"골든의 정답 값은 주지 않는다. 이 규칙을 스펙대로 정밀히 재점검하라.")
