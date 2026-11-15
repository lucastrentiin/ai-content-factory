"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Pill, Select, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";

const FORMAT: Record<string, string> = { sequential: "Série contínua", anthology: "Antologia", miniseries: "Minissérie", novela: "Novela curta" };

export default function Series() {
  const { data: series, mutate } = useSWR("/series");
  const { data: universes, mutate: mu } = useSWR("/universes");
  const { data: channels } = useSWR("/channels");
  const { data: engines } = useSWR("/engines");
  const [ns, setNs] = useState(false);
  const [nu, setNu] = useState(false);
  return (
    <div className="space-y-8">
      <PageHeader title="Séries e universos" description="Universos agrupam personagens, cenários e histórias. Séries mantêm continuidade entre episódios, e cada episódio precisa funcionar para quem chega agora."
        actions={<><Button onClick={() => setNu(true)}>Novo universo</Button><Button variant="primary" onClick={() => setNs(true)}>Nova série</Button></>} />
      <section>
        <h2 className="mb-3">Séries</h2>
        {!series ? <Loading /> : series.length === 0 ? <Empty title="Nenhuma série">Crie uma série ligada a um canal e ao motor Séries e Novelas. O planejador da fábrica produz o próximo episódio automaticamente.</Empty> : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {series.map((s: any) => (
              <Link key={s.id} href={`/series/${s.id}`} className="rounded-[var(--radius-frame)] border border-line bg-surface p-4 hover:border-reel/50">
                <div className="flex items-center justify-between"><span className="text-xs text-muted">{FORMAT[s.format]}</span><Pill tone={s.status === "active" ? "preview" : "neutral"}>{s.status === "active" ? "ativa" : s.status}</Pill></div>
                <h3 className="mt-1 font-display text-lg">{s.title}</h3>
                <p className="line-clamp-2 text-sm text-muted">{s.synopsis}</p>
                <div className="mt-2 text-xs text-muted">{s.episodes} episódio(s){s.episode_target && ` de ${s.episode_target}`}</div>
              </Link>
            ))}
          </div>
        )}
      </section>
      <section>
        <h2 className="mb-3">Universos</h2>
        {universes?.length === 0 && <p className="text-sm text-muted">Nenhum universo criado.</p>}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {universes?.map((u: any) => (
            <div key={u.id} className="rounded-[var(--radius-frame)] border border-line bg-surface p-4">
              <h3>{u.name}</h3><p className="line-clamp-3 text-sm text-muted">{u.description}</p>
              <div className="mt-2 text-xs text-muted">{u.characters} personagens · {u.series} séries{u.is_shared && " · compartilhado"}</div>
            </div>
          ))}
        </div>
      </section>
      <NewSeries open={ns} onClose={() => setNs(false)} onDone={mutate} universes={universes || []} channels={channels || []} engines={engines || []} />
      <NewUniverse open={nu} onClose={() => setNu(false)} onDone={mu} channels={channels || []} />
    </div>
  );
}

function NewSeries({ open, onClose, onDone, universes, channels, engines }: any) {
  const [f, setF] = useState<any>({ title: "", synopsis: "", format: "sequential", universe_id: "", channel_id: "", engine_id: "", episode_target: "", visual_style: "cartoon", tone: "" });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Nova série" wide footer={<Button variant="primary" disabled={!f.title || !f.channel_id || !f.engine_id} busy={!!busy} onClick={() => run("c", async () => {
      await api("/series", { body: { title: f.title, synopsis: f.synopsis, format: f.format, visual_style: f.visual_style, universe_id: f.universe_id ? +f.universe_id : null,
        channel_id: +f.channel_id, engine_id: +f.engine_id, episode_target: f.episode_target ? +f.episode_target : null, story_bible: { tone: f.tone } } }); onDone(); onClose();
    }, "Série criada")}>Criar série</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field className="sm:col-span-2" label="Título"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Premissa"><Textarea value={f.synopsis} onChange={(e) => setF({ ...f, synopsis: e.target.value })} /></Field>
        <Field label="Formato"><Select value={f.format} onChange={(e) => setF({ ...f, format: e.target.value })}>{Object.entries(FORMAT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Episódios previstos"><Input type="number" value={f.episode_target} onChange={(e) => setF({ ...f, episode_target: e.target.value })} placeholder="Aberto" /></Field>
        <Field label="Canal"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Escolha…</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Motor"><Select value={f.engine_id} onChange={(e) => setF({ ...f, engine_id: e.target.value })}><option value="">Escolha…</option>{engines.map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
        <Field label="Universo"><Select value={f.universe_id} onChange={(e) => setF({ ...f, universe_id: e.target.value })}><option value="">Nenhum</option>{universes.map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
        <Field label="Estilo visual"><Select value={f.visual_style} onChange={(e) => setF({ ...f, visual_style: e.target.value })}><option value="cartoon">Cartoon</option><option value="stickman">Stickman</option><option value="cinematic">Cinematográfico</option></Select></Field>
        <Field className="sm:col-span-2" label="Tom e regras da série"><Input value={f.tone} onChange={(e) => setF({ ...f, tone: e.target.value })} placeholder="Ex.: suspense leve, sem violência, cada episódio termina com gancho" /></Field>
      </div>
    </Modal>
  );
}

function NewUniverse({ open, onClose, onDone, channels }: any) {
  const [f, setF] = useState<any>({ name: "", description: "", lore: "", rules: "", channel_id: "", is_shared: false });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Novo universo" footer={<Button variant="primary" disabled={!f.name} busy={!!busy} onClick={() => run("u", async () => {
      await api("/universes", { body: { ...f, channel_id: f.channel_id ? +f.channel_id : null } }); onDone(); onClose(); }, "Universo criado")}>Criar universo</Button>}>
      <div className="space-y-4">
        <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Descrição"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Regras do universo" hint="O que é sempre verdade neste mundo"><Textarea value={f.rules} onChange={(e) => setF({ ...f, rules: e.target.value })} /></Field>
        <Field label="Canal (opcional)"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Nenhum</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
      </div>
    </Modal>
  );
}
