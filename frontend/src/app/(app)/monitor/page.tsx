"use client";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { FilmStrip } from "@/components/FilmStrip";
import { Loading, PageHeader, Panel, Pill } from "@/components/ui";
import { ago, ms, STEP_LABEL } from "@/lib/format";
import { type LiveEvent, useLiveEvents } from "@/lib/live";

export default function Monitor() {
  const { data } = useSWR("/monitor", { refreshInterval: 5000 });
  const [feed, setFeed] = useState<LiveEvent[]>([]);
  useLiveEvents((e) => setFeed((f) => [e, ...f].slice(0, 80)));
  if (!data) return <Loading />;
  return (
    <div className="space-y-6">
      <PageHeader title="Monitor da fábrica" description="O que cada agente está fazendo agora, filas, workers e falhas recentes." />
      <div className="grid gap-4 sm:grid-cols-3">
        <Panel title="Workers">
          {data.workers.length ? data.workers.map((w: string) => <div key={w} className="flex items-center gap-2 text-sm"><span className="size-2 rounded-full bg-preview" />{w}</div>)
            : <p className="text-sm text-onair">Nenhum worker respondeu. Verifique o serviço <code>worker</code>.</p>}
        </Panel>
        <Panel title="Filas">
          {Object.entries(data.queues).map(([q, n]) => <div key={q} className="flex justify-between text-sm"><span>{q === "render" ? "Produção/renderização" : q === "default" ? "Tarefas gerais" : q}</span><span className="num">{String(n)}</span></div>)}
        </Panel>
        <Panel title="Produções ativas"><div className="num font-display text-3xl">{data.active_productions.length}</div></Panel>
      </div>

      {data.active_productions.length > 0 && (
        <Panel title="Em andamento" flush>
          {data.active_productions.map((j: any) => <ActiveRow key={j.id} j={j} />)}
        </Panel>
      )}

      <section>
        <h2 className="mb-3">Agentes</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.agents.map((a: any) => {
            const running = a.running.length > 0;
            return (
              <div key={a.key} className={clsx("rounded-[var(--radius-frame)] border bg-surface p-3", running ? "border-onair/50" : "border-line")}>
                <div className="flex items-center justify-between">
                  <span className="font-medium">{a.label}</span>
                  <span className={clsx("size-2.5 rounded-full", running ? "bg-onair animate-pulse" : a.last?.status === "failed" ? "bg-cue" : "bg-ink/15")} title={running ? "executando" : "ocioso"} />
                </div>
                <div className="mt-1 text-xs text-muted">
                  {running ? <>Executando {a.running[0].production_job_id && <Link className="text-reel" href={`/production/${a.running[0].production_job_id}`}>produção #{a.running[0].production_job_id}</Link>}</>
                    : a.last ? <>Última execução {ago(a.last.updated_at)} · {a.last.status === "failed" ? "falhou" : "ok"} · {ms(a.last.duration_ms)}</> : "Ainda não executou"}
                </div>
                <div className="mt-2 flex gap-3 text-xs text-muted">
                  <span>{a.stats.succeeded || 0} concluídas</span><span>{a.pending} pendentes</span><span className={a.stats.failed ? "text-onair" : ""}>{a.stats.failed || 0} falhas</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Eventos ao vivo" flush>
          <ul className="max-h-80 overflow-y-auto font-mono text-xs scroll-thin">
            {feed.length === 0 && <li className="p-4 font-sans text-sm text-muted">Aguardando eventos…</li>}
            {feed.map((e, i) => <li key={i} className="border-b border-line/60 px-4 py-1.5"><span className="text-muted">{new Date(e.ts).toLocaleTimeString("pt-BR")}</span> {e.type} {e.data?.agent && STEP_LABEL[e.data.agent]} {e.data?.job_id && `#${e.data.job_id}`} {e.data?.msg || e.data?.error || ""}</li>)}
          </ul>
        </Panel>
        <Panel title="Falhas recentes" flush>
          {data.recent_failures.length === 0 ? <p className="p-4 text-sm text-muted">Sem falhas registradas.</p> : (
            <ul className="max-h-80 overflow-y-auto scroll-thin">{data.recent_failures.map((f: any) => (
              <li key={f.id} className="border-b border-line/70 px-4 py-2.5 text-sm last:border-0">
                <div className="flex justify-between"><span className="font-medium">{STEP_LABEL[f.agent] || f.agent}</span><span className="text-xs text-muted">{ago(f.updated_at)}</span></div>
                <div className="line-clamp-2 text-xs text-onair">{f.error}</div>
                {f.production_job_id && <Link className="text-xs text-reel" href={`/production/${f.production_job_id}`}>Abrir produção #{f.production_job_id}</Link>}
              </li>))}</ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function ActiveRow({ j }: { j: any }) {
  const { data } = useSWR(`/productions/${j.id}`, { refreshInterval: 3000 });
  return (
    <Link href={`/production/${j.id}`} className="grid items-center gap-3 border-b border-line/70 px-4 py-3 last:border-0 hover:bg-paper/60 md:grid-cols-[1fr_360px_120px]">
      <div className="min-w-0"><div className="truncate font-medium">{j.title}</div><div className="text-xs text-muted">{j.channel?.name} · {j.current_step ? STEP_LABEL[j.current_step] : "na fila"}</div></div>
      {data && <FilmStrip steps={data.steps} />}
      <Pill tone={j.status === "paused" ? "cue" : "onair"} dot>{j.status === "paused" ? "aguardando você" : `${Math.round(j.progress * 100)}%`}</Pill>
    </Link>
  );
}
