# Spec · Retriever

- **Источники:** `data/kb_seed/*.md` (если есть) или встроенный набор советов (50/30/20, подушка, snowball/avalanche, категории, цели накоплений).
- **Бэкенд:** Chroma (default, embedded, persist_directory=`KB_PATH`) или Qdrant (`KB_BACKEND=qdrant`, `QDRANT_URL`, `KB_COLLECTION`).
- **Embeddings:** `OpenAIEmbeddings(model=EMBEDDING_MODEL, base_url=EMBEDDING_BASE_URL || LLM_BASE_URL, api_key=EMBEDDING_API_KEY || LLM_API_KEY)`.
- **Поиск:** `vectorstore.as_retriever(search_kwargs={"k": 5})`. Tool `search_advice` принимает `query`, `k≤10`.
- **Ranking:** дефолтный similarity score бэкенда; reranking не настроен (PoC). При наличии Cohere/BGE — drop-in через `ContextualCompressionRetriever`.
- **Индексация / seed:** при пустой коллекции при старте API.
- **Деградация:** при ошибке инициализации эмбеддингов или backend — `KnowledgeBase(None)`, `search_advice` возвращает `{"hits": []}`.
