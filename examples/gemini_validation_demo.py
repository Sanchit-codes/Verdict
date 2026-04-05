#!/usr/bin/env python3
"""Gemini integration demo: Generate + Validate pipeline.

This example demonstrates the complete HallucinationGuard workflow with Google Gemini:

1. Generate text using Gemini 2.5 Flash
2. Validate output through 3-tier cascade (heuristics → embeddings → HHEM)
3. Display decision with evidence and risk scores

The script shows both:
- **Faithful outputs**: Generated text that aligns with context (ALLOW)
- **Hallucinated outputs**: Generated text with facts not in context (BLOCK)

This is the simplest entry point for integrating HallucinationGuard with Gemini.

Required environment variable:
    GOOGLE_API_KEY: Your Google API key for Gemini access (get one at https://aistudio.google.com/apikey)

Installation:
    pip install google-generativeai rich

Usage:
    export GOOGLE_API_KEY=your_key_here
    python examples/gemini_validation_demo.py

Typical output:
    ✓ Case 1: Faithful output allowed
    ✗ Case 2: Hallucinated output blocked
    ✓ Case 3: Ambiguous output flagged for review
"""

import os
import sys
import logging
from typing import Optional

try:
    import google.generativeai as genai
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError as e:
    print("Error: Missing required dependencies.")
    print("Install with: pip install google-generativeai rich")
    sys.exit(1)

from hallucination_guard import Guard, HallucinationBlockedError


# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize rich console for formatting
console = Console()


def setup_guard() -> Guard:
    """Initialize HallucinationGuard with default policy.

    Returns:
        Configured Guard instance ready for validation.

    Raises:
        ValueError: If GOOGLE_API_KEY is not set.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print(
            "[red]Error: GOOGLE_API_KEY environment variable not set[/red]\n"
            "Set it with: [yellow]export GOOGLE_API_KEY=your_key[/yellow]"
        )
        sys.exit(1)

    # Configure Gemini API
    genai.configure(api_key=api_key)

    # Initialize HallucinationGuard with default policy
    guard = Guard(policy="default")
    return guard


def setup_gemini_model():
    """Initialize Google Gemini 2.5 Flash model.

    Returns:
        Configured GenerativeModel instance.
    """
    return genai.GenerativeModel("gemini-2.5-flash")


def format_decision(
    decision_str: str,
    risk_score: float,
    latency_ms: float,
    evidence: Optional[str] = None
) -> str:
    """Format validation decision for display.

    Args:
        decision_str: Decision type (allow/block/regenerate/abstain)
        risk_score: Risk score from 0.0 to 1.0
        latency_ms: Validation latency in milliseconds
        evidence: Optional evidence/reason for decision

    Returns:
        Formatted string ready for rich output.
    """
    # Color code based on decision
    if decision_str == "allow":
        icon = "[green]✓[/green]"
        decision_text = "[green]ALLOWED[/green]"
    elif decision_str == "block":
        icon = "[red]✗[/red]"
        decision_text = "[red]BLOCKED[/red]"
    elif decision_str == "regenerate":
        icon = "[yellow]↻[/yellow]"
        decision_text = "[yellow]REGENERATE[/yellow]"
    else:  # abstain
        icon = "[cyan]?[/cyan]"
        decision_text = "[cyan]ABSTAIN[/cyan]"

    result = f"{icon} {decision_text} (risk={risk_score:.2f}, latency={latency_ms:.1f}ms)"
    if evidence:
        result += f"\n   Evidence: {evidence[:150]}..."
    return result


def demo_case_1_faithful(guard: Guard, model) -> None:
    """Demo Case 1: Faithful output within context.

    This case generates a response about renewable energy using only
    facts from the provided context. The output should PASS validation.

    Args:
        guard: Initialized Guard instance.
        model: Configured Gemini model.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Case 1: Faithful Output (Expected: ALLOWED)[/bold]")
    console.print("=" * 80)

    prompt = "What is renewable energy? List 2-3 key characteristics."

    context = (
        "Renewable energy refers to energy derived from natural sources that are "
        "constantly replenished, such as sunlight, wind, water, and geothermal heat. "
        "Unlike fossil fuels, renewable energy sources do not deplete as they are used. "
        "Key characteristics include: (1) Sustainability - they are continuously "
        "replenished by nature, (2) Environmental benefit - they produce little to no "
        "greenhouse gas emissions, (3) Economic advantage - costs are becoming "
        "competitive with fossil fuels."
    )

    console.print(f"[bold]Prompt:[/bold]\n{prompt}")
    console.print(f"\n[bold]Context (Reference):[/bold]\n{context}")

    # Generate with Gemini
    console.print("\n[bold]Generating with Gemini 2.5 Flash...[/bold]")
    try:
        response = model.generate_content(
            f"Answer this question based on the provided context. Keep answer to 2-3 sentences.\n\n"
            f"Context: {context}\n\n"
            f"Question: {prompt}"
        )
        output = response.text
        console.print(f"[bold]Generated Output:[/bold]\n{output}")
    except Exception as e:
        console.print(f"[red]Error generating with Gemini: {e}[/red]")
        return

    # Validate with HallucinationGuard
    console.print("\n[bold]Validating output...[/bold]")
    try:
        decision = guard.validate(
            prompt=prompt,
            output=output,
            context=context,
            domain="energy"
        )

        result_text = format_decision(
            decision_str=decision.decision,
            risk_score=decision.risk_score,
            latency_ms=decision.latency_ms,
            evidence=decision.evidence
        )
        console.print(f"[bold]Validation Result:[/bold]\n{result_text}")

        if decision.decision == "allow":
            console.print("\n[green]✓ Faithful output successfully validated![/green]")
        else:
            console.print(f"\n[yellow]Note: Output was {decision.decision.upper()}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error during validation: {e}[/red]")


