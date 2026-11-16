"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { NewProduction } from "@/components/NewProduction";
import { Suspense, useState } from "react";
import useSWR from "swr";
import { FilmStrip } from "@/components/FilmStrip";
import { Button, Empty, ErrorBox, Loading, PageHeader, Pager, Pill, Select, Simulated } from "@/components/ui";
import { qs } from "@/lib/api";
import { ago, JOB_STATUS, usd } from "@/lib/format";

function ProductionList() {
  const sp = useSearchParams();
  const [status, setStatus] = useState(sp.get("status") || "");
  const [channel, setChannel] = useState("");
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const { data, error } = useSWR(`/productions${qs({ status, channel_id: channel, limit: 20, offset })}`, { refreshInterval: 8000 });
  const { data: channels } = useSWR("/channels");
  return (
    <>
      <PageHeader title="Produção" description="Cada linha é um vídeo atravessando a fábrica. A película mostra as 12 etapas: verde concluída, vermelha em execução ou com falha, âmbar aguardando nova tentativa."
        actions={<Button variant="primary" onClick={() => setCreating(true)}>Nova produção</Button>} />
      <div className="mb-4 flex flex-wrap gap-2">
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} className="w-56" aria-label="Filtrar por status">
          <option value="">Todos os status</option>
          <option value="queued,running">Em produção</option>
          <option value="awaiting_approval,needs_review,awaiting_input">Precisa de você</option>
          <option value="awaiting_approval,needs_review">Aguardando aprovação/revisão</option>
          <option value="awaiting_input">Aguardando resposta do Claude</option>
          <option value="paused">Pausadas (modo manual)</option>
          <option value="completed">Concluídas</option>
          <option value="failed,blocked_budget">Com problema</option>
          <option value="cancelled">Canceladas</option>
        </Select>
        <Select value={channel} onChange={(e) => { setChannel(e.target.value); setOffset(0); }} className="w-56" aria-label="Filtrar por canal">
          <option value="">Todos os canais</option>
          {channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </div>
      <ErrorBox error={error} />
      {!data ? <Loading /> : data.items.length === 0 ? (
        <Empty title="Nenhuma produção encontrada" action={<Button onClick={() => setCreating(true)}>Nova produção</Button>}>
          Produções nascem de ideias aprovadas, episódios de séries ou de um roteiro escrito por você.
        </Empty>
      ) : (
        <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
          {data.items.map((j: any) => <Row key={j.id} j={j} />)}
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </div>
      )}
      <NewProduction open={creating} onClose={() => setCreating(false)} channels={channels || []} />
    </>
  );
}

function Row({ j }: { j: any }) {
  const { data } = useSWR(j.status === "running" || j.status === "queued" ? `/productions/${j.id}` : null, { refreshInterval: 4000 });
  const st = JOB_STATUS[j.status] || { label: j.status, tone: "neutral" };
  return (
    <Link href={`/production/${j.id}`} className="grid grid-cols-[64px_1fr] gap-4 border-b border-line/70 px-4 py-3 last:border-0 hover:bg-paper/60 md:grid-cols-[64px_1fr_280px_150px]">
      <div className="aspect-[9/16] w-16 overflow-hidden rounded bg-ink/10">
        {j.thumbnail && <img src={j.thumbnail.url} alt="" className="size-full object-cover" loading="lazy" />}
      </div>
      <div className="min-w-0">
        <div className="flex items-center gap-2"><span className="truncate font-medium">{j.title}</span>{j.is_simulated && <Simulated />}</div>
        <div className="mt-0.5 text-xs text-muted">#{j.id} · {j.channel?.name} · <span style={{ color: j.engine?.color }}>{j.engine?.name}</span> · {j.visual_style} · {ago(j.created_at)}</div>
        {j.error && <div className="mt-1 line-clamp-1 text-xs text-onair">{j.error}</div>}
      </div>
      <div className="col-span-2 self-center md:col-span-1">
        {data?.steps ? <FilmStrip steps={data.steps} /> : (
          <div className="h-2 overflow-hidden rounded-full bg-ink/8"><div className="h-full bg-reel" style={{ width: `${(j.progress || 0) * 100}%` }} /></div>
        )}
      </div>
      <div className="col-span-2 flex items-center justify-between gap-2 md:col-span-1 md:flex-col md:items-end md:justify-center">
        <Pill tone={st.tone} dot>{st.label}</Pill>
        <span className="num text-xs text-muted">{usd(j.actual_cost_usd, 3)}</span>
      </div>
    </Link>
  );
}

export default function Page() {
  return <Suspense><ProductionList /></Suspense>;
}
