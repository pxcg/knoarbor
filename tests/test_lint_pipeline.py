from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_lint import LintRunRequest, WikiLintRequest, WikiScanRequest
from knoarbor.pipelines import WikiLintPipeline
from knoarbor.runtime import RunMonitor, run_monitor_context


class WikiLintPipelineTests(unittest.TestCase):
    def test_scan_pipeline_reads_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().scan(WikiScanRequest(obsidian_vault_path=str(vault)))

        self.assertEqual(len(response.pages), 1)
        self.assertEqual(response.pages[0].path, "concepts/Agent.md")

    def test_lint_pipeline_can_render_report_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=tmp_dir,
                    write_report=False,
                )
            )

        self.assertIsNone(response.report_path)
        self.assertIn("# Lint Report", response.report_content or "")

    def test_scoped_scan_limits_pages_and_expands_related_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Related Pages\n\n- [[entities/OpenClaw]]\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )
            (vault / "entities" / "OpenClaw.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: entity\nstatus: draft\nsource: raw/notes/openclaw.md\ncontent_hash: b\n---\n"
                "# OpenClaw\n\n## Summary\n\nOpenClaw notes.\n\n## Source\n\nraw/notes/openclaw.md\n",
                encoding="utf-8",
            )

            scoped = WikiLintPipeline().scan(
                WikiScanRequest(
                    obsidian_vault_path=str(vault),
                    scope_pages=["concepts/Agent.md"],
                    include_related=True,
                )
            )
            strict = WikiLintPipeline().scan(
                WikiScanRequest(
                    obsidian_vault_path=str(vault),
                    scope_pages=["concepts/Agent.md"],
                    include_related=False,
                )
            )

        self.assertEqual({page.path for page in scoped.pages}, {"concepts/Agent.md", "entities/OpenClaw.md"})
        self.assertEqual([page.path for page in strict.pages], ["concepts/Agent.md"])
        self.assertTrue(scoped.stats["scoped"])

    def test_scan_allows_additional_source_section_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nstatus: draft\nsource: raw/chats/session.json\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Source\n\n"
                "- raw/chats/session.json\n"
                "- /Users/[REDACTED_USER]/.claude/projects/session.jsonl\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().scan(WikiScanRequest(obsidian_vault_path=str(vault)))

        self.assertNotIn("source_section_mismatch", {issue.code for issue in response.issues})

    def test_lint_reports_duplicate_list_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Tags\n\n- agent\n- Agent\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        duplicate_issues = [issue for issue in response.issues if issue.code == "duplicate_section_item"]
        self.assertEqual(len(duplicate_issues), 1)
        self.assertEqual(duplicate_issues[0].details["section"], "Tags")
        self.assertTrue(any(fix.action == "deduplicate_section_items" for fix in response.fixes))

    def test_lint_reports_adjacent_duplicate_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n### Control\n\n### Control\n\nLoop details.\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        issues = [issue for issue in response.issues if issue.code == "adjacent_duplicate_heading"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].details["heading"], "Control")
        self.assertEqual(issues[0].details["level"], 3)
        self.assertTrue(any(fix.action == "remove_adjacent_duplicate_headings" for fix in response.fixes))

    def test_lint_reports_missing_required_page_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        missing_sections = [issue.details["section"] for issue in response.issues if issue.code == "missing_required_section"]
        self.assertIn("Answer", missing_sections)
        self.assertIn("Key Points", missing_sections)
        self.assertTrue(any(fix.action == "add_missing_section" for fix in response.fixes))

    def test_lint_reports_specialized_page_contract_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "claims").mkdir()
            (vault / "timelines").mkdir()
            (vault / "workflows").mkdir()
            frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\n"
            (vault / "claims" / "Claim.md").write_text(
                frontmatter + "type: claim\n---\n# Claim\n\n## Summary\n\nOne claim.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )
            (vault / "timelines" / "Timeline.md").write_text(
                frontmatter + "type: timeline\n---\n# Timeline\n\n## Summary\n\nOnly 2026 is mentioned.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )
            (vault / "workflows" / "Workflow.md").write_text(
                frontmatter + "type: workflow\n---\n# Workflow\n\n## Summary\n\nA workflow without steps.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        codes = {issue.code for issue in response.issues}
        self.assertIn("claim_missing_evidence_section", codes)
        self.assertIn("claim_missing_confidence", codes)
        self.assertIn("timeline_missing_chronology", codes)
        self.assertIn("workflow_missing_steps", codes)

    def test_lint_reports_p2_graph_and_path_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\n"
            (vault / "concepts" / "Agent.md").write_text(
                frontmatter + "type: concept\n---\n# Agent\n\n## Summary\n\nOne isolated page.\n\n## Answer\n\nBody.\n\n## Key Points\n\n- Point\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- agent\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )
            (vault / "entities" / "Agent.md").write_text(
                frontmatter + "type: entity\ncontent_hash: b\n---\n# Agent Entity\n\n## Summary\n\nEntity page.\n\n## Answer\n\nBody.\n\n## Key Points\n\n- Point\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- agent\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )
            related_items = "\n".join(f"- [[concepts/Page{i}|Page {i}]]" for i in range(22))
            (vault / "concepts" / "Dense.md").write_text(
                frontmatter + "type: concept\ncontent_hash: c\n---\n# Dense\n\n## Summary\n\nDense page.\n\n## Answer\n\nBody.\n\n## Key Points\n\n- Point\n\n## Related Pages\n\n"
                + related_items
                + "\n\n## Tags\n\n- graph\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        codes = {issue.code for issue in response.issues}
        self.assertIn("path_alias_conflict", codes)
        self.assertIn("weak_link_graph", codes)
        self.assertIn("overdense_link_graph", codes)
        graph_health = response.stats["graph_health"]
        self.assertGreaterEqual(graph_health["component_count"], 2)
        self.assertGreaterEqual(graph_health["isolated_page_count"], 1)

    def test_lint_reports_invalid_claim_confidence_and_empty_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "claims").mkdir()
            (vault / "claims" / "Claim.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: claim\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\nconfidence: high\n---\n"
                "# Claim\n\n## Summary\n\nOne claim.\n\n## Evidence\n\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- claim\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    obsidian_vault_path=str(vault),
                    write_report=False,
                )
            )

        codes = {issue.code for issue in response.issues}
        self.assertIn("claim_missing_evidence_section", codes)
        self.assertIn("claim_invalid_confidence", codes)

    def test_run_maintenance_uses_explicit_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            monitor = RunMonitor(vault_path=vault, flow="lint", run_id="lint-report-test")
            with run_monitor_context(monitor):
                response = WikiLintPipeline().run_maintenance(
                    LintRunRequest(
                        obsidian_vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="latest_ingest:test",
                            trigger="ingest",
                            source=MaintenanceScopeSource(kind="source", source_id="test"),
                            changed_pages=["concepts/Agent.md"],
                        ),
                    )
                )

        self.assertEqual(response.schema_version, "lint_run.v1")
        self.assertTrue(response.deterministic_lint.stats["scoped"])
        self.assertEqual(response.policy_decision.mode, "deterministic")
        self.assertEqual(response.report_path, "maintenance/lint_run_report_lint-report-test.md")
        self.assertIsNotNone(response.ledger_path)

    def test_run_maintenance_can_disable_artifact_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = WikiLintPipeline().run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=tmp_dir,
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                    ),
                    write_report=False,
                    append_ledger=False,
                )
            )

            maintenance_path = Path(tmp_dir) / "maintenance"

        self.assertIsNone(response.report_path)
        self.assertIsNone(response.ledger_path)
        self.assertFalse(maintenance_path.exists())

    def test_run_maintenance_can_execute_semantic_structural_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(FakeLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                )
            )

        self.assertEqual(response.mode, "semantic_structural")
        self.assertEqual(response.semantic_candidates["summary"], "One semantic candidate.")
        self.assertEqual(response.maintenance_review["decisions"][0]["decision"], "approve")

    def test_semantic_structural_skips_model_when_scan_has_no_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "index.md").write_text("# Index\n", encoding="utf-8")

            response = WikiLintPipeline(FailingLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=[],
                    ),
                    mode="semantic_structural",
                )
            )

        self.assertEqual(response.semantic_candidates["candidates"], [])
        self.assertEqual(response.maintenance_review["decisions"], [])


    def test_run_maintenance_applies_reviewed_wiki_operations_and_rescans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )
            (vault / "entities" / "OpenClaw.md").write_text(
                "---\ntype: entity\nstatus: draft\nsource: raw/notes/openclaw.md\n---\n"
                "# OpenClaw\n\n## Summary\n\nOpenClaw notes.\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(WikiOperationLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.applied_operations[0]["action"], "attach_related_pages")
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "attach_related_pages")
        self.assertIn("[[entities/OpenClaw|OpenClaw]]", content)
        self.assertIsNotNone(response.rescan)

    def test_run_maintenance_applies_missing_section_as_wiki_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "RAG.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/rag.md\ncontent_hash: a\ntags: rag\n---\n"
                "# RAG\n\n## Summary\n\nRAG evaluation notes.\n\n## Answer\n\nBody.\n\n## Key Points\n\n- Point.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/rag.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(MissingSectionWikiOperationWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/RAG.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.applied_operations[0]["action"], "add_missing_section")
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertIn("## Tags\n\n- rag", content)
        remaining_missing_sections = [issue for issue in response.rescan.issues if issue.code == "missing_required_section"]
        self.assertEqual(remaining_missing_sections, [])

    def test_run_maintenance_requires_explicit_wiki_operation_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "sources").mkdir()
            (vault / "sources" / "Agent.md").write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "update_source_field requires source_file"):
                WikiLintPipeline(MissingSourceFileLintSemanticWorkflow()).run_maintenance(
                    LintRunRequest(
                        obsidian_vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="manual:test",
                            trigger="manual",
                            source=MaintenanceScopeSource(kind="test"),
                            changed_pages=["sources/Agent.md"],
                        ),
                        mode="semantic_structural",
                        auto_apply_reviewed_changes=True,
                    )
                )

    def test_run_maintenance_rejects_list_source_file_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "sources").mkdir()
            page = vault / "sources" / "Agent.md"
            page.write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "update_source_field requires source_file"):
                WikiLintPipeline(ListSourceFileLintSemanticWorkflow()).run_maintenance(
                    LintRunRequest(
                        obsidian_vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="manual:test",
                            trigger="manual",
                            source=MaintenanceScopeSource(kind="test"),
                            changed_pages=["sources/Agent.md"],
                        ),
                        mode="semantic_structural",
                        auto_apply_reviewed_changes=True,
                    )
                )

            self.assertNotIn("['raw/notes/agent.md'", page.read_text(encoding="utf-8"))

    def test_run_maintenance_writes_reviewed_lint_drafts_and_rescans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nOld summary.\n\n## Answer\n\nOld answer.\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(DraftWriteLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_quality",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.written_pages, ["concepts/Agent.md"])
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "improve_summary")
        self.assertIn("Improved summary.", content)
        self.assertIsNotNone(response.rescan)

    def test_run_maintenance_records_approved_queued_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "claims").mkdir()
            (vault / "claims" / "Claim.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: claim\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\n---\n"
                "# Claim\n\n## Summary\n\nOne claim.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(QueuedActionLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["claims/Claim.md"],
                    ),
                    mode="semantic_structural",
                )
            )

        self.assertEqual(len(response.queued_actions), 2)
        self.assertEqual(response.queued_actions[0]["queue_type"], "refresh_request")
        self.assertEqual(response.queued_actions[0]["expected_effect"], "Queue source refresh for missing claim evidence.")
        self.assertEqual(response.queued_actions[0]["evidence"][0]["kind"], "scan_issue")
        self.assertEqual(response.queued_actions[1]["queue_type"], "report_only")

    def test_run_maintenance_supports_deep_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = WikiLintPipeline().run_maintenance(
                LintRunRequest(
                    obsidian_vault_path=tmp_dir,
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                    ),
                    profile="deep",
                    write_report=False,
                    append_ledger=False,
                )
            )

        self.assertEqual(response.profile, "deep")

    def test_lint_run_report_records_trend_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Tags\n\n- agent\n- Agent\n\n## Source\n\nraw/notes/agent.md\n",
                encoding="utf-8",
            )
            request = LintRunRequest(
                obsidian_vault_path=str(vault),
                scope=MaintenanceScope(
                    scope_id="manual:test",
                    trigger="manual",
                    source=MaintenanceScopeSource(kind="test"),
                ),
                mode="deterministic",
            )

            WikiLintPipeline().run_maintenance(request)
            response = WikiLintPipeline().run_maintenance(request)

            report = (vault / str(response.report_path)).read_text(encoding="utf-8")

        self.assertIn("## Trend Summary", report)
        self.assertIn("- previous_runs_considered: 1", report)
        self.assertIn("persistent_issue_codes: duplicate_section_item=1", report)


