"""main.py — campus-agent 第一版

用法：
    python -m agent "图书馆明天几点关门？"
    python -m agent "转专业什么时候能申请？" --debug

第一版只做一件事：把系统规则 + 资料原文 + 问题拼成 messages，
发给模型，把回答打出来，顺手记一行日志。

它现在有一堆毛病，都是故意的，因为每一处毛病后面都有一节在等它：
  · 资料是全塞进去的，没有预算控制 —— 第 2 幕（2.4）
  · 输出是纯文本，程序没法可靠地用 —— 第 2 幕（2.9）
  · 没有任何评测手段，改完不知道变好还是变坏 —— 第 8 幕
先让它跑起来。跑起来才有得改。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .llm import chat, count_tokens
from .knowledge import load_docs, load_rules

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"

# 第一版只装第 1 天抄的那 6 条。第 3 天资料涨到 37 条，这一行就成了事故源头。
FIRST_DAY = 1


def build_messages(question: str, day: int = FIRST_DAY) -> list[dict]:
    """把这一次要发给模型的东西拼好。

    现在的写法是「能塞的都塞」：规则 + 当天的全部资料 + 问题。
    等资料多起来，这段就是第一个要拆的地方（拆成 context.py）。
    """
    docs = [d for d in load_docs() if d.get("day", 1) <= day]

    blocks = []
    for d in docs:
        blocks.append(f"【校内资料】{d['label']}（{d['src']}）：{d['text']}")
    blocks.append(f"同学问：{question}")

    return [
        {"role": "system", "content": load_rules()},
        {"role": "user", "content": "\n\n".join(blocks)},
    ]


def answer(question: str, day: int = FIRST_DAY, log: bool = True) -> dict:
    """问一次，拿回一次。返回的东西比回答多——因为调用本身也要被记录。"""
    messages = build_messages(question, day)
    t0 = time.time()
    reply = chat(messages, question)
    ms = int((time.time() - t0) * 1000)

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question,
        "backend": reply.backend,
        "in_tokens": reply.in_tokens,
        "out_tokens": reply.out_tokens,
        "ms": ms,
        "answer": reply.text,
    }
    if log:
        LOGS.mkdir(exist_ok=True)
        with (LOGS / "run.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description="campus-agent 第一版")
    ap.add_argument("question", nargs="*", help="要问的问题，可以不加引号")
    ap.add_argument("--debug", action="store_true", help="把真正发给模型的东西打出来")
    ap.add_argument("--no-log", action="store_true", help="这次不写日志")
    args = ap.parse_args()

    question = " ".join(args.question).strip()
    if not question:
        question = input("问点什么（比如：一卡通丢了去哪补办）：").strip()
    if not question:
        print("没问东西，退出。")
        return 1

    messages = build_messages(question)
    if args.debug:
        print("─" * 60)
        print(f"messages：{len(messages)} 条，共 {sum(count_tokens(m['content']) for m in messages)} tokens")
        print(messages[0]["content"])
        print("─" * 60)
        print(messages[1]["content"][:600] + ("…" if len(messages[1]["content"]) > 600 else ""))
        print("─" * 60)

    row = answer(question, log=not args.no_log)
    print(row["answer"])
    print()
    print(f"[{row['backend']}] 入 {row['in_tokens']} / 出 {row['out_tokens']} tokens · {row['ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
