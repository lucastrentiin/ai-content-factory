"use client";
import Link from "next/link";
import { use, useState } from "react";
import useSWR from "swr";
import { FilmStrip } from "@/components/FilmStrip";
import { ManualPrompt } from "@/components/ManualPrompt";
import { Button, Empty, Field, Input, Loading, Modal, Panel, Pill, Select, Simulated, Tabs, Textarea, useAction } from "@/components/ui";
import { api } from "@/lib/api";
import { dt, JOB_STATUS, ms, PLATFORM, PUB_STATUS, secs, STEP_LABEL, usd } from "@/lib/format";

export default function ProductionDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: j, mutate, error } = useSWR(`/productions/${id}`, { refreshInterval: (d: any) => (d && ["running", "queued"].includes(d.status) ? 3000 : 20000) });
  const [tab, setTab] = useState<"scenes" | "steps" | "script" | "qc" | "publish" | "costs">("scenes");
  const [stepOpen, setStepOpen] = useState<string | null>(null);
  const [reject, setReject] = useState(false);
  const { busy, run } = useAction();
  if (error) return <Empty title="Produção não encontrada">{error.message}</Empty>;
  if (!j || !j.steps) return <Loading />;
  const st = JOB_STATUS[j.status] || { label: j.status, tone: "neutral" as const };
  const act = (key: string, path: string, msg: string, body?: unknown) => run(key, async () => { await api(`/productions/${id}/${path}`, { method: "POST", body: body ?? {} }); await mutate(); }, msg);
  const failedStep = (j.steps || []).find((s: any) => s.status === "failed");
  return (
    <div className="space-y-6">
      <div>
        <Link href="/production" className="text-sm text-muted hover:text-ink">Produção</Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="break-words">{j.title}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
              <Pill tone={st.tone} dot>{st.label}</Pill>
              <span>#{j.id} · {j.channel?.name} · <span style={{ color: j.engine?.color }}>{j.engine?.name}</span> · {j.visual_style} · modo {j.autonomy_mode}</span>
              {j.is_simulated && <Simulated />}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {j.status === "paused" && <Button variant="primary" busy={busy === "c"} onClick={() => act("c", "continue", "Próxima etapa iniciada")}>Executar próxima etapa</Button>}
            {["awaiting_approval", "needs_review"].includes(j.status) && <>
              <Button variant="primary" busy={busy === "a"} onClick={() => act("a", "approve", "Aprovado e agendado")}>Aprovar e agendar</Button>
              <Button onClick={() => setReject(true)}>Rejeitar</Button>
            </>}
            {["failed", "blocked_budget"].includes(j.status) && <Button variant="primary" busy={busy === "r"} onClick={() => act("r", "resume", "Produção retomada")}>Retomar de onde parou</Button>}
            {!["completed", "cancelled"].includes(j.status) && <Button variant="danger" busy={busy === "x"} onClick={() => confirm("Cancelar esta produção?") && act("x", "cancel", "Produção cancelada")}>Cancelar</Button>}
          </div>
        </div>
      </div>

      {j.status === "awaiting_input" && <AwaitingInput jobId={j.id} onDone={mutate} />}

      <section className="rounded-[var(--radius-frame)] bg-ink p-4 text-white">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span>{j.current_step ? <>Agora: <strong>{STEP_LABEL[j.current_step]}</strong></> : j.status === "running" ? "Iniciando…" : "Película de produção"}</span>
          <span className="num text-white/70">{Math.round((j.progress || 0) * 100)}% · {usd(j.actual_cost_usd, 4)}</span>
        </div>
        <FilmStrip steps={j.steps} height={34} onPick={setStepOpen} />
        <div className="mt-2 hidden grid-cols-12 gap-x-1 text-[11px] text-white/55 md:grid">
          {j.steps.map((s: any) => <span key={s.agent} className="truncate">{STEP_LABEL[s.agent]}</span>)}
        </div>
        {(j.error || failedStep) && <p className="mt-3 text-sm text-[#ffb3c1]">{j.error || failedStep?.error}</p>}
        {j.review_reasons?.length > 0 && <ul className="mt-3 list-disc pl-5 text-sm text-[#ffd99a]">{j.review_reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>}
      </section>

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="space-y-3">
          <div className="mx-auto aspect-[9/16] w-full max-w-[300px] overflow-hidden rounded-[var(--radius-frame)] bg-ink">
            {j.video ? <video key={j.video.url} src={j.video.url} poster={j.thumbnail?.url} controls playsInline className="size-full object-contain" />
              : <div className="flex size-full items-center justify-center p-6 text-center text-sm text-white/60">O vídeo aparece aqui quando a edição terminar.</div>}
          </div>
          {j.video && <div className="flex gap-2">
            <a className="flex-1" href={`${j.video.url}?download=1`}><Button className="w-full">Baixar vídeo</Button></a>
            {j.thumbnail && <a href={`${j.thumbnail.url}?download=1`}><Button>Capa</Button></a>}
          </div>}
          <div className="text-xs text-muted">Duração {secs(j.video?.duration_s)} · alvo {j.target_duration_s}s · criado {dt(j.created_at)}</div>
        </div>

        <div className="min-w-0">
          <Tabs value={tab} onChange={setTab} items={[
            { value: "scenes", label: `Cenas (${j.scenes.length})` }, { value: "steps", label: "Etapas" }, { value: "script", label: "Roteiro" },
            { value: "qc", label: "Qualidade" }, { value: "publish", label: `Publicação (${j.publications.length})` }, { value: "costs", label: "Custos" }]} />
          {tab === "scenes" && <Scenes j={j} onChange={mutate} />}
          {tab === "steps" && <Steps j={j} onOpen={setStepOpen} />}
          {tab === "script" && <ScriptView j={j} />}
          {tab === "qc" && <QC j={j} />}
          {tab === "publish" && <Pubs j={j} />}
          {tab === "costs" && <Costs j={j} />}
        </div>
      </div>

      <StepModal j={j} agent={stepOpen} onClose={() => setStepOpen(null)} onRerun={(a) => act("rr", "rerun", `Reprocessando a partir de ${STEP_LABEL[a]}`, { step: a })} />
      <RejectModal open={reject} onClose={() => setReject(false)} onConfirm={(reason) => { setReject(false); act("rj", "reject", "Produção rejeitada", { reason }); }} />
    </div>
  );
}

