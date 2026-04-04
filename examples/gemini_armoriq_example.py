#!/usr/bin/env python3
"""Two-layer AI safety demo: HallucinationGuard + ArmorIQ (deep integration).

Demonstrates the complete production-ready stack:

  Layer 1 — Text validation (HallucinationGuard):
    Validates Gemini output through a 3-tier cascade before users see it.

  Layer 2 — Action enforcement (ArmorIQ):
    Enforces intent alignment on tool/function calls before they execute.

The script shows three integration patterns:
  (A) GuardedGemini — automatic enforcement via armoriq= param
  (B) Guard.validate — manual enforcement via action_plan= param
  (C) HallucinationGuardCallback — automatic tool enforcement in LangChain

Requirements:
    GOOGLE_API_KEY must be set for Gemini calls.
    pip install google-generativeai rich

Usage:
    $ export GOOGLE_API_KEY="your-key"
    $ python examples/gemini_armoriq_example.py
"""

import os
import sys
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:
    print("❌ google-generativeai required. Install: pip install google-generativeai")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
except ImportError:
    print("❌ rich required. Install: pip install rich")
    sys.exit(1)

from hallucination_guard import Guard, HallucinationBlockedError, IntentViolationError
from hallucination_guard.integrations import GuardedGemini
from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
from hallucination_guard.core.decision import ActionEnforcementResult

console = Console()

# ---------------------------------------------------------------------------
# Shared reference data
# ---------------------------------------------------------------------------

FLIGHT_CONTEXT = (
    "FlightSearch API provides domestic and international flight search. "
    "Supported actions: search_flights(origin, destination, date), "
    "get_flight_details(flight_id), list_airports(country). "
    "The API does NOT support modifying user data, deleting records, or "
    "accessing systems outside the flight search domain."
)

OPENAI_CONTEXT = (
    "OpenAI was founded in December 2015 by Sam Altman, Elon Musk, Greg Brockman, "
    "Ilya Sutskever, Wojciech Zaremba, and John Schulman. It is an AI research company "
    "focused on developing safe and beneficial AI systems, headquartered in San Francisco, "
    "California. GPT-4 and ChatGPT are among its most notable products."
)


# ---------------------------------------------------------------------------
# Pattern A: GuardedGemini with automatic ArmorIQ via constructor
# ---------------------------------------------------------------------------

def demo_guarded_gemini(base_model: object) -> None:
    """Show GuardedGemini with armoriq= wired in at init time.

    After text validation passes, any Gemini function_call in the response
    is automatically enforced against user_task without extra code.
    """
    console.print(
        Panel(
            "[bold cyan]Pattern A: GuardedGemini + ArmorIQ (automatic)[/bold cyan]\n"
            "[dim]armoriq and user_task passed to constructor — zero extra code needed[/dim]",
            border_style="cyan",
        )
    )

    guarded = GuardedGemini(
        model=base_model,
        policy="rag_strict",
        max_retries=1,
        armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
        user_task="search for available flights to Paris",
    )

    console.print(f"\n[bold]Policy:[/bold] rag_strict")
    console.print(f"[bold]ArmorIQ:[/bold] RuleBasedArmorIQClient (offline enforcement)")
    console.print(f"[bold]User task:[/bold] search for available flights to Paris")
    console.print(f"\n[bold]Context provided:[/bold]\n{FLIGHT_CONTEXT}")

    prompt = "What flights are available to Paris today?"
    console.print(f"\n[bold yellow]→ Generating...[/bold yellow] [dim]{prompt}[/dim]")

    try:
        response = guarded.generate(
            prompt=prompt,
            context=FLIGHT_CONTEXT,
            domain="travel",
        )
        console.print(
            Panel(
                f"[bold green]✓ Passed text validation + ArmorIQ[/bold green]\n\n"
                f"[bold]Response:[/bold]\n{response}",
                border_style="green",
            )
        )
    except HallucinationBlockedError as e:
        console.print(
            Panel(
                f"[bold red]✗ Blocked by HallucinationGuard[/bold red]\n"
                f"Risk: {e.risk_score:.2f}  Evidence: {e.evidence}",
                border_style="red",
            )
        )
    except IntentViolationError as e:
        console.print(
            Panel(
                f"[bold red]✗ Blocked by ArmorIQ[/bold red]\n"
                f"Reason: {e.reason}",
                border_style="red",
            )
        )


# ---------------------------------------------------------------------------
# Pattern B: Guard.validate with action_plan= (manual)
# ---------------------------------------------------------------------------

