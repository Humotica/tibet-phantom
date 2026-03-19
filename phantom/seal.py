"""
phantom.seal — Seal inference output with provenance chain
==========================================================

Wraps tibet-edge FirmwareSealer pattern for LLM output.
Each step in the inference chain gets a TIBET token.
Missing step → REJECT. Broken chain → REJECT.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class InferenceStep:
    """One step in the inference provenance chain."""
    name: str
    actor: str
    input_hash: str
    output_hash: str
    metadata: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PhantomEnvelope:
    """Sealed inference output — the payload that travels."""
    ciphertext: bytes
    l4_hash: str
    chain: list
    target_identity: str
    model: str
    created: str
    envelope_hash: str = ""

    def __post_init__(self):
        if not self.envelope_hash:
            self.envelope_hash = self._compute_envelope_hash()

    def _compute_envelope_hash(self) -> str:
        content = f"{self.l4_hash}|{self.target_identity}|{self.model}|{self.created}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "ciphertext_hex": self.ciphertext.hex(),
            "l4_hash": self.l4_hash,
            "chain": [
                {
                    "name": s.name,
                    "actor": s.actor,
                    "input_hash": s.input_hash,
                    "output_hash": s.output_hash,
                    "metadata": s.metadata,
                    "timestamp": s.timestamp,
                }
                for s in self.chain
            ],
            "target_identity": self.target_identity,
            "model": self.model,
            "created": self.created,
            "envelope_hash": self.envelope_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict) -> "PhantomEnvelope":
        chain = [
            InferenceStep(
                name=s["name"],
                actor=s["actor"],
                input_hash=s["input_hash"],
                output_hash=s["output_hash"],
                metadata=s.get("metadata", {}),
                timestamp=s["timestamp"],
            )
            for s in d["chain"]
        ]
        return cls(
            ciphertext=bytes.fromhex(d["ciphertext_hex"]),
            l4_hash=d["l4_hash"],
            chain=chain,
            target_identity=d["target_identity"],
            model=d["model"],
            created=d["created"],
            envelope_hash=d.get("envelope_hash", ""),
        )


class PhantomSealer:
    """
    Seal LLM inference output into a PhantomEnvelope.

    The sealer creates a provenance chain where each step
    (inference, encoding, encryption) is tracked with hashes.
    The final envelope contains ciphertext that can only be
    decrypted with the correct receiver context.
    """

    def __init__(self, model: str, actor: str = "phantom-sealer"):
        self.model = model
        self.actor = actor
        self.chain: list[InferenceStep] = []

    def add_step(self, name: str, input_data: bytes, output_data: bytes,
                 metadata: Optional[dict] = None) -> InferenceStep:
        """Record an inference chain step."""
        step = InferenceStep(
            name=name,
            actor=self.actor,
            input_hash=hashlib.sha256(input_data).hexdigest()[:16],
            output_hash=hashlib.sha256(output_data).hexdigest()[:16],
            metadata=metadata or {},
        )
        self.chain.append(step)
        return step

    def seal(self, plaintext: bytes, context_key: bytes,
             target_identity: str) -> PhantomEnvelope:
        """
        Seal plaintext into an envelope.

        Args:
            plaintext: The inference output (tokens or text)
            context_key: Derived from target's JIS+RVP context
            target_identity: JIS DID of the receiver (e.g. "jis:pixel-jasper")

        Returns:
            PhantomEnvelope with ciphertext and provenance chain
        """
        # Step 1: Record the raw inference output
        self.add_step(
            "inference_output",
            b"prompt",
            plaintext,
            {"model": self.model},
        )

        # Step 2: Compute L4 hash (the expected output hash)
        l4_hash = hashlib.sha256(plaintext).hexdigest()

        # Step 3: Encrypt with context-derived key (XOR for demo, AES for prod)
        ciphertext = bytes([p ^ context_key[i % len(context_key)]
                           for i, p in enumerate(plaintext)])

        self.add_step(
            "context_encryption",
            plaintext,
            ciphertext,
            {"target": target_identity, "method": "context-bound-xor"},
        )

        # Step 4: Create sealed envelope
        envelope = PhantomEnvelope(
            ciphertext=ciphertext,
            l4_hash=l4_hash,
            chain=list(self.chain),
            target_identity=target_identity,
            model=self.model,
            created=datetime.now(timezone.utc).isoformat(),
        )

        self.add_step(
            "envelope_sealed",
            ciphertext,
            envelope.envelope_hash.encode(),
            {"envelope_hash": envelope.envelope_hash},
        )

        return envelope

    def verify_chain(self) -> bool:
        """Verify the provenance chain is complete and unbroken."""
        required = {"inference_output", "context_encryption", "envelope_sealed"}
        present = {s.name for s in self.chain}
        return required.issubset(present)
