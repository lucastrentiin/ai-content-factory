"use client";
import { useState } from "react";
import useSWR from "swr";
import { AreaSeries } from "@/components/Charts";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Pager, Pill, Select, Simulated, Table, Textarea, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { ago, day, int } from "@/lib/format";

const TSTATUS: Record<string, { label: string; tone: any }> = {
  rising: { label: "Em alta", tone: "preview" }, active: { label: "Estável", tone: "reel" }, declining: { label: "Perdendo força", tone: "cue" }, expired: { label: "Expirada", tone: "neutral" },
};

export default function Trends() {
  const [f, setF] = useState({ q: "", status: "", category: "", sort: "score" });
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const { data, mutate } = useSWR(`/trends${qs({ ...f, limit: 40, offset })}`);
  const { data: sources, mutate: ms } = useSWR("/trend-sources", { refreshInterval: 20000 });
  const { data: cats } = useSWR("/trends/categories");
  const { busy, run } = useAction();
  return (
    <div className="space-y-6">
      <PageHeader title="Tendências" description="Assuntos e formatos em alta, com evolução ao longo do tempo. A fábrica usa os sinais para criar conteúdo original, nunca para copiar."
        actions={<>
          <Button onClick={() => setImporting(true)}>Importar tendências</Button>
          <Button busy={busy === "a"} onClick={() => run("a", async () => { await api("/trends/analyze", { method: "POST" }); mutate(); }, "Tendências analisadas")}>Analisar novas</Button>
          <Button variant="primary" busy={busy === "r"} onClick={() => run("r", async () => { await api("/trends/research", { body: {} }); setTimeout(() => { mutate(); ms(); }, 4000); }, "Pesquisa iniciada nas fontes ativas")}>Pesquisar agora</Button>
        </>} />

      <section className="flex gap-2 overflow-x-auto pb-1 scroll-thin">
        {sources?.map((s: any) => (
          <div key={s.id} className="min-w-52 rounded-[var(--radius-frame)] border border-line bg-surface px-3 py-2 text-sm">
            <div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{s.name}</span>
              <span className={`size-2 shrink-0 rounded-full ${s.status === "ok" ? "bg-preview" : s.status === "error" ? "bg-onair" : s.status === "missing_credentials" ? "bg-cue" : "bg-ink/20"}`} /></div>
            <div className="text-xs text-muted">{s.status === "missing_credentials" ? "Falta credencial" : s.status === "manual" ? "Importação manual" : s.status === "error" ? "Erro na última coleta" : s.last_run_at ? `${s.items_last_run} itens · ${ago(s.last_run_at)}` : "Ainda não coletada"}</div>
            {s.last_error && <div className="line-clamp-1 text-xs text-onair" title={s.last_error}>{s.last_error}</div>}
          </div>
        ))}
      </section>

      <div className="flex flex-wrap gap-2">
        <Input className="w-64" placeholder="Buscar" value={f.q} onChange={(e) => { setF({ ...f, q: e.target.value }); setOffset(0); }} />
        <Select className="w-44" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} aria-label="Status"><option value="">Todos</option>{Object.entries(TSTATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
        <Select className="w-44" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} aria-label="Categoria"><option value="">Todas as categorias</option>{cats?.map((c: string) => <option key={c}>{c}</option>)}</Select>
        <Select className="w-44" value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value })} aria-label="Ordenar"><option value="score">Maior potencial</option><option value="recent">Mais recentes</option><option value="popularity">Mais populares</option></Select>
      </div>

      {!data ? <Loading /> : data.items.length === 0 ? (
        <Empty title="Nenhuma tendência ainda" action={<Button onClick={() => setImporting(true)}>Importar tendências</Button>}>
          Clique em Pesquisar agora para coletar do Google Trends, Google Notícias, YouTube e Reddit, ou importe as que você viu no TikTok Creative Center e no Instagram.
        </Empty>
      ) : (
        <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
          <Table head={["Tendência", "Status", "Potencial", "Categoria", "Fontes", "Visto"]}>
            {data.items.map((t: any) => (
              <tr key={t.id} className="cursor-pointer hover:bg-paper/60" onClick={() => setOpen(t.id)}>
                <td className="max-w-md"><div className="font-medium">{t.name}</div>{t.analysis?.why && <div className="line-clamp-1 text-xs text-muted">{t.analysis.why}</div>}</td>
                <td><Pill tone={TSTATUS[t.status]?.tone}>{TSTATUS[t.status]?.label}</Pill></td>
                <td><ScoreBar v={t.score} /></td>
                <td className="text-muted">{t.category || "—"}</td>
                <td className="text-xs text-muted">{(t.sources_seen || []).length}</td>
                <td className="whitespace-nowrap text-xs text-muted">{ago(t.last_seen_at)}</td>
              </tr>
            ))}
          </Table>
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </div>
      )}
      <TrendDetail id={open} onClose={() => setOpen(null)} />
      <ImportModal open={importing} onClose={() => setImporting(false)} onDone={() => { mutate(); ms(); }} sources={sources || []} />
    </div>
  );
}

