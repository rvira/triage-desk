# Working Instructions for Claude (cardwise-ai)

## Communication style
- **Keep answers crisp** — short, direct, no filler; lead with the answer.

## Always conclude an action (do this every time)
After any action taken, command run, or note produced, end with a **1–3 line
conclusion** stating the result and the implication — so a decision can be drawn
fast without re-reading the detail.
Format: `**Conclusion:** <what happened> → <what it means / next step>`.

---

## Mode: Discuss-only
- **Claude explains; the user implements.** Do NOT edit, create, or modify any
  code files. No Edit/Write/patch on the codebase except for the test cases.
- For each task, Claude describes exactly what to change: the file, the location
  (function / line range), the reasoning, and a code snippet to adapt — but the
  user types the change themselves.
- Claude may still read files, search, and run read-only commands to ground the
  discussion.
- The only files Claude may write are instruction/planning docs like this one
  (when explicitly asked).

## Current focus: Week 4 AI-2 (Hybrid Search + Evaluation)
Complete the six AI-2 deliverables in order, one at a time:
- **2.1** ✅ DONE — `chunk_id`/`card_id` metadata added; re-ingested clean store
- **2.2** ✅ DONE (except k-sweep) — RRF added alongside weighted `retrieve`
  (`reciprocal_rank_fusion` + `retrieve_rrf`, shared `_candidates`); `fusion=`
  selector on `stratified_retrieve`/`as_runnable`; 5 RRF tests pass. The
  RRF-k sweep (10/60/100, pick best by recall) stays OPEN until 2.4 + 2.5 exist.
- **2.3** ✅ DONE — README design decisions: (a) RRF vs weighted-sum, (b) Chroma memo
- **2.4** ✅ DONE — 20-query gold set at `src/evaluation/gold_set.json` (7/7/6)
- **2.5** ✅ DONE — `run_baseline_eval` reused for gold set; `numeric_hit` guard added.
  Config locked: **flat hybrid RRF, k=10** → context_recall 0.883 (≥0.85 ✓),
  numeric_exact 1.000. (Stratification tried and REJECTED — starved single-card
  queries; k-bump 6→10 was the lever that worked.)
- **2.6** ✅ DONE — Dense-vs-Hybrid before/after table in README (k=10).
  Dense 0.630/0.829/1.000 vs Hybrid 0.619/0.883/1.000. Honest finding: numeric-exact
  saturates at 1.0 for both at k=10 (small corpus, wide net); hybrid's measured win is
  recall + answer relevancy at equal precision.

## Closing task ✅ DONE
- Shipped app now matches the benchmarked config: `as_runnable` default `k=6`→`10`,
  and `app.py` `retrieve_docs` switched from weighted `retrieve` to `retrieve_rrf(k=10)`
  (also fixes app using weighted-sum while README claimed RRF is default).

## ALL SIX AI-2 DELIVERABLES COMPLETE (2.1–2.6). ✅

## Evaluation runs
- **Never run the eval command yourself** (`python -m src.evaluation.eval ...`).
  It spends Gemini API quota. Prepare the code and hand the user the exact command
  to run; the user runs it and pastes back the results.

## Git commits
- Do **not** add any Claude / AI attribution to commit messages. No
  `Co-Authored-By: Claude ...` trailer and no "Generated with Claude Code" line.
- Write commit messages as if authored solely by the repository owner.

## Project conventions to honor
- Keep the existing embedding model `gemini-embedding-001` (do NOT re-index to
  `text-embedding-004`). Retrieval quality is the bottleneck, not the model.
- Keep the existing ragas 0.4.x collections API in `src/evaluation/eval.py`
  (don't downgrade to the classic `evaluate()` + `Dataset` flow).
- Decision pending per task: add-alongside vs replace existing behavior — confirm
  with the user before assuming.

---

## Next focus: Week 5 AI-3 (Agentic CardWise, LangGraph) ✅ 3.1–3.5 IMPLEMENTED
Design rule honored: **the graph topology encodes the safety policy (step cap +
fallback), not the prompt.** Dependency added: `langgraph==1.2.9` (the `1.0.x` line
pulls an incompatible `langgraph-prebuilt`).

- **3.1** ✅ Graph skeleton — `src/agent/graph.py`: `agent ⇄ tools` ReAct loop,
  `route` conditional edge, `rag_fallback` node, `MAX_STEPS=6`, compiled `app`.
- **3.2** ✅ Tool #1 `card_search` — `src/agent/tools/retriever_tool.py`: lazy-cached
  wrapper over the hybrid retriever at k=10; docstring is the routing prompt.
- **3.3** ✅ Tool #2 `rewards_value` — `src/agent/tools/rewards_calc.py`: pure,
  deterministic math over the 3 real cards; untrusted JSON validated + fail-closed.
- **3.4** ✅ Routing + step cap — `route()` caps before dispatch; verified
  factual→retriever, cap→fallback (tests, no API).
- **3.5** ✅ Error recovery — `ToolNode(..., handle_tool_errors=True)`; forced tool
  failure → ToolMessage → recover; runaway loop → cap → `rag_fallback`.

- **Answer-quality pass** ✅ Fixed a real-world failure where "which card for my
  spend?" was answered via `card_search` + LLM prose-math (ignoring the annual fee,
  dropping SBI). System prompt now forbids in-reply arithmetic and mandates
  `rewards_value` for any value/comparison question, ranks all 3 by net-after-fee,
  states assumptions, and maps merchants→categories (Swiggy→dining). Tool docstrings
  sharpened for routing. Data fix: added Axis ACE `monthly_cap: 500` so the
  calculator agrees with the source docs (with a test). Routing/prompt behaviour is
  best-effort — confirm with one live run.
- **Honest-advice caveats** ✅ `rewards_value` now returns a deterministic `summary`
  (`all_net_negative`, `no_rewards_difference`, tied `best_cards`, human-readable
  `notes`) so the agent can't mis-sell a technically-correct-but-misleading ranking
  (e.g. calling a net-negative card "best suited", or hiding that all cards share the
  same rate so it's only a fee comparison). System prompt mandates surfacing these;
  covered by tests.
- **Frontend** ✅ `app.py`: added an **Agent** retrieval mode that runs the agent
  live and shows the tool-call trace in a collapsible `st.expander` (Claude-style
  disclosure). Untrusted tool/model output rendered via `st.code`/plain `st.markdown`
  (no `unsafe_allow_html`) so it can't inject HTML. `src/scripts/agent_trace.py`
  prints the same trace as README-ready markdown.

> **Conclusion:** AI-3.1–3.5 implemented + wired into the Streamlit UI; **26/26
> API-free tests pass**, ruff clean. Remaining (needs API key, user-run): install
> deps in the project env + re-run pytest, and paste a live trace + the
> `draw_mermaid()` diagram into README.

### README trace command (run with a real GOOGLE_API_KEY — spends quota)
```
python -c "from src.agent.graph import ask; [print(type(m).__name__, (getattr(m,'tool_calls',None) or m.content)) for m in ask('I spend 8000/mo on dining and 5000 online — which card nets me more?')['messages']]"
```
