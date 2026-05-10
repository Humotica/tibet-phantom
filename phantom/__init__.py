"""
tibet-phantom — Zero-Footprint AI Materialization
==================================================

Compute once on GPU. Verify everywhere. Materialize only with proof.

Data doesn't travel. It materializes — bound to identity, context,
and the living biometric state of the receiver.

Architecture:
    Server (GPU)  →  tibet-edge (seal)
                  →  tibet-overlay (resolve identity)
                  →  tibet-mesh (transport P2P)
                  →  ghost materialize (context-bound decrypt)
                  →  tlex-edge (token decode, 45k tok/sec)

Five packages. One flow. Zero plaintext in transit.
"""

__version__ = "0.2.1"
__author__ = "J. van de Meent, Root AI"

from phantom.seal import PhantomSealer
from phantom.resolve import PhantomResolver
from phantom.transport import PhantomTransport
from phantom.materialize import PhantomMaterializer
from phantom.decode import PhantomDecoder
from phantom.orchestrator import PhantomFlow

# phantom.icc is the ICC bridge (Identity-Bound Continuity Container).
# Importing it requires tibet-drop on sys.path or installed via the
# [icc] extra. Defensive: not auto-imported here, only available via
# explicit `from phantom import icc` when tibet-drop is present.

__all__ = [
    "PhantomSealer",
    "PhantomResolver",
    "PhantomTransport",
    "PhantomMaterializer",
    "PhantomDecoder",
    "PhantomFlow",
]
