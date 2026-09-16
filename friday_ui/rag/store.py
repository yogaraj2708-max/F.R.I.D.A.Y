"""
F.R.I.D.A.Y. 2.0 - Local Offline RAG Vector Store
100% Private, Zero External Network Dependency, Instant Chunked Ingestion & Deterministic Retrieval
"""

import os
import sqlite3
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from friday_ui.core.config import APP_DATA_DIR

class FastLocalEmbedder:
    """
    Deterministic, zero-latency local embedding generator using Blake2b hashed projections.
    Guarantees stable, identical vectors across distinct application runs and Python processes.
    """
    def __init__(self, dim: int = 384):
        self.dim = dim

    def _token_hash(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
        return int.from_bytes(digest, byteorder='little') % self.dim

    def embed_text(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = text.lower().split()
        if not tokens:
            return vec

        for idx, token in enumerate(tokens):
            h1 = self._token_hash(token)
            vec[h1] += 1.0
            # Bigrams for local phrase structure
            if idx > 0:
                bigram = f"{tokens[idx-1]}_{token}"
                h2 = self._token_hash(bigram)
                vec[h2] += 1.5

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def __call__(self, input_texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t).tolist() for t in input_texts]

class FridayVectorStore:
    """
    High-performance, local persistent SQLite vector store.
    Splits documents into overlapping chunks (~500 chars) with individual embeddings
    for accurate, granular paragraph semantic retrieval.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(APP_DATA_DIR, "friday_vectors.db")
        self.db_path = db_path
        self.embedder = FastLocalEmbedder()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT,
                    chunk_index INTEGER,
                    title TEXT,
                    category TEXT,
                    content TEXT,
                    embedding BLOB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(doc_id, chunk_index)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
        """Splits raw text into sliding window overlapping paragraphs."""
        cleaned = text.strip()
        if len(cleaned) <= chunk_size:
            return [cleaned]

        chunks = []
        start = 0
        while start < len(cleaned):
            end = start + chunk_size
            chunk = cleaned[start:end]
            chunks.append(chunk)
            start += (chunk_size - overlap)
            if start >= len(cleaned):
                break
        return chunks

    def add_document(self, doc_id: str, title: str, category: str, content: str):
        """Indexes document by chunking into semantic blocks with individual embeddings."""
        chunks = self._chunk_text(content)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            # Clean existing chunks for this doc_id
            cursor.execute("DELETE FROM document_chunks WHERE doc_id = ?", (doc_id,))

            for idx, chunk in enumerate(chunks):
                vec = self.embedder.embed_text(chunk)
                vec_bytes = vec.tobytes()
                cursor.execute("""
                    INSERT INTO document_chunks (doc_id, chunk_index, title, category, content, embedding)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (doc_id, idx, title, category, chunk, vec_bytes))

            conn.commit()
        finally:
            conn.close()

    def ingest_document(self, title: str, content: str, category: str = "general") -> int:
        """Convenience method: chunks, generates deterministic ID, and indexes document content."""
        doc_id = str(hashlib.md5(title.encode('utf-8')).hexdigest())[:8]
        chunks = self._chunk_text(content)
        self.add_document(doc_id, title, category, content)
        return len(chunks)

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Queries stored chunks by cosine similarity and returns the most relevant snippets."""
        query_vec = self.embedder.embed_text(query_text)

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT doc_id, chunk_index, title, category, content, embedding FROM document_chunks")
            rows = cursor.fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        scored_results = []
        for doc_id, chunk_idx, title, category, content, emb_bytes in rows:
            chunk_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            similarity = float(np.dot(query_vec, chunk_vec))
            scored_results.append({
                "doc_id": doc_id,
                "chunk_index": chunk_idx,
                "title": title,
                "category": category,
                "content": content,
                "score": round(similarity, 4)
            })

        scored_results.sort(key=lambda x: x["score"], reverse=True)
        return scored_results[:top_k]
