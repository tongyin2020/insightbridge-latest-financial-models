#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from qiskit import QuantumCircuit
from qiskit.circuit.library import QAOAAnsatz
from qiskit.primitives import StatevectorSampler
from qiskit.quantum_info import SparsePauliOp
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_optimization import QuadraticProgram
from qiskit_optimization.translators import to_ising


TOOLS_BASE = Path("/Users/tongyin/Desktop/Anaconda_Local_Tools")
DEFAULT_ENV_FILE = TOOLS_BASE / ".env.ibm_quantum"
DEFAULT_PACK_DIR = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_tasks")
DEFAULT_OUT_DIR = Path("/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest/reports/quantum_runs")
WAIT_ONE_HOT_LAMBDA = 1.2
RISK_ONE_HOT_LAMBDA = 1.1
RISK_BUDGET_LAMBDA = 0.35


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit or dry-run EventAlpha quantum optimization tasks."
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
    parser.add_argument("--mode", default="local", choices=["local", "ibm"], help="Run locally first, or submit to IBM backend.")
    parser.add_argument("--backend", default="ibm_fez", help="IBM backend name when --mode ibm.")
    parser.add_argument("--shots", type=int, default=2048, help="Shots per parameter setting.")
    parser.add_argument("--reps", type=int, default=1, help="QAOA depth.")
    parser.add_argument("--grid-points", type=int, default=5, help="Grid resolution per gamma/beta dimension.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Env file containing IBM_QUANTUM_TOKEN.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    parser.add_argument("--submit-only", action="store_true", help="For IBM mode, submit jobs and save job IDs without waiting for results.")
    parser.add_argument("--timeout", type=float, default=None, help="Optional timeout in seconds when waiting for IBM job results.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    return parser.parse_args()


def maybe_load_env(path: Path) -> None:
    if load_dotenv is not None and path.exists():
        load_dotenv(path, override=False)


def find_latest_pack(pack_dir: Path) -> Path:
    packs = sorted(pack_dir.glob("eventalpha_quantum_pack_*.json"))
    if not packs:
        raise FileNotFoundError(f"No quantum task pack found in {pack_dir}")
    return packs[-1]


def load_pack(path: Path) -> dict:
    return json.loads(path.read_text())


def make_param_grid(reps: int, grid_points: int) -> List[Dict[str, List[float]]]:
    gamma_values = [math.pi * i / max(1, grid_points - 1) for i in range(grid_points)]
    beta_values = [math.pi * i / (2 * max(1, grid_points - 1)) for i in range(grid_points)]
    grid = []
    for gamma_tuple in itertools.product(gamma_values, repeat=reps):
        for beta_tuple in itertools.product(beta_values, repeat=reps):
            grid.append({"γ": list(gamma_tuple), "β": list(beta_tuple)})
    return grid


def build_qaoa_circuit(operator: SparsePauliOp, reps: int) -> Tuple[QuantumCircuit, List]:
    ansatz = QAOAAnsatz(operator, reps=reps, flatten=True)
    qc = QuantumCircuit(ansatz.num_qubits, ansatz.num_qubits)
    qc.compose(ansatz, inplace=True)
    qc.measure(range(ansatz.num_qubits), range(ansatz.num_qubits))
    params = list(ansatz.parameters)
    return qc, params


def param_mapping(params: List, grid_item: Dict[str, List[float]]) -> Dict:
    values = list(grid_item["β"]) + list(grid_item["γ"])
    if len(values) != len(params):
        values = list(grid_item["γ"]) + list(grid_item["β"])
    return {params[i]: values[i] for i in range(len(params))}


def ensure_best_exact_solution(problem: dict, *, subject: dict | None = None) -> dict | None:
    kind = problem["problem"]
    if kind == "asset_subset_selection":
        if "best_exact_solution" in problem:
            return problem["best_exact_solution"]
        variables = problem["qubo_like"]["variables"]
        best = None
        for bits in itertools.product([0, 1], repeat=len(variables)):
            objective = objective_from_problem(problem, list(bits), subject=subject)
            selected = [variables[i] for i, bit in enumerate(bits) if bit == 1]
            candidate = {"bits": list(bits), "selected": selected, "objective": objective}
            if best is None or candidate["objective"] > best["objective"]:
                best = candidate
        problem["best_exact_solution"] = best
        return best
    if kind == "wait_bucket_optimization":
        asset = require_wait_asset(problem, subject)
        best = problem["per_asset"][asset]["best_exact_solution"]
        return {"asset": asset, **best}
    return problem.get("best_exact_solution")


def require_wait_asset(problem: dict, subject: dict | None) -> str:
    asset = (subject or {}).get("asset", "")
    if not asset:
        raise ValueError("wait_bucket_optimization requires an asset subject.")
    if asset not in problem["per_asset"]:
        raise KeyError(f"Asset {asset} not found in wait problem.")
    return asset


def build_subset_qp(problem: dict) -> Tuple[QuadraticProgram, List[str]]:
    qubo = problem["qubo_like"]
    variables = qubo["variables"]
    linear_scores = qubo["linear_scores"]
    pair_penalties = qubo["pair_penalties"]
    target = qubo["selection_target"]
    lam = qubo["cardinality_penalty_lambda"]
    qp = QuadraticProgram("eventalpha_asset_subset")
    for name in variables:
        qp.binary_var(name=name)

    constant = lam * (target ** 2)
    linear: Dict[str, float] = {}
    quadratic: Dict[Tuple[str, str], float] = {}

    for name in variables:
        benefit = float(linear_scores[name])
        linear[name] = -benefit + lam * (1 - 2 * target)

    for i, a in enumerate(variables):
        for b in variables[i + 1 :]:
            q = 2 * lam + float(pair_penalties.get(f"{a}|{b}", 0.0))
            quadratic[(a, b)] = q

    qp.minimize(constant=constant, linear=linear, quadratic=quadratic)
    return qp, variables


def build_wait_qp(problem: dict, *, subject: dict) -> Tuple[QuadraticProgram, List[str]]:
    asset = require_wait_asset(problem, subject)
    asset_block = problem["per_asset"][asset]
    bucket_scores = asset_block["bucket_scores"]
    variables = [f"{asset}__wait_{row['wait_seconds']}" for row in bucket_scores]
    qp = QuadraticProgram(f"eventalpha_wait_{asset}")
    for name in variables:
        qp.binary_var(name=name)

    target = 1.0
    lam = WAIT_ONE_HOT_LAMBDA
    constant = lam * (target ** 2)
    linear: Dict[str, float] = {}
    quadratic: Dict[Tuple[str, str], float] = {}
    for row, name in zip(bucket_scores, variables):
        linear[name] = -float(row["score"]) + lam * (1 - 2 * target)
    for i, a in enumerate(variables):
        for b in variables[i + 1 :]:
            quadratic[(a, b)] = 2 * lam
    qp.minimize(constant=constant, linear=linear, quadratic=quadratic)
    return qp, variables


def build_risk_qp(problem: dict) -> Tuple[QuadraticProgram, List[str]]:
    qubo = problem["qubo_like"]
    assets = qubo["selected_assets"]
    tiers = list(qubo["tiers"].items())
    budget = float(qubo["risk_budget"])
    asset_scores = qubo["asset_scores"]
    qp = QuadraticProgram("eventalpha_risk_tiers")
    variables: List[str] = []
    weights: Dict[str, float] = {}
    benefits: Dict[str, float] = {}
    groups: Dict[str, List[str]] = {}

    for asset in assets:
        group = []
        for tier_name, tier_weight in tiers:
            name = f"{asset}__tier__{tier_name}"
            qp.binary_var(name=name)
            variables.append(name)
            weights[name] = float(tier_weight)
            benefits[name] = float(asset_scores[asset]) * float(tier_weight)
            group.append(name)
        groups[asset] = group

    constant = 0.0
    linear: Dict[str, float] = {name: 0.0 for name in variables}
    quadratic: Dict[Tuple[str, str], float] = {}

    for asset, group in groups.items():
        constant += RISK_ONE_HOT_LAMBDA
        for name in group:
            linear[name] += -benefits[name] + RISK_ONE_HOT_LAMBDA * (1 - 2)
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                quadratic[(a, b)] = quadratic.get((a, b), 0.0) + 2 * RISK_ONE_HOT_LAMBDA

    constant += RISK_BUDGET_LAMBDA * (budget ** 2)
    for name in variables:
        weight = weights[name]
        linear[name] += RISK_BUDGET_LAMBDA * ((weight ** 2) - 2 * budget * weight)
    for i, a in enumerate(variables):
        for b in variables[i + 1 :]:
            quadratic[(a, b)] = quadratic.get((a, b), 0.0) + 2 * RISK_BUDGET_LAMBDA * weights[a] * weights[b]

    qp.minimize(constant=constant, linear=linear, quadratic=quadratic)
    return qp, variables


def build_problem_qp(problem: dict, *, subject: dict | None = None) -> Tuple[QuadraticProgram, List[str]]:
    kind = problem["problem"]
    if kind == "asset_subset_selection":
        return build_subset_qp(problem)
    if kind == "wait_bucket_optimization":
        return build_wait_qp(problem, subject=subject or {})
    if kind == "risk_tier_allocation":
        return build_risk_qp(problem)
    raise ValueError(f"Unsupported problem type: {kind}")


def objective_from_problem(problem: dict, bit_values: List[int], *, subject: dict | None = None) -> float:
    kind = problem["problem"]
    if kind == "asset_subset_selection":
        qubo = problem["qubo_like"]
        variables = qubo["variables"]
        x = {variables[i]: bit_values[i] for i in range(len(variables))}
        base = sum(qubo["linear_scores"][v] * x[v] for v in variables)
        pair_penalty = 0.0
        for key, penalty in qubo["pair_penalties"].items():
            a, b = key.split("|")
            pair_penalty += penalty * x[a] * x[b]
        size_penalty = qubo["cardinality_penalty_lambda"] * (sum(x.values()) - qubo["selection_target"]) ** 2
        return round(base - pair_penalty - size_penalty, 6)

    if kind == "wait_bucket_optimization":
        asset = require_wait_asset(problem, subject)
        bucket_scores = problem["per_asset"][asset]["bucket_scores"]
        selected_scores = [
            float(row["score"])
            for idx, row in enumerate(bucket_scores)
            if idx < len(bit_values) and bit_values[idx] == 1
        ]
        one_hot_penalty = WAIT_ONE_HOT_LAMBDA * (sum(bit_values) - 1) ** 2
        return round(sum(selected_scores) - one_hot_penalty, 6)

    if kind == "risk_tier_allocation":
        qubo = problem["qubo_like"]
        assets = qubo["selected_assets"]
        tier_items = list(qubo["tiers"].items())
        asset_scores = qubo["asset_scores"]
        risk_budget = float(qubo["risk_budget"])
        idx = 0
        benefit = 0.0
        one_hot_penalty = 0.0
        risk_used = 0.0
        for asset in assets:
            group_sum = 0
            for tier_name, tier_weight in tier_items:
                bit = bit_values[idx]
                idx += 1
                group_sum += bit
                if bit:
                    benefit += float(asset_scores[asset]) * float(tier_weight)
                    risk_used += float(tier_weight)
            one_hot_penalty += RISK_ONE_HOT_LAMBDA * (group_sum - 1) ** 2
        budget_penalty = RISK_BUDGET_LAMBDA * (risk_used - risk_budget) ** 2
        return round(benefit - one_hot_penalty - budget_penalty, 6)

    raise ValueError(f"Unsupported problem type: {kind}")


def decode_counts(counts: Dict[str, int], problem: dict, *, subject: dict | None = None) -> dict:
    kind = problem["problem"]
    ranked = []
    for bitstring, shots in counts.items():
        bits = [int(ch) for ch in bitstring[::-1]]
        objective = objective_from_problem(problem, bits, subject=subject)
        row = {
            "bitstring": bitstring,
            "decoded_bits": bits,
            "shots": shots,
            "objective": objective,
        }
        if kind == "asset_subset_selection":
            variables = problem["qubo_like"]["variables"]
            row["selected"] = [variables[i] for i, bit in enumerate(bits) if bit == 1]
        elif kind == "wait_bucket_optimization":
            asset = require_wait_asset(problem, subject)
            bucket_scores = problem["per_asset"][asset]["bucket_scores"]
            selected_waits = [
                int(bucket_scores[i]["wait_seconds"])
                for i, bit in enumerate(bits[: len(bucket_scores)])
                if bit == 1
            ]
            row["asset"] = asset
            row["selected_waits"] = selected_waits
            row["chosen_wait_seconds"] = selected_waits[0] if len(selected_waits) == 1 else None
            row["one_hot_valid"] = len(selected_waits) == 1
        elif kind == "risk_tier_allocation":
            qubo = problem["qubo_like"]
            assets = qubo["selected_assets"]
            tier_items = list(qubo["tiers"].items())
            allocation = {}
            idx = 0
            risk_used = 0.0
            valid = True
            for asset in assets:
                chosen = []
                for tier_name, tier_weight in tier_items:
                    bit = bits[idx]
                    idx += 1
                    if bit == 1:
                        chosen.append((tier_name, tier_weight))
                if len(chosen) != 1:
                    valid = False
                if chosen:
                    tier_name, tier_weight = chosen[0]
                    allocation[asset] = {"tier": tier_name, "weight": tier_weight}
                    risk_used += float(tier_weight)
                else:
                    allocation[asset] = {"tier": None, "weight": 0.0}
            row["allocation"] = allocation
            row["risk_used"] = round(risk_used, 6)
            row["one_hot_valid"] = valid
        ranked.append(row)

    def sort_key(item: dict) -> tuple:
        if kind == "wait_bucket_optimization":
            return (1 if item.get("one_hot_valid") else 0, item["objective"], item["shots"])
        if kind == "risk_tier_allocation":
            budget = float(problem["qubo_like"]["risk_budget"])
            budget_valid = item.get("risk_used", budget + 1) <= budget + 1e-9
            return (
                1 if item.get("one_hot_valid") else 0,
                1 if budget_valid else 0,
                item["objective"],
                item["shots"],
            )
        return (1, item["objective"], item["shots"])

    ranked.sort(key=sort_key, reverse=True)
    return {"ranked_solutions": ranked, "best_sampled_solution": ranked[0] if ranked else None}


def resolve_subjects(problem: dict, asset_filter: str = "") -> List[dict | None]:
    if problem["problem"] != "wait_bucket_optimization":
        return [None]
    assets = sorted(problem["per_asset"].keys())
    if asset_filter:
        if asset_filter not in assets:
            raise KeyError(f"Asset {asset_filter} not found in wait problem. Available: {assets}")
        assets = [asset_filter]
    return [{"asset": asset} for asset in assets]


def subject_label(problem: dict, subject: dict | None) -> str:
    if problem["problem"] == "wait_bucket_optimization":
        return f"{problem['problem']}:{subject['asset']}"
    return problem["problem"]


def serialize_subject(subject: dict | None) -> dict | None:
    return dict(subject) if subject else None


def run_local(problem: dict, reps: int, shots: int, grid_points: int, *, asset_filter: str = "") -> dict:
    sampler = StatevectorSampler(default_shots=shots, seed=42)
    grid = make_param_grid(reps, grid_points)
    task_results = []

    for subject in resolve_subjects(problem, asset_filter):
        qp, _ = build_problem_qp(problem, subject=subject)
        operator, offset = to_ising(qp)
        qc, params = build_qaoa_circuit(operator, reps)
        evaluations = []
        for item in grid:
            job = sampler.run([(qc, param_mapping(params, item), shots)])
            pub = job.result()[0]
            counts = pub.data.c.get_counts() if hasattr(pub.data, "c") else pub.data.meas.get_counts()
            decoded = decode_counts(counts, problem, subject=subject)
            evaluations.append(
                {
                    "subject": serialize_subject(subject),
                    "params": item,
                    "best_sampled_solution": decoded["best_sampled_solution"],
                    "top_counts": sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5],
                }
            )
        evaluations.sort(key=lambda x: x["best_sampled_solution"]["objective"], reverse=True)
        task_results.append(
            {
                "subject": serialize_subject(subject),
                "label": subject_label(problem, subject),
                "ising_offset": offset,
                "grid_size": len(grid),
                "best_run": evaluations[0] if evaluations else None,
                "all_runs_top3": evaluations[:3],
            }
        )

    best_task = max(
        task_results,
        key=lambda x: x["best_run"]["best_sampled_solution"]["objective"] if x.get("best_run") else float("-inf"),
        default=None,
    )
    return {
        "mode": "local",
        "task_count": len(task_results),
        "tasks": task_results,
        "best_task": best_task,
    }


def run_ibm(
    problem: dict,
    reps: int,
    shots: int,
    grid_points: int,
    backend_name: str,
    env_file: Path,
    *,
    submit_only: bool = False,
    timeout: float | None = None,
    asset_filter: str = "",
) -> dict:
    maybe_load_env(env_file)
    token = os.getenv("IBM_QUANTUM_TOKEN", "").strip()
    channel = os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform").strip() or "ibm_quantum_platform"
    if channel == "ibm_quantum":
        channel = "ibm_quantum_platform"
    instance = os.getenv("IBM_QUANTUM_INSTANCE", "").strip() or None
    if not token:
        raise RuntimeError(f"Missing IBM_QUANTUM_TOKEN in {env_file}")

    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    kwargs = {"channel": channel, "token": token}
    if instance:
        kwargs["instance"] = instance
    service = QiskitRuntimeService(**kwargs)
    backend = service.backend(backend_name)
    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    sampler = SamplerV2(mode=backend)
    grid = make_param_grid(reps, grid_points)
    task_results = []
    pending = []

    for subject in resolve_subjects(problem, asset_filter):
        qp, _ = build_problem_qp(problem, subject=subject)
        operator, offset = to_ising(qp)
        qc, params = build_qaoa_circuit(operator, reps)
        isa_qc = pm.run(qc)
        evaluations = []
        for item in grid:
            mapping = param_mapping(params, item)
            job = sampler.run([(isa_qc, mapping, shots)])
            if submit_only:
                pending.append(
                    {
                        "subject": serialize_subject(subject),
                        "label": subject_label(problem, subject),
                        "params": item,
                        "job_id": job.job_id(),
                    }
                )
                continue
            pub = job.result(timeout=timeout)[0]
            counts = pub.data.c.get_counts() if hasattr(pub.data, "c") else pub.data.meas.get_counts()
            decoded = decode_counts(counts, problem, subject=subject)
            evaluations.append(
                {
                    "subject": serialize_subject(subject),
                    "params": item,
                    "job_id": job.job_id(),
                    "best_sampled_solution": decoded["best_sampled_solution"],
                    "top_counts": sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5],
                }
            )
        if not submit_only:
            evaluations.sort(key=lambda x: x["best_sampled_solution"]["objective"], reverse=True)
            task_results.append(
                {
                    "subject": serialize_subject(subject),
                    "label": subject_label(problem, subject),
                    "ising_offset": offset,
                    "grid_size": len(grid),
                    "best_run": evaluations[0] if evaluations else None,
                    "all_runs_top3": evaluations[:3],
                }
            )

    if submit_only:
        return {
            "mode": "ibm",
            "backend": backend_name,
            "task_count": len(resolve_subjects(problem, asset_filter)),
            "grid_size": len(grid),
            "submitted_jobs": pending,
            "waiting_for_results": True,
        }

    best_task = max(
        task_results,
        key=lambda x: x["best_run"]["best_sampled_solution"]["objective"] if x.get("best_run") else float("-inf"),
        default=None,
    )
    return {
        "mode": "ibm",
        "backend": backend_name,
        "task_count": len(task_results),
        "grid_size": len(grid),
        "tasks": task_results,
        "best_task": best_task,
    }


