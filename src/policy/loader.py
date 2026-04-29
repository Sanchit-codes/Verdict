"""
Policy loader with caching.

Loads and validates policy YAML files from disk, with in-memory caching
to avoid repeated reads.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Union

import yaml
from pydantic import ValidationError

from .schema import PolicyConfig


class PolicyLoadError(Exception):
    """Raised when a policy file cannot be loaded or validated."""
    pass


def _find_policy_file(name_or_path: str) -> Path:
    """
    Resolve a policy name or path to an actual file path.
    
    Args:
        name_or_path: Either a policy name (e.g., "default") or a file path
        
    Returns:
        Path to the policy YAML file
        
    Raises:
        PolicyLoadError: If the file cannot be found
    """
    # If it looks like a path (contains / or \\ or ends with .yaml/.yml), treat as path
    if "/" in name_or_path or "\\" in name_or_path or name_or_path.endswith((".yaml", ".yml")):
        path = Path(name_or_path)
        if not path.is_file():
            raise PolicyLoadError(f"Policy file not found: {path}")
        return path
    
    # Otherwise treat as a policy name and look in policies/ directory
    # Search relative to package root
    package_root = Path(__file__).parent.parent.parent
    policies_dir = package_root / "policies"
    
    for ext in [".yaml", ".yml"]:
        policy_path = policies_dir / f"{name_or_path}{ext}"
        if policy_path.is_file():
            return policy_path
    
    raise PolicyLoadError(
        f"Policy '{name_or_path}' not found. "
        f"Searched in: {policies_dir}"
    )


@lru_cache(maxsize=32)
def load_policy(name_or_path: str) -> PolicyConfig:
    """
    Load and validate a policy from YAML.
    
    Supports both policy names (e.g., "default") and file paths.
    Results are cached in memory to avoid repeated disk reads.
    
    Args:
        name_or_path: Policy name (without .yaml extension) or path to YAML file
        
    Returns:
        Validated PolicyConfig object
        
    Raises:
        PolicyLoadError: If the file cannot be found, parsed, or validated
        
    Examples:
        >>> policy = load_policy("default")
        >>> policy.name
        'default'
        
        >>> policy = load_policy("./custom_policy.yaml")
        >>> policy.latency_budget_ms
        150
    """
    try:
        policy_file = _find_policy_file(name_or_path)
    except PolicyLoadError:
        raise
    
    try:
        with open(policy_file, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PolicyLoadError(f"Invalid YAML in {policy_file}: {e}")
    except Exception as e:
        raise PolicyLoadError(f"Failed to read {policy_file}: {e}")
    
    if not isinstance(raw_data, dict):
        raise PolicyLoadError(f"Policy file must contain a YAML object, got {type(raw_data)}")
    
    try:
        policy = PolicyConfig(**raw_data)
    except ValidationError as e:
        raise PolicyLoadError(f"Policy validation failed for {policy_file}: {e}")
    
    return policy
