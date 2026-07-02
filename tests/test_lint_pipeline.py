from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.errors import ModelOutputError
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_lint import LintRunRequest, WikiLintCandidateSelectRequest, WikiLintIssue, WikiLintRequest, WikiScanPage, WikiScanRequest, WikiScanResponse
from knoarbor.maintenance.lint_candidates import score_lint_candidate
from knoarbor.pipelines import WikiLintPipeline
from knoarbor.pipelines.lint import _merge_candidates, _structural_diagnose_payload
from knoarbor.runtime import RunMonitor, run_monitor_context
from knoarbor.runtime.run_monitor import read_run_events


class WikiLintPipelineTests(unittest.TestCase):
    def test_scan_pipeline_reads_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().scan(WikiScanRequest(vault_path=str(vault)))

        self.assertEqual(len(response.pages), 1)
        self.assertEqual(response.pages[0].path, "Agent.md")

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
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "---\n---\n"
                "# Agent\n\n## Summary\n\n### Loop\n\n### Loop\n\nDetails.\n\n"
                "## Entities\n\n- Agent\n- agent\n",
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
        self.assertEqual(content.lower().count("- agent"), 1)
        self.assertTrue(any(fix.mode == "auto_applied" and fix.action == "remove_adjacent_duplicate_headings" for fix in response.fixes))
        self.assertTrue(any(fix.mode == "auto_applied" and fix.action == "deduplicate_section_items" for fix in response.fixes))

    def test_semantic_maintenance_first_applies_safe_structured_fixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\n### Loop\n\n### Loop\n\nAgent loop notes.\n\n"
                "## Entities\n\n- Agent\n- agent\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(FakeLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_retry_deferred_actions=False,
                )
            )
            content = page.read_text(encoding="utf-8")

        self.assertEqual(content.count("### Loop"), 1)
        self.assertEqual(content.lower().count("- agent"), 1)
        self.assertTrue(any(fix.mode == "auto_applied" for fix in response.deterministic_lint.fixes))

    def test_structural_diagnose_payload_excludes_deterministic_and_quality_issues(self) -> None:
        scan = WikiScanResponse(
            pages=[
                WikiScanPage(
                    path="Deploy.md",
                    directory="pages",
                    title="Deploy",
                    page_type="knowledge_page",
                    headings=["Summary", "Claims", "Entities", "Relations", "Evidence", "Synthesis", "Source"],
                ),
                WikiScanPage(
                    path="sources/Agent.md",
                    directory="sources",
                    title="Agent",
                    page_type="source",
                    headings=["Summary", "Source"],
                ),
                WikiScanPage(
                    path="Agent.md",
                    directory="pages",
                    title="Agent",
                    page_type="knowledge_page",
                    headings=["Summary", "Claims", "Source"],
                ),
            ],
            issues=[
                WikiLintIssue(
                    code="missing_required_section",
                    severity="info",
                    path="Deploy.md",
                    message="Page is missing required Evidence section.",
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
                    path="Agent.md",
                    message="Wiki link target does not exist.",
                ),
                WikiLintIssue(
                    code="knowledge_without_source_digest",
                    severity="info",
                    path="Agent.md",
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
        self.assertEqual([page["path"] for page in pages], ["Agent.md"])

    def test_semantic_candidate_scoring_prioritizes_quality_issues(self) -> None:
        missing_contract = score_lint_candidate(
            WikiScanPage(
                path="Agent.md",
                directory="pages",
                title="Agent",
                page_type="knowledge_page",
                updated="2026-05-01",
                content_preview="Agent notes.",
                original_content_length=1500,
                headings=["Summary", "Source"],
            ),
            [
                WikiLintIssue(
                    code="missing_required_section",
                    severity="info",
                    path="Agent.md",
                    message="Page is missing required Claims section.",
                )
            ],
        )
        provenance_only = score_lint_candidate(
            WikiScanPage(
                path="Agent.md",
                directory="pages",
                title="Agent",
                page_type="knowledge_page",
                updated="2026-05-01",
                content_preview="Agent notes.",
                original_content_length=1500,
                headings=["Summary", "Claims", "Entities", "Relations", "Evidence", "Synthesis"],
            ),
            [
                WikiLintIssue(
                    code="knowledge_without_source_digest",
                    severity="info",
                    path="Agent.md",
                    message="Generated knowledge page points to a raw source without a matching source digest page.",
                )
            ],
        )

        self.assertGreater(missing_contract.score, provenance_only.score)

    def test_semantic_candidate_scoring_ignores_deterministic_only_issues(self) -> None:
        candidate = score_lint_candidate(
            WikiScanPage(
                path="Agent.md",
                directory="pages",
                title="Agent",
                page_type="concept",
                updated="2026-05-01",
                summary="Agent notes.",
                headings=["Summary", "Claims", "Entities", "Relations", "Evidence", "Synthesis"],
                outgoing_links=["OpenClaw.md"],
                content_preview="Stable agent notes without temporal claims.",
                original_content_length=1500,
            ),
            [
                WikiLintIssue(
                    code="broken_wikilink",
                    severity="error",
                    path="Agent.md",
                    message="Wiki link target does not exist.",
                )
            ],
        )

        self.assertEqual(candidate.score, 0)
        self.assertEqual(candidate.reasons, [])

    def test_merge_candidates_deduplicates_same_operation_identity(self) -> None:
        seed = MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:Agent.md:weak_claims:seed",
                        "source": "quality",
                        "target_page": "Agent.md",
                        "issue_type": "weak_claims",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Claims are too shallow."}],
                        "recommended_action": {"action": "rewrite_section", "params": {"section": "Claims"}},
                        "expected_effect": "Rewrite Claims.",
                        "review_notes": "Seeded claims repair.",
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
                        "candidate_id": "quality:Agent.md:weak_claims:0",
                        "source": "quality",
                        "target_page": "Agent.md",
                        "issue_type": "weak_claims",
                        "severity": "medium",
                        "confidence": 0.8,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "page_excerpt", "ref": "Agent.md", "quote": "Agent loop."}],
                        "recommended_action": {"action": "rewrite_section", "params": {"section": "Claims"}},
                        "expected_effect": "Rewrite Claims.",
                        "review_notes": "Model claims repair.",
                    }
                ],
                "summary": "Model.",
                "warnings": [],
            }
        )

        merged = _merge_candidates(seed, model)

        self.assertEqual(len(merged.candidates), 1)
        self.assertEqual(merged.candidates[0].candidate_id, "quality:Agent.md:weak_claims:seed")

    def test_scoped_scan_limits_pages_and_expands_provenance_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: **Agent** uses loop control.\n\n## Entities\n\n- Agent\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent | implemented_by | OpenClaw | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent notes. | high |\n\n## Synthesis\n\nAgent notes.notes/agent.md\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: b\n---\n"
                "# OpenClaw\n\n## Summary\n\nOpenClaw notes.\n\n## Claims\n\n- C1: **OpenClaw** is an Agent implementation.\n\n## Entities\n\n- OpenClaw\n- Agent\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| OpenClaw | implements | Agent | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:1 | OpenClaw notes. | medium |\n\n## Synthesis\n\nOpenClaw notes.notes/agent.md\n",
                encoding="utf-8",
            )

            scoped = WikiLintPipeline().scan(
                WikiScanRequest(
                    vault_path=str(vault),
                    scope_pages=["Agent.md"],
                    include_related=True,
                )
            )
            strict = WikiLintPipeline().scan(
                WikiScanRequest(
                    vault_path=str(vault),
                    scope_pages=["Agent.md"],
                    include_related=False,
                )
            )

        self.assertEqual({page.path for page in scoped.pages}, {"Agent.md", "OpenClaw.md"})
        self.assertEqual([page.path for page in strict.pages], ["Agent.md"])
        self.assertTrue(scoped.stats["scoped"])

    def test_candidate_selection_respects_explicit_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: Agent loop coordinates tools.\n\n"
                "## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent notes. | medium |\n\n"
                "## Synthesis\n\nAgent loop notes.\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OutOfScope.md").write_text(
                "---\ncreated: 2025-01-01\nupdated: 2025-01-01\ncontent_hash: b\n---\n"
                "# Out Of Scope\n\n## Summary\n\nLatest ranking and current API price notes.\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().select_candidates(
                WikiLintCandidateSelectRequest(
                    vault_path=str(vault),
                    scope_pages=["Agent.md"],
                    include_related=False,
                )
            )

        self.assertNotIn("OutOfScope.md", {candidate.path for candidate in response.candidates})
        self.assertEqual(response.stats["scope_pages"], ["Agent.md"])

    def test_scan_reports_sensitive_generated_page_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "sources").mkdir(parents=True)
            (vault / "wiki" / "sources" / "Agent.md").write_text(
                "---\n---\n"
                "# Agent\n\n## Summary\n\nToken sk-abcdefghijklmnop1234567890 and app cli_aa9f1cd454399bc8.notes/agent.md\n",
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Entities\n\n- Agent\n- agent\n",
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
        self.assertEqual(duplicate_issues[0].details["section"], "Entities")
        self.assertTrue(any(fix.action == "deduplicate_section_items" for fix in response.fixes))

    def test_lint_reports_adjacent_duplicate_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n### Control\n\n### Control\n\nLoop details.notes/agent.md\n",
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Deploy.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                )
            )

        missing_sections = [issue.details["section"] for issue in response.issues if issue.code == "missing_required_section"]
        self.assertIn("Claims", missing_sections)
        self.assertIn("Entities", missing_sections)
        self.assertIn("Relations", missing_sections)
        self.assertIn("Evidence", missing_sections)
        self.assertIn("Synthesis", missing_sections)
        self.assertTrue(any(fix.action == "add_missing_section" for fix in response.fixes))

    def test_lint_uses_unified_page_contract_for_all_titles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
            (vault / "wiki" / "pages" / "Timeline.md").write_text(
                frontmatter + "# Timeline\n\n## Summary\n\nTimeline notes.\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "Workflow.md").write_text(
                frontmatter
                + "# Workflow\n\n## Summary\n\nWorkflow notes.\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                )
            )

        codes = {issue.code for issue in response.issues}
        self.assertIn("missing_required_section", codes)

    def test_lint_reports_p2_graph_and_path_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
            page_frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n"
            digest_frontmatter = "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: b\n"
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                page_frontmatter + "---\n# Agent\n\n## Summary\n\nOne isolated page.\n\n## Claims\n\n- C1: Agent has isolated notes.\n\n## Entities\n\n- Agent\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent | describes | Notes | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/source.md | unit:0 | Agent notes. | medium |\n\n## Synthesis\n\nBody.notes/source.md\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "sources" / "Agent.md").write_text(
                digest_frontmatter
                + "---\n# Agent Source\n\n## Source Identity\n\n- raw_source: raw/inbox/notes/source.md\n\n## Source Units\n\n| Unit | Title | Range | Summary |\n|---|---|---|---|\n| U1 | Agent | unit:0 | Agent notes. |\n\n## Contribution Map\n\n| Page | Claims | Units |\n|---|---|---|\n| Agent.md | C1 | U1 |\n\n## Raw Source\n\n- raw/inbox/notes/source.md\n",
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
        self.assertNotIn("weak_link_graph", codes)
        graph_health = response.stats["graph_health"]
        self.assertGreaterEqual(graph_health["component_count"], 1)
        self.assertEqual(graph_health["isolated_page_count"], 0)

    def test_lint_uses_structured_relations_and_evidence_for_graph_connectivity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            sources = vault / "wiki" / "sources"
            pages.mkdir(parents=True)
            sources.mkdir(parents=True)
            (vault / "raw" / "notes").mkdir(parents=True)
            (vault / "raw" / "notes" / "a2a.md").write_text("# A2A\n\nA2A notes.\n", encoding="utf-8")
            common_frontmatter = (
                "---\n"
                "created: 2026-06-25\n"
                "updated: 2026-06-25\n"
                "content_hash: a2a\n"
            )
            (pages / "A2A-(Agent-to-Agent)-Protocol.md").write_text(
                common_frontmatter
                + "---\n# A2A (Agent-to-Agent) Protocol\n\n"
                "## Summary\n\nA2A standardizes agent-to-agent collaboration.\n\n"
                "## Claims\n\n- C1: **A2A** defines cross-agent task and message exchange.\n\n"
                "## Entities\n\n- A2A\n- Agent Card\n\n"
                "## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| A2A | defines | Agent Card | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/a2a.md | unit:0 | A2A notes. | high |\n\n"
                "## Synthesis\n\nA2A is a protocol boundary for multi-agent systems.\n",
                encoding="utf-8",
            )
            (sources / "A2A-Source.md").write_text(
                common_frontmatter
                + "role: source_digest\n---\n# A2A Source\n\n"
                "## Source Identity\n\n- raw_source: raw/inbox/notes/a2a.md\n\n"
                "## Audit Summary\n\nThis source supports A2A claims.\n\n"
                "## Source Units\n\n| Unit | Title | Range | Summary |\n|---|---|---|---|\n| U1 | A2A | unit:0 | A2A notes. |\n\n"
                "## Contribution Map\n\n| Page | Claims | Units |\n|---|---|---|\n| A2A-(Agent-to-Agent)-Protocol.md | C1 | U1 |\n\n"
                "## Unresolved / Rejected\n\n- None.\n\n"
                "## Raw Source\n\n- raw/inbox/notes/a2a.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline().lint(WikiLintRequest(vault_path=str(vault), write_report=False))

        issues_by_code = {issue.code for issue in response.issues}
        self.assertNotIn("orphan_page", issues_by_code)
        self.assertNotIn("weak_link_graph", issues_by_code)
        self.assertNotIn("source_without_knowledge_links", issues_by_code)
        self.assertEqual(response.stats["graph_health"]["isolated_page_count"], 0)

    def test_scope_related_does_not_expand_by_shared_entity_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            base_frontmatter = "---\ncreated: 2026-06-25\nupdated: 2026-06-25\n"
            for name, source, claim in [
                ("Agent-Loop.md", "raw/inbox/notes/agent-loop.md", "Agent Loop controls tool execution."),
                ("Agent-Memory.md", "raw/inbox/notes/agent-memory.md", "Agent memory stores reusable session context."),
            ]:
                (pages / name).write_text(
                    base_frontmatter
                    + f"content_hash: {name}\n"
                    + "---\n"
                    + f"# {name.removesuffix('.md')}\n\n"
                    + f"## Summary\n\n{claim}\n\n"
                    + f"## Claims\n\n- C1: **Agent** related claim. {claim}\n\n"
                    + "## Entities\n\n- Agent\n\n"
                    + "## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent | relates_to | Runtime | C1 |\n\n"
                    + f"## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | {source} | unit:0 | {claim} | high |\n\n"
                    + f"## Synthesis\n\n{claim}\n",
                    encoding="utf-8",
                )

            response = WikiLintPipeline().lint(
                WikiLintRequest(
                    vault_path=str(vault),
                    write_report=False,
                    scope_pages=["Agent-Loop.md"],
                    include_related=True,
                )
            )

        self.assertTrue(response.stats["scoped"])
        self.assertEqual(response.stats["scope_pages"], ["Agent-Loop.md"])
        self.assertEqual(response.stats["scope_page_count"], 1)

    def test_run_maintenance_uses_explicit_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.notes/agent.md\n",
                encoding="utf-8",
            )

            monitor = RunMonitor(vault_path=vault, flow="lint", run_id="lint-report-test")
            monitor.start(message="lint test started")
            with run_monitor_context(monitor):
                response = WikiLintPipeline().run_maintenance(
                    LintRunRequest(
                        vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="latest_ingest:test",
                            trigger="ingest",
                            source=MaintenanceScopeSource(kind="source", source_id="test"),
                            changed_pages=["Agent.md"],
                        ),
                    )
                )

            self.assertEqual(response.schema_version, "lint_run.v1")
            self.assertTrue(response.deterministic_lint.stats["scoped"])
            self.assertEqual(response.policy_decision.mode, "deterministic")
            self.assertEqual(response.report_path, "maintenance/reports/lint/lint_run_report_lint-report-test.md")
            self.assertIsNotNone(response.ledger_path)
            events = read_run_events(vault, "lint-report-test")
            lint_steps = [
                event.payload.get("lint_step")
                for event in events
                if event.event_type in {"lint_step_finished", "lint_step_skipped"}
            ]
            self.assertEqual(lint_steps, ["scan", "diagnose", "review", "execute", "verify", "report"])

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

    def test_run_maintenance_can_execute_semantic_maintenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(FakeLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_retry_deferred_actions=False,
                )
            )

        self.assertEqual(response.mode, "semantic")
        self.assertEqual(response.semantic_candidates["summary"], "One semantic candidate.")
        self.assertEqual(response.maintenance_review["decisions"][0]["decision"], "approve")

    def test_semantic_skips_model_when_scan_has_no_issues(self) -> None:
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
                    mode="semantic",
                    auto_retry_deferred_actions=False,
                )
            )

        self.assertEqual(response.semantic_candidates["candidates"], [])
        self.assertEqual(response.maintenance_review["decisions"], [])


    def test_run_maintenance_applies_reviewed_wiki_operations_and_rescans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n## Synthesis\n\nAgent loop notes.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(WikiOperationLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.applied_operations[0]["action"], "add_missing_section")
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "add_missing_section")
        self.assertIn("## Evidence", content)
        self.assertIsNotNone(response.rescan)

    def test_run_maintenance_applies_missing_section_as_wiki_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "sources").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "RAG.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# RAG\n\n## Summary\n\nRAG evaluation notes.\n\n## Claims\n\n- C1: [[RAG evaluation]] needs source-backed metrics.\n\n## Entities\n\n- [[RAG evaluation]]\n- [[Retrieval quality]]\n\n## Relations\n\n| Subject | Predicate | Object | Based on |\n|---|---|---|---|\n| [[RAG evaluation]] | evaluates | [[Retrieval quality]] | C1 |\n\n## Synthesis\n\nBody.\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "sources" / "RAG.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: source-rag\n---\n"
                "# RAG Source\n\n"
                "## Source Identity\n\n- raw_source: raw/inbox/notes/rag.md\n\n"
                "## Audit Summary\n\nRAG source digest.\n\n"
                "## Source Units\n\n| Unit | Title | Range | Summary |\n|---|---|---|---|\n| U1 | RAG | unit:0 | RAG source. |\n\n"
                "## Contribution Map\n\n| Page | Claims | Units |\n|---|---|---|\n| RAG.md | C1 | U1 |\n\n"
                "## Unresolved / Rejected\n\n- None.\n\n"
                "## Raw Source\n\n- raw/inbox/notes/rag.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(MissingSectionWikiOperationWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["RAG.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.applied_operations[0]["action"], "add_missing_section")
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertIn("## Evidence", content)
        remaining_missing_sections = [issue for issue in response.rescan.issues if issue.code == "missing_required_section"]
        self.assertEqual(remaining_missing_sections, [])

    def test_run_maintenance_writes_reviewed_lint_drafts_and_rescans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nOld summary.\n\n## Claims\n\n- C1: **Agent loop** has old notes.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | has | notes | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Old source. | medium |\n\n## Synthesis\n\nOld answer.notes/agent.md\n",
                encoding="utf-8",
            )

            workflow = DraftWriteLintSemanticWorkflow()
            response = WikiLintPipeline(workflow).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.written_pages, ["Agent.md"])
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "improve_summary")
        self.assertIn("Improved summary.", content)
        self.assertIsNotNone(response.rescan)
        self.assertEqual(response.draft_batch["drafts"][0]["target_page"], "Agent.md")
        self.assertIn("approved_candidates", workflow.compile_payload)
        self.assertNotIn("maintenance_candidates", workflow.compile_payload)

    def test_quality_lint_rewrites_claims_as_local_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n"
                "## Claims\n\n- 暂无内容\n\n"
                "## Entities\n\n- Agent loop\n\n"
                "## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent loop notes. | medium |\n\n"
                "## Synthesis\n\nAgent loop notes.\n\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(ClaimsDraftWriteLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                )
            )

            content = page.read_text(encoding="utf-8")

        self.assertEqual(response.written_pages, ["Agent.md"])
        self.assertEqual(response.verifications[0]["status"], "verified")
        self.assertEqual(response.verifications[0]["action"], "rewrite_section")
        self.assertIn("C1:", content)
        self.assertIn("Agent loop", content)
        self.assertNotIn("暂无内容", content)
        self.assertIsNotNone(response.rescan)

    def test_lint_draft_compile_rejects_unapproved_target_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nOld summary.\n\n## Claims\n\n- C1: Agent loop has notes.\n\n"
                "## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | has | notes | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Old source. | medium |\n\n"
                "## Synthesis\n\nOld answer.\n",
                encoding="utf-8",
            )

            with self.assertRaises(ModelOutputError):
                WikiLintPipeline(OverreachingDraftWriteLintSemanticWorkflow()).run_maintenance(
                    LintRunRequest(
                        vault_path=str(vault),
                        scope=MaintenanceScope(
                            scope_id="manual:test",
                            trigger="manual",
                            source=MaintenanceScopeSource(kind="test"),
                            changed_pages=["Agent.md"],
                        ),
                        mode="semantic",
                        auto_apply_reviewed_changes=True,
                    )
                )

            content = (vault / "wiki" / "pages" / "Agent.md").read_text(encoding="utf-8")

        self.assertIn("Old summary.", content)

    def test_run_maintenance_does_not_compile_source_digest_from_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "raw" / "notes").mkdir(parents=True)
            (vault / "raw" / "notes" / "agent.md").write_text("# Agent source\n", encoding="utf-8")
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent notes.\n\n## Claims\n\n- C1: **Agent** has notes.\n\n## Entities\n\n- Agent\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent | has | notes | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent notes. | medium |\n\n## Synthesis\n\nAgent notes.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(UnsupportedCreateSourceDigestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                )
            )

            source_pages = sorted((vault / "wiki" / "sources").glob("*.md")) if (vault / "wiki" / "sources").exists() else []

        self.assertEqual(response.written_pages, [])
        self.assertEqual(source_pages, [])
        self.assertIsNone(response.draft_batch)

    def test_run_maintenance_records_approved_queued_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nOne concept.notes/source.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(QueuedActionLintSemanticWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
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
            (vault / "raw" / "inbox" / "notes").mkdir(parents=True)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "raw" / "inbox" / "notes" / "agent.md").write_text("# Agent raw\n\nAgent loop source.", encoding="utf-8")
            target = vault / "wiki" / "pages" / "Agent.md"
            target.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent loop source. | high |\n\n## Synthesis\n\nAgent loop answer.notes/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(RefreshRequestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=False,
                )
            )
            source_pages = sorted((vault / "wiki" / "sources").glob("*.md"))
            source_content = source_pages[0].read_text(encoding="utf-8")
            target_content = target.read_text(encoding="utf-8")

        self.assertEqual(len(source_pages), 1)
        self.assertIn("sources/", response.written_pages[0])
        self.assertTrue(any(operation["action"] == "create_source_digest" for operation in response.applied_operations))
        self.assertTrue(any(operation["action"] == "record_source_digest" for operation in response.applied_operations))
        self.assertIn("## Source Units", source_content)
        self.assertIn("| U1 | raw/inbox/notes/agent.md | source-level | source digest compiled from this raw source | medium |", source_content)
        self.assertIn("## Contribution Map", source_content)
        self.assertIn("Agent.md", source_content)
        self.assertIn("## Unresolved / Rejected", source_content)
        self.assertNotIn("[[sources/", target_content)
        self.assertIsNotNone(response.rescan)
        refresh_verifications = [item for item in response.verifications if item["action"] in {"create_source_digest", "record_source_digest"}]
        self.assertEqual([item["status"] for item in refresh_verifications], ["verified", "verified"])
        self.assertNotIn("knowledge_without_source_digest", {issue.code for issue in response.rescan.issues})

    def test_run_maintenance_executes_refresh_request_with_existing_source_digest_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "sources").mkdir(parents=True)
            target = vault / "wiki" / "pages" / "Agent.md"
            target.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent loop source. | high |\n\n## Synthesis\n\nAgent loop answer.notes/agent.md\n",
                encoding="utf-8",
            )
            digest = vault / "wiki" / "sources" / "Agent-Source.md"
            digest.write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: s\n---\n"
                "# Agent Source\n\n## Source Identity\n\n- raw_source: /Users/example/Documents/agent.md\n\n## Source Units\n\n| Unit | Title | Range | Summary |\n|---|---|---|---|\n| U1 | Agent | source-level | Source digest. |\n\n## Contribution Map\n\n| Page | Claims | Units |\n|---|---|---|\n| Agent.md | C1 | U1 |\n\n## Raw Source\n\n- /Users/example/Documents/agent.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(RefreshRequestWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=False,
                )
            )
            source_pages = sorted((vault / "wiki" / "sources").glob("*.md"))
            source_content = digest.read_text(encoding="utf-8")
            target_content = target.read_text(encoding="utf-8")

        self.assertEqual(len(source_pages), 1)
        self.assertFalse(response.written_pages)
        self.assertTrue(any(operation["action"] == "record_source_digest" for operation in response.applied_operations))
        refresh_verifications = [item for item in response.verifications if item["action"] == "record_source_digest"]
        self.assertEqual([item["status"] for item in refresh_verifications], ["verified"])
        self.assertNotIn("[[Agent|Agent]]", source_content)
        self.assertNotIn("[[sources/Agent-Source|Agent Source]]", target_content)

    def test_run_maintenance_retries_report_only_queue_with_enriched_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent-a.md | unit:0 | Primary notes. | medium |\n\n## Synthesis\n\nPrimary notes.notes/agent-a.md\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "Agent-Duplicate.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: b\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop duplicate notes.\n\n## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n## Entities\n\n- Agent loop\n\n## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent-b.md | unit:0 | Duplicate notes. | medium |\n\n## Synthesis\n\nDuplicate notes.notes/agent-b.md\n",
                encoding="utf-8",
            )

            response = WikiLintPipeline(DeferredMergeRetryWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="manual:test",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent.md", "Agent-Duplicate.md"],
                    ),
                    mode="semantic",
                    auto_apply_reviewed_changes=True,
                    auto_retry_deferred_actions=True,
                )
            )
            merged_content = (vault / "wiki" / "pages" / "Agent.md").read_text(encoding="utf-8")
            archived = list((vault / "maintenance" / "archives" / "merged_pages").glob("*Agent-Duplicate.md"))

        self.assertEqual(len(response.deferred_retries), 1)
        self.assertEqual(response.applied_operations[-1]["action"], "merge_pages")
        self.assertIn("## Merged Notes", merged_content)
        self.assertEqual(len(archived), 1)

    def test_lint_run_report_records_trend_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent.md").write_text(
                "---\ncreated: 2026-05-01\nupdated: 2026-05-01\ncontent_hash: a\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n\n## Entities\n\n- Agent\n- agentnotes/agent.md\n",
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
        self.assertIn("missing_required_section=4", report)


