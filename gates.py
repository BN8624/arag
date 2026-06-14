"""정적 게이트 (콜 0). 모델을 부르기 전에 공짜로 거를 수 있는 걸 다 거른다.

검사 항목:
  - syntax-error        : ast 파싱 실패
  - non-stdlib-import   : 표준 라이브러리 밖 import (1차 규격 위반)
  - broken-import       : 로컬 모듈에서 없는 이름을 import
  - missing-attr        : import한 로컬 모듈에 없는 속성 접근
  - unused-import       : 대놓고 안 쓰는 import
  - undefined-name      : 파일 어디에도 바인딩이 없는 이름 사용 (보수적)
  - stub                : 몸통이 비어 있는 함수 (pass / ... / NotImplementedError)
  - no-entrypoint       : 진입점 파일에 if __name__ == "__main__" 없음
  - fake-multifile      : 로컬 import 간선이 하나도 없음 (멀티파일 위장)
  - orphan-file         : 아무도 import하지 않는 비진입점 파일
  - missing-dependency  : 설계가 기대한 import 간선이 실제 코드에 없음
  - contract-missing    : 설계 계약의 함수/클래스가 파일에 없음
  - contract-mismatch   : 계약과 인자 개수 불일치
  - monkeypatch         : import한 모듈의 속성에 대입 (json.load = ... 류 변조)

원칙: 명백한 것만 잡는다. 동적 기법(eval/exec/globals/star import)이 보이면
해당 파일의 미정의 이름 검사는 건너뛴다 (과하게 빡빡하면 멀쩡한 코드를 막는다).
"""

import ast
import builtins
import re
import sys
from pathlib import Path

_BUILTIN_NAMES = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__",
}
_DYNAMIC_MARKERS = {"eval", "exec", "globals", "locals", "__import__", "vars"}

# 외부 패키지 화이트리스트: import 이름 -> pip 패키지 이름.
# Docker 게이트가 설치 단계에서만 네트워크를 열고 이 목록만 설치한다.
ALLOWED_PACKAGES = {
    "requests": "requests",
    "rich": "rich",
    "click": "click",
    "tabulate": "tabulate",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "tqdm": "tqdm",
    "colorama": "colorama",
    "jinja2": "Jinja2",
    "markdown": "Markdown",
    "openpyxl": "openpyxl",   # 엑셀 입출력 (sop류 앱)
    "PIL": "Pillow",          # 이미지 처리
    "pypdf": "pypdf",         # PDF 읽기 (순수 파이썬 - 시스템 의존성 없음)
}


def issue(file: str, line: int, kind: str, message: str) -> dict:
    return {"file": file, "line": line, "kind": kind, "message": message}


def format_issues(issues: list[dict]) -> str:
    """자가수정 프롬프트에 그대로 넣을 수 있는 형태로 정리."""
    lines = []
    for it in sorted(issues, key=lambda x: (x["file"], x["line"])):
        lines.append(f"{it['file']}:{it['line']} [{it['kind']}] {it['message']}")
    return "\n".join(lines)


def run_static_gate(workdir: Path, design: dict | None = None) -> list[dict]:
    """디렉토리의 .py 파일 전체를 검사. 문제 목록을 반환 (빈 목록 = 통과)."""
    workdir = Path(workdir)
    sources: dict[str, str] = {}
    trees: dict[str, ast.AST] = {}
    issues: list[dict] = []

    for path in sorted(workdir.glob("*.py")):
        name = path.name
        if name.startswith("test_"):
            continue  # 31B가 출제한 테스트는 정적 게이트 대상이 아님 - pytest가 검증
        text = path.read_text(encoding="utf-8-sig")
        sources[name] = text
        try:
            trees[name] = ast.parse(text, filename=name)
        except SyntaxError as err:
            issues.append(issue(name, err.lineno or 0, "syntax-error", err.msg or "syntax error"))

    local_modules = {Path(n).stem: n for n in sources}
    defined: dict[str, set[str]] = {
        name: _toplevel_names(tree) for name, tree in trees.items()
    }

    # 파일별 검사 + 실제 import 그래프 수집
    actual_edges: dict[str, set[str]] = {name: set() for name in sources}
    for name, tree in trees.items():
        issues.extend(_check_file(name, tree, local_modules, defined, actual_edges[name]))

    if trees:
        issues.extend(_check_graph(sources, trees, actual_edges, design))
    if design is not None:
        issues.extend(_check_contracts(trees, design))
        entry = design.get("entrypoint")
        if entry in trees and not _has_ifmain(trees[entry]):
            issues.append(issue(entry, 1, "no-entrypoint",
                                'entrypoint file has no `if __name__ == "__main__":` block'))
    return issues


# ---------------------------------------------------------------- per-file

