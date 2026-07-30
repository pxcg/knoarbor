from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.raw_evidence import OriginalSourceRecord, SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.presenters.wiki_context import search_query
from knoarbor.retrieval.unified import (
    QueryPlan,
    RecallSignal,
    UnifiedActiveRawRetriever,
    _best_channel_rank_score,
    _resolve_active_evidence,
)
from knoarbor.runtime.run_monitor import RunCancelled
from knoarbor.storage.index_snapshot import open_index_snapshot
from knoarbor.storage.lexical_snapshot import (
    RetrievalSafety,
    RetrievalSafetyExceeded,
    read_atom_batch_documents,
    read_raw_locator_metadata_by_evidence_ids,
    search_lexical_snapshot,
    verify_lexical_snapshot,
)
from knoarbor.storage.materialization import VaultMaterializer
from tests.transactional_ingest_helpers import publish_batch, publish_record


class SemanticIndexedQueryTests(unittest.TestCase):
    def test_atom_claim_scope_uses_plural_source_unit_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "resilience",
                    "Alpha sends telemetry to Bridge.",
                    source_unit_id="unit:resilience",
                ),
                _relation_batch(
                    source_id="source:resilience",
                    source_unit_id="unit:resilience",
                    claim_id="claim:resilience",
                    claim="Alpha sends telemetry to Bridge.",
                    subject=("ent:alpha", "Alpha"),
                    predicate="sends telemetry to",
                    obj=("ent:bridge", "Bridge"),
                ),
            )
            _materialize(vault)
            snapshot = open_index_snapshot(vault)
            assert snapshot is not None

            selected = search_lexical_snapshot(
                snapshot.retrieval_path,
                "Alpha telemetry",
                channel="atom_claim",
                safety=RetrievalSafety.with_timeout(),
                source_record_ids=frozenset({"source:resilience"}),
                source_unit_ids=frozenset({"unit:resilience"}),
            )
            excluded = search_lexical_snapshot(
                snapshot.retrieval_path,
                "Alpha telemetry",
                channel="atom_claim",
                safety=RetrievalSafety.with_timeout(),
                source_record_ids=frozenset({"source:resilience"}),
                source_unit_ids=frozenset({"unit:other"}),
            )

        self.assertGreater(len(selected.matches), 0)
        self.assertIn(
            "claim",
            {
                item.metadata["atom_type"]
                for item in selected.matches
            },
        )
        self.assertEqual(excluded.matches, ())

    def test_duplicate_locator_volume_does_not_increase_parent_rank_score(
        self,
    ) -> None:
        best = RecallSignal(
            channel="raw_lexical",
            channel_rank=1,
            channel_score=10.0,
        )
        duplicates = [
            RecallSignal(
                channel="raw_lexical",
                channel_rank=rank,
                channel_score=10.0 / rank,
            )
            for rank in range(2, 20)
        ]

        self.assertEqual(
            _best_channel_rank_score([best]),
            _best_channel_rank_score([best, *duplicates]),
        )

    def test_claim_only_handle_hydrates_raw_metadata_and_exact_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            _materialize(vault)

            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="dynamic tool decisions"))

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.retrieval_mode, "unified_active_raw_lexical")
        self.assertEqual(len(result.handles), 1)
        self.assertEqual(result.matches[0].raw_evidence.source_unit_id, "unit:rawrev:test")
        handle = result.handles[0]
        self.assertEqual(
            {signal.channel for signal in handle.signals},
            {"atom_claim"},
        )
        self.assertEqual(handle.source_path, "raw/test.md")
        self.assertEqual(
            handle.signals[0].matched_spans,
            ((0, len("Test source evidence.")),),
        )
        self.assertEqual(result.stats["retrieval_strategy"], "unified_active_raw_lexical_v1")

    def test_claim_resolution_reads_each_matching_atom_batch_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            _materialize(vault)

            with patch(
                "knoarbor.retrieval.unified.read_atom_batch_documents",
                wraps=read_atom_batch_documents,
            ) as read_batch:
                result = QueryPipeline().run(
                    QueryPipelineRequest(
                        vault_path=vault,
                        query="Agent Loop coordinates Tools",
                    )
                )
        self.assertEqual(result.status, "candidates")
        self.assertEqual(
            {item.atom.atom_type for item in result.atom_candidates},
            {"claim", "entity", "relation"},
        )
        self.assertEqual(read_batch.call_count, 1)

    def test_named_source_semantic_variant_ranks_matching_sibling_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            record = _record("openclaw", "placeholder")
            record = record.model_copy(
                update={
                    "source_units": [
                        SourceUnitRecord(
                            source_unit_id="unit:openclaw-overview",
                            raw_record_id=record.raw_record_id,
                            raw_revision_id=record.raw_revision_id,
                            unit_index=0,
                            title="总体架构",
                            content="Pi Agent 维护主循环、会话状态和工具调用。",
                            excerpt="Pi Agent 维护主循环、会话状态和工具调用。",
                            source_path="raw/OpenClaw架构.md",
                        ),
                        SourceUnitRecord(
                            source_unit_id="unit:openclaw-messagebus",
                            raw_record_id=record.raw_record_id,
                            raw_revision_id=record.raw_revision_id,
                            unit_index=1,
                            title="消息流",
                            content="MessageBus 是渠道和 Agent 之间的解耦层。",
                            excerpt="MessageBus 是渠道和 Agent 之间的解耦层。",
                            source_path="raw/OpenClaw架构.md",
                        ),
                    ]
                }
            )
            publish_record(vault, record, KnowledgeAtomBatch(source_record_id=record.source_record_id))
            _materialize(vault)

            result = QueryPipeline().run(
                QueryPipelineRequest(vault_path=vault, query="OpenClaw 解耦层")
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(
            result.matches[0].raw_evidence.source_unit_id,
            "unit:openclaw-messagebus",
        )
        self.assertEqual(
            {item.raw_evidence.source_unit_id for item in result.matches},
            {"unit:openclaw-messagebus", "unit:openclaw-overview"},
        )

    def test_real_low_budget_query_never_promises_offset_zero_progress(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "resilience",
                    "Alpha sends telemetry to Bridge.",
                    source_unit_id="unit:resilience",
                ),
                _relation_batch(
                    source_id="source:resilience",
                    source_unit_id="unit:resilience",
                    claim_id="claim:resilience",
                    claim="Alpha sends telemetry to Bridge.",
                    subject=("ent:alpha", "Alpha"),
                    predicate="sends telemetry to",
                    obj=("ent:bridge", "Bridge"),
                ),
            )
            _materialize(vault)
            retriever = UnifiedActiveRawRetriever()
            plan = QueryPlan(
                vault_path=vault,
                query="Alpha",
                safety=RetrievalSafety(
                    max_accumulated_bytes=1,
                    max_materialized_bytes=1,
                ),
            )
            first = retriever.retrieve(plan)
            second = retriever.retrieve(plan)

        for result in (first, second):
            self.assertEqual(result.status, "resource_exhausted")
            self.assertFalse(result.exhausted)
            self.assertIsNone(result.continuation_cursor)

    def test_raw_only_extraction_miss_remains_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)

            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="source evidence"))

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.claim_candidates, [])
        self.assertEqual(len(result.matches), 1)
        self.assertTrue(all(signal.channel == "raw_lexical" for signal in result.handles[0].signals))

    def test_raw_locator_window_reads_the_complete_parent_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            content = " ".join([*(f"filler{index}" for index in range(420)), "uniqueterminalfact"])
            publish_record(vault, _record("long", content), KnowledgeAtomBatch(source_record_id="source:long"))
            _materialize(vault)

            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="uniqueterminalfact"))

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.matches[0].raw_evidence.content, content)
        raw_signals = [signal for signal in result.handles[0].signals if signal.channel == "raw_lexical"]
        self.assertTrue(raw_signals)
        self.assertLess(raw_signals[0].matched_spans[0][0], len(content))

    def test_handle_only_query_does_not_resolve_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)

            with patch(
                "knoarbor.retrieval.unified._resolve_active_evidence",
                side_effect=AssertionError("handle-only recall must not resolve Raw"),
            ):
                result = QueryPipeline().run(
                    QueryPipelineRequest(
                        vault_path=vault,
                        query="dynamic tool decisions",
                        resolve_evidence=False,
                    )
                )

        self.assertEqual(result.status, "candidates")
        self.assertTrue(result.handles)
        self.assertEqual(result.matches, [])

    def test_raw_locator_metadata_is_compact_and_keeps_exact_rerank_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            content = " ".join(f"locator-{index}" for index in range(700))
            publish_record(vault, _record("compact", content), KnowledgeAtomBatch(source_record_id="source:compact"))
            _materialize(vault)
            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="locator-699"))
            snapshot = open_index_snapshot(vault)
            assert snapshot is not None

            rows = read_raw_locator_metadata_by_evidence_ids(
                snapshot.retrieval_path,
                [result.handles[0].evidence_id],
            )
            with closing(
                sqlite3.connect(snapshot.retrieval_path)
            ) as connection:
                window_metadata = [
                    json.loads(row[0])
                    for row in connection.execute(
                        """
                        select metadata_json
                          from retrieval_documents
                         where channel='raw_lexical'
                        """
                    )
                ]
                raw_unit_count = connection.execute(
                    "select count(*) from retrieval_raw_units"
                ).fetchone()[0]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rerank_text"], content)
        self.assertGreater(len(window_metadata), 1)
        self.assertEqual(raw_unit_count, 1)
        self.assertTrue(
            all("rerank_text" not in item for item in window_metadata)
        )
        self.assertTrue(
            {"evidence_id", "revision_id", "raw_revision_id", "source_unit_id", "window_char_start"}
            <= rows[0].keys()
        )
        self.assertTrue(
            {"content", "excerpt", "locator_atom_ids", "raw_indexes", "metadata"}.isdisjoint(rows[0])
        )
        self.assertEqual(result.matches[0].raw_evidence.content, content)

    def test_atom_locator_metadata_omits_duplicate_evidence_excerpts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)
            snapshot = open_index_snapshot(vault)
            assert snapshot is not None
            with closing(
                sqlite3.connect(snapshot.retrieval_path)
            ) as connection:
                revision_id = next(
                    item["revision_id"]
                    for item in (
                        json.loads(row[0])
                        for row in connection.execute(
                            """
                            select metadata_json
                              from retrieval_documents
                             where channel='atom_claim'
                            """
                        )
                    )
                    if item.get("revision_id")
                )
            atoms = read_atom_batch_documents(
                snapshot.retrieval_path,
                revision_id=revision_id,
                source_record_id="source:test",
            )

        entity = next(
            item for item in atoms if item["atom_type"] == "entity"
        )
        relation = next(
            item for item in atoms if item["atom_type"] == "relation"
        )
        claim = next(
            item for item in atoms if item["atom_type"] == "claim"
        )
        self.assertEqual(entity["evidence"], [])
        self.assertEqual(relation["evidence"], [])
        self.assertTrue(claim["evidence"])
        self.assertTrue(
            all(
                set(item)
                <= {
                    "source_unit_id",
                    "char_start",
                    "char_end",
                    "excerpt",
                }
                for item in claim["evidence"]
            )
        )

    def test_active_evidence_resolution_reads_verified_facts_not_locator_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            content = "Fact authority remains in the immutable source revision."
            publish_record(vault, _record("authority", content), KnowledgeAtomBatch(source_record_id="source:authority"))
            _materialize(vault)
            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="immutable source revision"))

            reads, warnings = _resolve_active_evidence(vault, result.handles)

        self.assertEqual(warnings, [])
        self.assertEqual(reads[0].raw_evidence.content, content)

    def test_v3_lexical_snapshot_is_rejected_for_lifecycle_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("schema", "Schema replacement evidence."),
                KnowledgeAtomBatch(source_record_id="source:schema"),
            )
            _materialize(vault)
            snapshot = open_index_snapshot(vault)
            assert snapshot is not None
            with closing(sqlite3.connect(snapshot.retrieval_path)) as connection:
                connection.execute(
                    "update retrieval_metadata set value=? where key='schema_version'",
                    (json.dumps("lexical_snapshot.v3"),),
                )
                connection.commit()

            with self.assertRaisesRegex(RuntimeError, "schema is unsupported"):
                verify_lexical_snapshot(snapshot.retrieval_path)

    def test_relation_source_claim_ids_resolve_only_inside_their_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            evidence_a = [KnowledgeEvidenceSpan(source_record_id="source:a", source_unit_id="unit:a", source_unit_index=0)]
            evidence_b = [KnowledgeEvidenceSpan(source_record_id="source:b", source_unit_id="unit:b", source_unit_index=0)]
            batch_a = KnowledgeAtomBatch(
                source_record_id="source:a",
                claims=[KnowledgeClaim(id="C1", claim="Alpha owns the correct evidence.", evidence=evidence_a)],
                relations=[
                    KnowledgeRelation(
                        id="R1",
                        subject=KnowledgeAtomObject(name="Alpha"),
                        predicate="coordinates",
                        object=KnowledgeAtomObject(name="Tools"),
                        source_claim_ids=["C1"],
                        evidence=evidence_a,
                    )
                ],
            )
            batch_b = KnowledgeAtomBatch(
                source_record_id="source:b",
                claims=[KnowledgeClaim(id="C1", claim="Wrong colliding claim.", evidence=evidence_b)],
            )
            publish_record(vault, _record("a", "Alpha evidence.", source_unit_id="unit:a"), batch_a)
            publish_record(vault, _record("b", "Wrong evidence.", source_unit_id="unit:b"), batch_b)
            _materialize(vault)

            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="coordinates tools"))

        self.assertEqual(result.status, "candidates")
        self.assertEqual([item.claim.source_record_id for item in result.claim_candidates], ["source:a"])
        self.assertEqual([item.raw_evidence.source_record_id for item in result.matches], ["source:a"])

    def test_synthesis_is_not_materialized_as_retrieval_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            _materialize(vault)
            snapshot = open_index_snapshot(vault)
            assert snapshot is not None

            with closing(sqlite3.connect(snapshot.retrieval_path)) as connection:
                atom_metadata = [
                    json.loads(row[0])
                    for row in connection.execute(
                        "select metadata_json from retrieval_documents where channel='atom_claim'"
                    )
                ]
            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="Adaptive orchestration patterns",
                )
            )

        self.assertNotIn(
            "synthesis",
            {item.get("atom_type") for item in atom_metadata},
        )
        self.assertFalse(
            any(item.atom.atom_type == "synthesis" for item in result.atom_candidates)
        )

    def test_missing_snapshot_is_typed_unavailable_without_runtime_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())

            result = QueryPipeline().run(QueryPipelineRequest(vault_path=vault, query="dynamic tool decisions"))

        self.assertEqual(result.status, "index_unavailable")
        self.assertEqual(result.matches, [])
        self.assertIn("No verified lexical retrieval snapshot", result.warnings[0])

    def test_safety_exhaustion_is_not_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="dynamic tool decisions",
                    safety=RetrievalSafety.with_timeout(None, max_accumulated_bytes=1),
                )
            )

        self.assertEqual(result.status, "resource_exhausted")
        self.assertNotEqual(result.status, "no_match")
        self.assertFalse(result.channel_statuses[-1].exhausted)

    def test_cancellation_is_typed_and_never_becomes_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)

            def cancelled() -> None:
                raise RunCancelled("cancelled by test")

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="dynamic tool decisions",
                    safety=RetrievalSafety.with_timeout(raise_if_cancelled=cancelled),
                )
            )

        self.assertEqual(result.status, "cancelled")
        self.assertNotEqual(result.status, "no_match")

    def test_cancellation_during_snapshot_verification_is_typed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch())
            _materialize(vault)
            checks = 0

            def cancel_during_snapshot() -> None:
                nonlocal checks
                checks += 1
                if checks == 3:
                    raise RunCancelled("cancelled during snapshot verification")

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="dynamic tool decisions",
                    safety=RetrievalSafety.with_timeout(
                        raise_if_cancelled=cancel_during_snapshot,
                    ),
                )
            )

        self.assertEqual(result.status, "cancelled")
        self.assertGreaterEqual(checks, 3)

    def test_public_query_contract_is_v4_with_separate_handles_and_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            _materialize(vault)

            response = search_query(
                WikiSearchRequest(vault_path=str(vault), query="dynamic tool decisions", record_query=False)
            )

        payload = response.model_dump()
        self.assertEqual(response.schema_version, "wiki_query.v4")
        self.assertEqual(response.status, "candidates")
        self.assertEqual(len(response.evidence_handles), 1)
        self.assertEqual(len(response.raw_evidence), 1)
        self.assertEqual(response.evidence_handles[0].evidence_id, response.raw_evidence[0].evidence_id)
        self.assertNotIn("evidence_coverage", payload)
        self.assertNotIn("response_guidance", payload)
        self.assertNotIn("gap_suggestions", payload)

    def test_incidental_cjk_overlap_remains_a_bm25_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "industrial",
                    "工业智能化架构包含机器层和数据代理层。数据代理负责数据分发。",
                    source_unit_id="unit:industrial",
                ),
                KnowledgeAtomBatch(source_record_id="source:industrial"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="这套架构的年度预算和项目负责人是谁")
            )

        self.assertEqual(result.status, "candidates")
        self.assertGreater(len(result.handles), 0)
        raw_status = next(item for item in result.channel_statuses if item.channel == "raw_lexical")
        self.assertGreater(raw_status.fts_hit_count, 0)
        self.assertEqual(raw_status.ineligible_hit_count, 0)

    def test_cjk_bigrams_remain_bm25_recall_terms_without_a_boolean_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "coordination",
                    "团队通过合作改善治理机制，这一作用需要持续评估。",
                    source_unit_id="unit:coordination",
                ),
                KnowledgeAtomBatch(source_record_id="source:coordination"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="光合作用")
            )
            wrapped_result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="用一句话解释光合作用")
            )

        self.assertEqual(result.status, "candidates")
        self.assertGreater(len(result.handles), 0)
        self.assertEqual(wrapped_result.status, "candidates")
        self.assertGreater(len(wrapped_result.handles), 0)

    def test_strong_partial_anchor_remains_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "industrial",
                    "工业智能化架构包含机器层和数据代理层。",
                    source_unit_id="unit:industrial",
                ),
                KnowledgeAtomBatch(source_record_id="source:industrial"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="工业智能化架构和年度预算")
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(len(result.handles), 1)

    def test_unknown_identifier_does_not_pass_on_generic_protocol_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record(
                    "adaptor",
                    "数据适配层负责协议转换和数据格式统一。",
                    source_unit_id="unit:adaptor",
                ),
                KnowledgeAtomBatch(source_record_id="source:adaptor"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="量子海豚协议 ZXQ-9917 的维护窗口是什么")
            )

        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.handles, ())

    def test_compound_identifier_does_not_enumerate_colliding_numeric_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("cell", "CELL-0000 负责设备状态采集。", source_unit_id="unit:cell"),
                KnowledgeAtomBatch(source_record_id="source:cell"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="ABSENT-0000")
            )

        self.assertEqual(result.status, "no_match")
        raw_status = next(item for item in result.channel_statuses if item.channel == "raw_lexical")
        self.assertEqual(raw_status.fts_hit_count, 0)

    def test_compound_identifier_reaches_space_separated_original_parts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_record(
                vault,
                _record("compound", "设备标识 ABSENT 0000 需要联合校验。", source_unit_id="unit:compound"),
                KnowledgeAtomBatch(source_record_id="source:compound"),
            )
            _materialize(vault)

            result = UnifiedActiveRawRetriever().retrieve(
                QueryPlan(vault_path=vault, query="ABSENT-0000")
            )

        self.assertEqual(result.status, "candidates")
        self.assertEqual(result.handles[0].source_record_id, "source:compound")

    def test_materialized_safety_continuation_preserves_complete_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for index in range(20):
                name = f"safety-{index:02d}"
                publish_record(
                    vault,
                    _record(name, f"工业协议证据 {index:02d}。"),
                    KnowledgeAtomBatch(source_record_id=f"source:{name}"),
                )
            _materialize(vault)
            snapshot = open_index_snapshot(vault)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None

            complete = search_lexical_snapshot(
                snapshot.retrieval_path,
                "工业协议",
                channel="raw_lexical",
                safety=RetrievalSafety.with_timeout(
                    None,
                    max_accumulated_bytes=None,
                    max_materialized_bytes=None,
                ),
            )
            resumed = []
            offset = 0
            rank_offset = 0
            exhaustion_count = 0
            while True:
                try:
                    final_page = search_lexical_snapshot(
                        snapshot.retrieval_path,
                        "工业协议",
                        channel="raw_lexical",
                        safety=RetrievalSafety.with_timeout(
                            None,
                            max_accumulated_bytes=None,
                            max_materialized_bytes=8_000,
                        ),
                        offset=offset,
                        rank_offset=rank_offset,
                    )
                except RetrievalSafetyExceeded as exc:
                    self.assertEqual(exc.reason, "materialized_bytes")
                    self.assertTrue(exc.partial_matches)
                    self.assertGreater(exc.continuation_offset, offset)
                    resumed.extend(exc.partial_matches)
                    offset = exc.continuation_offset
                    rank_offset = exc.continuation_rank
                    exhaustion_count += 1
                    continue
                resumed.extend(final_page.matches)
                break

        self.assertGreater(exhaustion_count, 0)
        self.assertEqual(
            [(match.doc_id, match.rank) for match in resumed],
            [(match.doc_id, match.rank) for match in complete.matches],
        )

    def test_unified_cursor_is_opaque_query_bound_and_completes_all_handles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            for index in range(20):
                name = f"cursor-{index:02d}"
                publish_record(
                    vault,
                    _record(name, f"工业协议游标证据 {index:02d}。"),
                    KnowledgeAtomBatch(source_record_id=f"source:{name}"),
                )
            _materialize(vault)
            retriever = UnifiedActiveRawRetriever()
            complete = retriever.retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="工业协议游标",
                    safety=RetrievalSafety.with_timeout(
                        None,
                        max_accumulated_bytes=None,
                        max_materialized_bytes=None,
                    ),
                )
            )

            cursor = None
            resumed_ids: list[str] = []
            exhaustion_count = 0
            while True:
                page = retriever.retrieve(
                    QueryPlan(
                        vault_path=vault,
                        query="工业协议游标",
                        continuation_cursor=cursor,
                        safety=RetrievalSafety.with_timeout(
                            None,
                            max_accumulated_bytes=None,
                            max_materialized_bytes=8_000,
                        ),
                    )
                )
                resumed_ids.extend(handle.evidence_id for handle in page.handles)
                if page.exhausted:
                    break
                self.assertEqual(page.status, "resource_exhausted")
                self.assertTrue(page.continuation_cursor)
                self.assertTrue(page.continuation_cursor.startswith("retrieval_cursor.v1."))
                cursor = page.continuation_cursor
                exhaustion_count += 1

            mismatched = retriever.retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="另一个查询",
                    continuation_cursor=cursor,
                )
            )
            publish_record(
                vault,
                _record("cursor-new-generation", "工业协议游标新证据。"),
                KnowledgeAtomBatch(source_record_id="source:cursor-new-generation"),
            )
            _materialize(vault)
            stale_generation = retriever.retrieve(
                QueryPlan(
                    vault_path=vault,
                    query="工业协议游标",
                    continuation_cursor=cursor,
                )
            )

        self.assertGreater(exhaustion_count, 0)
        self.assertEqual(resumed_ids, [handle.evidence_id for handle in complete.handles])
        self.assertEqual(mismatched.status, "invalid_query")
        self.assertIn("retrieval_cursor_query_mismatch", mismatched.warnings)
        self.assertEqual(stale_generation.status, "index_unavailable")
        self.assertIn("retrieval_cursor_generation_mismatch", stale_generation.warnings)


