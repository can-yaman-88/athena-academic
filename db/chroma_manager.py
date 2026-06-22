"""Local ChromaDB vector store for Athena-Academic academic documents.

:class:`ChromaManager` wraps a persistent ChromaDB collection that embeds text
locally on the CPU using ChromaDB's default embedding function
(``all-MiniLM-L6-v2`` via ONNX — no PyTorch, no network calls). Long documents
are chunked automatically by a dependency-free recursive character splitter
before they are embedded and stored.

ChromaDB's Python API is synchronous, so this manager is intentionally
synchronous; it can be called from async code via ``asyncio.to_thread`` if
needed by later phases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from config import settings
from db.exceptions import ChromaError

# Recursive split separators, ordered from coarsest (paragraph) to finest
# (character). The empty string is the terminal fallback that splits by
# individual characters when nothing else fits.
_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")


class ChromaManager:
    """Manage a persistent, locally-embedded collection of academic documents."""

    def __init__(
        self,
        persist_dir: Path | str | None = None,
        collection_name: str | None = None,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._persist_dir = (
            Path(persist_dir)
            if persist_dir is not None
            else settings.chroma_persist_dir
        )
        self._collection_name = collection_name or settings.chroma_collection
        self._chunk_size = (
            chunk_size if chunk_size is not None else settings.chunk_size
        )
        self._chunk_overlap = (
            chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        )

        if self._chunk_overlap >= self._chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        self._client: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def initialize(self) -> None:
        """Create the persistent client and get-or-create the collection.

        Imports are performed lazily so that importing this module does not pay
        the cost of loading ChromaDB (and downloading the ONNX model on first
        use) until a manager is actually initialised.
        """
        if self._collection is not None:
            return

        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as exc:  # pragma: no cover - missing dependency
            raise ChromaError(
                "chromadb is not installed; run `pip install chromadb`."
            ) from exc

        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._persist_dir))
            embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # chromadb raises a variety of error types
            raise ChromaError(
                f"Failed to initialise ChromaDB collection "
                f"'{self._collection_name}': {exc}"
            ) from exc

    def _require_collection(self) -> Any:
        if self._collection is None:
            raise ChromaError(
                "ChromaManager is not initialised; call initialize() first."
            )
        return self._collection

    # ------------------------------------------------------------------ #
    # Chunking (dependency-free recursive character splitter)
    # ------------------------------------------------------------------ #
    def _chunk_text(self, text: str) -> list[str]:
        """Split ``text`` into overlapping chunks no larger than ``chunk_size``."""
        cleaned = text.strip()
        if not cleaned:
            return []
        if len(cleaned) <= self._chunk_size:
            return [cleaned]
        chunks = self._split_recursive(cleaned, list(_SEPARATORS))
        return [chunk for chunk in chunks if chunk.strip()]

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split using the coarsest separator that applies."""
        separator = separators[-1]
        remaining: list[str] = []
        for index, candidate in enumerate(separators):
            if candidate == "":
                separator = candidate
                break
            if candidate in text:
                separator = candidate
                remaining = separators[index + 1 :]
                break

        splits = list(text) if separator == "" else text.split(separator)

        final_chunks: list[str] = []
        good_splits: list[str] = []
        for piece in splits:
            if len(piece) < self._chunk_size:
                good_splits.append(piece)
                continue
            if good_splits:
                final_chunks.extend(self._merge_splits(good_splits, separator))
                good_splits = []
            if remaining:
                final_chunks.extend(self._split_recursive(piece, remaining))
            else:
                final_chunks.append(piece)

        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, separator))
        return final_chunks

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """Greedily merge small splits into ``chunk_size`` windows with overlap."""
        sep_len = len(separator)
        chunks: list[str] = []
        current: list[str] = []
        total = 0

        for piece in splits:
            piece_len = len(piece)
            addition = piece_len + (sep_len if current else 0)
            if total + addition > self._chunk_size and current:
                merged = separator.join(current).strip()
                if merged:
                    chunks.append(merged)
                # Slide the window forward, retaining `chunk_overlap` characters.
                while current and (
                    total > self._chunk_overlap
                    or total + addition > self._chunk_size
                ):
                    removed = current.pop(0)
                    total -= len(removed) + (sep_len if current else 0)
            current.append(piece)
            total += piece_len + (sep_len if len(current) > 1 else 0)

        merged = separator.join(current).strip()
        if merged:
            chunks.append(merged)
        return chunks

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def add_document(
        self,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        *,
        doc_id: Optional[str] = None,
    ) -> list[str]:
        """Chunk ``text``, embed it, and store the chunks under a shared doc id.

        Returns the list of per-chunk ids that were written. Each chunk's stored
        metadata is a copy of ``metadata`` augmented with ``doc_id``,
        ``chunk_index`` and ``chunk_count`` so chunks of one document can be
        grouped, filtered, and reassembled later. A caller may supply ``doc_id``
        (e.g. a Brain fact id) so the document can later be deleted/looked up by
        that stable id; otherwise a random UUID is assigned.
        """
        collection = self._require_collection()

        if not text or not text.strip():
            raise ValueError("Cannot add an empty document.")

        chunks = self._chunk_text(text)
        if not chunks:
            raise ValueError("Document produced no chunks after splitting.")

        doc_id = doc_id or str(uuid4())
        base_metadata = dict(metadata) if metadata else {}
        chunk_count = len(chunks)

        ids = [f"{doc_id}:{index}" for index in range(chunk_count)]
        metadatas = [
            {
                **base_metadata,
                "doc_id": doc_id,
                "chunk_index": index,
                "chunk_count": chunk_count,
            }
            for index in range(chunk_count)
        ]

        try:
            collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        except Exception as exc:
            raise ChromaError(f"Failed to add document {doc_id}: {exc}") from exc

        return ids

    def query_documents(
        self, query: str, n_results: int = 3
    ) -> list[dict[str, Any]]:
        """Return the ``n_results`` chunks most similar to ``query``.

        Each result is ``{"id", "text", "metadata", "distance"}``, ordered from
        most to least similar (lowest cosine distance first). An empty list is
        returned when the collection holds no documents.
        """
        collection = self._require_collection()

        if not query or not query.strip():
            raise ValueError("Query text must be non-empty.")
        if n_results < 1:
            raise ValueError("n_results must be a positive integer.")

        try:
            available = collection.count()
            if available == 0:
                return []
            result = collection.query(
                query_texts=[query],
                n_results=min(n_results, available),
            )
        except Exception as exc:
            raise ChromaError(f"Query failed: {exc}") from exc

        return self._format_query_result(result)

    @staticmethod
    def _format_query_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten ChromaDB's per-query nested lists into a flat result list."""

        def first(key: str) -> list[Any]:
            value = result.get(key) or [[]]
            return value[0] if value else []

        ids = first("ids")
        documents = first("documents")
        metadatas = first("metadatas")
        distances = first("distances")

        formatted: list[dict[str, Any]] = []
        for index, chunk_id in enumerate(ids):
            formatted.append(
                {
                    "id": chunk_id,
                    "text": documents[index] if index < len(documents) else None,
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return formatted

    def delete_document(self, doc_id: str) -> None:
        """Delete every chunk belonging to ``doc_id``."""
        collection = self._require_collection()
        try:
            collection.delete(where={"doc_id": doc_id})
        except Exception as exc:
            raise ChromaError(
                f"Failed to delete document {doc_id}: {exc}"
            ) from exc

    def count(self) -> int:
        """Return the total number of stored chunks."""
        collection = self._require_collection()
        try:
            return int(collection.count())
        except Exception as exc:
            raise ChromaError(f"Failed to count documents: {exc}") from exc


__all__ = ["ChromaManager"]
