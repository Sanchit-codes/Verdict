#!/usr/bin/env python3
"""CLI tool for evaluating and benchmarking HallucinationGuard.

This module provides two main commands:
1. eval: Run validation on benchmark datasets (HaluBench, HaluEval)
2. benchmark: Measure latency percentiles under concurrent load

Both commands support custom policies and output results as JSON and
formatted tables. The datasets library is optional; without it, a small
hardcoded demo dataset is used.

Typical usage:
    verdict eval --dataset halubench --policy rag_strict --output results.json
    verdict benchmark --requests 1000 --concurrency 10 --policy default
"""

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from verdict import Guard
from verdict.core.exceptions import PolicyLoadError

# Try to import datasets library (optional for benchmarking)
try:
    import datasets
    HAS_DATASETS = True
except ImportError:
    HAS_DATASETS = False

# Setup logging and rich console
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
console = Console()

# Typer app
app = typer.Typer(
    help="HallucinationGuard evaluation and benchmarking CLI",
    no_args_is_help=True
)


# Demo dataset for when datasets library is not available
DEMO_DATASET = [
    {
        "prompt": "What is the capital of France?",
        "output": "The capital of France is Paris.",
        "context": "France is a country in Europe. The capital city is Paris.",
        "label": 0,  # 0 = faithful, 1 = hallucinated
    },
    {
        "prompt": "What is the population of New York?",
        "output": "New York has a population of 50 million people.",
        "context": "New York City is located in the United States. It has a population of approximately 8.3 million people.",
        "label": 1,  # Hallucinated (wrong number)
    },
    {
        "prompt": "Who invented the telephone?",
        "output": "Alexander Graham Bell invented the telephone in 1876.",
        "context": "Alexander Graham Bell is credited with inventing the telephone. He was a Scottish-born inventor.",
        "label": 0,  # Faithful
    },
    {
        "prompt": "What is the largest planet in our solar system?",
        "output": "Saturn is the largest planet in our solar system.",
        "context": "Jupiter is the largest planet in our solar system, with a diameter of approximately 88,846 miles.",
        "label": 1,  # Hallucinated (wrong planet)
    },
    {
        "prompt": "What year did World War II end?",
        "output": "World War II ended in 1945.",
        "context": "World War II was a global conflict that lasted from 1939 to 1945.",
        "label": 0,  # Faithful
    },
]


def load_dataset(dataset_name: str) -> list[dict]:
    """Load a benchmark dataset.
    
    Supports HaluBench and HaluEval from HuggingFace datasets library.
    Falls back to demo dataset if datasets library is not available.
    
    Args:
        dataset_name: Name of dataset ('halubench', 'halueval', or 'demo')
    
    Returns:
        List of dictionaries with keys: prompt, output, context, label
    """
    if dataset_name == "demo":
        logger.info("Using demo dataset (5 examples)")
        return DEMO_DATASET
    
    if not HAS_DATASETS:
        logger.warning(
            "datasets library not installed. Using demo dataset instead. "
            "Install with: pip install datasets"
        )
        return DEMO_DATASET
    
    try:
        if dataset_name == "halubench":
            logger.info("Loading HaluBench dataset...")
            dataset = datasets.load_dataset("tianyi_benchmark/HaluBench")
            # Convert to expected format
            examples = []
            for split in dataset.values():
                for item in split:
                    examples.append({
                        "prompt": item.get("question", ""),
                        "output": item.get("answer", ""),
                        "context": item.get("context", ""),
                        "label": 0 if item.get("label", 0) == "faithful" else 1,
                    })
            return examples
        
        elif dataset_name == "halueval":
            logger.info("Loading HaluEval dataset...")
            dataset = datasets.load_dataset("xinyadu/halueval")
            examples = []
            for item in dataset["evaluation"]:
                examples.append({
                    "prompt": item.get("question", ""),
                    "output": item.get("answer", ""),
                    "context": item.get("document", ""),
                    "label": 0 if item.get("label", 0) == 1 else 1,
                })
            return examples
        
        else:
            logger.error(f"Unknown dataset: {dataset_name}")
            console.print(f"[red]Error: Unknown dataset '{dataset_name}'[/red]")
            raise ValueError(f"Unknown dataset: {dataset_name}")
    
    except Exception as e:
        logger.error(f"Failed to load dataset {dataset_name}: {e}")
        console.print(
            f"[yellow]Warning: Failed to load {dataset_name}, using demo dataset[/yellow]"
        )
        return DEMO_DATASET


def compute_metrics(
    predictions: list[int],
    ground_truth: list[int],
) -> dict[str, float]:
    """Compute classification metrics.
    
    Args:
        predictions: List of predicted labels (0=faithful, 1=hallucinated)
        ground_truth: List of ground truth labels
    
    Returns:
        Dictionary with precision, recall, f1, and accuracy
    """
    if len(predictions) != len(ground_truth):
        raise ValueError("Predictions and ground truth must have same length")
    
    if len(predictions) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "accuracy": 0.0}
    
    # Compute true positives, false positives, false negatives
    tp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 1)
    fp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 0)
    fn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 1)
    tn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 0)
    
    # Compute metrics
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(predictions) if len(predictions) > 0 else 0.0
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


