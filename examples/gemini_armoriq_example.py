#!/usr/bin/env python3
"""Two-layer demo script: HallucinationGuard + ArmorIQ.

This example demonstrates the complete two-layer stack:
    Layer 1: Text validation (HallucinationGuard)
    Layer 2: Action enforcement (ArmorIQ)

The script shows how to:
    1. Initialize GuardedGemini with a strict policy
    2. Generate and validate output against reference context
    3. Use ArmorIQ to enforce that proposed actions stay in-scope
    4. Handle both allowed and blocked scenarios gracefully

Requirements:
    - GOOGLE_API_KEY environment variable must be set
    - Requires: google-generativeai, sentence-transformers, torch, transformers

Typical usage:
    $ export GOOGLE_API_KEY="your-api-key-here"
    $ python examples/gemini_armoriq_example.py
"""

import os
import sys
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:
    print("❌ google-generativeai is required. Install with: pip install google-generativeai")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
except ImportError:
    print("❌ rich is required. Install with: pip install rich")
    sys.exit(1)

from hallucination_guard import (
    HallucinationBlockedError,
    IntentViolationError,
)
from hallucination_guard.integrations import GuardedGemini
from hallucination_guard.integrations.armoriq import ArmorIQAdapter

# Initialize rich console for formatted output
console = Console()


