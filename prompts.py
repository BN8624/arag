"""프롬프트 템플릿. 31B(머리) = 설계·비평, 26B(손) = 구현·수정.

원칙:
- 수용기준은 31B가 만들고 26B는 따르기만 한다 (출제자/응시자 분리).
- 자가수정 프롬프트에는 게이트가 짚은 정확한 줄·에러 종류를 그대로 넣는다.
- 비평가에게는 LGTM 출구를 명시적으로 준다.
"""

import json
import re

# 프롬프트 세대 표식 — 프롬프트(이 파일 또는 reviewer.py)를 바꿀 때마다 갱신할 것.
# 런 index에 기록되어 전후 비교(A/B)의 분모를 가른다. 형식: 날짜-변경요약
PROMPT_VERSION = "20260612-reviewer-nochange-exit"

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
  "requirements": [
    {"text": "user can add a todo item from the command line", "covered_by": [0]},
    {"text": "user can list previously added items", "covered_by": [1]}
  ],
  "acceptance_criteria": [
    "adding an item prints a confirmation containing the item text",
    "listing items shows previously added items"
  ],
  "criteria_checks": [
    {"criterion": "adding an item prints a confirmation containing the item text",
     "command": "python main.py add \\"buy milk\\"",
     "expect_substring": "buy milk"},
    {"criterion": "listing items shows previously added items",
     "command": "python main.py list",
     "expect_substring": "buy milk"},
    {"criterion": "tool errors when run without required argument",
     "command": "python main.py add",
     "expect_substring": "Error",
     "expect_exit_code": 1}
  ],
  "success_signal": {
    "command": "python main.py add \\"buy milk\\"",
    "expect_substring": "buy milk"
  }
}"""

HARD_RULES = """HARD CONSTRAINTS (violations are rejected by automated gates):
- At least 2 .py files, flat layout (no subdirectories). The files must genuinely
  use each other via imports - decorative files that nothing imports are rejected.
  Aim for 3-5 focused modules when the idea has enough substance (e.g. CLI
  parsing / core logic / storage / formatting as separate files); use 2 only
  for genuinely trivial ideas.
- Allowed imports: the Python standard library, plus ONLY these third-party
  packages when genuinely needed: requests, rich, click, tabulate, yaml (PyYAML),
  dateutil, tqdm, colorama, jinja2, markdown, openpyxl, pypdf, Pillow (PIL).
  Any other package is rejected.
  Prefer the standard library when it is enough.
- NO interactive input: never use input() or read from stdin. All input comes
  from CLI arguments or files.
- The entrypoint file must have an `if __name__ == "__main__":` block.
- The program must run with plain `python <entrypoint> ...` and exit by itself.
- Commands run in a fresh directory containing ONLY the project files. They must
  not assume any other file exists - if the tool needs an input file, an earlier
  command must create it through the tool itself.
- The verification sandbox has NO network access. If the idea requires calling
  an external service/API, isolate ALL such calls in ONE dedicated module, and
  every command must work offline through a `--mock <file>` CLI option that
  reads a local fixture file instead of calling the real service. Secrets
  (API keys) come only from CLI arguments or environment variables - never
  hardcode them, and mock mode must not require one."""


def design_prompt(idea: str, previous_errors: list[str] | None = None,
                  lessons: list[str] | None = None) -> str:
    feedback = ""
    if previous_errors:
        feedback = (
            "\n\nYour previous design was rejected by automated validation "
            "with these errors:\n"
            + "\n".join(f"- {e}" for e in previous_errors)
            + "\nFix every error and return the complete corrected JSON.\n"
        )
    lessons_part = ""
    if lessons:
        lessons_part = (
            "\nLESSONS FROM PAST FAILED RUNS on similar ideas "
            "(design so these mistakes cannot repeat):\n"
            + "\n".join(f"- {l}" for l in lessons) + "\n")
    return f"""You are the architect of a small multi-file Python CLI prototype.
Design the project for this idea:

IDEA: {idea}

