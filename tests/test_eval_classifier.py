import json

import pytest

from app.llm import FakeChatModel
from scripts.eval_classifier import (
    DEFAULT_SAMPLES,
    INTENTS,
    INPUT_TYPES,
    confusion_table,
    evaluate,
    load_samples,
    main,
    report,
)


def test_shipped_samples_are_valid_and_balanced():
    samples = load_samples(DEFAULT_SAMPLES)
    assert len(samples) == 12
    assert sorted({s["input_type"] for s in samples}) == sorted(INPUT_TYPES)
    assert all(s["business_intent"] in INTENTS for s in samples)
    pdfs = [s for s in samples if s["input_type"] == "pdf"]
    assert all(s["content"].startswith(b"%PDF") for s in pdfs)


def test_fake_model_measures_the_heuristic_fallback():
    result = evaluate(FakeChatModel(), load_samples(DEFAULT_SAMPLES))
    assert result["sources"] == {"heuristic": 12}
    assert 0.0 <= result["business_intent_accuracy"] <= 1.0


def test_accuracy_and_confusion_from_model_answers(tmp_path):
    path = tmp_path / "samples.jsonl"
    rows = [
        {"id": "a", "input": "x", "input_type": "email", "business_intent": "Complaint"},
        {"id": "b", "input": "y", "input_type": "json", "business_intent": "Invoice"},
        {"id": "c", "input": "z", "input_type": "json", "business_intent": "Invoice"},
        {"id": "d", "input": "w", "input_type": "pdf", "business_intent": "Report"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n")
    llm = FakeChatModel(responses=[
        {"input_type": "email", "business_intent": "Complaint", "confidence": 0.9},
        {"input_type": "json", "business_intent": "Invoice", "confidence": 0.9},
        {"input_type": "email", "business_intent": "Fraud Risk", "confidence": 0.7},
        "not json",  # parse failure, then a repaired answer
        {"input_type": "pdf", "business_intent": "Report", "confidence": 0.8},
    ])
    result = evaluate(llm, load_samples(path))
    assert result["input_type_accuracy"] == 0.75
    assert result["business_intent_accuracy"] == 0.75
    assert result["sources"] == {"llm": 3, "repair": 1}

    table = confusion_table(result["rows"], "expected_type", "predicted_type", INPUT_TYPES)
    lines = table.splitlines()
    assert lines[0].split()[-3:] == ["email", "json", "pdf"]
    assert lines[2].split()[-3:] == ["1", "1", "."]  # json row: one read as email, one right
    text = report(result)
    assert "input_type accuracy:      75.0%" in text
    assert "heuristic" not in text


def test_unexpected_predictions_get_their_own_column():
    rows = [{"t": "pdf", "p": "unknown"}]
    table = confusion_table(rows, "t", "p", INPUT_TYPES)
    assert table.splitlines()[0].split()[-2:] == ["pdf", "unknown"]


@pytest.mark.parametrize("line, message", [
    ('{"id": "a", "input": "x", "input_type": "docx", "business_intent": "General"}', "input_type"),
    ('{"id": "a", "input": "x", "input_type": "pdf", "business_intent": "Memo"}', "business_intent"),
    ('{"id": "a", "input_type": "pdf", "business_intent": "General"}', "exactly one"),
    ('{"id": "a", "file": "nope.pdf", "input_type": "pdf", "business_intent": "General"}', "not found"),
    ('{"input": "x", "input_type": "pdf", "business_intent": "General"}', "missing 'id'"),
    ('not json', "not valid JSON"),
])
def test_bad_sample_lines_are_reported(tmp_path, line, message):
    path = tmp_path / "samples.jsonl"
    path.write_text(line + "\n")
    with pytest.raises(ValueError, match=message):
        load_samples(path)


def test_cli_runs_with_fake_provider(capsys):
    assert main(["--provider", "fake"]) == 0
    out = capsys.readouterr().out
    assert "Samples: 12" in out
    assert "business_intent confusion:" in out


def test_eval_runs_through_chat_ollama_without_a_server():
    import httpx
    from langchain_ollama import ChatOllama

    reply = json.dumps({"input_type": "email", "business_intent": "General", "confidence": 0.6})

    def handler(request):
        line = {"model": "m", "created_at": "2026-01-01T00:00:00Z",
                "message": {"role": "assistant", "content": reply}, "done": True, "done_reason": "stop"}
        return httpx.Response(200, content=(json.dumps(line) + "\n").encode())

    llm = ChatOllama(model="m", client_kwargs={"transport": httpx.MockTransport(handler)})
    result = evaluate(llm, load_samples(DEFAULT_SAMPLES))
    assert result["sources"] == {"llm": 12}
    assert result["input_type_accuracy"] == 4 / 12
