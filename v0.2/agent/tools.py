"""tools.py — 模型说「我要查」，代码真的去查

分工是这一节的全部重点：

    模型负责「填表」（输出参数），代码负责「验表」和「动手」。

所以调用顺序不能反过来：先 check，再执行。模型填错参数是常态，
把它退回去重填一次，比让它拿着错参数去查库要好 —— 查库那一步出错，
你连错在哪儿都不知道。

v0.2 只有一个工具：query_classroom。第 4 幕会把它换成真正的循环
（模型自己决定调哪个工具、调几次、什么时候停）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .schemas import check

DATA = Path(__file__).resolve().parent.parent / "data"


def load_classrooms() -> dict:
    return json.loads((DATA / "classrooms.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 工具本体
def query_classroom(args: dict) -> dict:
    """查某个时段某栋楼还有哪些空教室。

    返回值是固定形状的 JSON，不是一段话 —— 调用它的那一段代码要能直接读字段。
    """
    table = load_classrooms()
    day, slot, building = args["day"], args["slot"], args["building"]

    free = []
    for r in table["rooms"]:
        if r["building"] != building:
            continue
        what = r["busy"].get(day, {}).get(slot, "")
        if not what:
            free.append({"room": r["room"], "capacity": r["capacity"]})

    return {
        "ok": True,
        "day": day,
        "slot": slot,
        "building": building,
        "free": free,
        "checked": len(free) + sum(
            1 for r in table["rooms"]
            if r["building"] == building and r["busy"].get(day, {}).get(slot, "")),
        "note": "" if free else f"{building} 这个时段没有空教室，换一栋楼或者换个时间",
    }


REGISTRY = {"query_classroom": query_classroom}


def call(name: str, raw) -> dict:
    """按名字调工具，先验参数。

    三种结果都走同一个形状，调用方不用写三个分支：
      成功  {"ok": True, "data": {...}}
      参数错 {"ok": False, "reason": "slot 格式不对…", "retryable": True}
      没这工具 {"ok": False, "reason": "…", "retryable": False}
    """
    fn = REGISTRY.get(name)
    if fn is None:
        return {"ok": False, "reason": f"没有叫 {name} 的工具，现有 {sorted(REGISTRY)}",
                "retryable": False}

    spec = "classroom" if name == "query_classroom" else "search"
    ok, reason = check(raw, spec)
    if not ok:
        # retryable 的意义：这句话可以原样回传给模型，让它重填，而不是让整个请求失败
        return {"ok": False, "reason": reason, "retryable": True}

    try:
        return {"ok": True, "data": fn(raw)}
    except Exception as e:                      # 工具自己炸了，不该把整轮对话带崩
        return {"ok": False, "reason": f"工具执行出错：{e}", "retryable": False}


# ------------------------------------------------------- 模型那一侧的替身
# 真接模型时，下面这两个函数的工作由模型的 function call 完成。
# v0.2 还没有循环（第 4 幕才有），先用规则凑一份参数出来：
# 这样离线也能演示「验表 → 执行 → 回填」这条链路，而且参数错了照样会被挡住。
_INTENT = ("空教室", "有空", "没人上课", "哪间教室")


def wants_tool(question: str) -> bool:
    return any(k in question for k in _INTENT)


def guess_args(question: str) -> dict:
    import re

    day = "明天" if "明天" in question else "今天"
    m = re.search(r"(\d{1,2})\s*[点:：]", question)
    hour = f"{int(m.group(1)):02d}:00" if m else "14:00"
    building = next((b for b in ("三教", "二教", "一教", "图书馆") if b in question), "三教")
    return {"day": day, "slot": hour, "building": building}
