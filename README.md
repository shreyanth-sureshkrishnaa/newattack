# SIGWATCH — Quantum Digital Signature Threat Detection Framework

A quantum-inspired, non-machine-learning cyber threat detection framework for teleportation-based Quantum Digital Signature (QDS) protocols.

---

## 1. Architectural Overview

SIGWATCH implements a high-fidelity quantum simulation stack (pure NumPy state-vector physics) combined with closed-form statistical anomaly detectors to identify quantum cyber attacks on quantum digital signature schemes.

```

┌─────────────────────────────────────────────────────────────────────────┐
│                           SIGWATCH ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────────┘
   [Layer 1: qsim.py]       State-Vector Quantum Simulator (Pure NumPy)
   [Layer 2: bell.py]       Bell Pair Generation, CHSH Tests & Teleportation
   [Layer 3: qotp.py]       Quantum One-Time Pad Encryption (X^a Z^b)
   [Layer 4: qds.py]        Teleportation-Based QDS Protocol & Trial Runner
   [Layer 5: noise.py]      Single Canonical Depolarizing Channel & Probability Bounds
   [Layer 6: attacks.py]    Physical Attack Simulators (IR, EH, PF, CBM)
   [Layer 7: detectors.py]  Pure Non-ML Statistical Hypothesis Detectors
   [Layer 8: benchmark.py]  Sweep Suite & Calibration / FPR Validation
   [Layer 9: api.py]        Flask REST API with SSE Real-Time Event Stream
   [Layer 10: dashboard/]   Dark-Themed Live Control Center & Visualization

```

---

## 2. Theoretical Derivations & Mathematical Proofs

### 2.1 Quantum One-Time Pad (QOTP) Information-Theoretic Secrecy
Given a single-qubit state $\rho$ and uniform random key $(a, b) \in \{0, 1\}^2$:
$$\mathcal{E}(\rho) = \frac{1}{4} \sum_{a,b \in \{0,1\}} (X^a Z^b) \rho (X^a Z^b)^\dagger = \frac{1}{4} (\rho + X\rho X + Y\rho Y + Z\rho Z)$$
Using the identity for any $2 \times 2$ density matrix $\rho = \frac{1}{2}(I + \vec{r} \cdot \vec{\sigma})$ where $\sum_{i=1}^3 \sigma_i \rho \sigma_i = 2I - \rho$:
$$\mathcal{E}(\rho) = \frac{1}{4} (\rho + 2I - \rho) = \frac{I}{2}$$
Thus, the ciphertext density matrix is identically maximally mixed ($\text{Tr}(\rho^2) = 0.5$) regardless of plaintext state.

### 2.2 Genuine CHSH Bell Inequality & Tsirelson's Bound
The Clauser-Horne-Shimony-Holt (CHSH) test operates on independent Bell pairs $|\Phi^+\rangle = \frac{|00\rangle + |11\rangle}{\sqrt{2}}$.
Alice and Bob randomly choose measurement bases corresponding to $R_Y(2\theta)$:
- Alice bases: $a_1 = 0^\circ$, $a_2 = 45^\circ$ ($\frac{\pi}{4}$ rad)
- Bob bases: $b_1 = 22.5^\circ$ ($\frac{\pi}{8}$ rad), $b_2 = 67.5^\circ$ ($\frac{3\pi}{8}$ rad)

For angle difference $\theta = \theta_A - \theta_B$:
$$E(a, b) = \langle \Phi^+ | (\sigma_{\theta_A} \otimes \sigma_{\theta_B}) | \Phi^+ \rangle = \cos(2(\theta_A - \theta_B))$$
- $E(a_1, b_1) = \cos(-\frac{\pi}{4}) = +\frac{1}{\sqrt{2}} \approx 0.7071$
- $E(a_1, b_2) = \cos(-\frac{3\pi}{4}) = -\frac{1}{\sqrt{2}} \approx -0.7071$
- $E(a_2, b_1) = \cos(+\frac{\pi}{4}) = +\frac{1}{\sqrt{2}} \approx 0.7071$
- $E(a_2, b_2) = \cos(-\frac{\pi}{4}) = +\frac{1}{\sqrt{2}} \approx 0.7071$

The CHSH correlator evaluates to Tsirelson's quantum bound:
$$S = |E(a_1, b_1) - E(a_1, b_2) + E(a_2, b_1) + E(a_2, b_2)| = \left|\frac{1}{\sqrt{2}} - \left(-\frac{1}{\sqrt{2}}\right) + \frac{1}{\sqrt{2}} + \frac{1}{\sqrt{2}}\right| = 2\sqrt{2} \approx 2.8284$$
Any classical local-hidden-variable model satisfies $S \le 2.0$.

