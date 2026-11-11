"""AI analysis with mocked providers: grounding rules, pipeline, fallbacks and provider adapters."""

import json
from datetime import datetime, timezone

import httpx
import pytest
from conftest import FakeTranscriber, make_wav

from app import ai, transcription
from app.ai import AIClient, strict_schema
from app.ai.analysis import AnalysisOut, SegmentView, ground, run_analysis, windows
from app.ai.base import AIProvider, AIProviderError
from app.ai.providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from app.jobs import Worker


class FakeAI(AIProvider):
    def __init__(self, name="fake-ai", payload=None, text="Combined summary.", fail=None):
        self.name, self.model = name, f"{name}-model"
        self.payload, self.text, self.fail = payload, text, fail
        self.prompts: list[str] = []

    def generate_json(self, system, user, schema, max_tokens):
        self.prompts.append(user)
        if self.fail:
            raise self.fail
        return json.dumps(self.payload)

    def generate_text(self, system, user, max_tokens):
        self.prompts.append(user)
        if self.fail:
            raise self.fail
        return self.text


ANALYSIS = {
    "executive_summary": "The team agreed to ship the beta on Friday.",
    "discussion_points": [{"topic": "Beta", "summary": "Shipping plan", "segment_ids": [1]}],
    "decisions": [
        {"title": "Ship the beta on Friday", "description": "", "status": "confirmed", "participants": ["Speaker 2"],
         "segment_ids": [1, 2]},
        {"title": "Invented decision", "description": "", "status": "confirmed", "participants": [], "segment_ids": [99]},
    ],
    "action_items": [
        {"title": "Write the release notes", "description": "", "owner": "Dana", "deadline_text": "by March 3rd",
         "deadline_date": "2027-03-03", "priority": "high", "priority_basis": "suggested", "needs_confirmation": False,
         "segment_ids": [2]},
        {"title": "Book a venue", "description": "", "owner": "Zed", "deadline_text": "next Tuesday",
         "deadline_date": "2027-01-05", "priority": None, "priority_basis": None, "needs_confirmation": False,
         "segment_ids": [1]},
    ],
    "open_questions": [], "risks": [{"description": "No QA capacity", "segment_ids": []}],
    "follow_ups": [], "key_dates": [{"date_text": "Friday", "date": None, "description": "Beta", "segment_ids": [1]}],
}


def _views():
    return [SegmentView("s1", 1, "Let's agree to ship the beta on Friday.", 0.0, "Speaker 1"),
            SegmentView("s2", 2, "Agreed. Dana will write the release notes by March 3rd.", 2.6, "Speaker 2")]


def test_grounding_rules():
    g = ground(AnalysisOut.model_validate(ANALYSIS), _views(), ["Dana Smith"])
    assert [d.title for d in g.decisions] == ["Ship the beta on Friday"]  # uncited decision dropped
    assert g.decisions[0].participants == ["Speaker 2"] and g.decisions[0].segment_ids == ["s1", "s2"]
    notes = " ".join(g.notes)
    assert "Invented decision" in notes
    a1, a2 = g.action_items
    assert a1.owner == "Dana" and a1.due_text == "by March 3rd" and a1.due_source == "transcript"
    assert a1.priority == "high" and a1.priority_source == "ai_suggested"
    # Owner and deadline that do not appear in the cited line are removed, never kept.
    assert a2.owner is None and a2.due_date is None and a2.due_text is None and a2.needs_confirmation
    assert "Zed" in notes and "next Tuesday" in notes
    assert g.risks == []  # uncited risk dropped
    assert g.key_dates[0]["date_text"] == "Friday"


def test_relative_deadline_marked_interpreted():
    out = AnalysisOut.model_validate({**ANALYSIS, "decisions": [], "action_items": [
        {"title": "Ship", "description": "", "owner": None, "deadline_text": "on Friday", "deadline_date": "2027-01-08",
         "priority": "high", "priority_basis": "stated", "needs_confirmation": False, "segment_ids": [1]}]})
    a = ground(out, _views(), []).action_items[0]
    assert a.due_source == "ai_interpreted" and a.needs_confirmation and a.priority_source == "stated"


