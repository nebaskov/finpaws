from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from loguru import logger
from pydantic import BaseModel, Field

from app.config import SETTINGS


class KBHit(BaseModel):
    doc_id: str
    title: str
    snippet: str
    score: float = Field(ge=0, default=0.0)


class KnowledgeBase:
    """Wraps a retriever. Building the retriever can touch the embeddings API / a vector store,
    so when a ``factory`` is given it is invoked lazily on the first :meth:`search` and any failure
    degrades to "no KB" — importing the app never blocks on it.
    """

    def __init__(self, retriever: Any | None = None, *, factory: Callable[[], Any] | None = None) -> None:
        self._retriever = retriever
        self._factory = factory

    def _resolve(self) -> Any | None:
        if self._factory is not None:
            try:
                self._retriever = self._factory()
            except Exception:  # noqa: BLE001 - the KB is best-effort; never raise from here
                logger.exception("kb retriever init failed")
                self._retriever = None
            self._factory = None
        return self._retriever

    def search(self, query: str, k: int = 3) -> list[KBHit]:
        retriever = self._resolve()
        if retriever is None or not query.strip():
            return []
        try:
            docs = retriever.invoke(query)[:k]
        except Exception:  # noqa: BLE001 - the KB is best-effort; never fail a chat over it
            logger.bind(query=query).exception("kb retriever failed")
            return []
        return [_doc_to_hit(doc) for doc in docs]


def _doc_to_hit(doc: Document) -> KBHit:
    title = doc.metadata.get("title") or doc.metadata.get("source") or "doc"
    return KBHit(
        doc_id=str(doc.metadata.get("doc_id") or doc.metadata.get("source") or title),
        title=str(title),
        snippet=doc.page_content[:280].strip(),
        score=float(doc.metadata.get("score", 0.0)),
    )


def _build_embeddings() -> Embeddings | None:
    try:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=SETTINGS.embedding_model,
            api_key=SETTINGS.embedding_api_key or SETTINGS.llm_api_key or "missing-key",
            base_url=SETTINGS.embedding_base_url or SETTINGS.llm_base_url,
            check_embedding_ctx_length=False,
        )
    except Exception:  # noqa: BLE001 - missing keys / network: degrade to "no KB"
        logger.exception("failed to build embeddings")
        return None


def _seed_documents() -> list[Document]:
    seed_dir = Path(SETTINGS.kb_seed_path)
    if seed_dir.exists():
        docs: list[Document] = []
        for fp in sorted(seed_dir.glob("**/*.md")):
            text = fp.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text else fp.stem
            docs.append(
                Document(
                    page_content=text,
                    metadata={"doc_id": fp.name, "title": title, "source": str(fp)},
                )
            )
        if docs:
            return docs
    return list(_DEFAULT_DOCS)


def build_kb() -> KnowledgeBase:
    """Return a lazily-initialised knowledge base — the actual embeddings/vector-store work
    happens on the first :meth:`KnowledgeBase.search`, not here."""
    return KnowledgeBase(factory=_build_retriever)


def _build_retriever() -> Any | None:
    embeddings = _build_embeddings()
    if embeddings is None:
        return None
    backend = SETTINGS.kb_backend.lower()
    return _build_qdrant(embeddings) if backend == "qdrant" else _build_chroma(embeddings)


def _build_chroma(embeddings: Embeddings) -> Any:
    from langchain_chroma import Chroma

    persist_dir = Path(SETTINGS.kb_path)
    persist_dir.mkdir(parents=True, exist_ok=True)
    store = Chroma(
        collection_name=SETTINGS.kb_collection,
        embedding_function=embeddings,
        persist_directory=str(persist_dir),
    )
    if store._collection.count() == 0:
        store.add_documents(_seed_documents())
    return store.as_retriever(search_kwargs={"k": 5})


def _build_qdrant(embeddings: Embeddings) -> Any:
    from langchain_qdrant import QdrantVectorStore
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(url=SETTINGS.qdrant_url)
    collection = SETTINGS.kb_collection
    existing = {c.name for c in client.get_collections().collections}
    if collection not in existing:
        size = len(embeddings.embed_query("ping"))
        client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(size=size, distance=qmodels.Distance.COSINE),
        )
        store = QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings)
        store.add_documents(_seed_documents())
    else:
        store = QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings)
    return store.as_retriever(search_kwargs={"k": 5})


_DEFAULT_DOCS: tuple[Document, ...] = (
    Document(
        page_content=(
            "Правило 50/30/20 — базовая модель распределения дохода: 50% на обязательные расходы "
            "(жильё, еда, коммуналка, транспорт), 30% на желания (развлечения, шопинг, кафе), "
            "20% на сбережения и погашение долгов. Подходит как стартовая точка для планирования."
        ),
        metadata={"doc_id": "50-30-20", "title": "Правило 50/30/20"},
    ),
    Document(
        page_content=(
            "Подушка безопасности — ликвидный резерв на 3–6 месяцев обязательных расходов. "
            "Хранится на накопительном счёте или коротком вкладе. Цель — пережить потерю дохода без долгов."
        ),
        metadata={"doc_id": "emergency-fund", "title": "Подушка безопасности"},
    ),
    Document(
        page_content=(
            "Метод снежного кома: гасить долги от самого маленького к большому. "
            "Метод лавины: от самой высокой ставки. Снежный ком даёт мотивацию, лавина экономит проценты."
        ),
        metadata={"doc_id": "debt-snowball", "title": "Снежный ком долгов"},
    ),
    Document(
        page_content=(
            "Стандартные категории расходов: housing, food, transport, utilities, health, "
            "education, shopping, entertainment, other."
        ),
        metadata={"doc_id": "categories", "title": "Категории расходов"},
    ),
    Document(
        page_content=(
            "Чтобы накопить N за M месяцев — откладывай N/M ежемесячно. Учитывай инфляцию: "
            "подушку держи на накопительном счёте, среднесрочные цели — короткие вклады, "
            "долгосрочные — диверсифицированный портфель."
        ),
        metadata={"doc_id": "goal-planning", "title": "Планирование цели накоплений"},
    ),
)
