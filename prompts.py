"""프롬프트 템플릿. 31B(머리) = 설계·비평, 26B(손) = 구현·수정.

원칙:
- 수용기준은 31B가 만들고 26B는 따르기만 한다 (출제자/응시자 분리).
- 자가수정 프롬프트에는 게이트가 짚은 정확한 줄·에러 종류를 그대로 넣는다.
- 비평가에게는 LGTM 출구를 명시적으로 준다.
"""

import json
import re

DESIGN_SCHEMA_EXAMPLE = """{
  "project_name": "todo_cli",
  "description": "one-line description of the tool",
  "files": [
    {
      "path": "main.py",
      "role": "entry point: parses CLI args, dispatches to core",
      "interfaces": [
        {"kind": "function", "name": "main", "signature": "def main() -> int",
         "description": "parse args, call core, print result"}
      ]
    },
    {
      "path": "core.py",
      "role": "business logic",
      "interfaces": [
        {"kind": "function", "name": "add_item", "signature": "def add_item(store_path: str, text: str) -> dict",
         "description": "append an item, return it"}
      ]
    }
  ],
  "dependencies": {"main.py": ["core.py"], "core.py": []},
  "entrypoint": "main.py",
  "key_points": ["store data as JSON file", "no third-party packages"],
  "acceptance_criteria": [
    "adding an item prints a confirmation containing the item text",
    "listing items shows previously added items"
  ],
  "success_signal": {
    "command": "python main.py add \\"buy milk\\"",
    "expect_substring": "buy milk"
  }
}"""

HARD_RULES = """HARD CONSTRAINTS (violations are rejected by automated gates):
- At least 2 .py files, flat layout (no subdirectories). The files must genuinely
  use each other via imports - decorative files that nothing imports are rejected.
- Python standard library ONLY. No third-party packages.
- NO interactive input: never use input() or read from stdin. All input comes
  from CLI arguments or files.
- The entrypoint file must have an `if __name__ == "__main__":` block.
- The program must run with plain `python <entrypoint> ...` and exit by itself."""


def design_prompt(idea: str, previous_errors: list[str] | None = None) -> str:
    feedback = ""
    if previous_errors:
        feedback = (
            "\n\nYour previous design was rejected by automated validation "
            "with these errors:\n"
            + "\n".join(f"- {e}" for e in previous_errors)
            + "\nFix every error and return the complete corrected JSON.\n"
        )
    return f"""You are the architect of a small multi-file Python CLI prototype.
Design the project for this idea:

IDEA: {idea}

{HARD_RULES}

Also produce:
- "dependencies": which file imports which (this becomes the expected import
  graph that gates verify against the actual code).
- "interfaces": the exact functions/classes each file must define, with
  signatures. The implementer will follow these as a contract.
- "acceptance_criteria": 3-6 concrete, checkable statements of what the
  finished tool must do.
- "success_signal": ONE command that exercises a core behavior of the idea
  (not just --help) plus a substring its output must contain. The command must
  run the entrypoint, be deterministic, and finish within 30 seconds.

Respond with a single JSON object exactly in this shape (no prose before or
after, no markdown fences):

{DESIGN_SCHEMA_EXAMPLE}{feedback}"""


def implement_prompt(design: dict, file_path: str,
                     written: dict[str, str]) -> str:
    spec = next(f for f in design["files"] if f["path"] == file_path)
    context = ""
    if written:
        parts = [f"--- {name} ---\n{content}" for name, content in written.items()]
        context = ("\nFiles already implemented (import from these exactly "
                   "as they are written):\n\n" + "\n\n".join(parts) + "\n")
    return f"""You are implementing ONE file of a multi-file Python CLI project.

PROJECT DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

{HARD_RULES}
{context}
Now write the COMPLETE content of `{file_path}`.

Contract for this file (you must define these exactly):
{json.dumps(spec, ensure_ascii=False, indent=2)}

Rules:
- Implement fully. No stubs, no TODO, no `pass` bodies, no NotImplementedError.
- Import only from the standard library and from the project files listed in
  dependencies["{file_path}"].
- Do not invent attributes or functions that the already-implemented files do
  not define.

Respond with exactly one Python code block containing the full file:

```python
# {file_path}
...
```"""


def fix_prompt(file_path: str, all_files: dict[str, str],
               issues_text: str, design: dict) -> str:
    parts = [f"--- {name} ---\n{content}" for name, content in all_files.items()]
    return f"""A multi-file Python project failed automated checks.
You must fix the file `{file_path}`.

Exact errors reported by the gate (file:line [kind] message):
{issues_text}

Current project files:

{chr(10).join(parts)}

Design contract (interfaces must stay intact):
{json.dumps(design.get("files", []), ensure_ascii=False, indent=2)}

{HARD_RULES}

Fix ONLY `{file_path}` so the reported errors are resolved. Keep everything
that already works. Respond with exactly one Python code block containing the
complete corrected file."""


def critique_prompt(design: dict, all_files: dict[str, str],
                    static_summary: str, exec_log: str) -> str:
    parts = [f"--- {name} ---\n{content}" for name, content in all_files.items()]
    criteria = "\n".join(f"- {c}" for c in design["acceptance_criteria"])
    return f"""You are a strict but fair code reviewer for a small Python CLI prototype.
Base your review on EVIDENCE, not speculation.

ACCEPTANCE CRITERIA (you wrote these; check each):
{criteria}

EVIDENCE - static analysis result:
{static_summary or "clean (no findings)"}

EVIDENCE - execution log (ran inside Docker):
{exec_log}

PROJECT FILES:

{chr(10).join(parts)}

Review for: unmet acceptance criteria, real bugs, broken edge cases that a
normal user would hit, and files that do not genuinely work together.
Do NOT raise style preferences, hypothetical scaling concerns, or rewrites
that do not change behavior.

If there is nothing meaningful left to improve, reply with exactly:
LGTM

Otherwise reply with a single JSON object (no prose, no fences):
{{
  "verdict": "revise",
  "files": [
    {{"path": "main.py", "issues": ["specific problem and what to change"]}}
  ]
}}
Only list files that need changes. Keep issues concrete and actionable."""


def revise_prompt(file_path: str, all_files: dict[str, str],
                  issues: list[str], design: dict) -> str:
    parts = [f"--- {name} ---\n{content}" for name, content in all_files.items()]
    listed = "\n".join(f"- {i}" for i in issues)
    return f"""A code reviewer flagged problems in `{file_path}` of this multi-file
Python project. Apply the review feedback.

Review feedback for `{file_path}`:
{listed}

Current project files:

{chr(10).join(parts)}

Design contract (interfaces must stay intact):
{json.dumps(design.get("files", []), ensure_ascii=False, indent=2)}

{HARD_RULES}

Rewrite `{file_path}` with the feedback applied. Do not break anything that
currently works. Respond with exactly one Python code block containing the
complete revised file."""


def extract_code(text: str) -> str | None:
    """응답에서 파이썬 코드 블록을 꺼낸다. 펜스 없으면 코드처럼 보일 때 전체."""
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    stripped = text.strip()
    if stripped and not stripped.startswith("{") and (
            "def " in stripped or "import " in stripped or "class " in stripped):
        return stripped + "\n"
    return None
