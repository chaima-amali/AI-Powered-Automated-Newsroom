"""
tests/test_embedding_pipeline.py
----------------------------------
Unit tests for the embedding generator, clustering, and repository helpers.
Run: pytest tests/ -v
"""

from pathlib import Path

import matplotlib
import numpy as np
import pytest
from sklearn.decomposition import PCA

matplotlib.use("Agg")
import matplotlib.pyplot as plt

EMBED_DIM = 768


# ── embedding/generator.py ────────────────────────────────────────────────────

class TestBuildText:
    def test_title_and_content_format(self):
        from embedding.generator import build_text
        result = build_text("My Title", "First line.\nSecond line.\nThird line.")
        assert result.startswith("My Title. My Title.")

    def test_html_cleaning(self):
        from embedding.generator import build_text
        result = build_text("<b>Title</b>", "<p>Hello <i>world</i></p>")
        assert "<" not in result
        assert "Title" in result
        assert "Hello world" in result

    def test_missing_content(self):
        from embedding.generator import build_text
        assert build_text("Only Title", None) == "Only Title. Only Title"
        assert build_text("Only Title", "") == "Only Title. Only Title"

    def test_empty_title(self):
        from embedding.generator import build_text
        result = build_text("", "some content")
        assert "some content" in result


class TestEmbedTexts:
    def test_returns_correct_shape(self):
        from embedding.generator import embed_texts
        vecs = embed_texts(["Hello world", "News article text"])
        assert vecs.shape == (2, EMBED_DIM)
        assert vecs.dtype == np.float32

    def test_empty_input(self):
        from embedding.generator import embed_texts
        vecs = embed_texts([])
        assert vecs.shape == (0, EMBED_DIM)

    def test_vectors_are_normalised(self):
        from embedding.generator import embed_texts
        vecs = embed_texts(["Test sentence"])
        norms = np.linalg.norm(vecs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)


# ── embedding/clustering.py ───────────────────────────────────────────────────

class TestClusterEmbeddings:
    def test_empty_array(self):
        from embedding.clustering import cluster_embeddings
        labels = cluster_embeddings(np.array([]).reshape(0, EMBED_DIM))
        assert labels.shape == (0,)

    def test_fewer_than_min_samples(self):
        from embedding.clustering import cluster_embeddings
        vecs = np.random.rand(1, EMBED_DIM).astype(np.float32)
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        labels = cluster_embeddings(vecs)
        assert (labels == -1).all()

    def test_identical_vectors_cluster_together(self):
        from embedding.clustering import cluster_embeddings
        # 10 identical vectors should form one cluster
        vec = np.random.rand(EMBED_DIM).astype(np.float32)
        vec /= np.linalg.norm(vec)
        vecs = np.tile(vec, (10, 1))
        labels = cluster_embeddings(vecs)
        # All same cluster (not noise)
        assert len(set(labels)) == 1
        assert -1 not in labels


class TestClusteringGraph:
    def test_generate_clustering_graph_artifact(self):
        rng = np.random.default_rng(42)

        cluster_a = rng.normal(0.0, 0.07, size=(30, EMBED_DIM)).astype(np.float32)
        cluster_b = rng.normal(1.0, 0.07, size=(30, EMBED_DIM)).astype(np.float32)
        vectors = np.vstack([cluster_a, cluster_b]).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        from embedding.clustering import cluster_embeddings

        labels = cluster_embeddings(vectors)

        projection = PCA(n_components=2, random_state=42).fit_transform(vectors)
        output_path = Path("artifacts") / "tests" / "clustering_graph_test.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(figsize=(8, 6))
        for label in sorted(set(int(item) for item in labels)):
            points = projection[labels == label]
            marker = "x" if label == -1 else "o"
            ax.scatter(points[:, 0], points[:, 1], s=24, marker=marker, label=f"cluster {label}")

        ax.set_title("Test clustering graph (PCA projection)")
        ax.set_xlabel("PC1")
        ax.set_ylabel("PC2")
        ax.legend(loc="best", fontsize=8)
        fig.tight_layout()
        fig.savefig(output_path, dpi=180)
        plt.close(fig)

        assert output_path.exists()
        assert output_path.stat().st_size > 0
