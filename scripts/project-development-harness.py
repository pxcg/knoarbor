#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from development_harness.core import (
    HarnessError,
    approve_stage,
    capture_workspace_baseline,
    close_initiative,
    complete_stage,
    create_initiative,
    deliver_github,
    deliver_local,
    export_bundle,
    gate_delta,
    import_bundle,
    initiative_status,
    load_method,
    portfolio,
    project_context,
    record_external_gate,
    record_agent_call,
    record_retry,
    record_scar,
    recover_human,
    reject_stage,
    role_packet,
    run_acceptance,
    run_directory,
    run_gates,
    skip_stage,
    start_stage,
    submit_artifact,
    validate_run,
    verify_scope,
)


ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="KnoArbor development control plane v2")
    result.add_argument("--root", default=str(ROOT))
    result.add_argument("--runs-root")
    commands = result.add_subparsers(dest="command", required=True)

    commands.add_parser("validate-method")
    init = commands.add_parser("init")
    init.add_argument("initiative_id")
    init.add_argument("--title", required=True)
    init.add_argument("--route", choices=("fast", "standard", "strict"), required=True)
    init.add_argument("--spec", required=True)
    init.add_argument("--objective-ref", required=True)
    init.add_argument("--non-goal", action="append", default=[])
    init.add_argument("--allow", action="append", required=True)
    for role in ("controller", "requirement", "design", "implementer", "reviewer"):
        init.add_argument(f"--{role}", required=True)
    init.add_argument("--max-depth", type=int, default=1)
    init.add_argument("--max-parallel-children", type=int, default=1)
    init.add_argument("--max-agent-calls", type=int, default=4)
    init.add_argument("--max-retries-per-stage", type=int, default=2)
    init.add_argument("--authorize-side-effect", action="append", default=[])
    init.add_argument("--gate", action="append", default=[])

    for name in ("status", "validate", "context", "role-packet", "start", "complete", "baseline", "scope", "gate-delta", "acceptance", "deliver-local", "close", "retry", "recover-human"):
        command = commands.add_parser(name)
        command.add_argument("initiative_id")
        if name in {"start", "complete"}:
            command.add_argument("--actor", required=True)
        if name == "recover-human":
            command.add_argument("--actor", required=True)

    skip = commands.add_parser("skip")
    skip.add_argument("initiative_id")
    skip.add_argument("--actor", required=True)
    skip.add_argument("--skip-type", required=True)
    skip.add_argument("--reason-code", required=True)

    artifact = commands.add_parser("submit-artifact")
    artifact.add_argument("initiative_id")
    artifact.add_argument("--actor", required=True)
    artifact.add_argument("--kind", required=True)
    artifact.add_argument("--path")
    artifact.add_argument("--control-json")

    approve = commands.add_parser("approve")
    approve.add_argument("initiative_id")
    approve.add_argument("--actor", required=True)
    reject = commands.add_parser("reject")
    reject.add_argument("initiative_id")
    reject.add_argument("--actor", required=True)
    reject.add_argument("--to", required=True)
    reject.add_argument("--finding-id", action="append", default=[])

    agent = commands.add_parser("record-agent-call")
    agent.add_argument("initiative_id")
    agent.add_argument("--role", required=True)
    agent.add_argument("--parallel-children", type=int, default=1)

    gates = commands.add_parser("run-gates")
    gates.add_argument("initiative_id")
    gates.add_argument("--phase", choices=("baseline", "integration", "acceptance"), required=True)
    external = commands.add_parser("record-external-gate")
    external.add_argument("initiative_id")
    external.add_argument("--gate", required=True)
    external.add_argument("--outcome", choices=("passed", "failed"), required=True)
    external.add_argument("--evidence-id", required=True)
    external.add_argument("--evidence-digest", required=True)
    scar = commands.add_parser("record-scar")
    scar.add_argument("initiative_id")
    scar.add_argument("--gate", required=True)
    scar.add_argument("--owner", required=True)
    scar.add_argument("--acknowledgement", required=True)
    scar.add_argument("--expiry-or-removal", required=True)

    github = commands.add_parser("deliver-github")
    github.add_argument("initiative_id")
    github.add_argument("--base", required=True)
    github.add_argument("--head", required=True)
    github.add_argument("--dry-run", action="store_true")

    portfolio_command = commands.add_parser("portfolio")
    portfolio_command.add_argument("--metrics", action="store_true")
    export = commands.add_parser("export-bundle")
    export.add_argument("initiative_id")
    export.add_argument("--output", required=True)
    import_command = commands.add_parser("import-bundle")
    import_command.add_argument("--bundle", required=True)
    return result