{HARD_RULES}
{lessons_part}
Also produce:
- "requirements": FIRST decompose the IDEA into atomic requirements - every
  distinct capability AND stated promise the idea mentions or clearly
  implies (output units, file formats, supported syntax, generality), one
  entry each.
  Each requirement maps to the acceptance criteria that cover it via
  "covered_by" (a list of 0-based indices into "acceptance_criteria").
  Every requirement MUST be covered by at least one criterion - if a
  capability from the idea has no criterion, add a criterion for it.
- "dependencies": which file imports which (this becomes the expected import
  graph that gates verify against the actual code). dependencies and
  interfaces MUST be consistent: if file X is listed as importing file Y,
  X's code must genuinely import AND use Y. If a function instead receives
  a collaborator object as a parameter (dependency injection), do NOT also
  list that module in X's imports - pick one style per edge.
- "interfaces": the exact functions/classes each file must define, with
  signatures. The implementer will follow these as a contract.
- "acceptance_criteria": 3-6 concrete, checkable statements of what the
  finished tool must do. Criteria must verify the idea's PROMISES, not merely
  that commands exit 0:
  * if the idea states an output unit or format (hours, xlsx, a JSON report
    file...), one criterion must check that exact unit/format appears;
  * if it promises generality (any file path, user-defined config), one
    criterion must use a non-default input;
  * if it promises a syntax or range (e.g. standard cron expressions), one
    criterion must exercise a non-trivial case, not only the simplest one.
  A tool that runs but silently narrows a stated promise FAILS that criterion.
  Do not inflate the criterion count for this - tighten what each one covers.
- "criteria_checks": for EVERY acceptance criterion, one executable check:
  a command, a substring its output must contain, and optionally
  "expect_exit_code" (integer, default 0). Use "expect_exit_code": 1 when the
  criterion is that the tool FAILS (e.g. "tool errors when no API key given").
  Checks run in order in the same directory, so an earlier command may create
  state a later one reads.
  Keep these at CLI level (commands, produced files, exit codes) - internal
  function behavior and edge cases are covered separately by pytest.
- "success_signal": ONE command line that exercises a core behavior of the
  idea (not just --help) plus a substring its output must contain. Its final
  step must run the entrypoint, be deterministic, and finish within 30 seconds.
- "mock_fixtures" (ONLY if the idea calls an external service): realistic fake
  API response files, e.g. [{{"path": "mock_response.json", "content": {{...}}}}].
  These files are placed next to the code before verification. Every
  success_signal / criteria_checks command must then use `--mock <that file>`
  so the whole pipeline is verified offline. Make the fake response rich
  enough to exercise parsing, edge values included.

Command rules (for success_signal AND criteria_checks):
- A command line may chain several steps with '&&' when setup is needed,
  e.g. first create an input file THROUGH THE TOOL, then process it:
  "python main.py make-sample data.csv && python main.py convert data.csv"
- EVERY step must start with `python` (no echo/cat/shell tricks).
- Each option/subcommand a command uses MUST exist in the designed interfaces -
  commands and interfaces must match exactly.

Respond with a single JSON object exactly in this shape (no prose before or
after, no markdown fences):

{DESIGN_SCHEMA_EXAMPLE}{feedback}"""


def implement_prompt(design: dict, file_path: str,
                     written: dict[str, str],
                     notes: list[str] | None = None) -> str:
    spec = next(f for f in design["files"] if f["path"] == file_path)
    # 컨텍스트 다이어트: 이 파일이 직접 import하는 파일만 보여준다.
    # (전체를 넣으면 26B thinking이 입력 크기를 따라 길어져 비용의 주범이 됨)
    deps = design.get("dependencies", {}).get(file_path, [])
    relevant = {name: code for name, code in written.items() if name in deps}
    context = ""
    if relevant:
        parts = [f"--- {name} ---\n{content}"
                 for name, content in relevant.items()]
        context = ("\nFiles this file imports from (import from these exactly "
                   "as they are written):\n\n" + "\n\n".join(parts) + "\n")
    notes_part = ""
    if notes:
        joined = "\n".join(f"- {n}" for n in notes)
        notes_part = (f"\nA reviewer repeatedly flagged these problems in past "
                      f"projects. Pre-empt them in your code:\n{joined}\n")
    return f"""You are implementing ONE file of a multi-file Python CLI project.

