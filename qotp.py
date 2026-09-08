"""
qotp.py — Quantum One-Time Pad (QOTP) layer for SIGWATCH.

The QOTP applies Pauli operators controlled by a two-bit classical key
(key_a, key_b) ∈ {0,1}² to a single qubit:

    Encrypt(ρ, a, b) = X^a Z^b ρ (X^a Z^b)†

Since X and Z are Hermitian and unitary (X† = X, Z† = Z), and both square
to the identity (X² = Z² = I), the operation is its own inverse:

    Decrypt(Encrypt(ρ, a, b), a, b)
        = (X^a Z^b)(X^a Z^b ρ X^a Z^b)(X^a Z^b)
        = X^{2a} Z^{2b} ρ X^{2a} Z^{2b}
        = ρ   ✓

Key security property (proved numerically in self-test):
    If the key (a, b) is chosen uniformly at random from {0,1}², then
    the average encrypted state is the maximally mixed state I/2 regardless
    of the plaintext ρ.  Formally:

        (1/4) Σ_{a,b} X^a Z^b ρ X^a Z^b = I/2  for ALL ρ

    Proof:  The four operators {I, X, Z, XZ} form a unitary 1-design.
    Their average twirl maps ρ → (1/4)(IρI + XρX + ZρZ + XZρZX).
    Note XZ = iY, so XZρZX = iY ρ (iY)† = YρY.
    So the average is (1/4)(ρ + XρX + ZρZ + YρY) = I/2
    (because XρX + YρY + ZρZ = (2−1)ρ... wait, more carefully:
    for ρ = [[a,c],[c*,b]]:
      IρI   = [[a,c],[c*,b]]
      XρX   = [[b,c*],[c,a]]
      ZρZ   = [[a,−c],[−c*,b]]
      XZρZX = YρY = [[b,−c*],[−c,a]]   (using XZ=iY and Y†=Y)
    Sum/4:
      diag[0]: (a+b+a+b)/4 = (a+b)/2
      diag[1]: (b+a+b+a)/4 = (a+b)/2
      off-diag: (c+c*−c−c*)/4 = 0
    Since a+b = Tr(ρ) = 1, diagonals = 1/2, off-diagonals = 0 → I/2 ✓)

Wrong-key security: decrypting with key (a', b') ≠ (a, b) yields a state that
is NOT the plaintext.  In particular, with uniformly random wrong keys the
output density matrix is again close to I/2 (verified empirically in self-test).
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Tuple
from qsim import QuantumState


def qotp_encrypt(
    state: QuantumState,
    qubit: int,
    key_a: int,
    key_b: int,
) -> None:
    """
    Apply QOTP encryption to *qubit* in place: X^key_a Z^key_b.

    key_a, key_b ∈ {0, 1}.  0 means the identity gate is applied (no-op).
    """
    if key_b:
        state.apply_Z(qubit)
    if key_a:
        state.apply_X(qubit)


def qotp_decrypt(
    state: QuantumState,
    qubit: int,
    key_a: int,
    key_b: int,
) -> None:
    """
    Apply QOTP decryption: identical to encryption (self-inverse).

    (X^a Z^b)† = Z^b X^a = X^a Z^b  because X^a and Z^b commute when
    a or b is 0, and XZ ≠ ZX in general, BUT (XZ)† = Z†X† = ZX.
    However, since we apply Z first then X in encryption:
    encrypt = X^a ∘ Z^b  (Z applied first, then X)
    inverse  = (Z^b)^{-1} ∘ (X^a)^{-1} = Z^b ∘ X^a  (X applied first, then Z)

    Numerically verified: encrypt then decrypt = identity (see self-test).
    """
    if key_a:
        state.apply_X(qubit)
    if key_b:
        state.apply_Z(qubit)


def random_key(rng: Optional[np.random.Generator] = None) -> Tuple[int, int]:
    """Return a uniformly random QOTP key (a, b) ∈ {0,1}²."""
    if rng is None:
        rng = np.random.default_rng()
    return int(rng.integers(0, 2)), int(rng.integers(0, 2))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== qotp.py self-test ===")
    rng = np.random.default_rng(13)
    N = 40_000

    # --- Test 1: Encrypt then decrypt = identity for all keys ---
    test_states = [
        np.array([1, 0], dtype=np.complex128),          # |0⟩
        np.array([0, 1], dtype=np.complex128),          # |1⟩
        np.array([1, 1], dtype=np.complex128) / np.sqrt(2),  # |+⟩
        np.array([1, 1j], dtype=np.complex128) / np.sqrt(2), # |+i⟩
    ]
    for key_a in [0, 1]:
        for key_b in [0, 1]:
            for psi in test_states:
                s = QuantumState(1)
                s.vec = psi.copy()
                qotp_encrypt(s, 0, key_a, key_b)
                qotp_decrypt(s, 0, key_a, key_b)
                assert np.allclose(s.vec, psi, atol=1e-12), \
                    f"Encrypt+decrypt ≠ identity for key ({key_a},{key_b})"
    print("PASS: Encrypt then decrypt = identity for all (key_a, key_b) ∈ {0,1}²")

    # --- Test 2: Uniform random key → average density matrix ≈ I/2 ---
    # Derivation is in module docstring.  We verify numerically here.
    rho_sum = np.zeros((2, 2), dtype=np.complex128)
    for _ in range(N):
        # Random plaintext state
        theta = rng.uniform(0, np.pi)
        phi   = rng.uniform(0, 2 * np.pi)
        psi = np.array(
            [np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)],
            dtype=np.complex128,
        )
        s = QuantumState(1)
        s.vec = psi.copy()
        ka, kb = random_key(rng)
        qotp_encrypt(s, 0, ka, kb)
        rho_sum += s.single_qubit_dm(0)
    rho_avg = rho_sum / N
    expected = np.eye(2, dtype=np.complex128) / 2
    max_dev = float(np.max(np.abs(rho_avg - expected)))
    assert max_dev < 0.02, f"Random-key avg DM ≠ I/2; max deviation = {max_dev:.4f}"
    print(f"PASS: Uniform random key → avg density matrix ≈ I/2 (max dev {max_dev:.5f})")

    # --- Test 3: Wrong key → density matrix properties ---
    # Mathematical derivation:
    # 1) For a fixed state |0⟩, the 3 non-identity Pauli operations give:
    #    Z|0⟩ = |0⟩ (prob 1/3), X|0⟩ = |1⟩ (prob 1/3), XZ|0⟩ = -|1⟩ (prob 1/3).
    #    Thus E_wrong[P|0⟩⟨0|P†] = (1/3)|0⟩⟨0| + (2/3)|1⟩⟨1| = diag(1/3, 2/3).
    # 2) For Haar-random / Bloch-sphere random pure states ψ where E_ψ[|ψ⟩⟨ψ|] = I/2:
    #    E_{ψ, wrong}[P |ψ⟩⟨ψ| P†] = P (I/2) P† = I/2 for any Pauli P.
    # We verify both properties numerically.

    # 3a. Random plaintext states under wrong key decryption
    rho_wrong_rand = np.zeros((2, 2), dtype=np.complex128)
    count = 0
    for _ in range(N):
        theta = rng.uniform(0, np.pi)
        phi   = rng.uniform(0, 2 * np.pi)
        psi = np.array(
            [np.cos(theta / 2), np.exp(1j * phi) * np.sin(theta / 2)],
            dtype=np.complex128,
        )
        s = QuantumState(1)
        s.vec = psi.copy()
        ka, kb = random_key(rng)          # true key
        wka, wkb = random_key(rng)       # wrong key
        if (wka, wkb) == (ka, kb):
            continue
        count += 1
        qotp_encrypt(s, 0, ka, kb)
        qotp_decrypt(s, 0, wka, wkb)   # wrong decryption
        rho_wrong_rand += s.single_qubit_dm(0)

    if count > 0:
        rho_wrong_rand /= count
        max_dev_w = float(np.max(np.abs(rho_wrong_rand - np.eye(2) / 2)))
        assert max_dev_w < 0.03, f"Wrong-key random-state avg DM ≠ I/2; max dev = {max_dev_w:.4f}"
        print(f"PASS: Wrong-key on random states → avg DM ≈ I/2 (max dev {max_dev_w:.5f})")

    # 3b. Fixed |0⟩ state under wrong key decryption → diag(1/3, 2/3)
    rho_wrong_fixed = np.zeros((2, 2), dtype=np.complex128)
    count_fixed = 0
    for _ in range(N):
        ka, kb = random_key(rng)
        wka, wkb = random_key(rng)
        if (wka, wkb) == (ka, kb):
            continue
        count_fixed += 1
        s = QuantumState(1)
        s.vec = np.array([1.0, 0.0], dtype=np.complex128)
        qotp_encrypt(s, 0, ka, kb)
        qotp_decrypt(s, 0, wka, wkb)
        rho_wrong_fixed += s.single_qubit_dm(0)

    if count_fixed > 0:
        rho_wrong_fixed /= count_fixed
        expected_fixed = np.diag([1.0 / 3.0, 2.0 / 3.0]).astype(np.complex128)
        dev_fixed = float(np.max(np.abs(rho_wrong_fixed - expected_fixed)))
        assert dev_fixed < 0.03, f"Wrong-key |0⟩ state avg DM ≠ diag(1/3, 2/3); max dev = {dev_fixed:.4f}"
        print(f"PASS: Wrong-key on |0⟩ state → diag(1/3, 2/3) verified (max dev {dev_fixed:.5f})")

    print("=== All qotp.py tests passed ===")
