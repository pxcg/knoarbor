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
from knoarbor.core.schemas.wiki_lint import LintRunRequest, WikiLintIssue, WikiLintRequest, WikiScanPage, WikiScanRequest, WikiScanResponse
from knoarbor.maintenance.lint_candidates import score_lint_candidate
from knoarbor.pipelines import WikiLintPipeline
from knoarbor.pipelines.lint import _merge_candidates, _structural_diagnose_payload
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

            response = WikiLintPipeline().scan(WikiScanRequest(vault_path=str(vault)))

        self.assertEqual(len(response.pages), 1)
        self.assertEqual(response.pages[0].path, "concepts/Agent.md")

    def test_lint_pipeline_can_render_report_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=tmp_dir,
                    write_report=False,
                )
            )

        self.assertIsNone(response.report_path)
        self.assertIn("# Lint Report", response.report_content or "")

    def test_lint_pipeline_applies_safe_deterministic_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "---\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\n### Loop\n\n### Loop\n\nDetails.\n\n"
                "## Tags\n\n- agent\n- agent\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                    apply_safe_fixes=True,
                )
            )
            content = page.read_text(encoding="utf-8")

        self.assertEqual(content.count("### Loop"), 1)
        self.assertEqual(content.count("- agent"), 1)
        self.assertTrue(any(fix.mode == "auto_applied" and fix.action == "remove_adjacent_duplicate_headings" for fix in response.fixes))
        self.assertTrue(any(fix.mode == "auto_applied" and fix.action == "deduplicate_section_items" for fix in response.fixes))

    def test_structural_diagnose_payload_excludes_deterministic_and_quality_issues(self) -> None:
        scan = WikiScanResponse(
            pages=[
                WikiScanPage(
                    path="workflows/Deploy.md",
                    directory="workflows",
                    title="Deploy",
                    page_type="workflow",
                    headings=["Summary", "Answer", "Related Pages", "Tags", "Source"],
                ),
                WikiScanPage(
                    path="sources/Agent.md",
                    directory="sources",
                    title="Agent",
                    page_type="source",
                    headings=["Summary", "Source"],
                ),
                WikiScanPage(
                    path="concepts/Agent.md",
                    directory="concepts",
                    title="Agent",
                    page_type="concept",
                    headings=["Summary", "Answer", "Source"],
                ),
            ],
            issues=[
                WikiLintIssue(
                    code="workflow_missing_steps",
                    severity="info",
                    path="workflows/Deploy.md",
                    message="Workflow page does not expose an ordered or step-oriented procedure.",
                ),
                WikiLintIssue(
                    code="privacy_sensitive_content",
                    severity="warning",
                    path="sources/Agent.md",
                    message="Page contains text that matches configured privacy redaction patterns.",
                ),
                WikiLintIssue(
                    code="broken_wikilink",
                    severity="error",
                    path="concepts/Agent.md",
                    message="Wiki link target does not exist.",
                ),
                WikiLintIssue(
                    code="knowledge_without_source_digest",
                    severity="info",
                    path="concepts/Agent.md",
                    message="Generated knowledge page points to a raw source without a matching source digest page.",
                ),
            ],
            fixes=[],
            stats={"issue_count": 4},
        )

        payload = _structural_diagnose_payload(scan)
        issues = payload["scan"]["issues"]
        pages = payload["scan"]["pages"]

        self.assertEqual([issue["code"] for issue in issues], ["knowledge_without_source_digest"])
        self.assertEqual([page["path"] for page in pages], ["concepts/Agent.md"])

    def test_quality_candidate_scoring_prioritizes_quality_issues(self) -> None:
        workflow = score_lint_candidate(
            WikiScanPage(
                path="workflows/Deploy.md",
                directory="workflows",
                title="Deploy",
                page_type="workflow",
                updated="2026-05-01",
                content_preview="Deploy workflow.",
                original_content_length=1500,
            ),
            [
                WikiLintIssue(
                    code="workflow_missing_steps",
                    severity="info",
                    path="workflows/Deploy.md",
                    message="Workflow page does not expose an ordered or step-oriented procedure.",
                )
            ],
            "quality",
        )
        provenance_only = score_lint_candidate(
            WikiScanPage(
                path="concepts/Agent.md",
                directory="concepts",
                title="Agent",
                page_type="concept",
                updated="2026-05-01",
                content_preview="Agent notes.",
                original_content_length=1500,
            ),
            [
                WikiLintIssue(
                    code="knowledge_without_source_digest",
                    severity="info",
                    path="concepts/Agent.md",
                    message="Generated knowledge page points to a raw source without a matching source digest page.",
                )
            ],
            "quality",
        )

        self.assertGreater(workflow.score, provenance_only.score)

    def test_quality_candidate_scoring_ignores_deterministic_only_issues(self) -> None:
        candidate = score_lint_candidate(
            WikiScanPage(
                path="concepts/Agent.md",
                directory="concepts",
                title="Agent",
                page_type="concept",
                updated="2026-05-01",
                summary="Agent notes.",
                headings=["Summary", "Key Points", "Related Pages", "Source"],
                outgoing_links=["entities/OpenClaw.md"],
                content_preview="Stable agent notes without temporal claims.",
                original_content_length=1500,
            ),
            [
                WikiLintIssue(
                    code="broken_wikilink",
                    severity="error",
                    path="concepts/Agent.md",
                    message="Wiki link target does not exist.",
                )
            ],
            "quality",
        )

        self.assertEqual(candidate.score, 0)
        self.assertEqual(candidate.reasons, [])

    def test_merge_candidates_deduplicates_same_operation_identity(self) -> None:
        seed = MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:workflows/Deploy.md:workflow_missing_steps:seed",
                        "source": "quality",
                        "target_page": "workflows/Deploy.md",
                        "issue_type": "workflow_missing_steps",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "scan_issue", "ref": "workflows/Deploy.md", "quote": "Missing Steps"}],
                        "recommended_action": {"action": "rewrite_section", "params": {"section": "Steps"}},
                        "related_pages": [],
                        "expected_effect": "Rewrite Steps.",
                        "review_notes": "Seeded workflow repair.",
                    }
                ],
                "summary": "Seed.",
                "warnings": [],
            }
        )
        model = MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:workflows/Deploy.md:workflow_missing_steps:0",
                        "source": "quality",
                        "target_page": "workflows/Deploy.md",
                        "issue_type": "workflow_missing_steps",
                        "severity": "medium",
                        "confidence": 0.8,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "page_excerpt", "ref": "workflows/Deploy.md", "quote": "Validate, test, deploy."}],
                        "recommended_action": {"action": "rewrite_section", "params": {"section": "Steps"}},
                        "related_pages": [],
                        "expected_effect": "Rewrite Steps.",
                        "review_notes": "Model workflow repair.",
                    }
                ],
                "summary": "Model.",
                "warnings": [],
            }
        )

        merged = _merge_candidates(seed, model)

        self.assertEqual(len(merged.candidates), 1)
        self.assertEqual(merged.candidates[0].candidate_id, "quality:workflows/Deploy.md:workflow_missing_steps:seed")

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
                    vault_path=str(vault),
                    scope_pages=["concepts/Agent.md"],
                    include_related=True,
                )
            )
            strict = WikiLintPipeline().scan(
                WikiScanRequest(
                    vault_path=str(vault),
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

            response = WikiLintPipeline().scan(WikiScanRequest(vault_path=str(vault)))

        self.assertNotIn("source_section_mismatch", {issue.code for issue in response.issues})

    def test_scan_reports_sensitive_generated_page_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "sources").mkdir()
            (vault / "sources" / "Agent.md").write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nToken sk-abcdefghijklmnop1234567890 and app cli_aa9f1cd454399bc8.\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().scan(WikiScanRequest(vault_path=str(vault)))

        issues = [issue for issue in response.issues if issue.code == "privacy_sensitive_content"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "error")
        self.assertEqual(issues[0].details["redaction_counts"]["api_keys"], 1)
        self.assertEqual(issues[0].details["redaction_counts"]["platform_ids"], 1)

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
                    vault_path=str(vault),
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
                    vault_path=str(vault),
                    write_report=False,
                )
            )

        issues = [issue for issue in response.issues if issue.code == "adjacent_duplicate_heading"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].details["heading"], "Control")
        self.assertEqual(issues[0].details["level"], 3)
        self.assertTrue(any(fix.action == "remove_adjacent_duplicate_headings" for fix in response.fixes))

    def test_lint_reports_unclosed_fenced_code_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "workflows").mkdir()
            (vault / "workflows" / "Deploy.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: workflow\nstatus: draft\nsource: raw/notes/deploy.md\ncontent_hash: a\n---\n"
                "# Deploy\n\n## Summary\n\nDeploy notes.\n\n## Steps\n\n```bash\necho deploy\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                )
            )

        issues = [issue for issue in response.issues if issue.code == "unclosed_fenced_code_block"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "error")

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
                    vault_path=str(vault),
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
            (vault / "timelines").mkdir()
            (vault / "workflows").mkdir()
            frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\n"
            (vault / "timelines" / "Timeline.md").write_text(
                frontmatter + "type: timeline\n---\n# Timeline\n\n## Summary\n\nOnly 2026 is mentioned.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )
            (vault / "workflows" / "Workflow.md").write_text(
                frontmatter
                + "type: workflow\n---\n# Workflow\n\n## Summary\n\nA workflow without steps.\n\n## Steps\n\n- 暂无内容\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                )
            )

        codes = {issue.code for issue in response.issues}
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
                    vault_path=str(vault),
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
                        vault_path=str(vault),
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
                    vault_path=tmp_dir,
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
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                    auto_retry_deferred_actions=False,
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
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=[],
                    ),
                    mode="semantic_structural",
                    auto_retry_deferred_actions=False,
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
                    vault_path=str(vault),
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
            (vault / "sources").mkdir()
            page = vault / "concepts" / "RAG.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/rag.md\ncontent_hash: a\ntags: rag\n---\n"
                "# RAG\n\n## Summary\n\nRAG evaluation notes.\n\n## Answer\n\nBody.\n\n## Key Points\n\n- Point.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/rag.md\n",
                encoding="utf-8",
            )
            (vault / "sources" / "RAG.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: source\nstatus: draft\nsource: raw/notes/rag.md\ncontent_hash: source-rag\n---\n"
                "# RAG Source\n\n## Summary\n\nRAG source digest.\n\n## Source\n\n- raw/notes/rag.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(MissingSectionWikiOperationWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
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
            (vault / "concepts").mkdir()
            (vault / "sources" / "Agent.md").write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )
            (vault / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "update_source_field requires source_file"):
                WikiLintPipeline(MissingSourceFileLintSemanticWorkflow()).run_maintenance(
                    LintRunRequest(
                        vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="manual:test",
                            trigger="manual",
                            source=MaintenanceScopeSource(kind="test"),
                            changed_pages=["sources/Agent.md", "concepts/Agent.md"],
                        ),
                        mode="semantic_structural",
                        auto_apply_reviewed_changes=True,
                    )
                )

    def test_run_maintenance_rejects_list_source_file_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "sources").mkdir()
            (vault / "concepts").mkdir()
            page = vault / "sources" / "Agent.md"
            page.write_text(
                "---\ntype: source\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )
            (vault / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "update_source_field requires source_file"):
                WikiLintPipeline(ListSourceFileLintSemanticWorkflow()).run_maintenance(
                    LintRunRequest(
                        vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="manual:test",
                            trigger="manual",
                            source=MaintenanceScopeSource(kind="test"),
                            changed_pages=["sources/Agent.md", "concepts/Agent.md"],
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
                    vault_path=str(vault),
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

    def test_quality_lint_rewrites_workflow_steps_as_local_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "workflows").mkdir()
            page = vault / "workflows" / "Deploy.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: workflow\nstatus: draft\nsource: raw/notes/deploy.md\ncontent_hash: a\n---\n"
                "# Deploy\n\n## Summary\n\nBuild and deploy the app after validating configuration.\n\n"
                "## Answer\n\nValidate configuration, run tests, build artifacts, then deploy.\n\n"
                "## Steps\n\n- 暂无内容\n\n## Source\n\n- raw/notes/deploy.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(SeededWorkflowStepsDraftWriteLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["workflows/Deploy.md"],
                    ),
                    mode="semantic_quality",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.written_pages, ["workflows/Deploy.md"])
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "rewrite_section")
        self.assertIn("1. Validate configuration", content)
        self.assertIn("2. Run tests", content)
        self.assertNotIn("暂无内容", content)
        self.assertIsNotNone(response.rescan)

    def test_run_maintenance_does_not_compile_source_digest_from_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "raw" / "notes").mkdir(parents=True)
            (vault / "raw" / "notes" / "agent.md").write_text("# Agent source\n", encoding="utf-8")
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(UnsupportedCreateSourceDigestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
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

            source_pages = sorted((vault / "sources").glob("*.md")) if (vault / "sources").exists() else []

        self.assertEqual(response.written_pages, [])
        self.assertEqual(source_pages, [])
        self.assertIsNone(response.draft_batch)

    def test_run_maintenance_records_approved_queued_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/source.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nOne concept.\n\n## Source\n\n- raw/notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(QueuedActionLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                    auto_retry_deferred_actions=False,
                )
            )

        self.assertEqual(len(response.queued_actions), 2)
        self.assertEqual(response.queued_actions[0]["queue_type"], "refresh_request")
        self.assertEqual(response.queued_actions[0]["expected_effect"], "Queue source refresh for missing provenance.")
        self.assertEqual(response.queued_actions[0]["evidence"][0]["kind"], "scan_issue")
        self.assertEqual(response.queued_actions[1]["queue_type"], "report_only")

    def test_run_maintenance_executes_refresh_request_for_missing_source_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "raw" / "notes").mkdir(parents=True)
            (vault / "concepts").mkdir()
            (vault / "raw" / "notes" / "agent.md").write_text("# Agent raw\n\nAgent loop source.", encoding="utf-8")
            target = vault / "concepts" / "Agent.md"
            target.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Answer\n\nAgent loop answer.\n\n## Key Points\n\n- Agent loop.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- agent\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(RefreshRequestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=False,
                )
            )
            source_pages = sorted((vault / "sources").glob("*.md"))
            source_content = source_pages[0].read_text(encoding="utf-8")
            target_content = target.read_text(encoding="utf-8")

        self.assertEqual(len(source_pages), 1)
        self.assertIn("sources/", response.written_pages[0])
        self.assertTrue(any(operation["action"] == "create_source_digest" for operation in response.applied_operations))
        self.assertTrue(any(operation["action"] == "attach_source_digest" for operation in response.applied_operations))
        self.assertIn("- raw/notes/agent.md", source_content)
        self.assertIn("[[concepts/Agent|Agent]]", source_content)
        self.assertIn("[[sources/", target_content)
        self.assertIsNotNone(response.rescan)
        self.assertNotIn("knowledge_without_source_digest", {issue.code for issue in response.rescan.issues})

    def test_run_maintenance_executes_refresh_request_with_existing_source_digest_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "sources").mkdir()
            target = vault / "concepts" / "Agent.md"
            target.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Answer\n\nAgent loop answer.\n\n## Key Points\n\n- Agent loop.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- agent\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )
            digest = vault / "sources" / "Agent-Source.md"
            digest.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: source\nstatus: draft\nsource: /Users/example/Documents/agent.md\ncontent_hash: s\n---\n"
                "# Agent Source\n\n## Summary\n\nSource digest.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- /Users/example/Documents/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(RefreshRequestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=False,
                )
            )
            source_pages = sorted((vault / "sources").glob("*.md"))
            source_content = digest.read_text(encoding="utf-8")
            target_content = target.read_text(encoding="utf-8")

        self.assertEqual(len(source_pages), 1)
        self.assertFalse(response.written_pages)
        self.assertTrue(any(operation["action"] == "attach_source_digest" for operation in response.applied_operations))
        self.assertIn("[[concepts/Agent|Agent]]", source_content)
        self.assertIn("[[sources/Agent-Source|Agent Source]]", target_content)

    def test_run_maintenance_executes_safe_graph_repair_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            target = vault / "concepts" / "JSON-RPC.md"
            target.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/mcp.md\ncontent_hash: a\n---\n"
                "# JSON RPC\n\n## Summary\n\nJSON RPC protocol for MCP tools.\n\n## Answer\n\nJSON RPC is used by MCP tool servers.\n\n## Key Points\n\n- MCP transport.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Tags\n\n- mcp\n\n## Source\n\n- raw/notes/mcp.md\n",
                encoding="utf-8",
            )
            related = vault / "concepts" / "MCP.md"
            related.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/mcp.md\ncontent_hash: b\n---\n"
                "# MCP\n\n## Summary\n\nModel Context Protocol and JSON RPC tool transport.\n\n## Related Pages\n\n- 暂无关联知识\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(GraphRepairWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/JSON-RPC.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=False,
                )
            )
            target_content = target.read_text(encoding="utf-8")

        self.assertEqual(response.queued_actions[0]["queue_type"], "graph_repair")
        self.assertTrue(any(operation["action"] == "attach_related_pages" for operation in response.applied_operations))
        self.assertIn("[[concepts/MCP|MCP]]", target_content)

    def test_run_maintenance_retries_report_only_queue_with_enriched_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent-a.md\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Answer\n\nPrimary notes.\n\n## Key Points\n\n- Agent loop.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent-a.md\n",
                encoding="utf-8",
            )
            (vault / "concepts" / "Agent-Duplicate.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ntype: concept\nstatus: draft\nsource: raw/notes/agent-b.md\ncontent_hash: b\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop duplicate notes.\n\n## Answer\n\nDuplicate notes.\n\n## Key Points\n\n- Agent loop.\n\n## Related Pages\n\n- 暂无关联知识\n\n## Source\n\n- raw/notes/agent-b.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(DeferredMergeRetryWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["concepts/Agent.md", "concepts/Agent-Duplicate.md"],
                    ),
                    mode="semantic_structural",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=True,
                )
            )
            merged_content = (vault / "concepts" / "Agent.md").read_text(encoding="utf-8")
            archived = list((vault / "maintenance" / "merged_pages").glob("*Agent-Duplicate.md"))

        self.assertEqual(len(response.deferred_retries), 1)
        self.assertEqual(response.applied_operations[-1]["action"], "merge_pages")
        self.assertIn("## Merged Notes", merged_content)
        self.assertEqual(len(archived), 1)

    def test_run_maintenance_supports_deep_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            response = WikiLintPipeline().run_maintenance(
                LintRunRequest(
                    vault_path=tmp_dir,
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
                vault_path=str(vault),
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
        self.assertRegex(report, r"- previous_runs_considered: [1-9]\d*")
        self.assertIn("persistent_issue_codes:", report)
        self.assertIn("missing_required_section=3", report)


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


class DeferredMergeRetryWorkflow(FakeLintSemanticWorkflow):
    def __init__(self) -> None:
        self.diagnose_calls = 0

    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        self.diagnose_calls += 1
        if self.diagnose_calls == 1:
            return MaintenanceCandidates.model_validate(
                {
                    "schema_version": "maintenance_candidates.v1",
                    "candidates": [
                        {
                            "candidate_id": "structural:concepts/Agent.md:duplicate_title:0",
                            "source": "structural",
                            "target_page": "concepts/Agent.md",
                            "issue_type": "duplicate_title",
                            "severity": "low",
                            "confidence": 0.7,
                            "risk_hint": "medium",
                            "executor_hint": "report_only",
                            "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Multiple pages share title"}],
                            "recommended_action": {
                                "action": "queue_merge_candidate",
                                "params": {"pages": ["concepts/Agent.md", "concepts/Agent-Duplicate.md"]},
                            },
                            "related_pages": ["concepts/Agent-Duplicate.md"],
                            "expected_effect": "Retry with page content before merging.",
                            "review_notes": "Needs enriched context.",
                        }
                    ],
                    "summary": "Queue merge candidate.",
                    "warnings": [],
                }
            )
        pages = {page["path"]: page for page in scan_payload["scan"]["pages"]}
        assert "content_preview" in pages["concepts/Agent.md"]
        assert "concepts/Agent-Duplicate.md" in pages
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:concepts/Agent.md:merge_pages:retry",
                        "source": "structural",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "duplicate_title",
                        "severity": "medium",
                        "confidence": 0.92,
                        "risk_hint": "medium",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "page_excerpt", "ref": "concepts/Agent-Duplicate.md", "quote": "Agent loop duplicate notes"}],
                        "recommended_action": {
                            "action": "merge_pages",
                            "params": {"source_pages": ["concepts/Agent-Duplicate.md"], "archive_sources": True},
                        },
                        "related_pages": ["concepts/Agent-Duplicate.md"],
                        "expected_effect": "Merge duplicate Agent concept pages.",
                        "review_notes": "Both pages describe the same knowledge object.",
                    }
                ],
                "summary": "Retry produced merge operation.",
                "warnings": [],
            }
        )

    def review(self, review_payload, *, max_tokens=None):
        candidate = review_payload["items"][0]
        executor_fit = "supported_by_wiki_operation" if candidate["recommended_action"]["action"] == "merge_pages" else "supported_by_report_only"
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
                        "executor_fit": executor_fit,
                        "risk_level": "medium",
                        "confidence": 0.9,
                        "reason": "Approved for the selected executor.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )


class WorkflowStepsDraftWriteLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:workflows/Deploy.md:workflow_missing_steps:0",
                        "source": "quality",
                        "target_page": "workflows/Deploy.md",
                        "issue_type": "workflow_missing_steps",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [
                            {
                                "kind": "page_excerpt",
                                "ref": "workflows/Deploy.md",
                                "quote": "Validate configuration, run tests, build artifacts, then deploy.",
                            }
                        ],
                        "recommended_action": {
                            "action": "rewrite_section",
                            "params": {"section": "Steps"},
                        },
                        "related_pages": [],
                        "expected_effect": "Replace placeholder workflow steps with actionable ordered steps.",
                        "review_notes": "Patch only the Steps section.",
                    }
                ],
                "summary": "One workflow steps candidate.",
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
                        "reason": "Steps patch is local and supported.",
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
                        "target_page": "workflows/Deploy.md",
                        "source_file": None,
                        "title": "Deploy",
                        "page_dir": "workflows",
                        "question": "Rewrite workflow steps",
                        "answer": "Replace placeholder steps with ordered steps.",
                        "summary": "Workflow steps rewritten.",
                        "key_points": ["Validate configuration.", "Run tests.", "Build and deploy."],
                        "tags": ["workflow"],
                        "patches": [
                            {
                                "operation": "replace_section",
                                "section": "Steps",
                                "content": "1. Validate configuration.\n2. Run tests.\n3. Build artifacts.\n4. Deploy the validated build.",
                            }
                        ],
                        "confidence": 0.9,
                        "model_provider": "fake",
                        "model_name": "unit",
                    }
                ],
                "batch_summary": "One workflow patch.",
                "warnings": [],
            }
        )