PROJECT DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

{HARD_RULES}
{notes_part}{context}
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
    sig = design.get("success_signal", {})
    signal_part = ""
    if sig.get("command"):
        signal_part = (f"\nThis exact command MUST succeed after your fix:\n"
                       f"  $ {sig['command']}\n"
                       f"  (its output must contain: {sig.get('expect_substring', '')!r})\n"
                       "If the command uses an option or subcommand the code does not\n"
                       "define, ADD it to the code - do not rename or remove it.\n")
    deps = design.get("dependencies", {}).get(file_path, [])
    deps_part = ""
    if deps:
        deps_part = (f"\nDesign dependency contract: `{file_path}` must import "
                     f"AND actually use: {', '.join(deps)}. Satisfy both - an "
                     "import that is never called is also a gate failure.\n")
    return f"""A multi-file Python project failed automated checks.
You must fix the file `{file_path}`.

Exact errors reported by the gate (file:line [kind] message):
{issues_text}
{signal_part}{deps_part}

Current project files:

{chr(10).join(parts)}

Design contract (interfaces must stay intact):
{json.dumps(design.get("files", []), ensure_ascii=False, indent=2)}

{HARD_RULES}

Fix ONLY `{file_path}` so the reported errors are resolved. Keep everything
that already works. Respond with exactly one Python code block containing the
complete corrected file."""


EDGE_CASE_CHECKLIST = """EDGE-CASE CHECKLIST (walk through the code for each;
flag only breaks a normal user would actually hit):
- empty input (empty file, empty string argument, zero rows)
- missing or nonexistent input file
- invalid values (non-numeric where a number is expected, negative, zero)
- malformed lines mixed into otherwise valid input
- duplicate entries
- non-ASCII text (Korean) in values"""


def critique_prompt(design: dict, all_files: dict[str, str],
                    static_summary: str, exec_log: str,
                    scoreboard: str | None = None,
                    idea: str | None = None) -> str:
    parts = [f"--- {name} ---\n{content}" for name, content in all_files.items()]
    criteria = "\n".join(f"- {c}" for c in design["acceptance_criteria"])
    idea_part = ""
    if idea:
        idea_part = (f"ORIGINAL IDEA (the user's actual request):\n{idea}\n\n"
                     "COVERAGE CHECK: compare the ORIGINAL IDEA against the code and\n"
                     "the acceptance criteria. If the idea mentions a capability that\n"
                     "neither the criteria nor the code delivers, that is a REAL issue -\n"
                     "flag the file that should implement it. The criteria passing is\n"
                     "not enough if the criteria themselves missed part of the idea.\n\n")
    return f"""You are a strict but fair code reviewer for a small Python CLI prototype.
Base your review on EVIDENCE, not speculation.

{idea_part}ACCEPTANCE CRITERIA (you wrote these; check each):
{criteria}

{EDGE_CASE_CHECKLIST}

EVIDENCE - acceptance check scoreboard (each criterion actually executed):
{scoreboard or "(not run)"}

EVIDENCE - static analysis result:
{static_summary or "clean (no findings)"}

EVIDENCE - execution log (ran inside Docker):
{exec_log}

PROJECT FILES:

{chr(10).join(parts)}

Review for: unmet acceptance criteria, real bugs, broken edge cases that a
normal user would hit, and files that do not genuinely work together.
A [FAIL] line in the scoreboard is a real unmet criterion - it MUST be
addressed, never excused. Do NOT raise style preferences, hypothetical
scaling concerns, or rewrites that do not change behavior.

If every scoreboard line is [PASS] and the execution log shows the tool
working, the default verdict is LGTM. Request changes only for a defect you
can point to in the evidence above - a concrete wrong output, a crash path,
or a capability from the ORIGINAL IDEA that is genuinely absent. Revisions
are not free: a wrong revision can break a working build.

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


def tests_prompt(design: dict) -> str:
    return f"""You are the examiner for a small multi-file Python CLI project.
