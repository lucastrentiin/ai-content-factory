"use client";
import { useState } from "react";
import useSWR from "swr";
import { AreaSeries, Bars } from "@/components/Charts";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Panel, Pill, Select, Stat, Table, Tabs, Textarea, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { day, int, pct } from "@/lib/format";

const DIMS: Record<string, string> = { engine: "Motor", visual_style: "Estilo visual", format: "Formato", duration_bucket: "Duração", platform: "Plataforma", hour: "Horário", channel: "Canal", character: "Personagem" };
const DIM_PT: Record<string, string> = { hook: "Gancho", title: "Título", cover: "Capa", narration: "Narração", duration: "Duração", visual_style: "Estilo visual", script_format: "Formato do roteiro" };

export default function Analytics() {
  const [tab, setTab] = useState<"results" | "learning" | "tests">("results");
  const [channel, setChannel] = useState("");
  const { data: channels } = useSWR("/channels");
  const { busy, run } = useAction();
  return (
    <div className="space-y-5">
      <PageHeader title="Analytics" description="Resultados por canal, motor, personagem, formato, duração e horário. A fábrica só muda a estratégia com amostra mínima e intervalo de confiança."
        actions={<>
          <Select className="w-48" value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="Canal"><option value="">Todos os canais</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          <Button busy={busy === "c"} onClick={() => run("c", () => api("/analytics/collect", { method: "POST" }), "Coleta de métricas iniciada")}>Coletar métricas</Button>
          <Button busy={busy === "o"} onClick={() => run("o", () => api("/analytics/optimize", { method: "POST" }), "Otimização iniciada")}>Rodar otimização</Button>
        </>} />
      <Tabs value={tab} onChange={setTab} items={[{ value: "results", label: "Resultados" }, { value: "learning", label: "Aprendizado" }, { value: "tests", label: "Testes A/B" }]} />
      {tab === "results" && <Results channel={channel} />}
      {tab === "learning" && <Learning channel={channel} channels={channels || []} />}
      {tab === "tests" && <Tests channel={channel} channels={channels || []} />}
    </div>
  );
}

