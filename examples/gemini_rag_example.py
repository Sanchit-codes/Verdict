#!/usr/bin/env python3
"""Primary demo: HallucinationGuard + Gemini RAG validation.

This example showcases the HallucinationGuard SDK integrated with Google Gemini,
demonstrating the three-tier cascade validation pipeline in action. It shows:

1. Blocked hallucinations (detected via heuristics, embeddings, and HHEM)
2. Allowed faithful outputs (pass validation)
3. Auto-regeneration behavior (optional, if configured)

The demo uses the rag_strict policy, designed for high-risk domains like
healthcare and finance where hallucination prevention is critical.

Required environment variable:
    GOOGLE_API_KEY: Your Google API key for Gemini access

Usage:
    export GOOGLE_API_KEY=your_key_here
    python examples/gemini_rag_example.py

Typical output:
    ✓ Case 1: Output allowed (risk_score=0.15, latency_ms=45.2)
    ✗ Case 2: Output blocked (risk_score=0.82, latency_ms=52.3)
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
from hallucination_guard.integrations import GuardedGemini


# Configure logging for visibility into validation pipeline
logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize rich console for nice formatting
console = Console()


def setup_guarded_gemini() -> GuardedGemini:
    """Initialize GuardedGemini with rag_strict policy.

    Returns:
        Configured GuardedGemini instance ready for validation.

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

    # Create base Gemini model
    base_model = genai.GenerativeModel("gemini-2.5-flash")

    # Wrap with HallucinationGuard using rag_strict policy
    # rag_strict is designed for high-risk domains with lower thresholds
    guarded = GuardedGemini(
        model=base_model,
        policy="rag_strict",
        max_retries=1  # Auto-regenerate once if validation fails
    )

    return guarded


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


def demo_case_1_hallucinated(guarded: GuardedGemini, context: str) -> None:
    """Demo Case 1: Hallucinated output that should be blocked.

    This case shows the system detecting a hallucination where the model
    makes up facts not supported by the context.

    Args:
        guarded: Initialized GuardedGemini instance.
        context: Reference context for validation.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Case 1: Hallucinated Output (Should Be BLOCKED)[/bold]")
    console.print("=" * 80)

    prompt = (
        "What are the main benefits of solar energy "
        "compared to fossil fuels?"
    )

    console.print(f"\n[bold]Prompt:[/bold]\n{prompt}")
    console.print(f"\n[bold]Context (RAG source):[/bold]\n{context}")

    try:
        # Generate and validate
        output = guarded.generate(
            prompt=prompt,
            context=context,
            domain="energy"
        )
        console.print(f"\n[bold]Output:[/bold]\n{output}")
        console.print(
            "\n[yellow]Warning: Output was allowed "
            "(expected block in this demo)[/yellow]"
        )
    except HallucinationBlockedError as e:
        evidence_preview = e.evidence[:200] if e.evidence else "Unknown"
        console.print(
            f"\n[bold]Output:[/bold]\n[red]{evidence_preview}...[/red]"
        )
        decision_str = format_decision(
            decision_str="block",
            risk_score=e.risk_score,
            latency_ms=0,  # Not tracked in exception
            evidence=e.evidence
        )
        console.print(f"\n[bold]Validation Result:[/bold]\n{decision_str}")
        console.print("\n[green]✓ Hallucination successfully blocked![/green]")


def demo_case_2_faithful(guarded: GuardedGemini, context: str) -> None:
    """Demo Case 2: Faithful output that should be allowed.

    This case shows the system correctly identifying output that aligns
    with the provided context.

    Args:
        guarded: Initialized GuardedGemini instance.
        context: Reference context for validation.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Case 2: Faithful Output (Should Be ALLOWED)[/bold]")
    console.print("=" * 80)

    prompt = "What is renewable energy?"

    console.print(f"\n[bold]Prompt:[/bold]\n{prompt}")
    console.print(f"\n[bold]Context (RAG source):[/bold]\n{context}")

    try:
        # Generate and validate
        output = guarded.generate(
            prompt=prompt,
            context=context,
            domain="energy"
        )
        console.print(f"\n[bold]Output:[/bold]\n{output}")
        console.print(
            f"\n[bold]Validation Result:[/bold]\n[green]✓ Output allowed[/green]"
        )
        console.print("\n[green]✓ Faithful output successfully validated![/green]")
    except HallucinationBlockedError as e:
        console.print(f"\n[bold]Output:[/bold]\n[red]BLOCKED[/red]")
        decision_str = format_decision(
            decision_str="block",
            risk_score=e.risk_score,
            latency_ms=0,
            evidence=e.evidence
        )
        console.print(f"\n[bold]Validation Result:[/bold]\n{decision_str}")
        console.print(
            "\n[yellow]Note: This output was blocked "
            "(might be a false positive)[/yellow]"
        )


