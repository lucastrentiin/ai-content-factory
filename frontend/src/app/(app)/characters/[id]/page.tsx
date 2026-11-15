"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";
import { Button, Field, Input, Loading, Panel, Select, Textarea, Toggle, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { day } from "@/lib/format";

const ROLE: Record<string, string> = { main: "Principal", secondary: "Secundário", temporary: "Temporário", narrator: "Narrador" };
const HAIR = ["short", "long", "spiky", "bun", "curly", "bald", "ponytail"];
const ACC = ["glasses", "hat", "scarf", "backpack", "bow"];
const ACC_PT: Record<string, string> = { glasses: "óculos", hat: "chapéu", scarf: "cachecol", backpack: "mochila", bow: "laço" };

export default function CharacterPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: c, mutate } = useSWR(`/characters/${id}`);
  const { data: voices } = useSWR("/voices");
  const { data: all } = useSWR("/characters?limit=200");
  const [f, setF] = useState<any>(null);
  const [rel, setRel] = useState({ other: "", type: "" });
  const { busy, run } = useAction();
  if (!c) return <Loading />;
  if (!f || f.__id !== c.id) setF({ ...c, catchphrases: (c.catchphrases || []).join("\n"), __id: c.id });
  if (!f) return null;
  const spec = f.visual_spec || {};
  const setSpec = (k: string, v: any) => setF({ ...f, visual_spec: { ...spec, [k]: v } });
  const preview = c.assets.find((a: any) => a.kind === "preview")?.asset;
  const save = () => run("s", async () => {
    await api(`/characters/${id}`, { method: "PATCH", body: { name: f.name, role_type: f.role_type, identity: f.identity, personality: f.personality, backstory: f.backstory,
      physical_description: f.physical_description, speech_style: f.speech_style, voice_tone: f.voice_tone, accent: f.accent, behaviors: f.behaviors,
      voice_id: f.voice_id ? +f.voice_id : null, is_shared: f.is_shared, visual_spec: f.visual_spec, catchphrases: f.catchphrases.split("\n").map((x: string) => x.trim()).filter(Boolean) } });
    setF(null); mutate();
  }, "Ficha salva");
  return (
    <div className="space-y-6">
      <div>
        <Link href="/characters" className="text-sm text-muted hover:text-ink">Personagens</Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <h1>{c.name}</h1>
          <div className="flex gap-2">
            <Button variant="danger" onClick={() => confirm(`Excluir ${c.name}?`) && run("d", async () => { await api(`/characters/${id}`, { method: "DELETE" }); router.push("/characters"); }, "Personagem excluído")}>Excluir</Button>
            <Button variant="primary" busy={busy === "s"} onClick={save}>Salvar ficha</Button>
          </div>
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        <div className="space-y-4">
          <div className="overflow-hidden rounded-[var(--radius-frame)] border border-line bg-surface">{preview && <img src={preview.url} alt={`Folha de referência de ${c.name}`} className="w-full" />}</div>
          <p className="text-xs text-muted">A folha é regenerada quando a aparência muda. Atenção: mudar a aparência afeta a continuidade em novos vídeos.</p>
          <Panel title="Aparência">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Estilo"><Select value={spec.style} onChange={(e) => setSpec("style", e.target.value)}><option value="cartoon">Cartoon</option><option value="stickman">Stickman</option></Select></Field>
              <Field label="Cabelo"><Select value={spec.hair} onChange={(e) => setSpec("hair", e.target.value)}>{HAIR.map((h) => <option key={h}>{h}</option>)}</Select></Field>
              {[["outfit_color", "Roupa"], ["pants_color", "Calça"], ["skin_tone", "Pele"], ["hair_color", "Cor do cabelo"]].map(([k, l]) => (
                <Field key={k} label={l}><Input type="color" className="h-9 p-1" value={spec[k] || "#888888"} onChange={(e) => setSpec(k, e.target.value)} /></Field>
              ))}
              <Field label="Altura"><Input type="number" step={0.05} min={0.6} max={1.3} value={spec.height ?? 1} onChange={(e) => setSpec("height", +e.target.value)} /></Field>
              <Field label="Gênero"><Select value={spec.gender || "neutral"} onChange={(e) => setSpec("gender", e.target.value)}><option value="female">Feminino</option><option value="male">Masculino</option><option value="neutral">Neutro</option></Select></Field>
            </div>
            <div className="mt-3 flex flex-wrap gap-3 text-sm">
              {ACC.map((a) => (
                <label key={a} className="flex items-center gap-1.5"><input type="checkbox" checked={(spec.accessories || []).includes(a)}
                  onChange={(e) => setSpec("accessories", e.target.checked ? [...(spec.accessories || []), a] : (spec.accessories || []).filter((x: string) => x !== a))} />{ACC_PT[a]}</label>
              ))}
            </div>
            <Field className="mt-3" label="Âncora para geradores de imagem" hint="Usada nos prompts para manter a aparência em imagens por IA."><Textarea rows={2} value={spec.prompt_anchor || ""} onChange={(e) => setSpec("prompt_anchor", e.target.value)} /></Field>
          </Panel>
          <Panel title="Imagens de referência">
            <div className="grid grid-cols-3 gap-2">{c.assets.filter((a: any) => a.kind === "reference").map((a: any) => <img key={a.id} src={a.asset.url} alt={a.label} className="aspect-square rounded object-cover" />)}</div>
            <label className="mt-3 inline-flex cursor-pointer items-center text-sm font-medium text-reel">
              Enviar imagem
              <input type="file" accept="image/*" className="sr-only" onChange={(e) => { const file = e.target.files?.[0]; if (!file) return; const fd = new FormData(); fd.append("file", file);
                run("u", async () => { await api(`/characters/${id}/references`, { form: fd }); mutate(); }, "Referência adicionada"); }} />
            </label>
          </Panel>
        </div>
        <div className="space-y-6">
          <Panel title="Identidade e personalidade">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
              <Field label="Papel"><Select value={f.role_type} onChange={(e) => setF({ ...f, role_type: e.target.value })}>{Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
              <Field className="sm:col-span-2" label="Quem é"><Textarea value={f.identity} onChange={(e) => setF({ ...f, identity: e.target.value })} /></Field>
              <Field className="sm:col-span-2" label="Personalidade"><Textarea value={f.personality} onChange={(e) => setF({ ...f, personality: e.target.value })} /></Field>
              <Field className="sm:col-span-2" label="História"><Textarea value={f.backstory} onChange={(e) => setF({ ...f, backstory: e.target.value })} /></Field>
              <Field label="Jeito de falar"><Input value={f.speech_style} onChange={(e) => setF({ ...f, speech_style: e.target.value })} /></Field>
              <Field label="Comportamentos"><Input value={f.behaviors} onChange={(e) => setF({ ...f, behaviors: e.target.value })} /></Field>
              <Field className="sm:col-span-2" label="Bordões" hint="Um por linha"><Textarea rows={2} value={f.catchphrases} onChange={(e) => setF({ ...f, catchphrases: e.target.value })} /></Field>
              <Toggle checked={!!f.is_shared} onChange={(v) => setF({ ...f, is_shared: v })} label="Pode aparecer em outros canais e universos" />
            </div>
          </Panel>
          <Panel title="Voz">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field className="sm:col-span-3" label="Voz associada"><Select value={f.voice_id || ""} onChange={(e) => setF({ ...f, voice_id: e.target.value })}><option value="">Escolhida automaticamente</option>
                {voices?.map((v: any) => <option key={v.id} value={v.id}>{v.name} ({v.provider_key}){!v.provider_available && " — provedor indisponível"}</option>)}</Select></Field>
              <Field label="Tom de voz"><Input value={f.voice_tone} onChange={(e) => setF({ ...f, voice_tone: e.target.value })} /></Field>
              <Field label="Sotaque"><Input value={f.accent} onChange={(e) => setF({ ...f, accent: e.target.value })} /></Field>
            </div>
            {c.voice?.sample && <audio controls src={c.voice.sample.url} className="mt-3 h-8" />}
          </Panel>
          <Panel title="Relações">
            <ul className="mb-3 space-y-1 text-sm">{c.relationships.map((r: any) => (
              <li key={r.id} className="flex justify-between"><span>{r.relation_type} — <Link href={`/characters/${r.other.id}`} className="text-reel">{r.other.name}</Link></span>
                <Button size="sm" variant="quiet" onClick={() => run("rd", async () => { await api(`/relationships/${r.id}`, { method: "DELETE" }); mutate(); })}>Remover</Button></li>))}
              {c.relationships.length === 0 && <li className="text-muted">Nenhuma relação.</li>}</ul>
            <div className="flex flex-wrap gap-2">
              <Select className="w-48" value={rel.other} onChange={(e) => setRel({ ...rel, other: e.target.value })} aria-label="Personagem"><option value="">Personagem…</option>{all?.items?.filter((x: any) => x.id !== c.id).map((x: any) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>
              <Input className="w-40" placeholder="ex.: irmã, rival" value={rel.type} onChange={(e) => setRel({ ...rel, type: e.target.value })} />
              <Button disabled={!rel.other || !rel.type} onClick={() => run("r", async () => { await api(`/characters/${id}/relationships`, { body: { other_character_id: +rel.other, relation_type: rel.type } }); setRel({ other: "", type: "" }); mutate(); }, "Relação adicionada")}>Adicionar</Button>
            </div>
          </Panel>
          <Panel title={`Aparições (${c.appearances.length})`} flush>
            <ul>{c.appearances.map((a: any) => (
              <li key={a.id} className="flex justify-between border-b border-line/70 px-4 py-2 text-sm last:border-0">
                <Link href={`/production/${a.production_job_id}`} className="truncate hover:text-reel">{a.title || `Produção #${a.production_job_id}`}</Link>
                <span className="shrink-0 text-muted">{a.scene_count} cenas · {a.lines_count} falas · {day(a.created_at)}</span></li>))}
              {c.appearances.length === 0 && <li className="px-4 py-3 text-sm text-muted">Ainda não apareceu em vídeos.</li>}</ul>
          </Panel>
        </div>
      </div>
    </div>
  );
}
