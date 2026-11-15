"use client";
import { useEffect, useRef, useState } from "react";
import { mutate } from "swr";

export type LiveEvent = { type: string; ts: string; data: Record<string, any> };

/** Assina eventos em tempo real (WebSocket). Revalida caches relevantes; reconecta com backoff. */
export function useLiveEvents(onEvent?: (e: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;
  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let delay = 1000;
    let timer: ReturnType<typeof setTimeout>;
    const connect = () => {
      const url = `${location.protocol === "https:" ? "wss" : "ws"}://${process.env.NEXT_PUBLIC_WS_HOST || location.host}/api/ws`;
      ws = new WebSocket(url);
      ws.onopen = () => { setConnected(true); delay = 1000; };
      ws.onclose = () => {
        setConnected(false);
        if (!stop) timer = setTimeout(connect, (delay = Math.min(delay * 2, 30000)));
      };
      ws.onmessage = (m) => {
        try {
          const e = JSON.parse(m.data) as LiveEvent;
          if (e.type === "ping") return;
          cb.current?.(e);
          if (e.type.startsWith("production") || e.type.startsWith("step")) {
            mutate((k) => typeof k === "string" && (k.startsWith("/productions") || k.startsWith("/monitor") || k.startsWith("/dashboard")));
          }
          if (e.type === "notification") mutate((k) => typeof k === "string" && k.startsWith("/notifications"));
        } catch { /* ignora */ }
      };
    };
    connect();
    return () => { stop = true; clearTimeout(timer); ws?.close(); };
  }, []);
  return connected;
}
