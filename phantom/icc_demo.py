"""End-to-end demo: Phantom session → ICC bundle → resumed phantom session.

Demonstrates the v0.2 bridge:
  STEP 1 — A claude session is sealed in Alice's vault
  STEP 2 — Export as .claude.tza ICC bundle (TBZ-sealed)
  STEP 3 — Bob normally imports → trusted forked session
  STEP 4 — Adversary renames bundle (urgent → normal, claude → gemini)
  STEP 5 — Bob imports renamed bundle → AUTOMATIC triage escalation
  STEP 6 — Bob imports original twice → two distinct forked sessions

Forward-only causal substrate is shown live:
  resume = fork (always new session_id, never restore)
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

_TIBET_DROP_SRC = Path("/srv/jtel-stack/sandbox/airdrop-cli/src")
if str(_TIBET_DROP_SRC) not in sys.path:
    sys.path.insert(0, str(_TIBET_DROP_SRC))
_TIBET_PHANTOM_ROOT = Path("/srv/jtel-stack/packages/tibet-phantom")
if str(_TIBET_PHANTOM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TIBET_PHANTOM_ROOT))

from tibet_drop.crypto import IdentityKey  # noqa: E402

from phantom.icc import (  # noqa: E402
    icc_to_phantom_session,
    phantom_session_to_icc,
)


def run_demo() -> int:
    print()
    print("═" * 64)
    print("  PHANTOM ↔ ICC BRIDGE — End-to-End Demo")
    print("  (v0.2: sealed process-state + triage-aware fork)")
    print("═" * 64)

    alice = IdentityKey.generate()
    bob = IdentityKey.generate()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        alice_vault = tmp / "alice_vault"
        alice_vault.mkdir()
        bob_vault = tmp / "bob_vault"

        # ─── STEP 1 — sealed Phantom session ──────────────────
        print()
        print("STEP 1 — Alice has a sealed Claude session in her vault")
        session_id = f"phantom-{int(time.time())}-claude01"
        session = {
            "session_id": session_id,
            "owner_did": "jis:pixel:alice",
            "provider": "claude",
            "backend": "vertex-claude",
            "model": "claude-opus-4-7@default",
            "status": "sealed",
            "sealed_at": "2026-05-09T10:00:00Z",
            "l4_hash": "a" * 64,
            "transcript": [
                {"role": "user", "content": "We're shipping Phantom v0.2 today."},
                {"role": "assistant",
                 "content": "Forward-only causal substrate confirmed."},
                {"role": "user", "content": "Demo it for Marco maandag."},
            ],
            "context_data": {"sprint": "phantom-v0.2", "marco_call": "11 mei"},
            "todos": [
                {"content": "Test bridge round-trip", "status": "completed"},
                {"content": "Show Marco the triage escalation",
                 "status": "pending"},
            ],
        }
        (alice_vault / f"{session_id}.json").write_text(json.dumps(session))
        print(f"  ✓ session_id   : {session_id}")
        print(f"  ✓ provider     : claude (vertex-claude)")
        print(f"  ✓ transcript   : {len(session['transcript'])} turns")

        # ─── STEP 2 — export as .claude.tza ────────────────────
        print()
        print("STEP 2 — Export to .claude.tza ICC bundle")
        out_dir = tmp / "transit"
        out_dir.mkdir()
        manifest = phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            vault=alice_vault,
        )
        bundle_path = next(out_dir.glob("*.tza"))
        print(f"  ✓ filename     : {bundle_path.name}")
        print(f"  ✓ size         : {bundle_path.stat().st_size} bytes")
        print(f"  ✓ surface_*    : {manifest['surface_time_fragment']} / "
              f"{manifest['surface_context']} / "
              f"{manifest['surface_profile']} / "
              f"{manifest['surface_priority']}")
        print(f"  ✓ blocks       : {manifest['block_count']} "
              f"(manifest + 3 payload blocks)")

        # ─── STEP 3 — normal import (MATCH) ────────────────────
        print()
        print("STEP 3 — Bob imports normally (surface MATCH)")
        r1 = icc_to_phantom_session(
            bundle_path=bundle_path,
            mode="normal",
            vault=bob_vault,
        )
        print(f"  ✓ surface      : {r1.surface_status}")
        print(f"  ✓ mode used    : {r1.mode_used}")
        print(f"  ✓ triage state : {r1.triage_state.triage_state}")
        print(f"  ✓ continuity   : {r1.triage_state.continuity_class}")
        print(f"  ✓ NEW session  : {r1.new_session_id}")
        print(f"  ✓ parent       : {r1.parent_session_id}")
        print(f"  ✓ session != parent (forward-only fork): "
              f"{r1.new_session_id != r1.parent_session_id}")

        # ─── STEP 4 — adversary rename ─────────────────────────
        print()
        print("STEP 4 — Adversary renames bundle (rename-attack)")
        attack_name = bundle_path.name \
            .replace(".normal.", ".urgent.") \
            .replace(".claude.", ".gemini.")
        attacker_path = bundle_path.parent / attack_name
        bundle_path.rename(attacker_path)
        print(f"  Original : {bundle_path.name}")
        print(f"  Renamed  : {attacker_path.name}")
        print(f"  Changes  : priority normal→urgent, profile claude→gemini")

        # ─── STEP 5 — auto-triage on import ────────────────────
        print()
        print("STEP 5 — Bob imports renamed bundle (mode=normal)")
        print("         …spec §6+§8 say: surface MISMATCH escalates "
              "automatically to triage")
        r2 = icc_to_phantom_session(
            bundle_path=attacker_path,
            mode="normal",  # caller asks normal, surface forces triage
            vault=bob_vault,
        )
        print(f"  ✓ surface      : {r2.surface_status}")
        print(f"  ✓ mode used    : {r2.mode_used}  "
              "(silent escalation, no exception)")
        print(f"  ✓ triage state : {r2.triage_state.triage_state}")
        print(f"  ✓ disposition  : {r2.triage_state.triage_disposition}")
        print(f"  ✓ reason       : {r2.triage_state.triage_reason}")
        print(f"  ✓ continuity   : {r2.triage_state.continuity_class}")
        print(f"  ✓ NEW session  : {r2.new_session_id}")

        # Verify quarantined session is visible AND distinct
        q_session = json.loads(
            (bob_vault / f"{r2.new_session_id}.json").read_text()
        )
        print(f"  ✓ vault status : {q_session['status']}")
        print(f"    → operator must approve / reject / tombstone")

        # ─── STEP 6 — double import is two new sessions ────────
        print()
        print("STEP 6 — Forward-only causal substrate proof")
        print("         Restore original filename and import twice.")
        attacker_path.rename(bundle_path)  # restore
        r3 = icc_to_phantom_session(bundle_path, vault=bob_vault)
        r4 = icc_to_phantom_session(bundle_path, vault=bob_vault)
        print(f"  ✓ first import  : {r3.new_session_id}")
        print(f"  ✓ second import : {r4.new_session_id}")
        print(f"  ✓ distinct      : {r3.new_session_id != r4.new_session_id}")
        print(f"  ✓ shared parent : "
              f"{r3.parent_session_id == r4.parent_session_id}")
        print()
        print("  Resume = fork. Never restore.")

        # ─── Summary ───────────────────────────────────────────
        print()
        print("═" * 64)
        print("  ✓ PHANTOM ICC BRIDGE COMPLETE")
        print("═" * 64)
        sessions = sorted(bob_vault.glob("*.json"))
        print(f"  Bob's vault: {len(sessions)} forked sessions, all from "
              f"one parent {session_id}")
        print()
        print("  Five primitives composed:")
        print("    ✓ TIBET    forward-only causal fork")
        print("    ✓ TBZ      sealed bundle (Ed25519 + per-block sigs)")
        print("    ✓ SSM      surface-aware filename + manifest mirror")
        print("    ✓ ICC      identity-bound continuity container")
        print("    ✓ Triage   first-class quarantine for mismatch")
        print()
        print('  "Phantom is not just a web function;')
        print('   it is a resumable triage-bearing continuity layer."')
        print()

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
