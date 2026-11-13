import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionList } from "./components/records";
import LandingPage from "./pages/Landing";
import { Highlight } from "./components/ui";
import { api, ApiError, qs } from "./lib/api";
import { dueLabel, formatDuration, formatTimestamp, ownerLabel } from "./lib/format";
import type { ActionItem } from "./lib/types";

function wrap(children: ReactNode) {
  return <QueryClientProvider client={new QueryClient()}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}

const base: ActionItem = {
  id: "a1", meeting_id: "m1", meeting_title: "Planning", meeting_date: "2026-11-01T10:00:00Z", project_id: null,
  title: "Write release notes", description: "", owner: null, owner_source: null, due_date: null, due_text: null,
  due_source: null, priority: null, priority_source: null, needs_confirmation: false, status: "todo", notes: "",
  source_segment_ids: [], excerpt: null, origin: "ai", user_modified: false, overdue: false, completed_at: null,
  created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-01T10:00:00Z",
};

describe("formatting", () => {
  it("formats timestamps and durations", () => {
    expect(formatTimestamp(0)).toBe("00:00");
    expect(formatTimestamp(3725)).toBe("1:02:05");
    expect(formatTimestamp(null)).toBe("");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(5400)).toBe("1 h 30 min");
  });
  it("never invents owners or deadlines", () => {
    expect(ownerLabel(base)).toBe("Unassigned");
    expect(dueLabel(base)).toBe("No deadline specified");
  });
  it("builds query strings without empty values", () => {
    expect(qs({ a: "1", b: "", c: null, d: undefined, e: false })).toBe("?a=1&e=false");
  });
});

describe("Highlight", () => {
  it("marks every search term case-insensitively", () => {
    const { container } = render(<Highlight text="Ship the Beta on Friday" query={["beta", "friday"]} />);
    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Beta", "Friday"]);
  });
  it("escapes regex characters", () => {
    const { container } = render(<Highlight text="cost (approx.) 5$" query="(approx.)" />);
    expect(container.querySelector("mark")?.textContent).toBe("(approx.)");
  });
});

describe("ActionList", () => {
  it("labels unassigned items and AI-suggested priorities", () => {
    const items = [base, { ...base, id: "a2", title: "Load test", owner: "Daniel", due_date: "2026-12-01", due_source: "ai_interpreted" as const,
      due_text: "before the freeze", priority: "high" as const, priority_source: "ai_suggested" as const }];
    render(wrap(<ActionList items={items} invalidate={[]} readOnly />));
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
    expect(screen.getByText("No deadline specified")).toBeInTheDocument();
    expect(screen.getByText(/High \(AI suggestion\)/)).toBeInTheDocument();
    expect(screen.getByText(/interpreted from “before the freeze”/)).toBeInTheDocument();
  });
});

describe("api client", () => {
  afterEach(() => vi.restoreAllMocks());
  it("turns error bodies into ApiError with field details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "validation_error",
      message: "Some fields are invalid.", details: [{ field: "email", message: "value is not a valid email address" }] } }), { status: 422 }));
    const err = (await api("/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toContain("email: value is not a valid email address");
  });
  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const err = (await api("/x").catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe("network_error");
  });
});

describe("LandingPage", () => {
  afterEach(() => vi.restoreAllMocks());
  const config = (persistent: boolean) =>
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ database_persistent: persistent, password_reset_email: false }), { status: 200 }));

  it("links its calls to action to real routes", async () => {
    config(true);
    render(wrap(<LandingPage />));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/meaningful progress/i);
    expect(screen.getAllByRole("link", { name: /create a free account/i })[0]).toHaveAttribute("href", "/register");
    expect(screen.getAllByRole("link", { name: /explore the demo/i })[0]).toHaveAttribute("href", "/demo");
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: /privacy/i })).toHaveAttribute("href", "/privacy");
    expect(screen.queryByText(/temporary storage/i)).not.toBeInTheDocument();
  });

  it("warns visitors when the server keeps data only temporarily", async () => {
    config(false);
    render(wrap(<LandingPage />));
    expect(await screen.findByText(/temporary storage/i)).toBeInTheDocument();
  });

  it("makes no testimonial, customer-count or pricing-plan claims", () => {
    config(true);
    const { container } = render(wrap(<LandingPage />));
    expect(container.textContent).not.toMatch(/testimonial|trusted by|\d[\d,]*\+? (teams|customers|users)|per month|\/mo\b/i);
  });
});
