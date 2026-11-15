"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, use, useEffect, useState } from "react";
import useSWR from "swr";
import { Button, Field, Input, Loading, Modal, Panel, Pill, Select, Textarea, Toggle, useAction, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { dt, PLATFORM } from "@/lib/format";

function ChannelPage({ id }: { id: string }) {
  const router = useRouter();
  const sp = useSearchParams();
  const toast = useToast();
  const { data: c, mutate } = useSWR(`/channels/${id}`);
  const { data: engines } = useSWR("/engines");
  const { data: templates } = useSWR("/templates");
  const { data: voices } = useSWR("/voices");
  const { data: platforms } = useSWR("/platforms");
  const [f, setF] = useState<any>(null);
  const [weights, setWeights] = useState<Record<number, { on: boolean; w: number }> | null>(null);
  const [acc, setAcc] = useState<any>(null);
  const { busy, run } = useAction();
  useEffect(() => {
    const o = sp.get("oauth");
    if (o) toast(o === "connected" ? "Conta conectada" : `Conexão não concluída (${o})`, o === "connected" ? "preview" : "onair");
  }, [sp, toast]);
  if (!c || !engines) return <Loading />;
  if (!f || f.__id !== c.id) setF({ ...c, preferred_hours: c.preferred_hours.join(", "), hashtags_base: (c.settings.hashtags_base || []).join(" "), watermark: c.settings.watermark || "", narrator_voice_id: c.settings.narrator_voice_id || "", __id: c.id });
  if (!weights || (weights as any).__id !== c.id) {
    const w: any = { __id: c.id }; engines.forEach((e: any) => { const l = c.engines.find((x: any) => x.engine_id === e.id); w[e.id] = { on: !!l?.is_enabled, w: l?.weight ?? 1 }; }); setWeights(w);
  }
  if (!f || !weights) return null;
  const total = engines.reduce((s: number, e: any) => s + (weights[e.id]?.on ? weights[e.id].w : 0), 0) || 1;
  const save = () => run("s", async () => {
    await api(`/channels/${id}`, { method: "PATCH", body: {
      name: f.name, description: f.description, identity: f.identity, niche: f.niche, target_audience: f.target_audience, language: f.language, visual_style: f.visual_style,
      color: f.color, autonomy_mode: f.autonomy_mode, require_approval: f.require_approval, videos_per_day: +f.videos_per_day, default_duration_s: +f.default_duration_s,
      preferred_hours: f.preferred_hours.split(",").map((h: string) => h.trim()).filter(Boolean), timezone: f.timezone, provider_strategy: f.provider_strategy,
      default_template_id: f.default_template_id ? +f.default_template_id : null, platforms: f.platforms, is_active: f.is_active,
      settings: { hashtags_base: f.hashtags_base.split(/\s+/).filter(Boolean).map((h: string) => h.replace(/^#/, "")), watermark: f.watermark,
        narrator_voice_id: f.narrator_voice_id ? +f.narrator_voice_id : null, auto_optimize: !!f.settings?.auto_optimize } } });
    await api(`/channels/${id}/engines`, { method: "PUT", body: engines.filter((e: any) => weights[e.id]?.on).map((e: any) => ({ engine_id: e.id, weight: +weights[e.id].w, is_enabled: true })) });
    setF(null); setWeights(null); mutate();
  }, "Canal salvo");
  const connect = (aid: number) => run(`c${aid}`, async () => { const r = await api(`/accounts/${aid}/connect`); window.location.href = r.auth_url; });
  return (
    <div className="space-y-6">
      <div>
        <Link href="/channels" className="text-sm text-muted hover:text-ink">Canais</Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <h1>{c.name}</h1>
          <div className="flex gap-2">
            <Button variant="danger" onClick={() => confirm(`Excluir o canal ${c.name}? Produções e publicações dele também serão removidas.`) && run("d", async () => { await api(`/channels/${id}`, { method: "DELETE" }); router.push("/channels"); }, "Canal excluído")}>Excluir</Button>
            <Button variant="primary" busy={busy === "s"} onClick={save}>Salvar alterações</Button>
          </div>
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Identidade">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Cor"><Input type="color" className="h-9 p-1" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} /></Field>
            <Field className="sm:col-span-2" label="Nicho"><Input value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })} /></Field>
            <Field className="sm:col-span-2" label="Público-alvo"><Input value={f.target_audience} onChange={(e) => setF({ ...f, target_audience: e.target.value })} /></Field>
            <Field className="sm:col-span-2" label="Identidade, tom e regras editoriais"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
            <Field label="Idioma"><Input value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })} /></Field>
            <Field label="Estilo visual"><Select value={f.visual_style} onChange={(e) => setF({ ...f, visual_style: e.target.value })}><option value="cartoon">Cartoon 2D</option><option value="stickman">Stickman</option><option value="cinematic">Cinematográfico</option></Select></Field>
            <Field label="Narrador"><Select value={f.narrator_voice_id} onChange={(e) => setF({ ...f, narrator_voice_id: e.target.value })}><option value="">Automático</option>{voices?.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}</Select></Field>
            <Field label="Template de edição"><Select value={f.default_template_id || ""} onChange={(e) => setF({ ...f, default_template_id: e.target.value })}><option value="">Padrão</option>{templates?.items.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select></Field>
            <Field label="Marca d'água"><Input value={f.watermark} onChange={(e) => setF({ ...f, watermark: e.target.value })} placeholder="@seucanal" /></Field>
            <Field label="Hashtags fixas"><Input value={f.hashtags_base} onChange={(e) => setF({ ...f, hashtags_base: e.target.value })} placeholder="#historias #animacao" /></Field>
          </div>
        </Panel>
        <Panel title="Autonomia e rotina">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field className="sm:col-span-2" label="Modo"><Select value={f.autonomy_mode} onChange={(e) => setF({ ...f, autonomy_mode: e.target.value })}>
              <option value="manual">Manual: você inicia cada etapa</option><option value="assisted">Assistido: produz e aguarda aprovação</option><option value="automatic">Automático: produz e publica conforme as regras</option></Select></Field>
            <Toggle checked={f.require_approval} onChange={(v) => setF({ ...f, require_approval: v })} label="Exigir aprovação antes de publicar" />
            <Toggle checked={!!f.settings?.auto_optimize} onChange={(v) => setF({ ...f, settings: { ...f.settings, auto_optimize: v } })} label="Aplicar otimizações automaticamente" />
            <Field label="Vídeos por dia"><Input type="number" min={0} max={50} value={f.videos_per_day} onChange={(e) => setF({ ...f, videos_per_day: e.target.value })} /></Field>
            <Field label="Duração padrão (s)"><Input type="number" min={10} max={600} value={f.default_duration_s} onChange={(e) => setF({ ...f, default_duration_s: e.target.value })} /></Field>
            <Field label="Horários de publicação" hint="HH:MM separados por vírgula"><Input value={f.preferred_hours} onChange={(e) => setF({ ...f, preferred_hours: e.target.value })} /></Field>
            <Field label="Fuso horário"><Input value={f.timezone} onChange={(e) => setF({ ...f, timezone: e.target.value })} /></Field>
            <Field className="sm:col-span-2" label="Escolha de provedores"><Select value={f.provider_strategy} onChange={(e) => setF({ ...f, provider_strategy: e.target.value })}>
              <option value="balanced">Equilíbrio entre qualidade e custo</option><option value="quality">Maior qualidade</option><option value="cost">Menor custo</option><option value="speed">Mais rápido</option></Select></Field>
            <div className="sm:col-span-2"><div className="mb-1 text-[13px] font-medium text-ink-2">Plataformas</div><div className="flex flex-wrap gap-4 text-sm">
              {Object.entries(PLATFORM).map(([k, v]) => <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={f.platforms.includes(k)} onChange={(e) => setF({ ...f, platforms: e.target.checked ? [...f.platforms, k] : f.platforms.filter((p: string) => p !== k) })} />{v}</label>)}</div></div>
            <Toggle checked={f.is_active} onChange={(v) => setF({ ...f, is_active: v })} label="Canal ativo" />
          </div>
        </Panel>
      </div>
      <Panel title="Distribuição entre motores" actions={<span className="text-xs text-muted">Ponto de partida; o otimizador ajusta com base nos resultados</span>}>
        <div className="space-y-3">
          {engines.map((e: any) => (
            <div key={e.id} className="grid grid-cols-[24px_1fr_120px_56px] items-center gap-3 text-sm sm:grid-cols-[24px_220px_1fr_80px_56px]">
              <input type="checkbox" aria-label={e.name} checked={weights[e.id]?.on} onChange={(x) => setWeights({ ...weights, [e.id]: { ...weights[e.id], on: x.target.checked } })} />
              <span style={{ color: e.color }} className="font-medium">{e.name}{!e.is_active && <span className="text-muted"> (desativado)</span>}</span>
              <div className="hidden h-2 overflow-hidden rounded-full bg-ink/8 sm:block"><div className="h-full" style={{ width: `${weights[e.id]?.on ? (weights[e.id].w / total) * 100 : 0}%`, background: e.color }} /></div>
              <Input type="number" min={0} step={0.1} value={weights[e.id]?.w} disabled={!weights[e.id]?.on} onChange={(x) => setWeights({ ...weights, [e.id]: { ...weights[e.id], w: +x.target.value } })} />
              <span className="num text-right text-muted">{weights[e.id]?.on ? Math.round((weights[e.id].w / total) * 100) : 0}%</span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Contas conectadas" actions={<Button size="sm" onClick={() => setAcc({ platform_key: "youtube", display_name: "", publish_mode: "api" })}>Adicionar conta</Button>}>
        {c.accounts.length === 0 && <p className="text-sm text-muted">Nenhuma conta. Sem conta conectada, as publicações ficam no modo assistido (você baixa o pacote e publica).</p>}
        <div className="space-y-3">{c.accounts.map((a: any) => {
          const plat = platforms?.find((p: any) => p.key === a.platform_key);
          return (
            <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-line p-3 text-sm">
              <div><div className="font-medium">{PLATFORM[a.platform_key]} · {a.display_name}</div>
                <div className="text-xs text-muted">{a.status === "connected" ? `Conectada${a.token_expires_at ? ` · token até ${dt(a.token_expires_at)}` : ""}` : a.last_error || "Não conectada"} · publicação {a.publish_mode === "api" ? "pela API" : "assistida"}</div>
                {plat && !plat.app_configured && <div className="text-xs text-[#a86a00]">{plat.app_detail} no servidor para habilitar a conexão.</div>}
                {a.platform_key === "tiktok" && <div className="text-xs text-muted">Apps do TikTok não auditados publicam apenas como privado.</div>}</div>
              <div className="flex items-center gap-2">
                <Pill tone={a.status === "connected" ? "preview" : a.status === "error" || a.status === "expired" ? "onair" : "neutral"}>{a.status}</Pill>
                {a.status === "connected" ? <Button size="sm" onClick={() => run(`x${a.id}`, async () => { await api(`/accounts/${a.id}/disconnect`, { method: "POST" }); mutate(); }, "Conta desconectada")}>Desconectar</Button>
                  : <Button size="sm" variant="primary" disabled={plat && !plat.app_configured} busy={busy === `c${a.id}`} onClick={() => connect(a.id)}>Conectar</Button>}
                {a.platform_key === "tiktok" && <Toggle checked={!!a.config?.app_audited} onChange={(v) => run("t", async () => { await api(`/accounts/${a.id}`, { method: "PATCH", body: { config: { app_audited: v } } }); mutate(); })} label="App auditado" />}
                <Button size="sm" variant="quiet" onClick={() => confirm("Remover conta?") && run(`r${a.id}`, async () => { await api(`/accounts/${a.id}`, { method: "DELETE" }); mutate(); }, "Conta removida")}>Remover</Button>
              </div>
            </div>);
        })}</div>
      </Panel>
      <Modal open={!!acc} onClose={() => setAcc(null)} title="Adicionar conta" footer={acc && <Button variant="primary" disabled={!acc.display_name} onClick={() => run("a", async () => { await api(`/channels/${id}/accounts`, { body: acc }); setAcc(null); mutate(); }, "Conta adicionada. Agora clique em Conectar.")}>Adicionar</Button>}>
        {acc && <div className="space-y-4">
          <Field label="Plataforma"><Select value={acc.platform_key} onChange={(e) => setAcc({ ...acc, platform_key: e.target.value })}>{Object.entries(PLATFORM).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
          <Field label="Nome da conta"><Input value={acc.display_name} onChange={(e) => setAcc({ ...acc, display_name: e.target.value })} placeholder="@seucanal" /></Field>
          <Field label="Publicação" hint="API exige o app da plataforma aprovado e a conta conectada via OAuth."><Select value={acc.publish_mode} onChange={(e) => setAcc({ ...acc, publish_mode: e.target.value })}><option value="api">Automática pela API oficial</option><option value="assisted">Assistida (download e publicação manual)</option></Select></Field>
        </div>}
      </Modal>
    </div>
  );
}

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <Suspense><ChannelPage id={id} /></Suspense>;
}
