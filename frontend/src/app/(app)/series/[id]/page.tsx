"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, Panel, Pill, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";

const EP: Record<string, { label: string; tone: any }> = { planned: { label: "Planejado", tone: "neutral" }, in_production: { label: "Em produção", tone: "onair" },
  produced: { label: "Produzido", tone: "preview" }, published: { label: "Publicado", tone: "reel" } };

export default function SeriesDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data, mutate } = useSWR(`/series/${id}`);
  const [newEp, setNewEp] = useState(false);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  const names: Record<number, string> = Object.fromEntries(data.characters.map((c: any) => [c.id, c.name]));
  return (
    <div className="space-y-6">
      <div>
        <Link href="/series" className="text-sm text-muted hover:text-ink">Séries</Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div><h1>{data.title}</h1><p className="mt-1 max-w-2xl text-sm text-muted">{data.synopsis}</p></div>
          <Button variant="primary" onClick={() => setNewEp(true)}>Planejar episódio</Button>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Panel title="Linha do tempo" flush>
          {data.episodes.length === 0 ? <div className="p-4"><Empty title="Nenhum episódio">Planeje o primeiro episódio ou deixe o planejador da fábrica criar.</Empty></div> : (
            <ol className="relative ml-6 border-l-2 border-line py-2">
              {data.episodes.map((e: any) => (
                <li key={e.id} className="relative py-3 pl-6 pr-4">
                  <span className={`absolute -left-[9px] top-4 size-4 rounded-full border-2 border-surface ${e.status === "produced" || e.status === "published" ? "bg-preview" : e.status === "in_production" ? "bg-onair" : "bg-line"}`} />
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3>Ep. {e.number} · {e.title}</h3>
                    <div className="flex items-center gap-2">
                      <Pill tone={EP[e.status]?.tone}>{EP[e.status]?.label}</Pill>
                      {e.production_job_id ? <Link className="text-sm text-reel" href={`/production/${e.production_job_id}`}>Abrir vídeo</Link>
                        : <Button size="sm" busy={busy === `p${e.id}`} onClick={() => run(`p${e.id}`, async () => { const r = await api(`/episodes/${e.id}/produce`, { method: "POST" }); router.push(`/production/${r.production_id}`); }, "Episódio em produção")}>Produzir</Button>}
                    </div>
                  </div>
                  {(e.summary || e.synopsis) && <p className="mt-1 line-clamp-3 text-sm text-muted">{e.summary || e.synopsis}</p>}
                  {e.hook_next && <p className="mt-1 text-sm"><span className="text-muted">Gancho:</span> {e.hook_next}</p>}
                </li>
              ))}
            </ol>
          )}
        </Panel>
        <div className="space-y-6">
          <Panel title="Elenco">
            {data.characters.length === 0 ? <p className="text-sm text-muted">Personagens aparecem aqui ao entrar em episódios ou ao serem ligados ao universo.</p> : (
              <ul className="space-y-2">{data.characters.map((c: any) => (
                <li key={c.id} className="flex justify-between text-sm"><Link className="font-medium hover:text-reel" href={`/characters/${c.id}`}>{c.name}</Link>
                  <span className="text-muted">{data.appearances.filter((a: any) => a.character_id === c.id).length} ep.</span></li>))}</ul>
            )}
          </Panel>
          <Panel title="Relações">
            {data.relationships.length === 0 ? <p className="text-sm text-muted">Sem relações cadastradas. Defina na ficha do personagem.</p> : (
              <ul className="space-y-1 text-sm">{data.relationships.map((r: any) => <li key={r.id}>{names[r.character_id]} <span className="text-muted">é {r.relation_type} de</span> {names[r.other_character_id] || `#${r.other_character_id}`}</li>)}</ul>
            )}
          </Panel>
          {data.universe && <Panel title={`Universo: ${data.universe.name}`}><p className="text-sm text-muted">{data.universe.rules || data.universe.description}</p></Panel>}
        </div>
      </div>
      <NewEpisode id={id} open={newEp} onClose={() => setNewEp(false)} onDone={mutate} />
    </div>
  );
}

function NewEpisode({ id, open, onClose, onDone }: { id: string; open: boolean; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ title: "", synopsis: "" });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Planejar episódio" footer={<Button variant="primary" disabled={!f.title} busy={!!busy} onClick={() => run("e", async () => {
      await api(`/series/${id}/episodes`, { body: f }); setF({ title: "", synopsis: "" }); onDone(); onClose(); }, "Episódio planejado")}>Planejar</Button>}>
      <div className="space-y-4">
        <Field label="Título"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="O que acontece" hint="O roteirista usa isto e o histórico dos episódios anteriores."><Textarea rows={5} value={f.synopsis} onChange={(e) => setF({ ...f, synopsis: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
