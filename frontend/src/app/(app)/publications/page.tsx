"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, Loading, Modal, PageHeader, Pager, Pill, Select, Table, Textarea, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { dt, int, PLATFORM, PUB_STATUS } from "@/lib/format";

export default function Publications() {
  const [status, setStatus] = useState("");
  const [platform, setPlatform] = useState("");
  const [offset, setOffset] = useState(0);
  const [edit, setEdit] = useState<any>(null);
  const [manual, setManual] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const key = `/publications${qs({ status, platform, limit: 30, offset })}`;
  const { data, mutate } = useSWR(key, { refreshInterval: 15000 });
  const { busy, run } = useAction();
  return (
    <div>
      <PageHeader title="Publicações" description="Conteúdos preparados para cada plataforma. Quando a API oficial não estiver autorizada, baixe o pacote e publique manualmente." />
      <div className="mb-4 flex flex-wrap gap-2">
        <Select className="w-52" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} aria-label="Status">
          <option value="">Todos os status</option>{Object.entries(PUB_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</Select>
        <Select className="w-52" value={platform} onChange={(e) => { setPlatform(e.target.value); setOffset(0); }} aria-label="Plataforma">
          <option value="">Todas as plataformas</option>{Object.entries(PLATFORM).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
      </div>
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Nenhuma publicação">Publicações são criadas automaticamente quando um vídeo passa pelo controle de qualidade.</Empty> : (
        <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
          <Table head={["", "Título", "Plataforma", "Status", "Data", "Resultados", ""]}>
            {data.items.map((p: any) => (
              <tr key={p.id}>
                <td className="w-12">{p.cover && <img src={p.cover.url} alt="" className="h-14 w-8 rounded object-cover" />}</td>
                <td className="max-w-xs"><Link href={`/production/${p.production_job_id}`} className="line-clamp-2 font-medium hover:text-reel">{p.title}</Link><div className="text-xs text-muted">{p.channel?.name} · {p.mode === "api" ? "API" : "assistida"}</div>
                  {p.last_error && <div className="line-clamp-1 text-xs text-onair" title={p.last_error}>{p.last_error}</div>}</td>
                <td>{PLATFORM[p.platform_key]}</td>
                <td><Pill tone={PUB_STATUS[p.status]?.tone}>{PUB_STATUS[p.status]?.label}</Pill></td>
                <td className="whitespace-nowrap text-muted">{dt(p.published_at || p.scheduled_at)}</td>
                <td className="num whitespace-nowrap text-muted">{p.metrics ? `${int(p.metrics.views)} views · ${int(p.metrics.likes)} curtidas` : "—"}</td>
                <td>
                  <div className="flex flex-wrap justify-end gap-1">
                    {p.url && <a href={p.url} target="_blank" rel="noreferrer"><Button size="sm" variant="quiet">Abrir</Button></a>}
                    {!["published", "cancelled", "publishing"].includes(p.status) && <>
                      <Button size="sm" onClick={() => setEdit(p)}>Editar</Button>
                      <Button size="sm" busy={busy === `n${p.id}`} onClick={() => run(`n${p.id}`, async () => { await api(`/publications/${p.id}/publish-now`, { method: "POST" }); mutate(); }, "Publicação enviada para a fila")}>Publicar agora</Button>
                    </>}
                    <a href={`/api/publications/${p.id}/export`}><Button size="sm" variant="quiet">Baixar pacote</Button></a>
                    {p.status !== "published" && p.status !== "cancelled" && <Button size="sm" variant="quiet" onClick={() => setManual(p)}>Marcar como publicado</Button>}
                    {p.status === "published" && <Button size="sm" variant="quiet" onClick={() => setMetrics(p)}>Registrar métricas</Button>}
                    {!["published", "cancelled"].includes(p.status) && <Button size="sm" variant="quiet" onClick={() => run(`c${p.id}`, async () => { await api(`/publications/${p.id}/cancel`, { method: "POST" }); mutate(); }, "Publicação cancelada")}>Cancelar</Button>}
                  </div>
                </td>
              </tr>
            ))}
          </Table>
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </div>
      )}
      <EditPub pub={edit} onClose={() => setEdit(null)} onSaved={mutate} />
      <ManualModal pub={manual} onClose={() => setManual(null)} onSaved={mutate} />
      <MetricsModal pub={metrics} onClose={() => setMetrics(null)} onSaved={mutate} />
    </div>
  );
}

