"""
detectors.py — Statistical detectors for Q-ATT&CK.

All detectors are PURE FUNCTIONS:
    detect_*(logs, config) -> List[Alert]

They take a list of TrialLogs and a DetectorConfig, and return zero or
more Alert objects.  No state, no ML, no trained models.

The API layer can pass in live-adjusted thresholds without redeploying code.

Detectors implemented:
  1. QBER detector       — bit error rate vs. derived z-score threshold
  2. CHSH detector       — genuine Bell inequality test (S < θ_CHSH)
  3. Pauli consistency   — asymmetric Pauli error distribution (χ² test)
  4. Correction-bit uniformity — (m0, m1) uniformity test (χ² test)

Threshold derivations (read before changing any default):
─────────────────────────────────────────────────────────
1. QBER threshold
   Under null (clean traffic, depolarizing noise p per qubit, n trials):
     QBER ~ Binomial(n, p_null) / n
     By CLT (n ≥ 30): QBER ~ N(p_null, p_null(1−p_null)/n)
     One-sided threshold for FPR α:
       θ_QBER = p_null + z_α · √(p_null(1−p_null)/n)
     where z_α = scipy.stats.norm.ppf(1−α).
   FPR = α  (exact by construction of the z-score threshold, CLT approx).

   Default α = 0.05, z_α ≈ 1.645.
   p_null is estimated from a held-out clean calibration run.

2. CHSH threshold
   Under null (clean Bell pairs, n_chsh CHSH samples):
     S_null ≈ 2√2 = 2.8284…
     Variance of the sample S:
       Each correlator E(a,b) is the mean of n_ab ≈ n/4 i.i.d. {±1} r.v.s.
       Var(E(a,b)) ≈ (1 − E(a,b)²) / n_ab ≈ 0.5 / (n/4) = 2/n
       Var(S) = Σ_pairs Var(E) = 4 · 2/n = 8/n   (independent basis choices)
       σ_S = 2√2 / √n
     Alert when S drops below:
       θ_CHSH = S_null − z_α · σ_S = 2√2 − z_α · 2√2/√n
   FPR = α (one-sided normal approximation; Berry-Esseen corrections
         are second-order for n ≥ 50 per basis pair).

3. Pauli consistency threshold
   Under null (depolarizing, n errors total):
     P(X-error) = P(Y-error) = P(Z-error) = 1/3  (among error trials)
     χ²(2) statistic for 3 bins with equal expected frequency n/3.
     Alert when χ² > χ²_{α}(df=2).
   FPR = α  (exact χ² CDF, valid for n_errors ≥ 5 per bin heuristic).

4. Correction-bit uniformity threshold
   Under null (legitimate protocol):
     P(m0,m1) = 0.25  for each of (0,0),(0,1),(1,0),(1,1).
     χ²(3) statistic for 4 bins with equal expected frequency n/4.
     Alert when χ² > χ²_{α}(df=3).
   FPR = α  (exact χ² CDF).

NOTE on Pauli consistency:
   The `pauli_error_type` field in TrialLog is simulation ground truth
   (the actual Pauli applied by the depolarizing channel or attack).
   In a real physical system, this would require process tomography or
   a protocol modification (e.g., randomly inserting test qubits measured
   in X and Y bases as well as Z).  This limitation is stated explicitly
   in the README.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from scipy.stats import norm as scipy_norm, chi2 as scipy_chi2

from qds import TrialLog
from bell import compute_chsh_S, S_THEORY


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    """One detector alert."""
    trial_batch_end: int     # last trial_id in the batch that triggered this
    detector:        str     # "QBER" | "CHSH" | "PauliConsistency" | "CorrBitUniformity"
    severity:        str     # "LOW" | "MEDIUM" | "HIGH"
    value:           float   # the statistic that crossed the threshold
    threshold:       float   # the threshold value at alert time
    message:         str


@dataclass
class DetectorConfig:
    """
    All tunable detection thresholds in one place.

    These are exposed via the REST API for live adjustment during the demo.
    Each threshold has a docstring explaining its derivation and the FPR
    it corresponds to at the default value.
    """

    # QBER thresholds
    qber_null:      float = 0.033
    """Baseline QBER under clean traffic (estimated from calibration run).
    For depolarizing p=0.05 on 3 qubits, empirical ≈ 0.033.
    Update this field after running benchmark calibration."""

    qber_alpha:     float = 0.05
    """FPR for QBER detector. Default 5%: z_0.05 = 1.645."""

    qber_min_trials: int = 30
    """Minimum trials before QBER detector fires (CLT requires n ≥ 30)."""

    # CHSH thresholds
    chsh_alpha:     float = 0.05
    """FPR for CHSH detector. Default 5%."""

    chsh_min_samples: int = 50
    """Minimum CHSH samples before detector fires (σ_S reliable for n ≥ 50)."""

    # Pauli consistency threshold
    pauli_alpha:    float = 0.05
    """FPR for Pauli-consistency chi-squared test. df=2."""

    pauli_min_errors: int = 15
    """Minimum error count before Pauli consistency fires (need ≥5 per bin)."""

    # Correction-bit uniformity threshold
    corr_alpha:     float = 0.05
    """FPR for correction-bit uniformity chi-squared test. df=3."""

    corr_min_trials: int = 40
    """Minimum trials before correction-bit detector fires (n/4 ≥ 10 heuristic)."""


# ---------------------------------------------------------------------------
# Detector 1: QBER
# ---------------------------------------------------------------------------

def detect_qber(
    logs: List[TrialLog],
    config: DetectorConfig,
) -> List[Alert]:
    """
    Detect anomalous bit error rate.

    Threshold:
        θ_QBER = p_null + z_α · √(p_null(1−p_null)/n)

    Derivation: see module docstring §1.
    FPR = config.qber_alpha (normal approximation, CLT).

    Returns an alert if QBER > θ_QBER and n ≥ config.qber_min_trials.
    """
    n = len(logs)
    if n < config.qber_min_trials:
        return []

    errors = sum(1 for l in logs if l.is_error)
    qber = errors / n

    p0 = config.qber_null
    z_alpha = float(scipy_norm.ppf(1.0 - config.qber_alpha))
    # Clip p0 to avoid sqrt of negative in edge cases
    p0_clipped = float(np.clip(p0, 1e-6, 1.0 - 1e-6))
    sigma = np.sqrt(p0_clipped * (1.0 - p0_clipped) / n)
    theta = p0 + z_alpha * sigma

    if qber > theta:
        excess = (qber - p0) / sigma
        sev = "HIGH" if excess > 4 else ("MEDIUM" if excess > 2.5 else "LOW")
        last_id = logs[-1].trial_id
        return [Alert(
            trial_batch_end=last_id,
            detector="QBER",
            severity=sev,
            value=round(qber, 5),
            threshold=round(theta, 5),
            message=(
                f"QBER={qber:.4f} exceeds threshold {theta:.4f} "
                f"({excess:.1f}σ above null p_null={p0:.4f}). "
                f"FPR={config.qber_alpha:.0%} at this threshold."
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# Detector 2: CHSH (genuine Bell test)
# ---------------------------------------------------------------------------

def detect_chsh(
    logs: List[TrialLog],
    config: DetectorConfig,
) -> List[Alert]:
    """
    Detect drop in CHSH S-value below the quantum bound.

    Threshold:
        σ_S  = 2√2 / √n_chsh    (derived in module docstring §2)
        θ_CHSH = 2√2 − z_α · σ_S

    The CHSH S-value for clean Bell pairs should be ≈ 2√2 ≈ 2.828.
    Any attack that destroys or degrades entanglement (IR, EH) will
    drop S below θ_CHSH.

    FPR = config.chsh_alpha (one-sided normal approx, valid n ≥ 50/basis-pair).

    Returns an alert if S < θ_CHSH and n_chsh ≥ config.chsh_min_samples.
    """
    chsh_samples = [
        (l.chsh_alice_angle, l.chsh_bob_angle, l.chsh_alice_sign, l.chsh_bob_sign)
        for l in logs
    ]
    n_chsh = len(chsh_samples)
    if n_chsh < config.chsh_min_samples:
        return []

    S, info = compute_chsh_S(chsh_samples)

    # Variance derivation:
    #   σ_S² = 4 × Var(E(a,b)) = 4 × 2/n = 8/n  → σ_S = 2√2/√n
    sigma_S = 2.0 * np.sqrt(2.0) / np.sqrt(n_chsh)
    z_alpha = float(scipy_norm.ppf(1.0 - config.chsh_alpha))
    theta_chsh = S_THEORY - z_alpha * sigma_S

    if S < theta_chsh:
        drop_sigma = (S_THEORY - S) / sigma_S
        sev = "HIGH" if drop_sigma > 6 else ("MEDIUM" if drop_sigma > 3 else "LOW")
        last_id = logs[-1].trial_id
        return [Alert(
            trial_batch_end=last_id,
            detector="CHSH",
            severity=sev,
            value=round(S, 5),
            threshold=round(theta_chsh, 5),
            message=(
                f"CHSH S={S:.4f} below threshold {theta_chsh:.4f} "
                f"({drop_sigma:.1f}σ below 2√2={S_THEORY:.4f}). "
                f"FPR={config.chsh_alpha:.0%}. Possible entanglement attack."
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# Detector 3: Pauli consistency
# ---------------------------------------------------------------------------

def detect_pauli_consistency(
    logs: List[TrialLog],
    config: DetectorConfig,
) -> List[Alert]:
    """
    Detect asymmetric Pauli error distribution (signatures of Pauli Forgery).

    Under depolarizing noise, Pauli errors are symmetric:
        P(X-error) = P(Y-error) = P(Z-error) = 1/3

    Under Pauli Forgery (Eve applies X), X-errors dominate.

    Test: χ²(2) on the conditional distribution (X, Y, Z) given an error.
    Alert when χ² > χ²_{α}(df=2).
    FPR = config.pauli_alpha (exact χ² CDF).

    NOTE: Uses simulation-level ground truth (pauli_error_type field).
    In a real protocol, this requires process tomography — see README.
    """
    error_logs = [l for l in logs if l.is_error]
    n_err = len(error_logs)
    if n_err < config.pauli_min_errors:
        return []

    counts = {"X": 0, "Y": 0, "Z": 0}
    for l in error_logs:
        pt = l.pauli_error_type
        if pt in counts:
            counts[pt] += 1

    total_counted = sum(counts.values())
    if total_counted == 0:
        return []

    observed = np.array([counts["X"], counts["Y"], counts["Z"]], dtype=float)
    expected_each = total_counted / 3.0
    expected = np.array([expected_each, expected_each, expected_each])

    chi2_stat = float(np.sum((observed - expected) ** 2 / expected))
    threshold = float(scipy_chi2.ppf(1.0 - config.pauli_alpha, df=2))

    if chi2_stat > threshold:
        sev = "HIGH" if chi2_stat > 3 * threshold else "MEDIUM"
        last_id = logs[-1].trial_id
        dom = max(counts, key=counts.get)
        return [Alert(
            trial_batch_end=last_id,
            detector="PauliConsistency",
            severity=sev,
            value=round(chi2_stat, 4),
            threshold=round(threshold, 4),
            message=(
                f"Pauli error distribution asymmetric: "
                f"X={counts['X']}, Y={counts['Y']}, Z={counts['Z']} "
                f"(χ²={chi2_stat:.2f} > {threshold:.2f}, df=2). "
                f"Dominant error: {dom}. Possible Pauli Forgery. "
                f"FPR={config.pauli_alpha:.0%}."
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# Detector 4: Correction-bit uniformity
# ---------------------------------------------------------------------------

def detect_corr_uniformity(
    logs: List[TrialLog],
    config: DetectorConfig,
) -> List[Alert]:
    """
    Detect non-uniform correction-bit distribution.

    Under the legitimate protocol, (m0, m1) ∈ {(0,0),(0,1),(1,0),(1,1)}
    each with probability 0.25.  CBM forces (m0,m1) toward (1,1),
    creating a non-uniform distribution.

    Test: χ²(3) on the 4-cell count vector.
    Alert when χ² > χ²_{α}(df=3).
    FPR = config.corr_alpha (exact χ² CDF).

    Expected frequency 0.25·n must be ≥ 5 (standard χ² rule of thumb):
    requires n ≥ 20.  We enforce n ≥ config.corr_min_trials.
    """
    n = len(logs)
    if n < config.corr_min_trials:
        return []

    counts = {(0,0): 0, (0,1): 0, (1,0): 0, (1,1): 0}
    for l in logs:
        key = (l.correction_m0, l.correction_m1)
        counts[key] = counts.get(key, 0) + 1

    observed = np.array([counts[k] for k in [(0,0),(0,1),(1,0),(1,1)]], dtype=float)
    expected = np.full(4, n / 4.0)
    chi2_stat = float(np.sum((observed - expected) ** 2 / expected))
    threshold = float(scipy_chi2.ppf(1.0 - config.corr_alpha, df=3))

    if chi2_stat > threshold:
        sev = "HIGH" if chi2_stat > 3 * threshold else "MEDIUM"
        last_id = logs[-1].trial_id
        return [Alert(
            trial_batch_end=last_id,
            detector="CorrBitUniformity",
            severity=sev,
            value=round(chi2_stat, 4),
            threshold=round(threshold, 4),
            message=(
                f"Correction-bit distribution non-uniform: "
                f"(0,0)={counts[(0,0)]}, (0,1)={counts[(0,1)]}, "
                f"(1,0)={counts[(1,0)]}, (1,1)={counts[(1,1)]} "
                f"(χ²={chi2_stat:.2f} > {threshold:.2f}, df=3). "
                f"Possible Correction-Bit Manipulation. "
                f"FPR={config.corr_alpha:.0%}."
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def run_all_detectors(
    logs: List[TrialLog],
    config: DetectorConfig,
) -> List[Alert]:
    """Run all four detectors and return combined alert list."""
    alerts = []
    alerts += detect_qber(logs, config)
    alerts += detect_chsh(logs, config)
    alerts += detect_pauli_consistency(logs, config)
    alerts += detect_corr_uniformity(logs, config)
    return alerts


def summarize(logs: List[TrialLog], config: DetectorConfig) -> Dict[str, Any]:
    """Compute summary statistics for a batch of logs."""
    if not logs:
        return {}
    n = len(logs)
    qber = sum(l.is_error for l in logs) / n
    chsh_samples = [(l.chsh_alice_angle, l.chsh_bob_angle,
                     l.chsh_alice_sign,  l.chsh_bob_sign) for l in logs]
    S, chsh_info = compute_chsh_S(chsh_samples)
    alerts = run_all_detectors(logs, config)
    return {
        "n_trials": n,
        "qber": round(qber, 5),
        "chsh_S": round(S, 5),
        "chsh_info": chsh_info,
        "n_alerts": len(alerts),
        "alerts": [vars(a) for a in alerts],
        "attack_type": logs[0].attack_type,
        "intensity": logs[0].intensity,
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== detectors.py self-test ===")
    import sys
    from qds import run_batch
    from attacks import make_ir_attack, make_pf_attack, make_cbm_attack

    rng = np.random.default_rng(77)
    config = DetectorConfig()
    N = 600

    # --- Test 1: Clean traffic → no alerts (FPR validation) ---
    # We run a large held-out clean run; no detector should fire.
    logs_clean = run_batch(N, noise_p=0.02, rng=rng, attack_type="clean")

    # Calibrate qber_null from the clean run
    config.qber_null = sum(l.is_error for l in logs_clean) / N
    print(f"     Calibrated qber_null = {config.qber_null:.5f}")

    # Now run a SEPARATE held-out validation run to check FPR
    logs_heldout = run_batch(N, noise_p=0.02, rng=rng, attack_type="clean")
    alerts_clean = run_all_detectors(logs_heldout, config)
    print(f"     Alerts on held-out clean run: {len(alerts_clean)}")
    for a in alerts_clean:
        print(f"       [{a.detector}] {a.message[:80]}")
    # FPR should be low; occasional false positive is expected but unusual
    assert len(alerts_clean) <= 1, \
        f"Too many false positives on clean traffic: {len(alerts_clean)}"
    print("PASS: ≤1 false positive on held-out clean run")

    # --- Test 2: IR attack → QBER + CHSH alerts ---
    ir_fn = make_ir_attack(1.0)
    logs_ir = run_batch(N, noise_p=0.02, rng=rng, attack_fn=ir_fn,
                        attack_type="IR", intensity=1.0)
    alerts_ir = run_all_detectors(logs_ir, config)
    names_ir = {a.detector for a in alerts_ir}
    print(f"  IR(1.0) alerts: {names_ir}")
    assert "QBER" in names_ir, "IR should trigger QBER detector"
    assert "CHSH" in names_ir, "IR should trigger CHSH detector"
    print("PASS: IR at intensity=1.0 triggers QBER + CHSH detectors")

    # --- Test 3: PF attack → QBER + PauliConsistency, CHSH silent ---
    pf_fn = make_pf_attack(1.0)
    logs_pf = run_batch(N, noise_p=0.02, rng=rng, attack_fn=pf_fn,
                        attack_type="PF", intensity=1.0)
    alerts_pf = run_all_detectors(logs_pf, config)
    names_pf = {a.detector for a in alerts_pf}
    print(f"  PF(1.0) alerts: {names_pf}")
    assert "QBER" in names_pf, "PF should trigger QBER detector"
    assert "PauliConsistency" in names_pf, "PF should trigger Pauli consistency detector"
    assert "CHSH" not in names_pf, f"PF should NOT trigger CHSH; got {names_pf}"
    print("PASS: PF at intensity=1.0 triggers QBER + PauliConsistency, NOT CHSH")

    # --- Test 4: CBM attack → CorrBitUniformity, CHSH silent ---
    cbm_fn = make_cbm_attack(1.0)
    logs_cbm = run_batch(N, noise_p=0.02, rng=rng, attack_fn=cbm_fn,
                         attack_type="CBM", intensity=1.0)
    alerts_cbm = run_all_detectors(logs_cbm, config)
    names_cbm = {a.detector for a in alerts_cbm}
    print(f"  CBM(1.0) alerts: {names_cbm}")
    assert "CorrBitUniformity" in names_cbm, "CBM should trigger correction-bit detector"
    assert "CHSH" not in names_cbm, f"CBM should NOT trigger CHSH; got {names_cbm}"
    print("PASS: CBM at intensity=1.0 triggers CorrBitUniformity, NOT CHSH")

    print("=== All detectors.py tests passed ===")
