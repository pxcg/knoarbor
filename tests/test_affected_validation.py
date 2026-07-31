from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "plan-affected-validation.py"
SPEC = importlib.util.spec_from_file_location("plan_affected_validation", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
PLAN_AFFECTED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLAN_AFFECTED)


class AffectedValidationPlanTests(unittest.TestCase):
    def test_explicit_scoped_paths_are_normalized_without_reading_the_whole_worktree(self) -> None:
        paths = PLAN_AFFECTED._scoped_paths(["./renderer/src/pages/ChatPage.tsx", "renderer/src/pages/ChatPage.tsx"])

        self.assertEqual(paths, ["renderer/src/pages/ChatPage.tsx"])

    def test_explicit_scoped_path_rejects_a_path_outside_the_repository(self) -> None:
        with self.assertRaises(SystemExit):
            PLAN_AFFECTED._scoped_paths(["/tmp/outside.py"])

    def test_renderer_page_change_selects_typecheck_without_build(self) -> None:
        plan = PLAN_AFFECTED.build_plan(["renderer/src/pages/ChatPage.tsx"])

        self.assertEqual(plan["risk_floor"], "R1")
        self.assertIn(["npm", "--prefix", "renderer", "run", "typecheck"], plan["commands"])
        self.assertFalse(any("build" in command for command in plan["commands"]))

    def test_storage_change_sets_r3_floor_without_full_gate(self) -> None:
        plan = PLAN_AFFECTED.build_plan(["src/knoarbor/storage/ledger.py"])

        self.assertEqual(plan["risk_floor"], "R3")
        self.assertTrue(plan["mechanical_test_selection_complete"])
        self.assertTrue(plan["python_closure"]["focused_tests"])
        self.assertFalse(any("dev-check" in part for command in plan["commands"] for part in command))

    def test_release_workflow_change_sets_r3_without_running_release_gate(self) -> None:
        plan = PLAN_AFFECTED.build_plan([".github/workflows/desktop-release.yml"])

        self.assertEqual(plan["risk_floor"], "R3")
        self.assertEqual(plan["commands"], [])
        self.assertTrue(any("release governance" in reason for reason in plan["review_required"]))

    def test_project_harness_change_sets_r3_governance_floor(self) -> None:
        plan = PLAN_AFFECTED.build_plan(["harness/src/index.ts"])

        self.assertEqual(plan["risk_floor"], "R3")
        self.assertTrue(any("release governance" in reason for reason in plan["review_required"]))

    def test_deleted_python_paths_do_not_enter_file_reading_commands(self) -> None:
        deleted = "tests/test_retired_query.py"

        plan = PLAN_AFFECTED.build_plan(
            ["src/knoarbor/core/schemas/wiki_query.py", deleted],
            deleted_files=[deleted],
        )

        self.assertIn(deleted, plan["deleted_files"])
        self.assertFalse(any(deleted in command for command in plan["commands"]))

    def test_reverse_import_closure_selects_direct_consumer_test(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            owner = root / "src" / "knoarbor" / "services" / "owner.py"
            consumer = root / "src" / "knoarbor" / "entrypoints" / "consumer.py"
            test = root / "tests" / "test_consumer.py"
            for path in (owner, consumer, test):
                path.parent.mkdir(parents=True, exist_ok=True)
            owner.write_text("VALUE = 1\n", encoding="utf-8")
            consumer.write_text("from knoarbor.services.owner import VALUE\n", encoding="utf-8")
            test.write_text("from knoarbor.entrypoints.consumer import VALUE\n", encoding="utf-8")

            plan = PLAN_AFFECTED.build_plan(
                ["src/knoarbor/services/owner.py"],
                root=root,
            )

        self.assertTrue(plan["mechanical_test_selection_complete"])
        self.assertEqual(plan["python_closure"]["focused_tests"], ["tests.test_consumer"])
        self.assertIn(
            ["uv", "run", "python", "-m", "unittest", "tests.test_consumer"],
            plan["commands"],
        )

    def test_uncovered_python_owner_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            owner = root / "src" / "knoarbor" / "services" / "uncovered.py"
            owner.parent.mkdir(parents=True)
            owner.write_text("VALUE = 1\n", encoding="utf-8")

            plan = PLAN_AFFECTED.build_plan(
                ["src/knoarbor/services/uncovered.py"],
                root=root,
            )

        self.assertFalse(plan["mechanical_test_selection_complete"])
        self.assertFalse(plan["python_closure"]["focused_tests"])
        self.assertTrue(any("No focused Python tests" in reason for reason in plan["review_required"]))


if __name__ == "__main__":
    unittest.main()
