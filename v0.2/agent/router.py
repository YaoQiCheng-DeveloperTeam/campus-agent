"""router.py — 这句问题，该让哪个模型答

第 2 幕之前所有问题都走同一个模型，包括「图书馆几点关门」这种一句话能答的。
全班 40 个人一天问两百句，账单一拉，八成花在根本不需要那么聪明的调用上。

这一版的规矩：先判断这题的难度和约束，再挑「够用里最便宜」的那个；
一个都满足不了，就降档并在结果上标 degraded —— 让调用方知道这题没答满。

路由写在代码里，不写在提示词里。提示词管不了「这次调用花多少钱」。

价格单位是「元 / 千 token」，是把公开报价按汇率粗略换算后的量级，
不是让你拿去报销的数 —— 真实价格以你用的那家为准，改了记得同步 MODELS。
"""
from __future__ import annotations

# max_level：这个模型能扛到第几级难度（1 最简单）
# p95：95% 的请求能在多少毫秒内返回
MODELS = [
    {"name": "mini", "cost": 0.001, "p95": 800, "json": True, "max_level": 2},
    {"name": "standard", "cost": 0.008, "p95": 2000, "json": True, "max_level": 3},
    {"name": "reason", "cost": 0.06, "p95": 8000, "json": True, "max_level": 3},
]

BY_NAME = {m["name"]: m for m in MODELS}

# 输出比输入贵，按 3 倍粗算，够用来比较两条路线谁更省
OUT_WEIGHT = 3


def classify(question: str) -> dict:
    """给问题分个级。

    真正该做的事是拿评测集学一个分类器（第 8 幕）；在那之前，
    用三条肉眼可见的规则就够，而且学生自己能解释每一级为什么。
    """
    q = question.strip()
    n = len(q)

    hard = any(k in q for k in ("为什么", "对比", "规划", "帮我", "报修", "怎么办", "流程"))
    multi = q.count("？") + q.count("?") > 1

    if hard or multi or n >= 30:
        level = 3
    elif n <= 12:
        level = 1
    else:
        level = 2

    # 数字题、要填表的题必须给够预算：省下来的钱不够赔一次答错
    return {
        "level": level,
        "max_cost": 0.010,
        "max_p95": 3000,
        "need_json": any(k in q for k in ("空教室", "有几个", "多少", "课表")),
    }


def affordable(m: dict, task: dict) -> bool:
    return (task["level"] <= m["max_level"]
            and m["cost"] <= task["max_cost"]
            and m["p95"] <= task["max_p95"]
            and (m["json"] or not task["need_json"]))


def route(task: dict) -> dict:
    """挑一个模型。同一批可行模型里选成本最低的 —— 一律上强模型也能跑，
    但那是别人一百倍的钱，而且并不会让「图书馆几点关门」答得更对。
    """
    ok = [m for m in MODELS if affordable(m, task)]
    if ok:
        return {"model": min(ok, key=lambda m: m["cost"])["name"]}

    # 一个都不满足：降档跑最便宜的那个，并且把「这次没答满」写在结果里，
    # 让上层能对它特殊处理（提示用户，或者记一条指标）
    return {"model": min(MODELS, key=lambda m: m["cost"])["name"], "degraded": True}


def price(model: str, in_tokens: int, out_tokens: int) -> float:
    """这一次调用花了多少钱（元）。日志里那一列就是这个数。"""
    m = BY_NAME.get(model)
    if m is None:
        return 0.0
    return (in_tokens + OUT_WEIGHT * out_tokens) / 1000 * m["cost"]


def explain(task: dict, picked: dict) -> str:
    m = BY_NAME[picked["model"]]
    tag = "（降档）" if picked.get("degraded") else ""
    return (f"难度 {task['level']} · 预算 {task['max_cost']} 元/千token · "
            f"p95≤{task['max_p95']}ms" + (" · 要 JSON" if task["need_json"] else "") +
            f" → {m['name']}{tag}（{m['cost']} 元/千token，p95 {m['p95']}ms）")
