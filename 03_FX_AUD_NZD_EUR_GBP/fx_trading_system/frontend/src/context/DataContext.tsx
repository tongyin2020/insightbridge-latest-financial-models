import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { apiGet, apiPost, apiPut } from '../hooks/useApi';

interface PriceData {
  pair: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp: string;
}

interface SignalData {
  pair: string;
  direction: string;
  confidence: number;
  regime: string;
  event_mode: boolean;
  override_mode: string;
  risk_check: boolean;
}

interface EventState {
  active: boolean;
  level: string;
  countdown: number;
  price_confirmed: boolean;
  spread_confirmed: boolean;
  structure_confirmed: boolean;
  decision: string;
  pre_event_price: number;
  current_price: number;
  pre_event_range_high: number;
  pre_event_range_low: number;
  spread_threshold: number;
  current_spread: number;
}

interface Trade {
  id: string;
  pair: string;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  pnl: number;
  status: string;
  open_time: string;
  close_time: string | null;
  lots: number;
}

interface Settings {
  [key: string]: any;
}

interface DataContextValue {
  prices: Record<string, PriceData>;
  signals: Record<string, SignalData>;
  eventState: EventState | null;
  trades: Trade[];
  settings: Settings;
  isConnected: boolean;
  fetchSettings: () => Promise<void>;
  updateSetting: (key: string, value: any) => Promise<void>;
  triggerEvent: (level: string) => Promise<void>;
  confirmEvent: () => Promise<void>;
}

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({ children }: { children: ReactNode }) {
  const [prices, setPrices] = useState<Record<string, PriceData>>({});
  const [signals, setSignals] = useState<Record<string, SignalData>>({});
  const [eventState, setEventState] = useState<EventState | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [settings, setSettings] = useState<Settings>({});

  const wsUrl = `ws://${window.location.hostname}:8000/ws`;
  const { lastMessage, isConnected } = useWebSocket(wsUrl);

  // Process incoming WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;
    const msg = lastMessage;

    switch (msg.type) {
      case 'price_update':
        setPrices((prev) => ({
          ...prev,
          [msg.data.pair]: msg.data,
        }));
        break;
      case 'signal_update':
        setSignals((prev) => ({
          ...prev,
          [msg.data.pair]: msg.data,
        }));
        break;
      case 'event_state':
        setEventState(msg.data);
        break;
      case 'trade_update':
        setTrades((prev) => {
          const idx = prev.findIndex((t) => t.id === msg.data.id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = msg.data;
            return updated;
          }
          return [msg.data, ...prev];
        });
        break;
      case 'settings_update':
        setSettings((prev) => ({ ...prev, ...msg.data }));
        break;
      default:
        break;
    }
  }, [lastMessage]);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await apiGet('/settings');
      // Flatten {key: {value, updated_at}} to {key: value}
      const flat: Settings = {};
      for (const [k, v] of Object.entries(data)) {
        flat[k] = typeof v === 'object' && v !== null && 'value' in (v as any) ? (v as any).value : v;
      }
      setSettings(flat);
    } catch (err) {
      console.error('Failed to fetch settings:', err);
    }
  }, []);

  const updateSetting = useCallback(async (key: string, value: any) => {
    try {
      await apiPut(`/settings/${key}`, { value });
      setSettings((prev) => ({ ...prev, [key]: value }));
    } catch (err) {
      console.error('Failed to update setting:', err);
    }
  }, []);

  const triggerEvent = useCallback(async (level: string) => {
    try {
      const data = await apiPost('/event/trigger', { level });
      setEventState(data);
    } catch (err) {
      console.error('Failed to trigger event:', err);
    }
  }, []);

  const confirmEvent = useCallback(async () => {
    try {
      const data = await apiPost('/event/confirm');
      setEventState(data);
    } catch (err) {
      console.error('Failed to confirm event:', err);
    }
  }, []);

  // Initial data load
  useEffect(() => {
    fetchSettings();
    apiGet<any>('/trades?limit=50')
      .then((res) => setTrades(res?.trades ?? res ?? []))
      .catch(() => {});
  }, [fetchSettings]);

  return (
    <DataContext.Provider
      value={{
        prices,
        signals,
        eventState,
        trades,
        settings,
        isConnected,
        fetchSettings,
        updateSetting,
        triggerEvent,
        confirmEvent,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}

export function useData(): DataContextValue {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error('useData must be used within DataProvider');
  return ctx;
}