def test_strict_schema_shape():
    schema = strict_schema(AnalysisOut)
    assert "$defs" not in json.dumps(schema)
    item = schema["properties"]["action_items"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


def test_windowing_and_merge():
    lines = [f"[{i}] line {'x' * 50}" for i in range(1, 41)]
    parts = windows(lines, 600)
    assert len(parts) > 1 and sum(len(p) for p in parts) == 40
    fake = FakeAI(payload={**ANALYSIS, "risks": []}, text="Merged summary.")
    views = [SegmentView(f"s{i}", i, "x" * 60, None, None) for i in range(1, 41)]
    out, _, _, chunked = run_analysis(AIClient([fake]), "T", datetime(2027, 1, 1, tzinfo=timezone.utc), [], views, 600)
    assert chunked and out.executive_summary == "Merged summary."
    assert len(out.decisions) == 2  # duplicates across parts merged by title
    assert any("part 1 of" in p for p in fake.prompts)


def _transcribed_meeting(account):
    transcription.set_transcription_factory(lambda: FakeTranscriber())
    m = account.meeting("Beta planning", participants=[{"name": "Dana Smith"}])
    account.upload(m["id"], make_wav())
    assert Worker().run_once()
    return m["id"]


def test_analysis_pipeline_end_to_end(alice):
    fake = FakeAI(payload=ANALYSIS)
    ai.set_ai_factory(lambda: AIClient([fake]))
    mid = _transcribed_meeting(alice)  # auto_analyze queues the analysis job
    assert alice.get(f"/api/v1/meetings/{mid}").json()["latest_job"]["kind"] == "analysis"
    assert Worker().run_once()
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["status"] == "completed" and m["action_count"] == 2 and m["decision_count"] == 1
    s = alice.get(f"/api/v1/meetings/{mid}/summary").json()
    assert s["executive_summary"].startswith("The team agreed") and s["provider"] == "fake-ai"
    assert s["grounding_notes"]
    acts = alice.get(f"/api/v1/action-items?workspace_id={alice.workspace_id}&meeting_id={mid}").json()["items"]
    venue = next(a for a in acts if a["title"] == "Book a venue")
    assert venue["owner"] is None and venue["due_date"] is None  # shown as Unassigned / No deadline specified
    assert "[1]" in fake.prompts[0] and "Speaker 1:" in fake.prompts[0] and "Dana Smith" in fake.prompts[0]


def test_user_edits_survive_reanalysis(alice):
    ai.set_ai_factory(lambda: AIClient([FakeAI(payload=ANALYSIS)]))
    mid = _transcribed_meeting(alice)
    Worker().run_once()
    acts = alice.get(f"/api/v1/action-items?workspace_id={alice.workspace_id}").json()["items"]
    alice.patch(f"/api/v1/action-items/{acts[0]['id']}", json={"status": "completed"})
    alice.post("/api/v1/action-items", json={"meeting_id": mid, "title": "Manual task"})
    assert alice.post(f"/api/v1/meetings/{mid}/analyze").status_code == 202
    Worker().run_once()
    titles = sorted(a["title"] for a in alice.get(f"/api/v1/action-items?workspace_id={alice.workspace_id}").json()["items"])
    assert titles.count("Manual task") == 1
    assert titles == ["Book a venue", "Manual task", "Write the release notes"]  # edited item kept, not duplicated


def test_analysis_failure_is_reported_separately(alice):
    ai.set_ai_factory(lambda: AIClient([FakeAI(fail=AIProviderError("Anthropic rejected the API key.", "provider_auth"))]))
    mid = _transcribed_meeting(alice)
    Worker().run_once()
    m = alice.get(f"/api/v1/meetings/{mid}").json()
    assert m["status"] == "failed" and m["error_stage"] == "analysis"
    assert alice.get(f"/api/v1/meetings/{mid}/transcript").status_code == 200  # transcript intact


def test_analyze_without_ai_is_503(alice):
    mid = _transcribed_meeting(alice)
    r = alice.post(f"/api/v1/meetings/{mid}/analyze")
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_not_configured"


def test_fallback_provider_used():
    primary = FakeAI("primary", fail=AIProviderError("down", "provider_unavailable", retryable=True))
    backup = FakeAI("backup", payload=ANALYSIS)
    out, provider, model = AIClient([primary, backup]).structured("s", "u", AnalysisOut)
    assert provider == "backup" and out.executive_summary


def test_invalid_structured_output_rejected():
    bad = FakeAI(payload={"wrong": True})
    with pytest.raises(AIProviderError) as e:
        AIClient([bad]).structured("s", "u", AnalysisOut)
    assert e.value.code == "invalid_output"


def test_registry_reads_settings(monkeypatch):
    from conftest import set_env
    set_env(monkeypatch, ai_provider="anthropic", anthropic_api_key="k1", ai_fallback_providers="gemini,openai",
            gemini_api_key="k2")
    client = ai.get_ai_client()
    assert [p.name for p in client.providers] == ["anthropic", "gemini"]  # openai skipped: no key
    assert client.primary.model == "claude-opus-5-5"


# --- Provider adapters against mocked transports ------------------------------------------------

def test_openai_adapter_structured_request():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 1, "model": "m",
                                         "choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": '{"a": 1}'}}]})
    import openai
    client = openai.OpenAI(api_key="k", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)
    out = OpenAIProvider("k", "gpt-test", client=client).generate_json("sys", "user", {"type": "object"}, 100)
    assert out == '{"a": 1}'
    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True