def demo_validation_metrics(guard: Guard) -> None:
    """Show validation metrics and policy configuration.

    Args:
        guard: Guard instance to extract policy info from.
    """
    console.print("\n" + "=" * 80)
    console.print("[bold]Validation Pipeline Configuration[/bold]")
    console.print("=" * 80)

    policy = guard.policy

    # Create metrics table
    table = Table(title="Policy Configuration")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Policy Name", policy.name)
    table.add_row("Description", policy.description)
    table.add_row("Risk Threshold", f"{policy.risk_threshold:.2f}")
    table.add_row("Latency Budget", f"{policy.latency_budget_ms}ms")

    console.print(table)

    # Validators configuration
    console.print("\n[bold]Validators (3-Tier Cascade):[/bold]")
    for i, validator_cfg in enumerate(policy.validators, 1):
        if not validator_cfg.enabled:
            continue
        status = "[green]✓[/green]" if validator_cfg.enabled else "[red]✗[/red]"
        console.print(
            f"{status} Tier {i}: {validator_cfg.name.upper()}\n"
            f"   Weight: {validator_cfg.weight:.1%} | "
            f"Threshold: {validator_cfg.threshold:.2f} | "
            f"Timeout: {validator_cfg.timeout_ms}ms"
        )

    console.print("\n[bold]Mitigation Actions:[/bold]")
    mitigation = policy.mitigation
    console.print(f"On Block: {mitigation.on_block.upper()}")
    console.print(f"On Timeout: {mitigation.on_timeout.upper()}")
    console.print(f"On Error: {mitigation.on_error.upper()}")


def main() -> None:
    """Run the primary HallucinationGuard + Gemini demo."""
    console.print("\n")
    console.print(
        Panel(
            "[bold cyan]HallucinationGuard + Gemini RAG Demo[/bold cyan]\n"
            "Demonstrating 3-tier cascade validation pipeline",
            expand=False
        )
    )

    # Setup
    console.print("[bold]Setting up GuardedGemini with rag_strict policy...[/bold]")
    try:
        guarded = setup_guarded_gemini()
        console.print("[green]✓ GuardedGemini initialized successfully[/green]")
    except Exception as e:
        console.print(f"[red]Error initializing GuardedGemini: {e}[/red]")
        sys.exit(1)

    # Show policy configuration
    demo_validation_metrics(guarded.guard)

    # Prepare sample context (renewable energy domain)
    context = """
    Renewable energy refers to energy derived from natural sources that are
    constantly replenished, such as sunlight, wind, water, and geothermal heat.
    Unlike fossil fuels, renewable energy sources do not deplete as they are
    used. Common renewable energy technologies include:

    1. Solar Energy: Converted to electricity via photovoltaic panels or
       concentrated solar power
    2. Wind Energy: Generated by wind turbines that convert kinetic energy
       to electricity
    3. Hydroelectric Power: Created by flowing or falling water driving turbines
    4. Geothermal Energy: Heat from within the Earth used for electricity
       generation

    Renewable sources are environmentally friendly and help reduce greenhouse
    gas emissions. They are becoming increasingly cost-competitive with fossil
    fuels.
    """

    # Run demo cases
    console.print("\n[bold]Running validation demos...[/bold]")

    # Note: In production, you would generate actual Gemini outputs
    # For this demo, we call the API with prompts designed to elicit hallucinations
    demo_case_1_hallucinated(guarded, context)
    demo_case_2_faithful(guarded, context)

    # Summary
    console.print("\n" + "=" * 80)
    console.print("[bold]Demo Complete[/bold]")
    console.print("=" * 80)
    console.print(
        "[cyan]Key Takeaways:[/cyan]\n"
        "  • HallucinationGuard uses a 3-tier cascade for efficient validation\n"
        "  • Tier 1 (Heuristics): Fast pattern matching (<5ms)\n"
        "  • Tier 2 (Embeddings): Semantic similarity checking (<30ms)\n"
        "  • Tier 3 (HHEM): Deep faithfulness classification (<80ms)\n"
        "  • Policy controls thresholds and mitigation actions\n"
        "  • GuardedGemini auto-regenerates on 'regenerate' decision\n"
    )
    console.print()


if __name__ == "__main__":
    main()