def demo_case_2_hallucinated(guard: Guard, model) -> None:
    """Demo Case 2: Hallucinated output with made-up facts.

    This case generates a response that may include facts not present
    in the context. The system should BLOCK or FLAG this output.

    Args:
        guard: Initialized Guard instance.
        model: Configured Gemini model.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Case 2: Potentially Hallucinated Output (Expected: BLOCKED/FLAGGED)[/bold]")
    console.print("=" * 80)

    prompt = "What are the specific efficiency percentages and cost comparisons for solar vs fossil fuels?"

    context = (
        "Renewable energy like solar is increasingly cost-competitive with fossil fuels. "
        "Solar technology has become more efficient in recent years."
    )

    console.print(f"[bold]Prompt:[/bold]\n{prompt}")
    console.print(f"\n[bold]Context (Reference):[/bold]\n{context}")
    console.print("\n[yellow]Note: Prompt asks for specific numbers not in context![/yellow]")

    # Generate with Gemini
    console.print("\n[bold]Generating with Gemini 2.5 Flash...[/bold]")
    try:
        response = model.generate_content(
            f"Answer this question based on the provided context. If the context "
            f"doesn't have specific numbers, say you don't have that data.\n\n"
            f"Context: {context}\n\n"
            f"Question: {prompt}"
        )
        output = response.text
        console.print(f"[bold]Generated Output:[/bold]\n{output}")
    except Exception as e:
        console.print(f"[red]Error generating with Gemini: {e}[/red]")
        return

    # Validate with HallucinationGuard
    console.print("\n[bold]Validating output...[/bold]")
    try:
        decision = guard.validate(
            prompt=prompt,
            output=output,
            context=context,
            domain="energy"
        )

        result_text = format_decision(
            decision_str=decision.decision,
            risk_score=decision.risk_score,
            latency_ms=decision.latency_ms,
            evidence=decision.evidence
        )
        console.print(f"[bold]Validation Result:[/bold]\n{result_text}")

        if decision.decision == "block":
            console.print("\n[green]✓ Hallucination successfully detected and blocked![/green]")
        elif decision.decision == "abstain":
            console.print("\n[yellow]⚠ Output flagged for manual review (uncertain)[/yellow]")
        else:
            console.print(f"\n[cyan]Note: Output was {decision.decision.upper()}[/cyan]")
    except HallucinationBlockedError as e:
        console.print(f"[red]✗ Blocked: {e.evidence}[/red]")
        console.print("\n[green]✓ Hallucination successfully blocked![/green]")
    except Exception as e:
        console.print(f"[red]Error during validation: {e}[/red]")


def demo_case_3_contextual(guard: Guard, model) -> None:
    """Demo Case 3: Ambiguous output requiring context sensitivity.

    This case generates a response that may be technically correct but
    requires careful evaluation in context. Good for testing ABSTAIN decision.

    Args:
        guard: Initialized Guard instance.
        model: Configured Gemini model.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Case 3: Contextual Output (May be ABSTAINED/REVIEWED)[/bold]")
    console.print("=" * 80)

    prompt = "Is wind energy always reliable and cost-effective?"

    context = (
        "Wind energy is a renewable energy source that converts wind power into "
        "electricity. Wind farms have become increasingly common. The cost of wind "
        "energy has decreased significantly over the past decade."
    )

    console.print(f"[bold]Prompt:[/bold]\n{prompt}")
    console.print(f"\n[bold]Context (Reference):[/bold]\n{context}")

    # Generate with Gemini
    console.print("\n[bold]Generating with Gemini 2.5 Flash...[/bold]")
    try:
        response = model.generate_content(
            f"Answer this question based on the provided context.\n\n"
            f"Context: {context}\n\n"
            f"Question: {prompt}"
        )
        output = response.text
        console.print(f"[bold]Generated Output:[/bold]\n{output}")
    except Exception as e:
        console.print(f"[red]Error generating with Gemini: {e}[/red]")
        return

    # Validate with HallucinationGuard
    console.print("\n[bold]Validating output...[/bold]")
    try:
        decision = guard.validate(
            prompt=prompt,
            output=output,
            context=context,
            domain="energy"
        )

        result_text = format_decision(
            decision_str=decision.decision,
            risk_score=decision.risk_score,
            latency_ms=decision.latency_ms,
            evidence=decision.evidence
        )
        console.print(f"[bold]Validation Result:[/bold]\n{result_text}")

        if decision.decision == "abstain":
            console.print(
                "\n[cyan]ℹ Output requires human review (uncertain decision)[/cyan]"
            )
        else:
            console.print(f"\n[cyan]Output: {decision.decision.upper()}[/cyan]")
    except Exception as e:
        console.print(f"[red]Error during validation: {e}[/red]")