@app.command()
def eval(
    dataset: str = typer.Option(
        "demo",
        "--dataset",
        help="Dataset to evaluate: 'demo', 'halubench', 'halueval'"
    ),
    policy: str = typer.Option(
        "default",
        "--policy",
        help="Policy to use: 'default', 'rag_strict', 'chatbot', or path to YAML file"
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Path to save results as JSON"
    ),
    max_samples: Optional[int] = typer.Option(
        None,
        "--max-samples",
        help="Maximum number of samples to evaluate (default: all)"
    ),
) -> None:
    """Evaluate HallucinationGuard on a benchmark dataset.
    
    Runs validation on benchmark examples and computes precision, recall, F1,
    and accuracy metrics. Results are displayed in a table and optionally
    saved to a JSON file.
    
    Examples:
        verdict eval --dataset demo --policy default
        verdict eval --dataset halubench --policy rag_strict --output results.json
    """
    console.print(f"\n[bold]HallucinationGuard Evaluation[/bold]")
    console.print(f"Dataset: {dataset}, Policy: {policy}\n")
    
    # Load dataset
    try:
        examples = load_dataset(dataset)
        if not examples:
            console.print("[red]Error: Dataset is empty[/red]")
            sys.exit(1)
        
        if max_samples:
            examples = examples[:max_samples]
        
        console.print(f"Loaded {len(examples)} examples")
    except Exception as e:
        console.print(f"[red]Error loading dataset: {e}[/red]")
        logger.error(f"Dataset load error: {e}", exc_info=True)
        sys.exit(1)
    
    # Initialize guard
    try:
        guard = Guard(policy=policy)
        console.print(f"Loaded policy: {guard.policy.name}")
    except PolicyLoadError as e:
        console.print(f"[red]Error loading policy: {e}[/red]")
        logger.error(f"Policy load error: {e}", exc_info=True)
        sys.exit(1)
    
    # Run validation
    console.print("\nRunning validation...\n")
    predictions = []
    latencies = []
    results_detail = []
    
    for i, example in enumerate(examples):
        try:
            decision = guard.validate(
                prompt=example.get("prompt", ""),
                output=example.get("output", ""),
                context=example.get("context"),
            )
            
            # Predict: 0 = faithful (allow/regenerate), 1 = hallucinated (block/abstain)
            prediction = 0 if decision.decision in ["allow", "regenerate"] else 1
            predictions.append(prediction)
            latencies.append(decision.latency_ms)
            
            results_detail.append({
                "prompt": example.get("prompt", "")[:100],  # Truncate for readability
                "decision": decision.decision,
                "risk_score": decision.risk_score,
                "latency_ms": decision.latency_ms,
            })
            
            if (i + 1) % max(1, len(examples) // 10) == 0:
                console.print(f"  Progress: {i + 1}/{len(examples)}")
        
        except Exception as e:
            logger.error(f"Validation error on example {i}: {e}", exc_info=True)
            # Treat validation errors as uncertain (neutral prediction)
            predictions.append(0)
            latencies.append(0.0)
    
    # Compute metrics
    ground_truth = [ex.get("label", 0) for ex in examples]
    metrics = compute_metrics(predictions, ground_truth)
    
    # Compute latency stats
    latencies_valid = [l for l in latencies if l > 0]
    avg_latency = sum(latencies_valid) / len(latencies_valid) if latencies_valid else 0.0
    
    # Display results table
    table = Table(title="Evaluation Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Samples", str(len(examples)))
    table.add_row("Precision", f"{metrics['precision']:.4f}")
    table.add_row("Recall", f"{metrics['recall']:.4f}")
    table.add_row("F1 Score", f"{metrics['f1']:.4f}")
    table.add_row("Accuracy", f"{metrics['accuracy']:.4f}")
    table.add_row("Avg Latency (ms)", f"{avg_latency:.2f}")
    
    console.print(table)
    
    # Save to JSON if requested
    if output:
        try:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            results = {
                "dataset": dataset,
                "policy": policy,
                "metrics": metrics,
                "latency_stats": {
                    "avg_ms": avg_latency,
                    "min_ms": min(latencies_valid) if latencies_valid else 0.0,
                    "max_ms": max(latencies_valid) if latencies_valid else 0.0,
                },
                "details": results_detail[:20],  # Limit details to first 20
            }
            
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            
            console.print(f"\n[green]Results saved to {output_path}[/green]")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            console.print(f"[yellow]Warning: Failed to save results: {e}[/yellow]")
    
    console.print("")


def run_single_validation(
    prompt: str,
    output: str,
    context: Optional[str],
    guard: Guard,
) -> float:
    """Run a single validation and return latency.
    
    Args:
        prompt: User prompt
        output: Model output
        context: Optional context
        guard: Guard instance
    
    Returns:
        Latency in milliseconds
    """
    decision = guard.validate(prompt=prompt, output=output, context=context)
    return decision.latency_ms


@app.command()
def benchmark(
    requests: int = typer.Option(
        1000,
        "--requests",
        help="Number of requests to send"
    ),
    concurrency: int = typer.Option(
        10,
        "--concurrency",
        help="Number of concurrent workers"
    ),
    policy: str = typer.Option(
        "default",
        "--policy",
        help="Policy to use: 'default', 'rag_strict', 'chatbot', or path to YAML file"
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Path to save results as JSON"
    ),
) -> None:
    """Benchmark HallucinationGuard latency under concurrent load.
    
    Measures p50, p95, and p99 latency percentiles by running multiple
    concurrent validation requests. Uses a fixed set of prompts and rotates
    through them.
    
    Examples:
        verdict benchmark --requests 100 --concurrency 5
        verdict benchmark --requests 1000 --concurrency 10 --policy rag_strict --output bench.json
    """
    console.print(f"\n[bold]HallucinationGuard Benchmark[/bold]")
    console.print(f"Requests: {requests}, Concurrency: {concurrency}, Policy: {policy}\n")
    
    # Initialize guard
    try:
        guard = Guard(policy=policy)
        console.print(f"Loaded policy: {guard.policy.name}")
    except PolicyLoadError as e:
        console.print(f"[red]Error loading policy: {e}[/red]")
        logger.error(f"Policy load error: {e}", exc_info=True)
        sys.exit(1)
    
    # Use demo dataset for prompts (doesn't require datasets library)
    prompts = DEMO_DATASET
    
    # Run benchmark
    console.print(f"\nSending {requests} requests with {concurrency} workers...\n")
    
    latencies: list[float] = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        
        for i in range(requests):
            # Rotate through prompts
            prompt_data = prompts[i % len(prompts)]
            
            future = executor.submit(
                run_single_validation,
                prompt=prompt_data["prompt"],
                output=prompt_data["output"],
                context=prompt_data["context"],
                guard=guard,
            )
            futures.append(future)
        
        # Collect results
        for i, future in enumerate(as_completed(futures)):
            try:
                latency = future.result(timeout=30)
                latencies.append(latency)
            except Exception as e:
                logger.error(f"Request {i} failed: {e}")
                # Skip failed requests in latency calculations
            
            if (i + 1) % max(1, requests // 10) == 0:
                console.print(f"  Progress: {i + 1}/{requests}")
    
    total_time = time.time() - start_time
    
    # Compute percentiles
    if not latencies:
        console.print("[red]Error: No successful requests[/red]")
        sys.exit(1)
    
    latencies.sort()
    p50_idx = len(latencies) // 2
    p95_idx = int(len(latencies) * 0.95)
    p99_idx = int(len(latencies) * 0.99)
    
    p50 = latencies[p50_idx] if p50_idx < len(latencies) else latencies[-1]
    p95 = latencies[p95_idx] if p95_idx < len(latencies) else latencies[-1]
    p99 = latencies[p99_idx] if p99_idx < len(latencies) else latencies[-1]
    
    avg_latency = sum(latencies) / len(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    throughput = len(latencies) / total_time
    
    # Display results table
    table = Table(title="Benchmark Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Successful Requests", str(len(latencies)))
    table.add_row("Total Time (s)", f"{total_time:.2f}")
    table.add_row("Throughput (req/s)", f"{throughput:.2f}")
    table.add_row("Min Latency (ms)", f"{min_latency:.2f}")
    table.add_row("Avg Latency (ms)", f"{avg_latency:.2f}")
    table.add_row("P50 Latency (ms)", f"{p50:.2f}")
    table.add_row("P95 Latency (ms)", f"{p95:.2f}")
    table.add_row("P99 Latency (ms)", f"{p99:.2f}")
    table.add_row("Max Latency (ms)", f"{max_latency:.2f}")
    
    console.print(table)
    
    # Save to JSON if requested
    if output:
        try:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            results = {
                "policy": policy,
                "requests": requests,
                "concurrency": concurrency,
                "successful": len(latencies),
                "total_time_s": total_time,
                "throughput_req_s": throughput,
                "latency_stats": {
                    "min_ms": min_latency,
                    "avg_ms": avg_latency,
                    "p50_ms": p50,
                    "p95_ms": p95,
                    "p99_ms": p99,
                    "max_ms": max_latency,
                },
            }
            
            with open(output_path, "w") as f:
                json.dump(results, f, indent=2)
            
            console.print(f"\n[green]Results saved to {output_path}[/green]")
        except Exception as e:
            logger.error(f"Error saving results: {e}")
            console.print(f"[yellow]Warning: Failed to save results: {e}[/yellow]")
    
    console.print("")


if __name__ == "__main__":
    app()
