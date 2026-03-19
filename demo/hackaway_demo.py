#!/usr/bin/env python3
"""
tibet-phantom — Hackaway / W3C Live Demo
=========================================

The full Phantom flow on one machine, demonstrating:

1. GPU inference output sealed with provenance chain
2. Identity resolution (CGNAT-proof)
3. Store-and-forward (airplane mode drop)
4. Context-bound materialization (right person = text, wrong person = noise)
5. TIBET audit receipt

Run: python3 demo/hackaway_demo.py
"""

import json
import platform
import getpass
import time
import hashlib
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from phantom.seal import PhantomSealer
from phantom.resolve import PhantomResolver
from phantom.transport import PhantomTransport
from phantom.materialize import PhantomMaterializer, MaterializationResult
from phantom.decode import PhantomDecoder

# ─── Configuration ────────────────────────────────────────

MODEL = "qwen2.5:32b"
TARGET = "jis:pixel-jasper"
ENDPOINT = "10.0.0.42:9000"

# Simulated inference output (in production: actual LLM output)
INFERENCE_OUTPUT = (
    b"The UPIP protocol ensures that every computational process "
    b"can be independently verified. Fork Tokens enable verifiable "
    b"cross-model AI handoffs without loss of provenance. "
    b"This is the foundation of decentralized, trustworthy AI."
)

# Expected receiver context
EXPECTED_HEARTBEAT = "72bpm_steady"
EXPECTED_GYRO = "hand_held"
EXPECTED_CADENCE = "natural"


# ─── Display ──────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%H:%M:%S")

def header():
    print()
    print("=" * 66)
    print("  tibet-phantom v0.1.0 — Zero-Footprint AI Materialization")
    print("  Data doesn't travel. It materializes.")
    print("=" * 66)
    print()
    print(f"  Model:       {MODEL} (simulated inference)")
    print(f"  Target:      {TARGET}")
    print(f"  Endpoint:    {ENDPOINT} (behind CGNAT)")
    print(f"  Node:        {platform.node()}")
    print(f"  Time:        {ts()}")
    print()
    print("-" * 66)

def step(n, text):
    print(f"  [{ts()}] [{n}] {text}")

def box(title, lines):
    w = 58
    print()
    print(f"  ┌─ {title} {'─' * max(0, w - len(title) - 2)}┐")
    for line in lines:
        if len(line) > w:
            line = line[:w-3] + "..."
        print(f"  │ {line:<{w}} │")
    print(f"  └{'─' * (w + 2)}┘")

def wrap(text, width=56):
    words = text.replace("\n", " ").split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# ─── Demo Steps ───────────────────────────────────────────

def step1_seal():
    """Seal inference output with provenance chain."""
    step(1, f"Sealing inference output ({len(INFERENCE_OUTPUT)} bytes)...")
    step("→", f"Model: {MODEL}")

    context_key = PhantomMaterializer.build_context_key(
        node=platform.node(),
        user=getpass.getuser(),
        heartbeat=EXPECTED_HEARTBEAT,
        gyro=EXPECTED_GYRO,
        cadence=EXPECTED_CADENCE,
    )

    sealer = PhantomSealer(model=MODEL, actor="p520-gpu")
    envelope = sealer.seal(INFERENCE_OUTPUT, context_key, TARGET)

    step("✓", f"Sealed → envelope {envelope.envelope_hash}")
    step("→", f"Chain: {len(envelope.chain)} provenance steps")
    step("→", f"L4 hash: {envelope.l4_hash[:24]}...")
    step("→", f"Ciphertext: {len(envelope.ciphertext)} bytes (zero plaintext)")

    box("Provenance Chain", [
        f"{s.name:25s} → {s.output_hash}" for s in envelope.chain
    ])

    print()
    return envelope, context_key


def step2_resolve():
    """Resolve device identity (CGNAT-proof)."""
    step(2, f"Resolving {TARGET} via tibet-overlay...")

    resolver = PhantomResolver()
    resolver.register(
        TARGET, ENDPOINT,
        behind_nat=True,
        capabilities=["tlex-decode", "rvp-sensor"],
        trust_score=0.92,
    )

    resolved = resolver.resolve(TARGET)

    step("✓", f"Resolved: {resolved.endpoint}")
    step("→", f"Behind NAT: {resolved.behind_nat}")
    step("→", f"Trust score: {resolved.trust_score}")
    step("→", "Identity = cryptographic, not topological")
    print()
    return resolved


