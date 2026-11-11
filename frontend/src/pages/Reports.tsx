import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button, Card, CardHeader, EmptyState, ErrorBox, PageHeader, Spinner } from "../components/ui";
import { del, download, get, post, qs } from "../lib/api";
import { formatBytes, formatDateTime } from "../lib/format";
import { canEdit, useWorkspace } from "../lib/session";
import type { Meeting, Page, Report } from "../lib/types";

export default function ReportsPage() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [meetingId, setMeetingId] = useState("");
  const [format, setFormat] = useState<"pdf" | "html">("pdf");
  const [withTranscript, setWithTranscript] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const reports = useQuery({ queryKey: ["reports", ws.id], queryFn: () => get<Report[]>(`/api/v1/reports${qs({ workspace_id: ws.id })}`) });
  const meetings = useQuery({ queryKey: ["meetings", ws.id, "all-for-reports"], queryFn: () => get<Page<Meeting>>(`/api/v1/meetings${qs({ workspace_id: ws.id, page_size: 100 })}`) });
  const gen = useMutation({ mutationFn: () => post<Report>(`/api/v1/meetings/${meetingId}/reports`, { format, include_transcript: withTranscript }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", ws.id] }) });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/v1/reports/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", ws.id] }) });
  return (
    <>
      <PageHeader title="Reports" description="Professional meeting reports in PDF or HTML, generated from the stored meeting record." />
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        {canEdit(ws) && (
          <Card className="h-fit">
            <CardHeader title="Generate a report" />
            <div className="space-y-3 p-5">
              <select aria-label="Meeting" className="input" value={meetingId} onChange={(e) => setMeetingId(e.target.value)}>
                <option value="">Choose a meeting…</option>
                {(meetings.data?.items ?? []).map((m) => <option key={m.id} value={m.id}>{m.title}</option>)}
              </select>
              <div className="flex gap-4 text-sm">
                {(["pdf", "html"] as const).map((f) => <label key={f} className="flex items-center gap-1.5"><input type="radio" checked={format === f} onChange={() => setFormat(f)} />{f.toUpperCase()}</label>)}
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={withTranscript} onChange={(e) => setWithTranscript(e.target.checked)} />Include full transcript</label>
              <Button className="w-full" disabled={!meetingId} loading={gen.isPending} onClick={() => gen.mutate()}><FileText className="size-4" />Generate</Button>
              <ErrorBox error={gen.error} />
            </div>
          </Card>
        )}
        <Card>
          <CardHeader title="Generated reports" />
          <ErrorBox error={error || remove.error} className="mx-5 mt-3" />
          {reports.isLoading ? <Spinner /> : !reports.data?.length ? (
            <EmptyState icon={<FileText className="size-5" />} title="No reports yet">Generate one here or from a meeting's Reports & export tab.</EmptyState>
          ) : (
            <ul className="divide-y divide-line">
              {reports.data.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
                  <div className="min-w-0">
                    <Link to={`/meetings/${r.meeting_id}`} className="text-sm font-medium hover:text-accent">{r.meeting_title}</Link>
                    <div className="text-xs text-muted">{r.format.toUpperCase()} · {formatBytes(r.size_bytes)} · {formatDateTime(r.created_at)}{r.include_transcript ? " · with transcript" : ""}</div>
                  </div>
                  <div className="flex gap-1">
                    <Button size="sm" variant="secondary" onClick={() => download(`/api/v1/reports/${r.id}/download`, `report.${r.format}`).catch(setError)}><Download className="size-3.5" />Download</Button>
                    {canEdit(ws) && <button aria-label="Delete report" onClick={() => confirm("Delete this report file?") && remove.mutate(r.id)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"><Trash2 className="size-4" /></button>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
