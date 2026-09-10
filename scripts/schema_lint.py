from __future__ import annotations

import re
import sys
from pathlib import Path

schema = (Path(__file__).resolve().parents[1] / "backend" / "database.py").read_text(encoding="utf-8")
forbidden = re.compile(r"\b(streak|goal|target|rank|progress|连续|目标|排名)\b", re.IGNORECASE)
matches = sorted(set(match.group(0) for match in forbidden.finditer(schema)))
if matches:
    print("数据库结构包含产品红线字段：", ", ".join(matches))
    sys.exit(1)
print("数据库结构红线检查通过。")
