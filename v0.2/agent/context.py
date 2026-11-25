"""context.py — 这一次到底往窗口里放什么

第 3 天的事故就出在这儿：main.py 把当天 37 条资料一次全塞，加上 24 轮历史，
一共 5 千多 token，窗口只有 4096。超出去的部分被截掉，要用的那条恰好
在被截掉的那一头 —— 于是它开始编。

这一版定四条规矩：

  1. 系统规则永远第一条，原文，不参与装填。
  2. 资料按「和问题有多像」排序，从最像的往下装；装不下就跳过这一条，
     不是把这条截一半 —— 截一半的资料比没有更坏，模型会接着半句话编。
  3. 历史从最近的一轮往回装，装到装不下就停。顺序反了就成了「先装历史」，
     聊到第 20 轮资料一条都进不来，又是那天出事的那个样子。
  4. 问题永远最后一条，一个字都不改。

预算 = window - OUTPUT_RESERVE。留出的 512 不是小气：输入塞满了，
模型连「好的」都写不完，出来就是半句话。
"""
from __future__ import annotations

from .knowledge import load_docs, load_history, load_rules, score
from .llm import count_tokens

# 给模型的回答留的位置。4096 的窗口里挪出 512，够写三四句带出处的话。
OUTPUT_RESERVE = 512

# 一次最多装几条资料。多一条就多一分「模型看见无关内容」的机会，
# 这正是下一节要讲的 context rot。
MAX_DOCS = 3


def plan(question: str, day: int | None = None, window: int = 4096) -> dict:
    """排一次装填方案，不发给模型。

    --debug 想看的就是这个东西：哪几条进了、哪几条被挤掉、用了多少预算。
    把它和 pack_context 分开，是因为「看得见」比「跑得对」更早需要。
    """
    budget = window - OUTPUT_RESERVE
    rules = load_rules()

    msgs = [{"role": "system", "content": rules}]
    used = count_tokens(rules)

    docs = load_docs() if day is None else [d for d in load_docs() if d.get("day", 1) <= day]
    ranked = sorted(docs, key=lambda d: -score(question, d))

    picked, dropped = [], []
    for d in ranked:
        if len(picked) >= MAX_DOCS:
            dropped.append(d)
            continue
        body = f"【校内资料】{d['label']}（{d['src']}）：{d['text']}"
        n = count_tokens(body)
        if used + n > budget:
            dropped.append(d)
            continue
        msgs.append({"role": "user", "content": body})
        picked.append(d)
        used += n

    # 问题那一份先扣出来，不然历史会把最后的空位吃光。
    room = budget - used - count_tokens(question)
    hist = []
    for h in reversed(load_history()):
        n = count_tokens(h["content"])
        if n > room:
            break
        hist.insert(0, {"role": h["role"], "content": h["content"]})
        room -= n
    msgs.extend(hist)

    msgs.append({"role": "user", "content": question})
    return {
        "messages": msgs,
        "docs": [{"label": d["label"], "src": d["src"]} for d in picked],
        "dropped": len(dropped),
        "hist_turns": len(hist),
        "used": sum(count_tokens(m["content"]) for m in msgs),
        "budget": budget,
    }


def pack_context(question: str, day: int | None = None, window: int = 4096) -> list[dict]:
    """装好就能发。判分和日常调用都从这里进。"""
    return plan(question, day, window)["messages"]