function ScoreBar({ v }: { v: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-ink/8"><div className="h-full rounded-full bg-reel" style={{ width: `${Math.round((v || 0) * 100)}%` }} /></div>
      <span className="num text-xs text-muted">{Math.round((v || 0) * 100)}</span>
    </div>
  );
}

function TrendDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data } = useSWR(id ? `/trends/${id}` : null);
  const { data: channels } = useSWR(id ? "/channels" : null);
  const [ch, setCh] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal open={!!id} onClose={onClose} title={data?.name || "Tendência"} wide
      footer={<>
        <Select className="w-56" value={ch} onChange={(e) => setCh(e.target.value)} aria-label="Canal"><option value="">Escolha o canal…</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Button variant="primary" disabled={!ch} busy={!!busy} onClick={() => run("g", async () => { await api("/ideas/generate", { body: { channel_id: +ch, trend_ids: [id], count: 5 } }); onClose(); }, "5 ideias geradas a partir da tendência")}>Gerar ideias</Button>
      </>}>
      {!data ? <Loading /> : (
        <div className="space-y-4 text-sm">
          {data.description && <p>{data.description}</p>}
          <div className="flex flex-wrap gap-4 text-muted">
            <span>Descoberta {day(data.discovered_at)}</span><span>Visto {data.times_seen}×</span><span>{data.region} · {data.language}</span>
            {data.url && <a className="text-reel" href={data.url} target="_blank" rel="noreferrer">Referência</a>}
            {data.is_simulated && <Simulated />}
          </div>
          {data.analysis?.why && <div className="rounded-md bg-paper p-3"><strong>Por que chama atenção:</strong> {data.analysis.why}
            {data.analysis.adaptable_formats && <div className="mt-1 text-muted">Formatos adaptáveis: {data.analysis.adaptable_formats.join(", ")}</div>}
            {data.analysis.sensitive && <div className="mt-1 text-onair">Tema sensível: excluído da geração automática.</div>}
            {data.analysis.simulated && <div className="mt-1"><Simulated /></div>}</div>}
          <div><div className="mb-1 font-medium">Evolução</div>
            {data.snapshots.length > 1 ? <AreaSeries data={data.snapshots.map((s: any) => ({ t: day(s.captured_at), v: Math.round(s.popularity_value * 100) }))} x="t" y="v" height={140} />
              : <p className="text-muted">Aparece após mais de uma coleta.</p>}</div>
          {data.popularity?.views != null && <p className="text-muted">Visualizações na fonte: {int(data.popularity.views)}</p>}
          <div><div className="mb-1 font-medium">Ideias relacionadas</div>
            {data.ideas.length ? <ul className="list-disc pl-5">{data.ideas.map((i: any) => <li key={i.id}>{i.title}</li>)}</ul> : <p className="text-muted">Nenhuma ainda.</p>}</div>
        </div>
      )}
    </Modal>
  );
}

function ImportModal({ open, onClose, onDone, sources }: { open: boolean; onClose: () => void; onDone: () => void; sources: any[] }) {
  const [src, setSrc] = useState("tiktok-creative-center");
  const [text, setText] = useState("");
  const { busy, run } = useAction();
  const items = text.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => { const [name, category, popularity] = l.split(";").map((x) => x?.trim()); return { name, category: category || null, popularity: +(popularity || 0) }; });
  return (
    <Modal open={open} onClose={onClose} title="Importar tendências" footer={<Button variant="primary" disabled={!items.length} busy={!!busy} onClick={() => run("i", async () => {
      const r = await api("/trends/import", { body: { source_key: src, items } }); setText(""); onDone(); onClose(); return r; }, `${items.length} tendência(s) importada(s)`)}>Importar {items.length || ""}</Button>}>
      <div className="space-y-4">
        <p className="text-sm text-muted">TikTok Creative Center e as tendências do Instagram não têm API pública oficial. Copie o que encontrar por lá e cole aqui.</p>
        <Field label="Fonte"><Select value={src} onChange={(e) => setSrc(e.target.value)}>{sources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</Select></Field>
        <Field label="Tendências" hint="Uma por linha. Opcional: nome; categoria; popularidade"><Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder={"#desafiodoespelho; humor; 120000\nPOV: primeiro dia no trabalho"} /></Field>
      </div>
    </Modal>
  );
}
