"""
api.py — Flask REST API for Q-ATT&CK.

Endpoints:
  POST /api/run          — run a batch of trials, returns logs + alerts
  GET  /api/alerts       — current alert feed
  GET  /api/config       — current DetectorConfig (all thresholds)
  PUT  /api/config       — update DetectorConfig thresholds live
  GET  /api/threat-matrix — static threat matrix
  GET  /api/benchmark    — benchmark results JSON
  GET  /api/stream       — SSE stream of live batch results
  GET  /api/status       — server health check

Thread safety: a threading.Lock protects all shared state.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS

from attacks import ATTACK_MAKERS, make_ir_attack, make_eh_attack, make_pf_attack, make_cbm_attack
from benchmark import RESULTS_FILE, load_results
from detectors import Alert, DetectorConfig, run_all_detectors, summarize
from qds import run_batch

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).parent / "dashboard"
app = Flask(__name__, static_folder=str(DASHBOARD_DIR), static_url_path="")
CORS(app)

# ---------------------------------------------------------------------------
# Shared state (protected by _lock)
# ---------------------------------------------------------------------------

_lock           = threading.Lock()
_config         = DetectorConfig()
_alert_feed:    List[Dict] = []
_trial_counter: int = 0
_sse_queue:     queue.Queue = queue.Queue(maxsize=200)

# Global RNG — re-seeded from request params when explicit seed is given
_rng = np.random.default_rng()

ATTACK_MAKER_MAP = {
    "IR":  make_ir_attack,
    "EH":  make_eh_attack,
    "PF":  make_pf_attack,
    "CBM": make_cbm_attack,
}


# ---------------------------------------------------------------------------
# Static threat matrix (informational)
# ---------------------------------------------------------------------------

THREAT_MATRIX = [
    {
        "id": "IR",
        "name": "Intercept-Resend",
        "tactic": "Credential Access",
        "technique": "Quantum Channel Interception",
        "severity": "HIGH",
        "description": (
            "Eve intercepts Bob's qubit, measures in a random basis, "
            "and re-sends a fresh qubit. Destroys entanglement."
        ),
        "channels": ["qds_bell", "chsh_bell"],
        "detectors": ["QBER", "CHSH"],
        "mitigation": "Monitor CHSH S-value and QBER; flag when S < 2√2 − 3σ.",
    },
    {
        "id": "EH",
        "name": "Entanglement Hijacking",
        "tactic": "Lateral Movement",
        "technique": "Bell Pair Substitution",
        "severity": "HIGH",
        "description": (
            "Eve replaces Bob's half of the Bell pair with an independent "
            "qubit, completely severing entanglement."
        ),
        "channels": ["qds_bell", "chsh_bell"],
        "detectors": ["CHSH", "QBER"],
        "mitigation": "CHSH S drops sharply to ≈ 0. Strong CHSH alert.",
    },
    {
        "id": "PF",
        "name": "Pauli Forgery",
        "tactic": "Impact",
        "technique": "Signature Qubit Manipulation",
        "severity": "MEDIUM",
        "description": (
            "Eve applies Pauli X to the QOTP-encrypted signature qubit, "
            "attempting to forge the signed message bit."
        ),
        "channels": ["payload"],
        "detectors": ["QBER", "PauliConsistency"],
        "mitigation": "Monitor Pauli error asymmetry; X-errors dominate under forgery.",
    },
    {
        "id": "CBM",
        "name": "Correction Bit Manipulation",
        "tactic": "Tampering",
        "technique": "Classical Channel Injection",
        "severity": "MEDIUM",
        "description": (
            "Eve modifies the classical teleportation correction bits (m0, m1), "
            "causing Bob to apply the wrong correction."
        ),
        "channels": ["correction"],
        "detectors": ["CorrBitUniformity"],
        "mitigation": "Monitor correction-bit distribution; (1,1) should not be over-represented.",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _push_sse(data: Dict) -> None:
    """Push data to the SSE queue (non-blocking; drops if full)."""
    try:
        _sse_queue.put_nowait(data)
    except queue.Full:
        pass  # Dashboard is slow; drop rather than block


def _alert_to_dict(a: Alert) -> Dict:
    return {
        "trial_batch_end": a.trial_batch_end,
        "detector": a.detector,
        "severity": a.severity,
        "value": a.value,
        "threshold": a.threshold,
        "message": a.message,
        "ts": time.time(),
    }


def _config_to_dict(cfg: DetectorConfig) -> Dict:
    return {
        "qber_null": cfg.qber_null,
        "qber_alpha": cfg.qber_alpha,
        "qber_min_trials": cfg.qber_min_trials,
        "chsh_alpha": cfg.chsh_alpha,
        "chsh_min_samples": cfg.chsh_min_samples,
        "pauli_alpha": cfg.pauli_alpha,
        "pauli_min_errors": cfg.pauli_min_errors,
        "corr_alpha": cfg.corr_alpha,
        "corr_min_trials": cfg.corr_min_trials,
    }


def _dict_to_config(d: Dict, base: DetectorConfig) -> DetectorConfig:
    cfg = DetectorConfig(
        qber_null=d.get("qber_null", base.qber_null),
        qber_alpha=d.get("qber_alpha", base.qber_alpha),
        qber_min_trials=int(d.get("qber_min_trials", base.qber_min_trials)),
        chsh_alpha=d.get("chsh_alpha", base.chsh_alpha),
        chsh_min_samples=int(d.get("chsh_min_samples", base.chsh_min_samples)),
        pauli_alpha=d.get("pauli_alpha", base.pauli_alpha),
        pauli_min_errors=int(d.get("pauli_min_errors", base.pauli_min_errors)),
        corr_alpha=d.get("corr_alpha", base.corr_alpha),
        corr_min_trials=int(d.get("corr_min_trials", base.corr_min_trials)),
    )
    return cfg


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(DASHBOARD_DIR), "index.html")


@app.route("/api/status")
def status():
    return jsonify({"status": "ok", "ts": time.time()})


@app.route("/api/run", methods=["POST"])
def run_trials():
    """
    Run a batch of QDS trials.

    Body (JSON):
        n_trials     int    (default 100)
        attack_type  str    "clean"|"IR"|"EH"|"PF"|"CBM" (default "clean")
        intensity    float  0.0–1.0 (default 0.5)
        noise_level  float  0.0–0.15 (default 0.02)
        seed         int    optional RNG seed
    """
    global _trial_counter, _rng

    body = request.get_json(silent=True) or {}
    n_trials    = max(1, min(int(body.get("n_trials", 100)), 2000))
    attack_type = body.get("attack_type", "clean")
    intensity   = float(np.clip(body.get("intensity", 0.5), 0.0, 1.0))
    noise_level = float(np.clip(body.get("noise_level", 0.02), 0.0, 0.3))
    seed        = body.get("seed")

    if seed is not None:
        local_rng = np.random.default_rng(int(seed))
    else:
        with _lock:
            local_rng = _rng

    attack_fn = None
    if attack_type in ATTACK_MAKER_MAP:
        attack_fn = ATTACK_MAKER_MAP[attack_type](intensity)

    try:
        with _lock:
            start_id = _trial_counter
        logs = run_batch(
            n_trials, noise_p=noise_level, rng=local_rng,
            attack_fn=attack_fn, attack_type=attack_type,
            intensity=intensity, start_id=start_id,
        )
        with _lock:
            _trial_counter += n_trials
            cfg_snapshot = DetectorConfig(
                qber_null=_config.qber_null,
                qber_alpha=_config.qber_alpha,
                qber_min_trials=_config.qber_min_trials,
                chsh_alpha=_config.chsh_alpha,
                chsh_min_samples=_config.chsh_min_samples,
                pauli_alpha=_config.pauli_alpha,
                pauli_min_errors=_config.pauli_min_errors,
                corr_alpha=_config.corr_alpha,
                corr_min_trials=_config.corr_min_trials,
            )

        summ = summarize(logs, cfg_snapshot)
        new_alerts = [Alert(**a) for a in summ["alerts"]]

        with _lock:
            for a in new_alerts:
                _alert_feed.append(_alert_to_dict(a))
            if len(_alert_feed) > 500:
                _alert_feed[:] = _alert_feed[-500:]

        # Build per-trial data for dashboard charts (lightweight)
        trial_data = [
            {
                "id": l.trial_id,
                "is_error": l.is_error,
                "chsh_a_angle": round(l.chsh_alice_angle, 4),
                "chsh_b_angle": round(l.chsh_bob_angle, 4),
                "chsh_a_sign": l.chsh_alice_sign,
                "chsh_b_sign": l.chsh_bob_sign,
                "m0": l.correction_m0,
                "m1": l.correction_m1,
                "pauli": l.pauli_error_type,
            }
            for l in logs
        ]

        result = {
            "batch_summary": summ,
            "alerts": [_alert_to_dict(a) for a in new_alerts],
            "trials": trial_data,
        }

        _push_sse({"type": "batch", "data": result})
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/alerts")
def get_alerts():
    with _lock:
        feed = list(_alert_feed)
    limit = int(request.args.get("limit", 100))
    return jsonify({"alerts": feed[-limit:]})


@app.route("/api/alerts/clear", methods=["POST"])
def clear_alerts():
    with _lock:
        _alert_feed.clear()
    return jsonify({"status": "cleared"})


@app.route("/api/config", methods=["GET"])
def get_config():
    with _lock:
        cfg = _config_to_dict(_config)
    return jsonify(cfg)


@app.route("/api/config", methods=["PUT"])
def set_config():
    global _config
    body = request.get_json(silent=True) or {}
    with _lock:
        _config = _dict_to_config(body, _config)
        cfg = _config_to_dict(_config)
    _push_sse({"type": "config_update", "data": cfg})
    return jsonify(cfg)


@app.route("/api/threat-matrix")
def threat_matrix():
    return jsonify({"threats": THREAT_MATRIX})


@app.route("/api/benchmark")
def benchmark():
    data = load_results()
    if data is None:
        return jsonify({"error": "Benchmark not run yet. Run benchmark.py first."}), 404
    return jsonify(data)


@app.route("/api/stream")
def sse_stream():
    """Server-Sent Events endpoint for live dashboard updates."""
    def generate():
        yield "data: {\"type\":\"connected\"}\n\n"
        while True:
            try:
                item = _sse_queue.get(timeout=25)
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"  # keep-alive comment

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
    print(f"Q-ATT&CK API server starting on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
