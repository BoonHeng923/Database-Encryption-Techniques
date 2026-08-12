"""The secret real/decoy identification function (plan B.4.1) -- the "formula".

    id(i)      = HMAC_SHA256(k, "id"  || i)                       (truncated to ID_LENGTH)
    isDecoy(i) = 1  if  ( HMAC_SHA256(k, "tag" || i) mod (d + 1) ) == 0
                 0  otherwise

`k` is a secret key held only by the client and never sent to the server. Records are
created in a fixed sequence with a counter `i = 0, 1, 2, ...`; for each `i` the client
derives both the server-visible identifier and the real/decoy status from `k` and `i`.
Because both real and decoy identifiers come from the *same* formula `id(i)`, they are
drawn from the same space and are indistinguishable on the server -- only the separate,
secret `isDecoy(i)` bit (never stored) tells them apart. `d` sets the decoy ratio: on
average 1 decoy for every `d` real records.

Without `k`, HMAC_SHA256 output is computationally indistinguishable from random, so an
attacker who does not hold the key sees a uniform pool of random-looking identifiers and
cannot recompute `isDecoy`, cannot tell which records are real, and cannot filter.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Iterator

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.core import config

ID_LENGTH = 16  # bytes


def _collection_key(collection: str | None) -> bytes:
    """Optionally re-derive the decoy master key per collection (via HKDF) so decoy
    placement differs per collection too, matching Approach D's per-collection design."""
    if collection is None:
        return config.DECOY_MASTER_KEY
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"encbench-decoy-{collection}".encode())
    return hkdf.derive(config.DECOY_MASTER_KEY)


def id_of(k: bytes, i: int) -> bytes:
    return hmac.new(k, b"id" + i.to_bytes(8, "big"), hashlib.sha256).digest()[:ID_LENGTH]


def _raw_decoy(k: bytes, i: int, d: int) -> bool:
    if d <= 0:
        return False
    digest = hmac.new(k, b"tag" + i.to_bytes(8, "big"), hashlib.sha256).digest()
    value = int.from_bytes(digest, "big")
    return (value % (d + 1)) == 0


def _decoy_params(n_real: int, n_decoy: int) -> tuple[int, bool]:
    """`isDecoy(i) = HMAC mod (d+1) == 0` has P(decoy) = 1/(d+1), which can only represent
    decoy fractions <= 1/2 for integer d >= 1 -- fine when decoys are the rarer class
    (d = reals-per-decoy) but not when a heavily-skewed value needs *more* decoys than
    reals (e.g. flattening a minority category up toward the majority's count can need
    50x as many decoys as real records). Below, `invert` swaps which outcome of the same
    formula counts as "decoy" so d can represent whichever class is rarer, keeping P(decoy)
    accurate in both directions instead of floor(d, 1) silently producing far too few
    decoys for exactly the skewed values the flattening is supposed to fix."""
    if n_decoy <= 0:
        return 0, False
    if n_real <= 0:
        return 0, True
    if n_decoy <= n_real:
        return max(1, round(n_real / n_decoy)), False
    return max(1, round(n_decoy / n_real)), True


def is_decoy(k: bytes, i: int, d: int, invert: bool = False) -> bool:
    raw = _raw_decoy(k, i, d)
    return (not raw) if invert else raw


@dataclass
class SecretIdEntry:
    i: int
    id_bytes: bytes
    is_decoy: bool


def iter_ids(n_real: int, n_decoy: int, collection: str | None = None, start: int = 0) -> Iterator[SecretIdEntry]:
    """Walk the counter from `start`, yielding one entry per index whose class (real or
    decoy) still has quota remaining, until both `n_real` real and `n_decoy` decoy entries
    have been produced. `d` (see `_decoy_params`) is derived internally from the two
    targets so P(is_decoy) matches the true n_decoy/(n_real+n_decoy) ratio regardless of
    which class is larger -- callers consume this generator and, for each entry, store a
    real or decoy record under `id_of(k, i)` accordingly."""
    k = _collection_key(collection)
    d, invert = _decoy_params(n_real, n_decoy)
    produced_real = 0
    produced_decoy = 0
    i = start
    while produced_real < n_real or produced_decoy < n_decoy:
        decoy = is_decoy(k, i, d, invert)
        if decoy and produced_decoy < n_decoy:
            yield SecretIdEntry(i=i, id_bytes=id_of(k, i), is_decoy=True)
            produced_decoy += 1
        elif not decoy and produced_real < n_real:
            yield SecretIdEntry(i=i, id_bytes=id_of(k, i), is_decoy=False)
            produced_real += 1
        # else: this slot's class already met its quota -- skip without yielding, counter
        # still advances so the id space stays a single deterministic sequence.
        i += 1


def real_ids(returned_ids: list[bytes], n_real: int, n_decoy: int, collection: str | None = None) -> set[bytes]:
    """Client-side filter: recompute id(i)/isDecoy(i) for the same (n_real, n_decoy)
    targets used to create the records, and return the subset of `returned_ids` that are
    real. This is the operation the legitimate client performs to keep reals and drop
    decoys from a query's result set; an attacker without `k` cannot perform it."""
    k = _collection_key(collection)
    d, invert = _decoy_params(n_real, n_decoy)
    returned = set(returned_ids)
    reals: set[bytes] = set()
    produced_real = 0
    produced_decoy = 0
    i = 0
    while produced_real < n_real or produced_decoy < n_decoy:
        decoy = is_decoy(k, i, d, invert)
        if decoy and produced_decoy < n_decoy:
            produced_decoy += 1
        elif not decoy and produced_real < n_real:
            candidate = id_of(k, i)
            if candidate in returned:
                reals.add(candidate)
            produced_real += 1
        i += 1
    return reals
