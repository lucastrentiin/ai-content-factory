"use client";
import clsx from "clsx";
import { X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Tone } from "@/lib/format";

// ---------------------------------------------------------------- botões e campos
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "quiet"; size?: "sm" | "md"; busy?: boolean };
export function Button({ variant = "ghost", size = "md", busy, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-reel text-white hover:bg-[#4a2fe0]",
        variant === "ghost" && "bg-surface text-ink border border-line hover:border-ink/40",
        variant === "danger" && "bg-surface text-onair border border-onair/40 hover:bg-onair-soft",
        variant === "quiet" && "text-ink-2 hover:bg-ink/5",
        className,
      )}
    >
      {busy && <span className="size-3 rounded-full border-2 border-current border-t-transparent animate-spin" />}
      {children}
    </button>
  );
}

const fieldCls = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-reel focus:outline-none";
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={clsx(fieldCls, "h-9", p.className)} />;
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={clsx(fieldCls, "min-h-20", p.className)} />;
export const Select = ({ className, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={clsx(fieldCls, "h-9 pr-8", className)} />;

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="mb-1 block text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-sm">
      <span className={clsx("relative h-5 w-9 rounded-full transition-colors", checked ? "bg-reel" : "bg-line")}>
        <span className={clsx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
      </span>
      {label}
    </button>
  );
}

// ---------------------------------------------------------------- estados
const toneCls: Record<Tone, string> = {
  neutral: "bg-ink/6 text-ink-2",
  reel: "bg-reel-soft text-reel",
  onair: "bg-onair-soft text-onair",
  preview: "bg-preview-soft text-[#0f8a5d]",
  cue: "bg-cue-soft text-[#a86a00]",
};
export function Pill({ tone = "neutral", children, dot }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", toneCls[tone])}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}
export const Simulated = () => (
  <span title="Gerado por provedor simulado (sem IA real). Configure um provedor em Configurações." className="rounded border border-cue px-1.5 text-[11px] font-semibold text-[#a86a00]">
    simulado
  </span>
);

// ---------------------------------------------------------------- layout
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1>{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ title, actions, children, className, flush }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={clsx("rounded-[var(--radius-frame)] border border-line bg-surface", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          {typeof title === "string" ? <h2 className="text-base">{title}</h2> : title}
          <div className="flex gap-2">{actions}</div>
        </header>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone }) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-muted">{label}</div>
      <div className={clsx("num font-display text-2xl font-semibold", tone === "onair" && "text-onair", tone === "preview" && "text-[#0f8a5d]")}>{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-[var(--radius-frame)] border border-dashed border-line px-5 py-8">
      <h3>{title}</h3>
      {children && <p className="max-w-xl text-sm text-muted">{children}</p>}
      {action}
    </div>
  );
}

export function Loading({ label = "Carregando" }: { label?: string }) {
  return <div className="py-10 text-sm text-muted" role="status">{label}…</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div role="alert" className="rounded-md border border-onair/30 bg-onair-soft px-3 py-2 text-sm text-onair">{(error as Error).message}</div>;
}

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("overflow-x-auto scroll-thin", className)}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-[13px] text-muted">
            {head.map((h, i) => <th key={i} className="px-3 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody className="[&>tr]:border-b [&>tr]:border-line/70 [&>tr:last-child]:border-0 [&_td]:px-3 [&_td]:py-2.5 [&_td]:align-middle">{children}</tbody>
      </table>
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b border-line scroll-thin">
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={clsx("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm", value === it.value ? "border-reel font-medium text-ink" : "border-transparent text-muted hover:text-ink")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Pager({ total, limit, offset, onChange }: { total: number; limit: number; offset: number; onChange: (o: number) => void }) {
  if (total <= limit) return null;
  return (
    <div className="flex items-center justify-between px-3 py-3 text-sm text-muted">
      <span className="num">{offset + 1}–{Math.min(offset + limit, total)} de {total}</span>
      <div className="flex gap-2">
        <Button size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Anterior</Button>
        <Button size="sm" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Próxima</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- modal
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 sm:items-center sm:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title}
        className={clsx("flex max-h-[92vh] w-full flex-col rounded-t-xl bg-surface shadow-2xl sm:rounded-xl", wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2>{title}</h2>
          <button aria-label="Fechar" onClick={onClose} className="rounded p-1 text-muted hover:bg-ink/5"><X size={18} /></button>
        </header>
        <div className="overflow-y-auto px-5 py-4 scroll-thin">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; text: string; tone: Tone };
const ToastCtx = createContext<(text: string, tone?: Tone) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Tone = "neutral") => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, text, tone }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 5200);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="fixed bottom-4 right-4 z-[60] flex w-[min(92vw,380px)] flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={clsx("rounded-lg border bg-surface px-4 py-3 text-sm shadow-lg",
            t.tone === "onair" ? "border-onair/40" : t.tone === "preview" ? "border-preview/40" : "border-line")}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/** Executa uma ação da API mostrando estado de envio e mensagens de sucesso/erro. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const run = useCallback(async <T,>(key: string, fn: () => Promise<T>, success?: string): Promise<T | undefined> => {
    setBusy(key);
    try {
      const r = await fn();
      if (success) toast(success, "preview");
      return r;
    } catch (e) {
      toast((e as Error).message, "onair");
      return undefined;
    } finally {
      setBusy(null);
    }
  }, [toast]);
  return { busy, run };
}

export function JsonField({ value, onChange, rows = 8 }: { value: unknown; onChange: (v: any, valid: boolean) => void; rows?: number }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [err, setErr] = useState<string | null>(null);
  return (
    <div>
      <Textarea rows={rows} spellCheck={false} className="font-mono text-xs" value={text}
        onChange={(e) => {
          setText(e.target.value);
          try { const v = JSON.parse(e.target.value); setErr(null); onChange(v, true); } catch (x) { setErr("JSON inválido"); onChange(null, false); }
        }} />
      {err && <span className="text-xs text-onair">{err}</span>}
    </div>
  );
}