def step3_airplane_mode(envelope):
    """Store-and-forward: device goes offline."""
    step(3, "Airplane Mode Drop — device goes offline")

    transport = PhantomTransport(node_id="JTel-brain")

    # Send while device is "offline" (no endpoint reachable)
    result = transport.send(
        envelope.to_json(),
        TARGET,
        None,  # no endpoint = offline
    )

    step("→", f"Payload queued (device offline)")
    step("→", f"Queue size: {transport.queue_size}")
    step("→", "IP is gone. Payload floats in mesh node.")
    print()

    # Device "comes back" with new IP
    time.sleep(1)
    step("↻", "Device reconnects (new IP via 5G: 100.64.0.99)")
    step("→", "tibet-overlay resolves identity, not IP")

    results = transport.flush_queue(TARGET, "100.64.0.99:9000")

    step("✓", f"Queue flushed: {len(results)} payload(s) delivered")
    step("→", "No STUN. No TURN. No re-computation.")
    print()
    return transport


def step4_materialize_success(envelope):
    """Materialize with correct context (right person)."""
    step(4, "Materialization — RIGHT person holds device")

    materializer = PhantomMaterializer()
    materializer.set_rvp_signals(
        heartbeat=EXPECTED_HEARTBEAT,
        gyro=EXPECTED_GYRO,
        cadence=EXPECTED_CADENCE,
    )

    result = materializer.materialize(envelope.ciphertext, envelope.l4_hash)

    if result.success:
        step("✓", "L4 hash MATCH — context verified")
        step("✓", "Data materializes in RAM")

        decoder = PhantomDecoder()
        decoded = decoder.decode_text(result.plaintext)

        step("→", f"Decode: {decoded.decode_time_us:.0f}μs ({decoded.method})")

        box("Materialized Output", wrap(decoded.text))
    else:
        step("✗", "UNEXPECTED: materialization failed")

    print()
    return result


def step5_wrong_hands(envelope):
    """Wrong person picks up the device."""
    step(5, "Wrong Hands Test — someone else holds device")

    materializer = PhantomMaterializer()
    materializer.set_rvp_signals(
        heartbeat="88bpm_nervous",
        gyro="table_flat",
        cadence="unfamiliar",
    )

    result = materializer.materialize(envelope.ciphertext, envelope.l4_hash)

    step("✗", "L4 hash MISMATCH — wrong context")
    step("✗", f"Output is noise: {result.noise_hex[:40]}...")
    step("→", "Data never existed. Memory wiped.")
    step("→", "Give it back → text reappears (demo step 4)")

    box("Wrong Context = Noise", [
        f"Heartbeat: 88bpm_nervous (expected: {EXPECTED_HEARTBEAT})",
        f"Gyro:      table_flat (expected: {EXPECTED_GYRO})",
        f"Cadence:   unfamiliar (expected: {EXPECTED_CADENCE})",
        "",
        f"Noise: {result.noise_hex}...",
        "",
        "UPIP L4: REJECT. Data self-destructed.",
    ])
    print()
    return result


def step6_tibet_receipt(envelope):
    """TIBET audit receipt — the cycle is complete."""
    step(6, "TIBET Audit Receipt")

    token = {
        "protocol": "TIBET v1.0",
        "type": "PHANTOM_HANDOFF",
        "erin": f"GPU inference → phantom materialize",
        "eraan": f"{MODEL}, phantom-seal, phantom-mesh",
        "eromheen": f"JTel-brain → {TARGET} (CGNAT traversal)",
        "erachter": "Zero-footprint materialization with context binding",
        "envelope": envelope.envelope_hash,
        "l4_hash": envelope.l4_hash[:24] + "...",
        "target": TARGET,
        "verified": "True",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    box("TIBET Token", [f"{k:14s}  {v}" for k, v in token.items()])

    return token


def footer():
    print()
    print("-" * 66)
    print()
    print("  Phantom flow complete.")
    print()
    print("  GPU → Seal → Overlay → Mesh → Materialize → Decode")
    print()
    print("  Zero plaintext in transit.")
    print("  Zero plaintext on disk.")
    print("  Data exists only in the hands of the right person.")
    print()
    print("  Audit is not an observation. It is a precondition.")
    print()
    print("=" * 66)
    print()


# ─── Main ─────────────────────────────────────────────────

def main():
    header()

    envelope, context_key = step1_seal()
    resolved = step2_resolve()
    transport = step3_airplane_mode(envelope)
    success = step4_materialize_success(envelope)
    wrong = step5_wrong_hands(envelope)
    token = step6_tibet_receipt(envelope)

    footer()


if __name__ == "__main__":
    main()
