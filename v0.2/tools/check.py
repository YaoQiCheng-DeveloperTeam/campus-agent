"""check.py — 项目的十条验收

课程里每节做完，跑一次这个。它问的不是「你懂了吗」，
是「你的项目现在能不能过这十条」。

    cd campus-agent
    python tools/check.py

全绿才算 v0.2 交付。有一条红，就照它给的那句提示去改。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, BAD = "\033[32m✓\033[0m", "\033[31m✗\033[0m"


def _run(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("AGENT_GATEWAY", "OPENAI_API_KEY")}   # 验收一律走离线，别花学生的钱
    # Windows 下子进程默认按 GBK 写中文，父进程按 UTF-8 读就会读成乱码，
    # 断言「回答里有没有『资料里没写』」会永远失败。这一行是为了让验收在
    # Windows / macOS / Linux 上表现一致。
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=env)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # 1. CLI 能跑，回答非空
    p = _run(["-m", "agent", "一卡通丢了去哪补办", "--no-log"])
    out = (p.stdout or "").strip()
    checks.append(("命令行能跑通", p.returncode == 0 and bool(out),
                   (p.stderr or "").strip().splitlines()[-1] if p.returncode else ""))

    # 2. 回答里有出处标记
    has_src = "[" in out and "]" in out
    checks.append(("回答带出处", has_src,
                   "" if has_src else "回答里没有 [出处] 标记，模型可能没照规则来"))

    # 3. 资料里没写的，不硬编
    p2 = _run(["-m", "agent", "附近哪家火锅好吃", "--no-log"])
    o2 = (p2.stdout or "")
    honest = ("资料里没写" in o2) or ("不了解" in o2) or ("没找到" in o2)
    checks.append(("不知道就说不知道", honest,
                   "" if honest else "问了校外问题，它居然答了——这是最危险的一种错"))

    # 4. 日志留痕
    log = ROOT / "logs" / "run.jsonl"
    p3 = _run(["-m", "agent", "补考没过怎么办"])
    ok_log, why = False, "logs/run.jsonl 没生成"
    if log.exists():
        lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            try:
                row = json.loads(lines[-1])
                need = {"ts", "question", "in_tokens", "out_tokens", "ms"}
                ok_log = need <= set(row) and row["in_tokens"] > 0
                why = "" if ok_log else f"最后一行的字段不全：{sorted(row)}"
            except json.JSONDecodeError:
                why = "最后一行不是合法 JSON"
    checks.append(("每次调用都有日志", ok_log, why))

    # 5. 规则只有一份
    rules_file = (ROOT / "data" / "rules.md").read_text(encoding="utf-8").strip()
    from agent.main import build_messages
    same = build_messages("x")[0]["content"].strip() == rules_file
    checks.append(("系统规则来自 rules.md", same,
                   "" if same else "代码里另写了一份规则，两处会不一致"))

    # 6. 单测
    p4 = _run(["-m", "unittest", "discover", "-s", "tests"], timeout=120)
    checks.append(("单测全过", p4.returncode == 0,
                   "" if p4.returncode == 0 else (p4.stderr or "").strip()[-160:]))

    from agent.context import OUTPUT_RESERVE, plan
    from agent.router import BY_NAME, classify, price, route
    from agent.tools import call as call_tool

    # 7. 装得进窗口：37 条资料 + 48 条历史，谁都不能超预算
    filled = plan("转专业什么时候能申请？")
    under = filled["used"] <= 4096 - OUTPUT_RESERVE
    checks.append(("装得进窗口", under,
                   "" if under else f"用了 {filled['used']}，预算 {4096 - OUTPUT_RESERVE}"))

    # 8. 该进的资料真的进了（不是「装了三条随便什么」）
    labels = [d["label"] for d in filled["docs"]]
    hit = any("转专业" in x for x in labels)
    checks.append(("命中的资料在窗口里", hit,
                   "" if hit else f"装了 {labels}，没有转专业那一条"))

    # 9. 参数错了要被挡住，而且说清是哪个字段
    bad = call_tool("query_classroom", {"day": "明天", "slot": "25:00", "building": "三教"})
    blocked = (not bad["ok"]) and "slot" in bad.get("reason", "")
    checks.append(("非法参数进不了工具", blocked,
                   "" if blocked else f"25:00 这种时间居然被放行了：{bad}"))

    # 10. 成本能算出来（不然日志里那一列永远是 0）
    picked = route(classify("帮我对比一下两个转专业方向，哪个更适合考研"))
    money = price(picked["model"], 1200, 300)
    has_cost = picked["model"] in BY_NAME and money > 0
    checks.append(("每次调用算得出成本", has_cost,
                   "" if has_cost else f"路由给了 {picked}，价格算不出来"))

    print()
    for name, ok, why in checks:
        print(f"  {OK if ok else BAD} {name}" + (f"  — {why}" if why else ""))
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n  {passed} / {len(checks)} 通过" + ("  · v0.2 交付 ✓" if passed == len(checks) else ""))
    print()
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