def _materialize(vault: Path) -> None:
    state = VaultMaterializer().reconcile(vault, force=True)
    if state["phase"] != "clean":
        raise AssertionError(state)


def _record(name: str, content: str, *, source_unit_id: str | None = None) -> SourceProcessingRecord:
    source_id = f"source:{name}"
    raw_record_id = f"raw:{name}"
    raw_revision_id = f"rawrev:{name}"
    return SourceProcessingRecord(
        processing_record_id=f"spr:{name}",
        raw_record_id=raw_record_id,
        raw_revision_id=raw_revision_id,
        source_record_id=source_id,
        source=OriginalSourceRecord(
            raw_record_id=raw_record_id,
            raw_revision_id=raw_revision_id,
            source_id=source_id,
            raw_path=f"raw/{name}.md",
        ),
        source_units=[
            SourceUnitRecord(
                source_unit_id=source_unit_id or f"unit:{name}",
                raw_record_id=raw_record_id,
                raw_revision_id=raw_revision_id,
                unit_index=0,
                content=content,
                excerpt=content,
                source_path=f"raw/{name}.md",
            )
        ],
    )


def _batch() -> KnowledgeAtomBatch:
    evidence = [KnowledgeEvidenceSpan(source_record_id="source:test", excerpt="Test source evidence.")]
    entity = KnowledgeAtomObject(
        object_type="knowledge_object",
        name="Agent Loop",
        atom_id="entity:agent-loop",
        aliases=["智能体循环"],
        evidence=evidence,
    )
    claim = KnowledgeClaim(
        id="claim:loop",
        claim="Agent loops make dynamic tool decisions.",
        entity_names=["Agent Loop"],
        entity_ids=["entity:agent-loop"],
        evidence=evidence,
    )
    relation = KnowledgeRelation(
        id="relation:coordinates",
        subject=KnowledgeAtomObject(name="Agent Loop", atom_id="entity:agent-loop"),
        predicate="coordinates",
        object=KnowledgeAtomObject(name="Tools", atom_id="entity:tools"),
        source_claim_ids=["claim:loop"],
        evidence=evidence,
    )
    return KnowledgeAtomBatch(
        source_record_id="source:test",
        entities=[entity],
        claims=[claim],
        relations=[relation],
        synthesis="Adaptive orchestration patterns.",
    )


def _relation_batch(
    *,
    source_id: str,
    source_unit_id: str,
    claim_id: str,
    claim: str,
    subject: tuple[str, str],
    predicate: str,
    obj: tuple[str, str],
) -> KnowledgeAtomBatch:
    evidence = [KnowledgeEvidenceSpan(source_record_id=source_id, source_unit_id=source_unit_id, excerpt=claim)]
    entities = [
        KnowledgeAtomObject(name=name, atom_id=entity_id, evidence=evidence)
        for entity_id, name in (subject, obj)
    ]
    return KnowledgeAtomBatch(
        source_record_id=source_id,
        entities=entities,
        claims=[
            KnowledgeClaim(
                id=claim_id,
                claim=claim,
                evidence=evidence,
                entity_names=[subject[1], obj[1]],
                entity_ids=[subject[0], obj[0]],
            )
        ],
        relations=[
            KnowledgeRelation(
                id=f"relation:{claim_id}",
                subject=KnowledgeAtomObject(name=subject[1], atom_id=subject[0]),
                predicate=predicate,
                object=KnowledgeAtomObject(name=obj[1], atom_id=obj[0]),
                source_claim_ids=[claim_id],
                evidence=evidence,
            )
        ],
    )
