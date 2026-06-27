#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/numba_cache")

from braket.aws import AwsDevice, AwsSession
from braket.circuits import Circuit
from braket.devices import LocalSimulator

from ibm_quantum_eventalpha_submit import (
    decode_counts,
    ensure_best_exact_solution,
    find_latest_pack,
    load_pack,
    objective_from_problem,
    require_wait_asset,
    resolve_subjects,
    serialize_subject,
    subject_label,
)


BASE = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest")
DEFAULT_PACK_DIR = BASE / "reports" / "quantum_tasks"
DEFAULT_OUT_DIR = BASE / "reports" / "quantum_runs"
DEFAULT_DEVICE_ARN = "arn:aws:braket:::device/quantum-simulator/amazon/sv1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit or locally evaluate EventAlpha quantum optimization tasks via AWS Braket."
    )
    parser.add_argument("--pack", default="", help="Specific quantum task pack JSON path.")
    parser.add_argument("--pack-dir", default=str(DEFAULT_PACK_DIR), help="Directory to search for the newest task pack.")
    parser.add_argument(
        "--problem",
        default="asset_subset_selection",
        choices=["asset_subset_selection", "wait_bucket_optimization", "risk_tier_allocation"],
        help="Problem type to run.",
    )
    parser.add_argument(
        "--asset",
        default="",
        help="Optional asset filter for wait_bucket_optimization. If omitted, all assets in the pack are evaluated.",
    )
    parser.add_argument("--mode", default="local", choices=["local", "aws"], help="Run on Braket LocalSimulator or AWS Braket.")
    parser.add_argument("--device-arn", default=DEFAULT_DEVICE_ARN, help="AWS Braket device ARN for --mode aws.")
    parser.add_argument("--shots", type=int, default=512, help="Shots per parameter setting.")
    parser.add_argument("--reps", type=int, default=1, help="QAOA depth.")
    parser.add_argument("--grid-points", type=int, default=3, help="Grid resolution per gamma/beta dimension.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument("--submit-only", action="store_true", help="For AWS mode, save task arns without waiting for results.")
    parser.add_argument("--poll-timeout", type=float, default=900.0, help="AWS poll timeout seconds when waiting for results.")
    parser.add_argument("--poll-interval", type=float, default=10.0, help="AWS poll interval seconds when waiting for results.")
    parser.add_argument("--s3-bucket", default="", help="Optional explicit S3 bucket for Braket results.")
    parser.add_argument("--s3-prefix", default="insightbridge-eventalpha-quantum", help="S3 prefix for Braket results.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args()


def make_param_grid(reps: int, grid_points: int) -> List[Dict[str, List[float]]]:
    gamma_values = [math.pi * i / max(1, grid_points - 1) for i in range(grid_points)]
    beta_values = [math.pi * i / (2 * max(1, grid_points - 1)) for i in range(grid_points)]
    grid = []
    for gamma_tuple in itertools.product(gamma_values, repeat=reps):
        for beta_tuple in itertools.product(beta_values, repeat=reps):
            grid.append({"gamma": list(gamma_tuple), "beta": list(beta_tuple)})
    return grid


def make_truth_table(problem: dict, *, subject: dict | None = None) -> dict[str, float]:
    if problem["problem"] == "asset_subset_selection":
        n_bits = len(problem["qubo_like"]["variables"])
    elif problem["problem"] == "wait_bucket_optimization":
        asset = require_wait_asset(problem, subject)
        n_bits = len(problem["per_asset"][asset]["bucket_scores"])
    elif problem["problem"] == "risk_tier_allocation":
        qubo = problem["qubo_like"]
        n_bits = len(qubo["selected_assets"]) * len(qubo["tiers"])
    else:
        raise ValueError(f"Unsupported problem type: {problem['problem']}")

    truth: dict[str, float] = {}
    for bits in itertools.product([0, 1], repeat=n_bits):
        bit_values = list(bits)
        bitstring = "".join(str(bit) for bit in reversed(bit_values))
        truth[bitstring] = float(objective_from_problem(problem, bit_values, subject=subject))
    return truth


def build_cost_terms(n_qubits: int, truth_table: dict[str, float]) -> tuple[list[tuple[list[int], float]], float]:
    terms: list[tuple[list[int], float]] = []
    constant = 0.0
    bitstrings = list(truth_table.keys())
    for subset_mask in range(1 << n_qubits):
        coef = 0.0
        for bitstring in bitstrings:
            x = [int(ch) for ch in bitstring[::-1]]
            spin_prod = 1.0
            for i in range(n_qubits):
                if (subset_mask >> i) & 1:
                    spin = 1.0 if x[i] == 0 else -1.0
                    spin_prod *= spin
            coef += truth_table[bitstring] * spin_prod
        coef /= float(1 << n_qubits)
        if abs(coef) < 1e-12:
            continue
        qubits = [i for i in range(n_qubits) if (subset_mask >> i) & 1]
        if not qubits:
            constant = float(coef)
        else:
            terms.append((qubits, float(coef)))
    return terms, constant


def apply_pauli_z_term(circuit: Circuit, qubits: list[int], angle: float) -> Circuit:
    if len(qubits) == 1:
        return circuit.rz(qubits[0], angle)
    target = qubits[-1]
    for control in qubits[:-1]:
        circuit.cnot(control, target)
    circuit.rz(target, angle)
    for control in reversed(qubits[:-1]):
        circuit.cnot(control, target)
    return circuit


def build_qaoa_circuit(n_qubits: int, cost_terms: list[tuple[list[int], float]], gammas: list[float], betas: list[float]) -> Circuit:
    circuit = Circuit()
    for qubit in range(n_qubits):
        circuit.h(qubit)
    for gamma, beta in zip(gammas, betas):
        for qubits, coef in cost_terms:
            circuit = apply_pauli_z_term(circuit, qubits, 2.0 * gamma * coef)
        for qubit in range(n_qubits):
            circuit.rx(qubit, 2.0 * beta)
    return circuit


def build_s3_destination(bucket_override: str, prefix: str) -> tuple[str, str]:
    session = AwsSession(default_bucket=bucket_override or None)
    bucket = bucket_override or session.default_bucket()
    return bucket, prefix.rstrip("/")


def select_problem(pack: dict, problem_name: str) -> dict:
    for problem in pack.get("problems", []):
        if problem.get("problem") == problem_name:
            return problem
    raise KeyError(f"Problem {problem_name} not found in pack.")


def run_local(problem: dict, reps: int, shots: int, grid_points: int, *, asset_filter: str = "") -> dict:
    simulator = LocalSimulator()
    task_results = []
    for subject in resolve_subjects(problem, asset_filter):
        truth_table = make_truth_table(problem, subject=subject)
        cost_terms, _ = build_cost_terms(len(next(iter(truth_table.keys()))), truth_table)
        evaluations = []
        for item in make_param_grid(reps, grid_points):
            circuit = build_qaoa_circuit(len(next(iter(truth_table.keys()))), cost_terms, item["gamma"], item["beta"])
            task = simulator.run(circuit, shots=shots)
            result = task.result()
            decoded = decode_counts(result.measurement_counts, problem, subject=subject)
            evaluations.append(
                {
                    "subject": serialize_subject(subject),
                    "params": item,
                    "best_sampled_solution": decoded["best_sampled_solution"],
                    "top_counts": sorted(dict(result.measurement_counts).items(), key=lambda x: x[1], reverse=True)[:8],
                }
            )
        evaluations.sort(key=lambda row: row["best_sampled_solution"]["objective"], reverse=True)
        task_results.append(
            {
                "subject": serialize_subject(subject),
                "label": subject_label(problem, subject),
                "grid_size": len(evaluations),
                "baseline_exact": ensure_best_exact_solution(problem, subject=subject),
                "best_run": evaluations[0] if evaluations else None,
                "all_runs_top3": evaluations[:3],
            }
        )
    best_task = max(
        task_results,
        key=lambda x: x["best_run"]["best_sampled_solution"]["objective"] if x.get("best_run") else float("-inf"),
        default=None,
    )
    return {"mode": "local", "task_count": len(task_results), "tasks": task_results, "best_task": best_task}


def run_aws(
    problem: dict,
    reps: int,
    shots: int,
    grid_points: int,
    device_arn: str,
    *,
    submit_only: bool,
    poll_timeout: float,
    poll_interval: float,
    s3_bucket: str,
    s3_prefix: str,
    asset_filter: str = "",
) -> dict:
    bucket, prefix = build_s3_destination(s3_bucket, s3_prefix)
    destination = (bucket, prefix)
    device = AwsDevice(device_arn)
    task_results = []
    submitted_tasks = []

    for subject in resolve_subjects(problem, asset_filter):
        truth_table = make_truth_table(problem, subject=subject)
        n_qubits = len(next(iter(truth_table.keys())))
        cost_terms, _ = build_cost_terms(n_qubits, truth_table)
        evaluations = []
        for item in make_param_grid(reps, grid_points):
            circuit = build_qaoa_circuit(n_qubits, cost_terms, item["gamma"], item["beta"])
            task = device.run(
                circuit,
                s3_destination_folder=destination,
                shots=shots,
                poll_timeout_seconds=poll_timeout,
                poll_interval_seconds=poll_interval,
            )
            task_arn = getattr(task, "id", None) or getattr(task, "arn", None) or str(task)
            if submit_only:
                submitted_tasks.append(
                    {
                        "subject": serialize_subject(subject),
                        "label": subject_label(problem, subject),
                        "params": item,
                        "task_arn": task_arn,
                    }
                )
                continue
            result = task.result()
            decoded = decode_counts(result.measurement_counts, problem, subject=subject)
            evaluations.append(
                {
                    "subject": serialize_subject(subject),
                    "params": item,
                    "task_arn": task_arn,
                    "best_sampled_solution": decoded["best_sampled_solution"],
                    "top_counts": sorted(dict(result.measurement_counts).items(), key=lambda x: x[1], reverse=True)[:8],
                }
            )
        if not submit_only:
            evaluations.sort(key=lambda row: row["best_sampled_solution"]["objective"], reverse=True)
            task_results.append(
                {
                    "subject": serialize_subject(subject),
                    "label": subject_label(problem, subject),
                    "grid_size": len(evaluations),
                    "baseline_exact": ensure_best_exact_solution(problem, subject=subject),
                    "best_run": evaluations[0] if evaluations else None,
                    "all_runs_top3": evaluations[:3],
                }
            )

    if submit_only:
        return {
            "mode": "aws",
            "device_arn": device_arn,
            "task_count": len(resolve_subjects(problem, asset_filter)),
            "submitted_tasks": submitted_tasks,
            "waiting_for_results": True,
            "s3_destination": {"bucket": bucket, "prefix": prefix},
        }

    best_task = max(
        task_results,
        key=lambda x: x["best_run"]["best_sampled_solution"]["objective"] if x.get("best_run") else float("-inf"),
        default=None,
    )
    return {
        "mode": "aws",
        "device_arn": device_arn,
        "task_count": len(task_results),
        "tasks": task_results,
        "best_task": best_task,
        "s3_destination": {"bucket": bucket, "prefix": prefix},
    }


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_path = Path(args.pack).expanduser() if args.pack else find_latest_pack(Path(args.pack_dir).expanduser())
    pack = load_pack(pack_path)
    problem = select_problem(pack, args.problem)

    if args.mode == "local":
        result = run_local(problem, args.reps, args.shots, args.grid_points, asset_filter=args.asset)
    else:
        result = run_aws(
            problem,
            args.reps,
            args.shots,
            args.grid_points,
            args.device_arn,
            submit_only=args.submit_only,
            poll_timeout=args.poll_timeout,
            poll_interval=args.poll_interval,
            s3_bucket=args.s3_bucket,
            s3_prefix=args.s3_prefix,
            asset_filter=args.asset,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "aws" if args.mode == "aws" else "local"
    out_path = out_dir / f"eventalpha_quantum_run_{args.problem}_{suffix}_{stamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_path": str(pack_path),
        "problem": args.problem,
        "asset_filter": args.asset or None,
        "mode": args.mode,
        "shots": args.shots,
        "reps": args.reps,
        "grid_points": args.grid_points,
        "result": result,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("AWS Braket EventAlpha Submit Runner")
    print("=" * 60)
    print(f"pack_path: {pack_path}")
    print(f"problem: {args.problem}")
    if args.asset:
        print(f"asset_filter: {args.asset}")
    print(f"mode: {args.mode}")
    print("-" * 60)
    if result.get("best_task"):
        print(f"best_task: {json.dumps(result['best_task'], ensure_ascii=False)}")
    if result.get("submitted_tasks") is not None:
        print(f"submitted_tasks: {json.dumps(result['submitted_tasks'], ensure_ascii=False)}")
    if result.get("s3_destination") is not None:
        print(f"s3_destination: {json.dumps(result['s3_destination'], ensure_ascii=False)}")
    print("-" * 60)
    print(f"saved: {out_path}")
    print("This runner evaluates only abstract EventAlpha portfolio-selection problems via AWS Braket.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
