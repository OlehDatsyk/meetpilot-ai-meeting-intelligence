export function Logo({ dark = false }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#4f46e5" />
        <path d="M9 21V11l7 6 7-6v10" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <div className="leading-tight">
        <div className={`text-[15px] font-semibold tracking-tight ${dark ? "text-white" : "text-ink"}`}>MeetPilot AI</div>
        <div className={`text-[11px] ${dark ? "text-slate-400" : "text-muted"}`}>Turn conversations into clear outcomes</div>
      </div>
    </div>
  );
}