def _check_file(name, tree, local_modules, defined, edges) -> list[dict]:
    issues: list[dict] = []
    import_aliases: dict[str, tuple[str, int]] = {}  # 바인딩명 -> (로컬모듈 파일, 줄)
    module_bindings: set[str] = set()  # 비-로컬 모듈 바인딩명 (몽키패치 탐지용)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                bound = alias.asname or top
                if top in local_modules:
                    edges.add(local_modules[top])
                    import_aliases[bound] = (local_modules[top], node.lineno)
                    module_bindings.add(bound)  # 로컬 모듈 패치도 금지
                else:
                    module_bindings.add(bound)
                    if not _is_stdlib(top) and top not in ALLOWED_PACKAGES:
                        issues.append(issue(name, node.lineno, "non-stdlib-import",
                                            f"'{alias.name}' is not in the standard library "
                                            "or the allowed package whitelist"))
                if not _name_used(tree, bound, node):
                    issues.append(issue(name, node.lineno, "unused-import",
                                        f"'{bound}' is imported but never used"))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # 상대 import는 평탄 구조에선 안 나옴; 나오면 실행 게이트가 잡음
            mod = (node.module or "").split(".")[0]
            if mod in local_modules:
                target = local_modules[mod]
                edges.add(target)
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if target in defined and alias.name not in defined[target]:
                        issues.append(issue(
                            name, node.lineno, "broken-import",
                            f"cannot import '{alias.name}' from {target} - "
                            f"it is not defined there"))
                    bound = alias.asname or alias.name
                    if not _name_used(tree, bound, node):
                        issues.append(issue(name, node.lineno, "unused-import",
                                            f"'{bound}' is imported but never used"))
            elif (mod and mod != "__future__" and not _is_stdlib(mod)
                    and mod not in ALLOWED_PACKAGES):
                issues.append(issue(name, node.lineno, "non-stdlib-import",
                                    f"'{node.module}' is not in the standard library "
                                    "or the allowed package whitelist"))

    # import한 로컬 모듈의 없는 속성 접근 (utils.foo 인데 utils에 foo 없음)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in import_aliases):
            target, _ = import_aliases[node.value.id]
            if target in defined and node.attr not in defined[target]:
                issues.append(issue(name, node.lineno, "missing-attr",
                                    f"{target} has no attribute '{node.attr}'"))

    issues.extend(_check_stubs(name, tree))
    issues.extend(_check_undefined(name, tree))
    issues.extend(_check_secrets(name, tree))
    issues.extend(_check_monkeypatch(name, tree, module_bindings))
    return issues


# sys.stdout = ... 류 인코딩 래핑은 정당한 패턴이라 sys만 예외
_MONKEYPATCH_EXEMPT = {"sys"}


def _check_monkeypatch(name, tree, module_bindings) -> list[dict]:
    """import한 모듈의 속성에 대입 탐지 (json.load = patched 류).

    깨진 테스트에 코드를 끼워맞추려는 퇴행 패턴 — 실제 런에서 관측됨.
    """
    issues = []
    targets_of = (ast.Assign, ast.AugAssign, ast.AnnAssign)
    for node in ast.walk(tree):
        if not isinstance(node, targets_of):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id in module_bindings
                    and t.value.id not in _MONKEYPATCH_EXEMPT):
                issues.append(issue(
                    name, node.lineno, "monkeypatch",
                    f"assigning to {t.value.id}.{t.attr} - monkeypatching an "
                    "imported module is forbidden (fix the code, not the library)"))
    return issues


_SECRET_NAME = re.compile(r"(?i)(api_?key|secret|token|password|passwd)")


