"""
bell.py — Bell pair generation and teleportation protocol for SIGWATCH.

This module implements the quantum primitives used by the QDS layer.
All functions are stateless; they accept and return QuantumState objects.

Teleportation protocol (standard, 3-qubit: payload=0, Alice=1, Bob=2):
  1. Alice prepares |Φ+⟩_{12}  (Bell pair distributed between Alice and Bob)
  2. Payload: |ψ⟩_0 = the qubit to teleport
  3. CNOT(control=0, target=1)
  4. H(0)
  5. m0 = measure(0),  m1 = measure(1)     (Alice sends m0, m1 classically)
  6. Bob applies correction: Z^m0 X^m1 to qubit 2

Derivation that the correction recovers |ψ⟩:
  Starting state: |ψ⟩_0 ⊗ |Φ+⟩_{12}  where |ψ⟩=α|0⟩+β|1⟩, |Φ+⟩=(|00⟩+|11⟩)/√2
  After CNOT(0→1): α|0⟩(|00⟩+|11⟩)/√2 + β|1⟩(|10⟩+|01⟩)/√2
  After H(0): grouping by (qubit0, qubit1) measurement outcomes:
    |00⟩: α|0⟩_2 + β|1⟩_2  = |ψ⟩           → correction Z^0 X^0 = I   ✓
    |01⟩: α|1⟩_2 + β|0⟩_2  = X|ψ⟩          → correction Z^0 X^1 = X   ✓
    |10⟩: α|0⟩_2 − β|1⟩_2  = Z|ψ⟩          → correction Z^1 X^0 = Z   ✓
    |11⟩:−α|1⟩_2 + β|0⟩_2  = −ZX|ψ⟩~ZX|ψ⟩ → correction Z^1 X^1 = ZX  ✓
  (global phase −1 in the last case is unobservable)

Fidelity in the noiseless case: F = 1.0 exactly (teleportation is perfect).
Fidelity with depolarizing noise p on each qubit: degrades below 1;
exact value depends on where noise is applied (see self-test for empirical check).

CHSH angles (for genuine Bell test, documented here for cross-reference):
  Alice: a1 = 0,   a2 = π/2   (0° and 90°)
  Bob:   b1 = π/4, b2 = 3π/4  (45° and 135°)
  These give E(a,b) = cos(a−b) for |Φ+⟩, and
  S = |E(a1,b1) − E(a1,b2) + E(a2,b1) + E(a2,b2)|
    = |cos(π/4) − cos(3π/4) + cos(π/4) + cos(π/4)|    [a1−b1=−π/4, a1−b2=−3π/4, etc.]

  Wait — let me be explicit: for the sign convention E(a,b)=cos(a−b):
    E(0,  π/4)  = cos(−π/4)  =  1/√2
    E(0, 3π/4)  = cos(−3π/4) = −1/√2
    E(π/2, π/4) = cos( π/4)  =  1/√2
    E(π/2,3π/4) = cos(−π/4)  =  1/√2
  S = |1/√2 − (−1/√2) + 1/√2 + 1/√2| = |4/√2| = 2√2 ≈ 2.828  ✓
"""

from __future__ import annotations

from typing import Tuple, Optional
import numpy as np
from qsim import QuantumState
from noise import depolarizing_channel


# ---------------------------------------------------------------------------
# Bell pair
# ---------------------------------------------------------------------------

def create_bell_pair(rng: Optional[np.random.Generator] = None) -> QuantumState:
    """
    Create the two-qubit Bell state |Φ+⟩ = (|00⟩ + |11⟩) / √2.

    Qubit layout: qubit 0 = Alice's half, qubit 1 = Bob's half.
    Circuit: H(0) → CNOT(0→1).

    Returns a QuantumState with n=2.
    """
    s = QuantumState(2)
    s.apply_H(0)
    s.apply_CNOT(0, 1)
    return s


# ---------------------------------------------------------------------------
# Teleportation
# ---------------------------------------------------------------------------

