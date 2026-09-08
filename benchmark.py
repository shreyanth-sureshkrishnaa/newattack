"""
benchmark.py — Evaluation suite for SIGWATCH.

Sweeps noise_level × attack_type × intensity, producing a results table
that the dashboard reads for the detection-rate-vs-intensity curve.

Key design points:
  1. Threshold calibration uses a SEPARATE clean-traffic run from the
     held-out FPR validation run — never the same data (circular).
  2. Detection rates are reported per intensity level, not as a single
     binary number.
  3. FPR is validated on a genuinely held-out clean run after calibration.
"""

from __future__ import annotations

import json
import time
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path

from qds import run_batch
from attacks import make_ir_attack, make_eh_attack, make_pf_attack, make_cbm_attack, ATTACK_MAKERS
from detectors import DetectorConfig, run_all_detectors, summarize


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NOISE_LEVELS     = [0.0, 0.02, 0.05]
ATTACK_TYPES     = ["IR", "EH", "PF", "CBM"]
INTENSITIES      = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]
N_TRIALS_SWEEP   = 400    # trials per (noise, attack, intensity) combination
N_TRIALS_CALIB   = 1000   # clean-run for threshold calibration
N_TRIALS_HELDOUT = 1000   # separate clean-run for FPR validation
SEED_CALIB       = 1001
SEED_HELDOUT     = 2002
SEED_SWEEP       = 3003

RESULTS_FILE = Path(__file__).parent / "benchmark_results.json"


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

def calibrate_qber_null(noise_p: float, n: int, seed: int) -> float:
    """
    Estimate QBER_null for a given noise level from a fresh clean run.

    This run is SEPARATE from the held-out FPR validation run.
    """
    rng = np.random.default_rng(seed)
    logs = run_batch(n, noise_p=noise_p, rng=rng, attack_type="clean")
    return sum(l.is_error for l in logs) / n


def make_config(noise_p: float, calib_n: int = N_TRIALS_CALIB) -> DetectorConfig:
    """Build a DetectorConfig calibrated for the given noise level."""
    config = DetectorConfig()
    config.qber_null = calibrate_qber_null(noise_p, calib_n, SEED_CALIB)
    return config


# ---------------------------------------------------------------------------
# FPR validation (held-out run)
# ---------------------------------------------------------------------------

def validate_fpr(config: DetectorConfig, noise_p: float) -> Dict[str, float]:
    """
    Run a held-out clean traffic run and measure empirical FPR per detector.

    This run uses SEED_HELDOUT, completely separate from calibration (SEED_CALIB).
    The FPR reported here is the empirical estimate — it should be ≈ alpha for
    each detector if the threshold derivation is correct.
    """
    rng = np.random.default_rng(SEED_HELDOUT)
    logs = run_batch(N_TRIALS_HELDOUT, noise_p=noise_p, rng=rng, attack_type="clean")
    alerts = run_all_detectors(logs, config)
    fired = {a.detector for a in alerts}
    # FPR per detector: 1 if it fired, 0 if not (single-batch estimate)
    detectors = ["QBER", "CHSH", "PauliConsistency", "CorrBitUniformity"]
    return {d: (1 if d in fired else 0) for d in detectors}


# ---------------------------------------------------------------------------
# Sweep
# ---------------------------------------------------------------------------

