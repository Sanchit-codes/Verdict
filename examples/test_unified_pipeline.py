import os
import sys
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add SDK to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hallucination_guard import Guard
from hallucination_guard.core.exceptions import HallucinationBlockedError, IntentViolationError

console = Console()

def run_test_case(name, prompt, context=None, domain="demo", preprocessing=True, armoriq=None):
    console.print(f"\n[bold blue]>>> Test Case: {name}[/bold blue]")
    console.print(f"[dim]Prompt: {prompt}[/dim]")
    if context:
        console.print(f"[dim]Context tokens: {len(context)//4} (est)[/dim]")
    
    guard = Guard(policy="rag_strict", preprocessing=preprocessing, armoriq=armoriq)
    
    try:
        console.print("[yellow]Running Generate & Validate pipeline...[/yellow]")
        decision = guard.generate_and_validate(
            prompt=prompt,
            context=context,
            domain=domain,
            session_key="demo_session"
        )
        
        # Display results panel
        decision_color = "green" if decision.decision == "allow" else "red"
        panel_content = [
            f"Decision: [bold {decision_color}]{decision.decision.upper()}[/bold {decision_color}]",
            f"Risk Score: {decision.risk_score:.2f}",
            f"Confidence: {decision.confidence:.2f}",
            f"Latency: {decision.latency_ms:.1f}ms",
            "\n[bold]Output:[/bold]",
            decision.output
        ]
        console.print(Panel("\n".join(panel_content), title="SDK Decision"))
        
        # Display Preprocessing Metadata
        if decision.preprocessing_metadata:
            table = Table(title="Preprocessing & Context Stats")
            table.add_column("Stage")
            table.add_column("Result")
            
            p_meta = decision.preprocessing_metadata.get("prompt_analysis", {})
            table.add_row("Prompt Refined", "Yes" if p_meta.get("was_refined") else "No")
            table.add_row("Intent", p_meta.get("intent", "Unknown"))
            
            c_meta = decision.preprocessing_metadata.get("context_compaction", {})
            if c_meta:
                ratio = (c_meta['compacted_tokens']/c_meta['original_tokens']*100) if c_meta['original_tokens']>0 else 100
                table.add_row("Context Compaction", f"{c_meta['original_tokens']} -> {c_meta['compacted_tokens']} tokens ({ratio:.0f}%)")
            
            console.print(table)
            
    except HallucinationBlockedError as e:
        console.print(f"[bold red]❌ BLOCKED:[/bold red] {e.evidence}")
    except IntentViolationError as e:
        console.print(f"[bold red]❌ INTENT VIOLATION:[/bold red] {e.reason}")
    except Exception as e:
        console.print(f"[bold red]❌ ERROR:[/bold red] {e}")

if __name__ == "__main__":
    if not os.getenv("GOOGLE_API_KEY"):
        console.print("[bold red]ERROR: GOOGLE_API_KEY environment variable not set.[/bold red]")
        console.print("Please set it with: export GOOGLE_API_KEY=your_key")
        # For demo purposes, we will mock if no key, but ideally user provides it.
        sys.exit(1)

    # 1. Standard RAG case
    run_test_case(
        "Standard RAG (Faithful)",
        "What is the capital of France?",
        context="France is a country in Europe. Its capital is Paris. It is known for the Eiffel Tower."
    )
    
    # 2. Deflection case (ArmorIQ should catch this)
    # We use a rule-based ArmorIQClient mock for a quick test
    from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
    armor = ArmorIQAdapter(client=RuleBasedArmorIQClient())
    
    run_test_case(
        "Model Deflection (ArmorIQ Test)",
        "Search for flights to Paris",
        context="User is asking for flight information.",
        armoriq=armor
    )