def locations(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    root = Path(args.root).resolve()
    runs_root = Path(args.runs_root).resolve() if args.runs_root else root / ".codex" / "initiatives"
    initiative_id = getattr(args, "initiative_id", None)
    return root, runs_root, run_directory(runs_root, initiative_id) if initiative_id else None


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    args = parser().parse_args()
    try:
        root, runs_root, run_dir = locations(args)
        if args.command == "validate-method":
            method = load_method(root)
            emit({"method_version": method.version, "path": method.relative_path, "digests": method.digests})
        elif args.command == "init":
            roles = {role: getattr(args, role) for role in ("controller", "requirement", "design", "implementer", "reviewer")}
            budgets = {"max_depth": args.max_depth, "max_parallel_children": args.max_parallel_children, "max_agent_calls": args.max_agent_calls, "max_retries_per_stage": args.max_retries_per_stage}
            created = create_initiative(root=root, runs_root=runs_root, initiative_id=args.initiative_id, title=args.title, route=args.route, spec=args.spec, objective_ref=args.objective_ref, non_goals=args.non_goal, allowed_paths=args.allow, roles=roles, budgets=budgets, side_effects=args.authorize_side_effect, extra_gates=args.gate)
            print(created)
        elif args.command == "portfolio":
            emit(portfolio(runs_root, root, include_metrics=args.metrics))
        elif args.command == "import-bundle":
            print(import_bundle(Path(args.bundle).resolve(), runs_root, root))
        else:
            assert run_dir is not None
            if args.command == "status":
                emit(initiative_status(run_dir, root))
            elif args.command == "validate":
                errors = validate_run(run_dir, root)
                if errors:
                    raise HarnessError("; ".join(errors))
                print("Initiative records are valid.")
            elif args.command == "context":
                emit(project_context(run_dir, root))
            elif args.command == "role-packet":
                emit(role_packet(run_dir, root))
            elif args.command == "start":
                start_stage(run_dir, root, actor=args.actor)
            elif args.command == "skip":
                skip_stage(run_dir, root, actor=args.actor, skip_type=args.skip_type, reason_code=args.reason_code)
            elif args.command == "submit-artifact":
                control = json.loads(args.control_json) if args.control_json else None
                print(submit_artifact(run_dir, root, actor=args.actor, kind=args.kind, path=args.path, control=control))
            elif args.command == "complete":
                complete_stage(run_dir, root, actor=args.actor)
            elif args.command == "approve":
                approve_stage(run_dir, root, actor=args.actor)
            elif args.command == "reject":
                reject_stage(run_dir, root, actor=args.actor, rollback_target=args.to, finding_ids=args.finding_id)
            elif args.command == "record-agent-call":
                record_agent_call(run_dir, root, role=args.role, parallel_children=args.parallel_children)
            elif args.command == "retry":
                record_retry(run_dir, root)
            elif args.command == "recover-human":
                recover_human(run_dir, root, actor=args.actor)
            elif args.command == "baseline":
                capture_workspace_baseline(run_dir, root)
            elif args.command == "scope":
                value = verify_scope(run_dir, root)
                emit(value)
                return 1 if value["scope_overflow"] else 0
            elif args.command == "run-gates":
                emit(run_gates(run_dir, root, phase=args.phase))
            elif args.command == "record-external-gate":
                record_external_gate(run_dir, root, gate_id=args.gate, outcome=args.outcome, evidence_id=args.evidence_id, evidence_digest=args.evidence_digest)
            elif args.command == "gate-delta":
                value = gate_delta(run_dir, root)
                emit(value)
                return 1 if value["blockers"] else 0
            elif args.command == "record-scar":
                record_scar(run_dir, root, gate_id=args.gate, owner=args.owner, acknowledgement=args.acknowledgement, expiry_or_removal=args.expiry_or_removal)
            elif args.command == "acceptance":
                run_acceptance(run_dir, root)
            elif args.command == "deliver-local":
                deliver_local(run_dir, root)
            elif args.command == "deliver-github":
                emit(deliver_github(run_dir, root, base_ref=args.base, head_ref=args.head, dry_run=args.dry_run))
            elif args.command == "export-bundle":
                export_bundle(run_dir, root, Path(args.output).resolve())
            elif args.command == "close":
                close_initiative(run_dir, root)
        return 0
    except (HarnessError, json.JSONDecodeError) as exc:
        print(f"Harness error: {exc}", file=sys.stderr)
        return 2
    except (OSError, KeyError, TypeError, ValueError):
        print("Harness error: malformed input or unavailable local process", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
