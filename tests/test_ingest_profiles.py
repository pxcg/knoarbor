from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from knoarbor.core.config import IngestSegmentationConfig
from knoarbor.core.errors import ModelOutputError, UserInputError
from knoarbor.core.schemas.ingest_run import IngestFileRunRequest, IngestRecoveryRunRequest, UnifiedIngestRequest
from knoarbor.core.schemas.index_metadata_extract import (
    ExtractedAmbiguity,
    ExtractedClaim,
    ExtractedEntity,
    ExtractedEvidenceQuote,
    ExtractedRelation,
    IndexMetadataExtractResult,
)
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.pipelines.index_metadata_atoms import (
    compile_extracted_index_metadata,
    dominant_source_language,
)
from knoarbor.pipelines.ingest_compilation import IndexExtractResult, render_synthesis_topics
from knoarbor.pipelines.ingest_auto import (
    IndexMetadataExtractionFailed,
    AutoIngestPipeline,
    _auto_source_record,
    _index_metadata_extract_payload,
)
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.presenters.wiki_context import search_query
from knoarbor.services.ingest_coordinator import IngestCoordinator
from knoarbor.services.ingest_execution import load_execution_config
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.storage.wiki_paths import content_root
from knoarbor.storage.source_records import read_raw_evidence_records, read_source_processing_records
from knoarbor.storage.entity_registry import read_entity_registry
from tests.ingest_v4_helpers import execute_file_command