function AwaitingInput({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const { data } = useSWR(`/manual-requests?production_job_id=${jobId}&status=pending,answered`);
  const req = data?.[0];
  return (
    <section className="rounded-[var(--radius-frame)] border-2 border-cue bg-cue-soft/50 p-4">
      <h2>{req?.title || "Resposta do Claude"}: falta só você</h2>
      <p className="mb-4 mt-1 text-sm text-muted">Esta produção usa o Claude pela sua assinatura. É um único copiar e colar por vídeo: o resto (personagens, voz, animação, legendas e publicação) a fábrica faz sozinha.</p>
      {req ? <ManualPrompt requestId={req.id} onDone={onDone} /> : <Loading />}
    </section>
  );
}

function Scenes({ j, onChange }: { j: any; onChange: () => void }) {
  const [edit, setEdit] = useState<any>(null);
  const { busy, run } = useAction();
  if (!j.scenes.length) return <Empty title="Cenas ainda não planejadas">Elas aparecem depois do Planejamento de cenas.</Empty>;
  const locked = j.status === "running";
  return (
    <div className="space-y-3">
      {j.scenes.map((s: any) => (
        <article key={s.id} className="grid gap-4 rounded-[var(--radius-frame)] border border-line bg-surface p-3 sm:grid-cols-[110px_1fr]">
          <div className="aspect-[9/16] w-[110px] overflow-hidden rounded bg-ink/10">
            {s.clip ? <video src={`${s.clip.url}#t=1`} muted loop playsInline className="size-full object-cover" onMouseEnter={(e) => e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} />
              : <div className="flex size-full items-center justify-center text-xs text-muted">sem clipe</div>}
          </div>
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3>Cena {s.index + 1} · {s.title}</h3>
              <div className="flex items-center gap-1.5 text-xs text-muted">
                <span className="num">{secs(s.duration_s)}</span> · {s.visual_mode === "animation_2d" ? "animação 2D" : s.visual_mode === "ai_image" ? "imagem IA" : "vídeo IA"} · {s.camera} · {s.location_name}
                {s.status === "failed" && <Pill tone="onair">falhou</Pill>}
              </div>
            </div>
            {s.narration && <p className="text-sm"><span className="text-muted">Narração:</span> {s.narration}</p>}
            {s.dialogue.map((d: any, i: number) => <p key={i} className="text-sm"><strong>{d.character}:</strong> {d.text} <span className="text-xs text-muted">({d.emotion})</span></p>)}
            {s.audio && <audio src={s.audio.url} controls preload="none" className="h-8 w-full max-w-sm" />}
            {s.error && <p className="text-xs text-onair">{s.error}</p>}
            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" disabled={locked} onClick={() => setEdit(s)}>Editar cena</Button>
              <Button size="sm" disabled={locked} busy={busy === `v${s.index}`} onClick={() => run(`v${s.index}`, async () => { await api(`/productions/${j.id}/scenes/${s.index}/rerender`, { body: {} }); onChange(); }, "Cena enviada para nova renderização")}>Renderizar de novo</Button>
              <Button size="sm" disabled={locked} busy={busy === `a${s.index}`} onClick={() => run(`a${s.index}`, async () => { await api(`/productions/${j.id}/scenes/${s.index}/rerender`, { body: { regenerate_audio: true } }); onChange(); }, "Áudio da cena será gerado de novo")}>Refazer áudio</Button>
              {s.visual_mode !== "animation_2d" && <Button size="sm" disabled={locked} onClick={() => run(`i${s.index}`, async () => { await api(`/productions/${j.id}/scenes/${s.index}/rerender`, { body: { regenerate_visual: true } }); onChange(); }, "Visual será gerado de novo")}>Refazer visual</Button>}
            </div>
          </div>
        </article>
      ))}
      <SceneEditor scene={edit} jobId={j.id} onClose={() => setEdit(null)} onSaved={onChange} />
    </div>
  );
}

function SceneEditor({ scene, jobId, onClose, onSaved }: { scene: any; jobId: number; onClose: () => void; onSaved: () => void }) {
  const [narr, setNarr] = useState("");
  const [lines, setLines] = useState("");
  const [cam, setCam] = useState("static");
  const [text, setText] = useState("");
  const { busy, run } = useAction();
  const [key, setKey] = useState<number | null>(null);
  if (scene && key !== scene.id) {
    setKey(scene.id); setNarr(scene.narration); setCam(scene.camera); setText(scene.on_screen_text || "");
    setLines(scene.dialogue.map((d: any) => `${d.character}: ${d.text}`).join("\n"));
  }
  return (
    <Modal open={!!scene} onClose={onClose} title={scene ? `Editar cena ${scene.index + 1}` : ""} wide
      footer={<Button variant="primary" busy={!!busy} onClick={() => run("s", async () => {
        const dialogue = lines.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
          const [c, ...rest] = l.split(":"); const prev = scene.dialogue.find((d: any) => d.character === c.trim());
          return { character: c.trim(), text: rest.join(":").trim(), emotion: prev?.emotion || "neutral" };
        }).filter((d) => d.text);
        await api(`/productions/${jobId}/scenes/${scene.index}`, { method: "PATCH", body: { narration: narr, dialogue, camera: cam, on_screen_text: text } });
        onSaved(); onClose();
      }, "Cena salva. Somente as partes alteradas serão refeitas.")}>Salvar e reprocessar</Button>}>
      <div className="space-y-4">
        <Field label="Narração"><Textarea rows={3} value={narr} onChange={(e) => setNarr(e.target.value)} /></Field>
        <Field label="Diálogos" hint="Uma fala por linha, no formato Nome: texto"><Textarea rows={4} value={lines} onChange={(e) => setLines(e.target.value)} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Câmera"><Select value={cam} onChange={(e) => setCam(e.target.value)}>
            {["static", "zoom_in", "zoom_out", "slow_zoom", "pan_left", "pan_right", "shake"].map((c) => <option key={c}>{c}</option>)}</Select></Field>
          <Field label="Texto na tela"><Input value={text} maxLength={80} onChange={(e) => setText(e.target.value)} /></Field>
        </div>
        <p className="text-xs text-muted">Salvar cria uma nova versão do roteiro. Cenas não alteradas reaproveitam o render anterior.</p>
      </div>
    </Modal>
  );
}

