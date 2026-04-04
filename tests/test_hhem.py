import os

import pytest

from hallucination_guard.validators.hhem import HHEMValidator, _get_hhem_model, preload_hhem
from hallucination_guard.validators.base import ValidationInput


@pytest.mark.skipif(os.getenv("HG_DISABLE_HHEM", "false").lower() == "true", reason="HHEM disabled via env")
def test_hhem_singleton_shared_between_validators(monkeypatch):
    # Ensure fresh state
    from hallucination_guard.validators import hhem as hhem_module

    hhem_module._HHEM_MODEL = None

    v1 = HHEMValidator({"threshold": 0.5, "timeout_ms": 80})
    v2 = HHEMValidator({"threshold": 0.5, "timeout_ms": 80})

    model1, err1 = _get_hhem_model()
    model2, err2 = _get_hhem_model()

    assert err1 is None
    assert err2 is None
    assert model1 is model2


@pytest.mark.skipif(os.getenv("HG_DISABLE_HHEM", "false").lower() == "true", reason="HHEM disabled via env")
def test_hhem_preload_then_validate(monkeypatch):
    # Preload once
    loaded = preload_hhem()
    assert loaded is True

    validator = HHEMValidator({"threshold": 0.0, "timeout_ms": 200})
    input_data = ValidationInput(
        prompt="What is the capital of France?",
        output="The capital of France is Paris.",
        context="France is a country in Europe. Its capital is Paris.",
        domain="geography",
    )

    result = validator.validate(input_data)
    assert 0.0 <= result.score <= 1.0
    assert result.validator_name == "hhem"


def test_hhem_disabled_env_fast_neutral(monkeypatch):
    monkeypatch.setenv("HG_DISABLE_HHEM", "true")
    validator = HHEMValidator({"threshold": 0.5, "timeout_ms": 80})
    input_data = ValidationInput(
        prompt="What is the capital of France?",
        output="The capital of France is Paris.",
        context="France is a country in Europe. Its capital is Paris.",
        domain="geography",
    )

    result = validator.validate(input_data)
    assert result.score == 0.5
    assert not result.passed
    assert result.error == "HHEM disabled"


def test_hhem_no_context_returns_neutral(monkeypatch):
    monkeypatch.delenv("HG_DISABLE_HHEM", raising=False)
    validator = HHEMValidator({"threshold": 0.5, "timeout_ms": 80})
    input_data = ValidationInput(
        prompt="What is the capital of France?",
        output="The capital of France is Paris.",
        context=None,
        domain="geography",
    )

    result = validator.validate(input_data)
    assert result.score == 0.5
    assert not result.passed
    assert result.error == "No context"
