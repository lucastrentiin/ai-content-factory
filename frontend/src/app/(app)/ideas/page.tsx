"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Pager, Pill, Select, Simulated, Textarea, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { usd } from "@/lib/format";

const CRIT: Record<string, string> = { attention: "Prende nos 2s", retention: "Retenção", shareability: "Compartilhamento", originality: "Originalidade",
  trend_fit: "Aderência à tendência", production_ease: "Facilidade", continuation: "Continuação", historical: "Histórico do canal" };
const ISTATUS: Record<string, { label: string; tone: any }> = { new: { label: "Nova", tone: "reel" }, approved: { label: "Aprovada", tone: "preview" },
  rejected: { label: "Rejeitada", tone: "neutral" }, in_production: { label: "Em produção", tone: "onair" }, produced: { label: "Produzida", tone: "preview" }, archived: { label: "Arquivada", tone: "neutral" } };

export default function Ideas() {
  const [f, setF] = useState({ status: "new,approved", channel_id: "", engine_id: "", q: "" });
  const [offset, setOffset] = useState(0);
  const [gen, setGen] = useState(false);
  const [create, setCreate] = useState(false);
  const [open, setOpen] = useState<any>(null);
  const { data, mutate } = useSWR(`/ideas${qs({ ...f, limit: 24, offset })}`);
  const { data: channels } = useSWR("/channels");
  const { data: engines } = useSWR("/engines");
  return (
    <div className="space-y-5">
      <PageHeader title="Banco de ideias" description="Ideias pontuadas por potencial de atenção, retenção, compartilhamento, originalidade, custo e pelo histórico real do canal."
        actions={<><Button onClick={() => setCreate(true)}>Nova ideia</Button><Button variant="primary" onClick={() => setGen(true)}>Gerar ideias</Button></>} />
      <div className="flex flex-wrap gap-2">
        <Input className="w-56" placeholder="Buscar" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        <Select className="w-44" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} aria-label="Status">
          <option value="new,approved">Disponíveis</option><option value="">Todas</option>{Object.entries(ISTATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
        <Select className="w-44" value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })} aria-label="Canal"><option value="">Todos os canais</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Select className="w-44" value={f.engine_id} onChange={(e) => setF({ ...f, engine_id: e.target.value })} aria-label="Motor"><option value="">Todos os motores</option>{engines?.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Nenhuma ideia" action={<Button variant="primary" onClick={() => setGen(true)}>Gerar ideias</Button>}>Gere ideias a partir das tendências ou escreva as suas.</Empty> : (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data.items.map((i: any) => (
              <button key={i.id} onClick={() => setOpen(i)} className="flex flex-col gap-2 rounded-[var(--radius-frame)] border border-line bg-surface p-4 text-left hover:border-reel/50">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium" style={{ color: i.engine?.color }}>{i.engine?.name}</span>
                  <span className="num font-display text-xl font-semibold">{Math.round(i.total_score * 100)}</span>
                </div>
                <div className="font-medium leading-snug">{i.title}</div>
                {i.hook && <p className="line-clamp-2 text-sm text-muted">“{i.hook}”</p>}
                <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Pill tone={ISTATUS[i.status]?.tone}>{ISTATUS[i.status]?.label}</Pill><span>{i.format} · {i.duration_s}s · {usd(i.est_cost_usd, 3)}</span>{i.is_simulated && <Simulated />}
                </div>
              </button>
            ))}
          </div>
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </>
      )}
      <GenerateModal open={gen} onClose={() => setGen(false)} channels={channels || []} engines={engines || []} onDone={mutate} />
      <CreateModal open={create} onClose={() => setCreate(false)} channels={channels || []} engines={engines || []} onDone={mutate} />
      <IdeaModal idea={open} onClose={() => setOpen(null)} onChanged={mutate} />
    </div>
  );
}

