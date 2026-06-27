from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.semantic.page_assembly import build_page_assembly_payload

from tests.harness.semantic_cases import wiki_atom_extract_output, wiki_page_plan_output


class PageAssemblyTests(unittest.TestCase):
    def test_builds_claims_first_scaffold_from_page_plan_closure(self) -> None:
        atom_batch = wiki_atom_extract_output()["output"]
        plan = wiki_page_plan_output()["output"]

        payload = build_page_assembly_payload(
            KnowledgeAtomBatch.model_validate(atom_batch),
            WikiPagePlan.model_validate(plan),
        )

        self.assertEqual(payload["schema_version"], "page_assembly.v1")
        operation = payload["operations"][0]
        self.assertEqual(operation["operation_index"], 0)
        self.assertEqual(operation["title"], "Agent Loop")
        self.assertEqual(operation["source_digest_ids"], ["sd_test_agent"])
        self.assertEqual(operation["atom_ids"], ["claim_agent_loop_control_pattern", "rel_agent_loop_mentions_control"])
        self.assertEqual(operation["entities"], ["[[Agent Loop]]", "[[Agent Control]]"])
        self.assertEqual(operation["claims"][0]["number"], "C1")
        self.assertIn("[[Agent Loop]]", operation["claims"][0]["text"])
        self.assertEqual(
            operation["relations"][0]["triple"],
            "[[Agent Loop]] | includes | [[Agent Control]] | C1",
        )
        self.assertEqual(operation["evidence"][0]["claim"], "C1")
        self.assertEqual(operation["evidence"][0]["range"], "unit:0")
        self.assertEqual(operation["evidence"][0]["confidence"], "high")

    def test_missing_atoms_return_empty_payload_with_warning(self) -> None:
        plan = WikiPagePlan.model_validate(wiki_page_plan_output()["output"])

        payload = build_page_assembly_payload(None, plan)

        self.assertEqual(payload["operations"], [])
        self.assertEqual(payload["warnings"], ["knowledge_atom_batch_missing"])

    def test_applies_page_plan_canonical_entity_and_relation_mapping(self) -> None:
        atom_batch = KnowledgeAtomBatch.model_validate(wiki_atom_extract_output()["output"])
        plan_payload = wiki_page_plan_output()["output"]
        plan_payload["operations"][0]["entity_mappings"] = [
            {
                "source_name": "Agent Control",
                "canonical_name": "Agent Control Pattern",
                "aliases": ["Agent Control"],
                "reason": "Candidate profile uses the canonical pattern name.",
            }
        ]
        plan_payload["operations"][0]["relation_mappings"] = [
            {
                "relation_id": "rel_agent_loop_mentions_control",
                "canonical_subject": "Agent Loop",
                "predicate": "includes",
                "canonical_object": "Agent Control Pattern",
                "supporting_claim_ids": ["claim_agent_loop_control_pattern"],
                "reason": "The selected claim supports the canonical relation.",
            }
        ]

        payload = build_page_assembly_payload(atom_batch, WikiPagePlan.model_validate(plan_payload))

        operation = payload["operations"][0]
        self.assertEqual(operation["entities"], ["[[Agent Loop]]", "[[Agent Control Pattern]]"])
        self.assertEqual(operation["claims"][0]["entity_names"], ["Agent Loop", "Agent Control Pattern"])
        self.assertEqual(
            operation["relations"][0]["triple"],
            "[[Agent Loop]] | includes | [[Agent Control Pattern]] | C1",
        )


if __name__ == "__main__":
    unittest.main()
