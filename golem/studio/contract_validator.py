# Golem Studio v0.1 계약 검증기 — manifest와 실제 CommonJS 코드의 파일/export/import 기계적 일치를 콜0으로 검증한다
"""PENDING-003 bridge I/O 계약을 따른다.
입력: workspace_path, manifest_path
출력: {"ok": bool, "checks": [{"name","ok"}...], "errors": [...], "warnings": [...]}
checks 이름 4종 고정: manifest_schema, file_exists, import_export, static_gate.
실제 API 호출 없음(네트워크/genai import 없음). static_gate는 콜0 정적 검사만 재사용한다.
"""

import json
import posixpath
import re
import sys
from pathlib import Path

# 상위 golem 패키지(static_gate)를 재사용
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import static_gate  # noqa: E402

_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
_EXPORTS_PROP = re.compile(r"""(?:^|[^.\w])exports\.([A-Za-z_$][\w$]*)\s*=""")
_MODULE_OBJ = re.compile(r"""module\.exports\s*=\s*\{([^}]*)\}""")
_MODULE_BARE = re.compile(r"""module\.exports\s*=\s*(?!\{)""")
_IDENT = re.compile(r"""([A-Za-z_$][\w$]*)""")


def _read(ws, rel):
    p = ws / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


def _extract_exports(text):
    """반환: (named_exports:set, bare_default:bool). bare = module.exports = <object아닌것>."""
    named = set(_EXPORTS_PROP.findall(text))
    m = _MODULE_OBJ.search(text)
    if m:
        for part in m.group(1).split(","):
            key = part.split(":")[0].strip()
            id_m = _IDENT.match(key)
            if id_m:
                named.add(id_m.group(1))
    bare = bool(_MODULE_BARE.search(text)) and not m
    return named, bare


def _resolve(target, from_path):
    """require 대상을 워크스페이스 상대 .js 경로로 해소(파일 디렉터리 기준)."""
    base = posixpath.dirname(from_path)
    r = posixpath.normpath(posixpath.join(base, target))
    return r if r.endswith(".js") else r + ".js"


def _check_manifest_schema(manifest):
    errors = []
    for k in ("schema_version", "module_format", "entry", "files"):
        if k not in manifest:
            errors.append(f"필수 필드 없음: {k}")
    if manifest.get("schema_version") not in (None, "0.1"):
        errors.append(f"schema_version은 0.1이어야 함: {manifest.get('schema_version')}")
    if manifest.get("module_format") not in (None, "commonjs"):
        errors.append("module_format은 commonjs여야 함")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) < 2:
        errors.append("files는 2개 이상 배열이어야 함(멀티파일 계약)")
        return (False, errors)
    paths = set()
    for f in files:
        for k in ("path", "exports", "imports"):
            if k not in f:
                errors.append(f"파일 항목 필드 없음: {k} in {f.get('path', '?')}")
        p = f.get("path")
        if p in paths:
            errors.append(f"path 중복: {p}")
        paths.add(p)
    if manifest.get("entry") not in paths:
        errors.append(f"entry가 files에 없음: {manifest.get('entry')}")
    return (len(errors) == 0, errors)


def _check_file_exists(manifest, ws):
    errors = []
    declared = {f["path"] for f in manifest.get("files", []) if "path" in f}
    for path in sorted(declared):
        if not (ws / path).is_file():
            errors.append(f"매니페스트 파일 없음: {path}")
    actual = {p.relative_to(ws).as_posix() for p in ws.rglob("*.js")}
    for p in sorted(actual - declared):
        errors.append(f"매니페스트에 없는 파일(위장 의심): {p}")
    return (len(errors) == 0, errors)