class AutoIngestTests(unittest.TestCase):
    def test_ingest_language_hints_preserve_bilingual_source_units(self) -> None:
        from knoarbor.core.hashing import file_content_hash
        from knoarbor.core.source_unitization import attach_source_unitization

        text = (
            "# 中文部分\n\n检索流程保留中文事实，并根据原始材料生成中文 claim。\n\n"
            "# English section\n\nThe retrieval planner preserves English facts and English claims."
        )
        document = attach_source_unitization(
            SourceDocument(
                source_id="unit:bilingual",
                source_type="markdown",
                origin=SourceOrigin(
                    connector="test",
                    uri="file:///bilingual.md",
                    raw_path="/tmp/bilingual.md",
                ),
                content=SourceContent(format="markdown", text=text),
                fingerprint=SourceFingerprint(
                    content_hash=file_content_hash(text),
                    connector_version="test",
                ),
            )
        )
        source_record = _auto_source_record(document, "/tmp/bilingual.md")

        payload = _index_metadata_extract_payload(
            document,
            "/tmp/bilingual.md",
            source_record,
        )

        self.assertEqual(dominant_source_language(document), "mixed")
        self.assertEqual(payload["source"]["language"], "mixed")
        self.assertEqual(
            [unit["language"] for unit in payload["units"]],
            ["zh", "en"],
        )

    def test_explicit_vault_path_survives_execution_config_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configured_vault = root / "configured"
            explicit_vault = root / "explicit"
            init_wiki_vault(configured_vault)
            init_wiki_vault(explicit_vault)
            config_path = _write_config(root, configured_vault)
            coordinator = IngestCoordinator()

            with patch.object(coordinator.scheduler, "submit"):
                started = coordinator.start(
                    UnifiedIngestRequest(
                        kind="excerpt",
                        excerpt_text="explicit vault evidence",
                        config_path=str(config_path),
                        vault_path=str(explicit_vault),
                        write=False,
                    )
                )

            store = TransactionalIngestStore(explicit_vault)
            command = store.command_for_task(str(store.attempt(started.run_id)["task_id"]))
            self.assertIsNone(command.vault_id)
            self.assertEqual(command.vault_path, str(explicit_vault.resolve()))
            self.assertEqual(load_execution_config(command).vault.path, explicit_vault.resolve())

    def test_configured_vault_profile_survives_execution_config_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            default_vault = root / "default"
            personal_vault = root / "personal"
            init_wiki_vault(default_vault)
            init_wiki_vault(personal_vault)
            config_path = _write_profile_config(root, default_vault, personal_vault)
            coordinator = IngestCoordinator()

            with patch.object(coordinator.scheduler, "submit"):
                started = coordinator.start(
                    UnifiedIngestRequest(
                        kind="excerpt",
                        excerpt_text="profile vault evidence",
                        config_path=str(config_path),
                        vault_id="personal",
                        write=False,
                    )
                )

            store = TransactionalIngestStore(personal_vault)
            command = store.command_for_task(str(store.attempt(started.run_id)["task_id"]))
            self.assertEqual(command.vault_id, "personal")
            self.assertEqual(command.vault_path, str(personal_vault.resolve()))
            self.assertEqual(load_execution_config(command).vault.path, personal_vault.resolve())

    def test_profile_path_drift_is_rejected_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            default_vault = root / "default"
            personal_vault = root / "personal"
            moved_vault = root / "moved"
            for vault in (default_vault, personal_vault, moved_vault):
                init_wiki_vault(vault)
            config_path = _write_profile_config(root, default_vault, personal_vault)
            coordinator = IngestCoordinator()
            with patch.object(coordinator.scheduler, "submit"):
                started = coordinator.start(
                    UnifiedIngestRequest(
                        kind="excerpt",
                        excerpt_text="profile drift evidence",
                        config_path=str(config_path),
                        vault_id="personal",
                        write=False,
                    )
                )
            store = TransactionalIngestStore(personal_vault)
            command = store.command_for_task(str(store.attempt(started.run_id)["task_id"]))
            _write_profile_config(root, default_vault, moved_vault)

            with self.assertRaisesRegex(UserInputError, "different vault path"):
                load_execution_config(command)

    def test_segment_synthesis_composes_locator_list_without_truncation(self) -> None:
        synthesis = render_synthesis_topics(
            [
                "预训练、后训练与数据工程",
                "分布式训练与并行策略",
            ]
        )

        self.assertEqual(synthesis, "- 预训练、后训练与数据工程\n- 分布式训练与并行策略")

    def test_recovery_uses_persisted_custom_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            config_path = _write_config(root, vault)
            coordinator = IngestCoordinator()
            with patch.object(coordinator.scheduler, "submit"):
                started = coordinator.start(
                    UnifiedIngestRequest(
                        kind="excerpt",
                        execution="queued",
                        excerpt_text="persisted config evidence",
                        config_path=str(config_path),
                        write=False,
                    )
                )
            store = TransactionalIngestStore(vault)
            attempt = store.attempt(started.run_id)
            task_id = str(attempt["task_id"])
            store.fail_queued_task(
                task_id,
                started.run_id,
                error="retry",
                result={"failure": {"retryable": True}},
            )

            with patch.object(coordinator.scheduler, "submit"):
                recovered = coordinator.recover_task(
                    str(vault),
                    task_id,
                    IngestRecoveryRunRequest(),
                )

            self.assertEqual(recovered.status, "queued")
            self.assertEqual(store.command_for_task(task_id).config_path, str(config_path.resolve()))

    def test_auto_file_ingest_writes_indexes_and_projection_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Fast Note\n\nThis is a simple document for index metadata ingest.", encoding="utf-8")
            config_path = _write_config(root, vault)

            compiler = FakeQuickCompiler()
            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=compiler),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=True,
                        append_ledger=True,
                    )
                )

            self.assertEqual(result.ingest_profile, "auto")
            self.assertEqual(compiler.calls, 1)
            self.assertEqual(result.stats["source_count"], 1)
            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(result.stats["failed_count"], 0)
            self.assertEqual(result.stats["written_count"], 1)
            self.assertEqual(result.metrics["semantic"]["semantic_call_count"], 1)
            self.assertEqual(result.results[0].segments[0]["metrics"]["semantic"]["total_tokens"], 30)
            processing_records = read_source_processing_records(vault)
            self.assertEqual(len(processing_records), 1)
            self.assertTrue(processing_records[0].run_id.startswith("attempt_"))
            written_pages = [path.name for path in content_root(vault).glob("*.md")]
            self.assertEqual(len(written_pages), 1)
            self.assertEqual(len(list(content_root(vault).glob("*.md"))), 1)
            projection = content_root(vault) / written_pages[0]
            projection_content = projection.read_text(encoding="utf-8")
            self.assertIn("projection_kind: source_index", projection_content)
            self.assertIn("not_fact_material: true", projection_content)
            self.assertIn("## Synthesis", projection_content)
            self.assertIn("## Claims", projection_content)
            self.assertIn("## Entities", projection_content)
            self.assertIn("## Relations", projection_content)
            self.assertNotIn("## Source Units", projection_content)
            self.assertIn("source_revision", result.results[0].context)
            self.assertTrue(result.results[0].context["entity_identity"]["registry_bound"])
            self.assertTrue(result.results[0].context["entity_identity"]["entity_ids"])
            self.assertEqual(len(read_entity_registry(vault).entries), 2)
            raw_evidence = read_raw_evidence_records(vault)
            self.assertTrue(raw_evidence)
            self.assertIn("This is a simple document", raw_evidence[0].content)
            self.assertEqual(raw_evidence[0].locator_page_paths, written_pages)
            query_response = search_query(WikiSearchRequest(vault_path=str(vault), query="index metadata ingest", record_query=False))
            self.assertTrue(query_response.raw_evidence)
            self.assertIn("This is a simple document", query_response.raw_evidence[0].content)
            report = vault / result.report_path
            self.assertIn("- ingest_profile: auto", report.read_text(encoding="utf-8"))

    def test_auto_file_ingest_checkpoint_skips_unchanged_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Repeat Note\n\nStable content.", encoding="utf-8")
            config_path = _write_config(root, vault)
            request = UnifiedIngestRequest(
                kind="file",
                execution="queued",
                config_path=str(config_path),
                input_path=str(source),
                write=True,
                write_report=False,
                append_ledger=False,
            )

            compiler = FakeQuickCompiler()
            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=compiler),
            ):
                first = execute_file_command(request)
                repeated = execute_file_command(request.model_copy(update={"write_report": True}))

            self.assertEqual(first.results[0].status, "processed")
            self.assertEqual(repeated.results[0].status, "skipped")
            self.assertEqual(repeated.results[0].semantic_skip_reason, "committed_source_revision")
            self.assertEqual(compiler.calls, 1)

            page = next(content_root(vault).glob("*.md"))
            WikiPageService().delete_page(vault, page.name)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=compiler),
            ):
                restored = execute_file_command(request)

            self.assertEqual(restored.results[0].status, "processed")
            self.assertEqual(restored.stats["written_count"], 1)
            self.assertEqual(compiler.calls, 2)
            self.assertEqual(len(list(content_root(vault).glob("*.md"))), 1)

    def test_all_rejected_claims_keep_raw_and_mark_source_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Raw Only\n\nThe source remains authoritative.", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeAllClaimsRejectedCompiler()),
            ):
                dry_run = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=False,
                        write_report=False,
                        append_ledger=False,
                    )
                )
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            self.assertEqual(dry_run.results[0].status, "partial")
            self.assertFalse(dry_run.results[0].wrote)
            self.assertEqual(result.results[0].status, "partial")
            self.assertFalse(result.results[0].error_retryable)
            self.assertEqual(result.stats["partial_count"], 1)
            self.assertEqual(result.stats["failed_count"], 0)
            self.assertTrue(read_raw_evidence_records(vault))

    def test_auto_ingest_is_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Default Quick\n\nNo profile is passed.", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeQuickCompiler()),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            self.assertEqual(result.ingest_profile, "auto")
            self.assertEqual(result.results[0].ingest_profile, "auto")

    def test_auto_file_ingest_fails_on_compiler_integrity_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Invalid Quick\n\nNeeds evidence.", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeInvalidQuickCompiler()),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            source_result = result.results[0]
            self.assertEqual(source_result.status, "failed")
            self.assertFalse(source_result.generated_pages)
            self.assertEqual(source_result.error_stage, "index_metadata_validation")
            self.assertEqual(source_result.error_category, "internal_error")
            self.assertFalse(source_result.error_retryable)

    def test_auto_file_ingest_does_not_gate_model_output_by_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# 检索设计\n\n检索流程应该先定位相关 raw，再基于原文片段回答。", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeTranslatedChineseCompiler()),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            source_result = result.results[0]
            self.assertEqual(source_result.status, "processed")
            self.assertTrue(source_result.generated_pages)

    def test_auto_file_ingest_preserves_long_synthesis_without_length_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Generic Metadata\n\nThis source is still valid.", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeLongSynthesisCompiler()),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            source_result = result.results[0]
            self.assertEqual(source_result.status, "processed")

    def test_auto_file_ingest_accepts_claims_without_synthesis_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Generic Metadata\n\nThis source is still valid.", encoding="utf-8")
            config_path = _write_config(root, vault)

            with patch(
                "knoarbor.services.ingest._build_auto_ingest_pipeline",
                return_value=AutoIngestPipeline(extractor=FakeMissingSynthesisCompiler()),
            ):
                result = execute_file_command(
                    IngestFileRunRequest(
                        config_path=str(config_path),
                        input_path=str(source),
                        write=True,
                        write_report=False,
                        append_ledger=False,
                    )
                )

            source_result = result.results[0]
            self.assertEqual(source_result.status, "processed")

    def test_segment_failure_records_completed_failed_and_unprocessed_segments(self) -> None:
        from knoarbor.core.hashing import file_content_hash

        with tempfile.TemporaryDirectory() as tmp_dir:
            text = "\n\n".join(
                [
                    "# One\n\n" + ("first segment evidence " * 140),
                    "# Two\n\n" + ("second segment evidence " * 140),
                    "# Three\n\n" + ("third segment evidence " * 140),
                ]
            )
            document = SourceDocument(
                source_id="unit:segments",
                source_type="markdown",
                origin=SourceOrigin(connector="test", uri="file:///segments.md", raw_path="/tmp/segments.md"),
                content=SourceContent(format="markdown", text=text),
                fingerprint=SourceFingerprint(content_hash=file_content_hash(text), connector_version="test"),
            )

            result = AutoIngestPipeline(extractor=FakeSecondSegmentFailureCompiler()).run_document(
                document,
                vault_path=Path(tmp_dir),
                write=False,
                write_report=False,
                append_ledger=False,
                segmentation_config=IngestSegmentationConfig(
                    max_chars_per_segment=4000,
                    soft_chars_per_segment=2000,
                    min_segment_chars=1000,
                ),
            )

            self.assertEqual(result.status, "failed")
            self.assertEqual([segment["status"] for segment in result.segments], ["processed", "failed", "not_processed"])
            self.assertEqual(result.segments[1]["error_code"], "KA-MODEL-001")

    def test_queued_run_metadata_does_not_expose_profile_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            init_wiki_vault(vault)
            source = root / "source.md"
            source.write_text("# Queued\n\nMetadata profile.", encoding="utf-8")
            config_path = _write_config(root, vault)
            request = UnifiedIngestRequest(
                kind="file",
                execution="queued",
                config_path=str(config_path),
                input_path=str(source),
                write=False,
                write_report=False,
                append_ledger=False,
            )

            coordinator = IngestCoordinator()
            with patch.object(coordinator.scheduler, "submit"):
                started = coordinator.start(request)

            self.assertNotIn("ingest_profile", started.run.metadata)
            store = TransactionalIngestStore(vault)
            task = store.task(store.attempt(started.run_id)["task_id"])
            self.assertEqual(task["command"]["request_kind"], "file")
            self.assertEqual(task["command"]["generation_id"], task["input_generation_id"])
            self.assertTrue(task["command"]["vault_identity"].startswith("vault:"))

    def test_lightweight_extract_maps_to_internal_atom_batch(self) -> None:
        from knoarbor.core.hashing import file_content_hash
        from knoarbor.core.source_unitization import attach_source_unitization

        text = "# A2A\n\nA2A (Agent-to-Agent) uses Agent Card to describe server capabilities."
        document = attach_source_unitization(
            SourceDocument(
                source_id="unit:a2a",
                source_type="markdown",
                origin=SourceOrigin(connector="test", uri="file:///a2a.md", raw_path="/tmp/a2a.md"),
                content=SourceContent(format="markdown", text=text),
                metadata={"title": "A2A"},
                fingerprint=SourceFingerprint(content_hash=file_content_hash(text), connector_version="test"),
            )
        )
        source_record = _auto_source_record(document, "/tmp/a2a.md")
        evidence_quote = "A2A (Agent-to-Agent) uses Agent Card to describe server capabilities."
        extracted = IndexMetadataExtractResult(
            entities=[
                ExtractedEntity(name="Agent Card", aliases=["智能体名片", "A2A"], unit_positions=[0]),
                ExtractedEntity(name="A2A", aliases=["Agent-to-Agent"], unit_positions=[0]),
            ],
            claims=[
                ExtractedClaim(
                    text="Agent Card describes A2A server capabilities.",
                    entity_positions=[0, 1],
                    evidence=[ExtractedEvidenceQuote(unit_position=0, quote=evidence_quote)],
                    relations=[
                        ExtractedRelation(
                            subject_entity_position=1,
                            predicate="includes",
                            object_entity_position=0,
                        )
                    ],
                )
            ],
            synthesis_topics=["Useful for locating A2A Agent Card capability notes."],
        )

        compilation = compile_extracted_index_metadata(extracted, source_record=source_record, source_file="/tmp/a2a.md")
        atom_batch = compilation.atom_batch

        self.assertEqual(atom_batch.source_record_id, source_record.record_id)
        self.assertEqual(len(atom_batch.claims), 1)
        self.assertTrue(atom_batch.claims[0].id.startswith("claim:"))
        self.assertEqual(atom_batch.claims[0].evidence[0].source_record_id, source_record.record_id)
        self.assertEqual(atom_batch.relations[0].source_claim_ids, [atom_batch.claims[0].id])
        self.assertEqual(atom_batch.relations[0].subject.name, "A2A")
        self.assertTrue(any(entity.name == "Agent Card" for entity in atom_batch.entities))
        self.assertTrue(any(entity.name == "A2A" for entity in atom_batch.entities))
        self.assertEqual(next(entity for entity in atom_batch.entities if entity.name == "Agent Card").aliases, [])
        self.assertEqual(atom_batch.claims[0].evidence[0].excerpt, evidence_quote)

        exact_claim_text = evidence_quote
        exact_extract = extracted.model_copy(
            update={
                "claims": [
                    ExtractedClaim(
                        text=exact_claim_text,
                        entity_positions=[0, 1],
                        evidence=[ExtractedEvidenceQuote(unit_position=0, quote=evidence_quote)],
                    )
                ]
            }
        )
        exact_batch = compile_extracted_index_metadata(
            exact_extract,
            source_record=source_record,
            source_file="/tmp/a2a.md",
        ).atom_batch
        exact_evidence = exact_batch.claims[0].evidence[0]
        unit_excerpt = source_record.units[0].evidence.excerpt.strip()
        expected_start = (source_record.units[0].evidence.char_start or 0) + unit_excerpt.index(exact_claim_text)
        self.assertEqual(exact_evidence.excerpt, exact_claim_text)
        self.assertEqual(exact_evidence.char_start, expected_start)
        self.assertEqual(exact_evidence.char_end, expected_start + len(exact_claim_text))

        payload = _index_metadata_extract_payload(document, "/tmp/a2a.md", source_record)
        self.assertEqual(set(payload), {"source", "units"})

        invalid_evidence = extracted.model_copy(
            update={
                "claims": [
                    extracted.claims[0].model_copy(
                        update={"evidence": [ExtractedEvidenceQuote(unit_position=99, quote=evidence_quote)]}
                    )
                ],
            }
        )
        invalid_compilation = compile_extracted_index_metadata(
            invalid_evidence, source_record=source_record, source_file="/tmp/a2a.md"
        )
        self.assertEqual(invalid_compilation.atom_batch.claims, [])
        self.assertEqual(invalid_compilation.diagnostics["rejected_claims"][0]["reason"], "unknown_unit_position")

        unsupported_claim = extracted.model_copy(
            update={
                "claims": [
                    extracted.claims[0].model_copy(
                        update={"evidence": [ExtractedEvidenceQuote(unit_position=0, quote="not present in source")]}
                    )
                ],
            }
        )
        unsupported_compilation = compile_extracted_index_metadata(
            unsupported_claim, source_record=source_record, source_file="/tmp/a2a.md"
        )
        self.assertEqual(unsupported_compilation.atom_batch.claims, [])
        self.assertEqual(unsupported_compilation.atom_batch.synthesis, "")
        self.assertEqual(unsupported_compilation.diagnostics["rejected_claims"][0]["reason"], "quote_not_found")

        layout_quote = "适用于智能制造、工\n业4.0场景。"
        layout_source = source_record.model_copy(
            update={
                "units": [
                    source_record.units[0].model_copy(
                        update={"evidence": source_record.units[0].evidence.model_copy(update={"excerpt": layout_quote})}
                    )
                ]
            }
        )
        layout_extract = IndexMetadataExtractResult(
            claims=[
                ExtractedClaim(
                    text="该方案适用于智能制造和工业4.0场景。",
                    entity_positions=[],
                    evidence=[ExtractedEvidenceQuote(unit_position=0, quote="适用于智能制造、工业4.0场景。")],
                )
            ],
            synthesis_topics=["工业智能化方案"],
        )
        layout_compilation = compile_extracted_index_metadata(
            layout_extract, source_record=layout_source, source_file="/tmp/a2a.md"
        )
        self.assertEqual(layout_compilation.atom_batch.claims[0].evidence[0].excerpt, layout_quote)

        mixed_claims = extracted.model_copy(
            update={
                "claims": [
                    extracted.claims[0],
                    extracted.claims[0].model_copy(
                        update={
                            "text": "Unsupported candidate.",
                            "evidence": [ExtractedEvidenceQuote(unit_position=0, quote="not present in source")],
                        }
                    ),
                ]
            }
        )
        mixed_compilation = compile_extracted_index_metadata(
            mixed_claims, source_record=source_record, source_file="/tmp/a2a.md"
        )
        self.assertEqual(len(mixed_compilation.atom_batch.claims), 1)
        self.assertEqual(len(mixed_compilation.atom_batch.relations), 1)
        self.assertEqual(len(mixed_compilation.diagnostics["rejected_claims"]), 1)
        self.assertTrue(
            any(item["reason"] == "parent_claim_rejected" for item in mixed_compilation.diagnostics["rejected_relations"])
        )

        invalid_entity_and_ambiguity = extracted.model_copy(
            update={
                "entities": [extracted.entities[0].model_copy(update={"unit_positions": [99]}), extracted.entities[1]],
                "ambiguities": [
                    ExtractedAmbiguity(kind="entity", description="Unknown source position.", unit_positions=[99])
                ],
            }
        )
        candidate_compilation = compile_extracted_index_metadata(
            invalid_entity_and_ambiguity,
            source_record=source_record,
            source_file="/tmp/a2a.md",
        )
        self.assertEqual([entity.name for entity in candidate_compilation.atom_batch.entities], ["A2A"])
        self.assertEqual(candidate_compilation.ambiguities, [])
        self.assertEqual(candidate_compilation.diagnostics["rejected_entities"][0]["reason"], "unknown_unit_position")
        self.assertEqual(
            candidate_compilation.diagnostics["rejected_ambiguities"][0]["reason"], "unknown_unit_position"
        )

        unsupported_entity_name = compile_extracted_index_metadata(
            IndexMetadataExtractResult(
                entities=[ExtractedEntity(name="Missing Entity", unit_positions=[0])],
            ),
            source_record=source_record,
            source_file="/tmp/a2a.md",
        )
        self.assertEqual(unsupported_entity_name.atom_batch.entities, [])
        self.assertEqual(
            unsupported_entity_name.diagnostics["rejected_entities"][0]["reason"],
            "name_not_explicit_in_cited_units",
        )
        punctuated_source = source_record.model_copy(
            update={
                "units": [
                    source_record.units[0].model_copy(
                        update={
                            "evidence": source_record.units[0].evidence.model_copy(
                                update={"excerpt": "智能、制造"}
                            )
                        }
                    )
                ]
            }
        )
        punctuated_name = compile_extracted_index_metadata(
            IndexMetadataExtractResult(
                entities=[ExtractedEntity(name="智能制造", unit_positions=[0])],
            ),
            source_record=punctuated_source,
            source_file="/tmp/a2a.md",
        )
        self.assertEqual(punctuated_name.atom_batch.entities, [])

        repeated_source = source_record.model_copy(
            update={
                "units": [
                    source_record.units[0].model_copy(
                        update={
                            "evidence": source_record.units[0].evidence.model_copy(
                                update={"excerpt": f"{evidence_quote}\n{evidence_quote}"}
                            )
                        }
                    )
                ]
            }
        )
        repeated_evidence = compile_extracted_index_metadata(
            extracted,
            source_record=repeated_source,
            source_file="/tmp/a2a.md",
        ).atom_batch.claims[0].evidence[0]
        self.assertEqual(repeated_evidence.excerpt, evidence_quote)
        self.assertEqual(repeated_evidence.char_start, source_record.units[0].evidence.char_start)

        invalid_annotations = extracted.model_copy(
            update={
                "claims": [
                    extracted.claims[0].model_copy(
                        update={
                            "entity_positions": [99],
                            "relations": [
                                ExtractedRelation(subject_entity_position=1, predicate="includes", object_entity_position=99),
                                ExtractedRelation(subject_entity_position=1, predicate="equals", object_entity_position=1),
                            ],
                        }
                    ),
                ],
            }
        )
        closed = compile_extracted_index_metadata(
            invalid_annotations,
            source_record=source_record,
            source_file="/tmp/a2a.md",
        )
        closed_batch = closed.atom_batch
        self.assertEqual(closed_batch.claims[0].entity_names, [])
        self.assertEqual(closed_batch.relations, [])
        self.assertEqual(len(closed.diagnostics["rejected_claim_entity_references"]), 1)
        self.assertEqual(len(closed.diagnostics["rejected_relations"]), 2)
        self.assertEqual(
            closed.diagnostics["rejected_relations"][1]["reason"],
            "self_relation",
        )


