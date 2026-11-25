"""每一版都带单测。第一版是为了「后面每一版都要靠它」，第二版是因为
上面多了三个东西（装填、校验、路由），每一个都有自己的边界。

跑：cd campus-agent && python -m unittest discover -s tests -v

这些测试不联网：走的都是离线后端和本地数据，所以你在没网的自习室也能跑。
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import knowledge, schemas, tools  # noqa: E402
from agent.context import OUTPUT_RESERVE, plan  # noqa: E402
from agent.llm import count_tokens  # noqa: E402
from agent.main import build_messages  # noqa: E402
from agent.router import MODELS, classify, price, route  # noqa: E402


class TestMessages(unittest.TestCase):
    def test_first_is_system_last_mentions_question(self):
        msgs = build_messages("一卡通丢了去哪补办")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("校园助手", msgs[0]["content"])
        self.assertIn("一卡通丢了去哪补办", msgs[-1]["content"])

    def test_never_exceeds_budget(self):
        """37 条资料 + 48 条历史，装完必须在预算内。超了就是第一版那个事故。"""
        filled = plan("转专业什么时候能申请？")
        self.assertLessEqual(filled["used"], 4096 - OUTPUT_RESERVE)

    def test_relevant_doc_wins_a_seat(self):
        """「装三条」不等于「装对三条」：问转专业，转专业那条必须在里面。"""
        labels = [d["label"] for d in plan("转专业什么时候能申请？")["docs"]]
        self.assertTrue(any("转专业" in x for x in labels), labels)

    def test_question_is_verbatim_last(self):
        q = "图书馆明天几点关门？"
        self.assertEqual(build_messages(q)[-1]["content"], q)

    def test_rules_file_is_the_system_prompt(self):
        """系统提示来自 data/rules.md，不是在代码里另写一份。"""
        rules = (ROOT / "data" / "rules.md").read_text(encoding="utf-8").strip()
        self.assertEqual(build_messages("x")[0]["content"].strip(), rules)


class TestKnowledge(unittest.TestCase):
    def test_finds_by_word_overlap(self):
        hits = knowledge.search("一卡通丢了怎么办", k=3)
        self.assertTrue(hits, "一条都没找到，说明打分或数据出了问题")
        self.assertIn("一卡通", hits[0]["label"])

    def test_empty_question_finds_nothing(self):
        self.assertEqual(knowledge.search("", k=3), [])

    def test_day_filter_excludes_later_docs(self):
        """图书馆那条是第 3 天才抄的：按第 1 天的口径找，它不该出现。

        注意不能断言「结果为空」——按字面重合打分时，「图书馆几点关门」
        会误命中「图书借阅规则」，那是这种土办法的正常表现，也是第 5 幕
        要换掉它的理由。
        """
        day1 = knowledge.search("图书馆几点关门", k=5, day=1)
        ids = [d["id"] for d in day1]
        self.assertNotIn("kb0", ids)


class TestSchemas(unittest.TestCase):
    def test_accepts_a_good_payload(self):
        ok, why = schemas.check({"query": " 一卡通 ", "top_k": 5, "mode": "fast"})
        self.assertTrue(ok, why)

    def test_string_number_is_not_a_number(self):
        ok, why = schemas.check({"query": "x", "top_k": "5", "mode": "fast"})
        self.assertFalse(ok)
        self.assertIn("top_k", why)

    def test_bool_is_not_an_int(self):
        """Python 里 True 是 int 的子类，不单独挡就会当成 1 放进来。"""
        self.assertFalse(schemas.check({"query": "x", "top_k": True, "mode": "fast"})[0])

    def test_unknown_key_is_rejected(self):
        ok, why = schemas.check({"query": "x", "top_k": 5, "mode": "fast", "sql": "drop"})
        self.assertFalse(ok)
        self.assertIn("sql", why)


class TestTools(unittest.TestCase):
    def test_good_args_reach_the_tool(self):
        res = tools.call("query_classroom", {"day": "明天", "slot": "14:00", "building": "三教"})
        self.assertTrue(res["ok"], res)
        self.assertIn("free", res["data"])

    def test_bad_slot_is_stopped_before_the_tool(self):
        res = tools.call("query_classroom", {"day": "明天", "slot": "25:00", "building": "三教"})
        self.assertFalse(res["ok"])
        self.assertTrue(res["retryable"], "参数错应该能重填，不该整轮失败")
        self.assertIn("slot", res["reason"])


class TestRouter(unittest.TestCase):
    def test_never_exceeds_the_budget(self):
        for level in (1, 2, 3):
            task = {"level": level, "max_cost": 0.01, "max_p95": 3000, "need_json": False}
            name = route(task)["model"]
            m = next(x for x in MODELS if x["name"] == name)
            self.assertLessEqual(m["cost"], task["max_cost"])

    def test_picks_the_cheapest_that_fits(self):
        task = {"level": 1, "max_cost": 1.0, "max_p95": 9999, "need_json": False}
        self.assertEqual(route(task)["model"], "mini")

    def test_says_degraded_when_nothing_fits(self):
        task = {"level": 1, "max_cost": 0.0001, "max_p95": 50, "need_json": False}
        out = route(task)
        self.assertTrue(out.get("degraded"), "一个都不满足时要标出来，不能装作正常")

    def test_price_grows_with_tokens(self):
        self.assertGreater(price("mini", 1000, 200), 0)
        self.assertGreater(price("reason", 1000, 200), price("mini", 1000, 200))


class TestOffline(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ("AGENT_GATEWAY", "OPENAI_API_KEY")}

    def tearDown(self):
        for k, v in self._env.items():
            if v is not None:
                os.environ[k] = v

    def test_offline_does_not_pretend_to_be_a_model(self):
        from agent.llm import chat
        r = chat(build_messages("一卡通丢了去哪补办"), "一卡通丢了去哪补办")
        self.assertEqual(r.backend, "offline")
        self.assertIn("不是模型回答", r.text)
        self.assertGreater(r.out_tokens, 0)


class TestTokens(unittest.TestCase):
    def test_count_is_positive_and_monotonic(self):
        a = count_tokens("你好")
        b = count_tokens("你好，" * 10)
        self.assertGreater(a, 0)
        self.assertGreater(b, a)


if __name__ == "__main__":
    unittest.main()
