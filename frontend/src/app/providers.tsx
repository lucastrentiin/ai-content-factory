"use client";
import { SWRConfig } from "swr";
import { ToastProvider } from "@/components/ui";
import { fetcher } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig value={{ fetcher, revalidateOnFocus: true, shouldRetryOnError: (e: any) => e?.status !== 401 && e?.status !== 403 }}>
      <ToastProvider>{children}</ToastProvider>
    </SWRConfig>
  );
}