function EditPub({ pub, onClose, onSaved }: { pub: any; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<any>(null);
  const { busy, run } = useAction();
  if (pub && (!f || f.id !== pub.id)) setF({ id: pub.id, title: pub.title, description: pub.description, hashtags: pub.hashtags.join(" "),
    scheduled_at: pub.scheduled_at ? new Date(pub.scheduled_at).toISOString().slice(0, 16) : "", privacy: pub.privacy });
  return (
    <Modal open={!!pub} onClose={onClose} title="Editar publicação" wide footer={<Button variant="primary" busy={!!busy} onClick={() => run("s", async () => {
      await api(`/publications/${pub.id}`, { method: "PATCH", body: { title: f.title, description: f.description, privacy: f.privacy,
        hashtags: f.hashtags.split(/\s+/).filter(Boolean), scheduled_at: f.scheduled_at ? new Date(f.scheduled_at).toISOString() : null } });
      onSaved(); onClose();
    }, "Publicação atualizada")}>Salvar</Button>}>
      {f && <div className="space-y-4">
        <Field label="Título"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label="Descrição"><Textarea rows={5} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="Hashtags" hint="Separadas por espaço"><Input value={f.hashtags} onChange={(e) => setF({ ...f, hashtags: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Data e hora"><Input type="datetime-local" value={f.scheduled_at} onChange={(e) => setF({ ...f, scheduled_at: e.target.value })} /></Field>
          <Field label="Privacidade" hint="TikTok sem app auditado só permite 'privado'."><Select value={f.privacy} onChange={(e) => setF({ ...f, privacy: e.target.value })}>
            <option value="public">Pública</option><option value="unlisted">Não listada</option><option value="private">Privada</option></Select></Field>
        </div>
      </div>}
    </Modal>
  );
}

function ManualModal({ pub, onClose, onSaved }: { pub: any; onClose: () => void; onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const { busy, run } = useAction();
  return (
    <Modal open={!!pub} onClose={onClose} title="Marcar como publicado" footer={<Button variant="primary" busy={!!busy} disabled={url.length < 8} onClick={() => run("m", async () => {
      await api(`/publications/${pub.id}/mark-published`, { body: { url } }); setUrl(""); onSaved(); onClose(); }, "Publicação registrada")}>Registrar</Button>}>
      <Field label="Link da publicação" hint="Necessário para acompanhar resultados."><Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" /></Field>
    </Modal>
  );
}

function MetricsModal({ pub, onClose, onSaved }: { pub: any; onClose: () => void; onSaved: () => void }) {
  const [m, setM] = useState<any>({ views: "", likes: "", comments: "", shares: "", saves: "", followers_gained: "", completion_rate: "" });
  const { busy, run } = useAction();
  const fields: [string, string][] = [["views", "Visualizações"], ["likes", "Curtidas"], ["comments", "Comentários"], ["shares", "Compartilhamentos"], ["saves", "Salvamentos"], ["followers_gained", "Seguidores ganhos"]];
  return (
    <Modal open={!!pub} onClose={onClose} title="Registrar métricas" footer={<Button variant="primary" busy={!!busy} disabled={m.views === ""} onClick={() => run("m", async () => {
      const body: any = {}; fields.forEach(([k]) => (body[k] = +(m[k] || 0)));
      if (m.completion_rate !== "") body.completion_rate = +m.completion_rate / 100;
      await api(`/publications/${pub.id}/metrics`, { body }); onSaved(); onClose(); }, "Métricas registradas")}>Salvar</Button>}>
      <p className="mb-3 text-sm text-muted">Use quando a plataforma não estiver conectada por API. As métricas entram no aprendizado da fábrica.</p>
      <div className="grid grid-cols-2 gap-3">
        {fields.map(([k, l]) => <Field key={k} label={l}><Input type="number" min={0} value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })} /></Field>)}
        <Field label="Taxa de conclusão (%)"><Input type="number" min={0} max={100} value={m.completion_rate} onChange={(e) => setM({ ...m, completion_rate: e.target.value })} /></Field>
      </div>
    </Modal>
  );
}
