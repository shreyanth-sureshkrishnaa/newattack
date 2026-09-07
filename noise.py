"""
noise.py — Shared depolarizing noise model for Q-ATT&CK.

ALL noise in the project flows through this single module.
Do NOT implement depolarizing noise in any other file.

Single-qubit depolarizing channel (formal definition):
    ε(ρ) = (1−p)ρ + (p/3)(XρX† + YρY† + ZρZ†)

State-vector simulation: with probability (1−p) apply I; with
probability p/3 each apply X, Y, or Z.  The density matrix averaged
over many i.i.d. trials equals the channel formula above exactly.

Known limitations:
  - Single-qubit, i.i.d. depolarizing only; no correlated/crosstalk noise.
  - No T1/T2 decoherence, no gate-miscalibration, no leakage.
  - Applied once per qubit at designated "noisy step", not per gate.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from qsim import QuantumState   # only for type-checker; no runtime import


def clip_prob(p: float) -> float:
    """
    Clip a probability into [0.0, 1.0] to guard against floating-point drift.

    MUST be called before every random-sampling expression in the codebase:
        rng.random() < clip_prob(p)       ← correct
        rng.random() < p                  ← unsafe (p may be 1.0000000002)
    """
    return float(np.clip(p, 0.0, 1.0))


def depolarizing_channel(
    state: "QuantumState",
    qubit: int,
    p: float,
    rng: Optional[np.random.Generator] = None,
) -> None:
    """
    Apply the single-qubit depolarizing channel in place.

    State-vector protocol (equivalent to the density-matrix channel in expectation):
        r ~ Uniform[0, 1)
        r < p/3        → apply X   (bit-flip error)
        p/3 ≤ r < 2p/3 → apply Y   (bit+phase error)
        2p/3 ≤ r < p   → apply Z   (phase-flip error)
        r ≥ p          → identity  (no error, probability 1−p)

    The three error branches each have probability p/3; the no-error branch
    has probability 1−p.  Summing: p/3 + p/3 + p/3 + (1−p) = 1 ✓.
    Trace is preserved because Pauli gates are unitary.

    Args:
        state : QuantumState to modify in place.
        qubit : Index of qubit to apply noise to.
        p     : Depolarizing error probability ∈ [0, 1].
        rng   : NumPy random Generator (creates new one if None).
    """
    p = clip_prob(p)
    if p == 0.0:
        return
    if rng is None:
        rng = np.random.default_rng()
    r = rng.random()
    if r < p / 3:
        state.apply_X(qubit)
    elif r < 2.0 * p / 3:
        state.apply_Y(qubit)
    elif r < p:
        state.apply_Z(qubit)
    # else: identity (probability 1−p), do nothing


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== noise.py self-test ===")
    from qsim import QuantumState

    rng = np.random.default_rng(0)
    N = 60_000   # shots for density-matrix estimate

    # --- Test 1: clip_prob correctness ---
    assert clip_prob(-1e-15) == 0.0,  "clip_prob should clamp negatives to 0"
    assert clip_prob(1 + 1e-15) == 1.0, "clip_prob should clamp >1 to 1"
    assert clip_prob(0.5) == 0.5,     "clip_prob should be identity on (0,1)"
    print("PASS: clip_prob clamps correctly")

    # --- Test 2: p=0 → identity ---
    s = QuantumState(1)
    s.apply_H(0)
    original = s.vec.copy()
    depolarizing_channel(s, 0, 0.0, rng)
    assert np.allclose(s.vec, original), "p=0 must leave state unchanged"
    print("PASS: p=0 → identity")

    # --- Test 3: trace preserved for several p values ---
    for p_test in [0.1, 0.5, 1.0]:
        s = QuantumState(1)
        s.apply_H(0)
        depolarizing_channel(s, 0, p_test, rng)
        norm = float(np.linalg.norm(s.vec))
        assert abs(norm - 1.0) < 1e-10, f"Norm ≠ 1 after depolarizing(p={p_test})"
    print("PASS: trace (L2-norm) preserved for p ∈ {0.1, 0.5, 1.0}")

    # --- Test 4: p=1 → maximally mixed output (density matrix ≈ I/2) ---
    # Derivation: ε(ρ)|_{p=1} = (1/3)(XρX + YρY + ZρZ).
    # For any single-qubit ρ = [[a, c],[c*, b]], the channel gives:
    #   XρX = [[b, c*],[c, a]], YρY = [[b, -c*],[-c, a]], ZρZ = [[a, -c],[-c*, b]]
    #   Sum/3 = [[(a+b+a)/3*... wait, let me be exact:
    #   diagonal: (b+b+a)/3 and (a+a+b)/3  → both = (a+2b)/3 and (2a+b)/3
    #   Hmm that's not I/2 for general ρ...
    #
    # Actually the correct channel for p=1:
    #   ε(ρ) = (0)ρ + (1/3)(XρX + YρY + ZρZ)
    # For ρ = |0⟩⟨0| = [[1,0],[0,0]]:
    #   XρX = [[0,0],[0,1]], YρY = [[0,0],[0,1]], ZρZ = [[1,0],[0,0]]
    #   ε(ρ) = (1/3)([[0,0],[0,1]]+[[0,0],[0,1]]+[[1,0],[0,0]])
    #         = (1/3)[[1,0],[0,2]] ≠ I/2
    #
    # NOTE: The p=1 depolarizing channel is NOT the same as the completely
    # depolarizing channel (which is ε(ρ) = I/2 regardless of ρ).  The
    # standard formula ε(ρ) = (1-p)ρ + (p/3)(X+Y+Z) at p=1 gives
    # ε(ρ) = (1/3)(XρX+YρY+ZρZ), which for |0⟩⟨0| gives [[1/3,0],[0,2/3]].
    #
    # The COMPLETELY depolarizing channel corresponds to p = 3/4 in the
    # parameterisation ε(ρ) = (1-4p/3)ρ + (p/3)(X+Y+Z) that is common
    # in the QEC literature but NOT the parameterisation used here.
    #
    # Here we use the convention p = total error probability,
    # so ε(ρ)|_{p=3/4} = I/2 (completely mixed).
    # We test this instead.
    rho_sum = np.zeros((2, 2), dtype=np.complex128)
    for _ in range(N):
        s = QuantumState(1)
        depolarizing_channel(s, 0, 0.75, rng)
        rho_sum += s.single_qubit_dm(0)
    rho_avg = rho_sum / N
    expected = np.eye(2, dtype=np.complex128) / 2
    max_dev = float(np.max(np.abs(rho_avg - expected)))
    assert max_dev < 0.02, f"p=3/4 should give I/2; max deviation = {max_dev:.4f}"
    print(f"PASS: p=3/4 → density matrix ≈ I/2 (max deviation {max_dev:.4f})")

    print("=== All noise.py tests passed ===")
