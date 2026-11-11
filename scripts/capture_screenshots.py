"""Capture the README screenshots from a running local instance (API on :8000, web on :5173).

Uses Playwright with the locally installed Microsoft Edge (no browser download):
    pip install playwright
    python scripts/capture_screenshots.py --email you@example.com --password ... [--out docs/screenshots]

The account should contain the fictional demo workspace (Settings -> Create demo workspace) and, for the transcript
viewer, one meeting transcribed from a recording. Never capture real private meetings for public screenshots.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

WEB = "http://localhost:5173"
API = "http://127.0.0.1:8000/api/v1"


def api(path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--out", default="docs/screenshots")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    token = api("/auth/login", body={"email": a.email, "password": a.password})["access_token"]
    workspaces = api("/workspaces", token)
    demo = next(w for w in workspaces if w["is_demo"])
    own = next(w for w in workspaces if not w["is_demo"])
    demo_meeting = api(f"/meetings?workspace_id={demo['id']}&sort=date_desc", token)["items"][0]
    own_meeting = next(m for m in api(f"/meetings?workspace_id={own['id']}", token)["items"] if m["has_transcript"])

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        page.goto(WEB + "/login")
        page.evaluate("([t, w]) => { localStorage.setItem('meetpilot.token', t); localStorage.setItem('meetpilot.workspace', w); }",
                      [token, demo["id"]])

        def shot(name: str, path: str, wait: str | None = None, action=None, full: bool = False):
            page.goto(WEB + path)
            page.wait_for_load_state("networkidle")
            if wait:
                page.get_by_text(wait, exact=False).first.wait_for()
            if action:
                action()
            page.wait_for_timeout(700)
            page.screenshot(path=os.path.join(a.out, name), full_page=full)
            print("saved", name)

        shot("dashboard.png", "/", "Recent meetings")
        shot("meetings.png", "/meetings", "release planning")
        shot("meeting-summary.png", f"/meetings/{demo_meeting['id']}?tab=summary", "Executive summary")
        shot("action-items.png", "/action-items?status=all", "Action items")
        shot("decision-tracker.png", "/decisions?review=all", "Decisions")
        shot("speaker-management.png", f"/meetings/{demo_meeting['id']}?tab=transcript", "Speakers",
             action=lambda: page.get_by_role("button", name="Speakers").click())

        def ask():
            page.get_by_role("button", name="What decisions were made?").last.click()  # the suggestion chip
            page.get_by_text("Sources").first.wait_for(timeout=15000)
        shot("ai-assistant.png", "/assistant", "What would you like to know?", action=ask)
        shot("reports.png", f"/meetings/{demo_meeting['id']}?tab=export", "Meeting report")
        shot("analytics.png", "/analytics", "Meetings per week")
        shot("demo-public.png", "/demo", "Executive summary")

        page.evaluate("w => localStorage.setItem('meetpilot.workspace', w)", own["id"])
        shot("upload-recording.png", "/upload", "Meeting details")
        shot("transcript-viewer.png", f"/meetings/{own_meeting['id']}?tab=transcript", "Language")
        browser.close()


if __name__ == "__main__":
    main()
