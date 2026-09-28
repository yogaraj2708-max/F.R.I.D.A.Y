"""
F.R.I.D.A.Y. 3.0 — Hybrid RAG Retriever (Dense Vector + Lexical BM25)
Combines dense hashed embeddings with BM25 lexical matching to ensure both
high-level conceptual queries and exact keyword/identifier matches succeed.
Enforces dimension compatibility checks, relevance filtering, and bounded top-k.
"""

import math
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from friday_ui.rag.store import FastLocalEmbedder
from friday_core.rag.models import DocumentChunk, QueryResult

logger = logging.getLogger("FRIDAY.HybridRetriever")


class BM25Index:
    """
    In-memory BM25 ranker for exact lexical keyword matching and provenance verification.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_lens: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_term_freqs: List[Dict[str, int]] = []
        self.df: Dict[str, int] = {}
        self.total_docs: int = 0

    @staticmethod
    def tokenize(text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def index_documents(self, documents: List[str]):
        self.total_docs = len(documents)
        self.doc_lens = []
        self.doc_term_freqs = []
        self.df = {}

        if self.total_docs == 0:
            self.avg_doc_len = 0.0
            return

        total_len = 0
        for doc in documents:
            tokens = self.tokenize(doc)
            length = len(tokens)
            self.doc_lens.append(length)
            total_len += length

            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self.doc_term_freqs.append(tf)

            for term in tf.keys():
                self.df[term] = self.df.get(term, 0) + 1

        self.avg_doc_len = total_len / self.total_docs if self.total_docs > 0 else 0.0

    def score(self, query: str) -> List[float]:
        query_terms = self.tokenize(query)
        scores = [0.0] * self.total_docs
        if self.total_docs == 0 or not query_terms:
            return scores

        for q in query_terms:
            if q not in self.df:
                continue
            df_val = self.df[q]
            # Standard Lucene-style IDF
            idf = math.log(1.0 + (self.total_docs - df_val + 0.5) / (df_val + 0.5))
            for doc_idx, tf_dict in enumerate(self.doc_term_freqs):
                tf = tf_dict.get(q, 0)
                if tf == 0:
                    continue
                num = tf * (self.k1 + 1.0)
                denom = tf + self.k1 * (1.0 - self.b + self.b * (self.doc_lens[doc_idx] / (self.avg_doc_len or 1.0)))
                scores[doc_idx] += idf * (num / denom)
        return scores


class HybridRetriever:
    """
    Ranks chunks using weighted linear combination of dense cosine similarity and BM25.
    """
    def __init__(self, alpha: float = 0.5, embedder: Optional[FastLocalEmbedder] = None):
        """
        alpha: Weight for dense vector search (0.0 to 1.0).
               1.0 = Pure Vector Search
               0.0 = Pure BM25 Lexical Search
               0.5 = Balanced Hybrid Search (Recommended)
        """
        self.alpha = alpha
        self.embedder = embedder or FastLocalEmbedder()
        self.bm25 = BM25Index()

    def rank(
        self,
        query: str,
        chunks: List[DocumentChunk],
        chunk_embeddings: List[np.ndarray],
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[QueryResult]:
        if not chunks:
            return []

        # 1. Dense Vector Scoring with dimension compatibility validation
        query_vec = self.embedder.embed_text(query)
        vector_scores = []
        for emb in chunk_embeddings:
            if emb.shape == query_vec.shape:
                sim = float(np.dot(query_vec, emb))
            else:
                logger.warning(
                    f"Vector dimension mismatch detected: chunk vector shape {emb.shape} "
                    f"vs query vector shape {query_vec.shape}. Incompatible vector skipped."
                )
                sim = 0.0
            vector_scores.append(max(0.0, sim))

        # 2. Lexical BM25 Scoring
        doc_texts = [c.content for c in chunks]
        self.bm25.index_documents(doc_texts)
        raw_bm25_scores = self.bm25.score(query)

        # Normalize BM25 scores to [0.0, 1.0]
        max_bm25 = max(raw_bm25_scores) if raw_bm25_scores else 0.0
        normalized_bm25 = [
            (s / max_bm25) if max_bm25 > 0.0 else 0.0
            for s in raw_bm25_scores
        ]

        # 3. Fuse Scores
        results: List[QueryResult] = []
        for idx, chunk in enumerate(chunks):
            v_score = vector_scores[idx]
            b_score = normalized_bm25[idx]
            hybrid = (self.alpha * v_score) + ((1.0 - self.alpha) * b_score)

            if hybrid >= min_score:
                results.append(QueryResult(
                    chunk=chunk,
                    vector_score=round(v_score, 4),
                    bm25_score=round(b_score, 4),
                    hybrid_score=round(hybrid, 4)
                ))

        results.sort(key=lambda r: r.hybrid_score, reverse=True)
        return results[:top_k]
