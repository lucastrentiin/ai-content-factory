"use client";
import { Sparkles } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <form className="space-y-4" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError(null);
      try { await api("/auth/login", { body: { email, password } }); router.replace(next); } catch (x) { setError(x); } finally { setBusy(false); }
    }}>
      <Field label="E-mail"><Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
      <Field label="Senha"><Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
      <ErrorBox error={error} />
      <Button variant="primary" className="w-full" busy={busy} type="submit">Entrar</Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden bg-ink p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-2"><Sparkles className="text-cue" size={20} /><span className="font-display text-xl font-semibold">Content Factory</span></div>
        <div>
          <div className="filmstrip mb-8 h-10 max-w-md" aria-hidden>
            {["succeeded", "succeeded", "succeeded", "succeeded", "running", "pending", "pending", "pending"].map((s, i) => <span key={i} className="frame" data-s={s} />)}
          </div>
          <p className="max-w-md font-display text-4xl leading-tight">Tendência de manhã. História à tarde. No ar à noite.</p>
          <p className="mt-4 max-w-md text-white/60">Pesquise, roteirize, anime, narre, publique e aprenda com os resultados, com você no controle de cada etapa.</p>
        </div>
        <div className="text-xs text-white/40">Ambiente privado</div>
      </section>
      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h1 className="mb-1">Entrar</h1>
          <p className="mb-6 text-sm text-muted">Use a conta de administrador definida no arquivo .env.</p>
          <Suspense><LoginForm /></Suspense>
        </div>
      </section>
    </main>
  );
}
