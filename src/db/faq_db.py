import asyncio
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from structlog import get_logger

from src.config import settings

logger = get_logger()

FAQ_DIR = Path("data/faq")
COLLECTION_NAME = "faq"


def _get_chroma_path() -> str:
    return settings.chroma_db_dir or "data/chroma"


def _get_client() -> chromadb.PersistentClient:
    path = _get_chroma_path()
    Path(path).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=path)


def _get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    return SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


def get_collection() -> chromadb.Collection:
    client = _get_client()
    embedding_fn = _get_embedding_function()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def _parse_faq_file(filepath: Path) -> list[dict]:
    content = filepath.read_text(encoding="utf-8")
    entries = []
    current_q: str | None = None
    current_a: list[str] = []

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Вопрос:") or line.startswith("Q:"):
            if current_q:
                entries.append(
                    {"question": current_q, "answer": "\n".join(current_a).strip()}
                )
            current_q = line.split(":", 1)[1].strip()
            current_a = []
        elif line.startswith("Ответ:") or line.startswith("A:"):
            current_a.append(line.split(":", 1)[1].strip())
        elif current_q:
            current_a.append(line)

    if current_q:
        entries.append({"question": current_q, "answer": "\n".join(current_a).strip()})

    return entries


def load_faq_to_chroma() -> int:
    collection = get_collection()

    if collection.count() > 0:
        logger.info("faq.already_loaded", count=collection.count())
        return collection.count()

    faq_dir = Path(FAQ_DIR)
    if not faq_dir.exists():
        logger.warning("faq.directory_not_found", path=str(faq_dir))
        return 0

    all_entries: list[dict] = []
    for filepath in sorted(faq_dir.glob("*.txt")):
        try:
            entries = _parse_faq_file(filepath)
            topic = filepath.stem
            for entry in entries:
                doc_id = f"{topic}_{len(all_entries)}"
                all_entries.append(
                    {
                        "id": doc_id,
                        "question": entry["question"],
                        "answer": entry["answer"],
                        "topic": topic,
                        "source": filepath.name,
                    }
                )
        except Exception:
            logger.exception("faq.parse_error", file=str(filepath))

    if not all_entries:
        logger.warning("faq.no_entries_found")
        return 0

    ids = [e["id"] for e in all_entries]
    documents = [f"Вопрос: {e['question']}\nОтвет: {e['answer']}" for e in all_entries]
    metadatas = [
        {"topic": e["topic"], "source": e["source"], "question": e["question"]}
        for e in all_entries
    ]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info("faq.loaded", count=len(all_entries))
    return len(all_entries)


async def search_faq(query: str, n_results: int = 3) -> list[dict]:
    loop = asyncio.get_event_loop()
    collection = get_collection()

    if collection.count() == 0:
        logger.warning("faq.collection_empty")
        return []

    def _query() -> dict:
        return collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()),
        )

    results = await loop.run_in_executor(None, _query)

    entries: list[dict] = []
    if results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            entries.append(
                {
                    "id": doc_id,
                    "document": results["documents"][0][i],
                    "metadata": (
                        results["metadatas"][0][i] if results["metadatas"] else {}
                    ),
                    "distance": (
                        results["distances"][0][i] if results.get("distances") else 0
                    ),
                }
            )

    return entries
