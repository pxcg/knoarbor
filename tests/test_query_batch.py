from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from knoarbor.core.vault_selection import ResolvedVault
from knoarbor.core.schemas.raw_evidence import RawEvidenceRecord
from knoarbor.core.schemas.raw_evidence import SourceUnitRecord
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.pipelines.query_batch import (
    BM25_GLOBAL_RESULT_WINDOW,
    BM25_RESULT_WINDOW_PER_GROUP,
    QueryBatchExpression,
    QueryBatchPipeline,
    QueryBatchRequest,
    _batch_status,
    _expression_status,
    build_evidence_segments,
)
from knoarbor.retrieval.corpus_catalog import NavigationRegionScope
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.index_snapshot import open_index_snapshot
from tests.test_semantic_indexed_query import _batch, _record
from tests.transactional_ingest_helpers import publish_batch, publish_record


class QueryBatchPipelineTest(unittest.TestCase):
    def test_batch_verifies_one_snapshot_per_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("shared", "Shared snapshot evidence."),
            )
            VaultMaterializer().reconcile(vault, force=True)

            with patch(
                "knoarbor.pipelines.query_batch.open_index_snapshot",
                wraps=open_index_snapshot,
            ) as open_snapshot:
                result = QueryBatchPipeline().run(
                    QueryBatchRequest(
                        vaults=(
                            ResolvedVault(
                                path=vault,
                                vault_id="test",
                            ),
                        ),
                        expressions=(
                            QueryBatchExpression(
                                query_id="literal",
                                query="shared snapshot",
                                group_id="region:test",
                            ),
                            QueryBatchExpression(
                                query_id="rewrite",
                                query="snapshot evidence",
                                group_id="region:test",
                            ),
                        ),
                    )
                )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(open_snapshot.call_count, 1)

    def test_batch_consumes_a_bm25_ranked_window_per_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for index in range(BM25_RESULT_WINDOW_PER_GROUP + 5):
                publish_record(
                    vault,
                    _record(
                        f"ranked-{index:02d}",
                        f"Shared ranked retrieval evidence {index}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(ResolvedVault(path=vault, vault_id="test"),),
                    expressions=(
                        QueryBatchExpression(
                            query_id="ranked",
                            query="shared ranked retrieval evidence",
                        ),
                    ),
                )
            )

        self.assertEqual(
            result.candidate_set.count,
            BM25_RESULT_WINDOW_PER_GROUP,
        )
        self.assertEqual(
            result.query_results[0]["eligible_candidate_count"],
            BM25_RESULT_WINDOW_PER_GROUP + 5,
        )
        self.assertEqual(
            result.group_results[0]["result_window"],
            BM25_RESULT_WINDOW_PER_GROUP,
        )

    def test_literal_and_rewritten_queries_share_one_group_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for prefix in ("literal", "rewritten"):
                for index in range(10):
                    publish_record(
                        vault,
                        _record(
                            f"{prefix}-{index:02d}",
                            f"{prefix} shared regional evidence {index}.",
                        ),
                    )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(ResolvedVault(path=vault, vault_id="test"),),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="literal shared regional evidence",
                            group_id="region:test",
                        ),
                        QueryBatchExpression(
                            query_id="rewrite",
                            query="rewritten shared regional evidence",
                            group_id="region:test",
                        ),
                    ),
                )
            )

        self.assertEqual(len(result.query_results), 2)
        self.assertEqual(len(result.group_results), 1)
        self.assertEqual(
            result.group_results[0]["eligible_candidate_count"],
            20,
        )
        self.assertEqual(
            result.group_results[0]["candidate_count"],
            BM25_RESULT_WINDOW_PER_GROUP,
        )
        self.assertEqual(
            result.candidate_set.count,
            BM25_RESULT_WINDOW_PER_GROUP,
        )

    def test_alternative_queries_do_not_double_vote_generic_matches(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for index in range(BM25_RESULT_WINDOW_PER_GROUP + 1):
                publish_record(
                    vault,
                    _record(
                        f"front-{index:02d}",
                        f"IPCC climate report front matter {index}.",
                    ),
                )
            publish_record(
                vault,
                _record(
                    "figure-3-2",
                    (
                        "IPCC Figure 3.2 warming levels impact natural "
                        "systems and human health risks."
                    ),
                ),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(ResolvedVault(path=vault, vault_id="test"),),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="IPCC",
                            group_id="region:ipcc",
                        ),
                        QueryBatchExpression(
                            query_id="rewrite",
                            query=(
                                "IPCC warming levels natural systems "
                                "human health risks"
                            ),
                            group_id="region:ipcc",
                        ),
                    ),
                )
            )

        self.assertIn(
            "source:figure-3-2",
            {
                item.handle.source_record_id
                for item in result.candidate_set.items
            },
        )

    def test_batch_applies_global_window_after_cross_region_deduplication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            region_source_ids: dict[str, set[str]] = {
                "region_alpha": set(),
                "region_beta": set(),
            }
            region_unit_ids: dict[str, set[str]] = {
                "region_alpha": set(),
                "region_beta": set(),
            }
            for region_name in ("alpha", "beta"):
                region_id = f"region_{region_name}"
                for index in range(BM25_RESULT_WINDOW_PER_GROUP):
                    name = f"{region_name}-{index:02d}"
                    publish_record(
                        vault,
                        _record(
                            name,
                            f"Shared bounded retrieval evidence {index}.",
                        ),
                    )
                    region_source_ids[region_id].add(f"source:{name}")
                    region_unit_ids[region_id].add(f"unit:{name}")
            VaultMaterializer().reconcile(vault, force=True)
            scopes = {
                region_id: NavigationRegionScope(
                    region_id=region_id,
                    source_record_ids=frozenset(
                        region_source_ids[region_id]
                    ),
                    source_unit_ids=frozenset(
                        region_unit_ids[region_id]
                    ),
                )
                for region_id in region_source_ids
            }
            with patch(
                "knoarbor.pipelines.query_batch.resolve_navigation_region_scopes",
                return_value=scopes,
            ):
                result = QueryBatchPipeline().run(
                    QueryBatchRequest(
                        vaults=(
                            ResolvedVault(path=vault, vault_id="test"),
                        ),
                        expressions=(
                            QueryBatchExpression(
                                query_id="alpha",
                                query="shared bounded retrieval evidence",
                                region_id="region_alpha",
                            ),
                            QueryBatchExpression(
                                query_id="beta",
                                query="shared bounded retrieval evidence",
                                region_id="region_beta",
                            ),
                        ),
                    )
                )

        self.assertEqual(
            [item["candidate_count"] for item in result.query_results],
            [BM25_RESULT_WINDOW_PER_GROUP] * 2,
        )
        self.assertEqual(
            result.global_eligible_candidate_count,
            BM25_RESULT_WINDOW_PER_GROUP * 2,
        )
        self.assertEqual(
            result.global_result_window,
            BM25_GLOBAL_RESULT_WINDOW,
        )
        self.assertEqual(
            result.candidate_set.count,
            BM25_GLOBAL_RESULT_WINDOW,
        )
        self.assertEqual(result.raw_read_count, BM25_GLOBAL_RESULT_WINDOW)
        self.assertEqual(
            {
                item.read.handle.source_record_id.split(":", 1)[1].split(
                    "-", 1
                )[0]
                for item in result.evidence_set.items
            },
            {"alpha", "beta"},
        )

    def test_evidence_segments_preserve_all_disjoint_matches_and_offsets(
        self,
    ) -> None:
        content = (
            "Unrelated introduction.\n\n"
            "First requested fact. Supporting context.\n\n"
            "Unrelated middle.\n\n"
            "Second requested fact. More context.\n\n"
            "Unrelated ending."
        )
        first_start = content.index("First requested fact")
        second_start = content.index("Second requested fact")
        raw = RawEvidenceRecord(
            evidence_id="ev:segments",
            raw_record_id="raw:segments",
            raw_revision_id="rawrev:segments",
            source_unit_id="unit:segments",
            source_record_id="source:segments",
            unit_index=0,
            excerpt=content,
            content=content,
            char_start=0,
            char_end=len(content),
        )

        segments = build_evidence_segments(
            raw,
            (
                (first_start, first_start + len("First requested fact")),
                (second_start, second_start + len("Second requested fact")),
            ),
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(
            [item.text for item in segments],
            ["First requested fact.", "Second requested fact."],
        )
        self.assertEqual(
            [content[item.char_start:item.char_end] for item in segments],
            [item.text for item in segments],
        )

    def test_single_query_reads_every_independently_relevant_raw(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for name in ("one", "two", "three"):
                publish_record(
                    vault,
                    _record(
                        name,
                        f"Shared retrieval evidence appears in source {name}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="shared retrieval evidence",
                )
            )

        self.assertEqual(len(result.handles), 3)
        self.assertEqual(len(result.matches), 3)
        self.assertEqual(result.stats["evidence_handle_count"], 3)
        self.assertEqual(result.stats["evidence_selected_count"], 3)
        self.assertTrue(
            all(
                reasons[0].startswith("structural_evidence.v1:")
                for reasons in result.stats["evidence_selection_reasons"].values()
            )
        )

    def test_query_owner_deduplicates_expressions_and_resolves_selected_raw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(ResolvedVault(path=vault, vault_id="test", vault_name="Test"),),
                    expressions=(
                        QueryBatchExpression(query_id="literal", query="dynamic tool decisions"),
                        QueryBatchExpression(query_id="duplicate", query=" Dynamic   Tool Decisions "),
                        QueryBatchExpression(query_id="semantic", query="agent loop decisions"),
                    ),
                )
            )

        self.assertEqual(
            [(item.query_id, item.query) for item in result.expressions],
            [
                ("literal", "dynamic tool decisions"),
                ("semantic", "agent loop decisions"),
            ],
        )
        self.assertEqual(result.status, "candidates")
        self.assertGreaterEqual(result.candidate_set.count, result.raw_read_count)
        self.assertEqual(len(result.evidence_set.items), result.raw_read_count)
        self.assertEqual(
            list(result.evidence_set.selected_evidence_ids),
            [item.read.handle.evidence_id for item in result.evidence_set.items],
        )
        self.assertTrue(
            all(item.read.raw_evidence.content for item in result.evidence_set.items)
        )
        self.assertTrue(all("candidates" not in item for item in result.query_results))

    def test_candidate_and_evidence_sets_do_not_assign_authority_to_rank_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for name in ("one", "two", "three"):
                publish_record(
                    vault,
                    _record(
                        name,
                        f"Shared retrieval evidence appears in source {name}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="shared retrieval evidence",
                        ),
                    ),
                )
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.candidate_set.count, 3)
        self.assertEqual(len(result.evidence_set.items), 3)
        self.assertEqual(result.raw_read_count, 3)
        self.assertTrue(
            all(
                item.selection_reasons[0].startswith("structural_evidence.v1:")
                for item in result.evidence_set.items
            )
        )

    def test_source_diversity_does_not_change_relevance_admission(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for name in ("one", "two", "three"):
                publish_record(
                    vault,
                    _record(
                        name,
                        f"Shared retrieval evidence appears in source {name}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="compare shared retrieval evidence",
                        ),
                    ),
                )
            )

        self.assertEqual(result.candidate_set.count, 3)
        self.assertEqual(len(result.evidence_set.items), 3)

    def test_source_identity_does_not_inflate_partial_content_score(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "NASA",
                    "Risk appears in an unrelated bibliography entry.",
                ),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="NASA risk threshold mitigation",
                        ),
                    ),
                )
            )

        self.assertGreater(result.candidate_set.count, 0)
        self.assertEqual(len(result.evidence_set.items), 1)
        self.assertEqual(result.status, "candidates")
        reasons = result.evidence_set.items[0].selection_reasons
        self.assertIn(":decision=selected:", reasons[0])

    def test_source_scope_preserves_raw_that_matches_content_obligation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "NASA",
                    "A risk threshold triggers mitigation and contingency planning.",
                ),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="NASA risk threshold",
                        ),
                    ),
                )
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(len(result.evidence_set.items), 1)
        reason = result.evidence_set.items[0].selection_reasons[0]
        self.assertIn(":decision=selected:", reason)

    def test_navigation_scope_filters_only_its_own_expression(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for name in ("alpha", "beta"):
                publish_record(
                    vault,
                    _record(
                        name,
                        f"Shared risk governance evidence from {name}.",
                    ),
                )
            VaultMaterializer().reconcile(vault, force=True)
            resolved = ResolvedVault(
                path=vault,
                vault_id="test",
                vault_name="Test",
            )
            with patch(
                "knoarbor.pipelines.query_batch.resolve_navigation_region_scopes",
                return_value={"region_alpha": NavigationRegionScope(
                    region_id="region_alpha",
                    source_record_ids=frozenset({"source:alpha"}),
                    source_unit_ids=frozenset({"unit:alpha"}),
                )},
            ):
                result = QueryBatchPipeline().run(
                    QueryBatchRequest(
                        vaults=(resolved,),
                        expressions=(
                            QueryBatchExpression(
                                query_id="literal",
                                query="shared risk governance",
                            ),
                            QueryBatchExpression(
                                query_id="direction",
                                query="alpha shared risk governance",
                                region_id="region_alpha",
                            ),
                        ),
                    )
                )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(
            [
                item.read.raw_evidence.source_record_id
                for item in result.evidence_set.items
            ],
            ["source:alpha", "source:beta"],
        )
        beta = next(
            item
            for item in result.evidence_set.items
            if item.read.raw_evidence.source_record_id == "source:beta"
        )
        self.assertEqual(beta.query_ids, ("literal",))

    def test_navigation_region_scopes_unchanged_query_to_source_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            record = _record(
                "nasa",
                "Technical risk management overview.",
            )
            record.source_units[0].title = "6.4 Technical Risk Management"
            record.source_units.extend(
                [
                    SourceUnitRecord(
                        source_unit_id="unit:nasa-child",
                        raw_record_id=record.raw_record_id,
                        raw_revision_id=record.raw_revision_id,
                        unit_index=1,
                        title="6.4.1 Risk Thresholds",
                        content="A threshold triggers mitigation.",
                        excerpt="A threshold triggers mitigation.",
                        source_path="raw/nasa.md",
                    ),
                    SourceUnitRecord(
                        source_unit_id="unit:nasa-other",
                        raw_record_id=record.raw_record_id,
                        raw_revision_id=record.raw_revision_id,
                        unit_index=2,
                        title="7.0 Unrelated",
                        content="Unrelated appendix material.",
                        excerpt="Unrelated appendix material.",
                        source_path="raw/nasa.md",
                    ),
                ]
            )
            publish_record(vault, record)
            VaultMaterializer().reconcile(vault, force=True)
            resolved = ResolvedVault(path=vault, vault_id="test")
            with patch(
                "knoarbor.pipelines.query_batch.resolve_navigation_region_scopes",
                return_value={"region_risk": NavigationRegionScope(
                    region_id="region_risk",
                    source_record_ids=frozenset({"source:nasa"}),
                    source_unit_ids=frozenset(
                        {"unit:nasa", "unit:nasa-child"}
                    ),
                )},
            ):
                result = QueryBatchPipeline().run(
                    QueryBatchRequest(
                        vaults=(resolved,),
                        expressions=(
                            QueryBatchExpression(
                                query_id="direction",
                                query="threshold triggers mitigation",
                                region_id="region_risk",
                            ),
                        ),
                    )
                )

        self.assertEqual(result.raw_read_count, 1)
        self.assertEqual(
            {
                item.read.raw_evidence.title
                for item in result.evidence_set.items
            },
            {"6.4.1 Risk Thresholds"},
        )
        self.assertNotIn(
            "navigation_scope_no_literal_overlap",
            result.warnings,
        )
        self.assertTrue(
            all(
                "region_membership" not in item.selection_reasons
                for item in result.evidence_set.items
            )
        )

    def test_navigation_region_excludes_raw_outside_selected_scope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            record = _record(
                "handbook",
                "Selected section background.",
            )
            record.source_units[0].title = "2.0 Selected Section"
            record.source_units.append(
                SourceUnitRecord(
                    source_unit_id="unit:handbook-answer",
                    raw_record_id=record.raw_record_id,
                    raw_revision_id=record.raw_revision_id,
                    unit_index=1,
                    title="8.0 Actual Answer",
                    content="Unique fallback evidence answers the question.",
                    excerpt="Unique fallback evidence answers the question.",
                    source_path="raw/handbook.md",
                )
            )
            publish_record(vault, record)
            VaultMaterializer().reconcile(vault, force=True)
            resolved = ResolvedVault(path=vault, vault_id="test")
            with patch(
                "knoarbor.pipelines.query_batch.resolve_navigation_region_scopes",
                return_value={"region_selected": NavigationRegionScope(
                    region_id="region_selected",
                    source_record_ids=frozenset({"source:handbook"}),
                    source_unit_ids=frozenset({"unit:handbook"}),
                )},
            ):
                result = QueryBatchPipeline().run(
                    QueryBatchRequest(
                        vaults=(resolved,),
                        expressions=(
                            QueryBatchExpression(
                                query_id="direction",
                                query="unique fallback evidence",
                                region_id="region_selected",
                            ),
                        ),
                    )
                )

        self.assertEqual(result.raw_read_count, 0)
        self.assertEqual(result.status, "no_match")
        channel_statuses = result.query_results[0]["outcomes"][0][
            "channel_statuses"
        ]
        self.assertEqual(
            next(
                item["fts_hit_count"]
                for item in channel_statuses
                if item["channel"] == "raw_lexical"
            ),
            0,
        )
        self.assertNotIn(
            "navigation_scope_no_literal_overlap",
            result.warnings,
        )

    def test_batch_keeps_independently_relevant_expression_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("alpha", "Alpha protocol coordinates factory devices."),
            )
            publish_record(
                vault,
                _record("beta", "Beta topology connects research services."),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="alpha",
                            query="alpha protocol factory",
                        ),
                        QueryBatchExpression(
                            query_id="beta",
                            query="beta topology research",
                        ),
                    ),
                )
            )

        self.assertEqual(len(result.evidence_set.items), 2)
        self.assertEqual(
            {
                item.read.handle.source_record_id
                for item in result.evidence_set.items
            },
            {"source:alpha", "source:beta"},
        )
        self.assertTrue(
            all(
                reason.startswith("structural_evidence.v1:")
                for item in result.evidence_set.items
                for reason in item.selection_reasons
            )
        )

    def test_literal_and_semantic_expressions_share_one_relevance_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("alpha", "Alpha protocol coordinates factory devices."),
            )
            publish_record(
                vault,
                _record("beta", "Beta topology connects research services."),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="compare alpha and beta",
                        ),
                        QueryBatchExpression(
                            query_id="alpha",
                            query="alpha protocol factory",
                        ),
                        QueryBatchExpression(
                            query_id="beta",
                            query="beta topology research",
                        ),
                    ),
                )
            )

        self.assertEqual(
            {
                item.read.handle.source_record_id
                for item in result.evidence_set.items
            },
            {"source:alpha", "source:beta"},
        )

    def test_optional_expression_cannot_remove_literal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "literal",
                    "Alpha protocol coordinates factory devices.",
                ),
            )
            VaultMaterializer().reconcile(vault, force=True)

            literal_only = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="alpha protocol factory",
                        ),
                    ),
                )
            )
            with_optional = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="optional",
                            query="unrelated astronomy observation",
                        ),
                        QueryBatchExpression(
                            query_id="literal",
                            query="alpha protocol factory",
                        ),
                    ),
                )
            )

        self.assertEqual(
            {
                item.read.handle.evidence_id
                for item in literal_only.evidence_set.items
            },
            {
                item.read.handle.evidence_id
                for item in with_optional.evidence_set.items
            },
        )

    def test_candidate_status_without_selected_raw_is_no_match(self) -> None:
        self.assertEqual(
            _batch_status(["candidates"], has_evidence=False),
            "no_match",
        )

    def test_literal_terminal_failure_is_not_hidden_by_optional_evidence(
        self,
    ) -> None:
        self.assertEqual(
            _batch_status(
                ["resource_exhausted", "candidates"],
                has_evidence=True,
            ),
            "resource_exhausted",
        )
        self.assertEqual(
            _batch_status(
                ["candidates", "resource_exhausted"],
                has_evidence=True,
            ),
            "candidates",
        )

    def test_one_vault_failure_keeps_expression_incomplete(self) -> None:
        self.assertEqual(
            _expression_status(
                [
                    SimpleNamespace(
                        status="candidates",
                        exhausted=True,
                        channel_statuses=[],
                    ),
                    SimpleNamespace(
                        status="index_unavailable",
                        exhausted=False,
                        channel_statuses=[],
                    ),
                ]
            ),
            "index_unavailable",
        )

    def test_standalone_query_preserves_partial_content_for_semantic_filter(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("weak", "Alpha and beta appear here."),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="alpha beta gamma delta epsilon zeta",
                )
            )

        self.assertGreater(len(result.handles), 0)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.status, "candidates")

    def test_batch_records_structural_candidate_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("weak", "Alpha and beta appear here."),
            )
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(
                        ResolvedVault(
                            path=vault,
                            vault_id="test",
                            vault_name="Test",
                        ),
                    ),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="alpha beta gamma delta epsilon zeta",
                        ),
                    ),
                )
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.candidate_set.count, 1)
        reasons = next(
            iter(result.candidate_set.structural_decisions.values())
        )
        self.assertIn(":decision=selected:", reasons[0])
        self.assertIn(":channels=", reasons[0])
        self.assertIn(":spans=", reasons[0])

    def test_relation_only_expression_is_searchable_without_score_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="连接路径是什么",
                )
            )

        self.assertNotEqual(result.status, "invalid_query")

    def test_query_owner_returns_trustworthy_batch_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            VaultMaterializer().reconcile(vault, force=True)

            result = QueryBatchPipeline().run(
                QueryBatchRequest(
                    vaults=(ResolvedVault(path=vault, vault_id="test", vault_name="Test"),),
                    expressions=(
                        QueryBatchExpression(
                            query_id="literal",
                            query="uniquetermthatdoesnotexist",
                        ),
                    ),
                )
            )

        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.candidate_set.count, 0)
        self.assertEqual(result.evidence_set.items, ())
        self.assertEqual(result.raw_read_rounds, 0)


if __name__ == "__main__":
    unittest.main()
