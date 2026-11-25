"""llm.py — 怎么跟模型说一句话

第一版只要三件事：把 messages 发出去、把回答拿回来、记下这次花了多少 token。
没有重试、没有超时、没有并发——这些是后面几幕的事，先让它跑起来。

三种后端，按顺序找：
  1. AGENT_GATEWAY  平台的模型网关（学生不用自己买 key，课程内推荐）
  2. OPENAI_API_KEY 任何 OpenAI 兼容接口，配合 OPENAI_BASE_URL 用
  3. offline        都没有时走占位实现：不冒充模型，只把最像的那条资料原文贴出来
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Reply:
    text: str
    backend: str
    in_tokens: int = 0
    out_tokens: int = 0


# ---------------------------------------------------------------- token 计数
def count_tokens(text: str) -> int:
    """优先用真分词器；没装就按「一个汉字一个 token、四个字母一个」估。

    估算会偏差 10–20%，所以日志里要标清楚是估的还是真的——
    后面算钱的时候，这两个数不能混着用。
    """
    try:
        import tiktoken
    except ImportError:
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        other = len(text) - cjk
        return cjk + max(1, other // 4)
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _post(url: str, payload: dict, headers: dict, timeout: float = 40) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _as_prompt(messages: list[dict]) -> str:
    """网关只收一段 prompt，把 messages 摊平。

    这一层是给平台网关用的，不是通用做法：真接 OpenAI 兼容接口时
    messages 原样发过去，模型能分清谁说的。
    """
    out = []
    for m in messages:
        role = {"system": "系统", "user": "用户", "assistant": "助手"}.get(m["role"], m["role"])
        out.append(f"【{role}】\n{m['content']}")
    return "\n\n".join(out)


# ------------------------------------------------------------------- 后端
def _via_gateway(messages: list[dict], gateway: str) -> Reply:
    data = _post(gateway.rstrip("/"), {"prompt": _as_prompt(messages)}, {})
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "网关没返回内容")
    text = str(data.get("text") or "")
    return Reply(text=text, backend="gateway",
                 in_tokens=count_tokens(_as_prompt(messages)),
                 out_tokens=count_tokens(text))


def _via_openai(messages: list[dict]) -> Reply:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("AGENT_MODEL", "gpt-4o-mini")
    data = _post(f"{base}/chat/completions",
                 {"model": model, "messages": messages, "temperature": 0.2},
                 {"Authorization": f"Bearer {key}"})
    choice = (data.get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    usage = data.get("usage") or {}
    return Reply(text=text, backend=f"openai:{model}",
                 in_tokens=int(usage.get("prompt_tokens") or count_tokens(_as_prompt(messages))),
                 out_tokens=int(usage.get("completion_tokens") or count_tokens(text)))


def _offline(messages: list[dict], question: str = "") -> Reply:
    """没有模型时的占位：把最像的一条资料原文贴出来。

    它不会回答问题，只会抄书——所以输出必须自己声明「这不是模型回答」，
    免得有人拿它当效果。第一版就挂在这里，第 5 幕才真的有检索。

    question 必须由调用方传进来，不能从 messages 里猜：messages 最后一条
    是「资料 + 同学问：xxx」拼成的一整段，拿它去检索等于用资料搜资料，
    问什么都能命中——第一版就踩过这个坑，问「附近哪家火锅好吃」它答了一卡通。
    """
    from .knowledge import search

    # 只从第一版装进去的那 6 条里找，口径跟 main.build_messages 保持一致
    hits = search(question, k=1, day=1) if question else []
    if not hits:
        body = "（离线模式）资料里没找到相关条目。配一个模型再问一次，或者去问宿管。"
    else:
        d = hits[0]
        body = (f"（离线模式 · 这不是模型回答，只是把资料原文贴出来）\n"
                f"{d['label']}：{d['text']}\n[{d['src']}]")
    return Reply(text=body, backend="offline",
                 in_tokens=count_tokens(_as_prompt(messages)),
                 out_tokens=count_tokens(body))


def chat(messages: list[dict], question: str = "") -> Reply:
    """发一次对话。找不到任何后端时走离线占位，不抛异常。"""
    gateway = os.environ.get("AGENT_GATEWAY", "").strip()
    if gateway:
        try:
            return _via_gateway(messages, gateway)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            # 网关挂了不该让整个 CLI 崩：退回离线，把原因写在回答里
            r = _offline(messages, question)
            r.text = f"（模型网关连不上：{e}）\n\n{r.text}"
            r.backend = "offline"
            return r
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return _via_openai(messages)
    return _offline(messages, question)