def test_anthropic_adapter_request_and_refusal():
    calls = []

    import httpx2  # the Anthropic SDK 2.x uses httpx2, not httpx

    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, request.headers.get("anthropic-beta"), body))
        stop = "refusal" if "refuse" in body["messages"][0]["content"] else "end_turn"
        return httpx2.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                                         "content": [{"type": "text", "text": '{"ok": true}'}], "stop_reason": stop,
                                         "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
    import anthropic
    client = anthropic.Anthropic(api_key="k", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
                                 max_retries=0)
    prov = AnthropicProvider("k", client=client)
    assert prov.generate_json("sys", "hello", {"type": "object"}, 100) == '{"ok": true}'
    path, beta, body = calls[0]
    assert path == "/v1/messages" and "server-side-fallback" in (beta or "")
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"]["format"]["type"] == "json_schema" and body["system"] == "sys"
    with pytest.raises(AIProviderError) as e:
        prov.generate_text("sys", "please refuse", 100)
    assert e.value.code == "provider_refusal"


def test_anthropic_adapter_auth_error():
    import anthropic
    import httpx2
    client = anthropic.Anthropic(api_key="k", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(
        lambda r: httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "x"}}))))
    with pytest.raises(AIProviderError) as e:
        AnthropicProvider("k", "claude-haiku-5-5", client=client).generate_text("s", "u", 10)
    assert e.value.code == "provider_auth" and not e.value.retryable


def test_gemini_adapter_uses_json_schema():
    class Models:
        def generate_content(self, model, contents, config):
            self.args = (model, contents, config)

            class R:
                text = '{"x": 1}'
                candidates = [type("C", (), {"finish_reason": "STOP"})()]
            return R()

    class Client:
        models = Models()

    c = Client()
    out = GeminiProvider("k", client=c).generate_json("sys", "u", {"type": "object"}, 50)
    model, contents, config = c.models.args
    assert out == '{"x": 1}' and model == "gemini-2.5-flash"
    assert config.response_mime_type == "application/json" and config.response_json_schema == {"type": "object"}
    assert config.system_instruction == "sys"
