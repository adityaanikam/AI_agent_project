# Classifier evaluation samples

`samples.jsonl` holds one labelled sample per line. `scripts/eval_classifier.py`
reads it, classifies every sample the same way the app does (model answer,
repair on a parse failure, keyword heuristic last) and prints accuracy plus a
confusion table for `input_type` and for `business_intent`.

## Line format

Each line is one JSON object:

| key | required | value |
|---|---|---|
| `id` | yes | unique name, shown in the per-sample output |
| `input_type` | yes | expected label: `email`, `json` or `pdf` |
| `business_intent` | yes | expected label: `Invoice`, `Complaint`, `RFQ`, `Regulation`, `Fraud Risk`, `Certificate`, `Report` or `General` |
| `input` | one of `input` / `file` | the raw text the classifier receives (a whole email with headers, or a JSON document as a string) |
| `file` | one of `input` / `file` | path relative to the samples file, read as bytes like an upload (use this for PDFs) |

Blank lines are ignored. A bad line stops the run with its line number.

Examples:

```json
{"id": "email-rfq", "input_type": "email", "business_intent": "RFQ", "input": "From: a@x.example\nTo: b@y.example\nSubject: Quote please\n\nPlease quote 500 laptops."}
{"id": "pdf-invoice", "input_type": "pdf", "business_intent": "Invoice", "file": "files/invoice_acme.pdf"}
```

## Adding samples

1. Append a line to `samples.jsonl` (or write a new file and pass `--samples path`).
2. For a PDF, put the file under `eval/files/`. To make a simple text PDF:
   `python scripts/make_text_pdf.py eval/files/my.pdf "First line" "Second line"`
3. Run `python -m pytest tests/test_eval_classifier.py` to check the file still loads.
   That test also expects exactly 12 shipped samples; update it when you add to the shipped file.

## Shipped samples

12 samples: 4 emails, 4 JSON payloads, 4 PDFs. The PDFs in `files/` were made
with `scripts/make_text_pdf.py`. The labels are the intended answers, written
before any model was run on them.
