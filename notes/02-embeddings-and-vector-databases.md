# Embeddings and vector databases
An embedding is a list of numbers that represents the meaning of a piece of text. Texts with similar meaning end up close together in that space, even if they use different words.
A vector database stores these embeddings and finds the nearest ones to a query very quickly. ChromaDB is a simple open-source vector database that runs locally with no server. Others include Pinecone, Weaviate, pgvector and FAISS.
Closeness is usually measured with cosine similarity or distance. Approximate nearest neighbour indexes such as HNSW make search fast over millions of vectors.
Metadata filters let you restrict a search, for example only documents from one source or one date range.
