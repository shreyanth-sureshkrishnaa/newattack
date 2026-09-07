#!/usr/bin/env python3
"""
runner.py — Master CLI runner for Q-ATT&CK.

Usage:
    python runner.py serve [--port 5050]
    python runner.py benchmark
    python runner.py test
"""

import sys
import subprocess
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent

def run_tests():
    print("=== Running Q-ATT&CK Self-Test Suite ===")
    modules = [
        "qsim.py",
        "noise.py",
        "bell.py",
        "qotp.py",
        "qds.py",
        "attacks.py",
        "detectors.py"
    ]
    for mod in modules:
        print(f"\n--- Testing {mod} ---")
        res = subprocess.run([sys.executable, str(BASE_DIR / mod)], check=False)
        if res.returncode != 0:
            print(f"FAILED: {mod}")
            sys.exit(res.returncode)
    print("\n==========================================")
    print(" ALL TESTS PASSED SUCCESSFULLY (7/7) ")
    print("==========================================")

def run_benchmark():
    print("=== Running Full Benchmark Sweep ===")
    res = subprocess.run([sys.executable, str(BASE_DIR / "benchmark.py")], check=False)
    if res.returncode != 0:
        print("Benchmark failed!")
        sys.exit(res.returncode)

def serve_dashboard(port=5050):
    print(f"=== Starting Q-ATT&CK Live Server on http://localhost:{port} ===")
    from api import app
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

def main():
    parser = argparse.ArgumentParser(description="Q-ATT&CK Master CLI Runner")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start Flask REST API & Web Dashboard")
    serve_parser.add_argument("--port", type=int, default=5050, help="Port to listen on (default: 5050)")

    # benchmark command
    subparsers.add_parser("benchmark", help="Run full parameter sweep benchmark")

    # test command
    subparsers.add_parser("test", help="Run all unit and verification self-tests")

    args = parser.parse_args()

    if args.command == "serve":
        serve_dashboard(args.port)
    elif args.command == "benchmark":
        run_benchmark()
    elif args.command == "test":
        run_tests()
    else:
        # Default behavior: serve dashboard
        serve_dashboard(5050)

if __name__ == "__main__":
    main()
