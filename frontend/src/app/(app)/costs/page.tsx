"use client";
import { useState } from "react";
import useSWR from "swr";
import { AreaSeries, Bars } from "@/components/Charts";
import { Button, Field, Input, Loading, Modal, PageHeader, Panel, Pill, Select, Stat, Table, Toggle, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dt, ms, pct, usd } from "@/lib/format";

const SCOPE: Record<string, string> = { global: "Global", channel: "Canal", engine: "Motor", video: "Por vídeo" };
const PERIOD: Record<string, string> = { daily: "diário", monthly: "mensal", per_video: "por vídeo" };

export default function Costs() {
  const { data } = useSWR("/costs/summary?days=30");
  const { data: limits, mutate } = useSWR("/costs/limits");
  const { data: usage } = useSWR("/costs/usage?limit=40");
  const { data: channels } = useSWR("/channels");
  const { data: engines } = useSWR("/engines");
  const [edit, setEdit] = useState<any>(null);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  return (
    <div className="space-y-6">
      <PageHeader title="Custos" description="Consumo de cada provedor, custo por vídeo e limites. Ao atingir um limite, operações pagas param e a fábrica usa alternativas gratuitas quando existirem." />
      <section className="grid grid-cols-2 gap-5 rounded-[var(--radius-frame)] border border-line bg-surface p-5 md:grid-cols-5">
        <Stat label="Hoje" value={usd(data.today_usd)} /><Stat label="Este mês" value={usd(data.month_usd)} /><Stat label="Últimos 30 dias" value={usd(data.total_usd)} />
        <Stat label="Custo médio por vídeo" value={usd(data.avg_cost_per_video_usd, 3)} sub={`${data.videos_completed} vídeos concluídos`} />
        <Stat label="Custo por mil views" value={data.cost_per_1k_views != null ? usd(data.cost_per_1k_views, 3) : "—"} sub={data.cost_per_1k_views == null ? "sem métricas" : undefined} />
      </section>
      <Panel title="Limites" actions={<Button size="sm" variant="primary" onClick={() => setEdit({ scope: "global", period: "daily", limit_usd: 5, alert_threshold_pct: 80, action: "block", is_active: true })}>Novo limite</Button>} flush>
        <Table head={["Escopo", "Período", "Limite", "Usado", "Alerta em", "Ação", ""]}>
          {limits?.map((l: any) => (
            <tr key={l.id} className={l.is_active ? "" : "opacity-50"}>
              <td>{SCOPE[l.scope]}{l.scope_id && ` #${l.scope_id}`}</td><td>{PERIOD[l.period]}</td><td className="num">{usd(l.limit_usd)}</td>
              <td>{l.used_pct != null ? <div className="flex items-center gap-2"><div className="h-1.5 w-24 overflow-hidden rounded-full bg-ink/8"><div className={`h-full ${l.used_pct >= 100 ? "bg-onair" : l.used_pct >= l.alert_threshold_pct ? "bg-cue" : "bg-preview"}`} style={{ width: `${Math.min(100, l.used_pct)}%` }} /></div><span className="num text-xs">{usd(l.used_usd)}</span></div> : <span className="text-xs text-muted">verificado em cada vídeo</span>}</td>
              <td className="num">{l.alert_threshold_pct}%</td><td>{l.action === "block" ? <Pill tone="onair">bloquear</Pill> : <Pill tone="cue">só alertar</Pill>}</td>
              <td><Button size="sm" variant="quiet" onClick={() => setEdit(l)}>Editar</Button></td>
            </tr>
          ))}
        </Table>
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Custo por dia">{data.by_day.some((d: any) => d.cost_usd > 0) ? <AreaSeries data={data.by_day} x="day" y="cost_usd" color="#f5a623" format={(v) => `$${v.toFixed(2)}`} /> : <p className="text-sm text-muted">Nenhum gasto no período.</p>}</Panel>
        <Panel title="Por canal">{data.by_channel.some((d: any) => d.cost_usd > 0) ? <Bars data={data.by_channel} x="name" y="cost_usd" horizontal height={Math.max(140, data.by_channel.length * 36)} format={(v) => `$${v.toFixed(2)}`} /> : <p className="text-sm text-muted">Sem dados.</p>}</Panel>
      </div>
      <Panel title="Comparação entre provedores" flush>
        <Table head={["Provedor", "Tipo", "Chamadas", "Custo", "Tempo médio", "Sucesso"]}>
          {data.by_provider.map((p: any) => <tr key={p.provider + p.kind}><td className="font-medium">{p.provider}</td><td>{p.kind}</td><td className="num">{p.calls}</td><td className="num">{usd(p.cost_usd, 4)}</td><td className="num">{ms(p.avg_ms)}</td>
            <td className={p.success_rate < 0.9 ? "text-onair" : ""}>{pct(p.success_rate, 1)}</td></tr>)}
        </Table>
      </Panel>
      <Panel title="Últimas chamadas" flush>
        <Table head={["Quando", "Provedor", "Operação", "Unidades", "Custo", "Produção"]}>
          {usage?.items.map((u: any) => <tr key={u.id} className={u.success ? "" : "text-onair"}><td className="whitespace-nowrap text-xs">{dt(u.created_at)}</td><td>{u.provider_key}{u.is_simulated && <span className="ml-1 text-xs text-muted">(simulado)</span>}</td>
            <td>{u.operation}</td><td className="max-w-56 truncate text-xs text-muted">{u.error || Object.entries(u.units).map(([k, v]) => `${k}: ${v}`).join(", ")}</td><td className="num">{usd(u.actual_cost_usd ?? u.est_cost_usd, 5)}</td><td>{u.production_job_id && `#${u.production_job_id}`}</td></tr>)}
        </Table>
      </Panel>
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? "Editar limite" : "Novo limite"} footer={edit && <>
        {edit.id && <Button variant="danger" onClick={() => run("d", async () => { await api(`/costs/limits/${edit.id}`, { method: "DELETE" }); mutate(); setEdit(null); }, "Limite removido")}>Remover</Button>}
        <Button variant="primary" busy={busy === "s"} onClick={() => run("s", async () => {
          const body = { scope: edit.scope, scope_id: edit.scope_id ? +edit.scope_id : null, period: edit.scope === "video" ? "per_video" : edit.period, limit_usd: +edit.limit_usd,
            alert_threshold_pct: +edit.alert_threshold_pct, action: edit.action, is_active: edit.is_active };
          await api(edit.id ? `/costs/limits/${edit.id}` : "/costs/limits", { method: edit.id ? "PATCH" : "POST", body }); mutate(); setEdit(null); }, "Limite salvo")}>Salvar</Button></>}>
        {edit && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Escopo"><Select value={edit.scope} onChange={(e) => setEdit({ ...edit, scope: e.target.value, scope_id: "" })}>{Object.entries(SCOPE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          {edit.scope === "channel" && <Field label="Canal"><Select value={edit.scope_id || ""} onChange={(e) => setEdit({ ...edit, scope_id: e.target.value })}><option value="">Escolha…</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>}
          {edit.scope === "engine" && <Field label="Motor"><Select value={edit.scope_id || ""} onChange={(e) => setEdit({ ...edit, scope_id: e.target.value })}><option value="">Escolha…</option>{engines?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>}
          {edit.scope !== "video" && <Field label="Período"><Select value={edit.period} onChange={(e) => setEdit({ ...edit, period: e.target.value })}><option value="daily">Diário</option><option value="monthly">Mensal</option></Select></Field>}
          <Field label="Limite (US$)"><Input type="number" min={0.01} step={0.5} value={edit.limit_usd} onChange={(e) => setEdit({ ...edit, limit_usd: e.target.value })} /></Field>
          <Field label="Alertar ao atingir (%)"><Input type="number" min={1} max={100} value={edit.alert_threshold_pct} onChange={(e) => setEdit({ ...edit, alert_threshold_pct: e.target.value })} /></Field>
          <Field label="Ao atingir"><Select value={edit.action} onChange={(e) => setEdit({ ...edit, action: e.target.value })}><option value="block">Bloquear operações pagas</option><option value="alert">Apenas alertar</option></Select></Field>
          <Toggle checked={edit.is_active} onChange={(v) => setEdit({ ...edit, is_active: v })} label="Ativo" />
        </div>}
      </Modal>
    </div>
  );
}