def _check_secrets(name, tree) -> list[dict]:
    """키처럼 보이는 이름에 리터럴 문자열 대입 탐지. 키는 CLI 인자/환경변수로만."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
            value = node.value
        else:
            continue
        if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
            continue
        if len(value.value) < 12:
            continue  # 빈 문자열·짧은 기본값은 통과 (명백한 것만 잡는다)
        for t in targets:
            if _SECRET_NAME.search(t.id):
                issues.append(issue(
                    name, node.lineno, "hardcoded-secret",
                    f"'{t.id}' is assigned a literal string - secrets must "
                    "come from CLI arguments or environment variables"))
    return issues


def _check_stubs(name, tree) -> list[dict]:
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("__") and node.name.endswith("__"):
            continue
        if node.decorator_list:
            continue  # @abstractmethod 등 의도적 빈 몸통일 수 있음 - 명백한 것만 잡는다
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]  # docstring 제외
        if not body or all(_is_stub_stmt(s) for s in body):
            issues.append(issue(name, node.lineno, "stub",
                                f"function '{node.name}' has an empty body "
                                "(pass / ... / NotImplementedError only)"))
    return issues


def _is_stub_stmt(stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
            and stmt.value.value is Ellipsis:
        return True
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True
    return False


def _check_undefined(name, tree) -> list[dict]:
    """파일 어디에도 바인딩이 없는 이름 사용을 잡는다 (흐름·스코프 무시 = 보수적)."""
    all_loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if all_loads & _DYNAMIC_MARKERS:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return []

    bound = set(_BUILTIN_NAMES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    bound.add(alias.asname or alias.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.add(node.rest)

    issues = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) \
                and node.id not in bound and node.id not in seen:
            seen.add(node.id)
            issues.append(issue(name, node.lineno, "undefined-name",
                                f"name '{node.id}' is used but never defined or imported"))
    return issues


# ---------------------------------------------------------------- graph

def _check_graph(sources, trees, actual_edges, design) -> list[dict]:
    issues = []
    if not any(actual_edges.values()):
        issues.append(issue("(project)", 0, "fake-multifile",
                            "no file imports any other local file - "
                            "files must actually use each other"))
        return issues

    entry = design.get("entrypoint") if design else None
    imported_somewhere = set()
    for edges in actual_edges.values():
        imported_somewhere |= edges
    for name in sources:
        if name != entry and name not in imported_somewhere:
            if entry is None and _has_ifmain(trees.get(name)):
                continue  # 설계 없이 돌릴 때는 ifmain 있는 파일을 진입점으로 간주
            issues.append(issue(name, 1, "orphan-file",
                                f"{name} is never imported by any other file"))

    if design:
        expected = design.get("dependencies", {})
        for src, targets in expected.items():
            for t in targets:
                if src in actual_edges and t not in actual_edges[src]:
                    issues.append(issue(src, 1, "missing-dependency",
                                        f"design says {src} imports {t}, but it does not"))
    return issues


def _check_contracts(trees, design) -> list[dict]:
    """설계 계약 대비 시그니처 정합성 (ast 대조 - 모델 콜 불필요)."""
    issues = []
    for f in design.get("files", []):
        name = f.get("path")
        if name not in trees:
            if name and name.endswith(".py"):
                issues.append(issue(name, 0, "contract-missing",
                                    f"designed file {name} was not created"))
            continue
        tree = trees[name]
        top_funcs = {n.name: n for n in tree.body
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        top_names = _toplevel_names(tree)
        # 클래스 메서드도 정의로 인정 — 설계가 메서드 인터페이스(__init__/run 등)를
        # 선언했을 때 클래스 안에 있어도 false contract-missing이 안 나게 (하네스 버그 수정)
        class_methods = {m.name for node in tree.body
                         if isinstance(node, ast.ClassDef)
                         for m in node.body
                         if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        defined = top_names | class_methods
        for iface in f.get("interfaces", []):
            iname = iface.get("name")
            if not iname:
                continue
            if iname not in defined:
                issues.append(issue(name, 1, "contract-missing",
                                    f"design contract requires '{iname}' "
                                    f"to be defined in {name}"))
                continue
            expected_args = _contract_arg_count(iface.get("signature", ""))
            if expected_args is not None and iname in top_funcs:
                got = _func_arg_count(top_funcs[iname])
                if got is not None and got != expected_args:
                    issues.append(issue(
                        name, top_funcs[iname].lineno, "contract-mismatch",
                        f"'{iname}' takes {got} args but the design contract "
                        f"specifies {expected_args}"))
    return issues


def external_imports(workdir: Path) -> set[str]:
    """워크스페이스가 쓰는 화이트리스트 외부 패키지의 pip 이름 집합."""
    pkgs: set[str] = set()
    for path in sorted(Path(workdir).glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in ALLOWED_PACKAGES:
                        pkgs.add(ALLOWED_PACKAGES[top])
            elif isinstance(node, ast.ImportFrom) and not node.level:
                top = (node.module or "").split(".")[0]
                if top in ALLOWED_PACKAGES:
                    pkgs.add(ALLOWED_PACKAGES[top])
    return pkgs


# ---------------------------------------------------------------- helpers

def _toplevel_names(tree) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
    return names


def _is_stdlib(module: str) -> bool:
    return module in sys.stdlib_module_names


def _name_used(tree, bound: str, import_node) -> bool:
    """import 문 밖에서 그 이름이 실제로 쓰이나."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == bound:
            return True
    return False


def _has_ifmain(tree) -> bool:
    if tree is None:
        return False
    for node in tree.body:
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name) and test.left.id == "__name__"
                    and any(isinstance(c, ast.Constant) and c.value == "__main__"
                            for c in test.comparators)):
                return True
    return False


def _contract_arg_count(signature: str) -> int | None:
    """계약 시그니처 문자열에서 인자 개수를 뽑는다. 모호하면 None (검사 생략)."""
    sig = signature.strip()
    if not sig.startswith("def "):
        return None
    header = sig.split("->")[0].rstrip().rstrip(":")
    try:
        parsed = ast.parse(header + ": pass").body[0]
    except SyntaxError:
        return None
    if not isinstance(parsed, ast.FunctionDef):
        return None
    return _func_arg_count(parsed)


def _func_arg_count(node) -> int | None:
    """*args/**kwargs가 있으면 유연하다고 보고 None (검사 생략)."""
    a = node.args
    if a.vararg or a.kwarg:
        return None
    count = len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
    # self/cls는 계약 표기에 따라 다를 수 있으니 메서드 보정은 안 함 (top-level 함수만 대조)
    return count
