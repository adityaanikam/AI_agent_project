from typing import Literal

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.llm import (
    FakeChatModel,
    get_chat_model,
    structured_call,
    structured_call_with_repair,
)


class Verdict(BaseModel):
    label: Literal["yes", "no"]
    score: float


MESSAGES = [HumanMessage(content="is it?")]


def test_valid_structured_reply_is_parsed():
    llm = FakeChatModel(responses=[{"label": "yes", "score": 0.9}])
    result = structured_call(llm, Verdict, MESSAGES)
    assert result.ok
    assert result.parsed == Verdict(label="yes", score=0.9)
    assert len(llm.calls) == 1


def test_plain_text_reply_is_a_parse_failure():
    llm = FakeChatModel(responses=["```json\n{\"label\": \"yes\"}\n```"])
    result = structured_call(llm, Verdict, MESSAGES)
    assert not result.ok
    assert result.failure == "parse"
    assert "label" in result.raw


def test_schema_violation_is_a_parse_failure():
    llm = FakeChatModel(responses=[{"label": "maybe", "score": 0.9}])
    result = structured_call(llm, Verdict, MESSAGES)
    assert result.failure == "parse"
    assert "maybe" in result.raw
    assert result.error


def test_unreachable_model_is_a_call_failure():
    llm = FakeChatModel(responses=[ConnectionError("refused")])
    result = structured_call(llm, Verdict, MESSAGES)
    assert result.failure == "call"
    assert "refused" in result.error


def test_repair_resends_bad_reply_and_error():
    llm = FakeChatModel(responses=[{"label": "maybe", "score": 1}, {"label": "no", "score": 0.2}])
    result = structured_call_with_repair(llm, Verdict, MESSAGES)
    assert result.parsed == Verdict(label="no", score=0.2)
    assert len(llm.calls) == 2
    repair_prompt = llm.calls[1]
    assert "maybe" in repair_prompt[-2].content
    assert "did not match" in repair_prompt[-1].content


def test_repair_is_skipped_when_model_is_unreachable():
    llm = FakeChatModel(responses=[ConnectionError("refused")])
    result = structured_call_with_repair(llm, Verdict, MESSAGES)
    assert result.failure == "call"
    assert len(llm.calls) == 1


def test_fake_without_script_replies_unstructured():
    result = structured_call(FakeChatModel(), Verdict, MESSAGES)
    assert result.failure == "parse"


def test_responder_is_used_after_scripted_responses():
    llm = FakeChatModel(responses=[{"label": "yes", "score": 1}],
                        responder=lambda messages: {"label": "no", "score": 0})
    assert structured_call(llm, Verdict, MESSAGES).parsed.label == "yes"
    assert structured_call(llm, Verdict, MESSAGES).parsed.label == "no"


def test_provider_factory(monkeypatch):
    assert isinstance(get_chat_model("fake"), FakeChatModel)
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")
    ollama = get_chat_model("ollama")
    assert type(ollama).__name__ == "ChatOllama"
    assert ollama.model == "qwen2.5:7b"
    with pytest.raises(ValueError):
        get_chat_model("nope")


def _ollama_with_reply(content, seen):
    import json

    import httpx
    from langchain_ollama import ChatOllama

    def handler(request):
        seen.append(json.loads(request.content))
        line = {
            "model": "m",
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
        }
        return httpx.Response(200, content=(json.dumps(line) + "\n").encode())

    return ChatOllama(model="m", client_kwargs={"transport": httpx.MockTransport(handler)})


def test_ollama_receives_schema_as_format_and_reply_is_parsed():
    seen = []
    llm = _ollama_with_reply('{"label": "no", "score": 0.1}', seen)
    result = structured_call(llm, Verdict, MESSAGES)
    assert result.parsed == Verdict(label="no", score=0.1)
    assert seen[0]["format"]["properties"]["label"]["enum"] == ["yes", "no"]


def test_ollama_reply_outside_schema_is_a_parse_failure():
    llm = _ollama_with_reply('{"label": "maybe", "score": 0.1}', [])
    result = structured_call(llm, Verdict, MESSAGES)
    assert result.failure == "parse"
    assert "maybe" in result.raw


def test_gemini_provider_is_optional(monkeypatch):
    pytest.importorskip("langchain_google_genai")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    gemini = get_chat_model("gemini")
    assert type(gemini).__name__ == "ChatGoogleGenerativeAI"
    assert gemini.model.endswith("gemini-test")
