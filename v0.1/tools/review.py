"""review.py — 阿布提的改动，先过这一道

第 1.9 节要你把这个函数补完。它是你现在手工审 diff 的自动化版本：
三条仓库约定，机器先过一遍，过不了的直接打回，别浪费你的注意力。

    python -m tools.review changes.diff

三条约定（第 10 幕会真的写进 AGENTS.md）：
  touch-tests  不许改 tests/ 下的任何文件
  new-dep      不许动依赖清单（pyproject.toml / requirements.txt）
  drop-test    不许删掉已有的 def test_
"""
from __future__ import annotations

import sys
from pathlib import Path

DEP_FILES = ("pyproject.toml", "requirements.txt", "package.json")


def review(diff: str) -> dict:
    """返回 {"verdict": "accept" | "reject", "rules": [...], "evidence": [...]}。

    evidence 给「改动行原文」：去掉行首的 + / - 和缩进，不要给行号。
    合规时 rules 与 evidence 都是空列表。

    TODO(1.9)：先把被改的文件路径收齐，再把新增/删除行收齐，最后一次性套三条规则。
    注意 "+++" / "---" 这两个前缀也以 + / - 开头，不先跳过就会被当成改动行。
    """
    rules: list[str] = []
    evidence: list[str] = []

    # 提示：一份 diff 可能同时踩两条（改了 tests/ 又删了测试），两条都要报。
    return {"verdict": "accept" if not rules else "reject",
            "rules": rules, "evidence": evidence}


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python -m tools.review <diff 文件>")
        return 1
    diff = Path(sys.argv[1]).read_text(encoding="utf-8")
    r = review(diff)
    print(r["verdict"], r["rules"], r["evidence"])
    return 0 if r["verdict"] == "accept" else 2


if __name__ == "__main__":
    raise SystemExit(main())
