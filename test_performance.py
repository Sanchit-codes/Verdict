#!/usr/bin/env python3
"""Performance testing script for HallucinationGuard optimizations."""

import os
import time
import statistics
from hallucination_guard import Guard

def benchmark_guard_creation():
    """Benchmark Guard creation with and without preloading."""
    print("=== Guard Creation Benchmark ===\n")
    
    # Test 1: No preloading (lazy loading)
    print("1. Creating Guard without preloading...")
    start = time.time()
    guard_lazy = Guard(policy="default")
    lazy_init_time = time.time() - start
    print(".2f")
    
    # Test 2: With preloading
    print("\n2. Creating Guard with preloading...")
    start = time.time()
    guard_preload = Guard(policy="default", preload_models=True)
    preload_init_time = time.time() - start
    print(".2f")
    
    print(".1f"    return guard_lazy, guard_preload

def benchmark_validation_latency(guard, name, num_runs=10):
    """Benchmark validation latency for a guard."""
    print(f"\n=== {name} Validation Benchmark ({num_runs} runs) ===")
    
    latencies = []
    
    for i in range(num_runs):
        start = time.perf_counter()
        
        decision = guard.validate(
            prompt="What is the capital of France?",
            output="The capital of France is Paris.",
            context="France is a country in Europe. Its capital city is Paris.",
            domain="test"
        )
        
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)
        
        print(f"  Run {i+1}: {latency_ms:.1f}ms (decision: {decision.decision}, risk: {decision.risk_score:.3f})")
    
    print("\nStats:")
    print(".1f"    print(".1f"    print(".1f"    print(".1f"    print(".1f"    return latencies

def test_hhem_and_embedding_validators():
    """Test individual validators work correctly."""
    print("\n=== Validator Functionality Tests ===\n")
    
    from hallucination_guard.validators.embedding import EmbeddingValidator, preload_embedding
    from hallucination_guard.validators.hhem import HHEMValidator, preload_hhem
    from hallucination_guard.validators.base import ValidationInput
    
    # Test embedding
    print("1. Testing EmbeddingValidator...")
    preload_embedding()
    embedding_validator = EmbeddingValidator({"threshold": 0.7, "timeout_ms": 50})
    
    result = embedding_validator.validate(ValidationInput(
        prompt="test",
        output="Paris is the capital.",
        context="The capital of France is Paris.",
        domain="test"
    ))
    print(".1f")
    
    # Test HHEM
    print("\n2. Testing HHEMValidator...")
    preload_hhem()
    hhem_validator = HHEMValidator({"threshold": 0.5, "timeout_ms": 80})
    
    result = hhem_validator.validate(ValidationInput(
        prompt="test",
        output="Paris is the capital.",
        context="The capital of France is Paris.",
        domain="test"
    ))
    print(".1f")

def test_environment_variables():
    """Test environment variable controls."""
    print("\n=== Environment Variable Tests ===\n")
    
    # Test HG_PRELOAD_MODELS
    print("1. Testing HG_PRELOAD_MODELS=true...")
    os.environ["HG_PRELOAD_MODELS"] = "true"
    start = time.time()
    guard = Guard(policy="default")
    init_time = time.time() - start
    print(".2f")
    
    # Test HG_DISABLE_HHEM
    print("\n2. Testing HG_DISABLE_HHEM=true...")
    os.environ["HG_DISABLE_HHEM"] = "true"
    guard_fast = Guard(policy="default", preload_models=False)
    
    start = time.time()
    decision = guard_fast.validate(
        prompt="test",
        output="This is a test output.",
        context="This is test context.",
        domain="test"
    )
    latency = (time.time() - start) * 1000
    print(".1f")
    
    # Clean up
    del os.environ["HG_PRELOAD_MODELS"]
    del os.environ["HG_DISABLE_HHEM"]

def main():
    """Run all performance tests."""
    print("🚀 HallucinationGuard Performance Test Suite")
    print("=" * 50)
    
    try:
        # Test individual validators
        test_hhem_and_embedding_validators()
        
        # Benchmark guard creation
        guard_lazy, guard_preload = benchmark_guard_creation()
        
        # Benchmark validation latency
        lazy_latencies = benchmark_validation_latency(guard_lazy, "Lazy Loading Guard")
        preload_latencies = benchmark_validation_latency(guard_preload, "Preloaded Guard")
        
        # Test environment variables
        test_environment_variables()
        
        print("\n" + "=" * 50)
        print("✅ All tests completed successfully!")
        print("\n📊 Key Results:")
        print(".1f"        print(".1f"        print(".1f"        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
