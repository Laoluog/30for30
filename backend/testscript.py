from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

result = client.models.embed_content(
    model="gemini-embedding-001",
    contents="What is the meaning of life?",
    config=types.EmbedContentConfig(output_dimensionality=1536)
)

[embedding_obj] = result.embeddings
print(embedding_obj.values)
embedding_length = len(embedding_obj.values)

print(f"Length of embedding: {embedding_length}")