function Results({ channel }: { channel: string }) {
  const [dim, setDim] = useState("engine");
  const { data: ov } = useSWR("/analytics/overview");
  const { data: ts } = useSWR(`/analytics/timeseries${qs({ channel_id: channel })}`);
  const { data: bd } = useSWR(`/analytics/breakdown${qs({ dimension: dim, channel_id: channel })}`);
  if (!ov) return <Loading />;
  if (!ov.has_metrics) return <Empty title="Ainda não há métricas">As métricas chegam pelas APIs das plataformas conectadas (a cada 6 h na primeira semana) ou podem ser registradas manualmente em Publicações.</Empty>;
  return (
    <div className="space-y-6">
      <section className="grid grid-cols-2 gap-5 rounded-[var(--radius-frame)] border border-line bg-surface p-5 md:grid-cols-5">
        <Stat label="Visualizações" value={int(ov.views)} /><Stat label="Curtidas" value={int(ov.likes)} /><Stat label="Comentários" value={int(ov.comments)} />
        <Stat label="Compartilhamentos" value={int(ov.shares)} /><Stat label="Seguidores ganhos" value={int(ov.followers_gained)} />
      </section>
      <Panel title="Visualizações por dia de publicação">{ts?.length ? <AreaSeries data={ts.map((d: any) => ({ ...d, day: day(d.day) }))} x="day" y="views" format={(v) => int(v)} /> : <p className="text-sm text-muted">Sem dados no período.</p>}</Panel>
      <Panel title="Desempenho por" actions={<Select className="w-44" value={dim} onChange={(e) => setDim(e.target.value)} aria-label="Dimensão">{Object.entries(DIMS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}>
        {!bd ? <Loading /> : bd.length === 0 ? <p className="text-sm text-muted">Sem dados.</p> : (
          <div className="grid gap-6 lg:grid-cols-2">
            <Bars data={bd} x="key" y="score" horizontal height={Math.max(160, bd.length * 36)} format={(v) => v.toFixed(2)} />
            <Table head={[DIMS[dim], "Vídeos", "Pontuação", "IC 90%", "Média de views", "Conclusão"]}>
              {bd.map((r: any) => <tr key={r.key}><td>{r.key}</td><td className="num">{r.n}</td><td className="num font-medium">{r.score}</td>
                <td className="num text-xs text-muted">{r.ci_low != null ? `${r.ci_low.toFixed(2)}–${r.ci_high.toFixed(2)}` : "amostra pequena"}</td>
                <td className="num">{int(r.avg_views)}</td><td className="num">{pct(r.avg_completion)}</td></tr>)}
            </Table>
          </div>
        )}
        <p className="mt-3 text-xs text-muted">Pontuação = log₁₀(views) × (1 + 4 × engajamento ponderado) × retenção, quando disponível. Compartilhamentos valem 3×, comentários e salvamentos 2×.</p>
      </Panel>
    </div>
  );
}

function Learning({ channel, channels }: { channel: string; channels: any[] }) {
  const cid = channel || channels[0]?.id;
  const { data: arms } = useSWR(cid ? `/analytics/arms?channel_id=${cid}` : null);
  const { data: decs, mutate } = useSWR(`/optimization/decisions${qs({ channel_id: cid })}`);
  const { busy, run } = useAction();
  if (!cid) return <Empty title="Crie um canal primeiro" />;
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted">Canal: <strong>{channels.find((c) => c.id == cid)?.name}</strong>. Só publicações com mais de 48 h entram na conta. Um braço só é confiável a partir da amostra mínima (Configurações → Aprendizado).</p>
      <Panel title="Estatísticas por estratégia" flush>
        {!arms?.length ? <p className="p-4 text-sm text-muted">Sem publicações maduras com métricas ainda.</p> : (
          <Table head={["Dimensão", "Valor", "Amostra", "Média", "Intervalo", "Confiável"]}>
            {arms.map((a: any) => <tr key={a.id}><td>{DIMS[a.dimension] || a.dimension}</td><td>{a.value}</td><td className="num">{a.n}</td><td className="num">{a.mean.toFixed(3)}</td>
              <td className="num text-xs text-muted">{a.ci_low != null ? `${a.ci_low.toFixed(2)}–${a.ci_high.toFixed(2)}` : "—"}</td>
              <td>{a.reliable ? <Pill tone="preview">sim</Pill> : <Pill>ainda não</Pill>}</td></tr>)}
          </Table>
        )}
      </Panel>
      <Panel title="Decisões de otimização" flush>
        {!decs?.items?.length ? <p className="p-4 text-sm text-muted">Nenhuma decisão ainda. A otimização roda diariamente.</p> : decs.items.map((d: any) => (
          <div key={d.id} className="border-b border-line/70 px-4 py-3 text-sm last:border-0">
            <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-muted">{day(d.created_at)}</span>
              {d.applied ? <Pill tone="preview">aplicada</Pill> : JSON.stringify(d.previous) !== JSON.stringify(d.proposed) ?
                <Button size="sm" busy={busy === `a${d.id}`} onClick={() => run(`a${d.id}`, async () => { await api(`/optimization/decisions/${d.id}/apply`, { method: "POST" }); mutate(); }, "Nova distribuição aplicada")}>Aplicar</Button> : <Pill>sem mudança</Pill>}</div>
            <p className="mt-1">{d.rationale?.decision}</p>
            <div className="mt-2 flex flex-wrap gap-4 text-xs">{Object.keys(d.proposed).map((k) => <span key={k}>{k}: <span className="text-muted">{pct(d.previous[k] / Object.values<number>(d.previous).reduce((a, b) => a + b, 0))}</span> → <strong>{pct(d.proposed[k])}</strong>
              {d.rationale?.prob_best?.[k] != null && <span className="text-muted"> (P melhor {pct(d.rationale.prob_best[k])})</span>}</span>)}</div>
          </div>
        ))}
      </Panel>
    </div>
  );
}

function Tests({ channel, channels }: { channel: string; channels: any[] }) {
  const { data, mutate } = useSWR(`/experiments${qs({ channel_id: channel })}`);
  const [open, setOpen] = useState(false);
  const { busy, run } = useAction();
  return (
    <div className="space-y-4">
      <div className="flex justify-between gap-4"><p className="max-w-2xl text-sm text-muted">Enquanto um teste está ativo, novas produções automáticas do canal alternam entre as variantes. A vencedora só é declarada com significância estatística (teste t de Welch).</p>
        <Button variant="primary" onClick={() => setOpen(true)}>Novo teste</Button></div>
      {!data ? <Loading /> : data.length === 0 ? <Empty title="Nenhum teste A/B" /> : data.map((e: any) => (
        <Panel key={e.id} title={<div><h2 className="text-base">{e.name}</h2><div className="text-xs text-muted">{DIM_PT[e.dimension]} · métrica {e.metric} · mínimo {e.min_samples_per_variant} por variante · {pct(e.confidence)} de confiança</div></div>}
          actions={<>{e.status === "running" && <><Button size="sm" busy={busy === `e${e.id}`} onClick={() => run(`e${e.id}`, async () => { await api(`/experiments/${e.id}/evaluate`, { method: "POST" }); mutate(); })}>Avaliar agora</Button>
            <Button size="sm" variant="quiet" onClick={() => run(`s${e.id}`, async () => { await api(`/experiments/${e.id}/stop`, { method: "POST" }); mutate(); }, "Teste encerrado")}>Encerrar</Button></>}
            <Pill tone={e.status === "running" ? "onair" : e.status === "completed" ? "preview" : "neutral"}>{e.status === "running" ? "em andamento" : e.status === "completed" ? "concluído" : "encerrado"}</Pill></>}>
          {e.hypothesis && <p className="mb-3 text-sm">{e.hypothesis}</p>}
          <div className="grid gap-3 sm:grid-cols-2">{e.variants.map((v: any) => (
            <div key={v.id} className={`rounded-md border p-3 text-sm ${e.winner_variant_id === v.id ? "border-preview bg-preview-soft" : "border-line"}`}>
              <div className="font-medium">Variante {v.label}{e.winner_variant_id === v.id && " · vencedora"}</div>
              <div className="text-muted">{v.description || JSON.stringify(v.config)}</div>
              <div className="mt-1 text-xs text-muted">{v.assignments} produções · {e.result?.variants?.[v.label]?.n ?? 0} com métricas maduras · média {e.result?.variants?.[v.label]?.mean ?? "—"}</div>
            </div>))}</div>
          {e.result?.conclusion && <p className="mt-3 text-sm">{e.result.conclusion}</p>}
        </Panel>
      ))}
      <NewTest open={open} onClose={() => setOpen(false)} channels={channels} onDone={mutate} />
    </div>
  );
}

function NewTest({ open, onClose, channels, onDone }: any) {
  const [f, setF] = useState<any>({ channel_id: "", name: "", hypothesis: "", dimension: "duration", metric: "engagement_score", min: 10, a: "", b: "", ca: "{\"duration_s\": 30}", cb: "{\"duration_s\": 55}" });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Novo teste A/B" wide footer={<Button variant="primary" disabled={!f.channel_id || !f.name} busy={!!busy} onClick={() => run("t", async () => {
      await api("/experiments", { body: { channel_id: +f.channel_id, name: f.name, hypothesis: f.hypothesis, dimension: f.dimension, metric: f.metric, min_samples_per_variant: +f.min,
        variants: [{ label: "A", description: f.a, config: JSON.parse(f.ca) }, { label: "B", description: f.b, config: JSON.parse(f.cb) }] } }); onDone(); onClose(); }, "Teste iniciado")}>Iniciar teste</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Canal"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Escolha…</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Hipótese"><Input value={f.hypothesis} onChange={(e) => setF({ ...f, hypothesis: e.target.value })} placeholder="Vídeos de 30s retêm mais que os de 55s" /></Field>
        <Field label="O que varia"><Select value={f.dimension} onChange={(e) => setF({ ...f, dimension: e.target.value })}>{Object.entries(DIM_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Métrica"><Select value={f.metric} onChange={(e) => setF({ ...f, metric: e.target.value })}><option value="engagement_score">Pontuação composta</option><option value="views">Visualizações</option><option value="engagement_rate">Taxa de engajamento</option><option value="completion_rate">Taxa de conclusão</option><option value="shares_rate">Taxa de compartilhamento</option></Select></Field>
        <Field label="Amostra mínima por variante"><Input type="number" min={3} value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} /></Field>
        <div />
        <Field label="Variante A"><Input value={f.a} onChange={(e) => setF({ ...f, a: e.target.value })} placeholder="Descrição" /></Field>
        <Field label="Variante B"><Input value={f.b} onChange={(e) => setF({ ...f, b: e.target.value })} placeholder="Descrição" /></Field>
        <Field label="Parâmetros A" hint='Ex.: {"duration_s": 30} ou {"visual_style": "stickman"}'><Textarea rows={2} className="font-mono text-xs" value={f.ca} onChange={(e) => setF({ ...f, ca: e.target.value })} /></Field>
        <Field label="Parâmetros B"><Textarea rows={2} className="font-mono text-xs" value={f.cb} onChange={(e) => setF({ ...f, cb: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
