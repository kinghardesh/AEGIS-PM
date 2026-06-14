"""
aegis-pm / api / embeddings.py

Async OpenAI embeddings with a persistent DB cache.

Design
──────
  - AsyncOpenAI client so calls don't block the event loop.
  - Cache key = sha256(model | normalised_text). Normalising means
    "React, Node.js" and " node.js,react " collapse to one entry.
  - `get_embedding_batch()` splits inputs into (cached, uncached), calls
    OpenAI ONCE for the uncached set (the API accepts a list input), and
    writes the results back with ON CONFLICT DO NOTHING so two parallel
    requesters don't collide.
  - If OPENAI_API_KEY is unset or the call fails, `get_embedding*` returns
    None; the matcher then falls back to keyword Jaccard. The system stays
    usable offline.
  - Timeouts: 10 s per call (configurable). Under load you'd raise this or
    move to a retry-with-backoff wrapper.

Never log the `text` argument — skill lists aren't secret but the
principle holds if this module is ever used for email bodies or similar.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = logging.getLogger("aegis.embeddings")

MODEL            = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_TIMEOUT = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "10"))
# Circuit breaker: after a failure, skip the API for this many seconds so
# a quota-dead key doesn't cost 3-5s of SDK retry per candidate in a loop.
CIRCUIT_COOLDOWN_SECONDS = float(os.getenv("EMBEDDING_CIRCUIT_COOLDOWN", "60"))

# Local fallback model (BAAI/bge-small-en-v1.5 = 384d). Loaded lazily on
# first use. The first load downloads ~128MB; subsequent loads are fast.
LOCAL_MODEL_NAME = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
LOCAL_ENABLED    = os.getenv("LOCAL_EMBEDDING_ENABLED", "true").lower() == "true"


# ── Client (lazy) ────────────────────────────────────────────────────────────

_client = None
_client_init_failed = False
_circuit_open_until: float = 0.0    # monotonic timestamp; 0 = closed


def _client_ok():
    """Return an AsyncOpenAI client or None if unavailable."""
    global _client, _client_init_failed
    if _client is not None:
        return _client
    if _client_init_failed:
        return None
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        _client_init_failed = True
        log.info("embeddings: OPENAI_API_KEY not set — semantic matching disabled")
        return None
    try:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=key, timeout=EMBEDDING_TIMEOUT)
        return _client
    except Exception as e:
        _client_init_failed = True
        log.warning("embeddings: client init failed: %s", e)
        return None


def is_available() -> bool:
    """True iff **some** embedding backend is usable right now.

    Priority: OpenAI (if circuit closed + key valid) > local fastembed > none.
    Callers use this as a go/no-go on the semantic path; matcher falls back
    to keyword when this is False.
    """
    import time as _t
    if _t.monotonic() >= _circuit_open_until and _client_ok() is not None:
        return True
    return _local_ok() is not None


def _trip_circuit() -> None:
    """Open the circuit — subsequent calls skip straight to keyword fallback."""
    global _circuit_open_until
    import time as _t
    _circuit_open_until = _t.monotonic() + CIRCUIT_COOLDOWN_SECONDS
    log.info("embeddings: circuit tripped for %.0fs", CIRCUIT_COOLDOWN_SECONDS)


# ── Hashing / normalisation ──────────────────────────────────────────────────

def _normalise(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _hash(text: str, model: str = MODEL) -> str:
    """
    Cache key = sha256(model|normalised_text). Parameterised on model so
    OpenAI and local-ONNX vectors don't collide (they have different
    dimensions and can't be compared to each other).
    """
    return hashlib.sha256(f"{model}|{_normalise(text)}".encode("utf-8")).hexdigest()


# ── Local model (fastembed, lazy) ────────────────────────────────────────────

_local_model = None
_local_init_failed = False


def _local_ok():
    """
    Return a fastembed TextEmbedding instance or None.

    First call imports + loads the model (heavy: ~128MB download on first
    run, then cached on disk). Subsequent calls are cheap. Failures are
    sticky within the process so we don't re-attempt every request.
    """
    global _local_model, _local_init_failed
    if _local_model is not None:
        return _local_model
    if _local_init_failed or not LOCAL_ENABLED:
        return None
    try:
        from fastembed import TextEmbedding   # type: ignore
    except ImportError:
        _local_init_failed = True
        log.info("embeddings: fastembed not installed — local fallback disabled")
        return None
    try:
        _local_model = TextEmbedding(model_name=LOCAL_MODEL_NAME)
        log.info("embeddings: local fallback ready (%s)", LOCAL_MODEL_NAME)
        return _local_model
    except Exception as e:
        _local_init_failed = True
        log.warning("embeddings: local model init failed: %s", e)
        return None


async def _embed_local_batch(texts: list[str]) -> list[list[float]] | None:
    """Run fastembed in a worker thread so the event loop stays free."""
    import asyncio
    model = _local_ok()
    if model is None:
        return None
    try:
        def _run():
            return [list(v) for v in model.embed(texts)]
        return await asyncio.to_thread(_run)
    except Exception as e:
        log.warning("embeddings: local embed failed: %s", type(e).__name__)
        return None


# ── Single + batch fetch ─────────────────────────────────────────────────────

async def get_embedding(text: str) -> Optional[list[float]]:
    results = await get_embedding_batch([text])
    return results[0] if results else None


async def get_embedding_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Three-tier lookup:

      1. DB cache by (model|text) hash — both OpenAI and local vectors
         share this table; keys don't collide because the `model` byte is
         part of the hash.
      2. OpenAI remote (if circuit closed + key valid).
      3. Local fastembed (if installed + model loadable).

    Returns a list the same length as `texts`, with `None` where both
    remote and local failed — callers (matcher) then fall back to keyword.
    """
    import time as _t
    from api.main import SessionLocal
    from api.models import embeddings_cache_table

    # Decide which model tag drives this batch. When the circuit is open or
    # no OpenAI client, we switch to the local model tag so cache lookups
    # hit local vectors (which have different dimensions).
    use_remote = (
        _t.monotonic() >= _circuit_open_until and _client_ok() is not None
    )
    active_model = MODEL if use_remote else LOCAL_MODEL_NAME

    hashes: list[Optional[str]] = [
        _hash(t, active_model) if t and t.strip() else None for t in texts
    ]
    results: list[Optional[list[float]]] = [None] * len(texts)

    # 1) Cache lookup.
    wanted = [h for h in hashes if h]
    cached: dict[str, list[float]] = {}
    if wanted:
        async with SessionLocal() as db:
            rows = (await db.execute(
                sa.select(
                    embeddings_cache_table.c.text_hash,
                    embeddings_cache_table.c.embedding,
                ).where(embeddings_cache_table.c.text_hash.in_(wanted))
            )).all()
            cached = {h: emb for (h, emb) in rows}

    # 2) Partition missing indexes (dedupe identical texts across inputs).
    missing_indexes: dict[str, list[int]] = {}
    for idx, h in enumerate(hashes):
        if h is None:
            continue
        if h in cached:
            results[idx] = cached[h]
            continue
        missing_indexes.setdefault(h, []).append(idx)

    if not missing_indexes:
        return results

    missing_hashes = list(missing_indexes.keys())
    missing_texts = [
        _normalise(texts[missing_indexes[h][0]]) for h in missing_hashes
    ]

    vectors: list[list[float]] | None = None
    used_model = active_model

    # 3a) Try OpenAI if the circuit is closed and a client exists.
    if use_remote:
        client = _client_ok()
        try:
            resp = await client.embeddings.create(model=MODEL, input=missing_texts)
            vectors = [d.embedding for d in resp.data]
        except Exception as e:
            _trip_circuit()
            log.warning(
                "embeddings: remote batch failed (%d uncached); "
                "trying local fallback: %s",
                len(missing_texts), type(e).__name__,
            )
            vectors = None

    # 3b) Local fastembed fallback.
    if vectors is None:
        local_vecs = await _embed_local_batch(missing_texts)
        if local_vecs is not None:
            vectors = local_vecs
            used_model = LOCAL_MODEL_NAME
            # Rewrite hashes so we cache + fetch under the local tag.
            relabelled = [_hash(t, LOCAL_MODEL_NAME) for t in missing_texts]
            new_missing: dict[str, list[int]] = {}
            for old_h, new_h, t in zip(missing_hashes, relabelled, missing_texts):
                new_missing[new_h] = missing_indexes[old_h]
            missing_hashes = relabelled
            missing_indexes = new_missing

    if vectors is None:
        # Both remote and local failed — caller will use keyword path.
        return results

    # 4) Write back to cache + fill results.
    rows_to_insert = [
        {"text_hash": h, "model": used_model, "embedding": vec}
        for h, vec in zip(missing_hashes, vectors)
    ]
    try:
        async with SessionLocal() as db:
            stmt = pg_insert(embeddings_cache_table).on_conflict_do_nothing(
                index_elements=["text_hash"]
            )
            await db.execute(stmt, rows_to_insert)
            await db.commit()
    except Exception as e:
        log.debug("embeddings: cache write skipped: %s", e)

    for h, vec in zip(missing_hashes, vectors):
        for idx in missing_indexes[h]:
            results[idx] = vec

    return results


# ── Cosine similarity ────────────────────────────────────────────────────────

def cosine(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na  = 0.0
    nb  = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na  += x * x
        nb  += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
