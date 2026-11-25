"""knowledge.py — 资料放在哪、怎么找

资料是学生自己从学生手册和学校通知里抄下来的，存在 data/docs.json。
第一版只做最土的事：问题里的字和哪条资料重合得多，就认为是哪条。

别小看这几行：第 5 幕的检索（分块、向量、重排）本质上是在把
「按字面重合打分」换成一个更好的打分函数。你先知道最土的那版长什么样，
后面才知道每一层加的是什么。
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def load_docs() -> list[dict]:
    raw = json.loads((DATA / "docs.json").read_text(encoding="utf-8"))
    return raw["docs"]


def load_history() -> list[dict]:
    raw = json.loads((DATA / "history.json").read_text(encoding="utf-8"))
    return raw["messages"]


def load_rules() -> str:
    return (DATA / "rules.md").read_text(encoding="utf-8")


def _bigrams(text: str) -> set[str]:
    """把一句话切成相邻两个字一段。

    「转专业」切成 转专 / 专业 两段。比单字准：
    单字「的」「是」到处都是，两个字连在一起才有辨识度。
    """
    t = "".join(ch for ch in text if not ch.isspace())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def score(question: str, doc: dict) -> float:
    """重合度 = 问题里的 bigram 有多少条在资料里出现过。"""
    q = _bigrams(question)
    if not q:
        return 0.0
    body = _bigrams(doc["label"] + "。" + doc["text"])
    return len(q & body) / len(q)


def search(question: str, k: int = 3, day: int | None = None) -> list[dict]:
    """按重合度从高到低取前 k 条。day 用来只取某天之前抄的资料。"""
    docs = [d for d in load_docs() if day is None or d.get("day", 1) <= day]
    ranked = sorted(docs, key=lambda d: -score(question, d))
    return [d for d in ranked[:k] if score(question, d) > 0]