class FakeQuickCompiler:
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        self.calls += 1
        evidence = KnowledgeEvidenceSpan(
            source_record_id=source_record.record_id,
            source_path=source_file,
            source_unit_index=0,
            excerpt="This is a simple document for index metadata ingest.",
        )
        return IndexExtractResult(
            knowledge_atom_batch=KnowledgeAtomBatch(
                source_record_id=source_record.record_id,
                entities=[
                    KnowledgeAtomObject(name="Fast Note", atom_id="E1", evidence=[evidence]),
                    KnowledgeAtomObject(name="index metadata ingest", atom_id="E2", evidence=[evidence]),
                ],
                claims=[
                    KnowledgeClaim(
                        id="C1",
                        claim="Fast Note explains index metadata ingest semantics.",
                        evidence=[evidence],
                        entity_names=["Fast Note", "index metadata ingest"],
                    )
                ],
                relations=[
                    KnowledgeRelation(
                        id="R1",
                        subject=KnowledgeAtomObject(name="Fast Note", atom_id="E1"),
                        predicate="uses",
                        object=KnowledgeAtomObject(name="index metadata ingest", atom_id="E2"),
                        source_claim_ids=["C1"],
                        evidence=[evidence],
                    )
                ],
                synthesis="Useful for locating a simple source about index metadata ingest.",
            ),
            synthesis_topics=["Useful for locating a simple source about index metadata ingest."],
            ambiguities=[],
            semantic_metrics={
                "semantic_call_count": 1,
                "prompt_tokens": 10,
                "prompt_cached_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 10,
                "prompt_stable_chars": 100,
                "prompt_dynamic_chars": 50,
                "dynamic_to_stable_ratio": 0.5,
                "completion_tokens": 20,
                "total_tokens": 30,
                "elapsed_seconds": 0.1,
                "tokens_per_second": 200.0,
                "prompt_cache_rate": 0.0,
                "by_contract": [{"contract_name": "index_metadata_extract", "semantic_call_count": 1}],
                "calls": [{"contract_name": "index_metadata_extract", "schema_version": "index_metadata_extract.v7"}],
            },
        )


class FakeInvalidQuickCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        compiled = super().compile(document, source_file=source_file, source_record=source_record, max_tokens=max_tokens)
        return IndexExtractResult(
            knowledge_atom_batch=compiled.knowledge_atom_batch.model_copy(update={"source_record_id": "wrong_source_record"}),
            synthesis_topics=list(compiled.synthesis_topics),
            ambiguities=[],
            semantic_metrics=compiled.semantic_metrics,
        )


class FakeAllClaimsRejectedCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        compiled = super().compile(document, source_file=source_file, source_record=source_record, max_tokens=max_tokens)
        return IndexExtractResult(
            knowledge_atom_batch=KnowledgeAtomBatch(source_record_id=source_record.record_id),
            synthesis_topics=[],
            ambiguities=[],
            semantic_metrics=compiled.semantic_metrics,
            compilation_diagnostics={
                "candidates": {"entities": 0, "claims": 1, "relations": 0},
                "accepted": {"entities": 0, "claims": 0, "relations": 0},
                "rejected_claims": [
                    {
                        "claim_index": 0,
                        "quote_index": 0,
                        "unit_position": 0,
                        "reason": "quote_not_found",
                    }
                ],
            },
        )


class FakeSecondSegmentFailureCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        if self.calls == 0:
            return super().compile(document, source_file=source_file, source_record=source_record, max_tokens=max_tokens)
        self.calls += 1
        raise IndexMetadataExtractionFailed(
            ModelOutputError("invalid second segment output"),
            {"semantic_call_count": 1, "total_tokens": 10, "elapsed_seconds": 0.1, "calls": []},
        )


class FakeLongSynthesisCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        compiled = super().compile(document, source_file=source_file, source_record=source_record, max_tokens=max_tokens)
        return IndexExtractResult(
            knowledge_atom_batch=compiled.knowledge_atom_batch,
            synthesis_topics=["Locator. " * 260],
            ambiguities=[],
            semantic_metrics=compiled.semantic_metrics,
        )


class FakeMissingSynthesisCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        compiled = super().compile(document, source_file=source_file, source_record=source_record, max_tokens=max_tokens)
        return IndexExtractResult(
            knowledge_atom_batch=compiled.knowledge_atom_batch.model_copy(update={"synthesis": ""}),
            synthesis_topics=[],
            ambiguities=[],
            semantic_metrics=compiled.semantic_metrics,
        )


class FakeTranslatedChineseCompiler(FakeQuickCompiler):
    def compile(self, document, *, source_file: str, source_record, max_tokens=None):
        evidence = KnowledgeEvidenceSpan(
            source_record_id=source_record.record_id,
            source_path=source_file,
            source_unit_index=0,
            excerpt="检索流程应该先定位相关 raw，再基于原文片段回答。",
        )
        return IndexExtractResult(
            knowledge_atom_batch=KnowledgeAtomBatch(
                source_record_id=source_record.record_id,
                entities=[KnowledgeAtomObject(name="检索流程", atom_id="E1", evidence=[evidence])],
                claims=[
                    KnowledgeClaim(
                        id="C1",
                        claim="The retrieval flow should locate raw evidence before answering.",
                        evidence=[evidence],
                        entity_names=["检索流程"],
                    )
                ],
                synthesis="Useful for locating retrieval flow design decisions.",
            ),
            synthesis_topics=["Useful for locating retrieval flow design decisions."],
            ambiguities=[],
            semantic_metrics={
                "semantic_call_count": 1,
                "prompt_tokens": 10,
                "prompt_cached_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 10,
                "prompt_stable_chars": 100,
                "prompt_dynamic_chars": 50,
                "dynamic_to_stable_ratio": 0.5,
                "completion_tokens": 20,
                "total_tokens": 30,
                "elapsed_seconds": 0.1,
                "tokens_per_second": 200.0,
                "prompt_cache_rate": 0.0,
                "by_contract": [{"contract_name": "index_metadata_extract", "semantic_call_count": 1}],
                "calls": [{"contract_name": "index_metadata_extract", "schema_version": "index_metadata_extract.v7"}],
            },
        )


def _write_config(root: Path, vault: Path) -> Path:
    config_path = root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "vault": {"path": str(vault)},
                "models": {
                    "default_provider": "test",
                    "providers": {"test": {"model": "test", "base_url": "http://localhost"}},
                },
                "ingest": {"auto_scoped_lint": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_profile_config(root: Path, default_vault: Path, personal_vault: Path) -> Path:
    config_path = root / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "vault": {"path": str(default_vault)},
                "vaults": {
                    "default": "default",
                    "profiles": {
                        "default": {"name": "Default", "path": str(default_vault)},
                        "personal": {"name": "Personal", "path": str(personal_vault)},
                    },
                },
                "models": {
                    "default_provider": "test",
                    "providers": {"test": {"model": "test", "base_url": "http://localhost"}},
                },
                "ingest": {"auto_scoped_lint": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path