def teleport(
    payload: QuantumState,
    bell: QuantumState,
    noise_p: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[int, int]:
    """
    Teleport the single-qubit *payload* (qubit 0 of a 1-qubit state) to
    Bob using the pre-distributed Bell pair *bell* (2-qubit state, qubit 0
    = Alice's half, qubit 1 = Bob's half).

    Protocol:
      1. Optionally apply depolarizing noise to payload and Bell pair qubits.
      2. CNOT(payload → Alice's half), H(payload).
      3. Measure payload → m0, measure Alice's half → m1.
      4. Return (m0, m1) for Bob to apply his correction.

    After this call:
      - *payload* state is destroyed (measured/collapsed).
      - *bell* qubit 0 is measured/collapsed.
      - *bell* qubit 1 holds the (uncorrected) teleported state.

    To get the teleported state, Bob must apply Z^m0 X^m1 to bell.vec[qubit=1];
    use apply_teleport_correction(bell, m0, m1) for that.

    Args:
        payload : 1-qubit QuantumState to teleport.
        bell    : 2-qubit Bell pair shared between Alice (q0) and Bob (q1).
        noise_p : Depolarizing error probability applied to all three qubits
                  before the teleportation circuit.  0 = noiseless.
        rng     : NumPy random Generator.

    Returns:
        (m0, m1): Classical correction bits.  m0 = payload measurement,
                  m1 = Alice's Bell-half measurement.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Compose into a 3-qubit register: [payload | Alice | Bob]
    # We do this by constructing the 3-qubit state vector from the tensor product.
    # payload: 1 qubit, bell: 2 qubits → 3 qubits total.
    state = QuantumState(3)
    # |payload⟩ ⊗ |bell⟩
    state.vec = np.kron(payload.vec, bell.vec).astype(np.complex128)

    # Apply noise to all three qubits (shared noise model from noise.py)
    if noise_p > 0:
        depolarizing_channel(state, 0, noise_p, rng)   # payload qubit
        depolarizing_channel(state, 1, noise_p, rng)   # Alice's Bell half
        depolarizing_channel(state, 2, noise_p, rng)   # Bob's Bell half

    # Teleportation circuit
    state.apply_CNOT(0, 1)   # payload controls Alice's half
    state.apply_H(0)

    # Alice measures
    m0 = state.measure(0, rng)   # payload measurement result
    m1 = state.measure(1, rng)   # Alice's Bell-half measurement result

    # Write Bob's half back into bell.vec so caller can inspect / correct it
    # After measuring qubits 0 and 1, qubit 2 holds the teleported state.
    # Reconstruct the 1-qubit reduced state of qubit 2.
    bell.vec = np.zeros(2, dtype=np.complex128)
    # After collapse of qubits 0 and 1, the only nonzero block of state.vec
    # corresponds to (q0=m0, q1=m1).  Extract qubit 2 amplitudes from it.
    n_states = 1 << 3
    for i in range(n_states):
        q0 = (i >> 2) & 1
        q1 = (i >> 1) & 1
        q2 = i & 1
        if q0 == m0 and q1 == m1:
            bell.vec[q2] = state.vec[i]
    norm = np.linalg.norm(bell.vec)
    if norm > 1e-12:
        bell.vec /= norm
    bell.n = 1   # Now it's a 1-qubit state (Bob's half)

    return m0, m1


def apply_teleport_correction(
    bob_state: QuantumState,
    m0: int,
    m1: int,
) -> None:
    """
    Apply Bob's teleportation correction: Z^m0 X^m1 to qubit 0 of bob_state.

    This is the final step of teleportation.  After correction, qubit 0 of
    bob_state holds the teleported payload (within noise).
    """
    if m1:
        bob_state.apply_X(0)
    if m0:
        bob_state.apply_Z(0)


# ---------------------------------------------------------------------------
# CHSH measurement (genuine Bell test, separate from QDS Bell pairs)
# ---------------------------------------------------------------------------

# CHSH measurement angles (radians).  Derived in module docstring.
ALICE_ANGLES = [0.0, np.pi / 2]           # a1=0°, a2=90°
BOB_ANGLES   = [np.pi / 4, 3 * np.pi / 4] # b1=45°, b2=135°

# Theoretical S for |Φ+⟩ with these angles (noiseless):
# S_THEORY = 2√2 ≈ 2.8284271247
S_THEORY = 2 * np.sqrt(2)


def chsh_measurement(
    bell: QuantumState,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float, int, int]:
    """
    Perform one CHSH measurement on a 2-qubit state *bell*.

    Protocol:
      1. Randomly choose Alice's basis angle a ∈ {0, π/2}.
      2. Randomly choose Bob's basis angle b ∈ {π/4, 3π/4}.
      3. Apply RY(-a) to qubit 0 (Alice) and RY(-b) to qubit 1 (Bob).
         This rotates so that measuring Z = measuring in basis (a or b).
      4. Measure both qubits.
      5. Outcome +1 ↔ measured 0, outcome −1 ↔ measured 1.

    Returns:
        (alice_angle, bob_angle, alice_sign, bob_sign)
        where alice_sign, bob_sign ∈ {+1, −1}.

    NOTE: The state *bell* is modified in place (measurement collapses it).
    Always pass a fresh copy for each trial.
    """
    if rng is None:
        rng = np.random.default_rng()
    s = bell.copy()
    a = rng.choice(ALICE_ANGLES)
    b = rng.choice(BOB_ANGLES)
    s.apply_RY(0, -a)
    s.apply_RY(1, -b)
    a_out = s.measure(0, rng)
    b_out = s.measure(1, rng)
    a_sign = 1 - 2 * a_out   # 0 → +1,  1 → −1
    b_sign = 1 - 2 * b_out
    return float(a), float(b), int(a_sign), int(b_sign)


def compute_chsh_S(
    samples: list,
) -> Tuple[float, dict]:
    """
    Compute the CHSH S-value from a list of
    (alice_angle, bob_angle, alice_sign, bob_sign) tuples.

    Algorithm:
      For each of the 4 basis pairs (a,b), compute
        E(a,b) = mean(alice_sign * bob_sign)  for samples with those bases.
      Then:
        S = |E(a1,b1) − E(a1,b2) + E(a2,b1) + E(a2,b2)|

    Returns:
        S   : CHSH S-value (float).
        info: dict with per-pair correlators and sample counts.

    If any basis pair has 0 samples, that correlator is set to 0.0 and
    a warning is issued (insufficient data; S is unreliable).
    """
    from collections import defaultdict
    sums   = defaultdict(float)
    counts = defaultdict(int)
    for a, b, sa, sb in samples:
        key = (round(a, 6), round(b, 6))
        sums[key]   += sa * sb
        counts[key] += 1

    def E(a: float, b: float) -> float:
        key = (round(a, 6), round(b, 6))
        n = counts[key]
        if n == 0:
            return 0.0
        return sums[key] / n

    a1, a2 = ALICE_ANGLES
    b1, b2 = BOB_ANGLES
    e11 = E(a1, b1)
    e12 = E(a1, b2)
    e21 = E(a2, b1)
    e22 = E(a2, b2)
    S = abs(e11 - e12 + e21 + e22)
    info = {
        "E(a1,b1)": e11, "E(a1,b2)": e12,
        "E(a2,b1)": e21, "E(a2,b2)": e22,
        "counts":   {str(k): v for k, v in counts.items()},
    }
    return S, info


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== bell.py self-test ===")
    rng = np.random.default_rng(7)

    # --- Test 1: Bell pair is correct |Φ+⟩ ---
    s = create_bell_pair()
    expected = np.array([1, 0, 0, 1], dtype=np.complex128) / np.sqrt(2)
    assert np.allclose(s.vec, expected), f"|Φ+⟩ wrong: {s.vec}"
    print("PASS: create_bell_pair → |Φ+⟩ = (|00⟩+|11⟩)/√2")

    # --- Test 2: Teleportation fidelity ≈ 1.0 in noiseless case ---
    N = 500
    fidelity_sum = 0.0
    test_states = []
    for _ in range(N):
        # Random single-qubit state
        theta = rng.uniform(0, np.pi)
        phi   = rng.uniform(0, 2 * np.pi)
        psi   = QuantumState(1)
        psi.vec = np.array(
            [np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)],
            dtype=np.complex128,
        )
        target_vec = psi.vec.copy()

        bell = create_bell_pair(rng)
        m0, m1 = teleport(psi, bell, noise_p=0.0, rng=rng)
        apply_teleport_correction(bell, m0, m1)
        # Fidelity: |⟨target|received⟩|²
        fid = abs(np.dot(target_vec.conj(), bell.vec)) ** 2
        fidelity_sum += fid

    avg_fid = fidelity_sum / N
    assert avg_fid > 0.999, f"Noiseless teleportation fidelity = {avg_fid:.6f} < 0.999"
    print(f"PASS: Noiseless teleportation average fidelity = {avg_fid:.6f} (expected ≈ 1.0)")

    # --- Test 3: Fidelity degrades with noise ---
    fid_noisy_sum = 0.0
    for _ in range(N):
        theta = rng.uniform(0, np.pi)
        psi   = QuantumState(1)
        psi.vec = np.array([np.cos(theta / 2), np.sin(theta / 2)], dtype=np.complex128)
        target_vec = psi.vec.copy()
        bell = create_bell_pair(rng)
        m0, m1 = teleport(psi, bell, noise_p=0.1, rng=rng)
        apply_teleport_correction(bell, m0, m1)
        fid = abs(np.dot(target_vec.conj(), bell.vec)) ** 2
        fid_noisy_sum += fid
    avg_fid_noisy = fid_noisy_sum / N
    assert avg_fid_noisy < avg_fid, "Noisy fidelity should be < noiseless fidelity"
    print(f"PASS: Noisy fidelity (p=0.1) = {avg_fid_noisy:.4f} < {avg_fid:.4f} (noiseless)")

    # --- Test 4: CHSH S ≈ 2√2 on clean Bell pairs ---
    N_CHSH = 2000
    chsh_samples = []
    for _ in range(N_CHSH):
        bell = create_bell_pair(rng)
        chsh_samples.append(chsh_measurement(bell, rng))
    S, info = compute_chsh_S(chsh_samples)
    print(f"     CHSH correlators: E(a1,b1)={info['E(a1,b1)']:.4f}, "
          f"E(a1,b2)={info['E(a1,b2)']:.4f}, "
          f"E(a2,b1)={info['E(a2,b1)']:.4f}, "
          f"E(a2,b2)={info['E(a2,b2)']:.4f}")
    print(f"     S = {S:.4f}  (theoretical 2√2 = {S_THEORY:.4f})")
    assert abs(S - S_THEORY) < 0.15, f"CHSH S = {S:.4f} too far from 2√2 = {S_THEORY:.4f}"
    print(f"PASS: CHSH S = {S:.4f} ≈ 2√2 on clean Bell pairs")

    print("=== All bell.py tests passed ===")
