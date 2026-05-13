from __future__ import annotations

from app.agent.kb import KBHit, KnowledgeBase


class _StubRetriever:
    def __init__(self, docs) -> None:
        self._docs = docs

    def invoke(self, query):
        return self._docs


def _doc(text, **meta):
    from langchain_core.documents import Document

    return Document(page_content=text, metadata=meta)


def test_kb_returns_hits_from_retriever() -> None:
    kb = KnowledgeBase(
        _StubRetriever(
            [
                _doc("про подушку безопасности", doc_id="ef", title="Подушка"),
                _doc("про снежный ком долгов", doc_id="ds", title="Долги"),
            ]
        )
    )
    hits = kb.search("подушка", k=2)
    assert len(hits) == 2
    assert hits[0].title == "Подушка"
    assert isinstance(hits[0], KBHit)


def test_kb_empty_query() -> None:
    kb = KnowledgeBase(_StubRetriever([_doc("x")]))
    assert kb.search("") == []


def test_kb_no_retriever_returns_empty() -> None:
    assert KnowledgeBase(None).search("anything") == []


def test_kb_retriever_failure_swallowed() -> None:
    class Bad:
        def invoke(self, q):
            raise RuntimeError("boom")

    kb = KnowledgeBase(Bad())
    assert kb.search("x") == []


def test_kb_factory_built_lazily_on_first_search() -> None:
    built: list[int] = []

    def factory():
        built.append(1)
        return _StubRetriever([_doc("про подушку", doc_id="x", title="X")])

    kb = KnowledgeBase(factory=factory)
    assert not built  # importing/constructing must not build the retriever
    assert kb.search("подушка")[0].title == "X"
    assert built == [1]
    kb.search("again")
    assert built == [1]  # built once, then reused


def test_kb_factory_failure_degrades_to_empty() -> None:
    def factory():
        raise RuntimeError("vector store down")

    kb = KnowledgeBase(factory=factory)
    assert kb.search("anything") == []
