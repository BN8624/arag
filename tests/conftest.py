import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GOOD_CORE = '''\
import json
from pathlib import Path


def add_item(store_path: str, text: str) -> dict:
    path = Path(store_path)
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    item = {"id": len(items) + 1, "text": text}
    items.append(item)
    path.write_text(json.dumps(items), encoding="utf-8")
    return item
'''

GOOD_MAIN = '''\
import sys

from core import add_item


def main() -> int:
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        item = add_item("todo.json", sys.argv[2])
        print(f"added: {item['text']}")
        return 0
    print("usage: python main.py add <text>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def make_design() -> dict:
    return {
        "project_name": "todo_cli",
        "description": "tiny todo list CLI",
        "files": [
            {"path": "main.py", "role": "entry point",
             "interfaces": [{"kind": "function", "name": "main",
                             "signature": "def main() -> int",
                             "description": "parse args"}]},
            {"path": "core.py", "role": "logic",
             "interfaces": [{"kind": "function", "name": "add_item",
                             "signature": "def add_item(store_path: str, text: str) -> dict",
                             "description": "append item"}]},
        ],
        "dependencies": {"main.py": ["core.py"], "core.py": []},
        "entrypoint": "main.py",
        "key_points": ["store as JSON"],
        "requirements": [{"text": "user can add a todo item",
                          "covered_by": [0]}],
        "acceptance_criteria": ["adding an item prints confirmation with the text"],
        "success_signal": {"command": 'python main.py add "buy milk"',
                           "expect_substring": "buy milk"},
    }


def write_project(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path