class SeededWorkflowStepsDraftWriteLintSemanticWorkflow(WorkflowStepsDraftWriteLintSemanticWorkflow):
    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates(candidates=[], page_reviews=[], summary="Model did not emit candidates.")


class UnsupportedCreateSourceDigestWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:concepts/Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "create_source_digest",
                            "params": {"source_file": "raw/notes/agent.md"},
                        },
                        "related_pages": ["concepts/Agent.md"],
                        "expected_effect": "Create missing source digest.",
                        "review_notes": "This intentionally models an unsupported lint draft action.",
                    }
                ],
                "summary": "One unsupported draft write candidate.",
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
                        "reason": "Approved to verify execution router boundary.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved.",
                "warnings": [],
            }
        )

    def compile_drafts(self, draft_payload, *, max_tokens=None):
        raise AssertionError("lint must not compile create_source_digest draft actions")


class QueuedActionLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:concepts/Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "refresh_request",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "refresh_request",
                            "params": {"section": "Evidence", "source_file": "raw/notes/source.md"},
                        },
                        "related_pages": [],
                        "expected_effect": "Queue source refresh for missing provenance.",
                        "review_notes": "Refresh must use the raw source.",
                    },
                    {
                        "candidate_id": "graph:concepts/Agent.md:weak_link_graph:1",
                        "source": "graph",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "weak_link_graph",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Weak graph"}],
                        "recommended_action": {
                            "action": "queue_graph_review",
                            "params": {"reason": "weak graph"},
                        },
                        "related_pages": [],
                        "expected_effect": "Queue graph review.",
                        "review_notes": "Graph repair needs review.",
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
                        "reason": "Missing provenance should be refreshed from source.",
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
                        "reason": "Weak graph should be visible in report queue.",
                        "constraints": [],
                        "required_followups": [],
                    },
                ],
                "summary": "Queued.",
                "warnings": [],
            }
        )


class RefreshRequestWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:concepts/Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "concepts/Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "low",
                        "executor_hint": "refresh_request",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "refresh_request",
                            "params": {"source_file": "raw/notes/agent.md"},
                        },
                        "related_pages": [],
                        "expected_effect": "Create source digest and attach provenance links.",
                        "review_notes": "Raw source exists and target page is explicit.",
                    }
                ],
                "summary": "One refresh request.",
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
                        "risk_level": "low",
                        "confidence": 0.95,
                        "reason": "The raw source exists and provenance refresh is deterministic.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved refresh.",
                "warnings": [],
            }
        )


class GraphRepairWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "graph:concepts/JSON-RPC.md:weak_link_graph:0",
                        "source": "graph",
                        "target_page": "concepts/JSON-RPC.md",
                        "issue_type": "weak_link_graph",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "safe",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "concepts/JSON-RPC.md", "quote": "No links"}],
                        "recommended_action": {
                            "action": "queue_graph_review",
                            "params": {},
                        },
                        "related_pages": ["concepts/MCP.md"],
                        "expected_effect": "Attach related pages to integrate the page into the graph.",
                        "review_notes": "Only related-page links are changed.",
                    }
                ],
                "summary": "One graph repair candidate.",
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
                        "executor_fit": "supported_by_report_only",
                        "risk_level": "safe",
                        "confidence": 0.9,
                        "reason": "Weak graph page can be safely repaired by attaching explicit related pages.",
                        "constraints": [],
                        "required_followups": [],
                    }
                ],
                "summary": "Approved graph repair.",
                "warnings": [],
            }
        )


if __name__ == "__main__":
    unittest.main()
