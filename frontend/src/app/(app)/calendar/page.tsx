"use client";
import clsx from "clsx";
import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import useSWR from "swr";
import { Button, PageHeader, Select } from "@/components/ui";
import { qs } from "@/lib/api";
import { PLATFORM, PUB_STATUS } from "@/lib/format";

const WEEK = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const DOT: Record<string, string> = { published: "bg-preview", scheduled: "bg-reel", failed: "bg-onair", awaiting_manual: "bg-cue", processing: "bg-cue", publishing: "bg-onair", cancelled: "bg-ink/20", draft: "bg-ink/30" };

export default function CalendarPage() {
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [channel, setChannel] = useState("");
  const start = new Date(month.getFullYear(), month.getMonth(), 1 - month.getDay());
  const end = new Date(start); end.setDate(end.getDate() + 42);
  const { data } = useSWR(`/calendar${qs({ start: start.toISOString(), end: end.toISOString(), channel_id: channel })}`);
  const { data: channels } = useSWR("/channels");
  const byDay = useMemo(() => {
    const m: Record<string, any[]> = {};
    (data || []).forEach((p: any) => { const d = new Date(p.scheduled_at || p.published_at).toDateString(); (m[d] ||= []).push(p); });
    return m;
  }, [data]);
  const days = Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(d.getDate() + i); return d; });
  const today = new Date().toDateString();
  return (
    <div>
      <PageHeader title="Calendário" description="Publicações agendadas e realizadas por dia."
        actions={<>
          <Select value={channel} onChange={(e) => setChannel(e.target.value)} className="w-48" aria-label="Canal"><option value="">Todos os canais</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Button aria-label="Mês anterior" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={16} /></Button>
          <Button onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Hoje</Button>
          <Button aria-label="Próximo mês" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={16} /></Button>
        </>} />
      <h2 className="mb-3 capitalize">{month.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}</h2>
      <div className="overflow-x-auto scroll-thin">
        <div className="grid min-w-[760px] grid-cols-7 overflow-hidden rounded-[var(--radius-frame)] border border-line bg-line gap-px">
          {WEEK.map((w) => <div key={w} className="bg-paper px-2 py-1.5 text-xs text-muted">{w}</div>)}
          {days.map((d) => {
            const items = byDay[d.toDateString()] || [];
            return (
              <div key={d.toISOString()} className={clsx("min-h-28 bg-surface p-1.5", d.getMonth() !== month.getMonth() && "bg-paper/60 text-muted")}>
                <div className={clsx("num mb-1 inline-flex size-6 items-center justify-center rounded-full text-xs", d.toDateString() === today && "bg-reel text-white")}>{d.getDate()}</div>
                <ul className="space-y-1">
                  {items.slice(0, 4).map((p) => (
                    <li key={p.id}><Link href={`/production/${p.production_job_id}`} title={`${PLATFORM[p.platform]} · ${PUB_STATUS[p.status]?.label}`}
                      className="flex items-center gap-1.5 truncate rounded px-1 py-0.5 text-[11px] hover:bg-paper">
                      <span className={clsx("size-1.5 shrink-0 rounded-full", DOT[p.status])} />
                      <span className="num text-muted">{new Date(p.scheduled_at || p.published_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>
                      <span className="truncate">{p.title}</span></Link></li>
                  ))}
                  {items.length > 4 && <li className="px-1 text-[11px] text-muted">+{items.length - 4}</li>}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        {["scheduled", "published", "awaiting_manual", "failed"].map((s) => <span key={s} className="flex items-center gap-1.5"><span className={clsx("size-2 rounded-full", DOT[s])} />{PUB_STATUS[s].label}</span>)}
      </div>
    </div>
  );
}
