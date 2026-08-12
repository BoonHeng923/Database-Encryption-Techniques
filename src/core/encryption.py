"""Client-side encryption layer, shared by every storage adapter (engine-independent).

Two primitives, matching plan section B.4:

- `deterministic_token(value, key=None)` — AES-SIV (RFC 5297) deterministic authenticated
  encryption of the sensitive field. Same plaintext -> same ciphertext, so the server
  can index/query it by equality. This is the "Approach B" property-preserving
  encryption (the deterministic-AES leg CryptDB calls its DET onion). Approaches B and C
  always use the single global key (`derive_token_key(None)`), so the same value tokenises
  to the same bytes everywhere -- this is *why* B/C leak cross-collection linkage (plan
  B.7 point 2). Approach D uses a distinct per-collection key (`derive_token_key(collection)`)
  for the link field and the sensitive field, so the same value tokenises differently in
  `patients`, `lab_orders`, and `billing` -- breaking that linkage.
- `encrypt_payload(value)` / `decrypt_payload(...)` — AES-GCM with a random nonce per
  call, i.e. semantically secure (non-deterministic) encryption for every field that is
  *not* queried. This is what actually protects patient data at rest; only the queried
  fields go through the weaker deterministic scheme, mirroring how property-preserving
  encryption is used in practice (only on columns that must support server-side queries).
"""
from __future__ import annotations

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM, AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from src.core import config


def _derive_key(master_key: bytes, info: bytes, length: int) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info)
    return hkdf.derive(master_key)


_GCM_KEY = _derive_key(config.ENC_MASTER_KEY, b"encbench-gcm-payload-key", 32)
_gcm = AESGCM(_GCM_KEY)

_token_key_cache: dict[str | None, bytes] = {}


def derive_token_key(collection: str | None = None) -> bytes:
    """SIV key (64 bytes) for tokenising a value.

    `collection=None` -> today's single global key, shared by every collection (used by
    Approaches B and C, and by D for non-linking fields). `collection="patients"` etc.
    -> a distinct key per collection (info=f"encbench-siv-{collection}"), used by
    Approach D for `patient_code` (and the sensitive field) so the same value tokenises
    differently per collection.
    """
    if collection not in _token_key_cache:
        info = b"encbench-siv-token-key" if collection is None else f"encbench-siv-{collection}".encode()
        _token_key_cache[collection] = _derive_key(config.ENC_MASTER_KEY, info, 64)
    return _token_key_cache[collection]


def deterministic_token(value: str, key: bytes | None = None) -> bytes:
    """Deterministic ciphertext of `value`, usable as an equality-searchable token."""
    siv_key = key if key is not None else derive_token_key(None)
    return AESSIV(siv_key).encrypt(value.encode("utf-8"), associated_data=None)


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


_NAME_TOKEN_CACHE: dict[str, str] = {}


def tokenize_name(name: str) -> str:
    """Opaque collection/field name (plan B.4 layer 4, e.g. `col_9f3a`) derived from a
    client-held HMAC map. Demonstrated, not scored -- structural metadata only."""
    import hmac
    import hashlib

    if name not in _NAME_TOKEN_CACHE:
        digest = hmac.new(config.ENC_MASTER_KEY, b"name" + name.encode(), hashlib.sha256).hexdigest()
        _NAME_TOKEN_CACHE[name] = f"col_{digest[:8]}"
    return _NAME_TOKEN_CACHE[name]
