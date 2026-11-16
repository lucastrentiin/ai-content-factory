"use client";
import Link from "next/link";
import useSWR from "swr";
import { useState } from "react";
import { AreaSeries } from "@/components/Charts";
import { ManualPrompt } from "@/components/ManualPrompt";
import { Button, Empty, Loading, Modal, Panel, Pill, Simulated, Stat, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, dt, int, JOB_STATUS, PLATFORM, STEP_LABEL, usd } from "@/lib/format";

export default function Dashboard() {
  const { data, error, mutate } = useSWR("/dashboard", { refreshInterval: 30000 });
  const [manualReq, setManualReq] = useState<number | null>(null);
  const { busy, run } = useAction();
  if (error) return <Empty title="Não foi possível carregar o painel">{error.message}</Empty>;
  if (!data) return <Loading />;
  const o = data.overview;
  const inProd = (o.jobs_by_status.running || 0) + (o.jobs_by_status.queued || 0);
  const waiting = (o.jobs_by_status.awaiting_approval || 0) + (o.jobs_by_status.needs_review || 0);
  return (
    <div className="space-y-6">
      <div>
        <h1>Visão geral</h1>
        <p className="mt-1 text-sm text-muted">Últimos 30 dias da fábrica.</p>
      </div>

      {data.channels === 0 && (
        <Empty title="Crie seu primeiro canal" action={<Link className="text-sm font-medium text-reel" href="/channels">Criar canal</Link>}>
          Cada canal tem nicho, idioma, motores de conteúdo e regras de publicação próprias. Depois disso a fábrica pode gerar ideias e vídeos.
        </Empty>
      )}
      {!data.has_real_llm && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-frame)] border border-cue/50 bg-cue-soft px-4 py-3 text-sm">
          <span className="max-w-3xl"><strong>Sem modelo de linguagem configurado.</strong> Roteiros e ideias estão vindo do gerador de modelos interno <Simulated />, que não é IA.
          Use o Claude da sua assinatura copiando e colando, ou adicione uma chave de API em <Link href="/settings" className="font-medium text-reel">Configurações</Link>.</span>
          <Button variant="primary" busy={busy === "m"} onClick={() => run("m", async () => { await api("/manual-mode", { body: { enabled: true } }); mutate(); }, "Modo copiar e colar ativado")}>Usar o Claude da minha assinatura</Button>
        </div>
      )}
      {data.manual_mode && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-frame)] border border-reel/30 bg-reel-soft px-4 py-3 text-sm">
          <span><strong>Modo copiar e colar ativo.</strong> Cada vídeo e cada geração de ideias pede uma resposta do Claude que você cola aqui.
            {data.manual_pending.length > 0 ? ` ${data.manual_pending.length} pedido(s) esperando você.` : " Nenhum pedido pendente."}</span>
          <Button variant="quiet" busy={busy === "off"} onClick={() => run("off", async () => { await api("/manual-mode", { body: { enabled: false } }); mutate(); }, "Modo copiar e colar desativado")}>Desativar</Button>
        </div>
      )}
      {data.manual_pending.length > 0 && (
        <Panel title="Respostas do Claude esperando você" flush>
          <ul>{data.manual_pending.map((r: any) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line/70 px-4 py-3 text-sm last:border-0">
              <span><strong>{r.title}</strong>{r.production_job_id && <span className="text-muted"> · produção #{r.production_job_id}</span>}{r.error && <span className="text-onair"> · resposta anterior inválida</span>}</span>
              {r.production_job_id ? <Link href={`/production/${r.production_job_id}`}><Button size="sm" variant="primary">Responder</Button></Link>
                : <Button size="sm" variant="primary" onClick={() => setManualReq(r.id)}>Responder</Button>}
            </li>))}</ul>
        </Panel>
      )}
      <Modal open={!!manualReq} onClose={() => setManualReq(null)} title="Resposta do Claude" wide>
        {manualReq && <ManualPrompt compact requestId={manualReq} onDone={() => { setManualReq(null); mutate(); }} />}
      </Modal>

      <section className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-[var(--radius-frame)] border border-line bg-surface p-5 md:grid-cols-4 xl:grid-cols-7">
        <Stat label="Vídeos produzidos" value={int(o.videos_produced)} />
        <Stat label="Publicados" value={int(o.videos_published)} />
        <Stat label="Agendados" value={int(o.scheduled)} />
        <Stat label="Visualizações" value={int(o.views)} sub={o.has_metrics ? undefined : "sem métricas ainda"} />
        <Stat label="Seguidores ganhos" value={int(o.followers_gained)} />
        <Stat label="Gasto hoje" value={usd(data.costs.today_usd)} />
        <Stat label="Gasto no mês" value={usd(data.costs.month_usd)} />
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel title="Produções recentes" actions={<Link href="/production" className="text-sm text-reel">Ver todas</Link>} flush>
          {data.recent_productions.length === 0 ? <div className="p-4"><Empty title="Nenhuma produção ainda">Gere ideias e envie a melhor para produção.</Empty></div> : (
            <ul>
              {data.recent_productions.map((j: any) => (
                <li key={j.id} className="flex items-center gap-3 border-b border-line/70 px-4 py-3 last:border-0">
                  <span className="h-9 w-1 rounded-full" style={{ background: j.engine?.color }} />
                  <div className="min-w-0 flex-1">
                    <Link href={`/production/${j.id}`} className="block truncate font-medium hover:text-reel">{j.title}</Link>
                    <div className="text-xs text-muted">{j.channel?.name} · {j.engine?.name} · {ago(j.updated_at)}</div>
                  </div>
                  {j.is_simulated && <Simulated />}
                  <Pill tone={JOB_STATUS[j.status]?.tone} dot>{JOB_STATUS[j.status]?.label || j.status}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <div className="space-y-6">
          <Panel title="Precisa de você">
            <div className="flex gap-8">
              <Stat label="Em produção" value={inProd} />
              <Stat label="Para aprovar ou revisar" value={waiting} tone={waiting ? "onair" : undefined} />
            </div>
            {waiting > 0 && <Link href="/production?status=awaiting_approval,needs_review" className="mt-3 inline-block text-sm font-medium text-reel">Abrir fila de revisão</Link>}
            {data.alerts.length > 0 && (
              <ul className="mt-4 space-y-2 border-t border-line pt-3">
                {data.alerts.map((a: any) => (
                  <li key={a.id} className="text-sm"><span className={a.level === "error" ? "text-onair" : "text-[#a86a00]"}>●</span> {a.title}</li>
                ))}
              </ul>
            )}
          </Panel>
          <Panel title="Próximas publicações" flush>
            {data.upcoming.length === 0 ? <p className="p-4 text-sm text-muted">Nada agendado.</p> : (
              <ul>{data.upcoming.map((p: any) => (
                <li key={p.id} className="flex justify-between gap-2 border-b border-line/70 px-4 py-2.5 text-sm last:border-0">
                  <span className="truncate">{p.title}</span><span className="shrink-0 text-muted">{PLATFORM[p.platform_key]} · {dt(p.scheduled_at)}</span>
                </li>))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Custo por dia">
          {data.costs.by_day.some((d: any) => d.cost_usd > 0) ? <AreaSeries data={data.costs.by_day} x="day" y="cost_usd" color="#f5a623" format={(v) => `$${v.toFixed(2)}`} />
            : <p className="text-sm text-muted">Nenhum gasto registrado. Provedores locais e simulados não têm custo.</p>}
        </Panel>
        <Panel title="Atividade dos agentes" flush>
          <ul className="max-h-64 overflow-y-auto scroll-thin">
            {data.activity.map((a: any) => (
              <li key={a.id} className="flex items-center justify-between gap-3 border-b border-line/70 px-4 py-2 text-sm last:border-0">
                <span>{STEP_LABEL[a.agent] || a.agent}{a.production_job_id && <Link className="ml-1 text-muted hover:text-reel" href={`/production/${a.production_job_id}`}>#{a.production_job_id}</Link>}</span>
                <span className="flex items-center gap-2 text-xs text-muted">
                  <Pill tone={a.status === "failed" ? "onair" : a.status === "running" ? "cue" : "preview"}>{a.status === "failed" ? "falhou" : a.status === "running" ? "executando" : "ok"}</Pill>
                  {ago(a.updated_at)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
