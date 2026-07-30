from __future__ import annotations

import unittest

from knoarbor.retrieval.query_text import (
    build_lexical_query_plan,
    lexical_tokens,
    query_terms,
)


class QueryTextTests(unittest.TestCase):
    def test_query_terms_support_cjk_bigrams_and_trigrams(self) -> None:
        terms = query_terms("注意力机制")

        self.assertIn("注意力机制", terms)
        self.assertIn("注意", terms)
        self.assertIn("注意力", terms)

    def test_query_terms_filters_cjk_question_noise(self) -> None:
        terms = query_terms("Agent Loop 是什么？请基于我的知识库回答")

        self.assertIn("agent", terms)
        self.assertIn("loop", terms)
        self.assertNotIn("是什么", terms)
        self.assertNotIn("什么", terms)
        self.assertNotIn("知识库", terms)

    def test_query_plan_splits_question_scaffolding_into_concept_anchors(self) -> None:
        plan = build_lexical_query_plan("这套架构的年度预算和项目负责人是谁")

        self.assertEqual(plan.cjk_anchors, ("架构", "年度预算", "项目负责人"))
        self.assertNotIn("架构的", plan.terms)
        self.assertNotIn("负责人是", plan.terms)

    def test_explicit_chinese_title_remains_a_rankable_phrase(self) -> None:
        plan = build_lexical_query_plan("《时间简史》主要讨论哪些主题？")

        self.assertIn("时间简史", plan.terms)
        self.assertIn("主题", plan.terms)

    def test_named_scope_and_concepts_all_remain_rankable(self) -> None:
        plan = build_lexical_query_plan("OpenClaw 架构 解耦层")

        self.assertIn("openclaw", plan.terms)
        self.assertIn("架构", plan.terms)
        self.assertIn("解耦层", plan.terms)

    def test_query_plan_preserves_technical_identifier_variants(self) -> None:
        plan = build_lexical_query_plan("量子海豚协议 ZXQ-9917 的维护窗口是什么")

        self.assertIn("zxq-9917", plan.terms)
        self.assertIn("zxq", plan.terms)
        self.assertIn("9917", plan.terms)
        self.assertIn("维护窗口", plan.terms)

    def test_compact_source_identity_splits_letter_number_boundaries(self) -> None:
        tokens = lexical_tokens("rfc9110")

        self.assertIn("rfc9110", tokens)
        self.assertIn("rfc", tokens)
        self.assertIn("9110", tokens)

    def test_compound_technical_identifier_keeps_compound_and_parts(self) -> None:
        plan = build_lexical_query_plan("ABSENT-0000")

        self.assertEqual(plan.technical_anchors[0].parts, ("absent", "0000"))
        self.assertIn("absent-0000", plan.technical_anchors[0].variants)

    def test_multiple_technical_identities_remain_separate_rank_groups(self) -> None:
        plan = build_lexical_query_plan("KnoArbor 2.5.0 Git commit SHA")

        self.assertGreaterEqual(len(plan.latin_anchor_groups), 4)
        self.assertIn(("2.5.0", "2", "5", "0", "250", "2_5_0", "2-5-0"), plan.latin_anchor_groups)

    def test_acronym_qualifier_remains_rankable(self) -> None:
        plan = build_lexical_query_plan("ANN 检索中的 HNSW")

        self.assertIn("ann", plan.terms)
        self.assertIn("hnsw", plan.terms)

    def test_technical_source_identity_and_content_words_share_bm25_query(self) -> None:
        plan = build_lexical_query_plan("RFC 9110 evaluating preconditions order")

        self.assertIn("rfc", plan.terms)
        self.assertIn("9110", plan.terms)
        self.assertIn("preconditions", plan.terms)

    def test_camel_case_identifier_preserves_compound_and_parts(self) -> None:
        plan = build_lexical_query_plan("OpenClaw 架构 中介层")

        self.assertIn("openclaw", plan.terms)
        self.assertIn("open", plan.terms)
        self.assertIn("claw", plan.terms)

    def test_domain_nouns_are_not_treated_as_question_scaffolding(self) -> None:
        plan = build_lexical_query_plan("这个框架有哪些架构组件、技术方法、设置位置和主题效果？")

        for term in ("框架", "架构", "组件", "技术", "方法", "设置", "位置", "主题", "效果"):
            self.assertIn(term, plan.terms)
        self.assertNotIn("这个", plan.terms)

if __name__ == "__main__":
    unittest.main()
