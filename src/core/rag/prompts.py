# src/core/rag/prompts.py

ENTERPRISE_ASSISTANT_PROMPT = """You are an expert Enterprise Assistant. 
Use the following context from corporate reports 
to answer the user's question. 
If the context does not contain relevant information, politely indicate that you do not have enough data.

Context:
{context}

User Question: {question}

Answer:
"""
