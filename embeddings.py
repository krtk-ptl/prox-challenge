from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer


class BGEEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self):
        self.model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self.model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()


bge_embed_fn = BGEEmbeddingFunction()