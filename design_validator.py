"""설계 JSON에 대한 의미 검증 (정적·콜0).

검사: 멀티파일(.py 2개 이상) / 평탄한 구조 / 순환참조 없음 / 진입점 존재 /
성공 신호 형식 / 파일 수 상한. 실패 목록을 돌려주면 오케스트레이터가
31B 재설계 프롬프트에 그대로 넣는다.
"""

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

    command = design["success_signal"]["command"].strip()
    if not command.startswith("python "):
        errors.append(f"success_signal.command must start with 'python ': {command!r}")
    else:
        first_arg = command.split()[1] if len(command.split()) > 1 else ""
        if first_arg != entry:
            errors.append(
                f"success_signal.command must run the entrypoint {entry!r} "
                f"(got {first_arg!r})"
            )
    return errors


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
