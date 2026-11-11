# AI analysis guide

## Provider architecture

`backend/app/ai/` defines one interface, `AIProvider`, with `generate_json(system, user, schema)` and `generate_text(system, user)`. Each adapter uses its vendor's official SDK:

| Provider | Default model | Structured output | Notes |
|---|---|---|---|
| `openai` | `gpt-5-mini` | Chat Completions `response_format: json_schema` (strict) | Refusals and length cut-offs are detected |
| `anthropic` | `claude-opus-5-5` | Messages API `output_config.format: json_schema` | Uses server-side refusal fallback (`fallbacks: "default"`) on models that support it, and checks `stop_reason` for `refusal` and `max_tokens` |
| `gemini` | `gemini-2.5-flash` | `response_mime_type: application/json` + `response_json_schema` | `MAX_TOKENS` and safety finish reasons are detected |

`AI_MODEL` overrides the primary model. `AIClient` tries the primary provider and then each provider in `AI_FALLBACK_PROVIDERS` that has a key, so an outage or quota error on one provider can be absorbed by another. Every response is parsed and validated with Pydantic, whatever the provider promises. Invalid output is treated as a retryable failure.

## What is sent

- **Analysis:** the meeting title, date and weekday (to interpret phrases like "by Friday"), participant names the user entered, and the transcript as numbered lines: `[12] (00:03:14) Speaker 2: text`.
- **Assistant:** the question, the asking user's name, up to six earlier messages, and the retrieved sources.

Nothing else from the workspace is sent.

## Summarisation

The model returns one JSON object: `executive_summary`, `discussion_points`, `decisions`, `action_items`, `open_questions`, `risks`, `follow_ups` and `key_dates`. Every item carries the `segment_ids` (line numbers) that support it. The system prompt requires using only the transcript, never guessing owners or deadlines, copying deadline phrases verbatim, separating confirmed decisions from proposals, and treating "Speaker N" labels as anonymous.

**Long transcripts:** if the numbered transcript is longer than `AI_MAX_INPUT_CHARS` (default 120,000 characters), it is analysed in consecutive windows. Lists are merged (decisions and actions de-duplicated by title), then a final text call combines the partial executive summaries using only those summaries. The summary is marked `chunked`.

## Grounding checks (`ai/analysis.py::ground`)

After the model responds, code checks every item against the transcript:

| Check | Result |
|---|---|
| Cited line numbers that do not exist | Ignored |
| Decision or action item with no valid citation | Dropped, with a note |
| Risk, question or follow-up with no valid citation | Dropped, with a note |
| Action owner not in the cited lines, and not the speaker of a cited line | Owner removed (shown as **Unassigned**), item marked "needs confirmation", note added |
| Deadline phrase not found in the cited lines | Deadline removed (**No deadline specified**), note added |
| Deadline date without a supporting phrase | Removed |
| Deadline phrase is relative ("next Friday") but the model resolved a date | Kept as `ai_interpreted`, marked "needs confirmation", shown as "interpreted from ..." |
| Decision participants not in the cited lines | Removed, with a note |
| Key date phrase not found in the cited lines | Dropped |
| Priority | `stated` only when the model says it was said; otherwise `ai_suggested`, labelled "AI suggestion" in the UI |

Notes appear under **Grounding checks** on the summary. Each decision and action keeps its source segment IDs and an excerpt, which link to the transcript.

## Decision extraction

`meeting_status` records what happened in the meeting: `confirmed` (agreement in the transcript), `proposed` (suggested, not agreed) or `uncertain`. The separate `review_status` (`unreviewed`, `confirmed`, `rejected`) records the user's own review. Proposals are never shown as confirmed decisions.

## Action item extraction

Each item has a title, description, owner (only if stated), deadline (only if stated, with the original words in `due_text`), priority with its source, status (`todo`, `in_progress`, `completed`, `cancelled`), notes, source segments and an excerpt. Items without a clear owner show **Unassigned**; items without a deadline show **No deadline specified**.

**Re-analysis** replaces untouched AI items. Items the user created, edited or reviewed are kept, and new AI items with the same title as a kept item are not added again.

## Grounded assistant answers

1. **Retrieve:** keyword search over transcript segments in the current workspace (optionally limited to one meeting or project), the summaries of the meetings found, the most recent meetings for time-based questions ("yesterday", "last"), and action items and decisions when the question is about tasks, deadlines, decisions or open issues. Questions with "me" or "my" filter action items by the user's first name.
2. **No sources:** the answer says nothing was found, and the AI is not called.
3. **No AI provider:** the matching records are listed with their labels (`retrieval_only`).
4. **Answer:** the model receives only numbered sources (`[S1]` segments, `[M1]` meeting summaries, `[A1]` action items, `[D1]` decisions) and must cite them. Earlier conversation is provided as context, not as a source. Cited labels are matched back to records; unknown labels are ignored. Answers with no citations are flagged in the UI.

Access control happens before retrieval: only workspaces the user belongs to are searched, and conversations are private to the user who started them.

## Error handling

| Situation | Behaviour |
|---|---|
| No AI provider configured | Analysis button hidden. `POST /analyze` returns `503 ai_not_configured`. The assistant lists matches |
| Invalid key or permission (401/403) | Fails without retry. Meeting `failed`, `error_stage = analysis`, transcript untouched |
| Rate limit, timeout, network error, 5xx, invalid JSON, cut-off output | Next fallback provider, then retried with back-off up to `JOB_MAX_ATTEMPTS` |
| Model refusal | Reported as a refusal. The Anthropic server-side fallback may answer first |
| Assistant provider failure | `502` with a safe message. The question is not saved |

Provider error bodies are never shown to users or written to logs.

## Verification status

All three adapters are tested against mocked SDK transports (request shape, structured output parameters, refusal and auth handling). The analysis pipeline, grounding rules, windowing, fallbacks and the assistant are tested with fake providers. **None of the three providers has been called with a real key in this project.** Run a real analysis before relying on a provider in production.
