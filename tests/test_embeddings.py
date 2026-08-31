import pytest

from kg.embeddings import (
    CachedEmbedder,
    EmbeddingCache,
    HashEmbedder,
    OpenAICompatibleEmbedder,
    OpenRouterEmbedder,
    build_embedder,
    cosine,
    nearest,
)


def test_hash_embedder_is_deterministic_and_normalised():
    e = HashEmbedder(dim=32)
    a1, a2 = e.embed(["Recycling-Beton"])[0], e.embed(["Recycling-Beton"])[0]
    assert a1 == a2
    assert abs(sum(x * x for x in a1) - 1.0) < 1e-6


def test_hash_embedder_scores_shared_words_higher_than_unrelated_text():
    e = HashEmbedder(dim=64)
    a, b, c = e.embed(["Recycling Beton", "Beton Recycling Verfahren", "Ländlicher Leerstand"])
    assert cosine(a, b) > cosine(a, c)


def test_nearest_returns_the_k_closest_keys_in_order():
    e = HashEmbedder(dim=64)
    query = e.embed(["modulares Bauen"])[0]
    candidates = {
        "t1": e.embed(["modulares Bauen im Bestand"])[0],
        "t2": e.embed(["Bodenversiegelung"])[0],
        "t3": e.embed(["modulares Bauen"])[0],
    }
    assert nearest(query, candidates, k=2) == ["t3", "t1"]


def test_nearest_handles_fewer_candidates_than_k():
    e = HashEmbedder(dim=16)
    assert nearest(e.embed(["x"])[0], {}, k=5) == []


class FakePost:
    """Stands in for the httpx POST. Records every request body."""

    def __init__(self, dim=4):
        self.dim = dim
        self.bodies = []

    def __call__(self, url, headers, json):
        self.bodies.append(json)
        return {
            "data": [
                {"index": i, "embedding": [float(len(t))] + [0.0] * (self.dim - 1)}
                for i, t in enumerate(json["input"])
            ]
        }


def test_openrouter_embedder_sends_an_openai_compatible_request():
    post = FakePost()
    embedder = OpenRouterEmbedder(
        model="openai/text-embedding-3-small",
        api_key="sk-or-test",
        url="https://openrouter.ai/api/v1/embeddings",
        post=post,
    )

    vectors = embedder.embed(["Holzbau", "Bodenpreise"])

    assert post.bodies == [
        {"model": "openai/text-embedding-3-small", "input": ["Holzbau", "Bodenpreise"]}
    ]
    assert len(vectors) == 2
    # Vectors come back normalised so `cosine` is a plain dot product.
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-6


