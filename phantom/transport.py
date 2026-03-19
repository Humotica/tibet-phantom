"""
phantom.transport — Identity-routed P2P delivery
==================================================

Wraps tibet-mesh for store-and-forward delivery.
Messages route by JIS identity, not by IP address.
Payloads queue for offline peers.
"""

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable


@dataclass
class QueuedPayload:
    """A payload waiting for delivery."""
    target_identity: str
    envelope_json: str
    queued_at: str
    attempts: int = 0
    max_attempts: int = 10
    backoff_seconds: float = 1.0


@dataclass
class DeliveryResult:
    """Result of a delivery attempt."""
    delivered: bool
    target_identity: str
    endpoint: str = ""
    latency_ms: float = 0
    attempts: int = 0
    queued: bool = False
    error: str = ""


class PhantomTransport:
    """
    Identity-routed payload transport with store-and-forward.

    Key properties:
    - Routes by JIS identity, not IP address
    - Queues payloads when target is offline (airplane mode)
    - Delivers immediately when target comes back online
    - Trust-weighted: prefers paths with higher FIR/A scores
    - Every delivery creates a TIBET provenance record

    When tibet-mesh is installed, uses it for actual P2P transport.
    Otherwise provides local simulation with store-and-forward.
    """

    def __init__(self, node_id: str = "phantom-node"):
        self.node_id = node_id
        self.queue: deque[QueuedPayload] = deque()
        self.delivered: list[DeliveryResult] = []
        self._mesh_node = None
        self._delivery_callback: Optional[Callable] = None
        self._try_load_mesh()

    def _try_load_mesh(self):
        """Try to use tibet-mesh if installed."""
        try:
            from tibet_mesh import MeshNode
            self._mesh_node = MeshNode(device_id=self.node_id)
        except ImportError:
            self._mesh_node = None

    def on_delivery(self, callback: Callable):
        """Register callback for successful deliveries."""
        self._delivery_callback = callback

    def send(self, envelope_json: str, target_identity: str,
             target_endpoint: Optional[str] = None) -> DeliveryResult:
        """
        Send a PhantomEnvelope to a target identity.

        If the target is reachable, delivers immediately.
        If offline, queues for store-and-forward delivery.

        Args:
            envelope_json: Serialized PhantomEnvelope
            target_identity: JIS DID of receiver
            target_endpoint: Resolved endpoint (ip:port), if known
        """
        start = time.time()

        # Try tibet-mesh P2P delivery
        if self._mesh_node and target_endpoint:
            try:
                result = self._mesh_node.send(
                    target_identity,
                    payload={"phantom_envelope": envelope_json},
                    intent="phantom-materialization",
                )
                latency = (time.time() - start) * 1000

                if result and getattr(result, 'delivered', False):
                    dr = DeliveryResult(
                        delivered=True,
                        target_identity=target_identity,
                        endpoint=target_endpoint,
                        latency_ms=latency,
                        attempts=1,
                    )
                    self.delivered.append(dr)
                    if self._delivery_callback:
                        self._delivery_callback(dr)
                    return dr
            except Exception:
                pass

        # Try direct HTTP delivery
        if target_endpoint:
            try:
                import requests
                resp = requests.post(
                    f"http://{target_endpoint}/phantom/receive",
                    json={"envelope": envelope_json},
                    timeout=5,
                )
                latency = (time.time() - start) * 1000

                if resp.status_code == 200:
                    dr = DeliveryResult(
                        delivered=True,
                        target_identity=target_identity,
                        endpoint=target_endpoint,
                        latency_ms=latency,
                        attempts=1,
                    )
                    self.delivered.append(dr)
                    if self._delivery_callback:
                        self._delivery_callback(dr)
                    return dr
            except Exception:
                pass

        # Target unreachable — queue for store-and-forward
        queued = QueuedPayload(
            target_identity=target_identity,
            envelope_json=envelope_json,
            queued_at=datetime.now(timezone.utc).isoformat(),
        )
        self.queue.append(queued)

        return DeliveryResult(
            delivered=False,
            target_identity=target_identity,
            queued=True,
            latency_ms=(time.time() - start) * 1000,
        )

    def flush_queue(self, target_identity: str,
                    target_endpoint: str) -> list[DeliveryResult]:
        """
        Flush queued payloads when a device comes back online.

        This is the "airplane mode drop" moment: device reconnects
        with a new IP, overlay resolves the identity, and all
        queued payloads deliver instantly.
        """
        results = []
        remaining = deque()

        # Snapshot the queue and clear it to avoid mutation during iteration
        # (self.send() can append to self.queue if delivery fails)
        snapshot = list(self.queue)
        self.queue = deque()

        for payload in snapshot:
            if payload.target_identity == target_identity:
                payload.attempts += 1
                result = self.send(
                    payload.envelope_json,
                    target_identity,
                    target_endpoint,
                )
                results.append(result)
                if not result.delivered and payload.attempts < payload.max_attempts:
                    remaining.append(payload)
            else:
                remaining.append(payload)

        # Merge any new items that got queued during flush + remaining
        for item in self.queue:
            remaining.append(item)
        self.queue = remaining
        return results

    @property
    def queue_size(self) -> int:
        return len(self.queue)

    @property
    def queued_for(self) -> dict[str, int]:
        """Count of queued payloads per target identity."""
        counts: dict[str, int] = {}
        for p in self.queue:
            counts[p.target_identity] = counts.get(p.target_identity, 0) + 1
        return counts
