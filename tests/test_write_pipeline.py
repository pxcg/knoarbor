from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftBatchWriteRequest, WikiDraftInput
from knoarbor.pipelines import WikiWritePipeline


class WikiWritePipelineTests(unittest.TestCase):
    def test_write_pipeline_creates_page_and_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/agent.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent Loop",
                            page_dir="concepts",
                            question="Agent loop",
                            answer="Agent loop repeats observe, decide, act, and feedback.",
                            summary="Agent loop is a repeated control pattern.",
                            key_points=["Observe and act in a loop."],
                            tags=["agent", "loop"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            output_path = Path(response.results[0].wiki_file_path)
            content = output_path.read_text(encoding="utf-8")

            self.assertEqual(response.stats["written_count"], 1)
            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.resolve().relative_to((vault / "pages").resolve()).as_posix(), "Agent-Loop.md")
            self.assertTrue((vault / "pages" / "index.md").exists())
            self.assertEqual(response.results[0].stats["directory"], "concepts")
            self.assertEqual(response.results[0].stats["canonical_path"], "Agent-Loop.md")
            self.assertEqual(response.results[0].stats["legacy_paths"], ["concepts/Agent-Loop.md"])
            self.assertEqual(response.results[0].stats["page_kind"], "concept")
            self.assertEqual(response.results[0].stats["role"], "knowledge_page")
            self.assertIn("canonical_path: Agent-Loop.md", content)
            self.assertIn('legacy_paths: ["concepts/Agent-Loop.md"]', content)
            self.assertIn("page_kind: concept", content)
            self.assertIn("role: knowledge_page", content)

    def test_write_pipeline_sanitizes_unresolved_wikilinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/wiki.md",
                        wiki_draft=WikiDraftInput(
                            title="LLM Wiki",
                            page_dir="concepts",
                            question="LLM Wiki",
                            answer="Use [[concepts]] carefully and link [[LLM Wiki Source]] only when it exists.",
                            summary="A wiki method.",
                            key_points=["Precompile durable knowledge."],
                            tags=["wiki"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

            self.assertIn("concepts carefully", content)
            self.assertNotIn("[[concepts]]", content)
            self.assertIn("unresolved_wikilinks_sanitized", response.results[0].stats)
            self.assertEqual(response.stats["unresolved_wikilinks_sanitized_count"], 2)

    def test_write_pipeline_can_display_redacted_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="/Users/alice/.claude/projects/session.jsonl",
                        display_source_file="/Users/[REDACTED_USER]/.claude/projects/session.jsonl",
                        wiki_draft=WikiDraftInput(
                            title="Claude Code",
                            page_dir="entities",
                            question="Claude Code",
                            answer="Claude Code is a coding assistant.",
                            summary="Claude Code is a coding assistant.",
                            key_points=["It records coding sessions."],
                            tags=["claude-code"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

            self.assertNotIn("/Users/alice", content)
            self.assertIn("/Users/[REDACTED_USER]/.claude/projects/session.jsonl", content)
            self.assertEqual(response.results[0].stats["source_file"], "/Users/alice/.claude/projects/session.jsonl")

    def test_write_pipeline_persists_atom_trace_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/agent.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent Loop",
                            page_dir="concepts",
                            question="Agent Loop",
                            answer="Agent loop repeats reasoning and tool use.",
                            summary="Agent loop is a control pattern.",
                            key_points=["Reason and act."],
                            tags=["agent"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                            source_digest_ids=["sd_agent_loop"],
                            atom_ids=["fact_agent_loop_cycle", "claim_agent_loop_boundary"],
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

            self.assertIn('source_digest_ids: ["sd_agent_loop"]', content)
            self.assertIn('atom_ids: ["fact_agent_loop_cycle", "claim_agent_loop_boundary"]', content)
            self.assertIn("## Definition", content)
            self.assertIn("## Claims", content)
            self.assertIn("- Reason and act.", content)
            self.assertIn("## Relations", content)
            self.assertIn("- 暂无显式关系", content)
            self.assertIn("## Synthesis", content)
            self.assertNotIn("## Answer", content)

    def test_write_pipeline_renders_evidence_page_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/agent.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent Loop",
                            page_dir="concepts",
                            question="Agent Loop source notes",
                            answer="Agent Loop is a loop for model-driven tool use.",
                            summary="Agent Loop is a control pattern.",
                            definition="Agent Loop is a control loop that alternates model reasoning, tool action, and observation.",
                            claims=[
                                "Agent Loop differs from workflow because runtime model decisions can choose the next step.",
                                "Production Agent Loop requires observability and error recovery.",
                            ],
                            relations=[
                                "Agent Loop contrasts Workflow",
                                "Agent Loop depends_on Tool Execution",
                            ],
                            synthesis="Agent Loop should be read as a dynamic control layer rather than a static workflow.",
                            key_points=["Dynamic control loop."],
                            tags=["agent", "loop"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

        self.assertIn("## Source Focus\n\nAgent Loop source notes", content)
        self.assertIn("## Definition\n\nAgent Loop is a control loop", content)
        self.assertIn("- Agent Loop differs from workflow", content)
        self.assertIn("- Agent Loop contrasts Workflow", content)
        self.assertIn("## Synthesis\n\nAgent Loop should be read as a dynamic control layer", content)

    def test_write_pipeline_scopes_source_digest_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/LLM-Wiki.md",
                        wiki_draft=WikiDraftInput(
                            title="LLM-Wiki.md",
                            page_dir="sources",
                            question="LLM-Wiki.md",
                            answer="Source digest.",
                            summary="Source digest.",
                            key_points=["Source provenance."],
                            tags=["source"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            output_path = Path(response.results[0].wiki_file_path)
            content = output_path.read_text(encoding="utf-8")

            self.assertEqual(output_path.resolve().relative_to((vault / "pages").resolve()).as_posix(), "sources/LLM-Wiki-Source.md")
            self.assertEqual(output_path.name, "LLM-Wiki-Source.md")
            self.assertIn("# LLM-Wiki Source", content)
            self.assertIn("page_kind: source_digest", content)
            self.assertIn("role: source_digest", content)

    def test_write_pipeline_surfaces_index_update_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        source_file="raw/notes/agent.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent Loop",
                            page_dir="concepts",
                            question="Agent loop",
                            answer="Agent loop repeats observe and act.",
                            summary="Agent loop is a control pattern.",
                            key_points=["Observe and act."],
                            tags=["agent"],
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            with patch("knoarbor.pipelines.write.update_index", side_effect=RuntimeError("index failed")):
                with self.assertRaisesRegex(RuntimeError, "index failed"):
                    WikiWritePipeline().run(request)

            self.assertTrue((vault / "pages" / "Agent-Loop.md").exists())
            self.assertFalse((vault / "pages" / "index.md").exists())


if __name__ == "__main__":
    unittest.main()
