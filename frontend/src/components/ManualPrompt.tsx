"use client";
import { Check, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Button, Loading, Textarea, useAction } from "./ui";

/** Copiar o prompt → colar no Claude (assinatura) → colar a resposta aqui. */
export function ManualPrompt({ requestId, onDone, compact }: { requestId: number; onDone?: (result: any) => void; compact?: boolean }) {
  const { data: req, mutate } = useSWR(`/manual-requests/${requestId}`);
  const [copied, setCopied] = useState(false);
  const [text, setText] = useState("");
  const [localErr, setLocalErr] = useState<string | null>(null);
  const { busy, run } = useAction();
  if (!req) return <Loading />;
  if (req.status === "cancelled") return <p className="text-sm text-muted">Pedido cancelado.</p>;
  if (req.status === "consumed") return <p className="text-sm text-[#0f8a5d]">Resposta recebida e usada.</p>;

  const copy = async () => {
    try { await navigator.clipboard.writeText(req.prompt); }
    catch {
      const ta = document.createElement("textarea"); ta.value = req.prompt; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    setCopied(true); setTimeout(() => setCopied(false), 2500);
  };
  const check = (v: string) => {
    if (!v.trim()) return setLocalErr(null);
    const s = v.indexOf("{"), e = v.lastIndexOf("}");
    try { JSON.parse(v.slice(s, e + 1)); setLocalErr(null); } catch { setLocalErr("Ainda não parece um JSON completo. Copie a resposta inteira do Claude, do primeiro { ao último }."); }
  };
  const send = () => run("send", async () => {
    const r = await api(`/manual-requests/${requestId}/answer`, { body: { response: text } });
    setText(""); await mutate(); onDone?.(r); return r;
  }, "Resposta enviada. A fábrica continua daqui.");

  return (
    <div className="space-y-4">
      <ol className={`grid gap-4 ${compact ? "" : "lg:grid-cols-3"}`}>
        <li className="rounded-[var(--radius-frame)] border border-line bg-surface p-4">
          <div className="mb-1 font-medium">1. Copie o prompt</div>
          <p className="mb-3 text-sm text-muted">Já contém todas as instruções do canal, do motor e do formato da resposta.</p>
          <Button variant="primary" onClick={copy}>{copied ? <><Check size={15} /> Copiado</> : <><Copy size={15} /> Copiar prompt</>}</Button>
          <details className="mt-3 text-sm"><summary className="cursor-pointer text-muted">Ver o prompt</summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-paper p-3 text-xs scroll-thin">{req.prompt}</pre></details>
        </li>
        <li className="rounded-[var(--radius-frame)] border border-line bg-surface p-4">
          <div className="mb-1 font-medium">2. Cole no Claude</div>
          <p className="mb-3 text-sm text-muted">Abra uma conversa nova com a sua conta, cole o prompt e envie. Espere a resposta terminar.</p>
          <a href="https://claude.ai/new" target="_blank" rel="noreferrer"><Button><ExternalLink size={15} /> Abrir o Claude</Button></a>
        </li>
        <li className="rounded-[var(--radius-frame)] border border-line bg-surface p-4">
          <div className="mb-1 font-medium">3. Traga a resposta</div>
          <p className="text-sm text-muted">Copie a resposta inteira (o botão de copiar embaixo da resposta do Claude) e cole aqui.</p>
        </li>
      </ol>
      {req.error && <div role="alert" className="rounded-md border border-onair/30 bg-onair-soft px-3 py-2 text-sm text-onair">{req.error}</div>}
      <Textarea rows={compact ? 6 : 9} className="font-mono text-xs" placeholder='Cole aqui a resposta do Claude (começa com { ou ```json)'
        value={text} onChange={(e) => { setText(e.target.value); check(e.target.value); }} aria-label="Resposta do Claude" />
      {localErr && <p className="text-sm text-[#a86a00]">{localErr}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" disabled={text.trim().length < 2} busy={busy === "send"} onClick={send}>Enviar resposta</Button>
        <Button variant="quiet" onClick={() => run("cancel", async () => { await api(`/manual-requests/${requestId}/cancel`, { method: "POST" }); await mutate(); onDone?.(null); }, "Pedido cancelado")}>Cancelar pedido</Button>
      </div>
    </div>
  );
}
