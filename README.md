# tibet-phantom

**Zero-Footprint AI Materialization**

*Compute once on GPU. Verify everywhere. Materialize only with proof.*

---

Data doesn't travel. It materializes.

tibet-phantom orchestrates the full pipeline from GPU inference output to
context-bound materialization on edge devices — with zero plaintext in transit,
zero plaintext on disk, and a complete TIBET provenance trail.

## The Problem

Running 32-layer LLM inference on every edge device is wasteful and often
impossible. But sending plaintext results over the network is a security and
privacy disaster. What if the output only exists in the hands of the right
person — literally?

## The Solution

```
GPU Server                          Edge Device
───────────                         ────────────
LLM inference (once)                No re-inference needed
    │                                    │
    ▼                                    ▼
tibet-edge: seal output ────────► tibet-mesh: receive
    │                                    │
    ▼                                    ▼
tibet-overlay: resolve ◄─────── tibet-overlay: identity
    │ identity (CGNAT-proof)             │
    ▼                                    ▼
provenance chain              materialize: context check
    │                           (heartbeat + gyro + cadence)
    ▼                                    │
TIBET audit receipt               ┌──────┴──────┐
                                  │             │
                              MATCH          MISMATCH
                            text appears     noise only
                            in RAM           data self-destructs
```

## Five Modules

| Module | Role | Protocol |
|--------|------|----------|
| `phantom.seal` | Seal inference output with provenance chain | UPIP |
| `phantom.resolve` | Resolve device identity (CGNAT-proof) | JIS |
| `phantom.transport` | Store-and-forward delivery | tibet-mesh |
| `phantom.materialize` | Context-bound decryption | RVP |
| `phantom.decode` | Token-to-text on CPU | T-LEX |

## Install

```bash
pip install tibet-phantom
```

With all transport + edge dependencies:

```bash
pip install tibet-phantom[full]
```

## Quick Start

```python
from phantom import PhantomFlow

# Full local demo
flow = PhantomFlow(model="qwen2.5:32b")
result = flow.demo(
    plaintext=b"AI output that should only exist for the right person",
    target_identity="jis:my-device",
    heartbeat="72bpm_steady",
)

print(result.text)           # Only if context matches
print(result.materialized)   # True/False
print(result.to_tibet_token())  # Full provenance
```

### Server-side (seal + send)

```python
from phantom import PhantomFlow, PhantomMaterializer

flow = PhantomFlow(model="qwen2.5:32b")
context_key = PhantomMaterializer.build_context_key(
    node="target-device", user="jasper",
    heartbeat="72bpm", gyro="hand_held", cadence="natural",
)
result = flow.send(plaintext, "jis:pixel-jasper", context_key)
```

### Client-side (materialize + decode)

```python
flow = PhantomFlow()
flow.materializer.set_rvp_signals(
    heartbeat="72bpm", gyro="hand_held", cadence="natural",
)
result = flow.receive(envelope_json)
print(result.text)  # Text, or empty if context mismatch
```

## Demo

```bash
phantom demo
```

Runs the full 6-step Hackaway demo:

1. **Seal** — GPU inference output sealed with UPIP provenance chain
2. **Resolve** — JIS identity resolution (CGNAT-proof, not IP-based)
3. **Airplane Mode** — Device goes offline, payload queues in mesh, device reconnects with new IP
4. **Materialize** — Right person holds device → L4 hash match → text appears
5. **Wrong Hands** — Someone else holds device → noise → data self-destructs
6. **TIBET Receipt** — Full audit token with provenance chain

## Architecture

tibet-phantom builds on four IETF Internet-Drafts:

| Protocol | Draft | Function |
|----------|-------|----------|
| **TIBET** | [draft-vandemeent-tibet-provenance](https://datatracker.ietf.org/doc/draft-vandemeent-tibet-provenance/) | Provenance chain |
| **JIS** | [draft-vandemeent-jis-identity](https://datatracker.ietf.org/doc/draft-vandemeent-jis-identity/) | Identity binding |
| **UPIP** | [draft-vandemeent-upip-process-integrity](https://datatracker.ietf.org/doc/draft-vandemeent-upip-process-integrity/) | Process integrity + L4 hash |
| **RVP** | [draft-vandemeent-rvp-continuous-verification](https://datatracker.ietf.org/doc/draft-vandemeent-rvp-continuous-verification/) | Continuous biometric verification |

And three companion packages:

| Package | PyPI | Role |
|---------|------|------|
| **tibet-edge** | [tibet-edge](https://pypi.org/project/tibet-edge/) | Firmware + inference sealing |
| **tibet-mesh** | [tibet-mesh](https://pypi.org/project/tibet-mesh/) | P2P store-and-forward transport |
| **tibet-overlay** | [tibet-overlay](https://pypi.org/project/tibet-overlay/) | CGNAT-proof identity overlay |

## Key Properties

- **Zero plaintext in transit** — Output is encrypted with context-derived key before leaving GPU
- **Zero plaintext on disk** — Ciphertext only; plaintext exists only in RAM during materialization
- **Context-bound** — Decryption key derived from hardware + identity + biometric signals (RVP)
- **Self-destructing** — Wrong context = cryptographic noise, not decryption error
- **CGNAT-proof** — Identity is cryptographic (JIS), not topological (IP address)
- **Airplane-mode resilient** — Store-and-forward mesh delivers when device reconnects
- **Auditable** — Every step creates a TIBET provenance record

## License

MIT — Humotica AI Lab