def test_openrouter_embedder_reorders_by_index():
    class ShuffledPost:
        def __call__(self, url, headers, json):
            return {"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]}

    embedder = OpenRouterEmbedder("m", "k", "u", post=ShuffledPost())
    assert embedder.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_openrouter_embedder_raises_on_a_short_response():
    # Finding 5: fewer rows than inputs would otherwise mis-pair vectors onto
    # the wrong labels by position after the sort.
    class ShortPost:
        def __call__(self, url, headers, json):
            return {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}

    embedder = OpenRouterEmbedder("m", "k", "u", post=ShortPost())
    with pytest.raises(RuntimeError, match="2"):
        embedder.embed(["a", "b"])


def test_openrouter_embedder_raises_when_indices_are_missing():
    # Finding 5: rows missing "index" all default to 0 and collide in the
    # sort, silently mis-pairing vectors — this must raise instead.
    class MissingIndexPost:
        def __call__(self, url, headers, json):
            return {"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]}

    embedder = OpenRouterEmbedder("m", "k", "u", post=MissingIndexPost())
    with pytest.raises(RuntimeError):
        embedder.embed(["a", "b"])


def test_openrouter_embedder_raises_when_indices_are_duplicated():
    class DuplicateIndexPost:
        def __call__(self, url, headers, json):
            return {"data": [
                {"index": 0, "embedding": [1.0, 0.0]},
                {"index": 0, "embedding": [0.0, 1.0]},
            ]}

    embedder = OpenRouterEmbedder("m", "k", "u", post=DuplicateIndexPost())
    with pytest.raises(RuntimeError):
        embedder.embed(["a", "b"])


def test_openrouter_embedder_refuses_to_run_without_a_key():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder("m", None, "u").embed(["a"])


def test_openrouter_embedder_skips_the_call_for_an_empty_batch():
    post = FakePost()
    assert OpenRouterEmbedder("m", "k", "u", post=post).embed([]) == []
    assert post.bodies == []


def test_cache_only_sends_misses_and_preserves_input_order(tmp_path):
    post = FakePost()
    inner = OpenRouterEmbedder("m", "k", "u", post=post)
    cache = EmbeddingCache(tmp_path / "emb.sqlite3")
    embedder = CachedEmbedder(inner, cache, model="m")

    first = embedder.embed(["Holzbau", "Bodenpreise"])
    second = embedder.embed(["Bodenpreise", "Holzbau", "Leerstand"])

    # Second call sends ONLY the unseen label.
    assert [b["input"] for b in post.bodies] == [
        ["Holzbau", "Bodenpreise"],
        ["Leerstand"],
    ]
    assert second[0] == first[1]
    assert second[1] == first[0]


def test_cache_survives_a_restart_so_a_rerun_is_offline_and_free(tmp_path):
    """Spec 6.2: the second simulation run must need neither key nor network."""
    path = tmp_path / "emb.sqlite3"
    post = FakePost()
    warm = CachedEmbedder(OpenRouterEmbedder("m", "k", "u", post=post), EmbeddingCache(path), "m")
    expected = warm.embed(["Holzbau"])

    class ExplodingPost:
        def __call__(self, *args, **kwargs):
            raise AssertionError("cache miss: the re-run went online")

    offline = CachedEmbedder(
        OpenRouterEmbedder("m", None, "u", post=ExplodingPost()), EmbeddingCache(path), "m"
    )
    assert offline.embed(["Holzbau"]) == expected


def test_cache_is_keyed_by_model_as_well_as_text(tmp_path):
    cache = EmbeddingCache(tmp_path / "emb.sqlite3")
    post = FakePost()
    CachedEmbedder(OpenRouterEmbedder("m1", "k", "u", post=post), cache, "m1").embed(["Holzbau"])
    CachedEmbedder(OpenRouterEmbedder("m2", "k", "u", post=post), cache, "m2").embed(["Holzbau"])
    assert len(post.bodies) == 2


# --- anbieterneutral, ohne den alten Namen zu brechen ----------------------


def test_the_old_class_name_still_works():
    """Der Name `OpenRouterEmbedder` steht in Notizen, Probes und Tests. Der
    Alias kostet eine Zeile und erspart einen Umbau, der nichts verbessert."""
    assert OpenRouterEmbedder is OpenAICompatibleEmbedder


def make_cfg(tmp_path, **overrides):
    from kg.config import Config

    return Config(data_dir=tmp_path / "state", openrouter_api_key="sk-or-test", **overrides)


def test_build_embedder_stays_on_openrouter_without_new_keys(tmp_path):
    """Fallback-Regel: eine unveränderte config.toml embedded wie bisher."""
    embedder = build_embedder(make_cfg(tmp_path))

    assert isinstance(embedder.inner, OpenAICompatibleEmbedder)
    assert embedder.inner.url == "https://openrouter.ai/api/v1/embeddings"
    assert embedder.inner.model == "openai/text-embedding-3-small"
    assert embedder.inner.api_key == "sk-or-test"


def test_build_embedder_can_be_pointed_at_infomaniak(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY", "sk-infomaniak")
    cfg = make_cfg(
        tmp_path,
        embedding_model="bge_multilingual_gemma2",
        embedding_url="https://api.infomaniak.com/2/ai/110416/openai/v1/embeddings",
        embedding_api_key_env="HERMES_CUSTOM_API_INFOMANIAK_COM_API_KEY",
    )

    embedder = build_embedder(cfg)

    assert embedder.inner.url == "https://api.infomaniak.com/2/ai/110416/openai/v1/embeddings"
    assert embedder.inner.model == "bge_multilingual_gemma2"
    assert embedder.inner.api_key == "sk-infomaniak"
    # Der Cache-Schlüssel wandert mit dem Modell mit — alte Vektoren aus einem
    # anderen Modell werden nie versehentlich mitbenutzt.
    assert embedder.model == "bge_multilingual_gemma2"


def test_the_hash_embedder_route_is_untouched(tmp_path):
    assert isinstance(build_embedder(make_cfg(tmp_path), hash_only=True), HashEmbedder)
