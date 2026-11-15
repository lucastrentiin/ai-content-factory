"use client";
import { useState } from "react";
import useSWR from "swr";
import { Button, Empty, Field, Input, JsonField, Loading, Modal, PageHeader, Pager, Pill, Select, Table, Tabs, Textarea, Toggle, useAction } from "@/components/ui";
import { api, qs } from "@/lib/api";
import { ago, dt } from "@/lib/format";

type T = "providers" | "engines" | "automation" | "workflows" | "users" | "tokens" | "logs" | "audit";
const KIND: Record<string, string> = { llm: "Linguagem (roteiros e ideias)", image: "Imagens", video: "Vídeo por IA", tts: "Voz (TTS)", music: "Música" };
const PSTATUS: Record<string, { label: string; tone: any }> = { configured: { label: "Configurado", tone: "preview" }, missing_credentials: { label: "Faltam credenciais", tone: "cue" },
  unavailable: { label: "Indisponível", tone: "onair" }, simulated: { label: "Simulado", tone: "cue" }, error: { label: "Erro", tone: "onair" }, disabled: { label: "Desativado", tone: "neutral" },
  circuit_open: { label: "Pausado após falhas", tone: "onair" }, unknown: { label: "Desconhecido", tone: "neutral" } };

export default function Settings() {
  const [tab, setTab] = useState<T>("providers");
  return (
    <div>
      <PageHeader title="Configurações" description="Provedores e chaves de API, motores de conteúdo, automações, usuários e registros." />
      <Tabs value={tab} onChange={setTab} items={[{ value: "providers", label: "Provedores" }, { value: "engines", label: "Motores" }, { value: "automation", label: "Parâmetros" },
        { value: "workflows", label: "Automações" }, { value: "users", label: "Usuários" }, { value: "tokens", label: "Tokens de API" }, { value: "logs", label: "Logs" }, { value: "audit", label: "Auditoria" }]} />
      {tab === "providers" && <Providers />}
      {tab === "engines" && <Engines />}
      {tab === "automation" && <Automation />}
      {tab === "workflows" && <Workflows />}
      {tab === "users" && <Users />}
      {tab === "tokens" && <Tokens />}
      {tab === "logs" && <Logs />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

function Providers() {
  const { data, mutate } = useSWR("/providers");
  const [sel, setSel] = useState<any>(null);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  const kinds = Object.keys(KIND).filter((k) => data.some((p: any) => p.kind === k));
  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-muted">Chaves são criptografadas no banco e nunca voltam para o navegador. Também podem vir do arquivo .env. A fábrica escolhe o provedor pela estratégia do canal e troca automaticamente se um falhar; depois de 3 falhas seguidas, o provedor fica pausado por 5 minutos.</p>
      {kinds.map((k) => (
        <section key={k}>
          <h2 className="mb-2">{KIND[k]}</h2>
          <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
            {data.filter((p: any) => p.kind === k).map((p: any) => (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-line/70 px-4 py-3 last:border-0">
                <div className="min-w-0">
                  <div className="font-medium">{p.name} <span className="text-xs font-normal text-muted">prioridade {p.priority}</span></div>
                  <div className="text-xs text-muted">{p.models.find((m: any) => m.is_default)?.display_name}{p.status_detail ? ` · ${p.status_detail}` : ""}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Pill tone={PSTATUS[p.status]?.tone} dot>{PSTATUS[p.status]?.label || p.status}</Pill>
                  <Toggle checked={p.is_enabled} onChange={(v) => run(`e${p.id}`, async () => { await api(`/providers/${p.id}`, { method: "PATCH", body: { is_enabled: v } }); mutate(); })} />
                  <Button size="sm" busy={busy === `t${p.id}`} onClick={() => run(`t${p.id}`, async () => { const r = await api(`/providers/${p.id}/test`, { method: "POST" }); mutate(); if (!r.ok) throw new Error(r.detail || r.status); }, "Conexão verificada")}>Testar</Button>
                  <Button size="sm" onClick={() => setSel(p)}>Configurar</Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
      <ProviderModal p={sel} onClose={() => setSel(null)} onSaved={mutate} />
    </div>
  );
}

function ProviderModal({ p, onClose, onSaved }: any) {
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [cfg, setCfg] = useState<any>(null);
  const [prio, setPrio] = useState<number | null>(null);
  const [model, setModel] = useState<any>(null);
  const { busy, run } = useAction();
  if (!p) return null;
  const close = () => { setCreds({}); setCfg(null); setPrio(null); onClose(); };
  return (
    <Modal open onClose={close} title={p.name} wide footer={<Button variant="primary" busy={busy === "s"} onClick={() => run("s", async () => {
      if (Object.keys(creds).length) await api(`/providers/${p.id}/credentials`, { method: "PUT", body: { credentials: creds } });
      if (cfg || prio != null) await api(`/providers/${p.id}`, { method: "PATCH", body: { ...(cfg ? { config: cfg } : {}), ...(prio != null ? { priority: prio } : {}) } });
      onSaved(); close(); }, "Provedor salvo")}>Salvar</Button>}>
      <div className="space-y-5 text-sm">
        {p.is_simulated && <p className="rounded-md bg-cue-soft p-3">Provedor simulado: não usa IA. Serve para testar o fluxo sem credenciais. Desative em Parâmetros quando tiver um provedor real.</p>}
        {p.commercial_use_note && <p className="text-muted">{p.commercial_use_note}</p>}
        {p.docs_url && <a className="text-reel" href={p.docs_url} target="_blank" rel="noreferrer">Documentação do provedor</a>}
        {p.required_credentials.length > 0 && <div className="space-y-3">
          {p.required_credentials.map((k: string) => {
            const c = p.credentials[k];
            return (
              <Field key={k} label={k} hint={c?.configured ? (c.source === "env" ? "Definida no .env do servidor" : `Salva: ${c.masked}. Deixe em branco para manter.`) : "Ainda não definida"}>
                <div className="flex gap-2">
                  <Input type="password" autoComplete="off" value={creds[k] ?? ""} onChange={(e) => setCreds({ ...creds, [k]: e.target.value })} placeholder={c?.configured ? "••••••••" : "Cole a chave"} />
                  {c?.source === "db" && <Button onClick={() => run("rm", async () => { await api(`/providers/${p.id}/credentials`, { method: "PUT", body: { credentials: { [k]: null } } }); onSaved(); close(); }, "Chave removida")}>Remover</Button>}
                </div>
              </Field>
            );
          })}
        </div>}
        <div className="grid gap-4 sm:grid-cols-[120px_1fr]">
          <Field label="Prioridade" hint="Menor = preferido"><Input type="number" min={0} max={100} value={prio ?? p.priority} onChange={(e) => setPrio(+e.target.value)} /></Field>
          <Field label="Configuração" hint="Ex.: base_url (Ollama/OpenRouter), default_voices, effort"><JsonField key={p.id} rows={5} value={p.config} onChange={(v, ok) => ok && setCfg(v)} /></Field>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between"><h3>Modelos e preços</h3><Button size="sm" onClick={() => setModel({ model_key: "", display_name: "", pricing: {}, quality_score: 5, speed_score: 5, is_default: false, is_enabled: true })}>Adicionar modelo</Button></div>
          <Table head={["Modelo", "Preço (US$)", "Qualidade", "Velocidade", ""]}>
            {p.models.map((m: any) => <tr key={m.id}><td>{m.display_name} {m.is_default && <Pill tone="reel">padrão</Pill>}<div className="text-xs text-muted">{m.model_key}</div></td>
              <td className="text-xs">{Object.entries(m.pricing).map(([k, v]) => `${k}: ${v}`).join(", ") || "grátis"}</td><td className="num">{m.quality_score}</td><td className="num">{m.speed_score}</td>
              <td><Button size="sm" variant="quiet" onClick={() => setModel(m)}>Editar</Button></td></tr>)}
          </Table>
          <p className="mt-2 text-xs text-muted">Preços são estimativas editáveis; confira a tabela oficial do provedor.</p>
        </div>
      </div>
      {model && <ModelModal pid={p.id} m={model} onClose={() => setModel(null)} onSaved={() => { onSaved(); close(); }} />}
    </Modal>
  );
}

function ModelModal({ pid, m, onClose, onSaved }: any) {
  const [f, setF] = useState({ ...m });
  const [ok, setOk] = useState(true);
  const { busy, run } = useAction();
  return (
    <Modal open onClose={onClose} title={m.id ? "Editar modelo" : "Novo modelo"} footer={<>
      {m.id && <Button variant="danger" onClick={() => run("d", async () => { await api(`/provider-models/${m.id}`, { method: "DELETE" }); onSaved(); }, "Modelo removido")}>Remover</Button>}
      <Button variant="primary" disabled={!f.model_key || !ok} busy={busy === "s"} onClick={() => run("s", async () => {
        const body = { model_key: f.model_key, display_name: f.display_name || f.model_key, pricing: f.pricing, quality_score: +f.quality_score, speed_score: +f.speed_score, is_default: f.is_default, is_enabled: f.is_enabled };
        await api(m.id ? `/provider-models/${m.id}` : `/providers/${pid}/models`, { method: m.id ? "PATCH" : "POST", body }); onSaved(); }, "Modelo salvo")}>Salvar</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="ID do modelo"><Input value={f.model_key} disabled={!!m.id} onChange={(e) => setF({ ...f, model_key: e.target.value })} /></Field>
        <Field label="Nome"><Input value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        <Field label="Qualidade (0–10)"><Input type="number" min={0} max={10} value={f.quality_score} onChange={(e) => setF({ ...f, quality_score: e.target.value })} /></Field>
        <Field label="Velocidade (0–10)"><Input type="number" min={0} max={10} value={f.speed_score} onChange={(e) => setF({ ...f, speed_score: e.target.value })} /></Field>
        <Field className="sm:col-span-2" label="Preços" hint="input_per_1m_tokens, output_per_1m_tokens, per_image, per_second, per_video, per_1k_chars"><JsonField rows={4} value={f.pricing} onChange={(v, valid) => { setOk(valid); if (valid) setF({ ...f, pricing: v }); }} /></Field>
        <Toggle checked={f.is_default} onChange={(v) => setF({ ...f, is_default: v })} label="Modelo padrão" />
        <Toggle checked={f.is_enabled} onChange={(v) => setF({ ...f, is_enabled: v })} label="Ativo" />
      </div>
    </Modal>
  );
}

function Engines() {
  const { data, mutate } = useSWR("/engines");
  const [f, setF] = useState<any>(null);
  const [ok, setOk] = useState(true);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  return (
    <div className="space-y-4">
      <div className="flex justify-between gap-4"><p className="max-w-2xl text-sm text-muted">Motores definem regras editoriais, tom, formatos, estilos, duração e etapas especiais (como verificação de fatos). Crie motores novos para formatos que a pesquisa encontrar.</p>
        <Button variant="primary" onClick={() => setF({ key: "", name: "", description: "", engine_type: "custom", color: "#7c5cff", is_active: true, config: { editorial_rules: "", tone: "", formats: [], default_visual_mode: "animation_2d", scene_count: [4, 7], requires_fact_check: false } })}>Novo motor</Button></div>
      <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        {data.map((e: any) => (
          <div key={e.id} className="flex flex-wrap items-center justify-between gap-3 border-b border-line/70 px-4 py-3 last:border-0">
            <div className="flex items-center gap-3"><span className="size-3 rounded-full" style={{ background: e.color }} />
              <div><div className="font-medium">{e.name} {e.is_system && <span className="text-xs text-muted">(padrão)</span>}</div><div className="max-w-xl text-xs text-muted">{e.description}</div></div></div>
            <div className="flex items-center gap-3"><span className="text-xs text-muted">{e.productions} produções</span>
              <Toggle checked={e.is_active} onChange={(v) => run("t", async () => { await api(`/engines/${e.id}`, { method: "PATCH", body: { is_active: v } }); mutate(); }, v ? "Motor ativado" : "Motor desativado")} />
              <Button size="sm" onClick={() => setF(e)}>Editar</Button></div>
          </div>
        ))}
      </div>
      <Modal open={!!f} onClose={() => setF(null)} title={f?.id ? `Motor: ${f.name}` : "Novo motor"} wide footer={f && <>
        {f.id && !f.is_system && <Button variant="danger" onClick={() => confirm("Excluir motor?") && run("d", async () => { await api(`/engines/${f.id}`, { method: "DELETE" }); mutate(); setF(null); }, "Motor excluído")}>Excluir</Button>}
        <Button variant="primary" disabled={!ok || !f.name || (!f.id && !f.key)} busy={busy === "s"} onClick={() => run("s", async () => {
          const body = { name: f.name, description: f.description, engine_type: f.engine_type, color: f.color, is_active: f.is_active, config: f.config };
          await api(f.id ? `/engines/${f.id}` : "/engines", { method: f.id ? "PATCH" : "POST", body: f.id ? body : { ...body, key: f.key } }); mutate(); setF(null); }, "Motor salvo")}>Salvar</Button></>}>
        {f && <div className="grid gap-4 sm:grid-cols-2">
          {!f.id && <Field label="Chave" hint="letras minúsculas, números e -"><Input value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} /></Field>}
          <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Tipo base"><Select value={f.engine_type} onChange={(e) => setF({ ...f, engine_type: e.target.value })}>{["storytelling", "series", "comedy", "horror", "curiosity", "experimental", "custom"].map((t) => <option key={t}>{t}</option>)}</Select></Field>
          <Field label="Cor"><Input type="color" className="h-9 p-1" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} /></Field>
          <Field className="sm:col-span-2" label="Descrição"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Field className="sm:col-span-2" label="Configuração" hint="editorial_rules, tone, formats, visual_styles, default_visual_mode (animation_2d|ai_image), ai_backgrounds, ai_video_scenes, durations, scene_count, requires_fact_check, speech_rate, narrator_voice_id">
            <JsonField key={f.id ?? "new"} rows={12} value={f.config} onChange={(v, valid) => { setOk(valid); if (valid) setF({ ...f, config: v }); }} /></Field>
        </div>}
      </Modal>
    </div>
  );
}

function Automation() {
  const { data, mutate } = useSWR("/settings");
  const { busy, run } = useAction();
  const [draft, setDraft] = useState<any>(null);
  if (!data) return <Loading />;
  const d = draft || data;
  const set = (g: string, k: string, v: any) => setDraft({ ...d, [g]: { ...d[g], [k]: v } });
  const LABELS: Record<string, [string, string]> = {
    factory_enabled: ["Fábrica ligada", "Desligue para parar todas as produções automáticas"], max_concurrent_productions: ["Produções simultâneas", ""],
    ideas_per_run: ["Ideias por geração", ""], min_idea_score_auto: ["Nota mínima para produzir automaticamente (0–1)", ""], auto_approve_ideas: ["Aprovar ideias automaticamente", "Nos canais automáticos/assistidos"],
    allow_simulated: ["Permitir provedores simulados", "Desative quando houver provedores reais configurados"],
    min_samples: ["Amostra mínima por estratégia", "Publicações maduras antes de confiar em um resultado"], confidence: ["Nível de confiança", ""], exploration_floor: ["Piso de exploração", "Fração mínima reservada para testar alternativas"],
    max_weight_change: ["Variação máxima por rodada", "Evita mudanças bruscas"], metric: ["Métrica de aprendizado", ""],
    min_loudness_lufs: ["Volume mínimo (LUFS)", ""], max_loudness_lufs: ["Volume máximo (LUFS)", ""], max_black_ratio: ["Máximo de quadros pretos (0–1)", ""], require_license_check: ["Exigir verificação de licenças", ""],
  };
  const GROUPS: Record<string, string> = { automation: "Fábrica", providers: "Provedores", learning: "Aprendizado", quality: "Controle de qualidade" };
  return (
    <div className="space-y-6">
      {Object.entries(GROUPS).map(([g, title]) => (
        <section key={g} className="rounded-[var(--radius-frame)] border border-line bg-surface p-4">
          <div className="mb-3 flex items-center justify-between"><h2>{title}</h2>
            <Button size="sm" variant="primary" disabled={!draft} busy={busy === g} onClick={() => run(g, async () => { await api(`/settings/${g}`, { method: "PUT", body: d[g] }); setDraft(null); mutate(); }, "Parâmetros salvos")}>Salvar</Button></div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(d[g]).map(([k, v]) => typeof v === "boolean"
              ? <div key={k}><Toggle checked={v} onChange={(x) => set(g, k, x)} label={LABELS[k]?.[0] || k} />{LABELS[k]?.[1] && <div className="mt-1 text-xs text-muted">{LABELS[k][1]}</div>}</div>
              : <Field key={k} label={LABELS[k]?.[0] || k} hint={LABELS[k]?.[1]}><Input type={typeof v === "number" ? "number" : "text"} step="any" value={String(v)} onChange={(e) => set(g, k, typeof v === "number" ? +e.target.value : e.target.value)} /></Field>)}
          </div>
        </section>
      ))}
    </div>
  );
}

function Workflows() {
  const { data, mutate } = useSWR("/workflows", { refreshInterval: 20000 });
  const [edit, setEdit] = useState<any>(null);
  const { busy, run } = useAction();
  if (!data) return <Loading />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">Automações recorrentes (cron, horário UTC). Integrações externas como o n8n podem chamar a API com um token.</p>
      <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        <Table head={["Automação", "Agenda", "Última execução", "Próxima", "Ativa", ""]}>
          {data.map((w: any) => (
            <tr key={w.id}>
              <td><div className="font-medium">{w.name}</div><div className="text-xs text-muted">{w.description}</div></td>
              <td><code className="text-xs">{w.schedule}</code></td>
              <td className="text-xs text-muted">{ago(w.last_run_at)} {w.last_status === "error" && <span className="text-onair">erro</span>}</td>
              <td className="text-xs text-muted">{dt(w.next_run_at)}</td>
              <td><Toggle checked={w.is_enabled} onChange={(v) => run(`e${w.id}`, async () => { await api(`/workflows/${w.id}`, { method: "PATCH", body: { is_enabled: v } }); mutate(); })} /></td>
              <td><div className="flex justify-end gap-1"><Button size="sm" busy={busy === `r${w.id}`} onClick={() => run(`r${w.id}`, async () => { await api(`/workflows/${w.id}/run`, { method: "POST" }); mutate(); }, "Automação disparada")}>Executar agora</Button>
                <Button size="sm" variant="quiet" onClick={() => setEdit({ ...w })}>Agenda</Button></div></td>
            </tr>
          ))}
        </Table>
      </div>
      <Modal open={!!edit} onClose={() => setEdit(null)} title="Alterar agenda" footer={edit && <Button variant="primary" onClick={() => run("s", async () => { await api(`/workflows/${edit.id}`, { method: "PATCH", body: { schedule: edit.schedule } }); mutate(); setEdit(null); }, "Agenda atualizada")}>Salvar</Button>}>
        {edit && <Field label="Expressão cron" hint="minuto hora dia mês dia-da-semana (UTC). Ex.: */15 * * * * = a cada 15 min"><Input value={edit.schedule} onChange={(e) => setEdit({ ...edit, schedule: e.target.value })} /></Field>}
      </Modal>
    </div>
  );
}

function Users() {
  const { data, mutate, error } = useSWR("/users");
  const [f, setF] = useState<any>(null);
  const { busy, run } = useAction();
  if (error) return <Empty title="Somente administradores gerenciam usuários" />;
  if (!data) return <Loading />;
  return (
    <div className="space-y-3">
      <div className="flex justify-end"><Button variant="primary" onClick={() => setF({ email: "", name: "", password: "", role: "editor" })}>Novo usuário</Button></div>
      <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        <Table head={["Nome", "E-mail", "Papel", "Último acesso", "Ativo", ""]}>
          {data.map((u: any) => <tr key={u.id}><td>{u.name}</td><td>{u.email}</td><td>{({ admin: "Administrador", editor: "Editor", viewer: "Leitura" } as any)[u.role]}</td><td className="text-xs text-muted">{ago(u.last_login_at)}</td>
            <td><Toggle checked={u.is_active} onChange={(v) => run("a", async () => { await api(`/users/${u.id}`, { method: "PATCH", body: { is_active: v } }); mutate(); })} /></td>
            <td><Button size="sm" variant="quiet" onClick={() => setF({ ...u, password: "" })}>Editar</Button></td></tr>)}
        </Table>
      </div>
      <Modal open={!!f} onClose={() => setF(null)} title={f?.id ? "Editar usuário" : "Novo usuário"} footer={f && <Button variant="primary" busy={!!busy} onClick={() => run("s", async () => {
        if (f.id) await api(`/users/${f.id}`, { method: "PATCH", body: { name: f.name, role: f.role, ...(f.password ? { password: f.password } : {}) } });
        else await api("/users", { body: { email: f.email, name: f.name, password: f.password, role: f.role } });
        mutate(); setF(null); }, "Usuário salvo")}>Salvar</Button>}>
        {f && <div className="space-y-4">
          {!f.id && <Field label="E-mail"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>}
          <Field label="Nome"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Papel" hint="Leitura vê tudo; Editor produz e publica; Administrador gerencia provedores, usuários e parâmetros.">
            <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}><option value="viewer">Leitura</option><option value="editor">Editor</option><option value="admin">Administrador</option></Select></Field>
          <Field label={f.id ? "Nova senha (opcional)" : "Senha"} hint="Mínimo de 8 caracteres"><Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
        </div>}
      </Modal>
    </div>
  );
}

function Tokens() {
  const { data, mutate } = useSWR("/api-tokens");
  const [name, setName] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const { busy, run } = useAction();
  return (
    <div className="space-y-4">
      <p className="max-w-2xl text-sm text-muted">Tokens permitem que n8n, scripts ou outras ferramentas usem a API com suas permissões. Envie no cabeçalho <code>Authorization: Bearer &lt;token&gt;</code>.</p>
      <div className="flex gap-2"><Input className="w-64" placeholder="Nome (ex.: n8n)" value={name} onChange={(e) => setName(e.target.value)} />
        <Button variant="primary" disabled={!name} busy={!!busy} onClick={() => run("c", async () => { const r = await api("/api-tokens", { body: { name } }); setCreated(r.token); setName(""); mutate(); })}>Criar token</Button></div>
      {created && <div className="rounded-md border border-cue bg-cue-soft p-3 text-sm">Copie agora; ele não será exibido de novo: <code className="break-all font-semibold">{created}</code></div>}
      <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        <Table head={["Nome", "Início", "Último uso", "Status", ""]}>
          {data?.map((t: any) => <tr key={t.id}><td>{t.name}</td><td><code className="text-xs">{t.prefix}…</code></td><td className="text-xs text-muted">{ago(t.last_used_at)}</td>
            <td>{t.revoked ? <Pill>revogado</Pill> : <Pill tone="preview">ativo</Pill>}</td>
            <td>{!t.revoked && <Button size="sm" variant="danger" onClick={() => run("r", async () => { await api(`/api-tokens/${t.id}`, { method: "DELETE" }); mutate(); }, "Token revogado")}>Revogar</Button>}</td></tr>)}
        </Table>
      </div>
    </div>
  );
}

function Logs() {
  const [level, setLevel] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error } = useSWR(`/system/logs${qs({ level, limit: 50, offset })}`);
  const { busy, run } = useAction();
  if (error) return <Empty title="Somente administradores veem os logs" />;
  return (
    <div className="space-y-3">
      <div className="flex justify-between gap-2"><Select className="w-40" value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Nível"><option value="">Todos</option><option>ERROR</option><option>WARNING</option><option>INFO</option></Select>
        <Button busy={!!busy} onClick={() => run("c", async () => { const r = await api("/system/cleanup", { method: "POST" }); return r; }, "Limpeza concluída")}>Limpar arquivos temporários</Button></div>
      {!data ? <Loading /> : <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
        <Table head={["Quando", "Nível", "Origem", "Mensagem"]}>
          {data.items.map((l: any) => <tr key={l.id}><td className="whitespace-nowrap text-xs">{dt(l.created_at)}</td><td><Pill tone={l.level === "ERROR" ? "onair" : l.level === "WARNING" ? "cue" : "neutral"}>{l.level}</Pill></td><td className="text-xs">{l.source}</td><td className="text-sm">{l.message}</td></tr>)}
        </Table>
        <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} /></div>}
      <p className="text-xs text-muted">Logs completos de cada serviço saem em JSON no stdout: <code>docker compose logs -f api worker</code>.</p>
    </div>
  );
}

function Audit() {
  const [offset, setOffset] = useState(0);
  const { data, error } = useSWR(`/audit-logs${qs({ limit: 50, offset })}`);
  if (error) return <Empty title="Somente administradores veem a auditoria" />;
  if (!data) return <Loading />;
  return (
    <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
      <Table head={["Quando", "Usuário", "Ação", "Alvo", "Detalhes"]}>
        {data.items.map((a: any) => <tr key={a.id}><td className="whitespace-nowrap text-xs">{dt(a.created_at)}</td><td className="text-xs">{a.user_email || "sistema"}</td><td><code className="text-xs">{a.action}</code></td>
          <td className="text-xs">{a.entity_type}{a.entity_id && ` #${a.entity_id}`}</td><td className="max-w-md truncate text-xs text-muted">{JSON.stringify(a.data)}</td></tr>)}
      </Table>
      <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
    </div>
  );
}
