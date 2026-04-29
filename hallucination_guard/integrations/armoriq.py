"""Compatibility wrapper for the ArmorIQ adapter module.

The implementation now lives at ``hallucination_guard.armoriq``. This shim
keeps older imports working while the package layout evolves.
"""

from hallucination_guard.armoriq import ArmorIQAdapter, ArmorIQClientProtocol, RuleBasedArmorIQClient

__all__ = [
    "ArmorIQAdapter",
    "ArmorIQClientProtocol",
    "RuleBasedArmorIQClient",
]