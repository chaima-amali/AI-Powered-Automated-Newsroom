"""
tests/test_embedding_pipeline.py
----------------------------------
Unit tests for the embedding generator, clustering, and repository helpers.
Run: pytest tests/ -v
"""

import numpy as np
import pytest


# ── embedding/generator.py ────────────────────────────────────────────────────

class TestBuildText:
    def test_title_and_content(self):
        from embedding.generator import build_text
        result = build_text("My Title", "word " * 600)
        words = result.split()
        # Title contributes 2 words ("My", "Title") + separator word + 500 content words ≤ 503
        assert len(words) <= 503

    def test_missing_content(self):
        from embedding.generator import build_text
        assert build_text("Only Title", None) == "Only Title"
        assert build_text("Only Title", "") == "Only Title"

    def test_empty_title(self):
        from embedding.generator import build_text
        result = build_text("", "some content")
        assert "some content" in result


class TestEmbedTexts:
    def test_returns_correct_shape(self):
        from embedding.generator import embed_texts
        vecs = embed_texts(["Hello world", "News article text"])
        assert vecs.shape == (2, 384)
        assert vecs.dtype == np.float32

    def test_empty_input(self):
        from embedding.generator import embed_texts
        vecs = embed_texts([])
        assert vecs.shape == (0, 384)

    def test_vectors_are_normalised(self):
        from embedding.generator import embed_texts
        vecs = embed_texts(["Test sentence"])
        norms = np.linalg.norm(vecs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)


# ── embedding/clustering.py ───────────────────────────────────────────────────

class TestClusterEmbeddings:
    def test_empty_array(self):
        from embedding.clustering import cluster_embeddings
        labels = cluster_embeddings(np.array([]).reshape(0, 384))
        assert labels.shape == (0,)

    def test_fewer_than_min_samples(self):
        from embedding.clustering import cluster_embeddings
        vecs = np.random.rand(2, 384).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        labels = cluster_embeddings(vecs)
        assert (labels == -1).all()

    def test_identical_vectors_cluster_together(self):
        from embedding.clustering import cluster_embeddings
        # 10 identical vectors should form one cluster
        vec = np.random.rand(384).astype(np.float32)
        vec /= np.linalg.norm(vec)
        vecs = np.tile(vec, (10, 1))
        labels = cluster_embeddings(vecs)
        # All same cluster (not noise)
        assert len(set(labels)) == 1
        assert -1 not in labels
