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
                            canonical_path="pages/Agent Loop.md",
                            question="Agent loop",
                            summary="Agent loop is a repeated control pattern.",
                            claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
                            entities=["[[Agent Loop]]"],
                            relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
                            evidence=["C1 | raw/notes/agent.md | section:Agent Loop | source states the loop cycle | high"],
                            synthesis="Agent loop repeats observe, decide, act, and feedback.",
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
            self.assertTrue((vault / ".knoarbor" / "index" / "manifest.json").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "graph_index.json").exists())
            self.assertEqual(response.results[0].stats["directory"], "concepts")
            self.assertEqual(response.results[0].stats["canonical_path"], "Agent-Loop.md")
            self.assertEqual(
                response.results[0].stats["legacy_paths"],
                ["pages/Agent Loop.md", "Agent Loop.md", "concepts/Agent-Loop.md"],
            )
            self.assertEqual(response.results[0].stats["page_kind"], "concept")
            self.assertEqual(response.results[0].stats["role"], "knowledge_page")
            self.assertIn("created:", content)
            self.assertIn("updated:", content)
            self.assertIn("content_hash:", content)
            self.assertNotIn("canonical_path:", content)
            self.assertNotIn("legacy_paths:", content)
            self.assertNotIn("page_kind:", content)
            self.assertNotIn("role:", content)

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
                            summary="A wiki method.",
                            claims=["C1: [[LLM Wiki]] precompiles durable knowledge."],
                            entities=["[[LLM Wiki]]"],
                            relations=["[[LLM Wiki]] | precompiles | [[Durable Knowledge]] | C1"],
                            evidence=["C1 | raw/notes/wiki.md | section:LLM Wiki | source states the method | high"],
                            synthesis="Use [[concepts]] carefully and link [[LLM Wiki Source]] only when it exists.",
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
            self.assertEqual(response.stats["unresolved_wikilinks_sanitized_count"], 3)

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
                            summary="Claude Code is a coding assistant.",
                            claims=["C1: [[Claude Code]] is a coding assistant."],
                            entities=["[[Claude Code]]"],
                            relations=["[[Claude Code]] | is_a | [[Coding Assistant]] | C1"],
                            evidence=["C1 | /Users/[REDACTED_USER]/.claude/projects/session.jsonl | session:summary | source identifies Claude Code | high"],
                            synthesis="Claude Code is a coding assistant.",
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
            (vault / "pages").mkdir()
            (vault / "pages" / "Tool-Use.md").write_text("# Tool Use\n", encoding="utf-8")
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
                            summary="Agent loop is a control pattern.",
                            claims=["C1: [[Agent Loop]] repeats reasoning and tool use."],
                            entities=["[[Agent Loop]]"],
                            relations=["[[Agent Loop]] | repeats | [[Tool Use]] | C1"],
                            evidence=["C1 | sd_agent_loop | unit:0 | atom trace supports the loop cycle | high"],
                            synthesis="Agent loop repeats reasoning and tool use.",
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

            self.assertNotIn("source_digest_ids:", content)
            self.assertNotIn("atom_ids:", content)
            self.assertNotIn("## Definition", content)
            self.assertIn("## Claims", content)
            self.assertIn("- C1: [[Agent Loop]] repeats reasoning and tool use.", content)
            self.assertIn("## Entities", content)
            self.assertIn("## Relations", content)
            self.assertIn("| [[Agent Loop]] | repeats | [[Tool Use]] | C1 |", content)
            self.assertIn("## Evidence", content)
            self.assertIn("| C1 | sd_agent_loop | unit:0 | atom trace supports the loop cycle | high |", content)
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
                            summary="Agent Loop is a control pattern.",
                            claims=[
                                "Agent Loop differs from workflow because runtime model decisions can choose the next step.",
                                "Production Agent Loop requires observability and error recovery.",
                            ],
                            relations=[
                                "Agent Loop | contrasts_with | Workflow | C1",
                                "Agent Loop | depends_on | Tool Execution | C2",
                            ],
                            evidence=[
                                "C1 | raw/notes/agent.md | section:Workflow | source contrasts runtime decisions with workflow | high",
                                "C2 | raw/notes/agent.md | section:Production | source names observability and recovery | high",
                            ],
                            synthesis="Agent Loop should be read as a dynamic control layer rather than a static workflow.",
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

        self.assertNotIn("## Source Focus", content)
        self.assertNotIn("## Definition", content)
        self.assertIn("- C1: Agent Loop differs from workflow", content)
        self.assertIn("| Agent Loop | contrasts_with | Workflow | C1 |", content)
        self.assertIn("## Synthesis\n\nAgent Loop should be read as a dynamic control layer", content)

    def test_write_pipeline_rejects_evidence_for_missing_claim(self) -> None:
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
                            summary="Agent Loop is a control pattern.",
                            claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
                            entities=["[[Agent Loop]]"],
                            relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
                            evidence=[
                                "C1 | raw/notes/agent.md | unit:0 | source states the loop cycle | high",
                                "C2 | raw/notes/agent.md | unit:1 | orphan evidence row | high",
                            ],
                            synthesis="Agent Loop repeats observe, decide, act, and feedback.",
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            with self.assertRaisesRegex(Exception, "evidence references missing claims: C2"):
                WikiWritePipeline().run(request)

            self.assertFalse((vault / "pages" / "Agent-Loop.md").exists())

    def test_write_pipeline_rewrites_current_structured_page_on_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            existing = vault / "pages" / "Agent-Loop.md"
            existing.parent.mkdir(parents=True)
            existing.write_text(
                "---\ncreated: 2026-01-01 00:00:00\nupdated: 2026-01-01 00:00:00\ncontent_hash: old\n---\n\n"
                "# Agent Loop\n\n"
                "## Summary\n\nOld summary.\n\n"
                "## Claims\n\n- C1: Old claim.\n\n"
                "## Entities\n\n- [[Agent Loop]]\n\n"
                "## Relations\n\n| Subject | Predicate | Object | Based on |\n|---|---|---|---|\n"
                "| [[Agent Loop]] | repeats | [[Control Cycle]] | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n"
                "| C1 | raw/old.md | unit:0 | old basis | high |\n\n"
                "## Synthesis\n\nOld synthesis.\n",
                encoding="utf-8",
            )
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        write_action="update",
                        target_page="Agent-Loop.md",
                        source_file="raw/notes/agent.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent Loop",
                            page_dir="concepts",
                            question="Agent Loop",
                            summary="Updated summary.",
                            claims=[
                                "C1: [[Agent Loop]] repeats observe, decide, act, and feedback.",
                                "C2: Production loops require observability.",
                            ],
                            entities=["[[Agent Loop]]", "[[Observability]]"],
                            relations=[
                                "[[Agent Loop]] | repeats | [[Control Cycle]] | C1",
                                "[[Agent Loop]] | requires | [[Observability]] | C2",
                            ],
                            evidence=[
                                "C1 | raw/notes/agent.md | unit:0 | source states the loop cycle | high",
                                "C2 | raw/notes/agent.md | unit:1 | source states observability requirement | high",
                            ],
                            synthesis="Updated synthesis.",
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

        self.assertIn("- C2: Production loops require observability.", content)
        self.assertIn("| C2 | raw/notes/agent.md | unit:1 | source states observability requirement | high |", content)
        self.assertNotIn("Old summary", content)

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
                            synthesis="Source digest.",
                            summary="Source digest.",
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

            self.assertEqual(output_path.resolve().relative_to(vault.resolve()).as_posix(), "pages/sources/LLM-Wiki-Source.md")
            self.assertEqual(output_path.name, "LLM-Wiki-Source.md")
            self.assertIn("# LLM-Wiki Source", content)
            self.assertIn("## Source Identity", content)
            self.assertIn("## Audit Summary", content)
            self.assertIn("## Source Units", content)
            self.assertIn("## Contribution Map", content)
            self.assertIn("## Unresolved / Rejected", content)
            self.assertIn("## Raw Source", content)
            self.assertNotIn("## Claims", content)
            self.assertNotIn("## Entities", content)
            self.assertNotIn("## Relations", content)
            self.assertNotIn("## Evidence", content)
            self.assertNotIn("## Synthesis", content)
            self.assertNotIn("page_kind: source_digest", content)
            self.assertNotIn("role: source_digest", content)
            self.assertEqual(response.results[0].stats["page_kind"], "source_digest")
            self.assertEqual(response.results[0].stats["role"], "source_digest")

    def test_write_pipeline_rewrites_legacy_source_digest_on_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            legacy = vault / "pages" / "sources" / "A2A-Source.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# A2A Source\n\n"
                "---\ncreated: 2026-01-01 00:00:00\nupdated: 2026-01-01 00:00:00\ncontent_hash: old\n---\n\n"
                "## Summary\n\nOld source summary.\n\n## Answer\n\nOld source body.\n",
                encoding="utf-8",
            )
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        write_action="update",
                        target_page="sources/A2A-Source.md",
                        source_file="raw/notes/A2A.md",
                        wiki_draft=WikiDraftInput(
                            title="A2A Source",
                            page_dir="sources",
                            question="A2A",
                            summary="Structured audit summary.",
                            claims=["C1: A2A defines multi-agent interaction."],
                            relations=["A2A | defines | Multi-agent interaction | C1"],
                            evidence=["U1 | raw/notes/A2A.md | unit:0 | A2A definition | high"],
                            synthesis="Structured audit summary.",
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

            self.assertTrue(content.startswith("---\ncreated:"))
            self.assertIn("## Source Identity", content)
            self.assertIn("## Audit Summary", content)
            self.assertIn("## Source Units", content)
            self.assertIn("## Contribution Map", content)
            self.assertIn("## Raw Source", content)
            self.assertNotIn("## Answer", content)
            self.assertNotIn("Old source body", content)

    def test_write_pipeline_rewrites_legacy_knowledge_page_on_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            legacy = vault / "pages" / "concepts" / "Agent-to-Agent-Interaction.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# Agent-to-Agent Interaction\n\n"
                "---\ncreated: 2026-01-01 00:00:00\nupdated: 2026-01-01 00:00:00\ncontent_hash: old\n---\n\n"
                "## Summary\n\nOld summary.\n\n## Answer\n\nOld answer.\n\n## Tags\n\n- old\n",
                encoding="utf-8",
            )
            request = WikiDraftBatchWriteRequest(
                vault_path=str(vault),
                auto_related_links=False,
                drafts=[
                    WikiDraftBatchWriteItem(
                        write_action="update",
                        target_page="concepts/Agent-to-Agent-Interaction.md",
                        source_file="raw/notes/A2A.md",
                        wiki_draft=WikiDraftInput(
                            title="Agent-to-Agent Interaction",
                            page_dir="concepts",
                            question="A2A",
                            summary="A2A enables multiple AI agents to collaborate.",
                            claims=["C1: [[A2A]] enables collaboration among multiple [[AI Agent]] systems."],
                            entities=["[[A2A]]", "[[AI Agent]]"],
                            relations=["[[A2A]] | enables | [[AI Agent Collaboration]] | C1"],
                            evidence=["C1 | sources/A2A-Source.md | unit:0 | source defines A2A collaboration | high"],
                            synthesis="A2A should be read as a protocol-level collaboration pattern for agents.",
                            confidence=0.8,
                            model_provider="test",
                            model_name="unit",
                        ),
                    )
                ],
            )

            response = WikiWritePipeline().run(request)
            content = Path(response.results[0].wiki_file_path).read_text(encoding="utf-8")

            self.assertTrue(content.startswith("---\ncreated:"))
            self.assertIn("## Claims", content)
            self.assertIn("## Entities", content)
            self.assertIn("## Relations", content)
            self.assertIn("## Evidence", content)
            self.assertIn("## Synthesis", content)
            self.assertNotIn("## Answer", content)
            self.assertNotIn("## Tags", content)
            self.assertIn("A2A enables collaboration", content)

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
                            summary="Agent loop is a control pattern.",
                            claims=["C1: [[Agent Loop]] repeats observe and act."],
                            entities=["[[Agent Loop]]"],
                            relations=["[[Agent Loop]] | repeats | [[Control Cycle]] | C1"],
                            evidence=["C1 | raw/notes/agent.md | section:Agent Loop | source states observe and act | high"],
                            synthesis="Agent loop repeats observe and act.",
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