def show_policy_config(guard: Guard) -> None:
    """Display the active policy configuration.

    Args:
        guard: Guard instance to extract policy info from.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Active Policy Configuration[/bold]")
    console.print("=" * 80)

    policy = guard.policy

    # Create configuration table
    table = Table(title="Policy Settings")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Policy Name", policy.name)
    table.add_row("Description", policy.description[:50] + "...")
    table.add_row("Risk Threshold", f"{policy.risk_threshold:.2f}")
    table.add_row("Latency Budget", f"{policy.latency_budget_ms}ms")

    console.print(table)

    # Validators info
    console.print("\n[bold]Validators (3-Tier Cascade):[/bold]")
    for i, validator_cfg in enumerate(policy.validators, 1):
        if not validator_cfg.enabled:
            continue
        icon = "[green]✓[/green]" if validator_cfg.enabled else "[red]✗[/red]"
        console.print(
            f"{icon} Tier {i}: {validator_cfg.name.upper()}\n"
            f"   Weight: {validator_cfg.weight:.1%} | "
            f"Threshold: {validator_cfg.threshold:.2f} | "
            f"Timeout: {validator_cfg.timeout_ms}ms"
        )


def main() -> None:
    """Run the Gemini validation demo."""
    console.print("\n")
    console.print(
        Panel(
            "[bold cyan]Gemini + HallucinationGuard Demo[/bold cyan]\n"
            "Generate text with Gemini, validate with 3-tier cascade",
            expand=False
        )
    )

    # Initialize
    console.print("[bold]Setting up Gemini and HallucinationGuard...[/bold]")
    try:
        guard = setup_guard()
        model = setup_gemini_model()
        console.print("[green]✓ Setup complete[/green]")
    except Exception as e:
        console.print(f"[red]Error during setup: {e}[/red]")
        sys.exit(1)

    # Show configuration
    show_policy_config(guard)

    # Run demo cases
    console.print("\n[bold]Running validation demos...[/bold]")
    console.print(
        "[cyan]Each case generates text with Gemini and validates with HallucinationGuard[/cyan]"
    )

    demo_case_1_faithful(guard, model)
    demo_case_2_hallucinated(guard, model)
    demo_case_3_contextual(guard, model)

    # Summary
    console.print("\n" + "=" * 80)
    console.print("[bold]Demo Complete[/bold]")
    console.print("=" * 80)
    console.print(
        "[cyan]Key Takeaways:[/cyan]\n"
        "  • Generate text freely with any LLM (here: Gemini 2.5 Flash)\n"
        "  • Validate output through 3-tier cascade:\n"
        "    - Tier 1: Fast heuristics (<5ms)\n"
        "    - Tier 2: Semantic similarity checking (<30ms)\n"
        "    - Tier 3: Deep faithfulness classification (<80ms)\n"
        "  • Decisions: ALLOW (safe) | BLOCK (hallucinated) | ABSTAIN (uncertain)\n"
        "  • Policy controls thresholds and mitigation actions\n"
        "  • All validation happens locally—no additional API calls\n"
    )
    console.print()


if __name__ == "__main__":
    main()
