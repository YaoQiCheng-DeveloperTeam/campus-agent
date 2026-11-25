"""第一版就带单测，不是因为第一版需要，是因为后面每一版都要靠它。

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

from agent import knowledge  # noqa: E402
from agent.llm import count_tokens  # noqa: E402
from agent.main import build_messages  # noqa: E402


class TestMessages(unittest.TestCase):
    def test_first_is_system_last_mentions_question(self):
        msgs = build_messages("一卡通丢了去哪补办")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("校园助手", msgs[0]["content"])
        self.assertIn("一卡通丢了去哪补办", msgs[-1]["content"])

    def test_first_day_only_six_docs(self):
        """第一版只装第 1 天抄的 6 条。这个数字变了，说明装填逻辑被人动过。"""
        msgs = build_messages("随便问问")
        self.assertEqual(msgs[1]["content"].count("【校内资料】"), 6)

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
