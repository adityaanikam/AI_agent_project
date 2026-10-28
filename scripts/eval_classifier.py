#!/usr/bin/env python3
"""
Measure classifier accuracy on labelled samples and print confusion tables

Usage:
  python scripts/eval_classifier.py                   # model from FLOWBIT_LLM_PROVIDER (default ollama)
  python scripts/eval_classifier.py --provider fake   # no model: measures the heuristic fallback alone
  python scripts/eval_classifier.py --samples path/to/samples.jsonl

The classifier runs exactly as in the app: model answer, repair on a parse
failure, keyword heuristic last. Sample format: eval/README.md
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, get_args

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.graph import Agents, build_graph  # noqa: E402
from app.llm import get_chat_model  # noqa: E402
from app.schemas.classification import BusinessIntent, InputType  # noqa: E402

INPUT_TYPES = list(get_args(InputType))
INTENTS = list(get_args(BusinessIntent))
DEFAULT_SAMPLES = ROOT / "eval" / "samples.jsonl"


def load_samples(path: Path) -> List[Dict[str, Any]]:
    """Read and check a samples file; raises ValueError naming the bad line"""
    samples = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path}:{number}"
        try:
            sample = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{where}: not valid JSON ({e})")
        for key in ("id", "input_type", "business_intent"):
            if not sample.get(key):
                raise ValueError(f"{where}: missing '{key}'")
        if sample["input_type"] not in INPUT_TYPES:
            raise ValueError(f"{where}: input_type must be one of {INPUT_TYPES}")
        if sample["business_intent"] not in INTENTS:
            raise ValueError(f"{where}: business_intent must be one of {INTENTS}")
        if ("input" in sample) == ("file" in sample):
            raise ValueError(f"{where}: give exactly one of 'input' or 'file'")

        if "file" in sample:
            file_path = path.parent / sample["file"]
            if not file_path.is_file():
                raise ValueError(f"{where}: file not found: {file_path}")
            filename, content = file_path.name, file_path.read_bytes()
        else:
            filename, content = f"{sample['id']}.txt", sample["input"].encode("utf-8")

        samples.append({
            "id": sample["id"],
            "filename": filename,
            "content": content,
            "input_type": sample["input_type"],
            "business_intent": sample["business_intent"]
        })
    if not samples:
        raise ValueError(f"{path}: no samples")
    return samples


def evaluate(llm, samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify every sample with the app's classification nodes"""
    graph = build_graph(Agents.with_llm(llm), classification_only=True)
    rows = []
    for sample in samples:
        out = graph.invoke({"process_id": sample["id"], "filename": sample["filename"],
                            "content": sample["content"]})
        classification = out["classification"]
        rows.append({
            "id": sample["id"],
            "expected_type": sample["input_type"],
            "predicted_type": classification["input_type"],
            "expected_intent": sample["business_intent"],
            "predicted_intent": classification["business_intent"],
            "confidence": classification["confidence"],
            "source": out["classification_source"]
        })
    total = len(rows)
    return {
        "rows": rows,
        "input_type_accuracy": sum(r["expected_type"] == r["predicted_type"] for r in rows) / total,
        "business_intent_accuracy": sum(r["expected_intent"] == r["predicted_intent"] for r in rows) / total,
        "sources": dict(Counter(r["source"] for r in rows))
    }


def confusion_table(rows: List[Dict[str, Any]], expected: str, predicted: str, labels: List[str]) -> str:
    """Rows are the true label, columns the predicted label"""
    seen = {r[expected] for r in rows} | {r[predicted] for r in rows}
    labels = [l for l in labels if l in seen] + sorted(seen - set(labels))
    counts = Counter((r[expected], r[predicted]) for r in rows)

    corner = "actual \\ predicted"
    first = max(len(corner), *(len(l) for l in labels))
    widths = [max(len(l), 3) for l in labels]
    lines = ["  ".join([corner.ljust(first)] + [l.rjust(w) for l, w in zip(labels, widths)])]
    for actual in labels:
        cells = [str(counts[(actual, p)] or ".").rjust(w) for p, w in zip(labels, widths)]
        lines.append("  ".join([actual.ljust(first)] + cells))
    return "\n".join(lines)


def report(result: Dict[str, Any]) -> str:
    rows = result["rows"]
    lines = ["Per sample:"]
    id_width = max(len(r["id"]) for r in rows)
    for r in rows:
        mark = "ok  " if (r["expected_type"], r["expected_intent"]) == (r["predicted_type"], r["predicted_intent"]) else "MISS"
        lines.append(
            f"  {mark} {r['id'].ljust(id_width)}  type {r['expected_type']}->{r['predicted_type']}"
            f"  intent {r['expected_intent']}->{r['predicted_intent']}"
            f"  conf {r['confidence']:.2f}  via {r['source']}"
        )
    total = len(rows)
    lines += [
        "",
        f"Samples: {total}",
        f"input_type accuracy:      {result['input_type_accuracy']:.1%}",
        f"business_intent accuracy: {result['business_intent_accuracy']:.1%}",
        "Answer source: " + ", ".join(f"{k}={v}" for k, v in sorted(result["sources"].items())),
        "",
        "input_type confusion:",
        confusion_table(rows, "expected_type", "predicted_type", INPUT_TYPES),
        "",
        "business_intent confusion:",
        confusion_table(rows, "expected_intent", "predicted_intent", INTENTS)
    ]
    fallback = result["sources"].get("heuristic", 0)
    if fallback:
        lines += ["", f"Note: the model gave no valid answer for {fallback} of {total} samples; "
                      "those were classified by the keyword heuristic."]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--provider", choices=["ollama", "gemini", "fake"],
                        help="defaults to FLOWBIT_LLM_PROVIDER, then ollama")
    args = parser.parse_args(argv)

    samples = load_samples(args.samples)
    result = evaluate(get_chat_model(args.provider), samples)
    print(report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
