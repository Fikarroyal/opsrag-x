"""Embedding providers.

* SentenceTransformerEmbedder - default when `sentence-transformers` and the model are available.
* HashingEmbedder            - deterministic, dependency-free lexical fallback (feature hashing of
                               normalised unigrams+bigrams). Used when the model cannot be loaded
                               (offline, CI, first boot) so RAG keeps working.

Every stored vector records the embedder `name`; the retriever only compares vectors produced by the
same embedder and otherwise falls back to keyword (TF-IDF) retrieval.
"""

from __future__ import annotations

import itertools
import logging
import re
import zlib
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)

# domain normalisation so Indonesian/English phrasings of the same idea share features
_NORMALISE = {
    "tidak": "not",
    "nggak": "not",
    "gak": "not",
    "cannot": "not",
    "cant": "not",
    "unable": "not",
    "gagal": "fail",
    "bisa": "can",
    "dapat": "can",
    "komputer": "pc",
    "computer": "pc",
    "komputer-komputer": "pc",
    "pcs": "pc",
    "terputus": "disconnect",
    "putus": "disconnect",
    "putus-putus": "intermittent",
    "offline": "disconnect",
    "lambat": "slow",
    "lemot": "slow",
    "slowness": "slow",
    "timeout": "timeout",
    "timedout": "timeout",
    "dibuka": "open",
    "membuka": "open",
    "buka": "open",
    "akses": "access",
    "mengakses": "access",
    "diakses": "access",
    "aplikasi": "app",
    "application": "app",
    "jaringan": "network",
    "koneksi": "connection",
    "terhubung": "connect",
    "konek": "connect",
    "server": "server",
    "unit": "unit",
    "beberapa": "several",
    "semua": "all",
    "seluruh": "all",
    "resolve": "resolve",
    "dns": "dns",
    "database": "database",
    "login": "login",
    "masuk": "login",
}
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    toks = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    return [_NORMALISE.get(t, t) for t in toks]


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.name = f"hashing-lexical-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float64)
        toks = tokenize(text)
        feats = toks + [f"{a}_{b}" for a, b in itertools.pairwise(toks)]
        counts: dict[str, int] = {}
        for f in feats:
            counts[f] = counts.get(f, 0) + 1
        for f, c in counts.items():
            h = zlib.crc32(f.encode("utf-8"))
            sign = 1.0 if (zlib.crc32(b"s" + f.encode("utf-8")) & 1) else -1.0
            weight = (1.0 + np.log(c)) * (1.0 if "_" not in f else 0.7)
            v[h % self.dim] += sign * weight
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim))


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, dim: int) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, kept lazy

        self._model = SentenceTransformer(model_name)
        real_dim = int(self._model.get_sentence_embedding_dimension() or 0)
        if real_dim != dim:
            raise ValueError(f"EMBEDDING_DIM={dim} but model outputs {real_dim}; update EMBEDDING_DIM and re-run migrations")
        self.dim = dim
        self.name = model_name

    def embed(self, texts: list[str]) -> np.ndarray:
        arr = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(arr, dtype=np.float64)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend in ("auto", "sentence-transformers"):
        try:
            emb = SentenceTransformerEmbedder(s.embedding_model, s.embedding_dim)
            logger.info("embedder ready: %s", emb.name)
            return emb
        except Exception as exc:  # offline / not installed / dim mismatch -> fallback (never crash)
            if s.embedding_backend == "sentence-transformers":
                logger.warning("sentence-transformers requested but unavailable (%s); using hashing fallback", exc)
            else:
                logger.info("sentence-transformers unavailable (%s); using hashing-lexical fallback", type(exc).__name__)
    return HashingEmbedder(s.embedding_dim)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0