def _check_import_export(manifest, ws, strict=True):
    """strict=True(v0.1): 코드가 매니페스트 export/import와 정확히 일치해야 한다.
    strict=False(Build): 선언된 export는 있어야 하나 추가 export 허용, import는 매니페스트 내부면
    추가 엣지 허용·선언 엣지 누락 허용, 매니페스트 밖 파일 import만 금지(자유 구현 수용)."""
    errors = []
    entry = manifest.get("entry")
    manifest_paths = {f.get("path") for f in manifest.get("files", [])}
    graph = {}
    for f in manifest.get("files", []):
        path = f.get("path")
        text = _read(ws, path)
        declared_exp = set(f.get("exports", []))
        declared_imp = set(f.get("imports", []))
        graph[path] = set(declared_imp)
        if text is None:
            errors.append(f"{path}: 파일을 읽을 수 없어 export/import 대조 불가")
            continue
        named, bare = _extract_exports(text)
        is_entry_script = (path == entry and not declared_exp)
        if bare and not is_entry_script:
            errors.append(f"{path}: bare default export(module.exports=...) 금지(PENDING-002)")
        if not bare:
            missing = declared_exp - named
            if missing:
                errors.append(f"{path}: 매니페스트 export가 코드에 없음 {sorted(missing)}")
            if strict:
                extra = named - declared_exp
                if extra:
                    errors.append(f"{path}: 코드 export가 매니페스트에 없음 {sorted(extra)}")
        actual_imp = {_resolve(t, path) for t in _REQUIRE.findall(text) if t.startswith(".")}
        if strict:
            miss_i = declared_imp - actual_imp
            extra_i = actual_imp - declared_imp
            if miss_i:
                errors.append(f"{path}: 매니페스트 import가 코드에 없음 {sorted(miss_i)}")
            if extra_i:
                errors.append(f"{path}: 코드 import가 매니페스트에 없음 {sorted(extra_i)}")
        else:
            outside = {r for r in actual_imp if r not in manifest_paths}
            if outside:
                errors.append(f"{path}: 매니페스트 밖 파일 import {sorted(outside)}")
    cyc = _find_cycle(graph)
    if cyc:
        errors.append(f"순환 의존성: {' -> '.join(cyc)}")
    return (len(errors) == 0, errors)


def _find_cycle(graph):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    stack = []

    def dfs(n):
        color[n] = GRAY
        stack.append(n)
        for m in graph.get(n, ()):
            if m not in color:
                continue
            if color[m] == GRAY:
                return stack[stack.index(m):] + [m]
            if color[m] == WHITE:
                r = dfs(m)
                if r:
                    return r
        stack.pop()
        color[n] = BLACK
        return None

    for n in graph:
        if color[n] == WHITE:
            r = dfs(n)
            if r:
                return r
    return None


def _check_static_gate(ws):
    res = static_gate.check(str(ws))
    return (res["ok"], [] if res["ok"] else [res.get("reason", "static_gate 실패")])


def validate(workspace_path, manifest_path, strict=True):
    ws = Path(workspace_path)
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False,
                "checks": [{"name": "manifest_schema", "ok": False}],
                "errors": [f"manifest 로드 실패: {e}"], "warnings": []}

    results = []
    for name, fn in (
        ("manifest_schema", lambda: _check_manifest_schema(manifest)),
        ("file_exists", lambda: _check_file_exists(manifest, ws)),
        ("import_export", lambda: _check_import_export(manifest, ws, strict=strict)),
        ("static_gate", lambda: _check_static_gate(ws)),
    ):
        try:
            ok, errs = fn()
        except Exception as e:  # noqa: BLE001
            ok, errs = False, [f"{name} 검사 중 예외: {e}"]
        results.append((name, ok, errs))

    checks = [{"name": n, "ok": o} for n, o, _ in results]
    errors = [f"[{n}] {msg}" for n, _, es in results for msg in es]
    ok = all(o for _, o, _ in results)
    return {"ok": ok, "checks": checks, "errors": errors, "warnings": []}


if __name__ == "__main__":
    try:
        from config import force_utf8_stdout
        force_utf8_stdout()
    except Exception:  # noqa: BLE001
        pass
    out = validate(sys.argv[1], sys.argv[2])
    print(json.dumps(out, ensure_ascii=False, indent=2))
