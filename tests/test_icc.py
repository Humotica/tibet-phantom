"""Tests for phantom.icc — Phantom ↔ ICC bridge.

Spec: /srv/jtel-stack/hersenspinsels/phantom-icc-as-triage-bearing-continuity.md

Four scenarios per spec §8:
1. Bundle valid + surface MATCH         → mode=normal, trusted session
2. Bundle valid + surface MISMATCH      → forced mode=triage, quarantined
3. Caller mode=triage explicitly        → quarantined regardless of MATCH
4. Double import = two distinct session_ids (forward-only fork verified)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Bridge to airdrop-cli source for crypto primitives in tests
_TIBET_DROP_SRC = Path("/srv/jtel-stack/sandbox/airdrop-cli/src")
if str(_TIBET_DROP_SRC) not in sys.path:
    sys.path.insert(0, str(_TIBET_DROP_SRC))

# Bridge to tibet-phantom local package
_TIBET_PHANTOM_ROOT = Path("/srv/jtel-stack/packages/tibet-phantom")
if str(_TIBET_PHANTOM_ROOT) not in sys.path:
    sys.path.insert(0, str(_TIBET_PHANTOM_ROOT))

from tibet_drop.crypto import IdentityKey  # noqa: E402

from phantom.icc import (  # noqa: E402
    TriageState,
    icc_to_phantom_session,
    phantom_session_to_icc,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def alice_bob():
    return IdentityKey.generate(), IdentityKey.generate()


@pytest.fixture
def vault_with_session(tmp_path):
    """Create a fake phantom vault with one sealed Claude session."""
    vault = tmp_path / "vault"
    vault.mkdir()
    session_id = "phantom-1746789012-abc123"
    session_data = {
        "session_id": session_id,
        "owner_did": "jis:pixel:jasper",
        "provider": "claude",
        "backend": "vertex-claude",
        "model": "claude-opus-4-7@default",
        "status": "sealed",
        "sealed_at": "2026-05-09T10:00:00Z",
        "l4_hash": "a" * 64,
        "transcript": [
            {"role": "user", "content": "Test the bridge"},
            {"role": "assistant", "content": "Bridge tested."},
        ],
        "context_data": {"client": "test-suite"},
        "todos": [{"content": "verify forward-only", "status": "pending"}],
    }
    (vault / f"{session_id}.json").write_text(json.dumps(session_data))
    return vault, session_id


# ─── Scenario 1: normal happy path ──────────────────────────────


def test_normal_match_creates_trusted_session(alice_bob, vault_with_session):
    alice, bob = alice_bob
    vault, session_id = vault_with_session

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)

        # Export
        manifest = phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            vault=vault,
        )

        # File should exist with surface-aware name
        bundle_path = next(out_dir.glob("*.tza"))
        assert "session-resume" in bundle_path.name
        assert ".claude." in bundle_path.name
        assert ".normal." in bundle_path.name

        # Manifest has correct surface fields
        assert manifest["surface_profile"] == "claude"
        assert manifest["surface_context"] == "session-resume"
        assert manifest["surface_priority"] == "normal"
        assert manifest["payload_type"] == "ai_state"
        assert manifest["block_count"] == 4  # 3 blocks + manifest

        # Import (mode normal, surface MATCH)
        recv_vault = Path(td) / "recv_vault"
        result = icc_to_phantom_session(
            bundle_path=bundle_path,
            mode="normal",
            vault=recv_vault,
        )

        assert result.surface_status == "MATCH"
        assert result.mode_used == "normal"
        assert result.triage_state.triage_state == "trusted"
        assert result.triage_state.continuity_class == "phantom-resume"
        assert result.parent_session_id == session_id
        assert result.new_session_id != session_id

        # New session is in vault, status sealed
        new_path = recv_vault / f"{result.new_session_id}.json"
        assert new_path.exists()
        new_session = json.loads(new_path.read_text())
        assert new_session["status"] == "sealed"
        assert new_session["parent_session_id"] == session_id
        assert new_session["transcript"] == [
            {"role": "user", "content": "Test the bridge"},
            {"role": "assistant", "content": "Bridge tested."},
        ]


# ─── Scenario 2: surface MISMATCH forces triage ─────────────────


def test_surface_mismatch_forces_triage(alice_bob, vault_with_session):
    alice, bob = alice_bob
    vault, session_id = vault_with_session

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)

        phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            priority="urgent",
            vault=vault,
        )
        bundle_path = next(out_dir.glob("*.tza"))

        # Adversary renames urgent → normal, profile claude → gemini
        attacker_name = bundle_path.name.replace(
            ".urgent.", ".normal.").replace(".claude.", ".gemini.")
        renamed = bundle_path.parent / attacker_name
        bundle_path.rename(renamed)

        # Caller asks normal mode — but surface MISMATCH escalates to triage
        recv_vault = Path(td) / "recv_vault"
        result = icc_to_phantom_session(
            bundle_path=renamed,
            mode="normal",
            vault=recv_vault,
        )

        assert result.surface_status == "MISMATCH"
        assert result.mode_used == "triage"  # silent escalation
        assert result.triage_state.triage_state == "quarantined"
        assert result.triage_state.continuity_class == \
            "phantom-resume-triage"
        assert "surface-mismatch" in result.triage_state.triage_reason

        # New session is quarantined in vault
        new_session = json.loads(
            (recv_vault / f"{result.new_session_id}.json").read_text()
        )
        assert new_session["status"] == "quarantined"
        assert new_session["triage_disposition"] == "operator-review"


# ─── Scenario 3: explicit triage mode ───────────────────────────


def test_explicit_triage_mode(alice_bob, vault_with_session):
    alice, bob = alice_bob
    vault, session_id = vault_with_session

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            vault=vault,
        )
        bundle_path = next(out_dir.glob("*.tza"))

        # Surface MATCH but caller wants triage
        recv_vault = Path(td) / "recv_vault"
        result = icc_to_phantom_session(
            bundle_path=bundle_path,
            mode="triage",
            vault=recv_vault,
        )

        assert result.surface_status == "MATCH"  # surface itself is fine
        assert result.mode_used == "triage"      # but caller forced
        assert result.triage_state.triage_state == "quarantined"
        assert "explicit-triage-mode" in \
            result.triage_state.triage_reason


# ─── Scenario 4: double import = two distinct sessions ──────────


def test_double_import_forward_only_fork(alice_bob, vault_with_session):
    """Import the same bundle twice — must produce two new session_ids."""
    alice, bob = alice_bob
    vault, session_id = vault_with_session

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            vault=vault,
        )
        bundle_path = next(out_dir.glob("*.tza"))

        recv_vault = Path(td) / "recv_vault"
        r1 = icc_to_phantom_session(bundle_path, vault=recv_vault)
        r2 = icc_to_phantom_session(bundle_path, vault=recv_vault)

        # Forward-only invariant: distinct new IDs
        assert r1.new_session_id != r2.new_session_id
        # Both share the same parent (the original sealed session)
        assert r1.parent_session_id == r2.parent_session_id == session_id

        # Both vault entries exist, both trusted
        assert (recv_vault / f"{r1.new_session_id}.json").exists()
        assert (recv_vault / f"{r2.new_session_id}.json").exists()


# ─── Scenario 5: tombstoned bundle is rejected ──────────────────


def test_tombstoned_bundle_rejected(alice_bob, vault_with_session):
    alice, bob = alice_bob
    vault, session_id = vault_with_session

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)

        phantom_session_to_icc(
            session_id=session_id,
            sender_aint="alice.aint",
            sender_signer=alice,
            receiver_aint="bob.aint",
            receiver_pubkey_hex=bob.pub_bytes().hex(),
            output_path=out_dir,
            triage=TriageState(
                triage_state="tombstoned",
                triage_reason="superseded by successor",
                triage_disposition="reject",
                continuity_class="phantom-resume",
                import_mode_required="triage",
            ),
            vault=vault,
        )
        bundle_path = next(out_dir.glob("*.tza"))

        recv_vault = Path(td) / "recv_vault"
        with pytest.raises(ValueError, match="tombstoned"):
            icc_to_phantom_session(
                bundle_path=bundle_path,
                vault=recv_vault,
            )


# ─── Scenario 6: provider → profile mapping ─────────────────────


@pytest.mark.parametrize("provider,expected_profile", [
    ("claude", "claude"),
    ("gemini", "gemini"),
    ("gpt", "gpt"),
    ("humotica-32b", "kit"),
    ("qwen2.5:7b", "kit"),
    ("unknown-model", "tza"),
])
def test_provider_to_profile_mapping(
    alice_bob, tmp_path, provider, expected_profile
):
    alice, bob = alice_bob
    vault = tmp_path / "vault"
    vault.mkdir()
    sid = f"phantom-test-{provider.replace(':', '-')}"
    (vault / f"{sid}.json").write_text(json.dumps({
        "session_id": sid,
        "provider": provider,
        "transcript": [],
        "context_data": {},
    }))

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    phantom_session_to_icc(
        session_id=sid,
        sender_aint="alice.aint",
        sender_signer=alice,
        receiver_aint="bob.aint",
        receiver_pubkey_hex=bob.pub_bytes().hex(),
        output_path=out_dir,
        vault=vault,
    )
    bundle_path = next(out_dir.glob("*.tza"))
    assert f".{expected_profile}." in bundle_path.name
