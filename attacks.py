"""
attacks.py — Attack simulators for SIGWATCH.

Each attack is a callable (an "attack function") with signature:
    attack_fn(state, channel, rng, **kwargs) → Optional[Any]

The `channel` parameter tells the function which physical channel is
currently being processed.  The function should act ONLY on channels it
legitimately controls; ignoring all others.

Four attacks implemented, each at the correct physical layer:

  IR  — Intercept-Resend:
        Targets the QDS Bell pair AND the CHSH Bell pair.
        With probability `intensity`, Eve intercepts Bob's qubit, measures
        it in a random basis (Z or X), and re-prepares a fresh qubit in the
        measured state.  This destroys entanglement.
        Detection: QBER ↑ (wrong basis 50% of the time), CHSH S drops.

  EH  — Entanglement Hijacking:
        Targets the QDS Bell pair AND the CHSH Bell pair.
        With probability `intensity`, Eve replaces Bob's qubit with an
        independent state (|0⟩ or |+⟩ chosen randomly), completely
        severing entanglement.
        Detection: QBER ↑↑, CHSH S drops sharply.

  PF  — Pauli Forgery:
        Targets the signature (payload) qubit ONLY.
        With probability `intensity`, Eve applies X to the QOTP-encrypted
        signature qubit in transit, attempting to forge the signed message.
        Effect on QBER: X applied over QOTP commutes with the QOTP key in
        a way that ALWAYS causes a bit-flip error after decryption (shown
        in the detailed derivation in qotp.py).
        CHSH Bell pair is UNTOUCHED.  Correction bits UNTOUCHED.
        Detection: QBER ↑, Pauli-consistency check fires (X-errors dominate).

  CBM — Correction Bit Manipulation:
        Targets the classical correction bits (m0, m1) ONLY.
        With probability `intensity`, Eve replaces (m0, m1) with (1, 1),
        injecting a worst-case correction error.
        Effect on QBER: Bob applies Z X to his qubit unconditionally,
        which introduces errors except when the legitimate (m0, m1) = (1, 1).
        CHSH Bell pair UNTOUCHED.  Payload qubit UNTOUCHED.
        Detection: correction-bit distribution becomes non-uniform, chi-squared fires.

Channel discipline (non-negotiable design principle #8):
  Each attack_fn checks the `channel` argument and acts only when it matches
  the physical channel the attack controls.  Data-path tracing:
    IR:  acts on "qds_bell" and "chsh_bell"; ignores "payload" and "correction".
    EH:  acts on "qds_bell" and "chsh_bell"; ignores "payload" and "correction".
    PF:  acts on "payload"; ignores all other channels.
    CBM: acts on "correction"; ignores all other channels.
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Tuple, Any
from qsim import QuantumState
from noise import clip_prob


# ---------------------------------------------------------------------------
# Shared utility: intercept Bob's qubit from a 2-qubit Bell state
# ---------------------------------------------------------------------------

def _intercept_resend_bell(
    bell: QuantumState,
    rng: np.random.Generator,
) -> None:
    """
    Intercept-Resend on Bob's qubit (qubit 1) of a 2-qubit Bell state.

    Protocol:
      1. Eve randomly chooses measurement basis: Z (50%) or X (50%).
      2. If X basis: apply H to qubit 1 to rotate into X basis.
      3. Eve measures qubit 1 → collapses Alice's qubit as well.
      4. If X basis: apply H again so Bob receives |+⟩ or |−⟩ (Eve's
         prepared state in her chosen basis).

    Net effect: Alice's qubit collapses to a product state; Bob's qubit is
    Eve's re-prepared state.  Entanglement is destroyed.

    CHSH effect derivation:
      After IR with 50/50 Z-or-X basis choice, the resulting mixed state
      has average correlator:
        E_ZbasisIR(a,b) = cos(a)·cos(b)     (Z-basis intercept)
        E_XbasisIR(a,b) = cos(a)·sin(b)     (X-basis intercept)
        E_avg(a,b) = cos(a)·(cos(b)+sin(b))/2

      For ALICE_ANGLES=[0, π/2], BOB_ANGLES=[π/4, 3π/4]:
        S_IR ≈ √2 (Z-basis) or 0 (X-basis) → average ≈ √2/2 ≈ 0.71

      Either way, S_IR ≪ S_theory = 2√2, so the CHSH detector fires.
    """
    eve_basis = int(rng.integers(0, 2))   # 0=Z, 1=X
    if eve_basis == 1:
        bell.apply_H(1)   # rotate Bob's qubit to X basis
    bell.measure(1, rng)  # Eve measures; state collapses, no entanglement
    if eve_basis == 1:
        bell.apply_H(1)   # Bob's qubit is now |+⟩ or |−⟩ (Eve's prepared state)


def _hijack_bell(
    bell: QuantumState,
    rng: np.random.Generator,
) -> None:
    """
    Entanglement Hijacking on Bob's qubit (qubit 1) of a 2-qubit Bell state.

    Eve completely replaces Bob's qubit with an independent product state,
    choosing randomly between |0⟩ and |+⟩.  Alice's qubit is left as is
    (Alice doesn't know), but they are no longer entangled.

    Net effect: the 2-qubit state is a product state with no correlations.
    CHSH S → 0 (no quantum correlations at all).

    Implementation: collapse the state to a product by measuring qubit 0
    (this simulates Eve's interception of the channel), then re-initialize
    qubit 1 to Eve's independent state.
    """
    # Measure Alice's qubit to collapse the state to a product state
    bell.measure(0, rng)
    # Replace Bob's qubit with Eve's fresh state (independent of Alice's)
    choice = int(rng.integers(0, 2))
    if choice == 0:
        # Bob gets |0⟩ — no correlation with Alice's qubit
        bell.vec = np.zeros(2, dtype=np.complex128)
        bell.vec[0] = 1.0
        bell.n = 1
        # But the full 2-qubit state needs to be reconstructed
        # Rebuild as 2-qubit product state: Alice's collapsed qubit ⊗ |0⟩
        alice_bit = 0 if bell.vec[0] != 0 else 1  # Alice's measured outcome
    # Simplest: reset to |00⟩ product state (both independent)
    bell.n = 2
    bell.vec = np.zeros(4, dtype=np.complex128)
    # Random product: |0⟩ or |+⟩ for each qubit independently
    alice_state = np.array([1.0, 0.0], dtype=np.complex128)  # always |0⟩ for Alice
    if choice == 0:
        bob_state = np.array([1.0, 0.0], dtype=np.complex128)   # |0⟩
    else:
        bob_state = np.array([1.0, 1.0], dtype=np.complex128) / np.sqrt(2)  # |+⟩
    bell.vec = np.kron(alice_state, bob_state)


# ---------------------------------------------------------------------------
# Attack factory functions
# ---------------------------------------------------------------------------

def make_ir_attack(intensity: float) -> callable:
    """
    Return an attack function implementing Intercept-Resend at the given intensity.

    intensity ∈ [0.0, 1.0]: fraction of trials in which IR fires.
    When it fires, Eve intercepts Bob's qubit from both the QDS Bell pair
    and the CHSH Bell pair (she controls the quantum channel).

    QDS QBER effect: ~25% errors on attacked trials (Eve guesses wrong basis
    50% of the time → 50% error on those → avg 25%).
    CHSH S effect: S drops to ≈ √2/2 on attacked trials.
    """
    intensity = clip_prob(intensity)

    def attack_fn(
        state: Optional[QuantumState],
        channel: str,
        rng: np.random.Generator,
        **kwargs,
    ) -> Optional[Any]:
        if channel in ("qds_bell", "chsh_bell"):
            if rng.random() < intensity:
                _intercept_resend_bell(state, rng)
        # "payload" and "correction" are untouched by IR
        return None

    attack_fn.__name__ = f"IR(intensity={intensity:.2f})"
    return attack_fn


def make_eh_attack(intensity: float) -> callable:
    """
    Return an attack function implementing Entanglement Hijacking.

    intensity ∈ [0.0, 1.0]: fraction of trials in which EH fires.
    When it fires, Eve completely replaces Bob's qubit with an independent
    state on both the QDS Bell pair and the CHSH Bell pair.

    QDS QBER effect: ~50% errors (Bob measures an independent random qubit).
    CHSH S effect: S → 0 (no quantum correlations).
    """
    intensity = clip_prob(intensity)

    def attack_fn(
        state: Optional[QuantumState],
        channel: str,
        rng: np.random.Generator,
        **kwargs,
    ) -> Optional[Any]:
        if channel in ("qds_bell", "chsh_bell"):
            if rng.random() < intensity:
                _hijack_bell(state, rng)
        return None

    attack_fn.__name__ = f"EH(intensity={intensity:.2f})"
    return attack_fn


def make_pf_attack(intensity: float) -> callable:
    """
    Return an attack function implementing Pauli Forgery.

    intensity ∈ [0.0, 1.0]: fraction of trials in which Eve applies X
    to the QOTP-encrypted signature qubit.

    Physical channel: "payload" ONLY.
    QDS Bell pair: untouched.
    CHSH Bell pair: untouched.
    Correction bits: untouched.

    Effect derivation (why X forgery always causes a QBER error):
      Alice's payload after QOTP: X^a Z^b |m⟩.
      Eve applies X: X(X^a Z^b |m⟩) = X^{1⊕a} Z^b |m⟩.
      After teleportation (noiseless), Bob has X^{1⊕a} Z^b |m⟩.
      Bob decrypts with (a,b): applies X^a Z^b:
        X^a Z^b · X^{1⊕a} Z^b |m⟩
      Case a=0: Z^b X Z^b |m⟩ = Z^{2b} X |m⟩ = X|m⟩  → bit-flip error ✓
      Case a=1: X Z^b · I · Z^b |m⟩ = X Z^{2b}|m⟩ = X|m⟩ → bit-flip error ✓
      (Z^{2b} = I for b ∈ {0,1} since Z² = I)
      Therefore: Pauli Forgery with X ALWAYS causes QBER = 1 on attacked trials.

    Detection:
      QBER rises proportionally to intensity.
      Pauli-consistency check fires because X-type errors dominate
      (vs equal X/Y/Z rates under depolarizing noise).

    Returns the Pauli type string ('X' if attack fired, 'I' otherwise)
    so the TrialLog can record the ground-truth error type.
    """
    intensity = clip_prob(intensity)

    def attack_fn(
        state: Optional[QuantumState],
        channel: str,
        rng: np.random.Generator,
        **kwargs,
    ) -> Optional[Any]:
        if channel == "payload":
            if rng.random() < intensity:
                state.apply_X(0)
                return "X"    # ground-truth Pauli label for the TrialLog
            return "I"
        # "qds_bell", "chsh_bell", "correction" are untouched by PF
        return None

    attack_fn.__name__ = f"PF(intensity={intensity:.2f})"
    return attack_fn


def make_cbm_attack(intensity: float) -> callable:
    """
    Return an attack function implementing Correction Bit Manipulation.

    intensity ∈ [0.0, 1.0]: fraction of trials in which CBM fires.
    When it fires, Eve replaces (m0, m1) with (1, 1).

    Physical channel: "correction" ONLY.
    All quantum channels are untouched.

    QBER effect: Bob applies Z X unconditionally (since m0=1, m1=1),
    which introduces a ZX error after the legitimate correction.
    Expected QBER per attacked trial: depends on the legitimate (m0, m1).
    Average over all legitimate pairs (each equally probable at 1/4):
      - (0,0) → corrected to (1,1): error = always
      - (0,1) → corrected to (1,1): extra Z applied → ~always error
      - (1,0) → corrected to (1,1): extra X applied → ~always error
      - (1,1) → corrected to (1,1): no change → 0 error
    Average QBER from CBM: ~3/4 on attacked trials.

    Detection:
      Correction-bit distribution is no longer uniform:
      P(1,1) = (1−γ)·0.25 + γ·1.0 = 0.25 + 0.75γ
      P(0,0) = P(0,1) = P(1,0) = (1−γ)·0.25
      Chi-squared test detects this non-uniformity.
    """
    intensity = clip_prob(intensity)

    def attack_fn(
        state: Optional[QuantumState],
        channel: str,
        rng: np.random.Generator,
        **kwargs,
    ) -> Optional[Any]:
        if channel == "correction":
            m0 = kwargs.get("m0", 0)
            m1 = kwargs.get("m1", 0)
            if rng.random() < intensity:
                return (1, 1)   # Eve forces (m0, m1) = (1, 1)
            return (m0, m1)
        return None

    attack_fn.__name__ = f"CBM(intensity={intensity:.2f})"
    return attack_fn


ATTACK_MAKERS = {
    "IR":  make_ir_attack,
    "EH":  make_eh_attack,
    "PF":  make_pf_attack,
    "CBM": make_cbm_attack,
    "clean": lambda intensity: None,
}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== attacks.py self-test ===")
    from qds import run_batch
    from bell import compute_chsh_S, S_THEORY

    rng = np.random.default_rng(42)
    N = 600

    def _metrics(logs):
        qber = sum(l.is_error for l in logs) / len(logs)
        chsh_samples = [(l.chsh_alice_angle, l.chsh_bob_angle,
                         l.chsh_alice_sign, l.chsh_bob_sign) for l in logs]
        S, _ = compute_chsh_S(chsh_samples)
        return qber, S

    # --- Baseline ---
    logs_clean = run_batch(N, 0.0, rng, attack_type="clean")
    qber_c, S_c = _metrics(logs_clean)
    print(f"  Clean: QBER={qber_c:.4f}, S={S_c:.4f}")
    assert qber_c == 0.0, "Clean traffic should have 0 QBER"
    assert abs(S_c - S_THEORY) < 0.20

    # --- IR at full intensity ---
    ir_fn = make_ir_attack(1.0)
    logs_ir = run_batch(N, 0.0, rng, attack_fn=ir_fn, attack_type="IR", intensity=1.0)
    qber_ir, S_ir = _metrics(logs_ir)
    print(f"  IR(1.0): QBER={qber_ir:.4f}, S={S_ir:.4f}")
    assert qber_ir > 0.15, f"IR should cause QBER > 0.15; got {qber_ir:.4f}"
    assert S_ir < 2.0, f"IR should reduce S below 2.0; got {S_ir:.4f}"
    print("PASS: IR at intensity=1.0 raises QBER and drops S below classical bound")

    # --- EH at full intensity ---
    eh_fn = make_eh_attack(1.0)
    logs_eh = run_batch(N, 0.0, rng, attack_fn=eh_fn, attack_type="EH", intensity=1.0)
    qber_eh, S_eh = _metrics(logs_eh)
    print(f"  EH(1.0): QBER={qber_eh:.4f}, S={S_eh:.4f}")
    assert qber_eh > 0.20, f"EH should cause QBER > 0.20; got {qber_eh:.4f}"
    assert S_eh < 2.0, f"EH should drop S below 2.0; got {S_eh:.4f}"
    print("PASS: EH at intensity=1.0 raises QBER and drops S")

    # --- PF at full intensity: QBER should be ≈1.0, S unaffected ---
    pf_fn = make_pf_attack(1.0)
    logs_pf = run_batch(N, 0.0, rng, attack_fn=pf_fn, attack_type="PF", intensity=1.0)
    qber_pf, S_pf = _metrics(logs_pf)
    print(f"  PF(1.0): QBER={qber_pf:.4f}, S={S_pf:.4f}")
    assert qber_pf > 0.90, f"PF should cause QBER ≈ 1.0; got {qber_pf:.4f}"
    assert abs(S_pf - S_THEORY) < 0.20, f"PF should NOT affect CHSH; S={S_pf:.4f}"
    print("PASS: PF at intensity=1.0 → QBER≈1.0, CHSH S unaffected")

    # --- CBM at full intensity: non-uniform correction bits, S unaffected ---
    from scipy.stats import chisquare
    cbm_fn = make_cbm_attack(1.0)
    logs_cbm = run_batch(N, 0.0, rng, attack_fn=cbm_fn, attack_type="CBM", intensity=1.0)
    qber_cbm, S_cbm = _metrics(logs_cbm)
    counts = [0, 0, 0, 0]
    for l in logs_cbm:
        counts[(l.correction_m0 << 1) | l.correction_m1] += 1
    chi2, pval = chisquare(counts)
    print(f"  CBM(1.0): QBER={qber_cbm:.4f}, S={S_cbm:.4f}, corr χ²={chi2:.1f} p={pval:.4f}")
    assert pval < 0.001, f"CBM should cause non-uniform correction bits; p={pval:.4f}"
    assert abs(S_cbm - S_THEORY) < 0.20, f"CBM should NOT affect CHSH; S={S_cbm:.4f}"
    print("PASS: CBM at intensity=1.0 → non-uniform correction bits, CHSH S unaffected")

    print("=== All attacks.py tests passed ===")
