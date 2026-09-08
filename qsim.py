"""
qsim.py — Quantum state-vector simulator core for SIGWATCH.

Pure NumPy, no external quantum SDK.  Big-endian (physics) convention:
qubit 0 is the MOST-significant bit in every basis label.

Index mapping:
    |q0 q1 … q_{n-1}⟩  ↔  index = Σ_k q_k · 2^(n-1-k)

So qubit 0 (MSB) controls the high half of the array.  This means
state.vec.reshape([2]*n): axis k corresponds to qubit k.

Known limitations:
    - Pure-state simulation only (no mixed-state tracking mid-circuit).
    - O(2^n) memory; only suitable for n ≤ ~20 qubits.
    - No parallelism; single-threaded NumPy.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from typing import Optional


# ---------------------------------------------------------------------------
# QuantumState
# ---------------------------------------------------------------------------

class QuantumState:
    """
    N-qubit pure state as a complex128 state vector of length 2^n.

    Convention: big-endian.  qubit 0 → MSB.  See module docstring.
    """

    def __init__(self, n_qubits: int) -> None:
        if n_qubits < 1:
            raise ValueError("n_qubits must be ≥ 1")
        self.n = n_qubits
        self.vec: NDArray[np.complex128] = np.zeros(
            2**n_qubits, dtype=np.complex128
        )
        self.vec[0] = 1.0  # |0…0⟩

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def copy(self) -> "QuantumState":
        s = QuantumState(self.n)
        s.vec = self.vec.copy()
        return s

    def _bit_pos(self, qubit: int) -> int:
        """
        Bit position in the integer index for a given qubit.
        qubit 0 → bit position n-1 (MSB), qubit n-1 → bit position 0 (LSB).
        """
        return self.n - 1 - qubit

    # ------------------------------------------------------------------
    # Single-qubit gate application (in-place)
    # ------------------------------------------------------------------

    def _apply_1q(self, gate: NDArray[np.complex128], qubit: int) -> None:
        """
        Apply a 2×2 unitary *gate* to *qubit* in place.

        Algorithm: iterate over all pairs (i0, i1) that differ only in the
        qubit's bit position, and apply the 2×2 matrix to the amplitude pair.
        """
        bit = self._bit_pos(qubit)
        step = 1 << bit  # 2^bit
        n_states = 1 << self.n  # 2^n
        g00, g01 = gate[0, 0], gate[0, 1]
        g10, g11 = gate[1, 0], gate[1, 1]
        for base in range(0, n_states, step << 1):
            for i in range(base, base + step):
                i0, i1 = i, i + step
                a, b = self.vec[i0], self.vec[i1]
                self.vec[i0] = g00 * a + g01 * b
                self.vec[i1] = g10 * a + g11 * b

    # Standard gates -------------------------------------------------

    _H  = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
    _X  = np.array([[0, 1], [1,  0]], dtype=np.complex128)
    _Y  = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
    _Z  = np.array([[1, 0], [0, -1]], dtype=np.complex128)

    def apply_H(self, qubit: int) -> None:
        """Hadamard gate."""
        self._apply_1q(self._H, qubit)

    def apply_X(self, qubit: int) -> None:
        """Pauli-X (bit-flip) gate."""
        self._apply_1q(self._X, qubit)

    def apply_Y(self, qubit: int) -> None:
        """Pauli-Y gate."""
        self._apply_1q(self._Y, qubit)

    def apply_Z(self, qubit: int) -> None:
        """Pauli-Z (phase-flip) gate."""
        self._apply_1q(self._Z, qubit)

    def apply_RY(self, qubit: int, theta: float) -> None:
        """
        RY(theta) rotation gate.

        RY(θ) = [[cos(θ/2), -sin(θ/2)],
                 [sin(θ/2),  cos(θ/2)]]

        Used for CHSH basis rotations: to measure qubit in basis angle φ
        (in the X-Z plane), apply RY(-φ) then measure Z.
        """
        c, s = np.cos(theta / 2), np.sin(theta / 2)
        gate = np.array([[c, -s], [s, c]], dtype=np.complex128)
        self._apply_1q(gate, qubit)

    def apply_RZ(self, qubit: int, theta: float) -> None:
        """
        RZ(theta) rotation gate.

        RZ(θ) = [[e^{-iθ/2},         0],
                 [        0, e^{+iθ/2}]]
        """
        gate = np.array(
            [[np.exp(-1j * theta / 2), 0],
             [0, np.exp(1j * theta / 2)]],
            dtype=np.complex128,
        )
        self._apply_1q(gate, qubit)

    def apply_gate(self, gate: NDArray[np.complex128], qubit: int) -> None:
        """Apply an arbitrary 2×2 unitary to a single qubit."""
        self._apply_1q(gate, qubit)

    # Two-qubit gate -------------------------------------------------

    def apply_CNOT(self, control: int, target: int) -> None:
        """
        CNOT gate: flip *target* when *control* is |1⟩.

        Correctness argument: we iterate over all indices where the control
        bit is 1 AND the target bit is 0, and swap with the index where the
        target bit is 1 instead.  This avoids double-swapping because each
        pair (i, j) is visited exactly once.
        """
        ctrl_bit = self._bit_pos(control)
        tgt_bit  = self._bit_pos(target)
        ctrl_mask = 1 << ctrl_bit
        tgt_mask  = 1 << tgt_bit
        n_states  = 1 << self.n
        for i in range(n_states):
            if (i & ctrl_mask) and not (i & tgt_mask):
                j = i | tgt_mask          # flip target bit: 0 → 1
                self.vec[i], self.vec[j] = self.vec[j], self.vec[i]

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure(
        self,
        qubit: int,
        rng: Optional[np.random.Generator] = None,
    ) -> int:
        """
        Projective Z-basis measurement of *qubit* (in-place collapse).

        Returns 0 or 1.  Probability of outcome 1 is computed via the
        Born rule: p(1) = Σ_{i: bit_pos set} |vec[i]|².

        Probability is clipped to [0,1] before sampling to guard against
        floating-point drift (see noise.clip_prob).
        """
        if rng is None:
            rng = np.random.default_rng()
        bit   = self._bit_pos(qubit)
        mask  = 1 << bit
        idxs  = np.arange(1 << self.n)
        p1    = float(np.sum(np.abs(self.vec[(idxs & mask) != 0]) ** 2))
        p1    = float(np.clip(p1, 0.0, 1.0))       # guard against drift
        outcome = int(rng.random() < p1)
        # Collapse: zero out amplitudes inconsistent with outcome
        for i in range(1 << self.n):
            if ((i >> bit) & 1) != outcome:
                self.vec[i] = 0.0
        # Renormalize
        norm = np.linalg.norm(self.vec)
        if norm > 1e-12:
            self.vec /= norm
        return outcome

    # ------------------------------------------------------------------
    # Density-matrix utilities
    # ------------------------------------------------------------------

    def density_matrix(self) -> NDArray[np.complex128]:
        """Full 2^n × 2^n density matrix |ψ⟩⟨ψ|."""
        return np.outer(self.vec, self.vec.conj())

    def single_qubit_dm(self, qubit: int) -> NDArray[np.complex128]:
        """
        2×2 reduced density matrix for *qubit*, tracing out all others.

        Algorithm:
          Reshape vec to [2]*n (axis k = qubit k in big-endian order).
          Move qubit axis to front, reshape to (2, 2^{n-1}).
          The reduced DM is then vec_r @ vec_r†, which correctly sums
          over the traced-out degrees of freedom.

        Derivation:
          ρ_q[i,j] = Σ_{others} ψ[…,i,…] ψ*[…,j,…]
                   = (vec_r @ vec_r†)[i,j]   where vec_r[s, others] = ψ[q=s, rest]
        """
        shape = [2] * self.n
        vec_r = self.vec.reshape(shape)
        vec_r = np.moveaxis(vec_r, qubit, 0).reshape(2, -1)
        return vec_r @ vec_r.conj().T


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== qsim.py self-test ===")
    rng = np.random.default_rng(42)

    # --- Test 1: H² = I ---
    s = QuantumState(1)
    s.apply_H(0)
    s.apply_H(0)
    assert np.allclose(s.vec, [1, 0]), f"H²≠I, got {s.vec}"
    print("PASS: H² = I")

    # --- Test 2: CNOT is its own inverse ---
    s = QuantumState(2)
    s.apply_H(0)   # Make |+0⟩
    s.apply_CNOT(0, 1)  # Bell-like state
    before = s.vec.copy()
    s.apply_CNOT(0, 1)  # Invert
    s.apply_H(0)
    assert np.allclose(s.vec, [1, 0, 0, 0]), f"CNOT not self-inverse"
    print("PASS: CNOT is self-inverse")

    # --- Test 3: Born-rule probabilities sum to 1 after each gate in a random circuit ---
    N_STEPS = 200
    s = QuantumState(3)
    for _ in range(N_STEPS):
        choice = rng.integers(0, 6)
        q = int(rng.integers(0, 3))
        if choice == 0: s.apply_H(q)
        elif choice == 1: s.apply_X(q)
        elif choice == 2: s.apply_Y(q)
        elif choice == 3: s.apply_Z(q)
        elif choice == 4: s.apply_RY(q, rng.uniform(0, 2 * np.pi))
        else:
            c, t = rng.choice(3, size=2, replace=False).tolist()
            s.apply_CNOT(c, t)
        norm = np.sum(np.abs(s.vec) ** 2)
        assert abs(norm - 1.0) < 1e-10, f"Born rule violated at step, norm={norm}"
    print(f"PASS: Born-rule norm preserved over {N_STEPS} random gates")

    # --- Test 4: Measurement collapses correctly ---
    # |+⟩ state, measure → ~50% each, but after collapse the probability is exact 0 or 1
    s = QuantumState(1)
    s.apply_H(0)
    outcome = s.measure(0, rng)
    p_check = float(np.sum(np.abs(s.vec[1::2]) ** 2)) if outcome == 1 else float(np.sum(np.abs(s.vec[::2]) ** 2))
    assert abs(p_check - 1.0) < 1e-10, "State not collapsed after measurement"
    print("PASS: Measurement collapses state correctly")

    # --- Test 5: single_qubit_dm traces correctly ---
    # Bell state: qubit 0 should be I/2
    s = QuantumState(2)
    s.apply_H(0)
    s.apply_CNOT(0, 1)
    rho0 = s.single_qubit_dm(0)
    expected = np.eye(2, dtype=np.complex128) / 2
    assert np.allclose(rho0, expected, atol=1e-10), f"Bell pair qubit 0 DM wrong:\n{rho0}"
    print("PASS: single_qubit_dm(0) of Bell pair = I/2")

    # --- Test 6: RY gate identity (RY(0) = I) ---
    s = QuantumState(1)
    s.apply_H(0)
    before = s.vec.copy()
    s.apply_RY(0, 0.0)
    assert np.allclose(s.vec, before), "RY(0) ≠ identity"
    print("PASS: RY(0) = I")

    print("=== All qsim.py tests passed ===")
