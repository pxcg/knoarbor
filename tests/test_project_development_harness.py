from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from development_harness import core as HARNESS  # noqa: E402


METHOD_SOURCE = Path(__file__).parents[1] / ".codex" / "development"


class ProjectDevelopmentHarnessTests(unittest.TestCase):
    def _repository(self, directory: str, *, remote: bool = False) -> tuple[Path, Path | None]:
        root = Path(directory) / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Harness Test"], cwd=root, check=True)
        shutil.copytree(METHOD_SOURCE, root / ".codex" / "development")
        (root / ".gitignore").write_text(".codex/initiatives/\n", encoding="utf-8")
        gates_path = root / ".codex" / "development" / "methods" / "v2" / "gates.json"
        gates = json.loads(gates_path.read_text(encoding="utf-8"))
        for gate in gates["gates"]:
            if gate["id"] in {"affected-validation", "artifact-consistency"}:
                gate["command"] = ["python3", "-c", "print('gate-ok')"]
        gates_path.write_text(json.dumps(gates, indent=2) + "\n", encoding="utf-8")
        (root / "specs" / "test").mkdir(parents=True)
        for name in ("requirements.md", "acceptance.md", "impact.md", "reproduction.md", "design.md", "tasks.md", "verification.md"):
            (root / "specs" / "test" / name).write_text(f"# {name}\n", encoding="utf-8")
        (root / "specs" / "registry.json").write_text(
            json.dumps({"specs": [{"id": "test", "path": "test", "title": "Test", "lifecycle": "Accepted", "owner": "test"}]}),
            encoding="utf-8",
        )
        (root / "work").mkdir()
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)
        remote_path: Path | None = None
        if remote:
            remote_path = Path(directory) / "remote.git"
            subprocess.run(["git", "init", "--bare", "-q", str(remote_path)], check=True)
            subprocess.run(["git", "remote", "add", "origin", str(remote_path)], cwd=root, check=True)
            subprocess.run(["git", "push", "-qu", "origin", "main"], cwd=root, check=True)
        return root, remote_path

    def _create(self, root: Path, *, route: str = "standard", side_effects: list[str] | None = None, extra_gates: list[str] | None = None, initiative_id: str = "test-initiative") -> tuple[Path, Path]:
        runs_root = root / ".codex" / "initiatives"
        run_dir = HARNESS.create_initiative(
            root=root,
            runs_root=runs_root,
            initiative_id=initiative_id,
            title="Test Initiative",
            route=route,
            spec="specs/test",
            objective_ref="specs/test/requirements.md",
            non_goals=["no product runtime"],
            allowed_paths=["specs/test/", "work/"],
            roles={"controller": "controller", "requirement": "requirement", "design": "design", "implementer": "implementer", "reviewer": "reviewer"},
            budgets={"max_depth": 1, "max_parallel_children": 1, "max_agent_calls": 4, "max_retries_per_stage": 1},
            side_effects=side_effects or [],
            extra_gates=extra_gates,
        )
        return run_dir, runs_root

    def _artifact(self, run_dir: Path, root: Path, actor: str, kind: str, path: str) -> None:
        HARNESS.submit_artifact(run_dir, root, actor=actor, kind=kind, path=path)

    def _control(self, run_dir: Path, root: Path, actor: str, kind: str, outcome: str = "passed") -> None:
        HARNESS.submit_artifact(
            run_dir,
            root,
            actor=actor,
            kind=kind,
            control={"outcome": outcome, "finding_ids": [], "summary_code": f"{kind}_ok"},
        )

    def _fast_to_baseline(self, run_dir: Path, root: Path) -> None:
        for actor in ("requirement", "controller", "requirement", "design", "controller", "reviewer"):
            HARNESS.skip_stage(run_dir, root, actor=actor, skip_type="fast_route", reason_code="bounded_patch")

    def _strict_to_baseline(self, run_dir: Path, root: Path) -> None:
        HARNESS.start_stage(run_dir, root, actor="requirement")
        self._artifact(run_dir, root, "requirement", "requirements", "specs/test/requirements.md")
        self._artifact(run_dir, root, "requirement", "acceptance_criteria", "specs/test/acceptance.md")
        self._artifact(run_dir, root, "requirement", "impact_map", "specs/test/impact.md")
        HARNESS.complete_stage(run_dir, root, actor="requirement")
        HARNESS.approve_stage(run_dir, root, actor="human")
        HARNESS.start_stage(run_dir, root, actor="requirement")
        self._artifact(run_dir, root, "requirement", "reproduction", "specs/test/reproduction.md")
        HARNESS.complete_stage(run_dir, root, actor="requirement")
        HARNESS.start_stage(run_dir, root, actor="design")
        self._artifact(run_dir, root, "design", "design", "specs/test/design.md")
        self._artifact(run_dir, root, "design", "task_plan", "specs/test/tasks.md")
        self._artifact(run_dir, root, "design", "verification_plan", "specs/test/verification.md")
        HARNESS.complete_stage(run_dir, root, actor="design")
        HARNESS.approve_stage(run_dir, root, actor="human")
        HARNESS.start_stage(run_dir, root, actor="reviewer")
        self._control(run_dir, root, "reviewer", "design_verdict", "approved")
        HARNESS.complete_stage(run_dir, root, actor="reviewer")

    def _implementation_to_closure(self, run_dir: Path, root: Path, *, review: bool) -> None:
        (root / "work" / "implementation.txt").write_text("implementation\n", encoding="utf-8")
        (root / "work" / "test.txt").write_text("test\n", encoding="utf-8")
        HARNESS.start_stage(run_dir, root, actor="implementer")
        self._artifact(run_dir, root, "implementer", "implementation", "work/implementation.txt")
        self._artifact(run_dir, root, "implementer", "tests", "work/test.txt")
        HARNESS.complete_stage(run_dir, root, actor="implementer")
        HARNESS.start_stage(run_dir, root, actor="controller")
        HARNESS.run_gates(run_dir, root, phase="integration")
        self._control(run_dir, root, "controller", "integration_evidence")
        HARNESS.complete_stage(run_dir, root, actor="controller")
        if review:
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            self._control(run_dir, root, "reviewer", "code_verdict", "approved")
            HARNESS.complete_stage(run_dir, root, actor="reviewer")
        else:
            HARNESS.skip_stage(run_dir, root, actor="reviewer", skip_type="fast_route", reason_code="bounded_patch")
        HARNESS.run_acceptance(run_dir, root)
        HARNESS.approve_stage(run_dir, root, actor="human")

    def _implementation_to_acceptance(self, run_dir: Path, root: Path, *, review: bool) -> None:
        (root / "work" / "implementation.txt").write_text("implementation\n", encoding="utf-8")
        (root / "work" / "test.txt").write_text("test\n", encoding="utf-8")
        HARNESS.start_stage(run_dir, root, actor="implementer")
        self._artifact(run_dir, root, "implementer", "implementation", "work/implementation.txt")
        self._artifact(run_dir, root, "implementer", "tests", "work/test.txt")
        HARNESS.complete_stage(run_dir, root, actor="implementer")
        HARNESS.start_stage(run_dir, root, actor="controller")
        HARNESS.run_gates(run_dir, root, phase="integration")
        self._control(run_dir, root, "controller", "integration_evidence")
        HARNESS.complete_stage(run_dir, root, actor="controller")
        if review:
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            self._control(run_dir, root, "reviewer", "code_verdict", "approved")
            HARNESS.complete_stage(run_dir, root, actor="reviewer")
        else:
            HARNESS.skip_stage(run_dir, root, actor="reviewer", skip_type="fast_route", reason_code="bounded_patch")

    def test_method_bundle_and_role_packet_are_versioned(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            method = HARNESS.load_method(root)
            run_dir, _ = self._create(root)
            packet = HARNESS.role_packet(run_dir, root)
        self.assertEqual(len(method.stages), 13)
        self.assertEqual(set(method.digests), set(HARNESS.METHOD_TEXT_FILES + HARNESS.METHOD_JSON_FILES))
        self.assertEqual(packet["role"], "requirement")
        self.assertEqual(packet["required_outputs"], ["requirements", "acceptance_criteria", "impact_map"])

    def test_pinned_method_survives_pointer_upgrade_but_rejects_mutation(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            source = root / ".codex" / "development" / "methods" / "v2"
            shutil.copytree(source, source.parent / "v2.1")
            pointer = root / ".codex" / "development" / "current.json"
            pointer.write_text(json.dumps({"schema_version": HARNESS.POINTER_SCHEMA, "method_version": "v2.1", "path": ".codex/development/methods/v2.1"}), encoding="utf-8")
            self.assertEqual(HARNESS.validate_run(run_dir, root), [])
            (source / "policy.md").write_text("changed\n", encoding="utf-8")
            errors = HARNESS.validate_run(run_dir, root)
        self.assertTrue(any("pinned development method changed" in error for error in errors))

    def test_manifest_authority_is_digest_bound(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            manifest_path = run_dir / "manifest.json"
            manifest = HARNESS.read_json(manifest_path)
            manifest["authorized_side_effects"] = ["github_pr"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = HARNESS.validate_run(run_dir, root)
        self.assertTrue(any("manifest digest" in error for error in errors))

    def test_method_rejects_noncanonical_stage_vocabulary(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            workflow_path = root / ".codex" / "development" / "methods" / "v2" / "workflow.json"
            workflow = HARNESS.read_json(workflow_path)
            workflow["stages"][1]["id"] = "invented_stage"
            workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
            with self.assertRaisesRegex(HARNESS.HarnessError, "canonical thirteen stages"):
                HARNESS.load_method(root)

    def test_fast_route_closes_and_auxiliary_views_regenerate(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_closure(run_dir, root, review=False)
            HARNESS.deliver_local(run_dir, root)
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.deliver_local(run_dir, root)
            HARNESS.close_initiative(run_dir, root)
            first = HARNESS.read_json(run_dir / "checkpoint.json")
            for name in HARNESS.DERIVED_VIEWS:
                (run_dir / f"{name}.json").unlink()
            manifest, checkpoint, method = HARNESS._load_run(run_dir, root)
            HARNESS._derive_views(run_dir, manifest, checkpoint, method)
            HARNESS.close_initiative(run_dir, root)
            second = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(first, second)
        self.assertEqual(second["delivery"]["state"], "delivered")

    def test_strict_route_exercises_roles_humans_and_review(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="strict")
            self._strict_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_closure(run_dir, root, review=True)
            HARNESS.deliver_local(run_dir, root)
            HARNESS.close_initiative(run_dir, root)
            checkpoint = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(checkpoint["stages"]["closure"]["status"], "passed")
        self.assertGreaterEqual(len(checkpoint["decisions"]), 3)
        self.assertTrue(any(item["storage_class"] == "control_record" for item in checkpoint["artifacts"]))
        sealed_ids = {item[0] for item in checkpoint["acceptance_seal"]["artifact_digests"]}
        self.assertTrue(any(value.startswith("acceptance:acceptance_verdict") for value in sealed_ids))

    def test_executed_conditional_review_requires_typed_verdict(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="standard")
            HARNESS.start_stage(run_dir, root, actor="requirement")
            self._artifact(run_dir, root, "requirement", "requirements", "specs/test/requirements.md")
            self._artifact(run_dir, root, "requirement", "acceptance_criteria", "specs/test/acceptance.md")
            self._artifact(run_dir, root, "requirement", "impact_map", "specs/test/impact.md")
            HARNESS.complete_stage(run_dir, root, actor="requirement")
            HARNESS.approve_stage(run_dir, root, actor="human")
            HARNESS.skip_stage(run_dir, root, actor="requirement", skip_type="not_bugfix", reason_code="not_bugfix")
            HARNESS.start_stage(run_dir, root, actor="design")
            self._artifact(run_dir, root, "design", "design", "specs/test/design.md")
            self._artifact(run_dir, root, "design", "task_plan", "specs/test/tasks.md")
            self._artifact(run_dir, root, "design", "verification_plan", "specs/test/verification.md")
            HARNESS.complete_stage(run_dir, root, actor="design")
            HARNESS.skip_stage(run_dir, root, actor="controller", skip_type="no_public_or_cross_owner_change", reason_code="bounded_design")
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            with self.assertRaisesRegex(HARNESS.HarnessError, "design_verdict"):
                HARNESS.complete_stage(run_dir, root, actor="reviewer")

    def test_reviewer_repository_mutation_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="strict")
            self._strict_to_baseline(run_dir, root)
            # The helper already completed design review; reproduce at code review.
            HARNESS.capture_workspace_baseline(run_dir, root)
            (root / "work" / "implementation.txt").write_text("implementation\n", encoding="utf-8")
            (root / "work" / "test.txt").write_text("test\n", encoding="utf-8")
            HARNESS.start_stage(run_dir, root, actor="implementer")
            self._artifact(run_dir, root, "implementer", "implementation", "work/implementation.txt")
            self._artifact(run_dir, root, "implementer", "tests", "work/test.txt")
            HARNESS.complete_stage(run_dir, root, actor="implementer")
            HARNESS.start_stage(run_dir, root, actor="controller")
            HARNESS.run_gates(run_dir, root, phase="integration")
            self._control(run_dir, root, "controller", "integration_evidence")
            HARNESS.complete_stage(run_dir, root, actor="controller")
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            self._control(run_dir, root, "reviewer", "code_verdict", "approved")
            (root / "work" / "implementation.txt").write_text("reviewer mutation\n", encoding="utf-8")
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.complete_stage(run_dir, root, actor="reviewer")

    def test_rejection_invalidates_downstream_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="strict")
            self._strict_to_baseline(run_dir, root)
            # Roll back the completed design review by moving to implementation then rejecting later.
            HARNESS.capture_workspace_baseline(run_dir, root)
            (root / "work" / "implementation.txt").write_text("implementation\n", encoding="utf-8")
            (root / "work" / "test.txt").write_text("test\n", encoding="utf-8")
            HARNESS.start_stage(run_dir, root, actor="implementer")
            self._artifact(run_dir, root, "implementer", "implementation", "work/implementation.txt")
            self._artifact(run_dir, root, "implementer", "tests", "work/test.txt")
            HARNESS.complete_stage(run_dir, root, actor="implementer")
            HARNESS.start_stage(run_dir, root, actor="controller")
            HARNESS.run_gates(run_dir, root, phase="integration")
            self._control(run_dir, root, "controller", "integration_evidence")
            HARNESS.complete_stage(run_dir, root, actor="controller")
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            HARNESS.reject_stage(run_dir, root, actor="reviewer", rollback_target="implementation", finding_ids=["F-1"])
            checkpoint = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(checkpoint["current_stage"], "implementation")
        self.assertTrue(any(item["kind"] == "implementation" and item["status"] == "invalidated" for item in checkpoint["artifacts"]))
        self.assertEqual(checkpoint["decisions"][-1]["finding_ids"], ["F-1"])

    def test_three_review_rejections_trip_circuit_breaker(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            for attempt in range(3):
                (root / "work" / "implementation.txt").write_text(f"implementation {attempt}\n", encoding="utf-8")
                (root / "work" / "test.txt").write_text(f"test {attempt}\n", encoding="utf-8")
                HARNESS.start_stage(run_dir, root, actor="implementer")
                self._artifact(run_dir, root, "implementer", "implementation", "work/implementation.txt")
                self._artifact(run_dir, root, "implementer", "tests", "work/test.txt")
                HARNESS.complete_stage(run_dir, root, actor="implementer")
                HARNESS.start_stage(run_dir, root, actor="controller")
                HARNESS.run_gates(run_dir, root, phase="integration")
                self._control(run_dir, root, "controller", "integration_evidence")
                HARNESS.complete_stage(run_dir, root, actor="controller")
                HARNESS.start_stage(run_dir, root, actor="reviewer")
                HARNESS.reject_stage(run_dir, root, actor="reviewer", rollback_target="implementation", finding_ids=[f"F-{attempt}"])
            checkpoint = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(checkpoint["usage"]["consecutive_rejections"], 3)
        self.assertEqual(checkpoint["stages"]["implementation"]["status"], "awaiting_human")
        self.assertIn("rejection_circuit_breaker", checkpoint["blockers"])

    def test_agent_and_retry_budgets_persist_awaiting_human(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            for _ in range(4):
                HARNESS.record_agent_call(run_dir, root, role="design", parallel_children=1)
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.record_agent_call(run_dir, root, role="design", parallel_children=1)
            checkpoint = HARNESS.read_json(run_dir / "checkpoint.json")
            HARNESS.recover_human(run_dir, root, actor="human")
            HARNESS.record_agent_call(run_dir, root, role="design", parallel_children=1)
            HARNESS.record_retry(run_dir, root)
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.record_retry(run_dir, root)
            retried = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(checkpoint["stages"]["requirement_analysis"]["status"], "awaiting_human")
        self.assertEqual(retried["stages"]["requirement_analysis"]["status"], "awaiting_human")
        self.assertEqual(retried["usage"]["agent_calls"], 5)

    def test_crash_after_event_recovers_prepared_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            os.environ["KNOARBOR_HARNESS_CRASH_AT"] = "after_event"
            try:
                with self.assertRaises(RuntimeError):
                    HARNESS.start_stage(run_dir, root, actor="requirement")
            finally:
                os.environ.pop("KNOARBOR_HARNESS_CRASH_AT", None)
            for name in HARNESS.DERIVED_VIEWS:
                (run_dir / f"{name}.json").unlink(missing_ok=True)
            checkpoint = HARNESS.initiative_status(run_dir, root)
            self.assertTrue(all((run_dir / f"{name}.json").is_file() for name in HARNESS.DERIVED_VIEWS))
            self.assertEqual(HARNESS.validate_run(run_dir, root), [])
        self.assertEqual(checkpoint["stages"]["requirement_analysis"]["status"], "running")
        self.assertEqual(checkpoint["revision"], 1)

    def test_crash_after_prepare_discards_uncommitted_checkpoint(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            os.environ["KNOARBOR_HARNESS_CRASH_AT"] = "after_prepare"
            try:
                with self.assertRaises(RuntimeError):
                    HARNESS.start_stage(run_dir, root, actor="requirement")
            finally:
                os.environ.pop("KNOARBOR_HARNESS_CRASH_AT", None)
            self.assertEqual(HARNESS.validate_run(run_dir, root), [])
            checkpoint = HARNESS.read_json(run_dir / "checkpoint.json")
        self.assertEqual(checkpoint["revision"], 0)
        self.assertEqual(checkpoint["stages"]["requirement_analysis"]["status"], "pending")

    def test_corrupt_event_chain_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            HARNESS.start_stage(run_dir, root, actor="requirement")
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            (run_dir / "events.jsonl").write_text(events.replace('"revision":1', '"revision":2'), encoding="utf-8")
            errors = HARNESS.validate_run(run_dir, root)
        self.assertTrue(any("event revision" in error for error in errors))

    def test_rejected_control_record_cannot_complete_review(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="strict")
            HARNESS.start_stage(run_dir, root, actor="requirement")
            self._artifact(run_dir, root, "requirement", "requirements", "specs/test/requirements.md")
            self._artifact(run_dir, root, "requirement", "acceptance_criteria", "specs/test/acceptance.md")
            self._artifact(run_dir, root, "requirement", "impact_map", "specs/test/impact.md")
            HARNESS.complete_stage(run_dir, root, actor="requirement")
            HARNESS.approve_stage(run_dir, root, actor="human")
            HARNESS.start_stage(run_dir, root, actor="requirement")
            self._artifact(run_dir, root, "requirement", "reproduction", "specs/test/reproduction.md")
            HARNESS.complete_stage(run_dir, root, actor="requirement")
            HARNESS.start_stage(run_dir, root, actor="design")
            self._artifact(run_dir, root, "design", "design", "specs/test/design.md")
            self._artifact(run_dir, root, "design", "task_plan", "specs/test/tasks.md")
            self._artifact(run_dir, root, "design", "verification_plan", "specs/test/verification.md")
            HARNESS.complete_stage(run_dir, root, actor="design")
            HARNESS.approve_stage(run_dir, root, actor="human")
            HARNESS.start_stage(run_dir, root, actor="reviewer")
            self._control(run_dir, root, "reviewer", "design_verdict", "rejected")
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.complete_stage(run_dir, root, actor="reviewer")

    def test_writer_lock_rejects_second_controller(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            with HARNESS.writer_lock(run_dir):
                with self.assertRaises(HARNESS.HarnessError):
                    with HARNESS.writer_lock(run_dir, timeout_seconds=0.05):
                        pass

    def test_scope_detects_preexisting_dirty_mutation_and_symlink(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            (root / "outside.txt").write_text("dirty before\n", encoding="utf-8")
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.run_gates(run_dir, root, phase="baseline")
            (root / "work" / "link").symlink_to("implementation.txt")
            self.assertEqual(HARNESS.verify_scope(run_dir, root)["scope_overflow"], [])
            (root / "outside.txt").write_text("dirty changed\n", encoding="utf-8")
            result = HARNESS.verify_scope(run_dir, root)
        self.assertEqual(result["scope_overflow"], ["outside.txt"])

    def test_output_proxy_never_prints_or_persists_canary(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            gates_path = root / ".codex" / "development" / "methods" / "v2" / "gates.json"
            gates = json.loads(gates_path.read_text(encoding="utf-8"))
            canary = "sk-" + "A" * 24
            for gate in gates["gates"]:
                if gate["id"] == "affected-validation":
                    gate["command"] = ["python3", "-c", "print('s' + 'k-' + 'A' * 24)"]
            gates_path.write_text(json.dumps(gates), encoding="utf-8")
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            stream = io.StringIO()
            with redirect_stdout(stream):
                HARNESS.capture_workspace_baseline(run_dir, root)
            persisted = "".join(path.read_text(encoding="utf-8") for path in run_dir.glob("*.*") if path.is_file())
        self.assertNotIn(canary, stream.getvalue())
        self.assertNotIn(canary, persisted)

    def test_output_summary_drops_nonrepository_absolute_locations(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            summary = HARNESS._redacted_summary(b"/private/tmp/company-secret.json:4 failed", root, 1, "gate", 1)
        self.assertEqual(summary["diagnostic_locations"], [])

    def test_failure_fingerprint_ignores_volatile_execution_output(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            first = HARNESS._redacted_summary(
                f"2026-07-22T10:00:00Z run_id=run-a\nERROR: worker task_id=task-a request=0f8fad5b-d9cb-469f-a165-70867728950e at localhost:43121 in /private/tmp/run-a/result.json\nFAIL: test_contract (tests.test_owner.OwnerTests.test_contract)\nAssertionError: expected stable value\nRan 1 test in 1.23s\n{root}/tests/test_owner.py:42 failed\n".encode(),
                root, 1, "gate", 1230,
            )
            second = HARNESS._redacted_summary(
                f"2026-07-22T11:00:00Z run_id=run-b\nERROR: worker task_id=task-b request=7c9e6679-7425-40de-944b-e07fc1f90ae7 at localhost:58234 in /private/tmp/run-b/result.json\nFAIL: test_contract (tests.test_owner.OwnerTests.test_contract)\nAssertionError: expected stable value\nRan 1 test in 9.87s\n{root}/tests/test_owner.py:42 failed\n".encode(),
                root, 1, "gate", 9870,
            )

        self.assertEqual(first["output_fingerprint"], second["output_fingerprint"])

    def test_opaque_failure_tail_preserves_distinct_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            common_tail = [f"shared opaque state {index}" for index in range(20)]
            alpha = HARNESS._redacted_summary(
                "\n".join(["opaque alpha state", *common_tail]).encode(), root, 1, "gate", 1,
            )
            beta = HARNESS._redacted_summary(
                "\n".join(["opaque beta state", *common_tail]).encode(), root, 1, "gate", 1,
            )

        self.assertNotEqual(alpha["output_fingerprint"], beta["output_fingerprint"])

    def test_failure_fingerprint_includes_the_complete_diagnostic_set(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            common = [f"ERROR: shared diagnostic {index}" for index in range(41)]
            alpha = HARNESS._redacted_summary(
                "\n".join([*common, "ERROR: alpha tail"]).encode(), root, 1, "gate", 1,
            )
            beta = HARNESS._redacted_summary(
                "\n".join([*common, "ERROR: beta tail"]).encode(), root, 1, "gate", 1,
            )

        self.assertNotEqual(alpha["output_fingerprint"], beta["output_fingerprint"])

    def test_failure_fingerprint_distinguishes_changed_diagnostic_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            original = HARNESS._redacted_summary(
                b"FAIL: test_contract (tests.test_owner.OwnerTests.test_contract)\nAssertionError: expected stable value",
                root, 1, "gate", 1,
            )
            changed = HARNESS._redacted_summary(
                b"FAIL: test_other_contract (tests.test_owner.OwnerTests.test_other_contract)\nValueError: malformed contract",
                root, 1, "gate", 1,
            )

        self.assertNotEqual(original["output_fingerprint"], changed["output_fingerprint"])

    def test_failure_fingerprint_distinguishes_repository_location(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            design = HARNESS._redacted_summary(
                f'File "{root}/specs/test/design.md", line 1\nAssertionError: invalid contract'.encode(),
                root, 1, "gate", 1,
            )
            acceptance = HARNESS._redacted_summary(
                f'File "{root}/specs/test/acceptance.md", line 1\nAssertionError: invalid contract'.encode(),
                root, 1, "gate", 1,
            )

        self.assertNotEqual(design["output_fingerprint"], acceptance["output_fingerprint"])
        self.assertEqual(design["diagnostic_locations"], ["specs/test/design.md"])

    def test_passing_fingerprint_ignores_normal_output(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            quiet = HARNESS._redacted_summary(b"ok", root, 0, "gate", 1)
            noisy = HARNESS._redacted_summary(b"progress 91%\ncompleted in 8.2s", root, 0, "gate", 8200)

        self.assertEqual(quiet["output_fingerprint"], noisy["output_fingerprint"])

    def test_acceptance_only_external_gate_uses_digest_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="fast", extra_gates=["full-chain-focused"])
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_acceptance(run_dir, root, review=False)
            HARNESS.record_external_gate(run_dir, root, gate_id="full-chain-focused", outcome="passed", evidence_id="acceptance:42", evidence_digest="a" * 64)
            HARNESS.run_acceptance(run_dir, root)
            delta = HARNESS.gate_delta(run_dir, root)
        self.assertEqual(delta["blockers"], [])

    def test_portfolio_context_and_metrics_are_derived(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, runs_root = self._create(root)
            context = HARNESS.project_context(run_dir, root)
            portfolio = HARNESS.portfolio(runs_root, root)
            metrics = HARNESS.read_json(run_dir / "metrics.json")
        self.assertEqual(context["current_stage"], "requirement_analysis")
        self.assertEqual(portfolio["initiatives"][0]["initiative_id"], "test-initiative")
        self.assertEqual(metrics["agent_calls"], 0)
        self.assertIn("cycle_duration_ms", metrics)
        self.assertIn("gate_passes", metrics)

    def test_github_delivery_requires_authorization(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root)
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.deliver_github(run_dir, root, base_ref="main", head_ref="main", dry_run=True)

    def test_github_delivery_reuses_oid_identical_pull_request(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory, remote=True)
            run_dir, _ = self._create(root, route="fast", side_effects=["github_pr"])
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_acceptance(run_dir, root, review=False)
            subprocess.run(["git", "add", "work"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "implementation"], cwd=root, check=True)
            subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
            HARNESS.run_acceptance(run_dir, root)
            HARNESS.approve_stage(run_dir, root, actor="human")
            oid = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            marker = f"[knoarbor-initiative:test-initiative:{oid}]"
            commands: list[list[str]] = []

            def fake_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[1:3] == ["repo", "view"]:
                    return subprocess.CompletedProcess(command, 0, json.dumps({"nameWithOwner": "example/repo"}), "")
                return subprocess.CompletedProcess(command, 0, json.dumps([{"number": 7, "url": "https://example.invalid/pr/7", "state": "OPEN", "headRefOid": oid, "body": marker}]), "")

            outcome = HARNESS.deliver_github(run_dir, root, base_ref="main", head_ref="main", runner=fake_runner)
        self.assertTrue(outcome["reused"])
        self.assertFalse(any(command[1:3] == ["pr", "create"] for command in commands))

    def test_github_remote_success_local_crash_recovers_by_lookup(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory, remote=True)
            run_dir, _ = self._create(root, route="fast", side_effects=["github_pr"])
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_acceptance(run_dir, root, review=False)
            subprocess.run(["git", "add", "work"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "implementation"], cwd=root, check=True)
            subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
            HARNESS.run_acceptance(run_dir, root)
            HARNESS.approve_stage(run_dir, root, actor="human")
            oid = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            marker = f"[knoarbor-initiative:test-initiative:{oid}]"
            created = False

            def fake_runner(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal created
                if command[1:3] == ["repo", "view"]:
                    return subprocess.CompletedProcess(command, 0, json.dumps({"nameWithOwner": "example/repo"}), "")
                if command[1:3] == ["pr", "list"]:
                    items = [{"number": 8, "url": "https://example.invalid/pr/8", "state": "OPEN", "headRefOid": oid, "body": marker}] if created else []
                    return subprocess.CompletedProcess(command, 0, json.dumps(items), "")
                created = True
                return subprocess.CompletedProcess(command, 0, "https://example.invalid/pr/8\n", "")

            os.environ["KNOARBOR_HARNESS_CRASH_AT"] = "after_remote_delivery"
            try:
                with self.assertRaises(RuntimeError):
                    HARNESS.deliver_github(run_dir, root, base_ref="main", head_ref="main", runner=fake_runner)
            finally:
                os.environ.pop("KNOARBOR_HARNESS_CRASH_AT", None)
            outcome = HARNESS.deliver_github(run_dir, root, base_ref="main", head_ref="main", runner=fake_runner)
        self.assertTrue(created)
        self.assertTrue(outcome["reused"])

    def test_git_backed_export_import_preserves_control_records(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory, remote=True)
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_acceptance(run_dir, root, review=False)
            subprocess.run(["git", "add", "work"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "implementation"], cwd=root, check=True)
            subprocess.run(["git", "push", "-q", "origin", "main"], cwd=root, check=True)
            HARNESS.run_acceptance(run_dir, root)
            HARNESS.approve_stage(run_dir, root, actor="human")
            HARNESS.deliver_local(run_dir, root)
            HARNESS.close_initiative(run_dir, root)
            bundle = Path(directory) / "initiative.json"
            HARNESS.export_bundle(run_dir, root, bundle)
            imported = HARNESS.import_bundle(bundle, root / ".codex" / "imported", root)
            imported_checkpoint = HARNESS.read_json(imported / "checkpoint.json")
            errors = HARNESS.validate_run(imported, root)
            hostile = HARNESS.read_json(bundle)
            hostile.pop("bundle_root_hash")
            hostile["manifest"]["title"] = "s" + "k-" + "Z" * 24
            hostile["checkpoint"]["manifest_digest"] = HARNESS.digest_json(hostile["manifest"])
            tail = hostile["events"][-1]
            tail["payload_digest"] = HARNESS.digest_json({key: value for key, value in hostile["checkpoint"].items() if key != "event_hash"})
            tail["event_hash"] = HARNESS.digest_json({key: value for key, value in tail.items() if key != "event_hash"})
            hostile["checkpoint"]["event_hash"] = tail["event_hash"]
            hostile["bundle_root_hash"] = HARNESS.digest_json(hostile)
            hostile_path = Path(directory) / "hostile.json"
            hostile_path.write_text(json.dumps(hostile), encoding="utf-8")
            hostile_runs = root / ".codex" / "hostile"
            with self.assertRaises(HARNESS.HarnessError):
                HARNESS.import_bundle(hostile_path, hostile_runs, root)
        self.assertTrue(any(item["storage_class"] == "control_record" for item in imported_checkpoint["artifacts"]))
        self.assertEqual(errors, [])
        self.assertFalse((hostile_runs / "test-initiative").exists())

    def test_closed_seal_is_not_invalidated_by_later_workspace_change(self) -> None:
        with TemporaryDirectory() as directory:
            root, _ = self._repository(directory)
            run_dir, _ = self._create(root, route="fast")
            self._fast_to_baseline(run_dir, root)
            HARNESS.capture_workspace_baseline(run_dir, root)
            self._implementation_to_closure(run_dir, root, review=False)
            HARNESS.deliver_local(run_dir, root)
            HARNESS.close_initiative(run_dir, root)
            (root / "work" / "implementation.txt").write_text("later initiative\n", encoding="utf-8")
            HARNESS.close_initiative(run_dir, root)
            errors = HARNESS.validate_run(run_dir, root)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
