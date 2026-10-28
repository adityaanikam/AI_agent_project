# How FlowBit works

One upload becomes one LangGraph run. The run's thread id is the upload's
`process_id`, so its checkpoints, its review pauses and its processing record
all share that id.

## Modules

### `main.py`
**What:** the FastAPI app. `/process` stores a processing record and starts
the graph in a background task. `/status`, `/history` read records.
`/review/{id}` resumes a paused run with the reviewer's decision.
`/resume/{id}` continues a failed run. On startup it resumes unfinished runs
in a background thread.
**Why:** the HTTP layer only creates records and hands work to the runner.
All pipeline logic lives in the graph, so the API can be tested with a fake
model and no server.

### `app/llm.py`
**What:** `get_chat_model()` builds the model named by `FLOWBIT_LLM_PROVIDER`
(Ollama by default, Gemini optional, `fake` for tests). `FakeChatModel` replays
scripted replies: a dict is returned as a valid structured reply, a string as
free text that will not parse, an exception is raised. `structured_call()`
wraps `with_structured_output(schema, include_raw=True)` and returns a
`StructuredResult` that says whether it worked and, if not, whether it was a
parse failure or a call failure. `repair_messages()` builds the re-ask.
**Why:** each provider uses its native structured output (Ollama gets the JSON
schema as its `format`). That replaces the hand-written fence stripping. The
parse/call split matters: re-asking an unreachable server is pointless, so a
call failure skips repair. The fake goes through LangChain's real
`with_structured_output` code (through `bind_tools`), so tests exercise the
same parsing path as production.

### `app/schemas/`
**What:** Pydantic models. `classification.py` (`Classification`, with
`Literal` input types and intents), `email.py` (`EmailAnalysis`), `json.py`
(`JSONAnalysis`), `pdf.py` (`PDFAnalysis`, which reuses `LineItem` and
`DocumentTotals`), `review.py` (`ReviewDecision` for the review endpoint).
**Why:** one schema serves three purposes: it is sent to the model as the
output format, it validates the reply, and it documents the shape. `Literal`
fields replace regex `pattern` fields so the allowed values appear as an enum
in the JSON schema a local model is constrained by.

### `app/agents/classifier_agent.py`
**What:** `llm_classify()` asks for a `Classification`; `repair()` re-asks
with the failed reply and its error; `heuristic()` is the original keyword
classifier, fixed to accept JSON arrays.
**Why:** the three steps are separate methods so each can be its own graph
node. The heuristic reports confidence 0.5, below the review threshold, so a
keyword guess is never acted on without a person seeing it.

### `app/agents/email_agent.py`, `json_agent.py`, `pdf_agent.py`
**What:** parse the input (email headers and body, `json.loads` plus
jsonschema checks, pypdf text extraction plus compliance keyword scan), ask the
model for the matching analysis schema with one repair attempt, and fall back
to the original rule-based analysis if the model gives nothing valid. Each
output now says `analysis_source: "llm"` or `"fallback"`.
**Why:** the deterministic parts (parsing, schema validation, compliance
keywords) never depended on the model and still do not. The model only adds
the analysis. The output shapes are unchanged so the router and the UI still
work. Fixed on the way: a plain-text email always reported
`has_attachments: true`, and a top-level JSON array crashed anomaly detection.

### `app/graph/state.py`
**What:** `FlowState`, the TypedDict that every node reads and updates:
input bytes, classification and its source, the last invalid model reply,
agent output, planned actions with review decisions, the dispatch index and
attempt counter, review history, status, error.
**Why:** everything a node needs to continue must be in the state, because
the state is what the checkpointer saves. The retry counter lives here, so a
crash in the middle of retries resumes at the right attempt.

### `app/graph/builder.py`
**What:** `build_graph()` wires the nodes: `classify`, `repair_classification`,
`heuristic_classify`, `review_classification`, `email_agent` / `json_agent` /
`pdf_agent`, `unsupported_input`, `plan_actions`, `review_actions`,
`dispatch_action`, `finalize`. Conditional edges pick the repair node on a
parse failure, the heuristic on a call failure or failed repair, review on low
confidence, and the agent by `input_type`. `dispatch_action` sends one action
per step; on failure it returns `attempt + 1` and its conditional edge loops
back to itself, sleeping 1, 2, 4 seconds before the retries. `GraphSettings`
holds the threshold, the risky action types and the retry settings.
`classification_only=True` builds just the classification nodes for the eval.
**Why:** the old flow was one function with try/except blocks and a recursive
retry. As a graph, every branch is a named edge that can be tested on its own,
every step is checkpointed, and pausing for a person is a built-in `interrupt`
instead of custom state handling. Review nodes do nothing before `interrupt()`,
because LangGraph runs the node again from the top when it resumes.

### `app/graph/runner.py`
**What:** `GraphRunner` starts, reviews and resumes runs. It streams node
updates and copies `classification`, `agent_output`, `actions_triggered`,
`status` and `error` into the processing record after each step, so
`/status` shows progress. It sets `awaiting_review` when the run stops on an
interrupt and records exceptions as `error`. `resume_incomplete()` finds
records left in a mid-run status and resumes those with a checkpoint.
`sqlite_checkpointer()` opens the `SqliteSaver`. A per-process set stops two
threads running the same thread id at once.
**Why:** the graph stays free of database code, and the API has a small
surface (`start`, `review`, `resume`, `pending_review`, `can_resume`).

