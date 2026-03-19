"""
phantom.resolve — Identity-based device resolution
====================================================

Wraps tibet-overlay for CGNAT-proof device discovery.
Resolves JIS identity to endpoint, regardless of IP changes.
"""

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DeviceEndpoint:
    """Resolved device endpoint."""
    identity: str
    endpoint: str
    trust_score: float
    behind_nat: bool
    capabilities: list
    last_seen: str
    resolved: bool = True


@dataclass
class DeviceRegistration:
    """A registered device in the overlay."""
    identity: str
    endpoint: str
    behind_nat: bool
    capabilities: list
    trust_score: float = 0.5
    last_seen: str = ""
    online: bool = True


class PhantomResolver:
    """
    Resolve device identity to network endpoint.

    Uses tibet-overlay pattern: identity is cryptographic (JIS),
    not topological (IP). Devices behind CGNAT, roaming between
    WiFi and 5G, or changing IPs are always reachable by identity.

    When tibet-overlay is installed, delegates to it.
    Otherwise provides standalone resolution.
    """

    def __init__(self):
        self.devices: dict[str, DeviceRegistration] = {}
        self._overlay = None
        self._try_load_overlay()

    def _try_load_overlay(self):
        """Try to use tibet-overlay if installed."""
        try:
            from tibet_overlay import IdentityOverlay
            self._overlay = IdentityOverlay()
        except ImportError:
            self._overlay = None

    def register(self, identity: str, endpoint: str,
                 behind_nat: bool = False,
                 capabilities: Optional[list] = None,
                 trust_score: float = 0.5) -> DeviceRegistration:
        """
        Register a device in the overlay.

        Args:
            identity: JIS identity (e.g. "jis:pixel-jasper")
            endpoint: Current network endpoint (ip:port)
            behind_nat: Whether device is behind CGNAT
            capabilities: Device capabilities
            trust_score: Initial FIR/A trust score (0.0-1.0)
        """
        reg = DeviceRegistration(
            identity=identity,
            endpoint=endpoint,
            behind_nat=behind_nat,
            capabilities=capabilities or [],
            trust_score=trust_score,
            last_seen=datetime.now(timezone.utc).isoformat(),
        )
        self.devices[identity] = reg

        # Also register in tibet-overlay if available
        if self._overlay:
            ip, _, port = endpoint.rpartition(":")
            self._overlay.register(
                identity.replace("jis:", ""),
                ip=ip,
                port=int(port) if port else 9000,
                behind_nat=behind_nat,
                capabilities=capabilities or [],
            )

        return reg

    def resolve(self, identity: str) -> Optional[DeviceEndpoint]:
        """
        Resolve identity to endpoint.

        The key insight: this works even when the device's IP has
        changed (DHCP, roaming, CGNAT reassignment), because identity
        is cryptographic, not topological.
        """
        # Try tibet-overlay first
        if self._overlay:
            try:
                result = self._overlay.resolve(identity.replace("jis:", ""))
                if result and result.resolved:
                    return DeviceEndpoint(
                        identity=identity,
                        endpoint=result.endpoint,
                        trust_score=result.trust_score if hasattr(result, 'trust_score') else 0.5,
                        behind_nat=True,
                        capabilities=[],
                        last_seen=datetime.now(timezone.utc).isoformat(),
                    )
            except Exception:
                pass

        # Fallback to local registry
        reg = self.devices.get(identity)
        if reg and reg.online:
            return DeviceEndpoint(
                identity=reg.identity,
                endpoint=reg.endpoint,
                trust_score=reg.trust_score,
                behind_nat=reg.behind_nat,
                capabilities=reg.capabilities,
                last_seen=reg.last_seen,
            )

        return None

    def update_endpoint(self, identity: str, new_endpoint: str):
        """
        Update endpoint after IP change.
        Identity stays the same — only the network path changes.
        """
        if identity in self.devices:
            self.devices[identity].endpoint = new_endpoint
            self.devices[identity].last_seen = datetime.now(timezone.utc).isoformat()

    def set_online(self, identity: str, online: bool = True):
        """Mark device as online/offline (airplane mode scenario)."""
        if identity in self.devices:
            self.devices[identity].online = online
            if online:
                self.devices[identity].last_seen = datetime.now(timezone.utc).isoformat()

    def find_by_capability(self, capability: str) -> list[DeviceEndpoint]:
        """Find all online devices with a specific capability."""
        results = []
        for reg in self.devices.values():
            if reg.online and capability in reg.capabilities:
                results.append(DeviceEndpoint(
                    identity=reg.identity,
                    endpoint=reg.endpoint,
                    trust_score=reg.trust_score,
                    behind_nat=reg.behind_nat,
                    capabilities=reg.capabilities,
                    last_seen=reg.last_seen,
                ))
        return results
