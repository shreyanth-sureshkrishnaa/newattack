"""
qds.py — QDS protocol, trial execution, and data structures for SIGWATCH.

Teleportation-based Quantum Digital Signature protocol:

  Sign (Alice):
    1. Generate QOTP key (a, b) uniformly at random.
    2. Prepare message qubit |m⟩ for message bit m ∈ {0, 1}.
    3. Apply QOTP: payload = X^a Z^b |m⟩.
    4. Distribute Bell pair |Φ+⟩_{Alice, Bob}.
    5. Teleport payload to Bob → classical correction bits (m0, m1).
    6. Send {m, a, b, m0, m1} to Bob.

  Verify (Bob):
    7. Receive correction bits (m0, m1); apply Z^m0 X^m1 to his qubit.
    8. Receive QOTP key (a, b); apply QOTP decrypt (X^a Z^b again).
    9. Measure in Z basis → received_bit.
    10. Verify: received_bit == m.

  CHSH check (runs in parallel, completely separate Bell pairs):
    - A fresh Bell pair is created per trial.
    - Alice and Bob each choose a random measurement basis.
    - Results are logged; the CHSH S-value is computed per batch.

Channel separation (see non-negotiable design principle #8):
  - Signature qubit:       operated on by QOTP and Pauli Forgery attacks.
  - Teleportation Bell pair: distributed to Bob for teleportation.
  - CHSH Bell pair:        fresh, separate; only CHSH detector reads it.
  - Correction bits (m0, m1): classical; target of CBM attack.
  - Verification decision: computed from the above.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

from qsim import QuantumState
from bell import create_bell_pair, teleport, apply_teleport_correction, chsh_measurement
from qotp import qotp_encrypt, qotp_decrypt, random_key
from noise import depolarizing_channel, clip_prob


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrialLog:
    """
    Complete record of one SIGWATCH trial.

    Fields are organized by the four physical channels they belong to
    (see non-negotiable design principle #8 and module docstring).
    """
    trial_id:   int
    attack_type: str    # "clean" | "IR" | "EH" | "PF" | "CBM"
    intensity:  float
    noise_level: float

    # --- Signature qubit channel ---
    message_bit:  int           # m ∈ {0, 1}: Alice's intended message
    received_bit: int = 0       # what Bob measured after full decode
    is_error:     bool = False  # received_bit != message_bit
    qotp_key_a:   int = 0       # QOTP key component a
    qotp_key_b:   int = 0       # QOTP key component b

    # Ground-truth Pauli error type (simulation metadata, not observable
    # in a real system without process tomography):
    #   'I' = no error, 'X' = bit-flip, 'Y' = bit+phase, 'Z' = phase-only
    pauli_error_type: str = "I"

    # --- Classical correction bits (m0, m1) ---
    correction_m0:  int = 0    # payload measurement result (Alice → Bob)
    correction_m1:  int = 0    # Alice's Bell-half measurement result

    # --- CHSH Bell pair channel (separate from QDS Bell pair) ---
    chsh_alice_angle: float = 0.0   # radians
    chsh_bob_angle:   float = 0.0   # radians
    chsh_alice_sign:  int   = 1     # +1 or -1
    chsh_bob_sign:    int   = 1     # +1 or -1

    # --- Verification decision ---
    verified: bool = False


# ---------------------------------------------------------------------------
# QDS Protocol runner
# ---------------------------------------------------------------------------

def run_trial(
    trial_id:    int,
    message_bit: int,
    noise_p:     float,
    rng:         np.random.Generator,
    attack_fn    = None,     # callable(state, channel, rng) or None
    attack_type: str = "clean",
    intensity:   float = 0.0,
) -> TrialLog:
    """
    Execute one complete QDS trial and return a TrialLog.

    The attack_fn hook is called at specific points in the protocol
    with a `channel` string identifying which channel is being processed:
        "qds_bell"    — after Bell pair is created, before teleportation
        "payload"     — after QOTP encryption, before teleportation
        "correction"  — after Alice measures, before Bob receives bits
        "chsh_bell"   — after CHSH Bell pair is created, before measurement

    Each hook can modify the state object in place (for quantum channels)
    or return modified (m0, m1) (for the correction channel).

    Args:
        trial_id    : Unique integer ID for this trial.
        message_bit : 0 or 1 — the bit Alice wants to sign.
        noise_p     : Depolarizing noise probability (shared, all qubits).
        rng         : NumPy random Generator.
        attack_fn   : Optional attack hook — see attacks.py.
        attack_type : String label for the TrialLog.
        intensity   : Attack intensity ∈ [0.0, 1.0].

    Returns:
        TrialLog with all fields populated.
    """
    log = TrialLog(
        trial_id=trial_id,
        attack_type=attack_type,
        intensity=intensity,
        noise_level=noise_p,
        message_bit=message_bit,
        received_bit=0,
        is_error=False,
    )

    # ── Step 1: Generate QOTP key ──────────────────────────────────────
    key_a, key_b = random_key(rng)
    log.qotp_key_a = key_a
    log.qotp_key_b = key_b

    # ── Step 2: Prepare message qubit ─────────────────────────────────
    payload = QuantumState(1)
    if message_bit == 1:
        payload.apply_X(0)

    # ── Step 3: QOTP encrypt ───────────────────────────────────────────
    qotp_encrypt(payload, 0, key_a, key_b)

    # ── Step 4: Payload attack (Pauli Forgery) ─────────────────────────
    # PF operates on the signature qubit AFTER QOTP and BEFORE teleportation.
    pauli_applied = "I"
    if attack_fn is not None:
        pauli_applied = attack_fn(payload, "payload", rng) or "I"
    log.pauli_error_type = pauli_applied

    # ── Step 5: Distribute QDS Bell pair ──────────────────────────────
    qds_bell = create_bell_pair(rng)

    # EH / IR attacks operate on the QDS Bell pair
    if attack_fn is not None:
        attack_fn(qds_bell, "qds_bell", rng)

    # ── Step 6: Teleport payload → Bob ────────────────────────────────
    m0, m1 = teleport(payload, qds_bell, noise_p=noise_p, rng=rng)

    # ── Step 7: CBM attack (modification of correction bits) ──────────
    if attack_fn is not None:
        result = attack_fn(None, "correction", rng, m0=m0, m1=m1)
        if result is not None:
            m0, m1 = result
    log.correction_m0 = m0
    log.correction_m1 = m1

    # ── Step 8: Bob applies correction ────────────────────────────────
    apply_teleport_correction(qds_bell, m0, m1)

    # ── Step 9: Bob decrypts QOTP ─────────────────────────────────────
    qotp_decrypt(qds_bell, 0, key_a, key_b)

    # ── Step 10: Bob measures ──────────────────────────────────────────
    received_bit = qds_bell.measure(0, rng)
    log.received_bit = received_bit
    log.is_error     = (received_bit != message_bit)
    log.verified     = not log.is_error

    # ── Step 11: CHSH Bell pair (completely separate from QDS) ────────
    chsh_bell = create_bell_pair(rng)
    if attack_fn is not None:
        attack_fn(chsh_bell, "chsh_bell", rng)
    a_angle, b_angle, a_sign, b_sign = chsh_measurement(chsh_bell, rng)
    log.chsh_alice_angle = a_angle
    log.chsh_bob_angle   = b_angle
    log.chsh_alice_sign  = a_sign
    log.chsh_bob_sign    = b_sign

    return log


def run_batch(
    n_trials:    int,
    noise_p:     float,
    rng:         np.random.Generator,
    attack_fn    = None,
    attack_type: str = "clean",
    intensity:   float = 0.0,
    start_id:    int = 0,
) -> List[TrialLog]:
    """
    Run *n_trials* QDS trials and return a list of TrialLogs.

    Message bits are sampled uniformly at random for each trial.
    """
    logs = []
    for i in range(n_trials):
        msg = int(rng.integers(0, 2))
        log = run_trial(
            trial_id=start_id + i,
            message_bit=msg,
            noise_p=noise_p,
            rng=rng,
            attack_fn=attack_fn,
            attack_type=attack_type,
            intensity=intensity,
        )
        logs.append(log)
    return logs


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== qds.py self-test ===")
    rng = np.random.default_rng(99)
    N = 500

    # --- Test 1: Clean traffic, no noise → 100% verification ---
    logs = run_batch(N, noise_p=0.0, rng=rng)
    errors = sum(l.is_error for l in logs)
    assert errors == 0, f"Noiseless QDS: {errors}/{N} errors (expected 0)"
    print(f"PASS: Clean, noiseless QDS → 0/{N} errors (fidelity = 1.0)")

    # --- Test 2: Noisy traffic → error rate consistent with depolarizing model ---
    # Each trial applies depolarizing (p=0.05) to 3 qubits.
    # X and Y errors on the payload qubit each cause QBER errors; Z does not.
    # Effective per-qubit error contribution to QBER: 2p/3 (X + Y errors).
    # With 3 qubits (payload, Alice, Bob) and interactions: empirical is simpler.
    logs_noisy = run_batch(N, noise_p=0.05, rng=rng)
    qber = sum(l.is_error for l in logs_noisy) / N
    print(f"     Noisy QBER (p=0.05): {qber:.4f}")
    assert 0.0 < qber < 0.35, f"Noisy QBER = {qber:.4f} out of expected range"
    print(f"PASS: Noisy QDS (p=0.05) QBER = {qber:.4f} ∈ (0, 0.35)")

    # --- Test 3: CHSH S ≈ 2√2 on clean traffic ---
    from bell import compute_chsh_S, S_THEORY
    chsh_samples = [(l.chsh_alice_angle, l.chsh_bob_angle,
                     l.chsh_alice_sign,  l.chsh_bob_sign) for l in logs]
    S, _ = compute_chsh_S(chsh_samples)
    assert abs(S - S_THEORY) < 0.20, f"CHSH S = {S:.4f} too far from {S_THEORY:.4f}"
    print(f"PASS: Clean CHSH S = {S:.4f} ≈ 2√2 = {S_THEORY:.4f}")

    # --- Test 4: Correction bits are uniform (χ² sanity check) ---
    from scipy.stats import chisquare
    pairs = [(l.correction_m0, l.correction_m1) for l in logs]
    counts_dict = {(0,0):0, (0,1):0, (1,0):0, (1,1):0}
    for p in pairs:
        counts_dict[p] += 1
    counts_arr = np.array([counts_dict[k] for k in [(0,0),(0,1),(1,0),(1,1)]])
    chi2, pval = chisquare(counts_arr)
    assert pval > 0.01, f"Correction bits not uniform! χ²={chi2:.2f}, p={pval:.4f}"
    print(f"PASS: Correction bits are uniform (χ²={chi2:.2f}, p={pval:.4f} > 0.01)")

    print("=== All qds.py tests passed ===")