function Steps({ j, onOpen }: { j: any; onOpen: (a: string) => void }) {
  return (
    <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
      {j.steps.map((s: any) => (
        <button key={s.id} onClick={() => onOpen(s.agent)} className="flex w-full items-center justify-between gap-3 border-b border-line/70 px-4 py-2.5 text-left text-sm last:border-0 hover:bg-paper/60">
          <span className="flex items-center gap-2"><span className="frame inline-block size-3" data-s={s.status} />{STEP_LABEL[s.agent]}</span>
          <span className="flex items-center gap-3 text-xs text-muted">
            {s.providers_used?.length > 0 && <span>{s.providers_used.join(", ")}</span>}
            <span className="num">{ms(s.duration_ms)}</span><span className="num">{usd(s.cost_usd, 4)}</span>
            {s.attempts > 1 && <span>{s.attempts} tentativas</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

function StepModal({ j, agent, onClose, onRerun }: { j: any; agent: string | null; onClose: () => void; onRerun: (a: string) => void }) {
  const s = (j.steps || []).find((x: any) => x.agent === agent);
  return (
    <Modal open={!!s} onClose={onClose} title={s ? STEP_LABEL[s.agent] : ""} wide
      footer={s && <Button disabled={j.status === "running"} onClick={() => { onRerun(s.agent); onClose(); }}>Reprocessar a partir desta etapa</Button>}>
      {s && <div className="space-y-3 text-sm">
        <div className="text-muted">Status: {s.status} · tentativas {s.attempts}/{s.max_attempts} · {ms(s.duration_ms)} · {usd(s.cost_usd, 4)}</div>
        {s.error && <pre className="whitespace-pre-wrap rounded bg-onair-soft p-3 text-xs text-onair">{s.error}</pre>}
        <div><div className="mb-1 font-medium">Saída</div><pre className="max-h-64 overflow-auto rounded bg-paper p-3 text-xs scroll-thin">{JSON.stringify(s.output, null, 2)}</pre></div>
        {s.events?.length > 0 && <div><div className="mb-1 font-medium">Registro</div>
          <ul className="max-h-48 space-y-1 overflow-auto text-xs scroll-thin">{s.events.filter((e: any) => !e.data?.trace).map((e: any, i: number) => <li key={i}><span className="text-muted">{dt(e.ts)}</span> {e.msg} {e.data && <code className="text-muted">{JSON.stringify(e.data)}</code>}</li>)}</ul></div>}
      </div>}
    </Modal>
  );
}

function RejectModal({ open, onClose, onConfirm }: { open: boolean; onClose: () => void; onConfirm: (r: string) => void }) {
  const [r, setR] = useState("");
  return (
    <Modal open={open} onClose={onClose} title="Rejeitar produção" footer={<Button variant="danger" onClick={() => onConfirm(r)}>Rejeitar</Button>}>
      <Field label="Motivo" hint="Fica registrado na auditoria e ajuda a calibrar as próximas produções."><Textarea value={r} onChange={(e) => setR(e.target.value)} /></Field>
    </Modal>
  );
}

function ScriptView({ j }: { j: any }) {
  const v = j.script_version;
  if (!v) return <Empty title="Roteiro ainda não escrito" />;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
        Versão {v.version} · {v.created_by} · {v.provider} {v.is_simulated && <Simulated />}
        <Link className="ml-auto text-reel" href={`/scripts/${j.script.id}`}>Abrir no editor de roteiros</Link>
      </div>
      <Panel title="Sinopse"><p className="text-sm">{v.synopsis}</p><p className="mt-3 text-sm"><strong>Gancho:</strong> {v.hook}</p><p className="mt-1 text-sm"><strong>Encerramento:</strong> {v.closing}</p></Panel>
      <Panel title="História completa"><p className="whitespace-pre-line text-sm leading-relaxed">{v.full_story}</p></Panel>
      {v.content?.fact_check && <Panel title="Verificação de fatos"><ul className="space-y-2 text-sm">{v.content.fact_check.map((c: any, i: number) => (
        <li key={i}><Pill tone={c.verified ? "preview" : "onair"}>{c.verified ? "verificado" : "não verificado"}</Pill> {c.claim} {c.sources?.length > 0 && <span className="text-xs text-muted">({c.sources.join(", ")})</span>} {c.note && <span className="text-xs text-muted">— {c.note}</span>}</li>))}</ul></Panel>}
    </div>
  );
}

function QC({ j }: { j: any }) {
  const r = j.qc_report;
  if (!r?.checks) return <Empty title="Controle de qualidade ainda não executado" />;
  return (
    <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line px-4 py-3 text-sm">
        <Pill tone={r.passed ? "preview" : "onair"} dot>{r.passed ? "Aprovado" : "Reprovado"}</Pill>
        <span className="text-muted">{r.fail_count} falha(s), {r.warn_count} alerta(s) · {dt(r.checked_at)}</span>
      </div>
      {r.checks.map((c: any, i: number) => (
        <div key={i} className="flex items-start gap-3 border-b border-line/70 px-4 py-2.5 text-sm last:border-0">
          <span className={c.status === "ok" ? "text-preview" : c.status === "warn" ? "text-cue" : "text-onair"}>●</span>
          <div><div className="font-medium">{QC_LABEL[c.key] || c.key}</div><div className="text-muted">{c.detail}</div></div>
        </div>
      ))}
    </div>
  );
}
const QC_LABEL: Record<string, string> = {
  resolution: "Resolução", aspect_ratio: "Proporção", fps: "Taxa de quadros", duration: "Duração", file_size: "Tamanho do arquivo",
  audio_stream: "Trilha de áudio", loudness: "Volume (loudness)", silence: "Silêncios", black_frames: "Quadros pretos", subtitles: "Legendas",
  scenes_complete: "Cenas completas", script_coherence: "Coerência com o roteiro", speech_sync: "Sincronia das falas",
  character_continuity: "Continuidade dos personagens", licenses: "Direitos de uso", images_valid: "Imagens íntegras",
  simulated_content: "Conteúdo simulado", editorial_review: "Revisão editorial", file_readable: "Arquivo legível", video_stream: "Trilha de vídeo",
};

function Pubs({ j }: { j: any }) {
  if (!j.publications.length) return <Empty title="Sem publicações preparadas">O Publicador prepara título, descrição e hashtags por plataforma depois do controle de qualidade.</Empty>;
  return (
    <div className="space-y-3">
      {j.publications.map((p: any) => (
        <div key={p.id} className="rounded-[var(--radius-frame)] border border-line bg-surface p-4 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong>{PLATFORM[p.platform_key]}</strong>
            <span className="flex items-center gap-2"><Pill tone={PUB_STATUS[p.status]?.tone}>{PUB_STATUS[p.status]?.label}</Pill><span className="text-muted">{p.mode === "api" ? "API oficial" : "assistida"}</span></span>
          </div>
          <div className="mt-2 font-medium">{p.title}</div>
          <p className="mt-1 whitespace-pre-line text-muted">{p.description}</p>
          <div className="mt-1 text-reel">{p.hashtags.join(" ")}</div>
          <div className="mt-2 text-xs text-muted">{p.scheduled_at ? `Agendado para ${dt(p.scheduled_at)}` : "Ainda não agendado"} {p.url && <a href={p.url} target="_blank" className="ml-2 text-reel">Abrir publicação</a>}</div>
        </div>
      ))}
      <Link href="/publications" className="text-sm text-reel">Gerenciar publicações</Link>
    </div>
  );
}

function Costs({ j }: { j: any }) {
  return (
    <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
      {j.costs.length === 0 && <p className="p-4 text-sm text-muted">Nenhuma chamada a provedores registrada.</p>}
      {j.costs.map((c: any, i: number) => (
        <div key={i} className="flex justify-between border-b border-line/70 px-4 py-2.5 text-sm last:border-0">
          <span>{c.provider} <span className="text-muted">({c.kind}, {c.calls} chamadas)</span></span><span className="num">{usd(c.cost_usd, 4)}</span>
        </div>
      ))}
      <div className="flex justify-between px-4 py-3 text-sm font-medium"><span>Total</span><span className="num">{usd(j.actual_cost_usd, 4)}</span></div>
    </div>
  );
}
