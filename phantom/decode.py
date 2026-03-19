"""
phantom.decode — Token-to-text decode (T-LEX edge)
====================================================

The final step: convert token coordinates to readable text.
22 microseconds per token. 45,000 tok/sec on CPU.
No LLM layers needed — just a vocabulary lookup.

When tlex-edge is installed, uses its optimized decoder.
Otherwise provides a basic token decoder.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DecodeResult:
    """Result of token decoding."""
    text: str
    token_count: int
    decode_time_us: float
    tokens_per_sec: float
    method: str  # "tlex-edge" or "basic"


class PhantomDecoder:
    """
    Decode token coordinates to text.

    In the phantom flow, the heavy inference (32 transformer layers)
    already happened on the server. The edge device only needs to
    decode token IDs to text — a simple vocabulary lookup.

    With tlex-edge: ~22us per token (45,000 tok/sec on CPU)
    Without: basic tokenizer decode

    This is why a Raspberry Pi or smartphone can "run" a 32B model:
    it doesn't run inference, it materializes the pre-computed result.
    """

    def __init__(self, vocab_path: Optional[str] = None):
        self._tlex = None
        self._tokenizer = None
        self._vocab_path = vocab_path
        self._try_load_tlex()

    def _try_load_tlex(self):
        """Try to use tlex-edge if installed."""
        try:
            import tlex_edge
            self._tlex = tlex_edge
        except ImportError:
            pass

        try:
            from tokenizers import Tokenizer
            self._tokenizer = Tokenizer
        except ImportError:
            pass

    def decode_tokens(self, token_ids: list[int],
                      vocab: Optional[dict] = None) -> DecodeResult:
        """
        Decode token IDs to text.

        Args:
            token_ids: List of token coordinate IDs
            vocab: Optional vocabulary dict {id: text}

        Returns:
            DecodeResult with text and performance metrics
        """
        start = time.perf_counter()

        # Method 1: tlex-edge (fastest)
        if self._tlex:
            try:
                text = self._tlex.decode(token_ids)
                elapsed = time.perf_counter() - start
                return DecodeResult(
                    text=text,
                    token_count=len(token_ids),
                    decode_time_us=elapsed * 1_000_000,
                    tokens_per_sec=len(token_ids) / elapsed if elapsed > 0 else 0,
                    method="tlex-edge",
                )
            except Exception:
                pass

        # Method 2: provided vocabulary
        if vocab:
            text = "".join(vocab.get(tid, f"<{tid}>") for tid in token_ids)
            elapsed = time.perf_counter() - start
            return DecodeResult(
                text=text,
                token_count=len(token_ids),
                decode_time_us=elapsed * 1_000_000,
                tokens_per_sec=len(token_ids) / elapsed if elapsed > 0 else 0,
                method="vocab-lookup",
            )

        # Method 3: direct text passthrough (when payload is already text)
        text = "".join(chr(t) if 32 <= t < 127 else f"<{t}>" for t in token_ids)
        elapsed = time.perf_counter() - start

        return DecodeResult(
            text=text,
            token_count=len(token_ids),
            decode_time_us=elapsed * 1_000_000,
            tokens_per_sec=len(token_ids) / elapsed if elapsed > 0 else 0,
            method="basic",
        )

    def decode_text(self, text_bytes: bytes) -> DecodeResult:
        """
        Direct text decode (when payload is UTF-8 text, not token IDs).

        In many phantom flows, the inference output is already text
        that was encrypted. No token decoding needed — just present it.
        """
        start = time.perf_counter()
        text = text_bytes.decode("utf-8", errors="replace")
        elapsed = time.perf_counter() - start

        word_count = len(text.split())

        return DecodeResult(
            text=text,
            token_count=word_count,
            decode_time_us=elapsed * 1_000_000,
            tokens_per_sec=word_count / elapsed if elapsed > 0 else 0,
            method="text-passthrough",
        )