Write a pytest test file that verifies the project against its design contract.
The implementer has NOT written the code yet - your tests ARE the bar it must
clear, so test only what the design promises.

PROJECT DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

Rules:
- The file will be saved as `test_acceptance.py` next to the project files and
  run with `python -m pytest -q` inside an offline container.
- Import ONLY: pytest, the standard library, and the project modules listed in
  the design. Use exactly the interfaces (names, signatures) the design
  defines - never invent helpers the design does not promise.
- Tests must be deterministic, offline, fast, and never read stdin.
- Use the tmp_path fixture for any files tests create; never depend on
  pre-existing files or on test execution order.
- NEVER pass a non-existent file path to a function in a test — always create
  the file first (e.g. with tmp_path) or use pytest.raises() to assert the
  expected exception. Calling f(mock_file="file") where "file" does not exist
  without wrapping it in pytest.raises is always wrong.
- If the project uses click: invoke CLI commands via click.testing.CliRunner,
  NOT by calling main() directly. CliRunner.invoke() returns a Result object;
  check result.exit_code (0 = success). Never assert that main() returns 0 —
  click functions return None in standalone_mode=False, not an integer.
- Construct CliRunner with NO arguments: `CliRunner()`. It accepts no path or
  working-directory arguments — for filesystem isolation use
  `runner.isolated_filesystem()` or pass tmp_path-based paths as CLI arguments.
- runner.invoke() only works on @click.command/@click.group objects. If the
  design does NOT use click (e.g. argparse), do NOT import click.testing —
  call the designed functions directly instead.
- Cover the acceptance criteria that are testable at function level, plus
  edge cases (empty input, invalid values) ONLY where the design contract
  makes the expected behavior unambiguous. When the contract does not specify
  a behavior, do not test it.
- Focus on FUNCTION-LEVEL behavior and edge cases. CLI-level happy paths
  (full commands, exit codes, produced files) are already verified by
  separate criteria checks - do not duplicate them here.
- NEVER assert equality against the ENTIRE stdout or a whole multi-line
  block. Assert on individual substrings or single lines instead - layout
  and ordering are implementation freedom unless the contract pins them.
- Compare numbers NUMERICALLY, never as strings: parse the value and use
  float(x) == pytest.approx(expected). String comparisons like "1.0" vs "1"
  are formatting accidents, not contract violations.
- If the contract does not pin an exact output format, assert that the key
  VALUES appear, not how they are formatted.
- Write 5-12 focused test functions.

Respond with exactly one Python code block containing the complete test file."""


def tests_fix_prompt(design: dict, test_code: str, pytest_log: str) -> str:
    return f"""You are the examiner for a small multi-file Python CLI project.
The pytest file YOU wrote earlier crashes because of bugs in the TEST CODE
itself (wrong library usage), not because the implementation is wrong.

PROJECT DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

YOUR CURRENT TEST FILE (test_acceptance.py):
```python
{test_code}
```

PYTEST OUTPUT (the errors come from the test code or the testing library,
not from the project modules):
{pytest_log}

Fix ONLY the broken test code. Keep what each test verifies (the contract)
unchanged - do not weaken or delete assertions about designed behavior.
Common causes to check:
- CliRunner takes NO constructor arguments. Use `CliRunner()`; for filesystem
  isolation use `runner.isolated_filesystem()` or tmp_path-based CLI arguments.
- runner.invoke() only works on @click.command/@click.group objects, never on
  plain functions. If the entrypoint is not a click command, call the designed
  functions directly instead.
- Never invent keyword arguments or helpers that the libraries or the design
  do not provide.
- If an ARBITER VERDICT appears in the output above, follow its instruction
  even when it relaxes an over-specified assertion (e.g. exact string
  formatting the design contract never promised).

Respond with exactly one Python code block containing the complete corrected
test file."""


def arbitrate_prompt(design: dict, test_code: str, pytest_log: str) -> str:
    """같은 단언 실패가 반복될 때: 시험지가 과한가, 코드가 계약 위반인가 (31B 판정)."""
    return f"""You are the examiner for a small multi-file Python CLI project.
