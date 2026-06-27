import React, { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts';
import { TrendingUp, Activity, DollarSign, Zap } from 'lucide-react';
import { useData } from '../context/DataContext';
import { useApi, apiGet } from '../hooks/useApi';
import PriceCard from '../components/PriceCard';
import SignalBadge from '../components/SignalBadge';

interface HistoryPoint {
  timestamp: string;
  close: number;
  sma20: number;
  sma50: number;
}

export default function Dashboard() {
  const { prices, signals, trades, isConnected } = useData();
  const { data: events } = useApi<any[]>('/events');
  const [chartPair, setChartPair] = useState('aud_usd');
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [stats, setStats] = useState<any>(null);

  // Fetch price history for chart
  useEffect(() => {
    apiGet<any>(`/prices/${chartPair}/history`)
      .then((res) => setHistory(res?.prices ?? res ?? []))
      .catch(() => setHistory([]));
  }, [chartPair]);

  // Fetch trade stats
  useEffect(() => {
    apiGet('/trades/stats').then(setStats).catch(() => {});
  }, []);

  const recentTrades = Array.isArray(trades) ? trades.slice(0, 10) : [];
  const upcomingEvents = Array.isArray(events) ? events.slice(0, 5) : (events as any)?.events?.slice(0, 5) ?? [];

  const audPrice = prices['AUD/USD'] || prices['aud_usd'] || prices['AUD_USD'];
  const nzdPrice = prices['NZD/USD'] || prices['nzd_usd'] || prices['NZD_USD'];
  const audSignal = signals['AUD/USD'] || signals['aud_usd'] || signals['AUD_USD'];
  const nzdSignal = signals['NZD/USD'] || signals['nzd_usd'] || signals['NZD_USD'];

  const tradesList = Array.isArray(trades) ? trades : [];
  const totalPnl = stats?.total_pnl_usd ?? stats?.total_pnl ?? tradesList.reduce((sum: number, t: any) => sum + (t.pnl_usd || t.pnl || 0), 0);
  const winRate = stats?.win_rate ?? 0;
  const openPositions = stats?.open_trades ?? stats?.open_positions ?? tradesList.filter((t: any) => t.status === 'OPEN').length;

  return (
    <div className="space-y-4">
      {/* Price cards row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <PriceCard
          pair="aud_usd"
          bid={audPrice?.bid ?? 0}
          ask={audPrice?.ask ?? 0}
          spread={audPrice?.spread_pips ?? audPrice?.spread ?? ((audPrice?.ask ?? 0) - (audPrice?.bid ?? 0)) * 10000}
          timestamp={audPrice?.timestamp}
        />
        <PriceCard
          pair="nzd_usd"
          bid={nzdPrice?.bid ?? 0}
          ask={nzdPrice?.ask ?? 0}
          spread={nzdPrice?.spread_pips ?? nzdPrice?.spread ?? ((nzdPrice?.ask ?? 0) - (nzdPrice?.bid ?? 0)) * 10000}
          timestamp={nzdPrice?.timestamp}
        />

        {/* Signal cards */}
        <div className="card">
          <div className="card-header">AUD/USD 信号</div>
          {audSignal ? (
            <SignalBadge direction={audSignal.direction} confidence={audSignal.confidence} />
          ) : (
            <span className="text-slate-500 text-sm">等待信号...</span>
          )}
          {audSignal && (
            <div className="mt-2 text-xs text-slate-500">
              Regime: {audSignal.regime} | Event: {audSignal.event_mode ? '是' : '否'}
            </div>
          )}
        </div>
        <div className="card">
          <div className="card-header">NZD/USD 信号</div>
          {nzdSignal ? (
            <SignalBadge direction={nzdSignal.direction} confidence={nzdSignal.confidence} />
          ) : (
            <span className="text-slate-500 text-sm">等待信号...</span>
          )}
          {nzdSignal && (
            <div className="mt-2 text-xs text-slate-500">
              Regime: {nzdSignal.regime} | Event: {nzdSignal.event_mode ? '是' : '否'}
            </div>
          )}
        </div>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <div className="text-xs text-slate-400">总盈亏</div>
            <div className={`text-lg font-bold font-mono ${totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}
            </div>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <div className="text-xs text-slate-400">胜率</div>
            <div className="text-lg font-bold font-mono text-blue-400">{(winRate * 100).toFixed(1)}%</div>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <div className="text-xs text-slate-400">持仓数</div>
            <div className="text-lg font-bold font-mono text-amber-400">{openPositions}</div>
          </div>
        </div>
        <div className="card flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
            <Zap className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <div className="text-xs text-slate-400">系统状态</div>
            <div className={`text-lg font-bold ${isConnected ? 'text-emerald-400' : 'text-red-400'}`}>
              {isConnected ? '运行中' : '离线'}
            </div>
          </div>
        </div>
      </div>

      {/* Chart + Events sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Price chart */}
        <div className="lg:col-span-2 card">
          <div className="flex items-center justify-between mb-4">
            <h3 className="card-header mb-0">价格走势</h3>
            <div className="flex gap-2">
              <button
                onClick={() => setChartPair('aud_usd')}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  chartPair === 'aud_usd' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
                }`}
              >
                AUD/USD
              </button>
              <button
                onClick={() => setChartPair('nzd_usd')}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  chartPair === 'nzd_usd' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
                }`}
              >
                NZD/USD
              </button>
            </div>
          </div>
          <div className="h-72">
            {history.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={history}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="timestamp"
                    stroke="#64748b"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(val) => {
                      const d = new Date(val);
                      return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
                    }}
                  />
                  <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    labelFormatter={(val) => new Date(val).toLocaleString()}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={2} name="Price" />
                  <Line type="monotone" dataKey="sma20" stroke="#f59e0b" dot={false} strokeWidth={1} strokeDasharray="4 2" name="SMA20" />
                  <Line type="monotone" dataKey="sma50" stroke="#a855f7" dot={false} strokeWidth={1} strokeDasharray="4 2" name="SMA50" />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">
                加载中...
              </div>
            )}
          </div>
        </div>

        {/* Upcoming Events sidebar */}
        <div className="card">
          <h3 className="card-header">即将发布的事件</h3>
          <div className="space-y-3">
            {upcomingEvents.length > 0 ? (
              upcomingEvents.map((evt: any, i: number) => (
                <div key={i} className={`p-2 rounded-lg bg-slate-900/50 border-l-2 ${
                  evt.impact === 'A' ? 'border-red-500' : evt.impact === 'B' ? 'border-amber-500' : 'border-slate-600'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-400">{evt.time || evt.datetime}</span>
                    <span className={`text-xs font-bold ${
                      evt.impact === 'A' ? 'text-red-400' : evt.impact === 'B' ? 'text-amber-400' : 'text-slate-400'
                    }`}>
                      {evt.impact}
                    </span>
                  </div>
                  <div className="text-sm text-white mt-1">{evt.event || evt.name}</div>
                  <div className="text-xs text-slate-500">{evt.country}</div>
                </div>
              ))
            ) : (
              <div className="text-slate-500 text-sm">暂无事件数据</div>
            )}
          </div>
        </div>
      </div>

      {/* Signal State Panel + Recent Trades */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Signal State Panel */}
        <div className="card">
          <h3 className="card-header">信号状态详情</h3>
          <div className="space-y-2">
            {['aud_usd', 'nzd_usd'].map((pair) => {
              const sig = signals[pair] || signals[pair.toUpperCase()];
              if (!sig) return (
                <div key={pair} className="text-sm text-slate-500">{pair.replace('_', '/').toUpperCase()}: 无信号</div>
              );
              return (
                <div key={pair} className="bg-slate-900/50 rounded-lg p-3">
                  <div className="text-sm font-medium text-white mb-2">{pair.replace('_', '/').toUpperCase()}</div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                    <div className="text-slate-400">方向</div>
                    <div className={sig.direction === 'BUY' ? 'text-emerald-400' : sig.direction === 'SELL' ? 'text-red-400' : 'text-amber-400'}>
                      {sig.direction}
                    </div>
                    <div className="text-slate-400">置信度</div>
                    <div className="text-white font-mono">{sig.confidence?.toFixed(1)}%</div>
                    <div className="text-slate-400">市场状态</div>
                    <div className="text-white">{sig.regime}</div>
                    <div className="text-slate-400">事件模式</div>
                    <div className={sig.event_mode ? 'text-amber-400' : 'text-slate-400'}>{sig.event_mode ? '开启' : '关闭'}</div>
                    <div className="text-slate-400">覆盖模式</div>
                    <div className="text-white">{sig.override_mode}</div>
                    <div className="text-slate-400">风控检查</div>
                    <div className={sig.risk_check ? 'text-emerald-400' : 'text-red-400'}>{sig.risk_check ? '通过' : '未通过'}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Trades table */}
        <div className="card">
          <h3 className="card-header">最近交易</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="text-left py-2 px-1">交易对</th>
                  <th className="text-left py-2 px-1">方向</th>
                  <th className="text-right py-2 px-1">入场价</th>
                  <th className="text-right py-2 px-1">盈亏</th>
                  <th className="text-left py-2 px-1">状态</th>
                  <th className="text-left py-2 px-1">时间</th>
                </tr>
              </thead>
              <tbody>
                {recentTrades.length > 0 ? recentTrades.map((trade, i) => (
                  <tr key={trade.id || i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-1.5 px-1 text-white">{trade.pair?.replace('_', '/').toUpperCase()}</td>
                    <td className="py-1.5 px-1">
                      <span className={trade.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>
                        {trade.direction}
                      </span>
                    </td>
                    <td className="py-1.5 px-1 text-right font-mono text-slate-300">{trade.entry_price?.toFixed(5)}</td>
                    <td className={`py-1.5 px-1 text-right font-mono ${(trade.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {(trade.pnl || 0) >= 0 ? '+' : ''}{(trade.pnl || 0).toFixed(2)}
                    </td>
                    <td className="py-1.5 px-1">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        trade.status === 'open' ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-600/30 text-slate-400'
                      }`}>
                        {trade.status === 'open' ? '持仓' : '已平'}
                      </span>
                    </td>
                    <td className="py-1.5 px-1 text-slate-500">{trade.open_time ? new Date(trade.open_time).toLocaleTimeString() : '-'}</td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={6} className="py-4 text-center text-slate-500">暂无交易记录</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