### `app/core/router.py`
**What:** `ActionRouter.plan_actions()` turns an agent output into a list of
actions. `send()` makes one HTTP POST. `mock_response()` builds the fallback
response. Endpoints come from environment variables.
**Why:** deciding and delivering are now separate, so the rules are pure
functions tested without HTTP, and retry control moved into the graph. The
rules were fixed to read fields the agents produce: `parsed_data` instead of
`data`, one compliance action only when keywords were found. Rules that read
fields no agent produces (`risk_score`, `compliance_issues`, `customer_data`)
were removed.

### `app/core/memory.py`
**What:** the SQLAlchemy `ProcessingRecord` table behind `/status` and
`/history`, plus `get_by_status()` for startup recovery. The constructor now
accepts a database URL so tests use temp files.
**Why:** kept as it was, so existing databases and the UI still work. The
checkpointer holds the full run state; this table is the readable summary.

### `scripts/eval_classifier.py`
**What:** loads `eval/samples.jsonl`, runs the classification-only graph on
each sample, prints per-sample results, accuracy, which step answered (model,
repair or heuristic), and confusion tables for `input_type` and
`business_intent`.
**Why:** it measures the same nodes the app runs, not a copy of them. With
`--provider fake` no model answers, so it reports the heuristic baseline.

### `scripts/smoke_api.py`, `scripts/make_text_pdf.py`
**What:** the first uploads the three `test_sample.*` files to a running
server and prints the results (it replaces the old `test_api.py`, which
needed `requests`). The second writes a minimal one-page text PDF, used for
the eval samples and in tests.

### `tests/`
**What:** 81 pytest tests: router rules, LLM helpers (including ChatOllama
through a mocked HTTP transport), schemas, agents, every graph branch
(repair, heuristic, both interrupts, retry loop, mock fallback, crash resume,
startup recovery), the HTTP API, and the eval script.
**Why:** no test needs a network or a model.

## Known limits

- Actions are delivered at least once. If the process dies after an endpoint
  accepted an action but before the step was checkpointed, the action is sent
  again on resume.
- After the last retry the router records a mock response with
  `"status": "success"` and `"mock": true`, as the original code did. A real
  outage therefore shows up as a mock, not as a failure.
- The keyword heuristic matches substrings ("Issued" matches "issue"), which
  is why it misclassifies some samples.
- The duplicate-run guard is per process. Running several app processes on one
  checkpoint file would need a lock outside the process.
- The classifier sees the first 800 characters of the raw upload. For a PDF
  that is the raw file, not extracted text, as before.

## Interview questions

1. **Why a state graph instead of plain function calls?**
   Every branch (repair, fallback, review, retry) is an explicit edge that can
   be tested alone, each step is checkpointed for crash recovery, and pausing
   for a person is a built-in primitive.

2. **How does the retry loop work, and why put it in the graph?**
   `dispatch_action` tries one send. On failure it increments `attempt` in the
   state and its conditional edge points back to itself. The counter is
   checkpointed, so a crash mid-retry resumes at the same attempt instead of
   starting over.

3. **What is the difference between the repair node and the heuristic?**
   Repair re-asks the model with its invalid reply and the validation error;
   it helps when the model was close. The heuristic uses keyword rules and
   needs no model. Repair runs only on a parse failure; an unreachable model
   goes straight to the heuristic.

4. **What does `with_structured_output` do differently per provider?**
   For Ollama it sends the JSON schema as the `format` parameter so decoding
   is constrained. LangChain's base version, which the fake model uses, binds
   the schema as a tool. With `include_raw=True` a failed parse comes back as
   `parsing_error` instead of an exception.

5. **How is a crashed run resumed?**
   The `SqliteSaver` stores state after every step under the thread id. On
   startup the runner finds records in a mid-run status, checks that the
   checkpoint has a next step and no pending interrupt, and calls
   `graph.stream(None, config)`, which continues from the last saved step.

6. **How do interrupts work, and what must a node do to be safe with them?**
   `interrupt(payload)` saves the state and stops the run; the payload is what
   `/status` shows as `review_request`. `Command(resume=value)` makes
   `interrupt()` return that value, but the node runs again from its start, so
   nothing with side effects may come before the `interrupt()` call.

7. **Why is the heuristic confidence below the review threshold?**
   A keyword guess should not trigger actions unseen. With 0.5 against a 0.6
   threshold, every heuristic answer pauses for a person, who can approve or
   correct `input_type` and `business_intent`.

8. **How do you test LLM code without a network?**
   `FakeChatModel` implements `bind_tools`, so LangChain's real
   `with_structured_output` path runs over scripted replies. ChatOllama is
   tested by passing an `httpx.MockTransport` through `client_kwargs`. HTTP
   actions use a mock transport too.

9. **What were the router bugs?**
   The amount rule read `agent_output["data"]` but the JSON agent returns
   `parsed_data` (with the amount under `data`), so high-value alerts never
   fired. Rules read `risk_score` and other fields that no agent produces.
   Every PDF triggered a compliance action even with no keywords, and a GDPR
   PDF triggered two.

10. **How would you know whether a model change made classification better?**
    Run `scripts/eval_classifier.py` before and after on the same labelled
    samples and compare accuracy, the confusion tables (which labels get
    confused), and the answer source counts (how often the model's answer was
    valid without repair).
