import math
import pytest

from components.vectorstoreadapter.adapters.inmemory import InMemoryVectorStore
from components.vectorstoreadapter.models import (
    VectorRecord,
    DNFFilter,
    FilterCondition,
)
from components.vectorstoreadapter.errors import NamespaceNotFound, BadRequest


def _rec(i: str, v, md=None, text=None):
    return VectorRecord(id=i, vector=v, metadata=md or {}, text=text)


def test_upsert_and_stats():
    vs = InMemoryVectorStore()
    ns = "tenantA__default"
    out = vs.upsert(ns, [
        _rec("r1", [1, 0, 0], {"lang": "en"}),
        _rec("r2", [0, 1, 0], {"lang": "ro"}),
    ])
    assert out.upserted_count == 2
    st = vs.stats(ns)
    assert st.namespaces[ns]["vector_count"] == 2


def test_query_cosine_ordering():
    vs = InMemoryVectorStore()
    ns = "ns1"
    vs.upsert(ns, [
        _rec("a", [1, 0], {"t": 1}),
        _rec("b", [0, 1], {"t": 2}),
        _rec("c", [1, 1], {"t": 3}),
    ])
    res = vs.query(ns, [1, 0], top_k=3)
    ids = [m.id for m in res.matches]
    # cosine with [1,0] -> a:1.0, c:~0.707, b:0.0
    assert ids == ["a", "c", "b"]
    assert math.isclose(res.matches[0].score, 1.0, rel_tol=1e-6)


def test_query_with_filter_dnf():
    vs = InMemoryVectorStore()
    ns = "nsF"
    vs.upsert(ns, [
        _rec("x", [1, 0], {"lang": "en", "tier": "pro"}),
        _rec("y", [0, 1], {"lang": "ro", "tier": "free"}),
        _rec("z", [1, 1], {"lang": "en", "tier": "free"}),
    ])
    # (lang=en AND tier=free) OR (lang=ro)
    flt = DNFFilter(groups=[
        [FilterCondition(field="lang", op="eq", value="en"),
         FilterCondition(field="tier", op="eq", value="free")],
        [FilterCondition(field="lang", op="eq", value="ro")]
    ])
    res = vs.query(ns, [1, 0], top_k=5, flt=flt)
    ids = [m.id for m in res.matches]
    # Filter matches: y (ro), z (en+free). x excluded (en+pro).
    assert set(ids) == {"y", "z"}


def test_fetch_and_delete():
    vs = InMemoryVectorStore()
    ns = "nsD"
    vs.upsert(ns, [
        _rec("a", [1], {"k": 1}),
        _rec("b", [2], {"k": 2}),
        _rec("c", [3], {"k": 3}),
    ])
    got = vs.fetch(ns, ["a", "c", "nope"])
    assert set(got.records.keys()) == {"a", "c"}

    # delete by ids
    d1 = vs.delete(ns, ids=["a"])
    assert d1.deleted_count == 1
    # delete by filter
    flt = DNFFilter(groups=[[FilterCondition(field="k", op="gte", value=3)]])
    d2 = vs.delete(ns, flt=flt)
    assert d2.deleted_count == 1
    # delete remaining (no ids/filters -> clear)
    d3 = vs.delete(ns)
    assert d3.deleted_count == 1
    assert vs.stats(ns).namespaces[ns]["vector_count"] == 0


def test_errors():
    vs = InMemoryVectorStore()
    with pytest.raises(NamespaceNotFound):
        vs.query("missing", [1, 0], 3)
    ns = "nsErr"
    vs.upsert(ns, [_rec("a", [1, 0])])
    with pytest.raises(BadRequest):
        vs.query(ns, [1, 0, 0], 3)  # dim mismatch

---

### Notes

* This iteration gives you a clean **port** + **contracts** + **in-memory adapter** with tests you can run immediately.
* Pinecone adapter is stubbed to keep the port stable; when you’re ready, we can fill in the actual client calls under the same contracts.
* I kept observability light (comments where the logger/spans go) per your “gate” wrapper idea. Happy to wire OTel spans next.

If you want this adapter auto-wired into other components (Indexer/SearchService) in this pass, say the word and I’ll add a minimal DI provider (e.g., `get_vector_store()` factory) and show usage in those components’ edges.
