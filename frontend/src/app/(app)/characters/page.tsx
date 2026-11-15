"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Select, Textarea, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";

const ROLE: Record<string, string> = { main: "Principal", secondary: "Secundário", temporary: "Temporário", narrator: "Narrador" };

export default function Characters() {
  const [q, setQ] = useState("");
  const [channel, setChannel] = useState("");
  const [role, setRole] = useState("");
  const [creating, setCreating] = useState(false);
  const { data } = useSWR(`/characters${qs({ q, channel_id: channel, role_type: role, limit: 100 })}`);
  const { data: channels } = useSWR("/channels");
  return (
    <div className="space-y-5">
      <PageHeader title="Personagens" description="Fichas persistentes: a aparência e a voz de cada personagem são as mesmas em todos os vídeos e episódios."
        actions={<Button variant="primary" onClick={() => setCreating(true)}>Novo personagem</Button>} />
      <div className="flex flex-wrap gap-2">
        <Input className="w-56" placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select className="w-48" value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="Canal"><option value="">Todos os canais</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
        <Select className="w-40" value={role} onChange={(e) => setRole(e.target.value)} aria-label="Papel"><option value="">Todos os papéis</option>{Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Nenhum personagem" action={<Button onClick={() => setCreating(true)}>Criar personagem</Button>}>O Designer de Personagens cria fichas automaticamente quando um roteiro precisa de alguém novo.</Empty> : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {data.items.map((c: any) => {
            const img = c.assets.find((a: any) => a.kind === "preview")?.asset?.url;
            return (
              <Link key={c.id} href={`/characters/${c.id}`} className="overflow-hidden rounded-[var(--radius-frame)] border border-line bg-surface hover:border-reel/50">
                <div className="aspect-square bg-paper">{img && <img src={img} alt={`Folha de ${c.name}`} className="size-full object-cover" loading="lazy" />}</div>
                <div className="p-3">
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-muted">{ROLE[c.role_type]} · {c.appearance_count} vídeo(s){c.auto_created && " · criado pela IA"}</div>
                  <div className="truncate text-xs text-muted">{c.voice?.name || "sem voz definida"}</div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
      <NewCharacter open={creating} onClose={() => setCreating(false)} channels={channels || []} />
    </div>
  );
}

function NewCharacter({ open, onClose, channels }: any) {
  const router = useRouter();
  const [f, setF] = useState<any>({ name: "", role_type: "main", personality: "", identity: "", art_style: "cartoon", channel_id: "", gender: "female", hair: "long", outfit_color: "#3b82f6" });
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Novo personagem" wide footer={<Button variant="primary" disabled={!f.name} busy={!!busy} onClick={() => run("c", async () => {
      const c = await api("/characters", { body: { name: f.name, role_type: f.role_type, personality: f.personality, identity: f.identity, art_style: f.art_style,
        channel_id: f.channel_id ? +f.channel_id : null, visual_spec: { gender: f.gender, hair: f.hair, outfit_color: f.outfit_color } } });
      onClose(); router.push(`/characters/${c.id}`); }, "Personagem criado com folha de referência")}>Criar</Button>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Papel"><Select value={f.role_type} onChange={(e) => setF({ ...f, role_type: e.target.value })}>{Object.entries(ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field className="sm:col-span-2" label="Quem é"><Textarea value={f.identity} onChange={(e) => setF({ ...f, identity: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Personalidade"><Input value={f.personality} onChange={(e) => setF({ ...f, personality: e.target.value })} /></Field>
        <Field label="Estilo"><Select value={f.art_style} onChange={(e) => setF({ ...f, art_style: e.target.value })}><option value="cartoon">Cartoon</option><option value="stickman">Stickman</option></Select></Field>
        <Field label="Canal exclusivo"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Nenhum</option>{channels.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
        <Field label="Gênero (para voz e aparência)"><Select value={f.gender} onChange={(e) => setF({ ...f, gender: e.target.value })}><option value="female">Feminino</option><option value="male">Masculino</option><option value="neutral">Neutro</option></Select></Field>
        <Field label="Cabelo"><Select value={f.hair} onChange={(e) => setF({ ...f, hair: e.target.value })}>{["short", "long", "spiky", "bun", "curly", "bald", "ponytail"].map((h) => <option key={h}>{h}</option>)}</Select></Field>
        <Field label="Cor da roupa"><Input type="color" value={f.outfit_color} onChange={(e) => setF({ ...f, outfit_color: e.target.value })} className="h-9 p-1" /></Field>
      </div>
    </Modal>
  );
}
