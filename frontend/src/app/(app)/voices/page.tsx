"use client";
import { useState } from "react";
import useSWR from "swr";
import { Button, Field, Input, Loading, Modal, PageHeader, Pill, Select, Table, Textarea, Toggle, useAction } from "@/components/ui";
import { api } from "@/lib/api";

export default function Voices() {
  const { data, mutate } = useSWR("/voices");
  const { data: providers } = useSWR("/providers");
  const [edit, setEdit] = useState<any>(null);
  const [testText, setTestText] = useState("Ninguém acreditou no que aconteceu naquela noite.");
  const [emotion, setEmotion] = useState("neutral");
  const [samples, setSamples] = useState<Record<number, string>>({});
  const { busy, run } = useAction();
  const tts = (providers || []).filter((p: any) => p.kind === "tts");
  return (
    <div className="space-y-5">
      <PageHeader title="Vozes" description="Biblioteca central de vozes. Cada personagem mantém a mesma voz entre episódios. Use apenas vozes de catálogo, próprias ou licenciadas: clonagem de pessoas reais sem autorização não é permitida."
        actions={<Button variant="primary" onClick={() => setEdit({ name: "", provider_key: "espeak", provider_voice_id: "", gender: "neutral", language: "pt-BR", settings: { speed: 1, pitch: 0 }, is_active: true })}>Nova voz</Button>} />
      <div className="flex flex-wrap items-end gap-3 rounded-[var(--radius-frame)] border border-line bg-surface p-4">
        <Field className="min-w-72 flex-1" label="Frase de teste"><Input value={testText} onChange={(e) => setTestText(e.target.value)} /></Field>
        <Field label="Emoção"><Select value={emotion} onChange={(e) => setEmotion(e.target.value)}>{["neutral", "happy", "sad", "angry", "scared", "surprised", "dread"].map((x) => <option key={x}>{x}</option>)}</Select></Field>
      </div>
      {!data ? <Loading /> : (
        <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
          <Table head={["Voz", "Provedor", "Gênero", "Personagens", "Amostra", ""]}>
            {data.map((v: any) => (
              <tr key={v.id} className={v.is_active ? "" : "opacity-50"}>
                <td><div className="font-medium">{v.name}</div><div className="text-xs text-muted">{v.provider_voice_id} · {v.language}</div></td>
                <td>{v.provider_key} {!v.provider_available && <Pill tone="cue">sem credencial</Pill>}</td>
                <td className="text-muted">{({ male: "masculina", female: "feminina", neutral: "neutra" } as any)[v.gender]}</td>
                <td className="max-w-48 truncate text-xs text-muted">{v.characters.join(", ") || "—"}</td>
                <td>{(samples[v.id] || v.sample?.url) && <audio controls src={samples[v.id] || v.sample.url} className="h-8 w-56" />}</td>
                <td><div className="flex justify-end gap-1">
                  <Button size="sm" busy={busy === `t${v.id}`} onClick={() => run(`t${v.id}`, async () => {
                    const r = await api(`/voices/${v.id}/test`, { body: { text: testText, emotion } }); setSamples((s) => ({ ...s, [v.id]: `${r.asset.url}?t=${Date.now()}` }));
                    if (r.fallback) throw new Error(`Provedor ${v.provider_key} indisponível: amostra gerada com ${r.provider}.`);
                  }, "Amostra gerada")}>Testar</Button>
                  <Button size="sm" variant="quiet" onClick={() => setEdit(v)}>Editar</Button></div></td>
              </tr>
            ))}
          </Table>
        </div>
      )}
      <VoiceModal voice={edit} onClose={() => setEdit(null)} onSaved={mutate} providers={tts} voices={data || []} />
    </div>
  );
}