One of YOUR acceptance tests keeps failing with an AssertionError even after
several implementation fixes. The implementer is stuck. Decide which side
violates the DESIGN CONTRACT: the test's expectation, or the implementation.

PROJECT DESIGN (the only authority):
{json.dumps(design, ensure_ascii=False, indent=2)}

YOUR TEST FILE (test_acceptance.py):
```python
{test_code}
```

PYTEST OUTPUT (tail):
{pytest_log}

Judging rules:
- The design contract is the ONLY authority.
- If the disputed detail (exact number formatting, exact line layout, exact
  wording) is NOT specified by the contract, the TEST over-specifies it -
  blame "test".
- If the implementation clearly violates what the contract states (wrong
  value, wrong classification, missing behavior), blame "code".

Respond with a single JSON object (no prose, no fences):
{{"blame": "test" or "code",
  "instruction": "one or two sentences: exactly what to change and why"}}"""


def improve_prompt(design: dict, files: dict[str, str], feedback: str,
                   scoreboard_text: str) -> str:
    parts = [f"--- {name} ---\n{content}" for name, content in files.items()]
    feedback_part = ""
    if feedback.strip():
        feedback_part = f"\nUSER FEEDBACK (the most important input):\n{feedback}\n"
    return f"""You are the architect reviewing a WORKING prototype that already
passed all automated gates. Decide how to make it meaningfully better.

ORIGINAL DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

CURRENT CODE:
{chr(10).join(parts)}

LAST ACCEPTANCE RESULTS:
{scoreboard_text}
{feedback_part}
{HARD_RULES}

Your job:
1. If there is genuinely nothing worth improving (and no user feedback to
   address), respond with exactly: NOCHANGE
2. Otherwise produce an UPGRADED design plus a minimal change plan.

Upgrade rules (violations are rejected automatically):
- KEEP every existing entry of "acceptance_criteria" and "criteria_checks"
  unchanged - they are the regression bar. APPEND 1-3 new, stricter criteria
  (each with an executable check) that capture the improvement. If the user
  feedback names a problem, at least one new criterion must verify the fix.
- Every new check "command" must consist ONLY of steps starting with
  `python ` (joined by '&&'). NO shell redirection (>, >>), echo, pipes, rm.
  If a check needs a fixture file (e.g. a broken input), create it inside a
  python step: python -c "open('bad.json','w').write('{{')" && python main.py bad.json
- Keep the existing file layout where possible. Prefer changing few files.
  You may add a new file only if the improvement clearly needs one.
- "changes": list every file that must be modified or created, with concrete
  instructions the implementer can follow without guessing.

Respond with a single JSON object (no prose, no fences):
{{"design": {{...the full updated design, same schema as the original...}},
  "changes": [{{"path": "main.py",
               "instructions": ["specific change 1", "specific change 2"]}}]}}"""


def readme_prompt(design: dict) -> str:
    sig = design.get("success_signal", {})
    checks = design.get("criteria_checks") or []
    examples = "\n".join(f"- {c.get('command', '')}" for c in checks if c.get("command"))
    return f"""Write a README.md for this small Python CLI tool, aimed at a
non-programmer who just wants to use it.

PROJECT DESIGN:
{json.dumps(design, ensure_ascii=False, indent=2)}

Known-working commands (verified by automated checks):
- {sig.get('command', '')}
{examples}

Structure: what the tool does (2-3 sentences), requirements (Python version,
`pip install .` if there are dependencies), usage with the verified commands
above as examples plus expected output, and a short options/subcommands table
if applicable. Keep it under 80 lines. Do not invent commands or options that
are not in the design.

Respond with exactly one markdown code block containing the complete README:

```markdown
# ...
```"""


def extract_markdown(text: str) -> str | None:
    """응답에서 마크다운 블록을 꺼낸다. 펜스 없으면 #으로 시작할 때 전체."""
    blocks = re.findall(r"```(?:markdown|md)\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return max(blocks, key=len).strip() + "\n"
    stripped = text.strip()
    if stripped.startswith("#"):
        return stripped + "\n"
    return None


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
