"""
phantom.orchestrator — The full Phantom flow
==============================================

Server (GPU)  →  seal  →  resolve  →  transport  →  materialize  →  decode

Five steps. Zero plaintext in transit.
Compute once. Verify everywhere. Materialize only with proof.
"""

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from phantom.seal import PhantomSealer, PhantomEnvelope
from phantom.resolve import PhantomResolver, DeviceEndpoint
from phantom.transport import PhantomTransport, DeliveryResult
from phantom.materialize import PhantomMaterializer, MaterializationResult
from phantom.decode import PhantomDecoder, DecodeResult


@dataclass
class PhantomResult:
    """End-to-end result of a Phantom flow."""
    # Seal
    envelope_hash: str = ""
    chain_steps: int = 0
    model: str = ""

    # Resolve
    target_identity: str = ""
    target_endpoint: str = ""
    behind_nat: bool = False
    trust_score: float = 0.0

    # Transport
    delivered: bool = False
    queued: bool = False
    transport_latency_ms: float = 0

    # Materialize
    materialized: bool = False
    l4_verified: bool = False
    context_match: bool = False

    # Decode
    text: str = ""
    decode_method: str = ""
    decode_us: float = 0

    # Meta
    total_latency_ms: float = 0
    timestamp: str = ""

    def to_tibet_token(self) -> dict:
        """Generate TIBET provenance token for the full flow."""
        return {
            "protocol": "TIBET v1.0",
            "type": "PHANTOM_HANDOFF",
            "erin": f"GPU inference → phantom materialize on {self.target_identity}",
            "eraan": f"{self.model}, phantom-seal, phantom-mesh, phantom-materialize",
            "eromheen": f"endpoint={self.target_endpoint}, nat={self.behind_nat}",
            "erachter": "Zero-footprint compute-once-verify-everywhere materialization",
            "target": self.target_identity,
            "trust_score": str(self.trust_score),
            "envelope_hash": self.envelope_hash,
            "l4_verified": str(self.l4_verified),
            "materialized": str(self.materialized),
            "latency_ms": f"{self.total_latency_ms:.1f}",
            "decode_method": self.decode_method,
            "decode_us": f"{self.decode_us:.0f}",
            "timestamp": self.timestamp,
        }


class PhantomFlow:
    """
    Orchestrates the full phantom flow.

    Server-side (seal + resolve + transport):
        flow = PhantomFlow(model="qwen2.5:32b")
        result = flow.send(plaintext, target="jis:pixel-jasper",
                          context_key=expected_key)

    Client-side (materialize + decode):
        result = flow.receive(envelope_json)

    Full local demo:
        result = flow.demo(plaintext, target="jis:pixel-jasper",
                          heartbeat="100bpm_steady")
    """

    def __init__(self, model: str = "unknown", node_id: str = "phantom-node"):
        self.sealer = PhantomSealer(model=model)
        self.resolver = PhantomResolver()
        self.transport = PhantomTransport(node_id=node_id)
        self.materializer = PhantomMaterializer()
        self.decoder = PhantomDecoder()
        self.model = model

    # --- Server-side ---

    def send(self, plaintext: bytes, target_identity: str,
             context_key: bytes,
             target_endpoint: Optional[str] = None) -> PhantomResult:
        """
        Server-side: seal, resolve, and transport a phantom payload.

        Args:
            plaintext: The inference output
            target_identity: JIS DID of receiver
            context_key: Key derived from expected receiver context
            target_endpoint: Override endpoint (skip resolve)
        """
        start = time.time()
        result = PhantomResult(model=self.model, target_identity=target_identity)

        # Step 1: Seal
        envelope = self.sealer.seal(plaintext, context_key, target_identity)
        result.envelope_hash = envelope.envelope_hash
        result.chain_steps = len(envelope.chain)

        # Step 2: Resolve
        if target_endpoint:
            result.target_endpoint = target_endpoint
        else:
            resolved = self.resolver.resolve(target_identity)
            if resolved:
                result.target_endpoint = resolved.endpoint
                result.behind_nat = resolved.behind_nat
                result.trust_score = resolved.trust_score

        # Step 3: Transport
        delivery = self.transport.send(
            envelope.to_json(),
            target_identity,
            result.target_endpoint or None,
        )
        result.delivered = delivery.delivered
        result.queued = delivery.queued
        result.transport_latency_ms = delivery.latency_ms

        result.total_latency_ms = (time.time() - start) * 1000
        result.timestamp = datetime.now(timezone.utc).isoformat()

        return result

    # --- Client-side ---

    def receive(self, envelope_json: str) -> PhantomResult:
        """
        Client-side: materialize and decode a phantom payload.

        Args:
            envelope_json: Serialized PhantomEnvelope
        """
        start = time.time()
        envelope = PhantomEnvelope.from_dict(json.loads(envelope_json))

        result = PhantomResult(
            model=envelope.model,
            target_identity=envelope.target_identity,
            envelope_hash=envelope.envelope_hash,
        )

        # Step 4: Materialize
        mat = self.materializer.materialize(
            envelope.ciphertext,
            envelope.l4_hash,
        )
        result.materialized = mat.success
        result.l4_verified = mat.l4_verified
        result.context_match = mat.context_match

        if mat.success and mat.plaintext:
            # Step 5: Decode
            dec = self.decoder.decode_text(mat.plaintext)
            result.text = dec.text
            result.decode_method = dec.method
            result.decode_us = dec.decode_time_us

        result.total_latency_ms = (time.time() - start) * 1000
        result.timestamp = datetime.now(timezone.utc).isoformat()

        return result

    # --- Full local demo ---

    def demo(self, plaintext: bytes, target_identity: str = "jis:demo-device",
             heartbeat: str = "100bpm_steady",
             gyro: str = "stable",
             cadence: str = "normal") -> PhantomResult:
        """
        Full local demo: seal → resolve → materialize → decode.

        Simulates the complete flow on one machine.
        The materializer reads context from the current machine
        and RVP signal overrides.
        """
        import platform
        import getpass

        start = time.time()

        # Build context key from expected receiver state
        context_key = PhantomMaterializer.build_context_key(
            node=platform.node(),
            user=getpass.getuser(),
            heartbeat=heartbeat,
            gyro=gyro,
            cadence=cadence,
        )

        # Seal
        self.sealer = PhantomSealer(model=self.model)
        envelope = self.sealer.seal(plaintext, context_key, target_identity)

        # Set materializer to match expected context
        self.materializer.set_rvp_signals(
            heartbeat=heartbeat,
            gyro=gyro,
            cadence=cadence,
        )

        # Materialize
        mat = self.materializer.materialize(envelope.ciphertext, envelope.l4_hash)

        result = PhantomResult(
            model=self.model,
            target_identity=target_identity,
            envelope_hash=envelope.envelope_hash,
            chain_steps=len(envelope.chain),
            materialized=mat.success,
            l4_verified=mat.l4_verified,
            context_match=mat.context_match,
        )

        if mat.success and mat.plaintext:
            dec = self.decoder.decode_text(mat.plaintext)
            result.text = dec.text
            result.decode_method = dec.method
            result.decode_us = dec.decode_time_us

        result.total_latency_ms = (time.time() - start) * 1000
        result.timestamp = datetime.now(timezone.utc).isoformat()

        # Test wrong context
        self.materializer.set_rvp_signals(heartbeat="WRONG_PERSON")
        wrong = self.materializer.materialize(envelope.ciphertext, envelope.l4_hash)
        self.materializer.clear_rvp_override()

        # Store wrong-context result for demo display
        result._wrong_context_noise = wrong.noise_hex if not wrong.success else ""

        return result