function VoiceModal({ voice, onClose, onSaved, providers, voices }: any) {
  const [f, setF] = useState<any>(null);
  const { busy, run } = useAction();
  const { data: catalog } = useSWR(f && ["elevenlabs"].includes(f.provider_key) ? `/voices/catalog/${f.provider_key}` : null, { shouldRetryOnError: false });
  if (voice && (!f || f.__k !== (voice.id ?? "new"))) setF({ ...voice, __k: voice.id ?? "new" });
  if (!voice || !f) return null;
  const s = f.settings || {};
  return (
    <Modal open onClose={() => { setF(null); onClose(); }} title={voice.id ? "Editar voz" : "Nova voz"} wide footer={<>
      {voice.id && <Button variant="danger" onClick={() => confirm("Excluir esta voz?") && run("d", async () => { await api(`/voices/${voice.id}`, { method: "DELETE" }); onSaved(); setF(null); onClose(); }, "Voz excluída")}>Excluir</Button>}
      <Button variant="primary" disabled={!f.name || !f.provider_voice_id} busy={busy === "s"} onClick={() => run("s", async () => {
        const body = { name: f.name, provider_key: f.provider_key, provider_voice_id: f.provider_voice_id, language: f.language, accent: f.accent || "", gender: f.gender,
          description: f.description || "", settings: f.settings, is_active: f.is_active, license_note: f.license_note || "", fallback_voice_id: f.fallback_voice_id ? +f.fallback_voice_id : null };
        await api(voice.id ? `/voices/${voice.id}` : "/voices", { method: voice.id ? "PATCH" : "POST", body }); onSaved(); setF(null); onClose();
      }, "Voz salva")}>Salvar</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Provedor"><Select value={f.provider_key} onChange={(e) => setF({ ...f, provider_key: e.target.value })}>{providers.map((p: any) => <option key={p.key} value={p.key}>{p.name}</option>)}</Select></Field>
        <Field label="ID da voz no provedor" hint={f.provider_key === "espeak" ? "Ex.: pt-br, pt-br+f2, pt-br+m3" : f.provider_key === "openai-tts" ? "alloy, onyx, nova, shimmer, echo…" : "ID do catálogo do provedor"}>
          {catalog?.length ? <Select value={f.provider_voice_id} onChange={(e) => setF({ ...f, provider_voice_id: e.target.value })}><option value="">Escolha…</option>{catalog.map((v: any) => <option key={v.voice_id} value={v.voice_id}>{v.name}</option>)}</Select>
            : <Input value={f.provider_voice_id} onChange={(e) => setF({ ...f, provider_voice_id: e.target.value })} />}
        </Field>
        <Field label="Gênero"><Select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option value="female">Feminina</option><option value="male">Masculina</option><option value="neutral">Neutra</option></Select></Field>
        <Field label="Velocidade"><Input type="number" step={0.05} min={0.5} max={2} value={s.speed ?? 1} onChange={(e) => setF({ ...f, settings: { ...s, speed: +e.target.value } })} /></Field>
        <Field label="Tom (pitch)" hint="-10 a 10"><Input type="number" min={-10} max={10} value={s.pitch ?? 0} onChange={(e) => setF({ ...f, settings: { ...s, pitch: +e.target.value } })} /></Field>
        {f.provider_key === "elevenlabs" && <>
          <Field label="Estabilidade"><Input type="number" step={0.05} min={0} max={1} value={s.stability ?? 0.5} onChange={(e) => setF({ ...f, settings: { ...s, stability: +e.target.value } })} /></Field>
          <Field label="Estilo"><Input type="number" step={0.05} min={0} max={1} value={s.style ?? 0.2} onChange={(e) => setF({ ...f, settings: { ...s, style: +e.target.value } })} /></Field>
        </>}
        <Field label="Voz reserva" hint="Usada se o provedor falhar"><Select value={f.fallback_voice_id || ""} onChange={(e) => setF({ ...f, fallback_voice_id: e.target.value })}><option value="">Automática</option>{voices.filter((v: any) => v.id !== voice.id).map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}</Select></Field>
        <Field label="Idioma"><Input value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Licença / origem da voz"><Textarea rows={2} value={f.license_note || ""} onChange={(e) => setF({ ...f, license_note: e.target.value })} /></Field>
        <Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label="Ativa" />
      </div>
    </Modal>
  );
}