### 2.3 Single-Qubit Depolarizing Channel Trace & Entropy Bounds
The depolarizing channel with parameter $p \in [0, 1]$ is:
$$\mathcal{E}_p(\rho) = (1 - p)\rho + \frac{p}{3}(X\rho X + Y\rho Y + Z\rho Z) = (1 - \frac{4p}{3})\rho + \frac{4p}{3}\frac{I}{2}$$
- At $p = 0$: $\mathcal{E}_0(\rho) = \rho$ (Identity)
- At $p = \frac{3}{4} = 0.75$: $\mathcal{E}_{3/4}(\rho) = \frac{I}{2}$ (Completely mixed state)
- Trace preservation: $\text{Tr}(\mathcal{E}_p(\rho)) = (1-p)\text{Tr}(\rho) + \frac{p}{3}\sum \text{Tr}(\sigma_i \rho \sigma_i) = 1$.

### 2.4 Statistical Hypothesis Testing Without Machine Learning
All detectors are pure deterministic functions evaluated against the null hypothesis $\mathcal{H}_0$:
1. **QBER Z-Score Test**: Under $\mathcal{H}_0$, bit errors follow $\text{Binomial}(N, p_{\text{null}})$. The threshold for false positive rate $\alpha$ is:
   $$\theta_{\text{QBER}} = p_{\text{null}} + z_{1-\alpha} \sqrt{\frac{p_{\text{null}}(1 - p_{\text{null}})}{N}}$$
2. **CHSH Bell Violation Test**: Sample mean $\bar{S}$ under $\mathcal{H}_0$ has standard error $\sigma_S = \frac{2}{\sqrt{N_{\text{pairs}}}}$. Threshold:
   $$\theta_{\text{CHSH}} = \bar{S}_{\text{null}} - z_{1-\alpha} \sigma_S$$
3. **Correction-Bit Pearson $\chi^2$ Test**: The classical measurement pair $(m_0, m_1)$ is uniformly distributed across $\{00, 01, 10, 11\}$ ($p = 0.25$ each, $k=3$ degrees of freedom):
   $$\chi^2 = \sum_{i=1}^4 \frac{(O_i - E_i)^2}{E_i} \sim \chi^2(3)$$
   Alert triggers when $p\text{-value} = 1 - F_{\chi^2(3)}(\chi^2) < \alpha$.

---

## 3. Threat Matrix (SIGWATCH)

| ID | Attack Vector | MITRE ATT&CK Tactic | Physical Channel Modified | Primary Detector | Analytical Effect |
|:---|:---|:---|:---|:---|:---|
| **IR** | Intercept-Resend | Credential Access | `qds_bell`, `chsh_bell` | **QBER & CHSH** | Destroys entanglement; $S \to \sqrt{2} \approx 1.414$, QBER rises to $\approx 25\%$ |
| **EH** | Entanglement Hijacking | Lateral Movement | `qds_bell`, `chsh_bell` | **CHSH** | Replaces Bell pair with separable state; $S \to 0$, strong CHSH alert |
| **PF** | Pauli Forgery | Impact / Tampering | `payload` | **PauliConsistency & QBER** | Applies $X$ to signature qubit; bit flip error rate rises without affecting CHSH $S$ |
| **CBM** | Correction Bit Manipulation | Classical Injection | `correction` | **CorrBitUniformity** | Inverts $(m_0, m_1)$ bits; skewing $(1,1)$ frequency causing high $\chi^2$ divergence |

---

## 4. Known Limitations & Honest Scope

1. **Noise Realism**: Only single-qubit isotropic depolarizing noise is modeled. Amplitude damping ($T_1$), phase damping ($T_2$), and cross-talk noise are not simulated.
2. **Side-Channels & Device Imperfections**: Detector dark counts, detector efficiency mismatch, and pulse-timing side channels are outside the scope of this model.
3. **Multi-Party Non-Repudiation**: The current protocol simulates single-signer to single-verifier verification. Full 3-party asymmetric QDS arbitrated broadcast (Alice, Bob, Charlie) is simplified to the core teleportation-QOTP primitive.

---

## 5. Quickstart & Usage

### 5.1 Run Self-Tests
Verify all 7 physics and statistical layers:
```bash
uv run python runner.py test
```

### 5.2 Execute Benchmark Parameter Sweep
Run the complete multi-channel intensity sweep (84 cells across noise and attack configurations):
```bash
uv run python runner.py benchmark
```

### 5.3 Launch the Interactive Live Dashboard
Start the REST API server and open the web dashboard:
```bash
uv run python runner.py serve --port 5050
```
Open your browser at `http://localhost:5050` to interact with:
- Live injection controls (attack vector, intensity slider $\eta \in [0, 1]$, physical noise level $p$).
- Real-time QBER and CHSH streaming charts.
- Dynamic threshold adjustment sliders with live updates via `PUT /api/config`.
- Mapped Threat Matrix with MITRE tactics.
