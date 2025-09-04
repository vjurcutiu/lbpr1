import pytest
from components.chatservice.service import InMemoryChatService
from components.chatservice.contracts import (
    CreateChatRequest,
    GetChatRequest,
    ListChatsRequest,
    ListMessagesRequest,
    PostUserMessageRequest,
    Role,
)


class FakeLLM:
    provider = "fake-llm"

    def generate(self, *, tenant_id, messages, params=None) -> str:
        last_user = next((m for m in reversed(messages) if m.role.value == "user"), None)
        txt = last_user.content if last_user else "Hello."
        return f"(assistant) You said: {txt}"


def test_create_and_get_chat_roundtrip():
    svc = InMemoryChatService()
    r = svc.create_chat(CreateChatRequest(tenant_id="t1", title="Hello"))
    chat = r.chat
    assert chat.title == "Hello"

    g = svc.get_chat(GetChatRequest(tenant_id="t1", chat_id=chat.id))
    assert g.chat.id == chat.id
    assert g.last_messages == []


def test_post_message_generates_assistant():
    svc = InMemoryChatService()
    chat = svc.create_chat(CreateChatRequest(tenant_id="t1", title=None)).chat

    llm = FakeLLM()
    resp = svc.post_user_message(
        PostUserMessageRequest(tenant_id="t1", chat_id=chat.id, content="Hi", stream=False),
        llm=llm,
        retrieval=None,
    )
    assert resp.user_message.role.value == "user"
    assert resp.assistant_message is not None
    assert resp.assistant_message.role.value == "assistant"
    assert "You said: Hi" in resp.assistant_message.content

    # history contains both
    msgs = svc.list_messages(ListMessagesRequest(tenant_id="t1", chat_id=chat.id)).items
    assert len(msgs) == 2
    assert msgs[0].role == Role.user
    assert msgs[1].role == Role.assistant


def test_list_chats_is_tenant_scoped():
    svc = InMemoryChatService()
    svc.create_chat(CreateChatRequest(tenant_id="A", title="A1"))
    svc.create_chat(CreateChatRequest(tenant_id="B", title="B1"))

    la = svc.list_chats(ListChatsRequest(tenant_id="A"))
    lb = svc.list_chats(ListChatsRequest(tenant_id="B"))
    assert all(c.tenant_id == "A" for c in la.items)
    assert all(c.tenant_id == "B" for c in lb.items)

