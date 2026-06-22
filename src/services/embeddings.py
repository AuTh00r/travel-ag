from functools import lru_cache

from sentence_transformers import SentenceTransformer
from structlog import get_logger

logger = get_logger()


class EmbeddingsService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("embeddings.model_loading", model=self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    async def get_embedding(self, text: str) -> list[float]:
        model = self._get_model()
        embedding = model.encode(text, show_progress_bar=False)
        return embedding.tolist()

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()


@lru_cache(maxsize=1)
def get_embeddings_service() -> EmbeddingsService:
    return EmbeddingsService()