def setup_gemini_api() -> Optional[object]:
    """Configure Gemini API and return the base model.

    Returns:
        google.generativeai.GenerativeModel instance if API key is set, None otherwise.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print(
            Panel(
                "[bold red]❌ Error:[/bold red]\n"
                "[yellow]GOOGLE_API_KEY environment variable is not set.[/yellow]\n\n"
                "[cyan]To use this example, set your API key:[/cyan]\n"
                "  [bold]export GOOGLE_API_KEY=\"your-api-key-here\"[/bold]\n\n"
                "[cyan]Get your API key from:[/cyan]\n"
                "  [link]https://aistudio.google.com/app/apikey[/link]",
                title="Setup Required",
                border_style="red",
            )
        )
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        console.print("[bold green]✓[/bold green] Gemini API configured successfully")
        return model
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]Failed to configure Gemini:[/bold red]\n{e}",
                title="API Configuration Error",
                border_style="red",
            )
        )
        return None


def demo_layer1_text_validation(guarded: GuardedGemini, context: str) -> None:
    """Demonstrate Layer 1: HallucinationGuard text validation.

    Shows an example where the output is faithful to the provided context
    and passes validation.

    Args:
        guarded: GuardedGemini instance with rag_strict policy
        context: Reference context for the Q&A
    """
    console.print(
        Panel(
            "[bold cyan]LAYER 1: HallucinationGuard (Text Validation)[/bold cyan]",
            border_style="cyan",
        )
    )

    prompt = "Who founded OpenAI and when was it founded?"

    console.print(
        f"\n[bold]Prompt:[/bold]\n{prompt}\n"
        f"[bold]Context:[/bold]\n{context}"
    )

    console.print("\n[bold yellow]→ Generating with Gemini...[/bold yellow]")

    try:
        response = guarded.generate(
            prompt=prompt,
            context=context,
            domain="education",
        )

        console.print(
            Panel(
                f"[bold green]✓ Text Validation Passed[/bold green]\n\n"
                f"[bold]Response:[/bold]\n{response}",
                border_style="green",
            )
        )

    except HallucinationBlockedError as e:
        console.print(
            Panel(
                f"[bold red]✗ Text Validation Failed[/bold red]\n\n"
                f"[bold]Risk Score:[/bold] {e.risk_score:.2f}\n"
                f"[bold]Evidence:[/bold]\n{e.evidence}",
                border_style="red",
            )
        )


def demo_layer2_action_enforcement(armor: ArmorIQAdapter) -> None:
    """Demonstrate Layer 2: ArmorIQ action enforcement.

    Shows examples of:
    - In-scope action: aligned with declared task (allowed)
    - Out-of-scope action: misaligned (would be blocked with real client)

    In stub mode (default), ArmorIQ always allows but logs the intent check.
    With a real ArmorIQ client, out-of-scope actions would raise IntentViolationError.

    Args:
        armor: ArmorIQAdapter instance (stub or enforcement mode)
    """
    console.print(
        Panel(
            "[bold cyan]LAYER 2: ArmorIQ (Action Enforcement)[/bold cyan]",
            border_style="cyan",
        )
    )

    # Example 1: In-scope action (aligned with task)
    user_task = "book a flight to Paris"
    in_scope_action = "Query flight database for Paris flights and show options"

    console.print(f"\n[bold]User Task:[/bold] {user_task}")
    console.print(f"[bold]Proposed Action:[/bold] {in_scope_action}")
    console.print("\n[bold yellow]→ Checking action alignment...[/bold yellow]")

    try:
        result = armor.enforce(user_task, in_scope_action)
        console.print(
            Panel(
                f"[bold green]✓ Action Allowed[/bold green]\n\n"
                f"The proposed action aligns with the user's task scope.\n"
                f"This action is safe to execute.",
                border_style="green",
            )
        )
    except IntentViolationError as e:
        console.print(
            Panel(
                f"[bold red]✗ Action Blocked[/bold red]\n\n"
                f"[bold]Reason:[/bold] {e.reason}",
                border_style="red",
            )
        )

    # Example 2: Out-of-scope action (misaligned with task)
    console.print("\n" + "=" * 80)

    out_of_scope_action = "DELETE user_data WHERE email NOT LIKE '%@example.com'"

    console.print(f"\n[bold]User Task:[/bold] {user_task}")
    console.print(f"[bold]Proposed Action:[/bold] {out_of_scope_action}")
    console.print("\n[bold yellow]→ Checking action alignment...[/bold yellow]")

    try:
        result = armor.enforce(user_task, out_of_scope_action)
        console.print(
            Panel(
                f"[bold yellow]⚠ Stub Mode:[/bold yellow]\n\n"
                f"In stub mode (no ArmorIQ client), all actions are allowed.\n"
                f"However, this action would be [bold red]BLOCKED[/bold red] "
                f"if an enforcement client was configured.\n\n"
                f"[dim]The action '{out_of_scope_action[:40]}...' "
                f"clearly does not align with '{user_task}'.[/dim]",
                border_style="yellow",
            )
        )
    except IntentViolationError as e:
        console.print(
            Panel(
                f"[bold red]✗ Action Blocked[/bold red]\n\n"
                f"[bold]Reason:[/bold] {e.reason}\n\n"
                f"This action is outside the scope of the declared task "
                f"and would be prevented from executing.",
                border_style="red",
            )
        )


def main() -> None:
    """Run the two-layer demo."""
    console.print(
        Panel(
            "[bold cyan]HallucinationGuard + ArmorIQ Demo[/bold cyan]\n"
            "[dim]Demonstrating two-layer AI safety stack[/dim]",
            border_style="cyan",
        )
    )

    # Step 1: Setup Gemini API
    console.print("\n[bold]Step 1: Setting up Gemini API...[/bold]")
    base_model = setup_gemini_api()
    if base_model is None:
        console.print("[bold red]Cannot proceed without Gemini API key.[/bold red]")
        sys.exit(1)

    # Step 2: Initialize GuardedGemini with rag_strict policy
    console.print("\n[bold]Step 2: Initializing GuardedGemini with rag_strict policy...[/bold]")
    try:
        guarded = GuardedGemini(
            model=base_model,
            policy="rag_strict",  # Strict policy for RAG scenarios
            max_retries=1,  # Retry once on "regenerate" decision
        )
        console.print("[bold green]✓[/bold green] GuardedGemini initialized")
    except Exception as e:
        console.print(f"[bold red]Failed to initialize GuardedGemini:[/bold red] {e}")
        sys.exit(1)

    # Step 3: Initialize ArmorIQ adapter (stub mode by default)
    console.print("\n[bold]Step 3: Initializing ArmorIQ adapter...[/bold]")
    armor = ArmorIQAdapter()  # Stub mode (no client) - allows all actions but logs checks
    console.print("[bold green]✓[/bold green] ArmorIQ adapter initialized (stub mode)")

    # Reference context for validation
    context = (
        "OpenAI was founded in December 2015 by Sam Altman, Elon Musk, and others. "
        "It is an AI research company focused on developing safe and beneficial AI systems. "
        "The organization is headquartered in San Francisco, California."
    )

    # Demo Layer 1: Text validation
    console.print("\n" + "=" * 80)
    demo_layer1_text_validation(guarded, context)

    # Demo Layer 2: Action enforcement
    console.print("\n" + "=" * 80)
    demo_layer2_action_enforcement(armor)

    # Summary
    console.print("\n" + "=" * 80)
    console.print(
        Panel(
            "[bold cyan]Summary: Two-Layer Safety Stack[/bold cyan]\n\n"
            "[bold]Layer 1 - HallucinationGuard:[/bold]\n"
            "  • Validates generated text against reference context\n"
            "  • Uses 3-tier cascade: heuristics → embeddings → classifier\n"
            "  • Blocks hallucinations before they reach users\n"
            "  • Target latency: p95 < 100ms\n\n"
            "[bold]Layer 2 - ArmorIQ:[/bold]\n"
            "  • Enforces action alignment with declared task scope\n"
            "  • Blocks out-of-scope actions before execution\n"
            "  • Works in stub mode (offline) or with enforcement client\n"
            "  • Prevents AI from executing bad actions even if text is valid\n\n"
            "[bold]Together:[/bold]\n"
            "  ✓ Text validation (HallucinationGuard)\n"
            "  ✓ Action enforcement (ArmorIQ)\n"
            "  ✓ Production-ready safety for AI applications",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