class FakeLintSemanticWorkflow:
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:Agent.md:source:0",
                        "source": "structural",
                        "target_page": "Agent.md",
                        "issue_type": "source_link",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "source"}],
                        "recommended_action": {"action": "report", "params": {}},
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
                        "candidate_id": "structural:Agent.md:missing_required_section:0",
                        "source": "structural",
                        "target_page": "Agent.md",
                        "issue_type": "missing_required_section",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "safe",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Missing Evidence section."}],
                        "recommended_action": {
                            "action": "add_missing_section",
                            "params": {"section": "Evidence"},
                        },
                        "expected_effect": "Add required Evidence section.",
                        "review_notes": "Schema-required section scaffolding only.",
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
                        "reason": "Missing section scaffolding is explicit and supported.",
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
                        "candidate_id": "structural:RAG.md:missing_required_section:0",
                        "source": "structural",
                        "target_page": "RAG.md",
                        "issue_type": "missing_required_section",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "safe",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "scan_issue", "ref": "RAG.md", "quote": "Page is missing required concepts section: Evidence."}],
                        "recommended_action": {
                            "action": "add_missing_section",
                            "params": {"section": "Evidence"},
                        },
                        "expected_effect": "Add required Evidence section.",
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


class DraftWriteLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def __init__(self) -> None:
        self.compile_payload = {}

    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates(candidates=[], summary="No structural candidates.")

    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:Agent.md:summary:0",
                        "source": "quality",
                        "target_page": "Agent.md",
                        "issue_type": "poor_summary",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "page_excerpt", "ref": "Agent.md", "quote": "Old summary."}],
                        "recommended_action": {"action": "improve_summary", "params": {}},
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
        self.compile_payload = draft_payload
        return WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "update",
                        "target_page": "Agent.md",
                        "source_file": None,
                        "title": "Agent",
                        "page_dir": "pages",
                        "question": "Improve summary",
                        "summary": "Improved summary.",
                        "synthesis": "Improved answer.",
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
                            "candidate_id": "structural:Agent.md:duplicate_title:0",
                            "source": "structural",
                            "target_page": "Agent.md",
                            "issue_type": "duplicate_title",
                            "severity": "low",
                            "confidence": 0.7,
                            "risk_hint": "medium",
                            "executor_hint": "report_only",
                            "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Multiple pages share title"}],
                            "recommended_action": {
                                "action": "queue_merge_candidate",
                                "params": {"pages": ["Agent.md", "Agent-Duplicate.md"]},
                            },
                            "expected_effect": "Retry with page content before merging.",
                            "review_notes": "Needs enriched context.",
                        }
                    ],
                    "summary": "Queue merge candidate.",
                    "warnings": [],
                }
            )
        pages = {page["path"]: page for page in scan_payload["scan"]["pages"]}
        assert "content_preview" in pages["Agent.md"]
        assert "Agent-Duplicate.md" in pages
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "structural:Agent.md:merge_pages:retry",
                        "source": "structural",
                        "target_page": "Agent.md",
                        "issue_type": "duplicate_title",
                        "severity": "medium",
                        "confidence": 0.92,
                        "risk_hint": "medium",
                        "executor_hint": "deterministic_wiki_operation",
                        "evidence": [{"kind": "page_excerpt", "ref": "Agent-Duplicate.md", "quote": "Agent loop duplicate notes"}],
                        "recommended_action": {
                            "action": "merge_pages",
                            "params": {"source_pages": ["Agent-Duplicate.md"], "archive_sources": True},
                        },
                        "expected_effect": "Merge duplicate Agent wiki pages.",
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


class ClaimsDraftWriteLintSemanticWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates(candidates=[], summary="No structural candidates.")

    def diagnose_quality(self, quality_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "quality:Agent.md:weak_claims:0",
                        "source": "quality",
                        "target_page": "Agent.md",
                        "issue_type": "weak_claims",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [
                            {
                                "kind": "page_excerpt",
                                "ref": "Agent.md",
                                "quote": "Agent loop notes.",
                            }
                        ],
                        "recommended_action": {
                            "action": "rewrite_section",
                            "params": {"section": "Claims"},
                        },
                        "expected_effect": "Replace placeholder claims with source-backed claims.",
                        "review_notes": "Patch only the Claims section.",
                    }
                ],
                "summary": "One claims candidate.",
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
                        "reason": "Claims patch is local and supported.",
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
                        "target_page": "Agent.md",
                        "source_file": None,
                        "title": "Agent",
                        "page_dir": "pages",
                        "question": "Rewrite claims",
                        "summary": "Claims rewritten.",
                        "synthesis": "Replace placeholder claims with source-backed claims.",
                        "patches": [
                            {
                                "operation": "replace_section",
                                "section": "Claims",
                                "content": "- C1: **Agent loop** coordinates reasoning, tool use, and observation.\n- C2: **Agent loop** should preserve evidence links for maintainable wiki updates.",
                            }
                        ],
                        "confidence": 0.9,
                        "model_provider": "fake",
                        "model_name": "unit",
                    }
                ],
                "batch_summary": "One claims patch.",
                "warnings": [],
            }
        )


