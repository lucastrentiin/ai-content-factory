// Cliente da API (mesma origem: /api é encaminhado ao FastAPI). Autenticação por cookie httpOnly.
export class ApiError extends Error {
  status: number;
  errors?: { field: string; msg: string }[];
  constructor(status: number, message: string, errors?: { field: string; msg: string }[]) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

async function handle(res: Response) {
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    }
    const msg = typeof body === "object" && body ? body.detail || "Erro inesperado" : String(body).slice(0, 200);
    const errs = typeof body === "object" && body ? body.errors : undefined;
    const full = errs?.length ? `${msg}: ${errs.map((e: { field: string; msg: string }) => `${e.field} — ${e.msg}`).join("; ")}` : msg;
    throw new ApiError(res.status, full, errs);
  }
  return body;
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const init: RequestInit = { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), credentials: "include" };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "Content-Type": "application/json" };
  }
  return handle(await fetch(`/api${path}`, init));
}

export const fetcher = (path: string) => api(path);

export function qs(params: Record<string, unknown>) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}
