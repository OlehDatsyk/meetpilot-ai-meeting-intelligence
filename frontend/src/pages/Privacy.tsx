import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { get, getToken } from "../lib/api";
import type { SystemStatus } from "../lib/types";

function H({ children }: { children: ReactNode }) {
  return <h2 className="mt-8 text-base font-semibold text-ink">{children}</h2>;
}

export default function PrivacyPage() {
  const signedIn = Boolean(getToken());
  const status = useQuery({ queryKey: ["system-status"], queryFn: () => get<SystemStatus>("/api/v1/system/status"), enabled: signedIn, retry: false });
  const s = status.data;
  return (
    <div className="min-h-full bg-white">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Link to="/" className="mb-6 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" />Back</Link>
        <Logo />
        <h1 className="mt-8 text-2xl font-semibold tracking-tight">Privacy notice</h1>
        <p className="mt-2 text-sm text-muted">This notice describes how this installation of MeetPilot AI handles data. It is not legal advice, and MeetPilot AI has not been certified against GDPR or any other regulation.</p>
        <div className="prose-sm mt-4 space-y-3 text-sm leading-relaxed text-slate-700">
          <H>What is stored</H>
          <ul className="list-disc space-y-1 pl-5">
            <li>Account details: your name, email address and a one-way hash of your password (never the password itself).</li>
            <li>Meeting records you create: titles, descriptions, dates, participant names you enter, and project names.</li>
            <li>Uploaded audio recordings, stored as files outside the database and only reachable through authorised requests.</li>
            <li>Transcripts (both the original machine text and your edits), speaker names you give, AI summaries, decisions, action items, assistant conversations, generated reports and an activity log.</li>
          </ul>
          <H>Who processes audio and text</H>
          <p>Processing depends on how this server is configured{signedIn ? "" : " (sign in to see this installation's settings)"}:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li><strong>Transcription:</strong> {s ? (s.transcription.configured ? <>audio is sent to <strong>{s.transcription.provider}</strong>{s.transcription.provider === "local" ? ", which runs on this server, so audio does not leave it" : ""}.</> : "no provider is configured, so audio is stored but not sent anywhere.") : "audio is sent to the configured speech-to-text provider (for example OpenAI), or processed on the server itself when local transcription is used."}</li>
            <li><strong>Analysis and assistant:</strong> {s ? (s.ai.configured ? <>transcript text and related meeting records are sent to <strong>{s.ai.provider}</strong>{s.ai.fallbacks?.length ? <> (and, if it fails, to {s.ai.fallbacks.map((f) => f.provider).join(", ")})</> : ""}.</> : "no AI provider is configured, so no text is sent to an AI service.") : "transcript text and related records are sent to the configured AI provider (OpenAI, Anthropic or Google), only when analysis runs or you ask the assistant a question."}</li>
          </ul>
          <p>MeetPilot AI does not use your recordings or transcripts to train models. Each provider's own terms decide how long it keeps API data and whether it uses it; read them before configuring a provider.</p>
          <H>Where data is stored</H>
          <p>{s ? <>Files are kept in <strong>{s.storage.provider === "s3" ? "S3-compatible object storage" : "the server's file system"}</strong>{!s.storage.persistent && " that is temporary: files can be lost when the server restarts"}. </> : "Files are kept in the server's file system or in S3-compatible object storage, depending on configuration. "}
            Records are kept in the application's database. The location depends on where the administrator hosts this installation.</p>
          <H>Deleting your data</H>
          <ul className="list-disc space-y-1 pl-5">
            <li>Deleting a meeting removes its recording, transcript, summary, decisions, action items, reports, and assistant answers that cited it.</li>
            <li>You can delete only a recording's audio and keep its transcript.</li>
            <li>Deleting a workspace removes everything in it. Deleting your account removes it and every workspace where you are the only owner.</li>
            <li>Data already sent to an external provider is governed by that provider's retention terms. Database backups made by the hosting provider may keep deleted records until those backups expire.</li>
          </ul>
          <H>Retention</H>
          <p>Workspace admins can set a retention period after which recording audio is deleted automatically; transcripts and analysis are kept until deleted. Without a retention period, data is kept until you delete it.</p>
          <H>Your responsibilities</H>
          <p>You must have permission from the people you record, and you are responsible for complying with recording, consent and data-protection laws that apply to you and to them. Do not upload recordings you are not allowed to process.</p>
          <H>Speakers</H>
          <p>When the transcription provider separates voices, speakers are shown as “Speaker 1”, “Speaker 2” and so on. MeetPilot AI does not identify people from their voice or infer personal characteristics from audio. Speaker names only come from what you type.</p>
        </div>
      </div>
    </div>
  );
}