def demo_guard_validate_with_enforcement() -> None:
    """Show Guard.validate carrying an action_plan for manual enforcement.

    Demonstrates:
      - Safe action → ActionEnforcementResult.allowed = True
      - Dangerous action → IntentViolationError raised
    """
    console.print(
        Panel(
            "[bold cyan]Pattern B: Guard.validate + action_plan (manual)[/bold cyan]\n"
            "[dim]action_plan and user_task passed per-call to validate()[/dim]",
            border_style="cyan",
        )
    )

    guard = Guard(
        policy="rag_strict",
        armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
    )

    cases = [
        {
            "label": "✓ Safe — search action aligned with task",
            "action_plan": "search_flights({'origin': 'JFK', 'destination': 'CDG', 'date': '2024-06-01'})",
            "user_task": "search for flights from New York to Paris",
            "expect_blocked": False,
            "border": "green",
        },
        {
            "label": "✗ Dangerous — SQL DROP statement blocked",
            "action_plan": "DROP TABLE bookings;",
            "user_task": "get my upcoming bookings",
            "expect_blocked": True,
            "border": "red",
        },
        {
            "label": "✗ Dangerous — filesystem destruction blocked",
            "action_plan": "rm -rf /var/data/users",
            "user_task": "list available flights",
            "expect_blocked": True,
            "border": "red",
        },
    ]

    prompt = "Who founded OpenAI?"
    output = "OpenAI was founded by Sam Altman and others in December 2015."

    for case in cases:
        console.print(f"\n[bold]Test:[/bold] {case['label']}")
        console.print(f"  Task:   {case['user_task']}")
        console.print(f"  Action: {case['action_plan']}")

        try:
            decision = guard.validate(
                prompt=prompt,
                output=output,
                context=OPENAI_CONTEXT,
                action_plan=case["action_plan"],
                user_task=case["user_task"],
            )
            enf: Optional[ActionEnforcementResult] = decision.action_enforcement
            status = "✓ allowed" if (enf and enf.allowed) else "⚠ no enforcement"
            console.print(
                Panel(
                    f"[bold green]{status}[/bold green]\n"
                    f"Text decision: {decision.decision}  "
                    f"Risk: {decision.risk_score:.2f}  "
                    f"ArmorIQ: {'allowed' if enf and enf.allowed else 'N/A'}",
                    border_style=case["border"],
                )
            )
        except IntentViolationError as e:
            console.print(
                Panel(
                    f"[bold red]✗ IntentViolationError raised[/bold red]\n"
                    f"Task: {e.user_task}\n"
                    f"Action: {e.action_plan}\n"
                    f"Reason: {e.reason}",
                    border_style="red",
                )
            )


# ---------------------------------------------------------------------------
# Pattern C: RuleBasedArmorIQClient standalone enforcement cases
# ---------------------------------------------------------------------------

def demo_rule_based_client() -> None:
    """Offline enforcement demo using RuleBasedArmorIQClient directly."""
    console.print(
        Panel(
            "[bold cyan]Pattern C: RuleBasedArmorIQClient (offline enforcement)[/bold cyan]\n"
            "[dim]No server, no LLM judge — pure Python rule engine[/dim]",
            border_style="cyan",
        )
    )

    client = RuleBasedArmorIQClient()
    adapter = ArmorIQAdapter(client=client)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Task", style="dim", width=30)
    table.add_column("Action", width=45)
    table.add_column("Result", justify="center")

    cases = [
        ("search for flights", "search_flights({'to': 'Paris'})", True),
        ("get flight details", "get_flight_details({'id': 'AF123'})", True),
        ("cancel booking", "DELETE FROM bookings WHERE id=42", False),
        ("find cheap tickets", "DROP TABLE prices;", False),
        ("view my account", "SELECT * FROM users; DROP TABLE users;--", False),
        ("check weather", "rm -rf /tmp/cache", False),
    ]

    for task, action, expect_allowed in cases:
        try:
            adapter.enforce(task, action)
            result = "[bold green]✓ ALLOWED[/bold green]"
        except IntentViolationError:
            result = "[bold red]✗ BLOCKED[/bold red]"

        table.add_row(task, action[:44] + ("…" if len(action) > 44 else ""), result)

    console.print(table)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    console.print(
        Panel(
            "[bold cyan]Two-Layer Safety Stack — Summary[/bold cyan]\n\n"
            "[bold]Layer 1 — HallucinationGuard (text validation):[/bold]\n"
            "  • 3-tier cascade: heuristics → embeddings → HHEM classifier\n"
            "  • Decisions: allow / block / regenerate / abstain\n"
            "  • Target: p95 < 100ms, CPU-only, no server required\n\n"
            "[bold]Layer 2 — ArmorIQ (action enforcement):[/bold]\n"
            "  • RuleBasedArmorIQClient: offline, zero infrastructure\n"
            "  • Detects SQL injection, filesystem destruction, and more\n"
            "  • Enforced automatically: GuardedGemini, Guard.validate, LangChain callbacks\n\n"
            "[bold]Integration patterns:[/bold]\n"
            "  A. GuardedGemini(armoriq=..., user_task=...)  ← fully automatic\n"
            "  B. guard.validate(..., action_plan=..., user_task=...)  ← per-call\n"
            "  C. HallucinationGuardCallback(armoriq=..., user_task=...)  ← LangChain\n\n"
            "[bold green]✓ Both layers are offline-first and crash-safe[/bold green]",
            border_style="cyan",
        )
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    console.print(
        Panel(
            "[bold cyan]HallucinationGuard + ArmorIQ — Deep Integration Demo[/bold cyan]\n"
            "[dim]Production AI safety: text validation + action enforcement[/dim]",
            border_style="cyan",
        )
    )

    # Check API key (required for Pattern A only)
    api_key = os.getenv("GOOGLE_API_KEY")
    base_model = None

    if api_key:
        try:
            genai.configure(api_key=api_key)
            base_model = genai.GenerativeModel("gemini-2.0-flash")
            console.print("[bold green]✓[/bold green] Gemini API configured")
        except Exception as e:
            console.print(f"[yellow]⚠ Gemini unavailable ({e}), skipping Pattern A[/yellow]")
    else:
        console.print(
            "[yellow]⚠ GOOGLE_API_KEY not set — skipping Pattern A (GuardedGemini demo)[/yellow]\n"
            "  Set it with: [bold]export GOOGLE_API_KEY=your-key[/bold]"
        )

    # Pattern A: GuardedGemini (requires Gemini API)
    if base_model is not None:
        console.print("\n" + "═" * 80)
        demo_guarded_gemini(base_model)

    # Pattern B: Guard.validate with action_plan (no API needed)
    console.print("\n" + "═" * 80)
    demo_guard_validate_with_enforcement()

    # Pattern C: RuleBasedArmorIQClient standalone (no API needed)
    console.print("\n" + "═" * 80)
    demo_rule_based_client()

    # Summary
    console.print("\n" + "═" * 80)
    print_summary()


if __name__ == "__main__":
    main()
