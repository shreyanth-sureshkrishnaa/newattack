# Q-ATT&CK — Live Demonstration Guide & Presentation Script

This guide outlines a step-by-step walkthrough to demonstrate the **Q-ATT&CK** Quantum Cyber Threat Detection Workbench to quantum physicists, cryptographers, and cybersecurity evaluators.

---

## 1. Quick Launch Checklist

Ensure the server is running on port 5055 (or 5050):
```bash
# Terminal 1: Start API server & Scientific Workbench
uv run python runner.py serve --port 5055
```
Open **`http://localhost:5055`** in your browser.

---

## 2. 5-Minute Demonstration Script

### Scene 1: The Elevator Pitch (30 seconds)
> *"Welcome to Q-ATT&CK. Quantum Digital Signatures (QDS) provide information-theoretic non-repudiation and integrity using quantum teleportation and Quantum One-Time Pads. However, when deployed over optical fiber channels, how do we distinguish benign physical noise from active adversarial tampering without relying on opaque machine learning? Q-ATT&CK is a non-ML, physics-grounded cyber threat detection workbench with closed-form statistical hypothesis testing."*

---

### Scene 2: Baseline State — The Physics of Clean Teleportation (45 seconds)
1. In the **Simulation Console** (Tab 1), select:
   - **Target Threat Vector**: `Clean Traffic (Null Hypothesis H₀)`
   - **Batch Sample Size**: `250`
   - **Depolarizing Noise ($p_{\text{noise}}$)**: `0.020`
2. Click **`Execute Quantum Trial Batch`**.
3. **What to Point Out**:
   - **QBER ($\hat{Q}$)**: Hovers around $\approx 2.0\%-3.5\%$, safely below the Gaussian Z-score threshold.
   - **CHSH Parameter ($S$)**: Evaluates to $S \approx 2.80 > 2.0$, clearly demonstrating Tsirelson's bound ($2\sqrt{2} \approx 2.828$) and proving non-local quantum entanglement across the channel.
   - **Alert Feed**: Shows *zero false alarms* ($\text{FPR} \le \alpha = 1\%$).

---

### Scene 3: Attack Scenario A — Intercept-Resend (IR) Attack (1 minute)
1. Change **Target Threat Vector** to: `Intercept-Resend Attack (IR)`.
2. Set **Attack Intensity ($\eta$)** to `0.80`.
3. Click **`Execute Quantum Trial Batch`**.
4. **What to Point Out**:
   - **CHSH Collapse**: Watch the $S$-curve instantly plunge below the classical Bell bound ($S < 2.0$, dropping to $\approx 1.50$). This proves Eve's measurement collapsed the entangled Bell state into an unentangled separable mixture.
   - **QBER Surge**: Error rate jumps to $\approx 20\%-25\%$.
   - **Alarms Raised**: Live alert cards trigger immediately from both the `CHSH` and `QBER` hypothesis tests.

---

### Scene 4: Attack Scenario B — Pauli Forgery (PF) on Payload Channel (1 minute)
1. Change **Target Threat Vector** to: `Pauli Forgery (PF)`.
2. Set **Intensity ($\eta$)** to `0.70`.
3. Click **`Execute Batch`**.
4. Click on Graph Tab **`2. Channel Correlators & Pauli Syndromes`**:
5. **What to Point Out (Crucial Physics Insight)**:
   - **Strict Channel Isolation**: Look at the **CHSH Correlators $E(a_i, b_j)$** and $S$-parameter — *CHSH remains completely unaffected ($S \approx 2.80$)* because Eve only touched the QOTP signature payload!
   - Look at the **Pauli Error Syndrome Breakdown**: Bit-flip errors ($X$) dramatically spike.
   - The framework accurately isolates that this is an impact/tampering attack on Alice's ciphertext, not an entanglement breach.

---

### Scene 5: Attack Scenario C — Classical Correction Bit Manipulation (CBM) (45 seconds)
1. Select **Target Threat Vector**: `Correction Bit Manipulation (CBM)` at $\eta = 0.80$.
2. Click **`Execute Batch`**.
3. Click on Graph Tab **`3. Correction Bit Uniformity (χ² Test)`**:
4. **What to Point Out**:
   - Legitimate teleportation demands that measurement outcomes $\{00, 01, 10, 11\}$ appear uniformly with probability $p = 0.25$.
   - Under CBM, the distribution skews heavily towards $(1, 1)$, triggering the Pearson $\chi^2$ detector ($p\text{-value} < 10^{-6}$) with zero impact on Bell entanglement.

---

### Scene 6: Live Dynamic Threshold Tuning (30 seconds)
1. In the **Significance Bounds (α)** strip at the top, drag the **QBER α** slider from `0.010` up to `0.080` (tightening the detection sensitivity) or down to `0.001` (loosening it).
2. **What to Point Out**:
   - Thresholds are updated live via the REST API (`PUT /api/config`) and push updates via Server-Sent Events (SSE).
   - Because all detectors are exact statistical integrals (Gaussian CDF and $\chi^2$ CDF), changing $\alpha$ guarantees mathematically bounded false alarm rates without retraining.

---

### Scene 7: Raw Telemetry & Empirical Benchmarks (30 seconds)
1. Click on Graph Tab **`4. Benchmark Sweep & Noise Physics`**:
   - Show the 84-cell parameter sweep curves: Detection probability $P_D(\eta)$ vs continuous intensity $\eta \in [0.0, 1.0]$.
   - Point out the analytical noise degradation curves for QBER $Q(p) = 2p/3$ and CHSH $S(p) = 2\sqrt{2}(1 - 4p/3)$.
2. Click on Graph Tab **`5. Raw Quantum Trial Inspector`**:
   - Show how evaluators can inspect individual quantum trials, viewing Alice's message $m$, Bob's received bit, QOTP keys $(a,b)$, correction bits $(m_0, m_1)$, CHSH measurement angles, and ground-truth Pauli syndromes.
   - Filter by *Bit Errors Only* or *Valid Signatures Only* to inspect intercepted trials in real-time.