def run_sweep(
    noise_levels: List[float]  = NOISE_LEVELS,
    attack_types: List[str]    = ATTACK_TYPES,
    intensities:  List[float]  = INTENSITIES,
    n_trials:     int          = N_TRIALS_SWEEP,
    progress_cb   = None,
) -> Dict[str, Any]:
    """
    Full benchmark sweep.

    Returns a dict structured as:
        {
          "meta": {...},
          "fpr_validation": {...},
          "results": [
            {
              "noise": 0.02, "attack": "IR", "intensity": 0.5,
              "qber": 0.17, "chsh_S": 1.4,
              "n_alerts": 2, "detection_rate": 1.0,
              "alerts_fired": ["QBER", "CHSH"], ...
            }, ...
          ]
        }
    """
    results = []
    rng_sweep = np.random.default_rng(SEED_SWEEP)
    total = len(noise_levels) * len(attack_types) * len(intensities)
    done = 0

    # Calibrate once per noise level
    configs: Dict[float, DetectorConfig] = {}
    fpr_vals: Dict[float, Dict] = {}
    for noise_p in noise_levels:
        cfg = make_config(noise_p)
        configs[noise_p] = cfg
        fpr_vals[noise_p] = validate_fpr(cfg, noise_p)

    attack_maker_map = {
        "IR":  make_ir_attack,
        "EH":  make_eh_attack,
        "PF":  make_pf_attack,
        "CBM": make_cbm_attack,
    }

    for noise_p in noise_levels:
        config = configs[noise_p]
        for attack_type in attack_types:
            for intensity in intensities:
                attack_fn = attack_maker_map[attack_type](intensity)
                logs = run_batch(
                    n_trials, noise_p=noise_p, rng=rng_sweep,
                    attack_fn=attack_fn, attack_type=attack_type,
                    intensity=intensity,
                )
                summ = summarize(logs, config)
                fired = [a["detector"] for a in summ["alerts"]]
                # Detection rate: did ANY detector fire?
                # (For a single batch this is binary; sweep gives the curve)
                detection_rate = 1.0 if len(fired) > 0 else 0.0
                row = {
                    "noise": noise_p,
                    "attack": attack_type,
                    "intensity": intensity,
                    "qber": summ["qber"],
                    "chsh_S": summ["chsh_S"],
                    "n_alerts": summ["n_alerts"],
                    "detection_rate": detection_rate,
                    "alerts_fired": fired,
                    "n_trials": n_trials,
                }
                results.append(row)
                done += 1
                if progress_cb:
                    progress_cb(done, total, row)

    output = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_trials_per_cell": n_trials,
            "n_calib": N_TRIALS_CALIB,
            "n_heldout": N_TRIALS_HELDOUT,
            "seed_calib":   SEED_CALIB,
            "seed_heldout": SEED_HELDOUT,
            "seed_sweep":   SEED_SWEEP,
            "note": (
                "Calibration and held-out FPR validation use separate seeds "
                "and are never mixed — see benchmark.py docstring."
            ),
        },
        "fpr_validation": {
            str(noise_p): fpr_vals[noise_p] for noise_p in noise_levels
        },
        "results": results,
    }
    return output


def save_results(data: Dict[str, Any], path: Path = RESULTS_FILE) -> None:
    path.write_text(json.dumps(data, indent=2))
    print(f"Saved benchmark results to {path}")


def load_results(path: Path = RESULTS_FILE) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Self-test / main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== benchmark.py — running full sweep ===")
    print(f"  Noise levels:  {NOISE_LEVELS}")
    print(f"  Attack types:  {ATTACK_TYPES}")
    print(f"  Intensities:   {INTENSITIES}")
    print(f"  Trials/cell:   {N_TRIALS_SWEEP}")
    print(f"  Total cells:   {len(NOISE_LEVELS)*len(ATTACK_TYPES)*len(INTENSITIES)}")

    def progress(done, total, row):
        print(f"  [{done:3d}/{total}] noise={row['noise']}, "
              f"attack={row['attack']}, intensity={row['intensity']:.1f} "
              f"→ QBER={row['qber']:.4f}, S={row['chsh_S']:.4f}, "
              f"detected={row['detection_rate']:.0f}")

    t0 = time.time()
    data = run_sweep(progress_cb=progress)
    elapsed = time.time() - t0
    save_results(data)

    # Verify detection rates at high intensity
    results = data["results"]
    for attack in ATTACK_TYPES:
        hi = [r for r in results if r["attack"] == attack and r["intensity"] == 1.0 and r["noise"] == 0.02]
        if hi:
            print(f"  {attack} at intensity=1.0, noise=0.02: "
                  f"detection_rate={hi[0]['detection_rate']:.0f}, "
                  f"detectors={hi[0]['alerts_fired']}")

    print(f"\nFPR validation (held-out, noise=0.02):")
    fpr = data["fpr_validation"].get("0.02", {})
    for det, val in fpr.items():
        print(f"  {det}: {'FIRED' if val else 'ok'}")

    print(f"\nCompleted in {elapsed:.1f}s")
    print("=== benchmark.py done ===")
