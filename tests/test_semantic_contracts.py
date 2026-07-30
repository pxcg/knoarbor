from __future__ import annotations

import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.index_metadata_extract import IndexMetadataExtractResult
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.semantic import load_semantic_contract
from knoarbor.semantic.contracts import load_prompt


class SemanticContractTests(unittest.TestCase):
    def test_current_semantic_contracts_load_prompt_and_schema(self) -> None:
        expected = {
            "index_metadata_extract": ("index_metadata_extract.v7", IndexMetadataExtractResult),
            "lint_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates),
            "lint_quality_diagnose": ("maintenance_candidates.v1", MaintenanceCandidates),
            "lint_maintenance_review": ("lint_maintenance_review.v1", LintMaintenanceReview),
        }

        for contract_name, (schema_version, schema_model) in expected.items():
            with self.subTest(contract_name=contract_name):
                contract = load_semantic_contract(contract_name)

                self.assertEqual(contract.schema_version, schema_version)
                self.assertIs(contract.schema_model, schema_model)
                self.assertIn(schema_version, contract.prompt_text)

    def test_maintenance_prompts_name_the_required_nested_contract_fields(self) -> None:
        for name in ("lint_diagnose", "lint_quality_diagnose"):
            with self.subTest(name=name):
                prompt = load_semantic_contract(name).prompt_text
                for field in (
                    "candidate_id",
                    "target_page",
                    "executor_hint",
                    "recommended_action",
                    "expected_effect",
                    "review_notes",
                    "overall_score",
                    "dimension_reviews",
                    "recommendation",
                ):
                    self.assertIn(f"`{field}`", prompt)

        review_prompt = load_semantic_contract("lint_maintenance_review").prompt_text
        for field in (
            "operation_index",
            "necessity",
            "correctness",
            "completeness",
            "executor_fit",
            "risk_level",
            "confidence",
            "required_followups",
        ):
            self.assertIn(f"`{field}`", review_prompt)
        self.assertIn("`approve`", review_prompt)
        self.assertNotIn("`approved`", review_prompt)

    def test_index_metadata_contract_has_strict_grounding_and_trust_boundaries(self) -> None:
        contract = load_semantic_contract("index_metadata_extract")

        self.assertIn("is evidence data", contract.prompt_text)
        self.assertIn("interpreted as subjects", contract.prompt_text)
        self.assertIn("zero-based position", contract.prompt_text)
        self.assertIn("## Empty Result", contract.prompt_text)
        self.assertIn("must not be homogenized", contract.prompt_text)
        self.assertIn("genuinely mixed statement or theme may remain mixed", contract.prompt_text)
        self.assertNotIn("canonical entity name", contract.prompt_text)

        with self.assertRaises(ValidationError):
            IndexMetadataExtractResult.model_validate({"schema_version": "index_metadata_extract.v7", "unexpected": True})

    def test_chat_answer_prompts_require_explicit_generated_image_intent(self) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())
        composer = " ".join(load_prompt("wiki_chat_response_composer.md").split())
        self.assertIn("Decide the two image channels independently", decision)
        self.assertIn("create a new image only", decision)
        self.assertIn("both separately requested", decision)
        self.assertIn("Never satisfy a create-new request with an existing source visual", decision)
        self.assertIn("Never satisfy a source-visual request with a generated replacement", decision)
        self.assertIn("Every selected visual is mandatory", decision)
        self.assertIn("must appear exactly once", composer)
        self.assertIn("generated_image_prompt", decision)
        self.assertIn("Image generation has already finished", composer)
        self.assertIn("generated_visual", composer)
        self.assertNotIn("return one useful generated_image_prompt", composer)
        self.assertIn("Do not write Markdown image syntax", composer)
        self.assertIn(
            "Normally place a visual after the first text item",
            composer,
        )
        self.assertIn("Do not move visuals to the end by default", composer)
        self.assertIn("Use a later gallery only when", composer)

    def test_chat_prompts_follow_one_visible_execution_order(self) -> None:
        planner = load_prompt("wiki_chat_retrieval_planner.md")
        decision = load_prompt("wiki_chat_answer_decision.md")
        composer = load_prompt("wiki_chat_response_composer.md")

        self.assertIn("## Work In Order", planner)
        self.assertIn("## Output Contract", planner)
        self.assertIn("## Boundary", planner)
        self.assertLess(planner.index("## Work In Order"), planner.index("## Output Contract"))
        self.assertLess(planner.index("## Output Contract"), planner.index("## Boundary"))

        self.assertIn("## Work In Order", decision)
        self.assertIn("## Output Contract", decision)
        self.assertLess(
            decision.index("## Work In Order"),
            decision.index("## Output Contract"),
        )
        self.assertIn("## Authority Boundary", composer)
        self.assertIn("## Source Visuals", composer)
        self.assertIn("## Generated Images", composer)
        self.assertIn("## Output Contract", composer)
        self.assertLess(
            composer.index("## Authority Boundary"),
            composer.index("## Output Contract"),
        )

    def test_retrieval_planner_remains_a_locator_only_contract(self) -> None:
        prompt = " ".join(load_prompt("wiki_chat_retrieval_planner.md").split())
        self.assertIn("exact `region_id` values visible in `active_corpus_outline`", prompt)
        self.assertIn("synthesis is only a locator and never answer evidence", prompt)
        self.assertIn("Use region language as a retrieval hint", prompt)
        self.assertIn("unchanged latest question as a companion expression", prompt)
        self.assertIn("Do not choose retrieval algorithms, scores, evidence, citations", prompt)
        self.assertNotIn("caption or heading terminology", prompt)

    def test_chat_answer_prompts_preserve_user_language_composition(self) -> None:
        prompt = " ".join(load_prompt("wiki_chat_response_composer.md").split())
        self.assertIn("Use the latest user message to determine response language", prompt)
        self.assertIn("Preserve source-written proper names", prompt)
        self.assertIn("unless translation is requested", prompt)

    def test_chat_separates_answer_decision_from_response_composition(self) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())
        composer = " ".join(load_prompt("wiki_chat_response_composer.md").split())
        self.assertIn("do not write the answer", decision)
        self.assertIn("exactly these five fields", decision)
        self.assertIn("Raw is the only factual authority", decision)
        self.assertIn("Do not reconsider relevance", composer)
        self.assertIn("original latest user message", composer)
        self.assertIn("complete dialogue-only history", composer)

    def test_response_composer_prompt_defines_clean_trusted_boundaries(self) -> None:
        composer = " ".join(load_prompt("wiki_chat_response_composer.md").split())

        self.assertIn("## Untrusted Data Boundary", composer)
        self.assertIn("source_label", composer)
        self.assertIn("natural Markdown structure", composer)
        self.assertIn("supporting material set changes", composer)
        self.assertIn(
            "answer gives the group a clear shared purpose",
            composer,
        )
        self.assertIn("does not prescribe the answer's paragraph count", composer)
        self.assertIn("Do not add unsupported facts while phrasing it", composer)
        self.assertIn("material IDs in prose", composer)

    def test_answer_decision_prompt_defines_complete_nonredundant_support(
        self,
    ) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())

        self.assertIn("Judge actual span text against the current request", decision)
        self.assertIn("retrieval presence is not support by itself", decision)
        self.assertIn(
            "Select a compact, sufficient set for the answer the user actually asked for",
            decision,
        )
        self.assertIn(
            "add a span only when it supplies necessary support not already covered",
            decision,
        )
        self.assertIn(
            "Never attribute one source's evidence to another",
            decision,
        )
        self.assertIn(
            "Do not fill an unsupported request part with weakly related Raw",
            decision,
        )
        self.assertIn(
            "stable model knowledge can answer any useful part",
            decision,
        )
        self.assertIn(
            "Do not discard an independently answerable part",
            decision,
        )
        self.assertIn(
            "`gap` mode means zero useful answer content can be written",
            decision,
        )
        self.assertIn("Apply this priority", decision)

    def test_answer_decision_prompt_preserves_local_followup_authority(self) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())

        self.assertIn("Preserve a continuing local-source requirement", decision)
        self.assertIn("When the latest message changes only presentation", decision)
        self.assertIn("resolve the referenced factual request from the complete dialogue", decision)
        self.assertIn("most recent applicable local request", decision)
        self.assertIn("Keep its factual subject and source scope", decision)
        self.assertIn("ignore them when judging Raw relevance", decision)
        self.assertIn(
            "Presentation words control later composition",
            decision,
        )
        self.assertIn(
            "depends on local sources never falls back to `general`",
            decision,
        )
        self.assertIn(
            "History may identify what the user means or which local subject they are continuing",
            decision,
        )
        self.assertIn("history and prior assistant wording are never factual support", decision)
        self.assertIn(
            "use a partial or complete gap, never `general` or a different topic",
            decision,
        )

    def test_answer_decision_prompt_uses_general_sufficiency_rules(self) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())

        self.assertIn("Select a compact, sufficient set", decision)
        self.assertIn(
            "Each requested fact or comparison side must be supported by the source that actually states it",
            decision,
        )
        self.assertIn(
            "you may still select source visuals that are relevant to a selected answer part",
            decision,
        )
        self.assertIn(
            "Omit visuals that are clearly unrelated to every selected answer part",
            decision,
        )
        self.assertIn(
            "Do not require a relevant visual to be necessary, better than text",
            decision,
        )
        for overfit_phrase in (
            "one to four",
            '"what", "which", "list", "compare"',
            '"all", "every", "exhaustive"',
            "For an analogy or cross-source mapping",
            "materially clearer than text alone",
            "materially improves understanding",
        ):
            self.assertNotIn(overfit_phrase, decision)

    def test_answer_decision_prompt_uses_partial_gap_without_visual_substitution(
        self,
    ) -> None:
        decision = " ".join(load_prompt("wiki_chat_answer_decision.md").split())

        self.assertIn(
            "Set `gap` after the text and image decisions",
            decision,
        )
        self.assertIn("including an unavailable requested source visual", decision)
        self.assertIn(
            "If requested source visuals are unsupported but text is supported",
            decision,
        )
        self.assertIn("select no substitute visual", decision)
        self.assertIn(
            "an unsatisfied source-visual request requires a non-null gap",
            decision,
        )


if __name__ == "__main__":
    unittest.main()
