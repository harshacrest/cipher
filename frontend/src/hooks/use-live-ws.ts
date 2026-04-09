"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface LiveEvent {
  type: "init" | "spot" | "order_event" | "position" | "log";
  data: Record<string, any>;
}

export interface LiveLog {
  level: string;
  msg: string;
  ts: number;
}

export interface LiveState {
  connected: boolean;
  spotPrice: number;
  positions: Record<string, any>[];
  logs: LiveLog[];
  events: LiveEvent[];
  pnlHistory: { time: number; value: number }[];
}

const WS_URL = "ws://localhost:1156/ws";
const MAX_LOGS = 100;
const MAX_EVENTS = 200;

export function useLiveWebSocket(enabled: boolean): LiveState {
  const [connected, setConnected] = useState(false);
  const [spotPrice, setSpotPrice] = useState(0);
  const [positions, setPositions] = useState<Record<string, any>[]>([]);
  const [logs, setLogs] = useState<LiveLog[]>([]);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [pnlHistory, setPnlHistory] = useState<{ time: number; value: number }[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onclose = () => {
        setConnected(false);
        if (enabled) {
          reconnectTimer.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => ws.close();

      ws.onmessage = (evt) => {
        try {
          const msg: LiveEvent = JSON.parse(evt.data);
          handleMessage(msg);
        } catch {}
      };
    } catch {}
  }, [enabled]);

  const handleMessage = useCallback((msg: LiveEvent) => {
    setEvents((prev) => [...prev.slice(-(MAX_EVENTS - 1)), msg]);

    switch (msg.type) {
      case "init":
        setSpotPrice(msg.data.spot_price || 0);
        if (msg.data.logs) {
          setLogs(msg.data.logs);
        }
        break;

      case "spot":
        setSpotPrice(msg.data.price);
        setPnlHistory((prev) => [
          ...prev,
          { time: msg.data.ts / 1000, value: msg.data.price },
        ]);
        break;

      case "order_event":
        // Order events are shown in the log
        break;

      case "position":
        setPositions((prev) => {
          const idx = prev.findIndex((p) => p.instrument === msg.data.instrument);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = msg.data;
            return next;
          }
          return [...prev, msg.data];
        });
        break;

      case "log":
        setLogs((prev) => [...prev.slice(-(MAX_LOGS - 1)), msg.data as LiveLog]);
        break;
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      wsRef.current?.close();
      setConnected(false);
    }

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [enabled, connect]);

  return { connected, spotPrice, positions, logs, events, pnlHistory };
}
