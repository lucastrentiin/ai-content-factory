"use client";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { Empty, Input, Loading, PageHeader, Pager, Pill, Simulated, Table } from "@/components/ui";
import { qs } from "@/lib/api";
import { ago } from "@/lib/format";

export default function Scripts() {
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const { data } = useSWR(`/scripts${qs({ q, limit: 30, offset })}`);
  return (
    <div>
      <PageHeader title="Roteiros" description="Roteiros estruturados em cenas, com narração, diálogos, câmera e histórico de versões." />
      <Input className="mb-4 w-64" placeholder="Buscar por título" value={q} onChange={(e) => setQ(e.target.value)} />
      {!data ? <Loading /> : data.items.length === 0 ? <Empty title="Nenhum roteiro">Roteiros são escritos pelo Roteirista quando uma ideia entra em produção.</Empty> : (
        <div className="rounded-[var(--radius-frame)] border border-line bg-surface">
          <Table head={["Título", "Cenas", "Versão", "Status", "Atualizado"]}>
            {data.items.map((s: any) => (
              <tr key={s.id}>
                <td className="max-w-md"><Link href={`/scripts/${s.id}`} className="font-medium hover:text-reel">{s.title}</Link> {s.is_simulated && <Simulated />}
                  <div className="line-clamp-1 text-xs text-muted">{s.synopsis}</div></td>
                <td className="num">{s.scenes}</td><td className="num">v{s.current_version}{s.variant_label && <span className="ml-1 text-xs text-muted">variante {s.variant_label}</span>}</td>
                <td><Pill tone={s.status === "approved" ? "preview" : "neutral"}>{s.status === "approved" ? "Aprovado" : s.status}</Pill></td>
                <td className="text-xs text-muted">{ago(s.updated_at)}</td>
              </tr>
            ))}
          </Table>
          <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} />
        </div>
      )}
    </div>
  );
}
