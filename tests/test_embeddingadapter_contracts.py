import math

from components.embeddingadapter.contracts import EmbedRequest
from components.embeddingadapter.adapter_fake import FakeEmbeddingAdapter


def test_fake_embedding_shapes_and_normalization():
    adapter = FakeEmbeddingAdapter(default_dims=64)
    texts = ["hello", "world", "hello world"]
    req = EmbedRequest(texts=texts, model="unit-test-model", normalize=True)
    res = adapter.embed(req)

    assert len(res.vectors) == len(texts)
    assert res.dimensions == 64
    assert res.model == "unit-test-model"
    assert res.provider == "fake"
    assert res.normalized is True

    # All vectors have identical dims and are L2 normalized
    for v in res.vectors:
        assert len(v) == 64
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6


def test_fake_embedding_respects_dimensions_override():
    adapter = FakeEmbeddingAdapter(default_dims=64)
    req = EmbedRequest(texts=["a"], model="m", normalize=False, dimensions=32)
    res = adapter.embed(req)
    assert len(res.vectors) == 1
    assert len(res.vectors[0]) == 32
    assert res.dimensions == 32
    # not normalized
    norm = math.sqrt(sum(x * x for x in res.vectors[0]))
    assert norm > 0.0 and abs(norm - 1.0) > 1e-6


