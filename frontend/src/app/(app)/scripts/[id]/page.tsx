"use client";
import Link from "next/link";
import { use, useState } from "react";
import useSWR from "swr";
import { Button, Field, Input, JsonField, Loading, Panel, Select, Simulated, Tabs, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dt } from "@/lib/format";

export default function ScriptEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, mutate } = useSWR(`/scripts/${id}`);
  const [sel, setSel] = useState<number | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [mode, setMode] = useState<"scenes" | "json">("scenes");
  const [jsonOk, setJsonOk] = useState(true);
  const [notes, setNotes] = useState("");
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  const version = data.versions.find((v: any) => v.version === (sel ?? data.current_version)) || data.versions[0];
  if (version && (!draft || draft.__v !== version.id)) setDraft({ ...structuredClone(version.content), __v: version.id });
  const scenes = draft?.scenes || [];
  const updScene = (i: number, patch: any) => setDraft({ ...draft, scenes: scenes.map((s: any, k: number) => (k === i ? { ...s, ...patch } : s)) });
  const save = () => run("s", async () => {
    const { __v, ...content } = draft; await api(`/scripts/${id}/versions`, { body: { content, notes } }); setSel(null); setDraft(null); setNotes(""); await mutate();
  }, "Nova versão salva");
  return (
    <div className="space-y-5">
      <div>
        <Link href="/scripts" className="text-sm text-muted hover:text-ink">Roteiros</Link>
        <h1 className="mt-1">{data.title}</h1>
        <div className="mt-1 text-sm text-muted">{data.production_ids.map((p: number) => <Link key={p} className="mr-2 text-reel" href={`/production/${p}`}>Produção #{p}</Link>)}</div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="space-y-4">
          <Tabs value={mode} onChange={setMode} items={[{ value: "scenes", label: "Cenas" }, { value: "json", label: "Estrutura completa (JSON)" }]} />
          {mode === "scenes" ? (
            <>
              <Panel>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field className="sm:col-span-2" label="Título"><Input value={draft?.title || ""} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></Field>
                  <Field className="sm:col-span-2" label="Sinopse"><Textarea value={draft?.synopsis || ""} onChange={(e) => setDraft({ ...draft, synopsis: e.target.value })} /></Field>
                  <Field label="Gancho"><Input value={draft?.hook || ""} onChange={(e) => setDraft({ ...draft, hook: e.target.value })} /></Field>
                  <Field label="Encerramento"><Input value={draft?.closing || ""} onChange={(e) => setDraft({ ...draft, closing: e.target.value })} /></Field>
                </div>
              </Panel>
              {scenes.map((s: any, i: number) => (
                <Panel key={i} title={`Cena ${i + 1} · ${s.title}`} actions={<Button size="sm" variant="quiet" disabled={scenes.length < 2} onClick={() => setDraft({ ...draft, scenes: scenes.filter((_: any, k: number) => k !== i).map((x: any, k: number) => ({ ...x, index: k })) })}>Remover</Button>}>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field className="sm:col-span-3" label="Narração"><Textarea rows={2} value={s.narration} onChange={(e) => updScene(i, { narration: e.target.value })} /></Field>
                    <Field className="sm:col-span-3" label="Diálogos" hint="Nome: fala (uma por linha)">
                      <Textarea rows={3} value={s.dialogue.map((d: any) => `${d.character}: ${d.text}`).join("\n")}
                        onChange={(e) => updScene(i, { dialogue: e.target.value.split("\n").map((l) => { const [c, ...r] = l.split(":"); return { character: c.trim(), text: r.join(":").trim(), emotion: s.dialogue.find((d: any) => d.character === c.trim())?.emotion || "neutral" }; }).filter((d) => d.character) })} />
                    </Field>
                    <Field label="Cenário"><Select value={s.location} onChange={(e) => updScene(i, { location: e.target.value })}>{draft.locations.map((l: any) => <option key={l.name}>{l.name}</option>)}</Select></Field>
                    <Field label="Câmera"><Select value={s.camera} onChange={(e) => updScene(i, { camera: e.target.value })}>{["static", "zoom_in", "zoom_out", "slow_zoom", "pan_left", "pan_right", "shake"].map((c) => <option key={c}>{c}</option>)}</Select></Field>
                    <Field label="Texto na tela"><Input value={s.on_screen_text} onChange={(e) => updScene(i, { on_screen_text: e.target.value })} /></Field>
                    <Field className="sm:col-span-3" label="Descrição visual"><Textarea rows={2} value={s.visual_description} onChange={(e) => updScene(i, { visual_description: e.target.value })} /></Field>
                  </div>
                </Panel>
              ))}
              <Button onClick={() => setDraft({ ...draft, scenes: [...scenes, { index: scenes.length, title: `Cena ${scenes.length + 1}`, location: draft.locations[0]?.name, narration: "", dialogue: [], characters: [], camera: "static", transition: "cut", sfx: [], on_screen_text: "", visual_description: "", emotion: "neutral" }] })}>Adicionar cena</Button>
            </>
          ) : draft && <JsonField key={draft.__v} rows={28} value={(({ __v, ...c }) => c)(draft)} onChange={(v, ok) => { setJsonOk(ok); if (ok) setDraft({ ...v, __v: draft.__v }); }} />}
          <div className="flex flex-wrap items-end gap-3 border-t border-line pt-4">
            <Field className="min-w-64 flex-1" label="Notas da versão"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="O que mudou" /></Field>
            <Button variant="primary" disabled={!jsonOk} busy={busy === "s"} onClick={save}>Salvar como nova versão</Button>
          </div>
          <p className="text-xs text-muted">Para aplicar no vídeo, abra a produção e reprocesse a partir de Personagens. Cenas sem alteração reaproveitam o render.</p>
        </div>
        <aside>
          <h2 className="mb-2">Versões</h2>
          <ul className="space-y-1.5">
            {data.versions.map((v: any) => (
              <li key={v.id}>
                <button onClick={() => { setSel(v.version); setDraft(null); }} className={`w-full rounded-md border px-3 py-2 text-left text-sm ${v.version === (sel ?? data.current_version) ? "border-reel bg-reel-soft" : "border-line bg-surface"}`}>
                  <div className="flex justify-between"><span className="font-medium">v{v.version}{v.version === data.current_version && " · atual"}</span>{v.is_simulated && <Simulated />}</div>
                  <div className="text-xs text-muted">{v.created_by} · {dt(v.created_at)}</div>
                  {v.notes && <div className="text-xs">{v.notes}</div>}
                </button>
                {v.version !== data.current_version && v.version === sel && (
                  <Button size="sm" className="mt-1" onClick={() => run("r", async () => { await api(`/scripts/${id}/versions/${v.version}/restore`, { method: "POST" }); setSel(null); setDraft(null); mutate(); }, `v${v.version} restaurada`)}>Restaurar esta versão</Button>
                )}
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}
