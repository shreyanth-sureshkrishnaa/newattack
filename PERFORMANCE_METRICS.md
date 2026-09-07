# Q-ATT&CK Simulation Speed & Performance Benchmark

**Benchmark Date:** September 2026  
**Execution Environment:** Linux x86_64, Python 3.14.7, NumPy 2.5.3, SciPy 1.18.1  
**Architecture:** Pure State-Vector Quantum Simulation (Big-Endian Vector Physics)  

---

## 1. Executive Performance Summary

- **End-to-End Trial Throughput:** **~3,605 quantum trials / second** (277.40 µs per complete signed trial).
- **Quantum Teleportation Circuit:** **124.70 µs** per 3-qubit teleportation + correction cycle.
- **Statistical Anomaly Evaluation:** **11514.31 µs** for full hypothesis testing over a batch of 2,000 trials (**87 detector evaluations / sec**).
- **Zero JIT / Pure Python Overhead:** Native NumPy complex128 vector projections with zero ML model inference lag.
---

## 2. Quantum Layer Micro-Latencies

Evaluation of isolated quantum operations across 5,000 continuous iterations:

| Quantum Simulation Layer | Primary Primitive | Latency (µs / op) | Ops / Second |
|:---|:---|:---:|:---:|
| **Layer 1: Quantum Simulator Core (`qsim.py`)** | 3-Qubit Alloc + H Gate + CNOT + Measure | **30.47 µs** | **32,817 ops/s** |
| **Layer 2: Bell Pair & CHSH (`bell.py`)** | $|\Phi^+\rangle$ Pair Alloc + Random-Basis CHSH | **89.80 µs** | **11,136 ops/s** |
| **Layer 3: Quantum One-Time Pad (`qotp.py`)** | Uniform Key Gen + Encrypt ($X^a Z^b$) + Decrypt | **9.33 µs** | **107,208 ops/s** |
| **Layer 4: Full Teleportation Circuit (`qds.py`)** | Alice Bell Measurement + Classical ($m_0, m_1$) + Bob Pauli Correction | **124.70 µs** | **8,019 ops/s** |
| **Layer 5: Depolarizing Noise Channel (`noise.py`)** | 2-Qubit Isotropic Depolarizing Channel | **7.46 µs** | **134,092 ops/s** |

---

## 3. End-to-End Batch Scaling & Throughput

Execution of complete 4-channel QDS protocol runs (Key Generation $\to$ Encryption $\to$ Distribution $\to$ Teleportation $\to$ Correction $\to$ Decryption $\to$ CHSH Bell Evaluation):

| Batch Sample Size ($N$) | Total Execution Time | Single-Trial Latency | Real-Time Simulation Throughput |
|:---:|:---:|:---:|:---:|
| **100 trials** | 35.22 ms | **352.23 µs / trial** | **2,839 trials / sec** |
| **500 trials** | 150.39 ms | **300.77 µs / trial** | **3,325 trials / sec** |
| **1,000 trials** | 277.40 ms | **277.40 µs / trial** | **3,605 trials / sec** |
| **2,500 trials** | 698.98 ms | **279.59 µs / trial** | **3,577 trials / sec** |
| **5,000 trials** | 1326.36 ms | **265.27 µs / trial** | **3,770 trials / sec** |
| **10,000 trials** | 2634.12 ms | **263.41 µs / trial** | **3,796 trials / sec** |

---

## 4. Adversarial Attack Simulation Overheads

Comparison of execution overhead across attack vector hooks at batch size $N = 2,000$ (Intensity $\eta = 0.80$):

| Attack Simulation Vector | Modified Physical Channel | Execution Time (2,000 Trials) | Trial Latency | Throughput |
|:---|:---|:---:|:---:|:---:|
| **Clean Baseline** | Physical Hook | 527.87 ms | **263.93 µs** | **3,789 trials/s** |
| **Intercept-Resend (IR)** | Physical Hook | 611.15 ms | **305.57 µs** | **3,273 trials/s** |
| **Entanglement Hijacking (EH)** | Physical Hook | 725.88 ms | **362.94 µs** | **2,755 trials/s** |
| **Pauli Forgery (PF)** | Physical Hook | 545.70 ms | **272.85 µs** | **3,665 trials/s** |
| **Correction Bit Manipulation (CBM)** | Physical Hook | 520.75 ms | **260.38 µs** | **3,841 trials/s** |

---

## 5. Statistical Hypothesis Detector Latency

Latency of non-ML statistical decision engine (Gaussian Z-score QBER + CHSH Bell violation + Pearson $\chi^2$ correction uniformity + Pauli asymmetry) on batch of $N = 2,000$ trials:

| Metric | Measured Latency |
|:---|:---:|
| **Median Latency (p50)** | **11514.31 µs** |
| **Mean Latency** | **12261.53 µs** |
| **95th Percentile (p95)** | **17352.36 µs** |
| **99th Percentile (p99)** | **20427.62 µs** |
| **Detector Evaluation Rate** | **87 full evaluations / second** |

---

## 6. Memory & Algorithmic Complexity

- **State Vector Representation:** $2^n$ complex128 array ($n=3 \implies 8 \times 16 = 128$ bytes per state vector).
- **Transient Memory Footprint:** $< 12$ MB working memory under full 10,000 trial continuous batch execution.
- **Space Complexity:** $\mathcal{O}(1)$ per quantum trial (instantaneous garbage collection and vector recycling).
- **Time Complexity:** $\mathcal{O}(N)$ linear scaling with sample size $N$, with zero quadratic overhead.

---

*Report automatically verified and printed by `perf_benchmark.py`.*