class FakeLintSemanticWorkflow:
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:concepts/Agent.md:source:0",
                        "source": "structural",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "source_link",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "source"}],
                        "recommended_action": {"action": "report", "params": {}},
                        "related_pages": [],
                        "expected_effect": "Record structural observation.",
                        "review_notes": "No write required.",
                    }
                ],
                "summary": "One semantic candidate.",
                "warnings": [],
            }
        )

    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates(candidates=[], summary="No quality candidates.")

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_report_only",
                        "risk_level": "low",
                        "confidence": 0.9,
                        "reason": "Candidate is report-only and supported.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Reviewed.",
                "warnings": [],
            }
        )


class FailingLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        raise AssertionError("semantic structural diagnose should not run")


class WikiOperationLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:concepts/Agent.md:related:0",
                        "source": "structural",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "missing_links",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Related Pages"}],
                        "recommended_action": {
                            "action": "attach_related_pages",
                            "params": {"related_pages": ["entities/OpenClaw.md"]},
                        },
                        "related_pages": ["entities/OpenClaw.md"],
                        "expected_effect": "Attach explicit related page.",
                        "review_notes": "Target page exists.",
                    }
                ],
                "summary": "One wiki operation candidate.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_wiki_operation",
                        "risk_level": "low",
                        "confidence": 0.9,
                        "reason": "Attach related page is explicit and supported.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )


class MissingSectionWikiOperationWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:concepts/RAG.md:missing_required_section:0",
                        "source": "structural",
                        "target_page": "concepts/RAG.md",
                        "issue_type": "missing_required_section",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "safe",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/RAG.md", "quote": "Page is missing required concepts section: Tags."}],
                        "recommended_action": {
                            "action": "add_missing_section",
                            "params": {"section": "Tags"},
                        },
                        "related_pages": [],
                        "expected_effect": "Add required Tags section.",
                        "review_notes": "Schema-required section scaffolding only.",
                    }
                ],
                "summary": "One missing section candidate.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_wiki_operation",
                        "risk_level": "safe",
                        "confidence": 0.95,
                        "reason": "Missing required section has explicit deterministic parameters.",
                        "constraints": ["Do not add new factual claims."],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )


class MissingSourceFileLintSemanticWorkflow(WikiOperationLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:sources/Agent.md:source_section_mismatch:0",
                        "source": "provenance",
                        "target_page": "sources/Agent.md",
                        "issue_type": "source_section_mismatch",
                        "severity": "high",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "sources/Agent.md", "quote": "Source mismatch"}],
                        "recommended_action": {
                            "action": "update_source_field",
                            "params": {},
                        },
                        "related_pages": [],
                        "expected_effect": "Update source provenance.",
                        "review_notes": "This intentionally omits source_file.",
                    }
                ],
                "summary": "One invalid wiki operation candidate.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_wiki_operation",
                        "risk_level": "low",
                        "confidence": 0.9,
                        "reason": "Review approved to verify executor parameter enforcement.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )


class ListSourceFileLintSemanticWorkflow(MissingSourceFileLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:sources/Agent.md:source_section_mismatch:0",
                        "source": "provenance",
                        "target_page": "sources/Agent.md",
                        "issue_type": "source_section_mismatch",
                        "severity": "high",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "sources/Agent.md", "quote": "Source mismatch"}],
                        "recommended_action": {
                            "action": "update_source_field",
                            "params": {"source_file": ["raw/notes/agent.md", "raw/notes/other.md"]},
                        },
                        "related_pages": [],
                        "expected_effect": "Update source provenance.",
                        "review_notes": "This intentionally uses invalid list provenance.",
                    }
                ],
                "summary": "One invalid wiki operation candidate.",
                "warnings": [],
            }
        )


class DraftWriteLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:concepts/Agent.md:summary:0",
                        "source": "quality",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "poor_summary",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "page_excerpt", "ref": "concepts/Agent.md", "quote": "Old summary."}],
                        "recommended_action": {"action": "improve_summary", "params": {}},
                        "related_pages": [],
                        "expected_effect": "Improve page summary.",
                        "review_notes": "Patch Summary only.",
                    }
                ],
                "summary": "One draft write candidate.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_draft_write",
                        "risk_level": "low",
                        "confidence": 0.9,
                        "reason": "Summary patch is local and supported.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )

    def compile_drafts(self, draft_payload, *, max_tokens=None):
        return WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "update",
                        "target_page": "concepts/Agent.md",
                        "source_file": None,
                        "title": "Agent",
                        "page_dir": "concepts",
                        "question": "Improve summary",
                        "answer": "Improved answer.",
                        "summary": "Improved summary.",
                        "key_points": ["Improved summary."],
                        "tags": ["agent"],
                        "patches": [
                            {
                                "operation": "replace_section",
                                "section": "Summary",
                                "content": "Improved summary.",
                            }
                        ],
                        "confidence": 0.9,
                        "model_provider": "fake",
                        "model_name": "unit",
                    }
                ],
                "batch_summary": "One patch.",
                "warnings": [],
            }
        )


class QueuedActionLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:claims/Claim.md:claim_missing_evidence_section:0",
                        "source": "structural",
                        "target_page": "claims/Claim.md",
                        "issue_type": "claim_missing_evidence_section",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "refresh_request",
                        "evidence": [{"kind": "scan_issue", "ref": "claims/Claim.md", "quote": "Missing evidence"}],
                        "recommended_action": {
                            "action": "refresh_request",
                            "params": {"section": "Evidence", "source_file": "raw/notes/source.md"},
                        },
                        "related_pages": [],
                        "expected_effect": "Queue source refresh for missing claim evidence.",
                        "review_notes": "Do not invent evidence.",
                    },
                    {
                        "candidate_id": "structural:claims/Claim.md:claim_missing_confidence:1",
                        "source": "structural",
                        "target_page": "claims/Claim.md",
                        "issue_type": "claim_missing_confidence",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "claims/Claim.md", "quote": "Missing confidence"}],
                        "recommended_action": {
                            "action": "queue_claim_review",
                            "params": {"field": "confidence"},
                        },
                        "related_pages": [],
                        "expected_effect": "Queue claim contract review.",
                        "review_notes": "Confidence must not be guessed.",
                    },
                ],
                "summary": "Two queued candidates.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        return LintMaintenanceReview.model_validate(
            {
                "schema_version": "lint_maintenance_review.v1",
                "decisions": [
                    {
                        "operation_index": 0,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_refresh_request",
                        "risk_level": "medium",
                        "confidence": 0.9,
                        "reason": "Missing claim evidence should be refreshed from source.",
                        "constraints": [],
                        "required_followups": ["refresh raw/notes/source.md"],
                    },
                    {
                        "operation_index": 1,
                        "decision": "approve",
                        "necessity": "necessary",
                        "correctness": "correct",
                        "completeness": "complete",
                        "executor_fit": "supported_by_report_only",
                        "risk_level": "medium",
                        "confidence": 0.9,
                        "reason": "Missing confidence should be visible in report queue.",
                        "constraints": [],
                        "required_followups": [],
                    },
                ],
                "summary": "Queued.",
                "warnings": [],
            }
        )


if __name__ == "__main__":
    unittest.main()
