import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, AudioLines, BarChart3, BookOpen, Bot, CheckCircle2, FileDown, FileText, Gavel, Code2,
  ListChecks, Lock, Mail, Search, ShieldCheck, Upload, Wand2,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { get } from "../lib/api";

const REPO = "https://github.com/OlehDatsyk/meetpilot-ai-meeting-intelligence";

const FEATURES: { icon: typeof Upload; title: string; text: string }[] = [
  { icon: AudioLines, title: "Timestamped transcripts",
    text: "Upload MP3, WAV, M4A, AAC, OGG or FLAC. Transcribe with OpenAI speech-to-text (with speaker diarisation) or a local Whisper model." },
  { icon: Wand2, title: "Grounded AI analysis",
    text: "Executive summary, discussion points, decisions, action items, open questions and risks, each linked to the transcript lines behind it." },
  { icon: ListChecks, title: "Action item tracking",
    text: "Assign owners, deadlines and priorities, mark tasks complete, and filter by status, owner, project or overdue." },
  { icon: Gavel, title: "Decision log",
    text: "Confirmed, proposed and uncertain decisions are kept apart, and you can confirm or reject each one." },
  { icon: Bot, title: "Meeting assistant",
    text: "Ask about your meetings. Answers come only from your own records, with citations you can click through to the transcript." },
  { icon: Search, title: "Search everything",
    text: "Keyword search across titles, transcripts, speakers, decisions, action items and projects." },
  { icon: FileDown, title: "Reports and exports",
    text: "PDF and HTML meeting reports, plus TXT, SRT, VTT, Markdown, CSV and calendar (.ics) exports." },
  { icon: BarChart3, title: "Analytics from real records",
    text: "Meetings and minutes per week, action item completion and activity by project, computed from what you have stored." },
];

const STEPS: { icon: typeof Upload; title: string; text: string }[] = [
  { icon: Upload, title: "Upload", text: "Add a recording and the meeting details: title, date, project and participants." },
  { icon: AudioLines, title: "Transcribe", text: "A background job transcribes the audio and shows its real progress." },
  { icon: Wand2, title: "Analyse", text: "Your configured AI provider extracts the summary, decisions and action items." },
  { icon: CheckCircle2, title: "Follow through", text: "Review, assign and complete tasks, search past meetings and export reports." },
];

const USE_CASES: { title: string; text: string }[] = [
  { title: "Project and product teams", text: "Keep track of who agreed to what across weekly planning and release meetings." },
  { title: "Client and stakeholder calls", text: "Share a clear report of decisions and next steps after each call." },
  { title: "Team leads", text: "See outstanding and overdue tasks across every meeting in one list." },
  { title: "Research interviews", text: "Search across transcripts and jump straight to the moment a topic came up." },
];

