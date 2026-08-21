# TriageDesk

A CrewAI support-ticket triage system for **CloudNote**, a fictional SaaS note-taking
product. It takes one raw customer ticket and produces a single **validated** decision —
category, best knowledge-base article, drafted reply, and whether the ticket can be
auto-answered — and **fails safe** (force-escalate, confidence `0.0`) whenever its own
output cannot be trusted.

Built as the CrewAI counterpart to a LangGraph project, so the two frameworks can be
compared on the same problem. See [`notes/framework_comparison.md`](notes/framework_comparison.md).

---

## Design decisions

**1. The schema is the contract, and it is hostile to the model.**
`TriageResult` is the only type that crosses the system boundary. It sets
`extra="forbid"`, so an unexpected key from the LLM is a validation error rather than a
silently absorbed field, and `frozen=True` so a validated decision cannot be mutated
downstream. Model output is treated as untrusted input throughout.

**2. Fail-safe is a code path, not a prompt instruction.**
Asking a model nicely to always return valid JSON is not a guarantee. `triage()` parses
defensively, re-asks at most twice, and then returns `TriageResult.failsafe(...)`. An
untrusted answer never reaches a customer because the *pipeline* refuses, not because
the *prompt* asked.

**3. A cited article is checked against the KB.**
Models invent plausible ids. `validate_payload()` rejects any `kb_article_id` that is not
a real article, and caps confidence at `0.49` when it does — below the auto-answer
threshold, so a fabricated citation can never be shipped automatically.

**4. Routing policy lives in `gate.py`, not in the prompt.**
Three bands on confidence: `>= 0.80` auto-answer, `0.50–0.79` human approval at the CLI,
`< 0.50` escalate. The gate may only ever be *more* cautious than the decision it
receives — an explicit `route="escalate"` from the model is never downgraded, whatever
the confidence.

**5. Tier-1 retrieval is lexical on purpose.**
Keyword overlap costs nothing, is fully deterministic, and therefore makes eval numbers
reproducible run to run. Embeddings are a Tier-2 swap behind the same `search_kb`
interface. Titles are weighted 2× and scores normalised by query length so long articles
cannot win on verbosity alone.

**6. The runtime never sees the labels.**
`ticket_text()` returns only `text`. `expected_category`, `expected_article`,
`expected_route` and `escalation_trigger` exist solely for the eval, so the harness
measures performance rather than leakage.

---

## Data assets

| Asset | Contents |
|---|---|
| `kb/articles.json` | **32 articles**, 8 per category (billing / troubleshooting / account / features), internally consistent on prices, limits and retention windows |
| `eval/tickets.json` | **25 hand-labeled tickets** — 7 billing, 7 troubleshooting, 5 account, 6 features — including **6 must-escalate** cases |

The six escalation triggers, one each, so recall can be sliced per trigger and a miss
tells you *which* trigger the system is blind to:

`refund_demand` · `legal_threat` · `data_loss` · `security_incident` · `gdpr_deletion` · `abusive_tone`

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime (includes crewai)
pip install -r requirements-dev.txt      # just enough to run the tests
cp .env.example .env                     # then add GOOGLE_API_KEY
```

Credentials are read from the environment only. Nothing secret is committed.

> `crewai` lags the newest CPython. The test suite runs on 3.14; if the `crewai`
> install fails there, create the runtime environment on Python 3.11 or 3.12.

## Run

```bash
python -m triage.run --ticket t01              # stored ticket, JSON to stdout
python -m triage.run --ticket t09 --gate       # apply the confidence gate
python -m triage.run --text "I was billed twice"   # ad-hoc text
```

## Test

48 tests, no API calls, no cost:

```bash
PYTHONPATH=. pytest tests -q
```

## Evaluate

Scoring a saved predictions file is free. `--live` spends model quota.

```bash
# free: score predictions you already have
python -m eval.run_eval --predictions predictions.json

# spends quota: run all 25 tickets, save the outputs for later re-scoring
python -m eval.run_eval --live --save predictions.json
```

Reported metrics: **escalation recall** (the signature metric — target 1.00 on all six
must-escalate tickets), escalation precision, routing accuracy, category accuracy,
article hit rate, and per-trigger recall. The process exits non-zero if escalation
recall is below 1.00, so it can gate CI.

Escalation precision is reported alongside recall for a reason: escalating *everything*
scores perfect recall, and precision is the metric that catches that degenerate policy.

---

## Layout

```
kb/articles.json          32 KB articles (build-time asset)
eval/tickets.json         25 labeled tickets (build-time asset)
eval/run_eval.py          scorer + live runner
triage/schema.py          TriageResult — the contract
triage/data.py            read-only JSON loaders, path-containment checked
triage/tools/kb_search.py keyword top-3 retrieval, wrapped as a CrewAI tool
triage/crew.py            classifier agent + fail-safe triage() orchestrator
triage/gate.py            confidence gate + human approval
triage/run.py             CLI
notes/                    framework comparison log
tests/                    48 API-free tests
```

`crew.py` depends on `schema.py`, never the reverse — the schema is the stable contract
the CLI, the gate and the eval all plug into.

## Status

Implemented: the W5/W6 scope (data assets, contract, agent + tool, CLI, fail-safe) plus
the Tier-2 confidence gate and eval harness.

Not yet built: hierarchical delegation with a manager agent, crew memory, embedding
retrieval, real ingestion (Jira / `.eml`), and the Tier-3 CrewAI Flow with KB write-back.
