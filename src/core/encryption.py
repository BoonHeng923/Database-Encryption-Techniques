"""Client-side encryption layer, shared by every storage adapter (engine-independent).

Two primitives, matching plan section B.4:

- `deterministic_token(value)` — AES-SIV (RFC 5297) deterministic authenticated
  encryption of the sensitive field. Same plaintext -> same ciphertext, so the server
  can index/query it by equality. This is the "Approach B" property-preserving
  encryption (the deterministic-AES leg CryptDB calls its DET onion). Both Approach B
  and Approach C use this same token function for the queried field, so any leakage
  difference between B and C comes purely from Approach C's volume-hiding padding, not
  from a different crypto primitive.
- `encrypt_payload(value)` / `decrypt_payload(...)` — AES-GCM with a random nonce per
  call, i.e. semantically secure (non-deterministic) encryption for every field that is
  *not* queried. This is what actually protects patient data at rest; only the one
  sensitive, queried field goes through the weaker deterministic scheme, mirroring how
  property-preserving encryption is used in practice (only on columns that must support
  server-side queries).
"""
from __future__ import annotations

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from src.core import config


def _derive_key(info: bytes, length: int) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info)
    return hkdf.derive(config.ENC_MASTER_KEY)


_SIV_KEY = _derive_key(b"encbench-siv-token-key", 64)  # AES-SIV needs a double-length key
_GCM_KEY = _derive_key(b"encbench-gcm-payload-key", 32)

_siv = AESSIV(_SIV_KEY)
_gcm = AESGCM(_GCM_KEY)


def deterministic_token(value: str) -> bytes:
    """Deterministic ciphertext of `value`, usable as an equality-searchable token."""
    return _siv.encrypt(value.encode("utf-8"), associated_data=None)


def encrypt_payload(fields: dict) -> bytes:
    """Semantically-secure encryption of the non-queried fields of a record."""
    plaintext = json.dumps(fields, default=str).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = _gcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_payload(blob: bytes) -> dict:
    nonce, ciphertext = blob[:12], blob[12:]
    plaintext = _gcm.decrypt(nonce, ciphertext, associated_data=None)
    return json.loads(plaintext.decode("utf-8"))
