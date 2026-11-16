export const usd = (v?: number | null, digits = 2) =>
  v == null ? "—" : `US$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, 4) })}`;
export const int = (v?: number | null) => (v == null ? "—" : v.toLocaleString("pt-BR"));
export const pct = (v?: number | null, d = 0) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
export const dt = (v?: string | null) =>
  v ? new Date(v).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
export const day = (v?: string | null) => (v ? new Date(v).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }) : "—");
export const secs = (v?: number | null) => (v == null ? "—" : v >= 60 ? `${Math.floor(v / 60)}min ${Math.round(v % 60)}s` : `${v.toFixed(1)}s`);
export const ms = (v?: number | null) => (v == null ? "—" : v > 60000 ? `${(v / 60000).toFixed(1)} min` : v > 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);
export function ago(v?: string | null) {
  if (!v) return "—";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "agora";
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  return `há ${Math.floor(s / 86400)} d`;
}

export const JOB_STATUS: Record<string, { label: string; tone: Tone }> = {
  queued: { label: "Na fila", tone: "neutral" },
  running: { label: "Produzindo", tone: "onair" },
  paused: { label: "Aguardando você", tone: "cue" },
  awaiting_input: { label: "Cole a resposta do Claude", tone: "cue" },
  awaiting_approval: { label: "Aguardando aprovação", tone: "cue" },
  needs_review: { label: "Precisa de revisão", tone: "cue" },
  approved: { label: "Aprovado", tone: "preview" },
  completed: { label: "Concluído", tone: "preview" },
  failed: { label: "Falhou", tone: "onair" },
  cancelled: { label: "Cancelado", tone: "neutral" },
  blocked_budget: { label: "Bloqueado por custo", tone: "onair" },
};
export const PUB_STATUS: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Rascunho", tone: "neutral" },
  scheduled: { label: "Agendado", tone: "reel" },
  publishing: { label: "Enviando", tone: "onair" },
  processing: { label: "Processando", tone: "cue" },
  published: { label: "Publicado", tone: "preview" },
  failed: { label: "Falhou", tone: "onair" },
  awaiting_manual: { label: "Publicar manualmente", tone: "cue" },
  cancelled: { label: "Cancelado", tone: "neutral" },
};
export const STEP_LABEL: Record<string, string> = {
  story_writer: "Roteirista", script_editor: "Editor de roteiro", fact_checker: "Verificação de fatos",
  character_designer: "Personagens", art_director: "Direção de arte", scene_planner: "Planejamento de cenas",
  voice_director: "Direção de voz", audio_generator: "Áudio", visual_generator: "Visual por IA",
  video_editor: "Edição e render", quality_controller: "Controle de qualidade", publisher: "Publicação",
  trend_researcher: "Pesquisa de tendências", trend_analyst: "Análise de tendências", idea_generator: "Geração de ideias",
  factory_planner: "Planejador", analytics_agent: "Métricas", optimization_agent: "Otimização",
};
export const PLATFORM: Record<string, string> = { youtube: "YouTube Shorts", tiktok: "TikTok", instagram: "Instagram Reels" };
export type Tone = "neutral" | "reel" | "onair" | "preview" | "cue";
