# CrewAI vs LangGraph — running friction log

Same problem shape in both frameworks: an LLM step that must produce a validated,
routable decision and fail safe when it cannot. Notes accumulate as the build proceeds.

## 1. Where the topology lives

**LangGraph** makes the graph the program. Nodes, edges and the conditional router are
Python, so the step cap and the fallback edge *are* the safety policy — reviewable as
code, testable without a model.

**CrewAI** starts from roles. `Agent` + `Task` + `Crew(process=...)` describes who does
what, and the orchestration is chosen from `Process.sequential` / `Process.hierarchical`
rather than drawn explicitly. Convenient at Tier 1, but the control flow is less
inspectable: with `hierarchical`, a manager LLM decides delegation at runtime, so the
execution path is not fully knowable ahead of time.

*Consequence for this build:* the confidence gate was deliberately kept **outside** the
crew, in `gate.py`. Routing that must be auditable does not belong to an agent.

## 2. Structured output

CrewAI offers `output_pydantic` on a `Task`, which is convenient but still ends in a
parse of model text. This build does not rely on it alone: `_extract_json_object()` plus
explicit `model_validate()` plus a retry ladder is used instead, so the failure mode is
observable and testable. Same conclusion as LangGraph — validate at the boundary
yourself, regardless of framework affordances.

## 3. Tool definition

Both wrap a plain function. CrewAI's `@tool` decorator uses the **docstring as the
routing prompt**, which is pleasant but means prose quality silently affects behaviour.
`search_kb()` is therefore kept as an ordinary function with `build_tool()` wrapping it
only when CrewAI is present — so retrieval is unit-testable with no framework and no key.

## 4. Import cost and testability

Importing CrewAI drags in the LLM client stack. Keeping the `crewai` import inside
`_build_crew()` means `schema`, `data`, `kb_search`, `gate` and the whole eval harness
import cleanly without it — which is why 48 tests run in ~0.1s with no API key.
Worth doing on both frameworks; more necessary here.

## 5. Open questions for Tier 2

- Does `Process.hierarchical` delegation show up usefully in a trace, or is manager
  reasoning opaque in practice?
- Is crew memory (short-term / entity) genuinely easier than threading state through a
  LangGraph `State` dict, or just less explicit?
- Retry semantics: does CrewAI's own task retry compose with the outer ladder in
  `triage()`, or double up on model calls?
