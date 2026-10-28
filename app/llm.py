"""
Chat model factory, a fake chat model for tests, and structured-output helpers
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Type

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# What the fake model says when it has no scripted response left. It is plain
# text, so structured parsing fails and callers take their fallback path.
FAKE_UNSTRUCTURED_REPLY = "fake model: no scripted response"


def get_chat_model(provider: Optional[str] = None) -> BaseChatModel:
    """
    Build the chat model selected by FLOWBIT_LLM_PROVIDER

    ollama (default): local model through Ollama, no API key
    gemini: optional, needs langchain-google-genai and GOOGLE_API_KEY
    fake: scripted model used by tests and offline runs
    """
    provider = (provider or os.getenv("FLOWBIT_LLM_PROVIDER", "ollama")).lower()

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
            temperature=0
        )
    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise RuntimeError(
                "FLOWBIT_LLM_PROVIDER=gemini needs: pip install -r requirements-gemini.txt"
            ) from e
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            temperature=0
        )
    if provider == "fake":
        return FakeChatModel()
    raise ValueError(f"Unknown FLOWBIT_LLM_PROVIDER: {provider}")


class FakeChatModel(BaseChatModel):
    """
    Scripted chat model, no network

    Each call consumes one entry of `responses`:
    - dict: returned as structured output (a tool call carrying the dict)
    - str: returned as plain text, so structured parsing fails
    - Exception: raised, like a model that is unreachable
    `responder(messages)` is used instead once `responses` is empty.
    Every call's messages are recorded in `calls`.
    """

    responses: List[Any] = Field(default_factory=list)
    responder: Optional[Callable[[Sequence[BaseMessage]], Any]] = None
    calls: List[Sequence[BaseMessage]] = Field(default_factory=list)
    bound_tool: Optional[str] = None

    @property
    def _llm_type(self) -> str:
        return "flowbit-fake"

    def bind_tools(self, tools, **kwargs):
        name = convert_to_openai_tool(tools[0])["function"]["name"]
        # Shallow copy: the copy shares `responses` and `calls` with self
        return self.model_copy(update={"bound_tool": name})

    def _next_response(self, messages) -> Any:
        if self.responses:
            return self.responses.pop(0)
        if self.responder is not None:
            return self.responder(messages)
        return FAKE_UNSTRUCTURED_REPLY

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.calls.append(list(messages))
        response = self._next_response(messages)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            message = AIMessage(content="", tool_calls=[{
                "name": self.bound_tool or "structured_output",
                "args": response,
                "id": f"call_{len(self.calls)}"
            }])
        else:
            message = AIMessage(content=str(response))
        return ChatResult(generations=[ChatGeneration(message=message)])


@dataclass
class StructuredResult:
    """Outcome of one structured-output call"""
    parsed: Optional[BaseModel]
    raw: str
    error: Optional[str] = None
    # None on success, "parse" when the reply did not match the schema,
    # "call" when the model could not be reached at all
    failure: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.parsed is not None


def _raw_text(message: Any) -> str:
    if message is None:
        return ""
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        return json.dumps(tool_calls[0].get("args", {}), default=str)
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else json.dumps(content, default=str)


def structured_call(llm: BaseChatModel, schema: Type[BaseModel],
                    messages: Sequence[BaseMessage]) -> StructuredResult:
    """Ask the model for an instance of `schema` using its native structured output"""
    try:
        out = llm.with_structured_output(schema, include_raw=True).invoke(list(messages))
    except Exception as e:
        return StructuredResult(None, "", f"{type(e).__name__}: {e}", "call")

    raw = _raw_text(out.get("raw"))
    parsed = out.get("parsed")
    if parsed is None:
        error = out.get("parsing_error")
        return StructuredResult(None, raw, str(error) if error else "no structured output in reply", "parse")
    if isinstance(parsed, dict):
        parsed = schema.model_validate(parsed)
    return StructuredResult(parsed, raw)


def repair_messages(messages: Sequence[BaseMessage], failed: StructuredResult) -> List[BaseMessage]:
    """Re-ask with the invalid reply and the validation error appended"""
    return list(messages) + [
        AIMessage(content=failed.raw or "(empty reply)"),
        HumanMessage(content=(
            "Your previous reply did not match the required schema.\n"
            f"Error: {failed.error}\n"
            "Reply again with only a valid object that matches the schema."
        ))
    ]


def structured_call_with_repair(llm: BaseChatModel, schema: Type[BaseModel],
                                messages: Sequence[BaseMessage]) -> StructuredResult:
    """structured_call, plus one repair attempt when the reply failed to parse"""
    first = structured_call(llm, schema, messages)
    if first.failure != "parse":
        return first
    return structured_call(llm, schema, repair_messages(messages, first))
