"""설계 JSON에 대한 의미 검증 (정적·콜0).

검사: 멀티파일(.py 2개 이상) / 평탄한 구조 / 순환참조 없음 / 진입점 존재 /
성공 신호 형식 / 파일 수 상한. 실패 목록을 돌려주면 오케스트레이터가
31B 재설계 프롬프트에 그대로 넣는다.
"""

import re

from schema import MAX_FILES


def validate_design(design: dict) -> list[str]:
    errors = []
    files = design["files"]
    paths = [f["path"] for f in files]

    py_paths = [p for p in paths if p.endswith(".py")]
    if len(py_paths) < 2:
        errors.append(
            f"need at least 2 .py files (got {len(py_paths)}) - "
            "single-file output is a failure by definition"
        )
    if len(paths) > MAX_FILES:
        errors.append(f"too many files: {len(paths)} (max {MAX_FILES})")
    if len(set(paths)) != len(paths):
        errors.append("duplicate file paths in 'files'")
    for p in paths:
        if "/" in p or "\\" in p:
            errors.append(f"nested path not allowed (flat layout only): {p}")
        elif not p.endswith(".py"):
            errors.append(f"only .py files allowed in v1: {p}")

    entry = design["entrypoint"]
    if entry not in paths:
        errors.append(f"entrypoint {entry!r} is not in 'files'")

    deps = design["dependencies"]
    path_set = set(paths)
    for src, targets in deps.items():
        if src not in path_set:
            errors.append(f"dependencies key {src!r} is not in 'files'")
        for t in targets:
            if t not in path_set:
                errors.append(f"dependency target {t!r} (of {src}) is not in 'files'")
            if t == src:
                errors.append(f"self-dependency: {src}")

    cycle = _find_cycle(deps)
    if cycle:
        errors.append("circular dependency: " + " -> ".join(cycle))

    # 멀티파일 위장 방지: 의존 간선이 하나도 없는 설계는 거른다
    if not any(targets for targets in deps.values()):
        errors.append("no import edges in 'dependencies' - files must actually use each other")

    # 요구사항 커버리지: 아이디어 분해 강제 + 모든 요구사항이 수용기준에 매핑돼야 함
    reqs = design.get("requirements")
    n_criteria = len(design["acceptance_criteria"])
    if not reqs:
        errors.append(
            "'requirements' is missing or empty - decompose the IDEA into "
            "atomic requirements, each with 'covered_by' criterion indices")
    else:
        for i, r in enumerate(reqs):
            if not isinstance(r, dict):
                continue  # 형태 문제는 schema가 이미 잡았다
            text = str(r.get("text", "")).strip()
            cov = r.get("covered_by")
            if not isinstance(cov, list) or not cov:
                errors.append(
                    f"requirements[{i}] ({text[:50]!r}) has empty 'covered_by' - "
                    "every requirement must map to at least one acceptance criterion")
            elif any(not isinstance(x, int) or x < 0 or x >= n_criteria
                     for x in cov):
                errors.append(
                    f"requirements[{i}].covered_by contains an invalid index - "
                    f"acceptance_criteria has {n_criteria} items (valid: 0..{n_criteria - 1})")

    # 모의 응답 파일: 평탄 구조, .py 금지, 코드 파일과 이름 충돌 금지
    for i, fx in enumerate(design.get("mock_fixtures") or []):
        p = str(fx.get("path", "")) if isinstance(fx, dict) else ""
        if "/" in p or "\\" in p:
            errors.append(f"mock_fixtures[{i}].path must be flat (no directories): {p}")
        elif p.endswith(".py"):
            errors.append(f"mock_fixtures[{i}].path must not be a .py file: {p}")
        elif p in set(paths):
            errors.append(f"mock_fixtures[{i}].path collides with a code file: {p}")

    for i, chk in enumerate(design.get("criteria_checks") or []):
        cmd = str(chk.get("command", "")).strip()
        bad = _non_python_parts(cmd)
        if bad:
            errors.append(
                f"criteria_checks[{i}].command: every '&&' step must start "
                f"with 'python ': {bad[0]!r}")
        inline = _inline_code_parts(cmd)
        if inline:
            errors.append(
                f"criteria_checks[{i}].command: 'python -c' inline code is "
                f"forbidden (multifile 계약 우회·오염 벡터): {inline[0]!r}")

    command = design["success_signal"]["command"].strip()
    bad = _non_python_parts(command)
    inline = _inline_code_parts(command)
    if bad:
        errors.append(
            f"success_signal.command: every '&&' step must start with "
            f"'python ': {bad[0]!r}")
    elif inline:
        errors.append(
            f"success_signal.command: 'python -c' inline code is forbidden "
            f"(멀티파일 계약 우회): {inline[0]!r}")
    else:
        last = command.split("&&")[-1].strip()
        first_arg = last.split()[1] if len(last.split()) > 1 else ""
        if first_arg != entry:
            errors.append(
                f"success_signal.command's final step must run the entrypoint "
                f"{entry!r} (got {first_arg!r})"
            )
    return errors


def _non_python_parts(command: str) -> list[str]:
    """'&&'로 쪼갠 각 단계 중 'python '으로 시작하지 않는 것들."""
    parts = [p.strip() for p in command.split("&&")]
    return [p for p in parts if not p.startswith("python ")]


def _inline_code_parts(command: str) -> list[str]:
    """'python -c ...' 인라인 코드 실행 단계들. 'python '은 통과시키되 -c는 막는다
    (리뷰 #6 — 멀티파일 계약을 우회하는 임의 코드 실행·워크스페이스 오염 벡터)."""
    parts = [p.strip() for p in command.split("&&")]
    return [p for p in parts if re.match(r"python\b.*\s-c(\s|$)", p)]


def _find_cycle(deps: dict) -> list[str] | None:
    """DFS로 순환 탐지. 발견 시 경로 반환, 없으면 None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in deps}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for nxt in deps.get(node, []):
            if color.get(nxt, WHITE) == GRAY:
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt, WHITE) == WHITE and nxt in deps:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in deps:
        if color[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None


def implementation_order(design: dict) -> list[str]:
    """의존되는 파일 먼저 (위상 정렬). 26B 구현 순서를 정한다."""
    deps = design["dependencies"]
    paths = [f["path"] for f in design["files"]]
    order: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for dep in deps.get(node, []):
            visit(dep)
        order.append(node)

    for p in paths:
        visit(p)
    return order