class OverreachingDraftWriteLintSemanticWorkflow(DraftWriteLintSemanticWorkflow):
    def compile_drafts(self, draft_payload, *, max_tokens=None):
        self.compile_payload = draft_payload
        return WikiDraftBatch.model_validate(
            {
                "drafts": [
                    {
                        "operation_index": 0,
                        "write_action": "update",
                        "target_page": "Other.md",
                        "source_file": None,
                        "title": "Other",
                        "page_dir": "pages",
                        "question": "Overreach",
                        "summary": "Wrong target.",
                        "synthesis": "Wrong target.",
                        "patches": [
                            {
                                "operation": "replace_section",
                                "section": "Summary",
                                "content": "Wrong target.",
                            }
                        ],
                        "confidence": 0.9,
                        "model_provider": "fake",
                        "model_name": "unit",
                    }
                ],
                "batch_summary": "Wrong target.",
                "warnings": [],
            }
        )


class UnsupportedCreateSourceDigestWorkflow(FakeLintSemanticWorkflow):
    def diagnose_structural(self, scan_payload, *, max_tokens=None):
        return MaintenanceCandidates.model_validate(
            {
                "schema_version": "maintenance_candidates.v1",
                "candidates": [
                    {
                        "candidate_id": "provenance:Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "low",
                        "confidence": 0.9,
                        "risk_hint": "low",
                        "executor_hint": "draft_write",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "create_source_digest",
                            "params": {"source_file": "raw/inbox/notes/agent.md"},
                        },
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
                        "candidate_id": "provenance:Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "refresh_request",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "refresh_request",
                            "params": {"section": "Evidence", "source_file": "raw/inbox/notes/source.md"},
                        },
                        "expected_effect": "Queue source refresh for missing provenance.",
                        "review_notes": "Refresh must use the raw source.",
                    },
                    {
                        "candidate_id": "graph:Agent.md:weak_link_graph:1",
                        "source": "graph",
                        "target_page": "Agent.md",
                        "issue_type": "weak_link_graph",
                        "severity": "medium",
                        "confidence": 0.9,
                        "risk_hint": "medium",
                        "executor_hint": "report_only",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Weak graph"}],
                        "recommended_action": {
                            "action": "queue_graph_review",
                            "params": {"reason": "weak graph"},
                        },
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
                        "required_followups": ["refresh raw/inbox/notes/source.md"],
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
                        "candidate_id": "provenance:Agent.md:knowledge_without_source_digest:0",
                        "source": "provenance",
                        "target_page": "Agent.md",
                        "issue_type": "knowledge_without_source_digest",
                        "severity": "medium",
                        "confidence": 0.95,
                        "risk_hint": "low",
                        "executor_hint": "refresh_request",
                        "evidence": [{"kind": "scan_issue", "ref": "Agent.md", "quote": "Missing source digest"}],
                        "recommended_action": {
                            "action": "refresh_request",
                            "params": {"source_file": "raw/inbox/notes/agent.md"},
                        },
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


if __name__ == "__main__":
    unittest.main()
