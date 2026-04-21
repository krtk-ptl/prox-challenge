import os
import chromadb
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
chroma = chromadb.PersistentClient(path="./chroma_db")
collection = chroma.get_or_create_collection(name="vulcan_manual")

def query_rag(question):
    # Retrieve top 5 relevant chunks
    results = collection.query(
        query_texts=[question],
        n_results=5
    )

    chunks = results["documents"][0]
    metadatas = results["metadatas"][0]

    context = ""
    for i, (chunk, meta) in enumerate(zip(chunks, metadatas)):
        context += f"[Source: {meta['source']}, Page {meta['page']}]\n{chunk}\n\n"

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""You are a helpful assistant for the Vulcan OmniPro 220 welder.
Answer the question using ONLY the context provided below.
If the answer is not in the context, say "I couldn't find that in the manual."

Context:
{context}

Question: {question}"""
            }
        ]
    )

    print(f"\nAnswer:\n{response.content[0].text}")
    print(f"\nInput tokens: {response.usage.input_tokens}")
    print(f"Output tokens: {response.usage.output_tokens}")

if __name__ == "__main__":
    question = "What is the duty cycle for MIG welding at 200A on 240V?"
    print(f"Question: {question}")
    query_rag(question)