"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Pill, Select, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { PLATFORM } from "@/lib/format";

const MODE: Record<string, string> = { manual: "Manual", assisted: "Assistido", automatic: "Automático" };

export default function Channels() {
  const { data } = useSWR("/channels");
  const [open, setOpen] = useState(false);
  return (
    <div>
      <PageHeader title="Canais" description="Cada canal tem identidade, nicho, idioma, motores permitidos, personagens, frequência e contas conectadas."
        actions={<Button variant="primary" onClick={() => setOpen(true)}>Novo canal</Button>} />
      {!data ? <Loading /> : data.length === 0 ? <Empty title="Nenhum canal" action={<Button variant="primary" onClick={() => setOpen(true)}>Criar canal</Button>}>Comece criando um canal: a fábrica precisa saber para quem produz.</Empty> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((c: any) => (
            <Link key={c.id} href={`/channels/${c.id}`} className="rounded-[var(--radius-frame)] border border-line bg-surface p-4 hover:border-reel/50" style={{ borderLeft: `4px solid ${c.color}` }}>
              <div className="flex items-center justify-between"><h3 className="font-display text-lg">{c.name}</h3><Pill tone={c.autonomy_mode === "automatic" ? "onair" : c.autonomy_mode === "assisted" ? "cue" : "neutral"}>{MODE[c.autonomy_mode]}</Pill></div>
              <p className="line-clamp-2 text-sm text-muted">{c.niche || c.description}</p>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                <span>{c.videos_per_day} vídeo(s)/dia</span><span>{c.language}</span><span>{c.engines.filter((e: any) => e.is_enabled).length} motores</span>
                <span>{c.accounts.filter((a: any) => a.status === "connected").length}/{c.platforms.length} contas conectadas</span>
              </div>
              <div className="mt-2 flex gap-1.5">{c.platforms.map((p: string) => <span key={p} className="rounded bg-paper px-1.5 py-0.5 text-[11px]">{PLATFORM[p]}</span>)}</div>
            </Link>
          ))}
        </div>
      )}
      <NewChannel open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function NewChannel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [f, setF] = useState<any>({ name: "", niche: "", target_audience: "", language: "pt-BR", region: "BR", visual_style: "cartoon", autonomy_mode: "assisted", videos_per_day: 1, default_duration_s: 45, description: "" });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Novo canal" wide footer={<Button variant="primary" disabled={!f.name} busy={!!busy} onClick={() => run("c", async () => {
      const c = await api("/channels", { body: { ...f, videos_per_day: +f.videos_per_day, default_duration_s: +f.default_duration_s } }); onClose(); router.push(`/channels/${c.id}`); }, "Canal criado com todos os motores habilitados")}>Criar canal</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Nicho"><Input value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })} placeholder="Ex.: histórias de suspense animadas" /></Field>
        <Field className="sm:col-span-2" label="Público-alvo"><Input value={f.target_audience} onChange={(e) => setF({ ...f, target_audience: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Identidade e tom"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Idioma"><Select value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}><option value="pt-BR">Português (Brasil)</option><option value="en-US">Inglês (EUA)</option><option value="es-ES">Espanhol</option></Select></Field>
        <Field label="Estilo visual"><Select value={f.visual_style} onChange={(e) => setF({ ...f, visual_style: e.target.value })}><option value="cartoon">Cartoon 2D</option><option value="stickman">Stickman</option><option value="cinematic">Cinematográfico</option></Select></Field>
        <Field label="Autonomia" hint="Manual: você inicia cada etapa. Assistido: produz e aguarda aprovação. Automático: produz e publica."><Select value={f.autonomy_mode} onChange={(e) => setF({ ...f, autonomy_mode: e.target.value })}>{Object.entries(MODE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Vídeos por dia"><Input type="number" min={0} max={50} value={f.videos_per_day} onChange={(e) => setF({ ...f, videos_per_day: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
