import { STEP_LABEL } from "@/lib/format";

type Step = { agent: string; status: string; next_retry_at?: string | null; error?: string | null };

/** Película de produção: cada quadro é um agente; cores de "tally" indicam o estado. */
export function FilmStrip({ steps, height = 18, onPick }: { steps: Step[]; height?: number; onPick?: (agent: string) => void }) {
  if (!steps?.length) return null;
  return (
    <div className="filmstrip" style={{ height: height + 14 }} role="list" aria-label="Etapas da produção">
      {steps.map((s) => {
        const label = `${STEP_LABEL[s.agent] || s.agent}: ${statusText(s)}`;
        return onPick ? (
          <button key={s.agent} role="listitem" className="frame" data-s={s.status} data-retry={s.next_retry_at ? 1 : 0}
            title={label} aria-label={label} onClick={() => onPick(s.agent)} />
        ) : (
          <span key={s.agent} role="listitem" className="frame" data-s={s.status} data-retry={s.next_retry_at ? 1 : 0} title={label} aria-label={label} />
        );
      })}
    </div>
  );
}

function statusText(s: Step) {
  if (s.status === "pending" && s.next_retry_at) return "nova tentativa agendada";
  return ({ pending: "pendente", running: "em execução", succeeded: "concluída", failed: "falhou", skipped: "não se aplica", cancelled: "cancelada" } as Record<string, string>)[s.status] || s.status;
}
