import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
  PieChart, Pie, Legend,
} from 'recharts';
import { Shield, ToggleLeft, ToggleRight, ChevronLeft, ChevronRight } from 'lucide-react';
import { useData } from '../context/DataContext';
import { apiGet } from '../hooks/useApi';

const RISK_RULES = [
  { key: 'time_stop', label: '时间止损', param: 'max_hold_minutes', unit: '分钟', desc: '持仓超时自动平仓' },
  { key: 'price_stop', label: '价格止损', param: 'stop_loss_pips', unit: 'pips', desc: '固定点数止损' },
  { key: 'profit_target', label: '止盈目标', param: 'take_profit_pips', unit: 'pips', desc: '达到目标自动止盈' },
  { key: 'event_pause', label: '事件暂停', param: 'event_pause_minutes', unit: '分钟', desc: '重大事件前暂停交易' },
  { key: 'spread_protection', label: '点差保护', param: 'max_spread_pips', unit: 'pips', desc: '点差过大暂停入场' },
  { key: 'anomaly_protection', label: '异常保护', param: 'anomaly_threshold', unit: 'x', desc: 'ATR异常波动保护' },
];

export default function RiskManagement() {
  const { settings, updateSetting, trades } = useData();
  const [stats, setStats] = useState<any>(null);
  const [dailyPnl, setDailyPnl] = useState<any[]>([]);
  const [page, setPage] = useState(0);
  const [brokerState, setBrokerState] = useState<any>(null);

  const pageSize = 15;

  useEffect(() => {
    apiGet('/trades/stats').then(setStats).catch(() => {});
    apiGet('/trades/daily_pnl').then(setDailyPnl).catch(() => setDailyPnl([]));
    apiGet('/broker/positions').then(setBrokerState).catch(() => {});
  }, []);

  const tradesList = Array.isArray(trades) ? trades : [];
  const closedTrades = tradesList.filter((t) => t.status === 'CLOSED' || t.status === 'closed' || t.status === 'filled');
  const pagedTrades = closedTrades.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.max(1, Math.ceil(closedTrades.length / pageSize));

  // PnL attribution data for pie chart
  const pnlByPair = tradesList.reduce<Record<string, number>>((acc, t) => {
    const pair = t.pair || 'unknown';
    acc[pair] = (acc[pair] || 0) + (t.pnl || 0);
    return acc;
  }, {});
  const pieData = Object.entries(pnlByPair).map(([name, value]) => ({ name: name.replace('_', '/').toUpperCase(), value: Math.abs(value), raw: value }));
  const PIE_COLORS = ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#a855f7', '#ec4899'];

  return (
    <div className="space-y-4">
      {/* Risk rule cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {RISK_RULES.map((rule) => {
          const enabled = settings[`${rule.key}_enabled`] ?? true;
          const raw = settings[rule.param];
          const paramValue = (typeof raw === 'object' && raw !== null) ? (raw as any).value ?? '-' : raw ?? '-';
          return (
            <div key={rule.key} className="card">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Shield className={`w-4 h-4 ${enabled ? 'text-emerald-400' : 'text-slate-500'}`} />
                  <span className="text-sm font-medium text-white">{rule.label}</span>
                </div>
                <button
                  onClick={() => updateSetting(`${rule.key}_enabled`, !enabled)}
                  className="transition-colors"
                >
                  {enabled ? (
                    <ToggleRight className="w-8 h-8 text-emerald-400" />
                  ) : (
                    <ToggleLeft className="w-8 h-8 text-slate-500" />
                  )}
                </button>
              </div>
              <div className="text-xs text-slate-400 mb-2">{rule.desc}</div>
              <div className="flex items-baseline gap-1">
                <span className="text-lg font-mono font-bold text-white">{paramValue}</span>
                <span className="text-xs text-slate-500">{rule.unit}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Stats + Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Trade performance stats */}
        <div className="card">
          <h3 className="card-header">交易统计</h3>
          <div className="space-y-3">
            {[
              { label: '总交易数', value: stats?.total_trades ?? trades.length },
              { label: '胜率', value: `${((stats?.win_rate ?? 0) * 100).toFixed(1)}%` },
              { label: '盈亏比', value: stats?.profit_factor?.toFixed(2) ?? '-' },
              { label: '最大回撤', value: `${(stats?.max_drawdown ?? 0).toFixed(2)}` },
              { label: '夏普比率', value: stats?.sharpe_ratio?.toFixed(2) ?? '-' },
              { label: '平均持仓时间', value: stats?.avg_hold_time ?? '-' },
              { label: '连续盈利', value: stats?.max_win_streak ?? '-' },
              { label: '连续亏损', value: stats?.max_loss_streak ?? '-' },
            ].map((row, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-slate-400">{row.label}</span>
                <span className="text-white font-mono">{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Daily PnL bar chart */}
        <div className="card">
          <h3 className="card-header">每日盈亏 (近7天)</h3>
          <div className="h-56">
            {dailyPnl.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailyPnl}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {dailyPnl.map((entry, i) => (
                      <Cell key={i} fill={entry.pnl >= 0 ? '#10b981' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">暂无数据</div>
            )}
          </div>
        </div>

        {/* PnL attribution pie chart */}
        <div className="card">
          <h3 className="card-header">盈亏归因</h3>
          <div className="h-56">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    label={({ name, raw }) => `${name}: ${raw >= 0 ? '+' : ''}${raw.toFixed(1)}`}
                    labelLine={false}
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(value: any, name: string, props: any) => [`${props.payload.raw?.toFixed(2)}`, name]}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500">暂无数据</div>
            )}
          </div>
        </div>
      </div>

      {/* Full trade history */}
      <div className="card">
        <h3 className="card-header">交易历史</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-2">ID</th>
                <th className="text-left py-2 px-2">交易对</th>
                <th className="text-left py-2 px-2">方向</th>
                <th className="text-right py-2 px-2">手数</th>
                <th className="text-right py-2 px-2">入场价</th>
                <th className="text-right py-2 px-2">出场价</th>
                <th className="text-right py-2 px-2">盈亏</th>
                <th className="text-left py-2 px-2">开仓时间</th>
                <th className="text-left py-2 px-2">平仓时间</th>
              </tr>
            </thead>
            <tbody>
              {pagedTrades.length > 0 ? pagedTrades.map((t, i) => (
                <tr key={t.id || i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-1.5 px-2 text-slate-500 font-mono">{t.id?.slice(0, 8) ?? '-'}</td>
                  <td className="py-1.5 px-2 text-white">{t.pair?.replace('_', '/').toUpperCase()}</td>
                  <td className="py-1.5 px-2">
                    <span className={t.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>{t.direction}</span>
                  </td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">{t.lots}</td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">{t.entry_price?.toFixed(5)}</td>
                  <td className="py-1.5 px-2 text-right font-mono text-slate-300">{t.exit_price?.toFixed(5) ?? '-'}</td>
                  <td className={`py-1.5 px-2 text-right font-mono ${(t.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {(t.pnl || 0) >= 0 ? '+' : ''}{(t.pnl || 0).toFixed(2)}
                  </td>
                  <td className="py-1.5 px-2 text-slate-400">{t.open_time ? new Date(t.open_time).toLocaleString('zh-CN') : '-'}</td>
                  <td className="py-1.5 px-2 text-slate-400">{t.close_time ? new Date(t.close_time).toLocaleString('zh-CN') : '-'}</td>
                </tr>
              )) : (
                <tr><td colSpan={9} className="py-4 text-center text-slate-500">暂无交易记录</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {/* Pagination */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-700">
          <span className="text-xs text-slate-400">共 {closedTrades.length} 条记录</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="p-1 rounded hover:bg-slate-700 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-xs text-slate-400">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="p-1 rounded hover:bg-slate-700 disabled:opacity-30 transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Broker reconciliation */}
      <div className="card">
        <h3 className="card-header">券商对账</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700 text-xs">
                <th className="text-left py-2 px-2">交易对</th>
                <th className="text-center py-2 px-2">本地持仓</th>
                <th className="text-center py-2 px-2">券商持仓</th>
                <th className="text-center py-2 px-2">状态</th>
              </tr>
            </thead>
            <tbody>
              {brokerState ? (
                (brokerState.positions || []).map((pos: any, i: number) => {
                  const matched = pos.local === pos.broker;
                  return (
                    <tr key={i} className="border-b border-slate-700/50">
                      <td className="py-2 px-2 text-white">{pos.pair?.replace('_', '/').toUpperCase()}</td>
                      <td className="py-2 px-2 text-center font-mono text-slate-300">{pos.local}</td>
                      <td className="py-2 px-2 text-center font-mono text-slate-300">{pos.broker}</td>
                      <td className="py-2 px-2 text-center">
                        {matched ? (
                          <span className="text-emerald-400 text-xs">一致</span>
                        ) : (
                          <span className="text-red-400 text-xs font-bold">不一致</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={4} className="py-4 text-center text-slate-500">等待券商数据...</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
