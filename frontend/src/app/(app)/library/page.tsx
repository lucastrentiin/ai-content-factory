"use client";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, JsonField, Loading, Modal, PageHeader, Pager, Pill, Select, Tabs, Textarea, Toggle, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { secs } from "@/lib/format";

const LIC: Record<string, string> = { internal_generated: "Gerado internamente", provider_commercial: "Uso comercial do provedor", cc0: "CC0", user_owned: "Próprio", licensed: "Licenciado", unknown: "Desconhecida" };

export default function Library() {
  const [tab, setTab] = useState<"assets" | "locations" | "templates">("assets");
  return (
    <div>
      <PageHeader title="Biblioteca" description="Imagens, vídeos, áudios, cenários e templates de edição reutilizáveis. Todo material guarda origem e licença, verificadas antes de publicar." />
      <Tabs value={tab} onChange={setTab} items={[{ value: "assets", label: "Arquivos" }, { value: "locations", label: "Cenários" }, { value: "templates", label: "Templates de edição" }]} />
      {tab === "assets" && <Assets />}
      {tab === "locations" && <Locations />}
      {tab === "templates" && <Templates />}
    </div>
  );
}

function Assets() {
  const [kind, setKind] = useState("image,video,music,sfx,audio");
  const [reusable, setReusable] = useState("true");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [up, setUp] = useState(false);
  const [sel, setSel] = useState<any>(null);
  const { data, mutate } = useSWR(`/assets${qs({ kind, q, reusable, limit: 48, offset })}`);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input className="w-56" placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select className="w-44" value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0); }} aria-label="Tipo">
          <option value="image,video,music,sfx,audio">Todos</option><option value="image">Imagens</option><option value="video">Vídeos</option><option value="audio">Áudios e falas</option><option value="music">Músicas</option><option value="sfx">Efeitos</option><option value="thumbnail">Capas</option></Select>
        <Select className="w-52" value={reusable} onChange={(e) => setReusable(e.target.value)} aria-label="Escopo"><option value="true">Materiais reutilizáveis</option><option value="">Inclui arquivos de produções</option></Select>
        <Button variant="primary" className="ml-auto" onClick={() => setUp(true)}>Enviar arquivo</Button>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Biblioteca vazia">Envie músicas, efeitos, imagens de referência ou fundos com direitos de uso.</Empty> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
            {data.items.map((a: any) => (
              <button key={a.id} onClick={() => setSel(a)} className="overflow-hidden rounded-[var(--radius-frame)] border border-line bg-surface text-left hover:border-reel/50">
                <div className="flex aspect-square items-center justify-center bg-paper text-xs text-muted">
                  {a.kind === "image" || a.kind === "thumbnail" ? <img src={a.url} alt={a.name} className="size-full object-cover" loading="lazy" />
                    : a.kind === "video" ? <video src={a.url} muted preload="metadata" className="size-full object-cover" /> : <span>{a.kind} · {secs(a.duration_s)}</span>}
                </div>
                <div className="p-2"><div className="truncate text-xs font-medium">{a.name}</div><div className="truncate text-[11px] text-muted">{LIC[a.license]}</div></div>
              </button>
            ))}
          </div>
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </>
      )}
      <Upload open={up} onClose={() => setUp(false)} onDone={mutate} />
      <AssetModal asset={sel} onClose={() => setSel(null)} onSaved={mutate} />
    </div>
  );
}

