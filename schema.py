"""설계 JSON 스키마: 파싱(관대한 추출) + 구조 검증.

31B가 내놓는 설계 산출물의 형태:
{
  "project_name": "todo_cli",
  "description": "한 줄 설명",
  "files": [
    {
      "path": "main.py",
      "role": "진입점. 인자 파싱 후 core 호출",
      "interfaces": [
        {"kind": "function", "name": "main", "signature": "def main() -> int",
         "description": "..."}
      ]
    }
  ],
  "dependencies": {"main.py": ["core.py"], "core.py": []},
  "entrypoint": "main.py",
  "key_points": ["..."],
  "acceptance_criteria": ["..."],
  "success_signal": {
    "command": "python main.py add \"buy milk\"",
    "expect_substring": "added"
  }
}

dependencies는 "누가 누굴 import하나" — 정적 게이트의 기대값이 된다.
"""

import json
import re

REQUIRED_KEYS = (
    "project_name", "files", "dependencies", "entrypoint",
    "acceptance_criteria", "success_signal",
)

MAX_FILES = 10  # 회차당 캡 (가드레일)


def extract_json(text: str) -> str | None:
    """모델 응답에서 JSON 본문을 끄집어낸다.

    우선순위: ```json 펜스 블록 → 첫 '{'부터 균형 맞는 '}'까지.
    """
    fence = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        if candidate.startswith("{"):
            return candidate
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_design(text: str) -> tuple[dict | None, list[str]]:
    """모델 응답 텍스트 → (설계 dict, 에러 목록). 실패 시 (None, errors)."""
    raw = extract_json(text)
    if raw is None:
        return None, ["no JSON object found in response"]
    try:
        design = json.loads(raw)
    except json.JSONDecodeError as err:
        return None, [f"JSON parse error: {err}"]
    if not isinstance(design, dict):
        return None, ["top-level JSON is not an object"]
    errors = validate_shape(design)
    if errors:
        return None, errors
    return design, []


def validate_shape(design: dict) -> list[str]:
    """구조(키 존재·타입)만 검증. 의미 검증은 design_validator가 한다."""
    errors = []
    for key in REQUIRED_KEYS:
        if key not in design:
            errors.append(f"missing required key: {key!r}")
    if errors:
        return errors

    files = design["files"]
    if not isinstance(files, list) or not files:
        errors.append("'files' must be a non-empty list")
    else:
        for i, f in enumerate(files):
            if not isinstance(f, dict) or not isinstance(f.get("path"), str):
                errors.append(f"files[{i}] must be an object with string 'path'")
                continue
            ifaces = f.get("interfaces", [])
            if not isinstance(ifaces, list):
                errors.append(f"files[{i}].interfaces must be a list")
                continue
            for j, iface in enumerate(ifaces):
                if not isinstance(iface, dict):
                    errors.append(f"files[{i}].interfaces[{j}] must be an object")
                elif not isinstance(iface.get("name"), str):
                    errors.append(f"files[{i}].interfaces[{j}] needs string 'name'")

    deps = design["dependencies"]
    if not isinstance(deps, dict):
        errors.append("'dependencies' must be an object (file -> [files it imports])")
    else:
        for k, v in deps.items():
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(f"dependencies[{k!r}] must be a list of file paths")

    if not isinstance(design["entrypoint"], str):
        errors.append("'entrypoint' must be a string file path")

    ac = design["acceptance_criteria"]
    if not isinstance(ac, list) or not ac or not all(isinstance(x, str) for x in ac):
        errors.append("'acceptance_criteria' must be a non-empty list of strings")

    sig = design["success_signal"]
    if not isinstance(sig, dict):
        errors.append("'success_signal' must be an object")
    else:
        if not isinstance(sig.get("command"), str) or not sig.get("command", "").strip():
            errors.append("success_signal.command must be a non-empty string")
        if (not isinstance(sig.get("expect_substring"), str)
                or not sig.get("expect_substring", "").strip()):
            errors.append("success_signal.expect_substring must be a non-empty string")
    return errors
