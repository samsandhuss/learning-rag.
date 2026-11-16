# Retrieval-augmented generation (RAG)
RAG means retrieving relevant chunks from your own documents and giving them to the model as context before it answers. It reduces hallucination and lets a model answer about private or recent information it was never trained on.
The pipeline is: load documents, split them into chunks, embed each chunk, store in a vector database, then at question time embed the question, retrieve the top-k chunks and pass them to the model in the prompt.
Chunk size matters. Too small loses context; too large dilutes the match. Overlap between chunks helps keep sentences together.
Good RAG systems cite their sources so a human can check the answer.