def main() -> int:
    args = parse_args()
    pack_path = Path(args.pack).expanduser() if args.pack else find_latest_pack(Path(args.pack_dir).expanduser())
    pack = load_pack(pack_path)
    out_dir = Path(args.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    problem = next(p for p in pack["problems"] if p["problem"] == args.problem)
    baseline_exact = [
        ensure_best_exact_solution(problem, subject=subject)
        for subject in resolve_subjects(problem, args.asset)
    ]
    if len(baseline_exact) == 1:
        baseline_exact = baseline_exact[0]

    if args.mode == "local":
        result = run_local(problem, args.reps, args.shots, args.grid_points, asset_filter=args.asset)
    else:
        result = run_ibm(
            problem,
            args.reps,
            args.shots,
            args.grid_points,
            args.backend,
            Path(args.env_file).expanduser(),
            submit_only=args.submit_only,
            timeout=args.timeout,
            asset_filter=args.asset,
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_path": str(pack_path),
        "event_type": pack["event_type"],
        "problem": args.problem,
        "asset_filter": args.asset or None,
        "result": result,
        "baseline_exact": baseline_exact,
        "note": "This runner only evaluates abstract optimization circuits. It does not execute finance logic or place orders.",
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"_{args.asset}" if args.asset else ""
    out_file = out_dir / f"eventalpha_quantum_run_{args.problem}{suffix}_{args.mode}_{stamp}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("EventAlpha Quantum Submit Runner")
        print("=" * 60)
        print(f"pack_path: {pack_path}")
        print(f"event_type: {pack['event_type']}")
        print(f"problem: {args.problem}")
        if args.asset:
            print(f"asset_filter: {args.asset}")
        print(f"mode: {args.mode}")
        print("-" * 60)
        print(f"baseline_exact: {json.dumps(baseline_exact, ensure_ascii=False)}")
        if args.submit_only:
            print(f"submitted_jobs: {json.dumps(result.get('submitted_jobs', []), ensure_ascii=False)}")
        else:
            best_task = result.get("best_task")
            print(f"best_task: {json.dumps(best_task, ensure_ascii=False)}")
        print("-" * 60)
        print(f"saved: {out_file}")
        print(payload["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
