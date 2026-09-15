"""
Lightweight local RAG (Retrieval-Augmented Generation).

Design constraints:
- 100% local, free, no external embedding API: retrieval uses TF-IDF
  cosine similarity over a curated JSON knowledge base of trusted
  guidance documents.
- The knowledge base contains ONLY curated safety guidance — no scraped
  internet content — so retrieved sources are always trustworthy and
  citable by title.
- Retrieval failure must never break the chat: any error degrades to
  "no documents found" and the AI answers from weather/risk context
  alone.
"""
import json
import math
import logging
import re
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge" / "india_weather_safety.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Very common words that carry no topical signal.
_STOPWORDS = frozenset(
    "a an and are as at be but by can do for from has have how i if in is it "
    "its may me my not of on or our should so than that the their them then "
    "there these they this to was we were what when where which who will with "
    "you your do does did been being am".split()
)


def _tokenize(text: str) -> list[str]:
    return [tok for tok in _TOKEN_RE.findall(text.lower()) if tok not in _STOPWORDS and len(tok) > 1]


class RetrievedDocument(dict):
    """A knowledge-base hit: id, title, content, and relevance score.

    Plain dict subclass so it serializes directly to JSON in API responses.
    """

    @property
    def title(self) -> str:
        return self.get("title", "")

    @property
    def content(self) -> str:
        return self.get("content", "")


@lru_cache(maxsize=4)
def _load_index(path_str: str) -> tuple[list[dict], dict[str, dict[str, float]], dict[str, float]]:
    """Load the knowledge base and precompute TF-IDF vectors.

    Returns (documents, tfidf_by_doc, idf_by_term).
    """
    path = Path(path_str)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        documents = data.get("documents", [])
    except (OSError, json.JSONDecodeError) as exc:
        log.error("rag.knowledge_base_unreadable path=%s error=%s", path, exc)
        documents = []

    doc_tokens: list[list[str]] = []
    for doc in documents:
        doc_tokens.append(_tokenize(f"{doc.get('title', '')} {' '.join(doc.get('tags', []))} {doc.get('content', '')}"))

    # Document frequency per term.
    df: dict[str, int] = {}
    for tokens in doc_tokens:
        for term in set(tokens):
            df[term] = df.get(term, 0) + 1

    n_docs = max(len(documents), 1)
    idf = {term: math.log((n_docs + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    tfidf_by_doc: dict[str, dict[str, float]] = {}
    for doc_id, tokens in zip([d.get("id", f"doc{i}") for i, d in enumerate(documents)], doc_tokens):
        tf: dict[str, float] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0.0) + 1.0
        total = max(len(tokens), 1)
        tfidf_by_doc[doc_id] = {term: (count / total) * idf.get(term, 1.0) for term, count in tf.items()}

    return documents, tfidf_by_doc, idf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class RagRetriever:
    """Retrieves relevant knowledge-base documents for a user question."""

    def __init__(self, knowledge_path: str | None = None, top_k: int | None = None) -> None:
        from app.core.config import get_settings

        settings = get_settings()
        self._path = str(Path(knowledge_path or settings.RAG_KNOWLEDGE_DIR or _DEFAULT_KNOWLEDGE_PATH))
        self._top_k = top_k or settings.RAG_TOP_K

    def retrieve(self, query: str) -> list[RetrievedDocument]:
        """Return up to top_k documents relevant to the query.

        Never raises: an empty result is the graceful degradation path.
        """
        try:
            documents, tfidf_by_doc, idf = _load_index(self._path)
        except Exception as exc:  # noqa: BLE001 - retrieval must not break chat
            log.warning("rag.retrieve_failed error=%s", type(exc).__name__)
            return []

        query_tokens = _tokenize(query)
        if not documents or not query_tokens:
            return []

        query_tf: dict[str, float] = {}
        for term in query_tokens:
            query_tf[term] = query_tf.get(term, 0.0) + 1.0
        total = len(query_tokens)
        query_vec = {term: (count / total) * idf.get(term, 1.0) for term, count in query_tf.items()}

        scored: list[tuple[float, dict]] = []
        for doc in documents:
            doc_id = doc.get("id", "")
            score = _cosine(query_vec, tfidf_by_doc.get(doc_id, {}))
            if score > 0.02:  # ignore incidental single-word overlaps
                scored.append((score, doc))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            RetrievedDocument(id=doc.get("id", ""), title=doc.get("title", ""), content=doc.get("content", ""), score=round(score, 4))
            for score, doc in scored[: self._top_k]
        ]


def get_retriever() -> RagRetriever:
    """Process-wide retriever bound to configured knowledge base + top_k."""
    return RagRetriever()
