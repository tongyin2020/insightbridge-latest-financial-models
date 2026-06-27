import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine, BarChart, Bar, Cell } from "recharts";
import { RefreshCw, Activity, Layers, Zap } from "lucide-react";
import { useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const ReplayTab = ({
  replayEvents, replayResult, isReplaying, simResult, isSimulating,
  simConfig, setSimConfig, runReplay, runSimulation, fetchReplayEvents
}) => {
  const [compareResult, setCompareResult] = useState(null);
  const [isComparing, setIsComparing] = useState(false);
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [isOptimizing, setIsOptimizing] = useState(false);

  const runComparison = async () => {
    setIsComparing(true);
    try {
      const res = await axios.post(`${API}/replay/compare`, { config: simConfig });
      setCompareResult(res.data);
    } catch (err) { console.error("Compare error:", err); }
    setIsComparing(false);
  };

  const runOptimizer = async () => {
    setIsOptimizing(true);
    try {
      const res = await axios.post(`${API}/replay/optimize`, {});
      setOptimizeResult(res.data);
    } catch (err) { console.error("Optimize error:", err); }
    setIsOptimizing(false);
  };

  const applyBestConfig = () => {
    if (optimizeResult?.best?.config) {
      const c = optimizeResult.best.config;
      setSimConfig({ min_confidence: c.min_confidence, atr_sl_mult: c.atr_sl_mult, atr_tp1_mult: c.atr_tp1_mult, atr_tp2_mult: c.atr_tp2_mult });
    }
  };

  const shareBestStrategy = async () => {
    if (!optimizeResult?.best) return;
    try {
      const name = prompt("Strategy name:", "Optimized Strategy") || "Optimized Strategy";
      await axios.post(`${API}/social/share`, {
        name,
        description: `Auto-optimized across ${optimizeResult.events_tested} events`,
        config: optimizeResult.best.config,
        performance: {
          total_pnl: optimizeResult.best.total_pnl,
          total_trades: optimizeResult.best.total_trades,
          win_rate: optimizeResult.best.win_rate,
          score: optimizeResult.best.score,
        },
      });
      alert("Strategy shared to leaderboard!");
    } catch (err) { console.error("Share error:", err); }
  };

  return (
  <div className="max-w-6xl mx-auto space-y-6" data-testid="replay-page">
    {/* Multi-Event Comparison Panel */}
    <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-outfit text-lg font-bold flex items-center gap-2">
            <Layers className="w-5 h-5 text-violet-400" />
            Multi-Event Comparison
          </h2>
          <p className="text-xs text-zinc-500 mt-1">Run your strategy across all 8 historical events simultaneously</p>
        </div>
        <button
          data-testid="run-compare-btn"
          onClick={runComparison}
          disabled={isComparing}
          className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          {isComparing ? 'Comparing...' : 'Run Comparison'}
        </button>
      </div>
      {isComparing && <div className="text-center py-4 text-violet-400 animate-pulse">Simulating across all events...</div>}
      {compareResult && !isComparing && (
        <div className="space-y-4" data-testid="compare-results">
          {/* Aggregate Summary */}
          <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
            <div className="bg-zinc-800/60 rounded p-2 text-center">
              <div className="text-[10px] text-zinc-500">Events</div>
              <div className="font-mono text-sm font-bold">{compareResult.events_count}</div>
            </div>
            <div className="bg-zinc-800/60 rounded p-2 text-center">
              <div className="text-[10px] text-zinc-500">Total Trades</div>
              <div className="font-mono text-sm font-bold">{compareResult.aggregate?.total_trades}</div>
            </div>
            <div className="bg-zinc-800/60 rounded p-2 text-center">
              <div className="text-[10px] text-zinc-500">Win Rate</div>
              <div className={`font-mono text-sm font-bold ${compareResult.aggregate?.overall_win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                {compareResult.aggregate?.overall_win_rate}%
              </div>
            </div>
            <div className="bg-zinc-800/60 rounded p-2 text-center">
              <div className="text-[10px] text-zinc-500">Aggregate PnL</div>
              <div className={`font-mono text-sm font-bold ${compareResult.aggregate?.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {compareResult.aggregate?.total_pnl >= 0 ? '+' : ''}${compareResult.aggregate?.total_pnl?.toLocaleString()}
              </div>
            </div>
            <div className="bg-zinc-800/60 rounded p-2 text-center">
              <div className="text-[10px] text-zinc-500">Worst DD</div>
              <div className="font-mono text-sm text-red-400">{compareResult.aggregate?.worst_drawdown_pct}%</div>
            </div>
          </div>

          {/* Per-Event Bar Chart */}
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={compareResult.per_event}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="event_name" tick={{ fontSize: 7, fill: '#71717a' }} angle={-15} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 8, fill: '#71717a' }} tickFormatter={v => `$${v}`} />
                <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', fontSize: 10 }} formatter={(v) => [`$${v.toLocaleString()}`, 'PnL']} />
                <Bar dataKey="total_pnl" name="PnL" radius={[3, 3, 0, 0]}>
                  {compareResult.per_event?.map((e, i) => (
                    <Cell key={i} fill={e.total_pnl >= 0 ? '#34d399' : '#f87171'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Per-Event Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="compare-table">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="py-2 px-2 text-left">Event</th>
                  <th className="py-2 px-2 text-center">Date</th>
                  <th className="py-2 px-2 text-right">Trades</th>
                  <th className="py-2 px-2 text-right">Win Rate</th>
                  <th className="py-2 px-2 text-right">PnL</th>
                  <th className="py-2 px-2 text-right">Return</th>
                  <th className="py-2 px-2 text-right">Max DD</th>
                </tr>
              </thead>
              <tbody>
                {compareResult.per_event?.map((evt) => (
                  <tr key={evt.event_id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="py-1.5 px-2 font-medium truncate max-w-[150px]">{evt.event_name}</td>
                    <td className="py-1.5 px-2 text-center text-zinc-500">{evt.date}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{evt.total_trades}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{evt.win_rate}%</td>
                    <td className={`py-1.5 px-2 text-right font-mono font-bold ${evt.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {evt.total_pnl >= 0 ? '+' : ''}${evt.total_pnl?.toLocaleString()}
                    </td>
                    <td className={`py-1.5 px-2 text-right font-mono ${evt.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {evt.return_pct >= 0 ? '+' : ''}{evt.return_pct}%
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono text-red-400">{evt.max_drawdown_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>

    {/* Strategy Optimizer Panel */}
    <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-outfit text-lg font-bold flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            Strategy Optimizer
          </h2>
          <p className="text-xs text-zinc-500 mt-1">Auto-search 100+ parameter combinations to find the best risk-adjusted config</p>
        </div>
        <button
          data-testid="run-optimizer-btn"
          onClick={runOptimizer}
          disabled={isOptimizing}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-zinc-700 text-white text-sm font-medium rounded-md transition-colors"
        >
          {isOptimizing ? 'Optimizing...' : 'Find Best Config'}
        </button>
      </div>
      {isOptimizing && <div className="text-center py-6 text-amber-400 animate-pulse">Testing parameter combinations across all events...</div>}
      {optimizeResult && !isOptimizing && (
        <div className="space-y-4" data-testid="optimizer-results">
          <div className="text-xs text-zinc-500">Tested {optimizeResult.total_combinations} combinations across {optimizeResult.events_tested} events</div>

          {/* Best Config */}
          {optimizeResult.best && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-md p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-bold text-amber-400 text-sm">Best Configuration</h3>
                <button
                  data-testid="apply-best-config-btn"
                  onClick={applyBestConfig}
                  className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded transition-colors"
                >
                  Apply to Bot
                </button>
                <button
                  data-testid="share-best-strategy-btn"
                  onClick={shareBestStrategy}
                  className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs font-medium rounded transition-colors"
                >
                  Share
                </button>
              </div>
              <div className="grid grid-cols-4 gap-3 mb-3">
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">Confidence</div>
                  <div className="font-mono text-sm font-bold">{optimizeResult.best.config.min_confidence}%</div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">SL (ATR x)</div>
                  <div className="font-mono text-sm font-bold">{optimizeResult.best.config.atr_sl_mult}</div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">TP1 (ATR x)</div>
                  <div className="font-mono text-sm font-bold">{optimizeResult.best.config.atr_tp1_mult}</div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">TP2 (ATR x)</div>
                  <div className="font-mono text-sm font-bold">{optimizeResult.best.config.atr_tp2_mult}</div>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3">
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">PnL</div>
                  <div className={`font-mono text-sm font-bold ${optimizeResult.best.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${optimizeResult.best.total_pnl?.toLocaleString()}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">Trades</div>
                  <div className="font-mono text-sm font-bold">{optimizeResult.best.total_trades}</div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">Win Rate</div>
                  <div className="font-mono text-sm font-bold text-emerald-400">{optimizeResult.best.win_rate}%</div>
                </div>
                <div className="text-center">
                  <div className="text-[10px] text-zinc-500">Score</div>
                  <div className="font-mono text-sm font-bold text-amber-400">{optimizeResult.best.score}</div>
                </div>
              </div>
            </div>
          )}

          {/* Top 10 Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="optimizer-table">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="py-2 px-2 text-left">#</th>
                  <th className="py-2 px-2 text-center">Conf%</th>
                  <th className="py-2 px-2 text-center">SL</th>
                  <th className="py-2 px-2 text-center">TP1</th>
                  <th className="py-2 px-2 text-center">TP2</th>
                  <th className="py-2 px-2 text-right">Trades</th>
                  <th className="py-2 px-2 text-right">Win%</th>
                  <th className="py-2 px-2 text-right">PnL</th>
                  <th className="py-2 px-2 text-right">Max DD</th>
                  <th className="py-2 px-2 text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {optimizeResult.top_10?.map((r, idx) => (
                  <tr key={idx} className={`border-b border-zinc-800/50 ${idx === 0 ? 'bg-amber-500/5' : 'hover:bg-zinc-800/30'}`}>
                    <td className="py-1.5 px-2 font-mono text-zinc-500">{idx + 1}</td>
                    <td className="py-1.5 px-2 text-center font-mono">{r.config.min_confidence}</td>
                    <td className="py-1.5 px-2 text-center font-mono">{r.config.atr_sl_mult}</td>
                    <td className="py-1.5 px-2 text-center font-mono">{r.config.atr_tp1_mult}</td>
                    <td className="py-1.5 px-2 text-center font-mono">{r.config.atr_tp2_mult}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{r.total_trades}</td>
                    <td className="py-1.5 px-2 text-right font-mono">{r.win_rate}%</td>
                    <td className={`py-1.5 px-2 text-right font-mono font-bold ${r.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${r.total_pnl?.toLocaleString()}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono text-red-400">{r.max_drawdown_pct}%</td>
                    <td className="py-1.5 px-2 text-right font-mono text-amber-400">{r.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>

    {/* Single Event Replay Section */}
    <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6">
      <h2 className="font-outfit text-2xl font-bold mb-2 flex items-center gap-2">
        <RefreshCw className="w-6 h-6 text-amber-400" />
        Strategy Replay
      </h2>
      <p className="text-sm text-zinc-500 mb-6">
        Replay historical oil market events to test how strategies perform under extreme conditions.
      </p>

      {/* Event Selection */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        {replayEvents.map(evt => (
          <button
            key={evt.id}
            data-testid={`replay-${evt.id}`}
            onClick={() => runReplay(evt.id)}
            disabled={isReplaying}
            className={`p-3 rounded-md text-left transition-all border ${
              replayResult?.event?.id === evt.id
                ? 'border-amber-500/50 bg-amber-500/10'
                : 'border-zinc-700 bg-zinc-800 hover:bg-zinc-700'
            }`}
          >
            <div className="text-sm font-semibold mb-1 truncate">{evt.name}</div>
            <div className="text-[10px] text-zinc-500 mb-1">{evt.date}</div>
            <div className="flex items-center gap-2 text-xs">
              <span className="font-mono">${evt.initial_price}</span>
              <span className={`font-mono font-bold ${evt.max_move_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {evt.max_move_pct > 0 ? '+' : ''}{evt.max_move_pct}%
              </span>
            </div>
          </button>
        ))}
        {replayEvents.length === 0 && (
          <button onClick={fetchReplayEvents} className="col-span-full p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-sm text-zinc-400 transition-colors">
            Load Historical Events
          </button>
        )}
      </div>

      {isReplaying && (
        <div className="text-center py-8 text-amber-400 animate-pulse">Replaying event...</div>
      )}

      {/* Replay Result */}
      {replayResult && !isReplaying && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-outfit text-lg font-bold">{replayResult.event?.name}</h3>
              <p className="text-xs text-zinc-500">{replayResult.event?.description}</p>
            </div>
            <span className="text-xs font-mono text-zinc-500">{replayResult.event?.date}</span>
          </div>

          {/* Analytics Cards */}
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Initial</div>
              <div className="font-mono text-sm">${replayResult.analytics?.initial_price}</div>
            </div>
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Final</div>
              <div className="font-mono text-sm">${replayResult.analytics?.final_price}</div>
            </div>
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Return</div>
              <div className={`font-mono text-sm font-bold ${replayResult.analytics?.total_return_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {replayResult.analytics?.total_return_pct > 0 ? '+' : ''}{replayResult.analytics?.total_return_pct}%
              </div>
            </div>
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Max DD</div>
              <div className="font-mono text-sm text-red-400">{replayResult.analytics?.max_drawdown_pct}%</div>
            </div>
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Avg Fragility</div>
              <div className="font-mono text-sm text-amber-400">{replayResult.analytics?.avg_fragility}</div>
            </div>
            <div className="bg-zinc-800/50 rounded p-3 text-center">
              <div className="text-[10px] text-zinc-500">Bars</div>
              <div className="font-mono text-sm">{replayResult.analytics?.duration_bars}</div>
            </div>
          </div>

          {/* Price Chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={replayResult.bars}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis dataKey="bar" tick={{ fontSize: 9, fill: '#71717a' }} label={{ value: 'Time (bars)', position: 'insideBottom', offset: -5, fill: '#52525b', fontSize: 10 }} />
                <YAxis tick={{ fontSize: 9, fill: '#71717a' }} domain={['auto', 'auto']} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 4, fontSize: 11 }}
                  formatter={(v, name) => {
                    if (name === 'price') return [`$${v}`, 'Price'];
                    if (name === 'fragility_score') return [v, 'Fragility'];
                    return [v, name];
                  }}
                />
                <Area type="monotone" dataKey="price" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.1} strokeWidth={2} name="price" />
                <ReferenceLine y={replayResult.analytics?.initial_price} stroke="#f59e0b" strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Fragility & Regime Timeline */}
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={replayResult.bars}>
                <XAxis dataKey="bar" tick={{ fontSize: 8, fill: '#52525b' }} />
                <YAxis tick={{ fontSize: 8, fill: '#52525b' }} domain={[0, 100]} />
                <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', fontSize: 10 }} />
                <Area type="monotone" dataKey="fragility_score" stroke="#ef4444" fill="#ef4444" fillOpacity={0.2} name="Fragility" />
                <Area type="monotone" dataKey="adx" stroke="#22c55e" fill="#22c55e" fillOpacity={0.05} name="ADX" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Regime Distribution */}
          {replayResult.analytics?.regime_distribution && (
            <div className="flex gap-2 flex-wrap">
              {Object.entries(replayResult.analytics.regime_distribution).map(([regime, count]) => (
                <span key={regime} className={`px-2 py-1 rounded text-xs font-mono ${
                  regime === 'spike' ? 'bg-red-500/20 text-red-400' :
                  regime === 'event' ? 'bg-amber-500/20 text-amber-400' :
                  regime === 'blocked' ? 'bg-purple-500/20 text-purple-400' :
                  'bg-zinc-700 text-zinc-400'
                }`}>{regime}: {count} bars</span>
              ))}
            </div>
          )}

          {/* Strategy Simulation Section */}
          <div className="mt-6 border-t border-zinc-800 pt-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-outfit text-lg font-bold flex items-center gap-2">
                  <Activity className="w-5 h-5 text-cyan-400" />
                  Bot Strategy Simulation
                </h3>
                <p className="text-xs text-zinc-500 mt-1">Simulate the trading bot on this historical event to evaluate hypothetical PnL</p>
              </div>
              <button
                data-testid="run-simulation-btn"
                onClick={() => runSimulation(replayResult.event?.id)}
                disabled={isSimulating}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-zinc-700 text-white text-sm font-medium rounded-md transition-colors"
              >
                {isSimulating ? 'Simulating...' : 'Run Simulation'}
              </button>
            </div>

            {/* Config Controls */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <div className="bg-zinc-800/50 rounded p-2">
                <label className="text-[10px] text-zinc-500 block mb-1">Min Confidence</label>
                <input data-testid="sim-confidence" type="number" value={simConfig.min_confidence} onChange={e => setSimConfig(p => ({...p, min_confidence: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" min={30} max={95} step={5} />
              </div>
              <div className="bg-zinc-800/50 rounded p-2">
                <label className="text-[10px] text-zinc-500 block mb-1">SL (ATR x)</label>
                <input data-testid="sim-sl-mult" type="number" value={simConfig.atr_sl_mult} onChange={e => setSimConfig(p => ({...p, atr_sl_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" min={0.5} max={5} step={0.5} />
              </div>
              <div className="bg-zinc-800/50 rounded p-2">
                <label className="text-[10px] text-zinc-500 block mb-1">TP1 (ATR x)</label>
                <input data-testid="sim-tp1-mult" type="number" value={simConfig.atr_tp1_mult} onChange={e => setSimConfig(p => ({...p, atr_tp1_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" min={0.5} max={8} step={0.5} />
              </div>
              <div className="bg-zinc-800/50 rounded p-2">
                <label className="text-[10px] text-zinc-500 block mb-1">TP2 (ATR x)</label>
                <input data-testid="sim-tp2-mult" type="number" value={simConfig.atr_tp2_mult} onChange={e => setSimConfig(p => ({...p, atr_tp2_mult: Number(e.target.value)}))} className="w-full bg-zinc-900 border border-zinc-700 rounded px-2 py-1 text-xs font-mono text-white" min={1} max={10} step={0.5} />
              </div>
            </div>

            {isSimulating && (
              <div className="text-center py-6 text-cyan-400 animate-pulse">Running bot simulation...</div>
            )}

            {/* Simulation Results */}
            {simResult && !isSimulating && (
              <div className="space-y-4" data-testid="sim-results">
                {/* Summary Cards */}
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Trades</div>
                    <div className="font-mono text-sm font-bold" data-testid="sim-total-trades">{simResult.summary?.total_trades}</div>
                  </div>
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Win Rate</div>
                    <div className={`font-mono text-sm font-bold ${simResult.summary?.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'}`} data-testid="sim-win-rate">
                      {simResult.summary?.win_rate}%
                    </div>
                  </div>
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Total PnL</div>
                    <div className={`font-mono text-sm font-bold ${simResult.summary?.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`} data-testid="sim-total-pnl">
                      {simResult.summary?.total_pnl >= 0 ? '+' : ''}${simResult.summary?.total_pnl?.toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Return</div>
                    <div className={`font-mono text-sm font-bold ${simResult.summary?.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {simResult.summary?.return_pct >= 0 ? '+' : ''}{simResult.summary?.return_pct}%
                    </div>
                  </div>
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Max DD</div>
                    <div className="font-mono text-sm text-red-400">{simResult.summary?.max_drawdown_pct}%</div>
                  </div>
                  <div className="bg-zinc-800/60 rounded p-2 text-center">
                    <div className="text-[10px] text-zinc-500">Profit Factor</div>
                    <div className="font-mono text-sm text-amber-400">{simResult.summary?.profit_factor >= 999 ? '---' : simResult.summary?.profit_factor}</div>
                  </div>
                </div>

                {/* Equity Curve */}
                {simResult.equity_curve?.length > 0 && (
                  <div>
                    <h4 className="text-xs text-zinc-400 font-semibold mb-2">Equity Curve</h4>
                    <div className="h-44">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={simResult.equity_curve}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                          <XAxis dataKey="bar" tick={{ fontSize: 8, fill: '#52525b' }} />
                          <YAxis tick={{ fontSize: 8, fill: '#71717a' }} domain={['auto', 'auto']} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', fontSize: 10 }} formatter={(v, name) => name === 'equity' ? [`$${v.toLocaleString()}`, 'Equity'] : [`${v}%`, 'Drawdown']} />
                          <Area type="monotone" dataKey="equity" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.1} strokeWidth={2} name="equity" />
                          <ReferenceLine y={50000} stroke="#3f3f46" strokeDasharray="4 4" />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {/* Trade List */}
                {simResult.trades?.length > 0 && (
                  <div>
                    <h4 className="text-xs text-zinc-400 font-semibold mb-2">Simulated Trades ({simResult.trades.length})</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs" data-testid="sim-trades-table">
                        <thead>
                          <tr className="text-zinc-500 border-b border-zinc-800">
                            <th className="py-2 px-2 text-left">#</th>
                            <th className="py-2 px-2 text-left">Direction</th>
                            <th className="py-2 px-2 text-right">Entry</th>
                            <th className="py-2 px-2 text-right">Exit</th>
                            <th className="py-2 px-2 text-center">Bars</th>
                            <th className="py-2 px-2 text-right">Size</th>
                            <th className="py-2 px-2 text-right">Conf%</th>
                            <th className="py-2 px-2 text-left">Exit Reason</th>
                            <th className="py-2 px-2 text-right">PnL</th>
                          </tr>
                        </thead>
                        <tbody>
                          {simResult.trades.map((t, idx) => (
                            <tr key={t.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30" data-testid={`sim-trade-${idx}`}>
                              <td className="py-1.5 px-2 font-mono text-zinc-500">{idx + 1}</td>
                              <td className="py-1.5 px-2">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${t.direction === 'long' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                                  {t.direction === 'long' ? 'LONG' : 'SHORT'}
                                </span>
                              </td>
                              <td className="py-1.5 px-2 text-right font-mono">${t.entry_price?.toFixed(2)}</td>
                              <td className="py-1.5 px-2 text-right font-mono">${t.exit_price?.toFixed(2)}</td>
                              <td className="py-1.5 px-2 text-center font-mono text-zinc-500">{t.entry_bar}-{t.exit_bar}</td>
                              <td className="py-1.5 px-2 text-right font-mono">{t.size}</td>
                              <td className="py-1.5 px-2 text-right font-mono">{t.confidence}%</td>
                              <td className="py-1.5 px-2">
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  t.exit_reason?.includes('TP') ? 'bg-emerald-500/10 text-emerald-400' :
                                  t.exit_reason?.includes('SL') || t.exit_reason?.includes('STOP') ? 'bg-red-500/10 text-red-400' :
                                  'bg-zinc-700 text-zinc-400'
                                }`}>{t.exit_reason}</span>
                              </td>
                              <td className={`py-1.5 px-2 text-right font-mono font-bold ${t.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {t.total_pnl >= 0 ? '+' : ''}${t.total_pnl?.toLocaleString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {simResult.trades?.length === 0 && (
                  <div className="text-center py-6 text-zinc-500 text-sm" data-testid="sim-no-trades">
                    No trades generated during this event with current parameters. Try lowering confidence threshold.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  </div>
  );
};
