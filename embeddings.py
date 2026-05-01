from chromadb.api.types import EmbeddingFunction, Documents, Embeddings


class BGEEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self):
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    def __call__(self, input: Documents) -> Embeddings:
        self._load_model()
        embeddings = self._model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()


bge_embed_fn = BGEEmbeddingFunction()