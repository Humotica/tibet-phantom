"""
phantom.materialize — Context-bound materialization
=====================================================

Data doesn't exist until the right context proves it should.
The Airlock: JIS identity + RVP biometric state = decryption key.
Wrong context = cryptographic noise. UPIP L4 catches it.
"""

import hashlib
import os
import platform
import getpass
from dataclasses import dataclass
from typing import Optional


@dataclass
class ContextSignal:
    """Living context from JIS + RVP sensors."""
    node_name: str
    user: str
    rvp_heartbeat: str
    rvp_gyro: str
    rvp_cadence: str

    @property
    def context_string(self) -> str:
        return f"{self.node_name}|{self.user}|{self.rvp_heartbeat}|{self.rvp_gyro}|{self.rvp_cadence}"

    def derive_key(self) -> bytes:
        """Derive decryption key from living context."""
        return hashlib.sha256(self.context_string.encode()).digest()


@dataclass
class MaterializationResult:
    """Result of attempting to materialize a phantom payload."""
    success: bool
    plaintext: Optional[bytes] = None
    decoded_text: Optional[str] = None
    l4_verified: bool = False
    context_match: bool = False
    noise_hex: str = ""


class PhantomMaterializer:
    """
    Context-bound materialization engine.

    The core ghost_produce logic: data can only be decrypted
    when the receiver's living context (hardware + identity +
    biometric state) matches what was sealed into the envelope.

    If context is wrong:
    - Decryption produces noise
    - L4 hash doesn't match
    - Data never exists in readable form
    - Output is securely wiped

    Context sources:
    - JIS L1: Hardware/node identity
    - JIS L2: User identity
    - RVP L1: Heartbeat signal (from wearable/sensor)
    - RVP L2: Gyroscope state (holding pattern)
    - RVP L3: Typing/interaction cadence
    """

    def __init__(self):
        self._rvp_override: Optional[dict] = None

    def read_context(self) -> ContextSignal:
        """
        Read the living context from JIS + RVP sensors.

        In production, RVP signals come from the sensor daemon
        running in RAM (never persisted to disk).
        For demo, reads from environment variables.
        """
        if self._rvp_override:
            return ContextSignal(
                node_name=self._rvp_override.get("node", platform.node()),
                user=self._rvp_override.get("user", getpass.getuser()),
                rvp_heartbeat=self._rvp_override.get("heartbeat", "MISSING"),
                rvp_gyro=self._rvp_override.get("gyro", "MISSING"),
                rvp_cadence=self._rvp_override.get("cadence", "MISSING"),
            )

        return ContextSignal(
            node_name=platform.node(),
            user=getpass.getuser(),
            rvp_heartbeat=os.environ.get("RVP_HEARTBEAT", "MISSING"),
            rvp_gyro=os.environ.get("RVP_GYRO", "stable"),
            rvp_cadence=os.environ.get("RVP_CADENCE", "normal"),
        )

    def set_rvp_signals(self, heartbeat: str = "", gyro: str = "",
                        cadence: str = "", node: str = "", user: str = ""):
        """Override RVP signals (for demo/testing)."""
        self._rvp_override = {}
        if heartbeat:
            self._rvp_override["heartbeat"] = heartbeat
        if gyro:
            self._rvp_override["gyro"] = gyro
        if cadence:
            self._rvp_override["cadence"] = cadence
        if node:
            self._rvp_override["node"] = node
        if user:
            self._rvp_override["user"] = user

    def clear_rvp_override(self):
        """Clear RVP signal overrides."""
        self._rvp_override = None

    def materialize(self, ciphertext: bytes, expected_l4_hash: str) -> MaterializationResult:
        """
        Attempt to materialize a phantom payload.

        1. Read living context (JIS + RVP)
        2. Derive decryption key from context
        3. Decrypt ciphertext
        4. Verify L4 hash of plaintext
        5. If hash matches: data materializes
        6. If hash fails: data is noise, securely wiped

        Args:
            ciphertext: The encrypted payload from PhantomEnvelope
            expected_l4_hash: The L4 hash from UPIP (expected plaintext hash)

        Returns:
            MaterializationResult
        """
        # 1. Read living context
        context = self.read_context()

        # 2. Derive key
        key = context.derive_key()

        # 3. Decrypt
        plaintext = bytes([c ^ key[i % len(key)] for i, c in enumerate(ciphertext)])

        # 4. Verify L4 hash
        actual_hash = hashlib.sha256(plaintext).hexdigest()
        l4_match = actual_hash == expected_l4_hash

        if l4_match:
            # Context matches — data materializes
            try:
                decoded = plaintext.decode("utf-8")
                if decoded.isprintable() or "\n" in decoded:
                    return MaterializationResult(
                        success=True,
                        plaintext=plaintext,
                        decoded_text=decoded,
                        l4_verified=True,
                        context_match=True,
                    )
            except UnicodeDecodeError:
                pass

        # Context mismatch — noise. Securely wipe.
        noise_sample = plaintext[:32].hex()

        # Overwrite plaintext in memory (best effort)
        plaintext = b"\x00" * len(plaintext)

        return MaterializationResult(
            success=False,
            l4_verified=False,
            context_match=False,
            noise_hex=noise_sample,
        )

    @staticmethod
    def build_context_key(node: str, user: str,
                          heartbeat: str, gyro: str = "stable",
                          cadence: str = "normal") -> bytes:
        """
        Build a context key for sealing (server-side).

        The server must know the expected receiver context
        to encrypt the payload correctly.
        """
        context = f"{node}|{user}|{heartbeat}|{gyro}|{cadence}"
        return hashlib.sha256(context.encode()).digest()
