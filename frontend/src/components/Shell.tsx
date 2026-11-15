"use client";
import clsx from "clsx";
import {
  Activity, BarChart3, Bell, BookOpen, CalendarDays, Clapperboard, Coins, Film, FolderOpen, Lightbulb, LogOut, Menu, Mic2,
  Radio, Send, Settings, Sparkles, TrendingUp, Tv, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { useLiveEvents } from "@/lib/live";
import { Loading } from "./ui";

const NAV: { group: string; items: { href: string; label: string; icon: any }[] }[] = [
  { group: "Fábrica", items: [
    { href: "/", label: "Visão geral", icon: Tv },
    { href: "/monitor", label: "Monitor", icon: Activity },
    { href: "/production", label: "Produção", icon: Clapperboard },
    { href: "/calendar", label: "Calendário", icon: CalendarDays },
    { href: "/publications", label: "Publicações", icon: Send },
  ] },
  { group: "Criação", items: [
    { href: "/trends", label: "Tendências", icon: TrendingUp },
    { href: "/ideas", label: "Ideias", icon: Lightbulb },
    { href: "/scripts", label: "Roteiros", icon: BookOpen },
    { href: "/series", label: "Séries e universos", icon: Film },
    { href: "/characters", label: "Personagens", icon: Users },
    { href: "/voices", label: "Vozes", icon: Mic2 },
    { href: "/library", label: "Biblioteca", icon: FolderOpen },
  ] },
  { group: "Resultados", items: [
    { href: "/analytics", label: "Analytics", icon: BarChart3 },
    { href: "/costs", label: "Custos", icon: Coins },
  ] },
  { group: "Sistema", items: [
    { href: "/channels", label: "Canais", icon: Radio },
    { href: "/settings", label: "Configurações", icon: Settings },
  ] },
];

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [bell, setBell] = useState(false);
  const { data: me, error } = useSWR("/auth/me");
  const { data: notes, mutate } = useSWR("/notifications?limit=12", { refreshInterval: 60000 });
  const live = useLiveEvents();
  if (error) return null; // redirecionado ao login pelo cliente da API
  if (!me) return <div className="p-8"><Loading /></div>;

  const nav = (
    <nav className="flex flex-col gap-5 px-3 py-4">
      {NAV.map((g) => (
        <div key={g.group}>
          <div className="px-2 pb-1 text-xs text-white/45">{g.group}</div>
          {g.items.map((it) => {
            const active = it.href === "/" ? path === "/" : path.startsWith(it.href);
            const Icon = it.icon;
            return (
              <Link key={it.href} href={it.href} onClick={() => setOpen(false)}
                className={clsx("flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm",
                  active ? "bg-white/12 text-white" : "text-white/70 hover:bg-white/6 hover:text-white")}>
                <Icon size={16} strokeWidth={1.8} />
                {it.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[232px_1fr]">
      <aside className={clsx("fixed inset-y-0 left-0 z-40 w-[260px] overflow-y-auto bg-ink scroll-thin transition-transform lg:sticky lg:top-0 lg:h-dvh lg:w-auto lg:translate-x-0",
        open ? "translate-x-0" : "-translate-x-full")}>
        <div className="flex items-center justify-between px-5 pt-5">
          <Link href="/" className="flex items-center gap-2 text-white">
            <Sparkles size={18} className="text-cue" />
            <span className="font-display text-lg font-semibold">Content Factory</span>
          </Link>
          <button className="text-white/60 lg:hidden" aria-label="Fechar menu" onClick={() => setOpen(false)}><X size={18} /></button>
        </div>
        {nav}
        <div className="mt-auto border-t border-white/10 px-5 py-4 text-xs text-white/60">
          <div className="flex items-center gap-2">
            <span className={clsx("size-2 rounded-full", live ? "bg-preview" : "bg-white/30")} />
            {live ? "Atualização em tempo real" : "Reconectando…"}
          </div>
          <div className="mt-2 truncate text-white/80">{me.name} · {me.role}</div>
          <button className="mt-2 inline-flex items-center gap-1.5 text-white/70 hover:text-white"
            onClick={async () => { await api("/auth/logout", { method: "POST" }); router.push("/login"); }}>
            <LogOut size={14} /> Sair
          </button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-ink/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur lg:px-8">
          <button className="lg:hidden" aria-label="Abrir menu" onClick={() => setOpen(true)}><Menu size={20} /></button>
          <div className="hidden lg:block" />
          <div className="relative">
            <button aria-label="Notificações" onClick={() => setBell(!bell)} className="relative rounded-md p-2 hover:bg-ink/5">
              <Bell size={18} />
              {notes?.unread > 0 && <span className="num absolute -right-0.5 -top-0.5 rounded-full bg-onair px-1.5 text-[10px] font-semibold text-white">{notes.unread}</span>}
            </button>
            {bell && (
              <div className="absolute right-0 top-11 z-30 w-[min(92vw,380px)] rounded-lg border border-line bg-surface shadow-xl">
                <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
                  <span className="text-sm font-medium">Notificações</span>
                  <button className="text-xs text-reel" onClick={async () => { await api("/notifications/read-all", { method: "POST" }); mutate(); }}>Marcar todas como lidas</button>
                </div>
                <ul className="max-h-96 overflow-y-auto scroll-thin">
                  {(notes?.items || []).length === 0 && <li className="px-4 py-6 text-sm text-muted">Nada por aqui.</li>}
                  {(notes?.items || []).map((n: any) => (
                    <li key={n.id} className={clsx("border-b border-line/70 px-4 py-2.5 text-sm last:border-0", !n.is_read && "bg-reel-soft/40")}>
                      <button className="w-full text-left" onClick={async () => {
                        await api(`/notifications/${n.id}/read`, { method: "POST" }); mutate(); setBell(false);
                        if (n.link?.startsWith("/")) router.push(n.link); else if (n.link) window.open(n.link, "_blank");
                      }}>
                        <div className={clsx("font-medium", n.level === "error" && "text-onair")}>{n.title}</div>
                        {n.message && <div className="line-clamp-2 text-xs text-muted">{n.message}</div>}
                        <div className="text-[11px] text-muted">{ago(n.created_at)}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </header>
        <main className="mx-auto max-w-[1280px] px-4 py-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
