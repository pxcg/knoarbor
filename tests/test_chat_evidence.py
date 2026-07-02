import unittest

from knoarbor.services.chat_evidence import ChatEvidencePlanner


class ChatEvidencePlannerTests(unittest.TestCase):
    def test_architecture_query_adds_answer_type_policy_and_role_rationale(self) -> None:
        pack = ChatEvidencePlanner().build_search_pack(
            query="如果要把它做成生产级系统，需要补哪些工程模块？",
            result_count=2,
            answer_scope={"kind": "broad"},
            answer_set={"kind": "multi_page"},
            evidence_coverage={"status": "strong", "primary_count": 1, "supporting_count": 1, "source_count": 0},
            primary_page={
                "path": "Agent-Infrastructure.md",
                "title": "Agent Infrastructure",
                "type": "concept",
                "summary": "Infrastructure page.",
                "content": "Architecture content.",
            },
            primary_pages=[
                {
                    "path": "Agent-Infrastructure.md",
                    "title": "Agent Infrastructure",
                    "type": "concept",
                    "summary": "Infrastructure page.",
                    "content": "Architecture content.",
                }
            ],
            supporting_pages=[
                {
                    "path": "Session-Memory.md",
                    "title": "Session Memory",
                    "type": "concept",
                    "summary": "Memory page.",
                    "content": "Memory content.",
                }
            ],
            source_pages=[],
            results=[],
            warnings=[],
        ).payload

        self.assertEqual(pack["answer_type"], "architecture")
        self.assertIn("answer_contract", pack["evidence_policy"])
        self.assertIn("Primary architecture material", pack["primary_pages"][0]["role_rationale"])
        self.assertIn("Supporting maintained page", pack["supporting_pages"][0]["role_rationale"])
        self.assertTrue(any("architecture thesis" in item for item in pack["synthesis_outline"]))

    def test_comparison_query_sets_comparison_outline(self) -> None:
        pack = ChatEvidencePlanner().build_search_pack(
            query="Agent Loop 和 Workflow 有什么区别？",
            result_count=1,
            answer_scope={"kind": "narrow"},
            answer_set={"kind": "single_page"},
            evidence_coverage={"status": "strong", "primary_count": 1, "supporting_count": 0, "source_count": 0},
            primary_page={
                "path": "Agent-Loop.md",
                "title": "Agent Loop",
                "type": "concept",
                "summary": "Agent Loop page.",
                "content": "Agent Loop content.",
            },
            primary_pages=[],
            supporting_pages=[],
            source_pages=[],
            results=[],
            warnings=[],
        ).payload

        self.assertEqual(pack["answer_type"], "comparison")
        self.assertTrue(any("central distinction" in item for item in pack["synthesis_outline"]))

    def test_preserves_renderable_attachments_in_primary_page(self) -> None:
        pack = ChatEvidencePlanner().build_search_pack(
            query="AC1 的 FOV 图片说明什么？",
            result_count=1,
            answer_scope={"kind": "narrow"},
            answer_set={"kind": "single_page"},
            evidence_coverage={"status": "strong", "primary_count": 1, "supporting_count": 0, "source_count": 0},
            primary_page={
                "path": "pages/AC1.md",
                "title": "AC1",
                "type": "page",
                "summary": "AC1 page.",
                "content": "AC1 content.",
                "attachments": [
                    {
                        "topic": "图2 AC1 激光雷达 FOV 分布图",
                        "description": "FOV rendering.",
                        "markdown_src": "raw/derived/assets/images/ac1-fov.jpg",
                    }
                ],
            },
            primary_pages=[],
            supporting_pages=[],
            source_pages=[],
            results=[],
            warnings=[],
        ).payload

        attachments = pack["primary_pages"][0]["attachments"]
        self.assertEqual(attachments[0]["markdown_src"], "raw/derived/assets/images/ac1-fov.jpg")


if __name__ == "__main__":
    unittest.main()
