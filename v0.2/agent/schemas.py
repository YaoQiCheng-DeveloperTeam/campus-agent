"""schemas.py — 模型吐出来的参数，先过这道门

工具的参数不是「大概齐」就行：把 "5" 当整数用，数据库那边不认；
让 top_k 变成 500，一次查询能把整张表捞回来；多一个没定义的字段，
下游要么报错要么静默忽略 —— 后者更难查。

所以模型只负责「填表」，能不能用由这里的 check() 说了算。
这一套写死了三件事：
  1. 类型不对 → 拒绝（不做隐式转换，"5" 不是 5）
  2. 超范围 → 拒绝，并且说清范围是多少
  3. 多了没定义的键 → 拒绝。宁可让它重填一次，也不要猜它想干什么
"""
from __future__ import annotations

# 搜索参数：第 5 幕真检索要用，现在先当契约练手
SEARCH = {
    "query": {"type": str, "min_len": 1, "max_len": 200, "required": True, "strip": True},
    "top_k": {"type": int, "min": 1, "max": 20, "required": True},
    "mode": {"type": str, "choices": ("fast", "deep"), "required": True},
    "filters": {"type": dict, "keys": ("lang", "year"), "required": False},
}

# 空教室查询：这一版真会用到的那个工具
CLASSROOM = {
    "day": {"type": str, "choices": ("今天", "明天"), "required": True},
    "slot": {"type": str, "pattern": r"^([01]\d|2[0-3]):00$", "required": True},
    "building": {"type": str, "min_len": 1, "max_len": 20, "required": True, "strip": True},
}

SPECS = {"search": SEARCH, "classroom": CLASSROOM}


def _bad_type(value, want: type) -> bool:
    """bool 是 int 的子类，True 会被当成 1 混进来，这种要单独挡掉。"""
    if want is int:
        return isinstance(value, bool) or not isinstance(value, int)
    return not isinstance(value, want)


def check(raw, spec: str = "search") -> tuple[bool, str]:
    """返回 (能不能用, 不能用的原因)。

    原因要说清是**哪个字段**、**合法范围是什么** —— 这句话会被原样回传给模型，
    让它重填。只说「参数错误」，模型下一轮还会错在同一个地方。
    """
    rules = SPECS[spec] if isinstance(spec, str) else spec

    if not isinstance(raw, dict):
        return False, f"参数必须是一个对象，收到的是 {type(raw).__name__}"

    unknown = [k for k in raw if k not in rules]
    if unknown:
        return False, f"不认识的字段 {unknown}，只接受 {sorted(rules)}"

    for field, rule in rules.items():
        if field not in raw:
            if rule.get("required", True):
                return False, f"缺少字段 {field}"
            continue

        value = raw[field]
        want = rule["type"]
        if _bad_type(value, want):
            return False, f"{field} 应该是 {want.__name__}，收到的是 {type(value).__name__}"

        if want is str:
            text = value.strip() if rule.get("strip") else value
            lo, hi = rule.get("min_len"), rule.get("max_len")
            if lo is not None and len(text) < lo:
                return False, f"{field} 不能为空" if lo == 1 else f"{field} 至少 {lo} 个字"
            if hi is not None and len(text) > hi:
                return False, f"{field} 最多 {hi} 个字，现在是 {len(text)}"
            if "choices" in rule and text not in rule["choices"]:
                return False, f"{field} 只能是 {' / '.join(rule['choices'])}，收到 {text!r}"
            if "pattern" in rule:
                import re
                if not re.match(rule["pattern"], text):
                    return False, f"{field} 格式不对，要像 14:00 这样，收到 {text!r}"

        if want is int:
            lo, hi = rule.get("min"), rule.get("max")
            if lo is not None and value < lo:
                return False, f"{field} 最小 {lo}，收到 {value}"
            if hi is not None and value > hi:
                return False, f"{field} 最大 {hi}，收到 {value}"

        if want is dict and "keys" in rule:
            extra = [k for k in value if k not in rule["keys"]]
            if extra:
                return False, f"{field} 里不认识的键 {extra}，只能是 {list(rule['keys'])}"

    return True, ""
