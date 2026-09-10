from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (ROOT / "frontend" / "src", ROOT / "backend")
SUFFIXES = {".vue", ".ts", ".py"}
IGNORED_PARTS = {".venv", "node_modules", "dist", "__pycache__"}
RULES = {
    "评判性禁用词": re.compile(
        r"坚持|加油|别放弃|落后|效率|自律|达成率|突破|战胜自己|失败|还差|已断|清零|努力不够|连续.{0,4}天"
    ),
    "感叹号": re.compile(r"！"),
}


def main() -> int:
    failures: list[str] = []
    for target in TARGETS:
        for path in target.rglob("*"):
            if path.suffix not in SUFFIXES or IGNORED_PARTS.intersection(path.parts):
                continue
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for label, pattern in RULES.items():
                    if pattern.search(line):
                        failures.append(f"{path.relative_to(ROOT)}:{line_number}: {label}: {line.strip()}")
    if failures:
        print("文案红线检查未通过：")
        print("\n".join(failures))
        return 1
    print("文案红线检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
