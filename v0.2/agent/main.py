"""main.py — campus-agent 第二版（v0.2）

第一版有三个问题，这一版各修一个：

  · 资料全塞、窗口爆掉       → context.pack_context() 按预算装（2.4）
  · 工具参数随手就信         → schemas.check() 先验再用（2.9）
  · 不知道每次问花多少钱     → router 先选模型，日志里记成本（2.14）

还没修（后面的幕会来收）：
  · 聊到第 20 轮就忘了规则   → 第 3 幕
  · 资料靠两个字重合来找     → 第 5 幕
  · 改完不知道是变好还是变坏 → 第 8 幕
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import tools
from .context import pack_context, plan
from .llm import chat
from .router import classify, explain, price, route

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def build_messages(question: str, day: int | None = None, window: int = 4096) -> list[dict]:
    """拼这一次要发出去的东西。

    第一版这段是「能塞的都塞」，现在它只是一层壳：真正做取舍的是 context.py。
    留这个函数名是为了不推翻 1.2 里点读过的那段代码 —— 读过的代码改了名，
    学生会以为自己看错了。
    """
    return pack_context(question, day=day, window=window)


def answer(question: str, log: bool = True) -> dict:
    task = classify(question)
    picked = route(task)
    model = picked["model"]

    filled = plan(question)
    messages = filled["messages"]

    tool_row = None
    if tools.wants_tool(question):
        args = tools.guess_args(question)
        res = tools.call("query_classroom", args)
        tool_row = {"args": args, "ok": res["ok"],
                    "reason": res.get("reason", ""), "data": res.get("data")}
        if res["ok"]:
            said = "工具返回（JSON，直接读字段）：" + json.dumps(
                res["data"], ensure_ascii=False)
        else:
            said = (f"工具拒绝了这次调用：{res['reason']}。"
                    f"按契约重填参数，不要改参数名，也不要自己猜结果。")
        messages = messages[:-1] + [{"role": "user", "content": said}, messages[-1]]

    t0 = time.time()
    reply = chat(messages, question, model=model)
    ms = int((time.time() - t0) * 1000)

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question,
        "model": model,
        "degraded": bool(picked.get("degraded")),
        "backend": reply.backend,
        "in_tokens": reply.in_tokens,
        "out_tokens": reply.out_tokens,
        "cost": round(price(model, reply.in_tokens, reply.out_tokens), 6),
        "docs": len(filled["docs"]),
        "ms": ms,
        "tool": tool_row,
        "answer": reply.text,
    }
    if log:
        LOGS.mkdir(exist_ok=True)
        with (LOGS / "run.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="campus-agent 第二版")
    ap.add_argument("question", nargs="*", help="要问的问题，可以不加引号")
    ap.add_argument("--debug", action="store_true", help="把路由理由和装填计划打出来")
    ap.add_argument("--no-log", action="store_true", help="这次不写日志")
    args = ap.parse_args()

    question = " ".join(args.question).strip()
    if not question:
        question = input("问点什么（比如：明天下午三教有空教室吗）：").strip()
    if not question:
        print("没问东西，退出。")
        return 1

    if args.debug:
        task = classify(question)
        picked = route(task)
        filled = plan(question)
        print("─" * 60)
        print("路由：" + explain(task, picked))
        print(f"装填：{filled['used']} / {filled['budget']} tokens，"
              f"资料 {len(filled['docs'])} 条，挤掉 {filled['dropped']} 条，"
              f"历史 {filled['hist_turns']} 条")
        for d in filled["docs"]:
            print(f"  + {d['label']}（{d['src']}）")
        print("─" * 60)

    row = answer(question, log=not args.no_log)

    if row["tool"]:
        t = row["tool"]
        print(f"[工具] query_classroom({json.dumps(t['args'], ensure_ascii=False)}) "
              f"→ {'成功' if t['ok'] else '拒绝：' + str(t['reason'])}")
        if t["ok"]:
            print(json.dumps(t["data"], ensure_ascii=False, indent=2))
        print()

    print(row["answer"])
    print()
    flag = " · 降档" if row["degraded"] else ""
    print(f"[{row['model']}{flag} · {row['backend']}] "
          f"入 {row['in_tokens']} / 出 {row['out_tokens']} tokens · "
          f"≈{row['cost']:.4f} 元 · {row['ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