function Upload({ open, onClose, onDone }: any) {
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("image");
  const [license, setLicense] = useState("user_owned");
  const [tags, setTags] = useState("");
  const [note, setNote] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal open={open} onClose={onClose} title="Enviar arquivo" footer={<Button variant="primary" disabled={!file} busy={!!busy} onClick={() => run("u", async () => {
      const fd = new FormData(); fd.append("file", file!); fd.append("kind", kind); fd.append("license", license); fd.append("tags", tags); fd.append("license_note", note);
      await api("/assets", { form: fd }); setFile(null); onDone(); onClose(); }, "Arquivo enviado")}>Enviar</Button>}>
      <div className="space-y-4">
        <Field label="Arquivo" hint="Até 500 MB"><Input type="file" accept="image/*,video/*,audio/*" onChange={(e) => setFile(e.target.files?.[0] || null)} className="py-1.5" /></Field>
        <Field label="Tipo"><Select value={kind} onChange={(e) => setKind(e.target.value)}><option value="image">Imagem</option><option value="video">Vídeo</option><option value="music">Música</option><option value="sfx">Efeito sonoro</option><option value="audio">Áudio</option></Select></Field>
        <Field label="Licença" hint="Materiais com licença desconhecida são bloqueados no controle de qualidade."><Select value={license} onChange={(e) => setLicense(e.target.value)}>{Object.entries(LIC).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
        <Field label="Detalhes da licença"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ex.: comprado em…, autor…" /></Field>
        <Field label="Etiquetas" hint="Separadas por vírgula"><Input value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

function AssetModal({ asset, onClose, onSaved }: any) {
  const { busy, run } = useAction();
  const [lic, setLic] = useState<string | null>(null);
  if (!asset) return null;
  return (
    <Modal open onClose={() => { setLic(null); onClose(); }} title={asset.name} wide footer={<>
      <Button variant="danger" busy={busy === "d"} onClick={() => confirm("Excluir este arquivo?") && run("d", async () => { await api(`/assets/${asset.id}`, { method: "DELETE" }); onSaved(); onClose(); }, "Arquivo excluído")}>Excluir</Button>
      <a href={`${asset.url}?download=1`}><Button>Baixar</Button></a>
      <Button variant="primary" disabled={!lic} busy={busy === "s"} onClick={() => run("s", async () => { await api(`/assets/${asset.id}`, { method: "PATCH", body: { license: lic } }); onSaved(); onClose(); }, "Licença atualizada")}>Salvar licença</Button></>}>
      <div className="grid gap-4 sm:grid-cols-[1fr_220px]">
        <div className="flex max-h-[60vh] items-center justify-center rounded bg-paper">
          {["image", "thumbnail"].includes(asset.kind) ? <img src={asset.url} alt="" className="max-h-[60vh]" /> : asset.kind === "video" ? <video src={asset.url} controls className="max-h-[60vh]" /> : <audio src={asset.url} controls />}
        </div>
        <dl className="space-y-2 text-sm">
          <div><dt className="text-muted">Origem</dt><dd>{asset.origin}{asset.provider_key && ` · ${asset.provider_key}`}</dd></div>
          <div><dt className="text-muted">Licença</dt><dd><Select value={lic ?? asset.license} onChange={(e) => setLic(e.target.value)}>{Object.entries(LIC).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></dd></div>
          {asset.prompt && <div><dt className="text-muted">Prompt / texto</dt><dd className="line-clamp-6 text-xs">{asset.prompt}</dd></div>}
          <div><dt className="text-muted">Tamanho</dt><dd>{(asset.size_bytes / 1e6).toFixed(2)} MB{asset.width && ` · ${asset.width}×${asset.height}`}</dd></div>
          {asset.is_simulated && <Pill tone="cue">simulado</Pill>}
        </dl>
      </div>
    </Modal>
  );
}

function Locations() {
  const { data, mutate } = useSWR("/locations");
  const { data: channels } = useSWR("/channels");
  const [f, setF] = useState<any>(null);
  const { busy, run } = useAction();
  return (
    <div className="space-y-4">
      <div className="flex justify-between"><p className="max-w-2xl text-sm text-muted">Cenários são reaproveitados entre vídeos para manter a identidade visual. O Diretor de Arte cria novos quando um roteiro pede.</p>
        <Button variant="primary" onClick={() => setF({ name: "", description: "", setting_type: "room", time_of_day: "day", channel_id: "" })}>Novo cenário</Button></div>
      {!data ? <Loading /> : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {data.map((l: any) => (
            <button key={l.id} onClick={() => setF({ ...l, channel_id: l.channel_id || "" })} className="overflow-hidden rounded-[var(--radius-frame)] border border-line bg-surface text-left hover:border-reel/50">
              <div className="aspect-[9/16] bg-paper">{l.background && <img src={l.background.url} alt={l.name} className="size-full object-cover" loading="lazy" />}</div>
              <div className="p-2"><div className="truncate text-sm font-medium">{l.name}</div><div className="text-xs text-muted">{l.setting_type} · {l.time_of_day} · usado {l.reuse_count}×</div></div>
            </button>
          ))}
        </div>
      )}
      <Modal open={!!f} onClose={() => setF(null)} title={f?.id ? "Editar cenário" : "Novo cenário"} footer={f && <>
        {f.id && <Button variant="danger" onClick={() => run("d", async () => { await api(`/locations/${f.id}`, { method: "DELETE" }); mutate(); setF(null); }, "Cenário excluído")}>Excluir</Button>}
        <Button variant="primary" disabled={!f.name} busy={busy === "s"} onClick={() => run("s", async () => {
          const body = { name: f.name, description: f.description, setting_type: f.setting_type, time_of_day: f.time_of_day, channel_id: f.channel_id ? +f.channel_id : null, visual_prompt: f.visual_prompt || "" };
          await api(f.id ? `/locations/${f.id}` : "/locations", { method: f.id ? "PATCH" : "POST", body }); mutate(); setF(null); }, "Cenário salvo")}>Salvar</Button></>}>
        {f && <div className="grid gap-4 sm:grid-cols-2">
          <Field className="sm:col-span-2" label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Tipo"><Select value={f.setting_type} onChange={(e) => setF({ ...f, setting_type: e.target.value })}>{["room", "kitchen", "office", "school", "street", "city", "park", "forest", "beach", "abandoned", "lab", "space", "abstract"].map((s) => <option key={s}>{s}</option>)}</Select></Field>
          <Field label="Período"><Select value={f.time_of_day} onChange={(e) => setF({ ...f, time_of_day: e.target.value })}><option value="day">Dia</option><option value="sunset">Pôr do sol</option><option value="night">Noite</option></Select></Field>
          <Field className="sm:col-span-2" label="Canal"><Select value={f.channel_id} onChange={(e) => setF({ ...f, channel_id: e.target.value })}><option value="">Todos</option>{channels?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
          <Field className="sm:col-span-2" label="Descrição para geradores de imagem"><Textarea value={f.visual_prompt || ""} onChange={(e) => setF({ ...f, visual_prompt: e.target.value })} /></Field>
        </div>}
      </Modal>
    </div>
  );
}

function Templates() {
  const { data, mutate } = useSWR("/templates");
  const [f, setF] = useState<any>(null);
  const [ok, setOk] = useState(true);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  return (
    <div className="space-y-4">
      <div className="flex justify-between gap-4"><p className="max-w-2xl text-sm text-muted">Templates mudam legendas, fontes, cores, transições, música, volume, marca d'água e resolução sem alterar código. Só os campos informados substituem o padrão.</p>
        <Button variant="primary" onClick={() => setF({ name: "", description: "", config: {}, is_default: false })}>Novo template</Button></div>
      <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        {data.items.map((t: any) => (
          <button key={t.id} onClick={() => setF(t)} className="flex w-full items-center justify-between border-b border-line/70 px-4 py-3 text-left last:border-0 hover:bg-paper/60">
            <div><div className="font-medium">{t.name} {t.is_default && <Pill tone="reel">padrão</Pill>}</div><div className="text-sm text-muted">{t.description}</div></div>
            <span className="text-xs text-muted">{Object.keys(t.config).join(", ") || "sem alterações"}</span>
          </button>
        ))}
      </div>
      <Modal open={!!f} onClose={() => setF(null)} title={f?.id ? "Editar template" : "Novo template"} wide footer={f && <>
        {f.id && <Button variant="danger" onClick={() => run("d", async () => { await api(`/templates/${f.id}`, { method: "DELETE" }); mutate(); setF(null); }, "Template excluído")}>Excluir</Button>}
        <Button variant="primary" disabled={!f.name || !ok} busy={busy === "s"} onClick={() => run("s", async () => {
          await api(f.id ? `/templates/${f.id}` : "/templates", { method: f.id ? "PATCH" : "POST", body: { name: f.name, description: f.description, config: f.config, is_default: f.is_default } }); mutate(); setF(null); }, "Template salvo")}>Salvar</Button></>}>
        {f && <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Descrição"><Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          </div>
          <Toggle checked={f.is_default} onChange={(v) => setF({ ...f, is_default: v })} label="Usar como padrão" />
          <Field label="Configuração (sobrescreve o padrão)"><JsonField key={f.id ?? "new"} rows={12} value={f.config} onChange={(v, valid) => { setOk(valid); if (valid) setF({ ...f, config: v }); }} /></Field>
          <details className="text-sm"><summary className="cursor-pointer text-muted">Ver todos os campos e valores padrão</summary><pre className="mt-2 max-h-64 overflow-auto rounded bg-paper p-3 text-xs scroll-thin">{JSON.stringify(data.defaults, null, 2)}</pre></details>
        </div>}
      </Modal>
    </div>
  );
}
