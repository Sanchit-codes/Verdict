#!/usr/bin/env python3
"""
Quick launcher for the HallucinationGuard testing frontend.
"""
import os
import sys
import subprocess

def main():
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # python-dotenv not installed, continue without .env loading
    # Check if Flask is installed
    try:
        import flask
    except ImportError:
        print("❌ Flask not installed. Install with: pip install flask")
        print("   Or install dev dependencies: pip install -e \".[dev]\"")
        sys.exit(1)
    
    # Check if SDK is available
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from hallucination_guard import Guard
        print("✅ HallucinationGuard SDK available")
    except ImportError as e:
        print(f"❌ HallucinationGuard SDK not available: {e}")
        print("   Install with: pip install -e .")
        sys.exit(1)
    
    # Run the app
    print("🚀 Starting HallucinationGuard Testing Frontend...")
    print("   URL: http://localhost:5000")
    print("   Press Ctrl+C to stop")
    print("-" * 50)
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run([sys.executable, "app.py"])

if __name__ == "__main__":
    main()