function IdeaModal({ idea, onClose, onChanged }: { idea: any; onClose: () => void; onChanged: () => void }) {
  const router = useRouter();
  const [variants, setVariants] = useState(1);
  const { busy, run } = useAction();
  if (!idea) return null;
  const set = (status: string) => run(status, async () => { await api(`/ideas/${idea.id}`, { method: "PATCH", body: { status } }); onChanged(); onClose(); }, status === "approved" ? "Ideia aprovada" : "Ideia atualizada");
  const canProduce = ["new", "approved"].includes(idea.status);
  return (
    <Modal open onClose={onClose} title={idea.title} wide footer={<>
      {idea.status !== "rejected" && canProduce && <Button onClick={() => set("rejected")} busy={busy === "rejected"}>Rejeitar</Button>}
      {idea.status === "new" && <Button onClick={() => set("approved")} busy={busy === "approved"}>Aprovar</Button>}
      {canProduce && <>
        <Select className="w-40" value={variants} onChange={(e) => setVariants(+e.target.value)} aria-label="Versões"><option value={1}>1 versão</option><option value={2}>2 versões (A/B)</option><option value={3}>3 versões</option></Select>
        <Button variant="primary" busy={busy === "p"} onClick={() => run("p", async () => {
          const r = await api(`/ideas/${idea.id}/produce`, { body: { variants } }); onClose(); router.push(variants > 1 ? "/production" : `/production/${r.production_ids[0]}`);
        }, "Enviada para produção")}>Produzir</Button>
      </>}
    </>}>
      <div className="space-y-4 text-sm">
        <p>{idea.description}</p>
        {idea.hook && <p><strong>Gancho:</strong> {idea.hook}</p>}
        <div className="flex flex-wrap gap-3 text-muted"><span>{idea.format}</span><span>{idea.visual_style}</span><span>{idea.duration_s}s</span><span>complexidade {idea.complexity}/3</span><span>custo estimado {usd(idea.est_cost_usd, 3)}</span>{idea.is_simulated && <Simulated />}</div>
        <div>
          <div className="mb-2 font-medium">Pontuação <span className="num">{Math.round(idea.total_score * 100)}</span></div>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {Object.entries(idea.scores || {}).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-40 shrink-0 text-muted">{CRIT[k] || k}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink/8"><div className="h-full bg-reel" style={{ width: `${(v as number) * 100}%` }} /></div>
                <span className="num w-8 text-right text-xs">{Math.round((v as number) * 100)}</span>
              </div>
            ))}
          </div>
          {idea.score_explanation?.historical?.reason && <p className="mt-2 text-xs text-muted">Histórico: {idea.score_explanation.historical.reason}.</p>}
          {idea.score_explanation?.rationale && <p className="mt-1 text-xs text-muted">{idea.score_explanation.rationale}</p>}
        </div>
        {idea.trends?.length > 0 && <p className="text-muted">Tendências: {idea.trends.map((t: any) => t.name).join(", ")}</p>}
        {idea.production_ids?.length > 0 && <p>Produções: {idea.production_ids.map((p: number) => <Link key={p} className="mr-2 text-reel" href={`/production/${p}`}>#{p}</Link>)}</p>}
      </div>
    </Modal>
  );
}

function GenerateModal({ open, onClose, channels, engines, onDone }: any) {
  const [f, setF] = useState({ channel_id: "", engine_id: "", count: 8 });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Gerar ideias" footer={<Button variant="primary" disabled={!f.channel_id} busy={!!busy} onClick={() => run("g", async () => {
      const r = await api("/ideas/generate", { body: { channel_id: +f.channel_id, engine_id: f.engine_id ? +f.engine_id : null, count: f.count } }); onDone(); onClose(); return r;
    }, "Ideias geradas e pontuadas")}>Gerar {f.count} ideias</Button>}>
      <div className="space-y-4">
        <Field label="Canal"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Escolha…</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Motor" hint="Sem escolha, usa o motor de maior peso no canal."><Select value={f.engine_id} onChange={(e) => setF({ ...f, engine_id: e.target.value })}><option value="">Automático</option>{engines.filter((e: any) => e.is_active).map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
        <Field label="Quantidade"><Input type="number" min={1} max={50} value={f.count} onChange={(e) => setF({ ...f, count: +e.target.value })} /></Field>
      </div>
    </Modal>
  );
}

function CreateModal({ open, onClose, channels, engines, onDone }: any) {
  const [f, setF] = useState<any>({ title: "", description: "", hook: "", channel_id: "", engine_id: "", format: "narrated_story", visual_style: "cartoon", duration_s: 45 });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Nova ideia" wide footer={<Button variant="primary" disabled={!f.title || !f.channel_id || !f.engine_id} busy={!!busy} onClick={() => run("c", async () => {
      await api("/ideas", { body: { ...f, channel_id: +f.channel_id, engine_id: +f.engine_id, duration_s: +f.duration_s } }); onDone(); onClose();
    }, "Ideia criada e avaliada")}>Criar ideia</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field className="sm:col-span-2" label="Título"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Descrição"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Gancho (primeira frase)"><Input value={f.hook} onChange={(e) => setF({ ...f, hook: e.target.value })} /></Field>
        <Field label="Canal"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Escolha…</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Motor"><Select value={f.engine_id} onChange={(e) => setF({ ...f, engine_id: e.target.value })}><option value="">Escolha…</option>{engines.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
        <Field label="Formato"><Select value={f.format} onChange={(e) => setF({ ...f, format: e.target.value })}>{["narrated_story", "dialogue_story", "pov", "sketch", "episode", "explainer", "list", "analog_horror", "relato", "trend_remix"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Estilo visual"><Select value={f.visual_style} onChange={(e) => setF({ ...f, visual_style: e.target.value })}><option value="stickman">Stickman</option><option value="cartoon">Cartoon</option><option value="cinematic">Cinematográfico</option></Select></Field>
        <Field label="Duração (s)"><Input type="number" value={f.duration_s} onChange={(e) => setF({ ...f, duration_s: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
