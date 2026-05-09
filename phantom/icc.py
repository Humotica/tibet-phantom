"""
phantom.icc — Phantom ↔ ICC bridge
====================================

Phantom is not just a web function; it is a resumable
triage-bearing continuity layer.

This module elevates Phantom v0.1's JSON-vault session storage to
v0.2's first-class ICC integration:

- export sealed Phantom session  → .claude.tza ICC bundle
  (TBZ envelope + Ed25519 sigs + surface_* routing fields +
   triage_state classification)

- import .tza ICC bundle  → new Phantom session
  (forward-only causal fork, never restore)
  with two paths:
    mode="normal"  → trusted continuation (auto-accept)
    mode="triage"  → quarantined continuation (operator review)

Surface mismatch automatically escalates the import path to
triage mode — silent-accept is structurally disallowed.

Spec: /srv/jtel-stack/hersenspinsels/phantom-icc-as-triage-bearing-continuity.md
SSM:  draft-vandemeent-tibet-semantic-surface-manifest-00 §9.4 + §12
Time: draft-vandemeent-tibet-causal-time-00 §8 + §13.1
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Bridge to tibet-drop tooling for TBZ pack/verify.
# In v0.2 this is path-imported; in v0.3 tibet-drop becomes a
# proper PyPI dep.
_TIBET_DROP_SRC = Path("/srv/jtel-stack/sandbox/airdrop-cli/src")
if _TIBET_DROP_SRC.exists() and str(_TIBET_DROP_SRC) not in sys.path:
    sys.path.insert(0, str(_TIBET_DROP_SRC))

try:
    from tibet_drop.bundle import (  # type: ignore
        compare_surfaces,
        inspect_bundle,
        pack_bundle,
        parse_filename_surface,
        verify_bundle,
    )
    from tibet_drop.crypto import IdentityKey  # type: ignore
    from tibet_drop.handshake import new_tpid  # type: ignore
except ImportError as e:
    raise ImportError(
        "phantom.icc requires tibet-drop. Install via PyPI (v0.3+) "
        "or ensure /srv/jtel-stack/sandbox/airdrop-cli/src is on "
        "sys.path."
    ) from e


DEFAULT_VAULT_DIR = Path(
    os.environ.get(
        "PHANTOM_VAULT_DIR",
        "/srv/jtel-stack/sandbox/.phantom_vault",
    )
)


# Provider → SSM surface_profile mapping per
# draft-vandemeent-tibet-semantic-surface-manifest-00 §8.1
PROVIDER_TO_PROFILE = {
    "claude": "claude",
    "gemini": "gemini",
    "gpt": "gpt",
    "humotica-32b": "kit",
    "humotica-7b": "kit",
    "qwen2.5:32b": "kit",
    "qwen2.5:7b": "kit",
    "qwen2.5:3b": "kit",
}


# Per spec §3.3 the four canonical triage states
TRIAGE_STATES = {"trusted", "quarantined", "under-review", "tombstoned"}


@dataclass
class TriageState:
    """Spec §3.3 — first-class triage classification."""
    triage_state: str = "trusted"
    triage_reason: str = "clean export"
    triage_disposition: str = "auto-accept"
    triage_parent_ref: Optional[str] = None
    continuity_class: str = "phantom-resume"
    import_mode_required: str = "either"

    def to_dict(self) -> dict:
        return {
            "triage_state": self.triage_state,
            "triage_reason": self.triage_reason,
            "triage_disposition": self.triage_disposition,
            "triage_parent_ref": self.triage_parent_ref,
            "continuity_class": self.continuity_class,
            "import_mode_required": self.import_mode_required,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TriageState":
        return cls(
            triage_state=d.get("triage_state", "trusted"),
            triage_reason=d.get("triage_reason", ""),
            triage_disposition=d.get("triage_disposition", "auto-accept"),
            triage_parent_ref=d.get("triage_parent_ref"),
            continuity_class=d.get("continuity_class", "phantom-resume"),
            import_mode_required=d.get("import_mode_required", "either"),
        )

    @classmethod
    def quarantined(cls, reason: str,
                    parent_ref: Optional[str] = None) -> "TriageState":
        return cls(
            triage_state="quarantined",
            triage_reason=reason,
            triage_disposition="operator-review",
            triage_parent_ref=parent_ref,
            continuity_class="phantom-resume-triage",
            import_mode_required="triage",
        )


@dataclass
class ImportResult:
    """Outcome of icc_to_phantom_session()."""
    new_session_id: str
    parent_session_id: str
    mode_used: str           # "normal" | "triage"
    triage_state: TriageState
    surface_status: str      # MATCH | MISMATCH | PARTIAL | NONE
    verify_errors: list = field(default_factory=list)
    bundle_path: Optional[Path] = None


# ─── Helpers ────────────────────────────────────────────────────


def _provider_to_profile(provider: str) -> str:
    return PROVIDER_TO_PROFILE.get(provider, "tza")


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_surface_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _new_session_id() -> str:
    return f"phantom-{int(time.time())}-{secrets.token_hex(3)}"


def _load_phantom_session(session_id: str, vault: Path) -> dict:
    p = vault / f"{session_id}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"Phantom session not found in vault: {session_id}"
        )
    return json.loads(p.read_text())


def _write_phantom_session(session: dict, vault: Path) -> Path:
    vault.mkdir(parents=True, exist_ok=True)
    p = vault / f"{session['session_id']}.json"
    p.write_text(json.dumps(session, indent=2))
    return p


def _compose_blocks(
    session: dict,
    triage: TriageState,
) -> list[tuple[str, bytes]]:
    """Compose the three normative blocks per spec §3."""
    process_state = {
        "transcript": session.get("transcript", []),
        "context_data": session.get("context_data", {}),
        "todos": session.get("todos", []),
        "files": session.get("files", {}),
        "model_state_ref": session.get("model_state_ref"),
    }
    phantom_meta = {
        "session_id_origin": session["session_id"],
        "owner_did_origin": session.get("owner_did"),
        "provider": session.get("provider"),
        "backend": session.get("backend"),
        "model": session.get("model"),
        "sealed_at": session.get("sealed_at"),
        "l4_hash": session.get("l4_hash"),
        "ttl_minutes_remaining": session.get("ttl_minutes_remaining"),
    }

    blocks: list[tuple[str, bytes]] = [
        ("process_state.json",
         json.dumps(process_state, sort_keys=True).encode()),
        ("phantom_meta.json",
         json.dumps(phantom_meta, sort_keys=True).encode()),
        ("triage_state.json",
         json.dumps(triage.to_dict(), sort_keys=True).encode()),
    ]

    if "tibet_chain" in session:
        blocks.append((
            "tibet_chain.json",
            json.dumps(session["tibet_chain"], sort_keys=True).encode(),
        ))

    return blocks


def _build_filename(profile: str, priority: str,
                    time_frag: Optional[str] = None) -> str:
    """Surface-aware filename per SSM §6.1."""
    t = time_frag or _today_surface_date()
    return f"{t}.session-resume.{profile}.{priority}.tza"


# ─── Export ─────────────────────────────────────────────────────


def phantom_session_to_icc(
    session_id: str,
    sender_aint: str,
    sender_signer: IdentityKey,
    receiver_aint: str,
    receiver_pubkey_hex: str,
    output_path: Path,
    *,
    triage: Optional[TriageState] = None,
    priority: str = "normal",
    vault: Path = DEFAULT_VAULT_DIR,
    time_fragment: Optional[str] = None,
) -> dict:
    """
    Export a sealed Phantom session as a .claude.tza ICC bundle.

    Returns the manifest dict. The original session is NOT modified.
    """
    session = _load_phantom_session(session_id, vault)
    triage = triage or TriageState()  # default = trusted clean export

    profile = _provider_to_profile(session.get("provider", ""))
    time_frag = time_fragment or _today_surface_date()

    # If output_path is a directory, derive surface-aware filename
    if output_path.is_dir():
        output_path = output_path / _build_filename(
            profile, priority, time_frag
        )

    blocks = _compose_blocks(session, triage)

    manifest = pack_bundle(
        output_path=output_path,
        blocks=blocks,
        sender_aint=sender_aint,
        sender_signer=sender_signer,
        receiver_aint=receiver_aint,
        receiver_pubkey_hex=receiver_pubkey_hex,
        payload_type="ai_state",
        tpid=new_tpid(),
        surface_time_fragment=time_frag,
        surface_context="session-resume",
        surface_profile=profile,
        surface_priority=priority,
    )
    return manifest


# ─── Import ─────────────────────────────────────────────────────


def _classify_required_mode(
    surface_status: str,
    triage_block: TriageState,
    caller_mode: str,
) -> str:
    """
    Determine the actual import mode after applying spec §6 + §8 rules.

    The rule of thumb is: if ANY signal suggests uncertainty, escalate
    silently to triage. Caller cannot override surface mismatch with
    mode='normal'.
    """
    if surface_status == "MISMATCH":
        return "triage"
    if surface_status == "PARTIAL":
        return "triage"
    if triage_block.triage_state == "quarantined":
        return "triage"
    if triage_block.triage_state == "tombstoned":
        return "reject"
    if triage_block.import_mode_required == "triage":
        return "triage"
    if caller_mode == "triage":
        return "triage"
    return "normal"


def icc_to_phantom_session(
    bundle_path: Path,
    *,
    mode: str = "normal",
    vault: Path = DEFAULT_VAULT_DIR,
    expected_sender_aint: Optional[str] = None,
    receiver_did: Optional[str] = None,
) -> ImportResult:
    """
    Import a .claude.tza bundle as a new Phantom session.

    Returns ImportResult with the new session_id (forward-only fork)
    and the triage classification that was applied.

    NEVER restores a previous session_id. NEVER modifies an existing
    session. Resume = fork.
    """
    if mode not in ("normal", "triage"):
        raise ValueError(f"unknown mode: {mode!r}")

    # Step 1: cryptographic verification of TBZ envelope
    valid, manifest, errors = verify_bundle(bundle_path)
    if not valid:
        raise ValueError(
            f"bundle verification failed: {errors}"
        )

    # Step 2: surface consistency check (SSM §9.4)
    fn_surface = parse_filename_surface(bundle_path.name)
    mf_surface = {k: manifest.get(k) for k in (
        "surface_time_fragment", "surface_context",
        "surface_profile", "surface_priority")}
    surface_status = compare_surfaces(fn_surface, mf_surface)

    # Step 3: optional sender pinning
    if expected_sender_aint and \
            manifest.get("sender_aint") != expected_sender_aint:
        raise ValueError(
            f"sender mismatch: expected={expected_sender_aint} "
            f"got={manifest.get('sender_aint')}"
        )

    # Step 4: extract embedded blocks (verify already passed)
    blocks_data = _read_block_payloads(bundle_path, manifest)
    process_state = json.loads(blocks_data["process_state.json"])
    phantom_meta = json.loads(blocks_data["phantom_meta.json"])
    triage_block = TriageState.from_dict(
        json.loads(blocks_data["triage_state.json"])
    )

    # Step 5: classify required import mode
    actual_mode = _classify_required_mode(
        surface_status, triage_block, mode
    )

    if actual_mode == "reject":
        raise ValueError(
            f"bundle is tombstoned (triage_state=tombstoned); "
            f"reason={triage_block.triage_reason!r}"
        )

    # Step 6: forward-only fork — new session_id always
    new_id = _new_session_id()
    parent_id = phantom_meta["session_id_origin"]

    # Step 7: compose triage classification for the new session
    if actual_mode == "triage":
        if triage_block.triage_state == "quarantined":
            new_triage = triage_block
        else:
            reason_parts = []
            if surface_status in ("MISMATCH", "PARTIAL"):
                reason_parts.append(f"surface-{surface_status.lower()}")
            if mode == "triage":
                reason_parts.append("explicit-triage-mode")
            reason = " ".join(reason_parts) or "uncertain-provenance"
            new_triage = TriageState.quarantined(
                reason=reason,
                parent_ref=parent_id,
            )
    else:
        new_triage = TriageState(
            triage_state="trusted",
            triage_reason="clean import (verified TBZ + MATCH surface)",
            triage_disposition="auto-accept",
            triage_parent_ref=parent_id,
            continuity_class="phantom-resume",
            import_mode_required="either",
        )

    # Step 8: write new phantom vault entry
    new_session = {
        "session_id": new_id,
        "parent_session_id": parent_id,
        "imported_from": manifest.get("sender_aint"),
        "import_mode_used": actual_mode,
        "owner_did": receiver_did or phantom_meta.get("owner_did_origin"),
        "provider": phantom_meta.get("provider"),
        "backend": phantom_meta.get("backend"),
        "model": phantom_meta.get("model"),
        "status": ("sealed" if actual_mode == "normal"
                   else "quarantined"),
        "sealed_at": _now_iso8601(),
        "imported_at": _now_iso8601(),
        "l4_hash": phantom_meta.get("l4_hash"),
        "transcript": process_state.get("transcript", []),
        "context_data": process_state.get("context_data", {}),
        "todos": process_state.get("todos", []),
        "files": process_state.get("files", {}),
        **new_triage.to_dict(),
    }
    _write_phantom_session(new_session, vault)

    return ImportResult(
        new_session_id=new_id,
        parent_session_id=parent_id,
        mode_used=actual_mode,
        triage_state=new_triage,
        surface_status=surface_status,
        verify_errors=errors,
        bundle_path=bundle_path,
    )


# ─── Internal: low-level block read ─────────────────────────────


def _read_block_payloads(bundle_path: Path,
                          manifest: dict) -> dict[str, bytes]:
    """Return {block_name: content_bytes} for the bundle."""
    import struct
    raw = bundle_path.read_bytes()
    pos = 0
    _total = struct.unpack(">I", raw[pos:pos + 4])[0]
    pos += 4
    mlen = struct.unpack(">I", raw[pos:pos + 4])[0]
    pos += 4 + mlen  # skip manifest

    out: dict[str, bytes] = {}
    for spec in manifest.get("blocks", []):
        blen = struct.unpack(">I", raw[pos:pos + 4])[0]
        pos += 4
        out[spec["name"]] = raw[pos:pos + blen]
        pos += blen
    return out


# ─── Public API ─────────────────────────────────────────────────


__all__ = [
    "TriageState",
    "ImportResult",
    "PROVIDER_TO_PROFILE",
    "phantom_session_to_icc",
    "icc_to_phantom_session",
]
