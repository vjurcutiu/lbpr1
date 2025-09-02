import pytest
from components.apigateway.contracts import (
    UWFResponse, ErrorPayload, MetaPayload, SearchRequest, ChatCompletionRequest, ChatMessage
)

def test_uwf_success_shape():
    resp = UWFResponse(ok=True, result={"x": 1}, error=None, meta=MetaPayload(trace_id="t", request_id="r"))
    assert resp.ok is True
    assert resp.result == {"x": 1}
    assert resp.error is None
    assert resp.meta.trace_id == "t"

def test_uwf_error_shape():
    err = ErrorPayload(type="VALIDATION", code="bad_input", message="nope")
    resp = UWFResponse(ok=False, result=None, error=err, meta=MetaPayload())
    assert resp.ok is False
    assert resp.result is None
    assert resp.error.code == "bad_input"

def test_search_request_validation():
    s = SearchRequest(query="hello", top_k=10)
    assert s.top_k == 10
    with pytest.raises(Exception):
        SearchRequest(query="hello", top_k=0)

def test_chat_completion_request():
    req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hi")])
    assert req.messages[0].role == "user"
