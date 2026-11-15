"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Button, Field, Input, Modal, Select, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { usd } from "@/lib/format";

export function NewProduction({ open, onClose, channels, presetIdea }: { open: boolean; onClose: () => void; channels: any[]; presetIdea?: any }) {
  const router = useRouter();
  const { data: engines } = useSWR(open ? "/engines" : null);
  const { data: templates } = useSWR(open ? "/templates" : null);
  const [form, setForm] = useState<any>({ channel_id: "", engine_id: "", title: "", visual_style: "", target_duration_s: "", template_id: "", script: "" });
  const [estimate, setEstimate] = useState<any>(null);
  const { busy, run } = useAction();
  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));
  const canEstimate = form.channel_id && form.engine_id;
  return (
    <Modal open={open} onClose={onClose} title="Nova produção" wide
      footer={<>
        <Button disabled={!canEstimate} busy={busy === "est"} onClick={() => run("est", async () => setEstimate(await api("/costs/estimate", { body: {
          channel_id: +form.channel_id, engine_id: +form.engine_id, duration_s: +(form.target_duration_s || 45), visual_style: form.visual_style || null } })))}>Estimar custo</Button>
        <Button variant="primary" disabled={!form.channel_id || !form.engine_id} busy={busy === "go"} onClick={() => run("go", async () => {
          let manual: any = undefined;
          if (form.script.trim()) manual = toManualScript(form.title, form.script);
          const job = await api("/productions", { body: {
            channel_id: +form.channel_id, engine_id: +form.engine_id, title: form.title || null, visual_style: form.visual_style || null,
            target_duration_s: form.target_duration_s ? +form.target_duration_s : null, template_id: form.template_id ? +form.template_id : null,
            manual_script: manual, idempotency_key: `ui-${Date.now()}` } });
          onClose(); router.push(`/production/${job.id}`);
        }, "Produção iniciada")}>Iniciar produção</Button>
      </>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Canal"><Select value={form.channel_id} onChange={(e) => set("channel_id", e.target.value)}>
          <option value="">Escolha…</option>{channels.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Motor de conteúdo"><Select value={form.engine_id} onChange={(e) => set("engine_id", e.target.value)}>
          <option value="">Escolha…</option>{engines?.filter((e: any) => e.is_active).map((e: any) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select></Field>
        <Field label="Título provisório"><Input value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="Opcional" /></Field>
        <Field label="Estilo visual"><Select value={form.visual_style} onChange={(e) => set("visual_style", e.target.value)}>
          <option value="">Padrão do canal</option><option value="stickman">Stickman</option><option value="cartoon">Cartoon 2D</option><option value="cinematic">Cinematográfico (imagens por IA)</option></Select></Field>
        <Field label="Duração alvo (s)"><Input type="number" min={10} max={600} value={form.target_duration_s} onChange={(e) => set("target_duration_s", e.target.value)} placeholder="Padrão do canal" /></Field>
        <Field label="Template de edição"><Select value={form.template_id} onChange={(e) => set("template_id", e.target.value)}>
          <option value="">Padrão</option>{templates?.items?.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
        <Field className="sm:col-span-2" label="Roteiro próprio (opcional)" hint="Uma cena por parágrafo. Para falas use “Nome: texto”. Linhas sem nome viram narração. Deixe vazio para o roteirista escrever.">
          <Textarea rows={6} value={form.script} onChange={(e) => set("script", e.target.value)} placeholder={"Ninguém acreditou quando o elevador parou no 13º andar.\n\nAna: Esse prédio não tem 13º andar.\nLucas: Então onde a gente está?"} />
        </Field>
      </div>
      {estimate && (
        <div className="mt-4 rounded-md bg-paper px-3 py-2 text-sm">
          Estimativa: <strong className="num">{usd(estimate.total_usd, 3)}</strong> · {Object.entries(estimate.breakdown).map(([k, v]) => `${k} ${usd(v as number, 3)}`).join(" · ") || "somente provedores locais"} · modo visual {estimate.visual_mode}
        </div>
      )}
    </Modal>
  );
}

function toManualScript(title: string, text: string) {
  const scenes = text.split(/\n\s*\n/).map((block, i) => {
    const narration: string[] = [];
    const dialogue: any[] = [];
    block.split("\n").map((l) => l.trim()).filter(Boolean).forEach((l) => {
      const m = l.match(/^([A-ZÀ-Úa-zà-ú][\wÀ-ú ]{0,30}):\s*(.+)$/);
      if (m) dialogue.push({ character: m[1].trim(), text: m[2], emotion: "neutral" }); else narration.push(l);
    });
    return { index: i, narration: narration.join(" "), dialogue, camera: i === 0 ? "zoom_in" : "static" };
  });
  return { title: title || "Roteiro próprio", scenes };
}

