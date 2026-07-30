import unittest

from knoarbor.services.chat_evidence import ChatEvidencePlanner


class ChatEvidencePlannerTests(unittest.TestCase):
    def test_query_raw_evidence_is_represented_once_as_support_spans(self) -> None:
        content = "x" * 12000
        projection = ChatEvidencePlanner().project_tool_observation(
            "retrieve_knowledge_batch",
            "ok",
            "read",
            {"raw_evidence": [{"evidence_id": "ev:long", "source_unit_id": "unit:long", "content": content}]},
        )
        evidence = projection["evidence_pack"]["raw_evidence"][0]
        self.assertNotIn("content", evidence)
        self.assertNotIn("excerpt", evidence)
        self.assertEqual(
            "".join(span["text"] for span in evidence["support_spans"]),
            content,
        )

    def test_query_raw_evidence_preserves_observed_image_attachments(self) -> None:
        attachment = {
            "attachment_id": "attachment:figure",
            "attachment_type": "image",
            "name": "figure.png",
            "topic": "Ingest flow",
            "description": "The diagram shows the ingest flow.",
            "asset_path": "images/figure.png",
            "src": "/vault-assets/images%2Ffigure.png?vault_path=%2Fvault",
            "markdown_src": "![Ingest flow](/vault-assets/images%2Ffigure.png?vault_path=%2Fvault)",
            "metadata": {"extractor_payload": "must not enter the model context"},
        }
        projection = ChatEvidencePlanner().project_tool_observation(
            "retrieve_knowledge_batch",
            "ok",
            "read",
            {
                "raw_evidence": [
                    {
                        "evidence_id": "ev:image",
                        "source_unit_id": "unit:image",
                        "content": "The diagram shows the ingest flow.",
                        "attachments": [attachment],
                    }
                ]
            },
        )

        self.assertEqual(
            projection["evidence_pack"]["raw_evidence"][0]["attachments"],
            [{
                "visual_ref": "visual_1_1",
                "source_caption": "Ingest flow",
                "extracted_content": "The diagram shows the ingest flow.",
            }],
        )

    def test_locator_candidates_do_not_enter_answer_projection(self) -> None:
        projection = ChatEvidencePlanner().project_answer_observations([])
        self.assertEqual(projection, [])

    def test_answer_projection_exposes_raw_linked_attachment_semantics_by_default(self) -> None:
        from knoarbor.core.schemas.chat import ChatToolTraceItem

        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [{
                    "evidence_id": "ev:image",
                    "source_unit_id": "unit:image",
                    "content": "The diagram shows the flow.",
                    "attachments": [{
                        "attachment_id": "attachment:figure",
                        "name": "flow.png",
                        "topic": "Agent Loop",
                        "description": "Cycle of reasoning, action, and observation.",
                        "markdown_src": "![flow](/vault-assets/flow.png)",
                    }],
                }],
            },
        )

        ordinary = ChatEvidencePlanner().project_answer_observations([observation])
        model_attachment = ordinary[0]["evidence_pack"]["raw_evidence"][0][
            "source_visuals"
        ][0]
        self.assertNotIn("attachment_id", model_attachment)
        self.assertNotIn("name", model_attachment)
        self.assertEqual(
            model_attachment,
            {
                "visual_ref": "visual_1_1",
                "source_caption": "Agent Loop",
                "extracted_content": "Cycle of reasoning, action, and observation.",
            },
        )

    def test_answer_projection_omits_raw_image_markdown_path(self) -> None:
        from knoarbor.core.schemas.chat import ChatToolTraceItem

        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [{
                    "evidence_id": "ev:image",
                    "source_unit_id": "unit:image",
                    "content": (
                        "The diagram shows the flow.\n\n"
                        "![](../assets/images/flow.png)\n\n"
                        "Figure 1. Agent Loop."
                    ),
                    "attachments": [{
                        "topic": "Figure 1. Agent Loop",
                        "description": "Reasoning, action, and observation.",
                        "markdown_src": "![Figure 1](/vault-assets/flow.png)",
                    }],
                }],
            },
        )

        projection = ChatEvidencePlanner().project_answer_observations(
            [observation]
        )
        raw_projection = projection[0]["evidence_pack"]["raw_evidence"][0]
        support_text = "\n".join(
            item["text"] for item in raw_projection["support_spans"]
        )

        self.assertNotIn("../assets/images/flow.png", support_text)
        self.assertEqual(
            raw_projection["source_visuals"][0]["visual_ref"],
            "visual_1_1",
        )

    def test_answer_projection_omits_filenames_without_source_semantics(self) -> None:
        from knoarbor.core.schemas.chat import ChatToolTraceItem

        raw_evidence = [{
            "evidence_id": "ev:image",
            "source_unit_id": "unit:image",
            "content": "Relevant source text.",
            "attachments": [
                {
                    "attachment_id": "attachment:opaque",
                    "attachment_type": "image",
                    "name": "report-0123456789abcdef0123456789abcdef.png",
                    "markdown_src": "![opaque](/vault-assets/opaque.png)",
                },
                {
                    "attachment_id": "attachment:named",
                    "attachment_type": "image",
                    "name": "risk-framework.png",
                    "markdown_src": "![risk framework](/vault-assets/risk-framework.png)",
                },
            ],
        }]
        projection = ChatEvidencePlanner().project_tool_observation(
            "retrieve_knowledge_batch",
            "ok",
            "read",
            {"raw_evidence": raw_evidence},
        )

        self.assertEqual(
            projection["evidence_pack"]["raw_evidence"][0]["attachments"],
            [],
        )
        prepared = ChatEvidencePlanner().prepare_answer_evidence([
            ChatToolTraceItem(
                tool="retrieve_knowledge_batch",
                result={"raw_evidence": raw_evidence},
            )
        ])
        self.assertEqual(
            prepared.source_visuals,
            {},
        )

    def test_answer_projection_avoids_duplicate_caption_content(self) -> None:
        from knoarbor.core.schemas.chat import ChatToolTraceItem

        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [{
                    "evidence_id": "ev:image",
                    "source_unit_id": "unit:image",
                    "content": "Figure 2 shows the architecture.",
                    "attachments": [{
                        "name": "generated-hash.png",
                        "topic": "Figure 2. System architecture",
                        "description": "Figure 2. System architecture",
                    }],
                }],
            },
        )

        projection = ChatEvidencePlanner().project_answer_observations(
            [observation]
        )

        self.assertEqual(
            projection[0]["evidence_pack"]["raw_evidence"][0][
                "source_visuals"
            ],
            [{"source_caption": "Figure 2. System architecture"}],
        )

    def test_answer_projection_keeps_caption_only_and_content_only_visuals(
        self,
    ) -> None:
        from knoarbor.core.schemas.chat import ChatToolTraceItem

        observation = ChatToolTraceItem(
            tool="retrieve_knowledge_batch",
            result={
                "raw_evidence": [{
                    "evidence_id": "ev:image",
                    "source_unit_id": "unit:image",
                    "content": "Two source figures.",
                    "attachments": [
                        {
                            "topic": "Figure 1. Architecture",
                            "markdown_src": "![Figure 1](/assets/figure-1.png)",
                        },
                        {
                            "description": "OCR content from the second figure.",
                            "markdown_src": "![Figure 2](/assets/figure-2.png)",
                        },
                    ],
                }],
            },
        )

        projection = ChatEvidencePlanner().project_answer_observations(
            [observation]
        )

        self.assertEqual(
            projection[0]["evidence_pack"]["raw_evidence"][0][
                "source_visuals"
            ],
            [
                {
                    "visual_ref": "visual_1_1",
                    "source_caption": "Figure 1. Architecture",
                },
                {
                    "visual_ref": "visual_1_2",
                    "extracted_content": (
                        "OCR content from the second figure."
                    ),
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