function Section({ id, eyebrow, title, intro, children, className = "" }:
  { id?: string; eyebrow: string; title: string; intro?: string; children: ReactNode; className?: string }) {
  return (
    <section id={id} className={`scroll-mt-20 px-4 py-20 sm:px-6 ${className}`} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="mx-auto max-w-6xl">
        <p className="text-sm font-semibold uppercase tracking-wider text-accent">{eyebrow}</p>
        <h2 id={id ? `${id}-title` : undefined} className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h2>
        {intro && <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted">{intro}</p>}
        <div className="mt-12">{children}</div>
      </div>
    </section>
  );
}

function Preview({ src, alt, caption, eager = false }: { src: string; alt: string; caption?: string; eager?: boolean }) {
  return (
    <figure>
      <div className="overflow-hidden rounded-xl border border-white/10 bg-navy-900 shadow-2xl shadow-indigo-950/40 ring-1 ring-black/5">
        <div className="flex items-center gap-1.5 border-b border-white/10 px-3 py-2" aria-hidden>
          <span className="size-2.5 rounded-full bg-slate-600" /><span className="size-2.5 rounded-full bg-slate-600" /><span className="size-2.5 rounded-full bg-slate-600" />
        </div>
        <img src={src} alt={alt} width={1440} height={900} loading={eager ? "eager" : "lazy"} decoding="async" className="block h-auto w-full" />
      </div>
      {caption && <figcaption className="mt-3 text-center text-xs text-muted">{caption}</figcaption>}
    </figure>
  );
}

export default function LandingPage() {
  const config = useQuery({
    queryKey: ["public-config"],
    queryFn: () => get<{ database_persistent: boolean; password_reset_email: boolean }>("/api/v1/system/config"),
    retry: false,
  });
  const temporary = config.data && !config.data.database_persistent;

  return (
    <div className="min-h-full bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-3 focus:py-2 focus:text-sm">
        Skip to content
      </a>

      <header className="sticky top-0 z-40 border-b border-white/10 bg-navy-950/90 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6" aria-label="Main">
          <Link to="/" aria-label="MeetPilot AI home"><Logo dark compact /></Link>
          <div className="hidden items-center gap-7 text-sm text-slate-300 md:flex">
            <a href="#features" className="hover:text-white">Features</a>
            <a href="#how-it-works" className="hover:text-white">How it works</a>
            <a href="#use-cases" className="hover:text-white">Use cases</a>
            <a href="#open-source" className="hover:text-white">Open source</a>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/login" className="whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white">Sign in</Link>
            <Link to="/register" className="whitespace-nowrap rounded-lg bg-accent px-3.5 py-2 text-sm font-medium text-white shadow-sm hover:bg-accent-strong">Get started</Link>
          </div>
        </nav>
      </header>

      <main id="main">
        {/* Hero */}
        <section className="relative overflow-hidden bg-navy-950 px-4 pb-20 pt-16 text-slate-300 sm:px-6 sm:pt-24">
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_50%_-10%,rgba(79,70,229,0.35),transparent)]" />
          <div className="relative mx-auto max-w-6xl">
            <div className="mx-auto max-w-3xl text-center">
              <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-indigo-200">
                <ShieldCheck className="size-3.5" aria-hidden /> Owners and deadlines only when the meeting actually states them
              </p>
              <h1 className="mt-6 text-4xl font-semibold leading-tight tracking-tight text-white sm:text-6xl">
                Turn every meeting into meaningful progress.
              </h1>
              <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-300">
                MeetPilot AI turns meeting recordings into timestamped transcripts, summaries, decisions and action items,
                each linked back to the moment it was said. Then it helps you follow through.
              </p>
              <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Link to="/register" className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-900/40 hover:bg-accent-strong sm:w-auto">
                  Create a free account <ArrowRight className="size-4" aria-hidden />
                </Link>
                <Link to="/demo" className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10 sm:w-auto">
                  Explore the demo meeting
                </Link>
              </div>
              <p className="mt-4 text-xs text-slate-400">The demo meeting is fictional and needs no account.</p>
              {temporary && (
                <p className="mx-auto mt-4 max-w-xl rounded-lg border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-xs text-amber-100">
                  This server is a public demonstration with temporary storage. Accounts and data are deleted whenever it restarts or sleeps.
                </p>
              )}
            </div>
            <div className="mx-auto mt-14 max-w-5xl">
              <Preview src="/previews/dashboard.webp" eager
                alt="MeetPilot AI dashboard showing meeting, recorded time, open action item and decision counts, recent meetings and upcoming deadlines"
                caption="The real dashboard, shown with the fictional demo workspace." />
            </div>
          </div>
        </section>

        <Section id="features" eyebrow="Features" title="Everything after the meeting, in one place"
          intro="From the raw recording to a tracked list of commitments. Every feature below is part of the application today.">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="card p-5 transition-shadow hover:shadow-md">
                <span className="inline-flex size-10 items-center justify-center rounded-lg bg-accent-soft text-accent"><Icon className="size-5" aria-hidden /></span>
                <h3 className="mt-4 font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="how-it-works" eyebrow="How it works" title="Four steps from recording to results" className="bg-white">
          <ol className="grid gap-6 md:grid-cols-4">
            {STEPS.map(({ icon: Icon, title, text }, i) => (
              <li key={title} className="relative">
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-10 items-center justify-center rounded-full bg-navy-950 text-sm font-semibold text-white">{i + 1}</span>
                  <Icon className="size-5 text-accent" aria-hidden />
                </div>
                <h3 className="mt-4 font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ol>
        </Section>

        <Section eyebrow="Grounded by design" title="No invented owners, deadlines or decisions"
          intro="AI note-takers often fill gaps with confident guesses. MeetPilot AI checks every extracted item against the transcript lines it cites.">
          <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.4fr]">
            <ul className="space-y-5 text-sm leading-relaxed text-muted">
              {[
                ["Every point has a source", "Summary points, decisions and action items link to the transcript lines that support them."],
                ["Unknown stays unknown", "If nobody was named, the task shows Unassigned. If no date was given, it shows No deadline specified."],
                ["Corrections are visible", "A Grounding checks card lists anything that was removed or corrected, and why."],
                ["You stay in control", "Edit the transcript, rename speakers, and confirm or reject each decision."],
              ].map(([title, text]) => (
                <li key={title} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden />
                  <span><strong className="font-semibold text-ink">{title}.</strong> {text}</span>
                </li>
              ))}
            </ul>
            <Preview src="/previews/meeting-summary.webp"
              alt="Meeting summary page with executive summary, discussion points and key dates, each with a source link"
              caption="Meeting summary with source links (fictional demo meeting)." />
          </div>
        </Section>

        <Section eyebrow="Inside the app" title="Built for reviewing and following through" className="bg-white">
          <div className="grid gap-8 lg:grid-cols-2">
            <Preview src="/previews/transcript-viewer.webp"
              alt="Transcript viewer with audio playback, timestamps and editable transcript lines"
              caption="Transcript viewer with click-to-seek playback." />
            <Preview src="/previews/action-items.webp"
              alt="Action items list with owners, deadlines, priorities and status filters"
              caption="Action items across meetings, with owners and deadlines." />
          </div>
        </Section>

        <Section id="use-cases" eyebrow="Use cases" title="Useful wherever meetings create work">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {USE_CASES.map(({ title, text }) => (
              <li key={title} className="card p-5">
                <h3 className="font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="open-source" eyebrow="Open source" title="Free to use, run it yourself" className="bg-white"
          intro="MeetPilot AI is open source under the MIT licence. There are no paid plans. You can run it on your own computer or deploy it to Render.">
          <div className="grid gap-4 md:grid-cols-3">
            {[
              [Lock, "Your keys stay on the server", "AI and transcription provider keys are environment variables on your server and are never sent to the browser."],
              [FileText, "You pay providers directly", "OpenAI, Anthropic or Google bill you for their API usage. Local Whisper transcription costs nothing."],
              [ShieldCheck, "Private by default", "Recordings are stored privately, playback links expire, and you can delete meetings, audio or your whole account."],
            ].map(([Icon, title, text]) => {
              const I = Icon as typeof Lock;
              return (
                <div key={title as string} className="card p-5">
                  <I className="size-5 text-accent" aria-hidden />
                  <h3 className="mt-3 font-semibold text-ink">{title as string}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{text as string}</p>
                </div>
              );
            })}
          </div>
        </Section>

        <section className="bg-navy-950 px-4 py-20 text-center sm:px-6">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Ready to try it?</h2>
            <p className="mt-4 text-slate-300">Create an account and upload a recording, or look around the fictional demo meeting first.</p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link to="/register" className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-white hover:bg-accent-strong sm:w-auto">
                Create a free account <ArrowRight className="size-4" aria-hidden />
              </Link>
              <Link to="/demo" className="inline-flex w-full items-center justify-center rounded-lg border border-white/15 bg-white/5 px-5 py-3 text-sm font-semibold text-white hover:bg-white/10 sm:w-auto">
                Explore the demo
              </Link>
            </div>
            <p className="mt-6 text-xs text-slate-500">Only record and upload meetings you have permission to record and process.</p>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 bg-navy-950 px-4 py-10 text-sm text-slate-400 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <Logo dark />
          <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-3">
            <a href={`${REPO}#readme`} className="inline-flex items-center gap-1.5 hover:text-white" target="_blank" rel="noopener noreferrer"><BookOpen className="size-4" aria-hidden />Documentation</a>
            <Link to="/privacy" className="inline-flex items-center gap-1.5 hover:text-white"><Lock className="size-4" aria-hidden />Privacy</Link>
            <a href={`${REPO}/issues`} className="inline-flex items-center gap-1.5 hover:text-white" target="_blank" rel="noopener noreferrer"><Mail className="size-4" aria-hidden />Contact</a>
            <a href={REPO} className="inline-flex items-center gap-1.5 hover:text-white" target="_blank" rel="noopener noreferrer"><Code2 className="size-4" aria-hidden />Source code</a>
          </nav>
        </div>
        <p className="mx-auto mt-6 max-w-6xl text-xs text-slate-500">MeetPilot AI is open-source software released under the MIT licence.</p>
      </footer>
    </div>
  );
}
