import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine, BarChart, Bar, Cell } from "recharts";
import {
  AlertTriangle, TrendingUp, TrendingDown,
  RefreshCw, Calendar, Shield, Clock, DollarSign, Target, XCircle,
  ChevronRight, Gauge, Brain, Lock, GitBranch, Check, BarChart3, Layers
} from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const DashboardTab = ({ ctx }) => {
  const {
    assets, allAssetPrices, currentSymbol, switchSymbol, marketData,
    renderPriceChart, spreadOpportunity, positions, closePosition,
    trades, exportTradesCSV, systemStatus, portfolioAnalysis,
    mlPrediction, getMlPrediction, signalScore, executionGate,
    fragility, riskControl, eventCalendar, calendarEvents, dailyPnl,
    fetchAdvancedAnalytics, fetchData, setRegimeOverride, clearOverride,
    triggerEvent, ASSET_COLORS, DIRECTION_COLORS, REGIME_COLORS
  } = ctx;
  return (
          <div className="grid grid-cols-12 gap-4">
            {/* Main Chart Area - 8 columns */}
            <div className="col-span-8 space-y-4">
              {/* Multi-Asset Price Overview */}
              <div className="grid grid-cols-3 gap-4">
                {assets.map(asset => (
                  <div 
                    key={asset.symbol}
                    onClick={() => switchSymbol(asset.symbol)}
                    className={`bg-zinc-900 border rounded-md p-4 cursor-pointer transition-all ${
                      currentSymbol === asset.symbol 
                        ? 'border-blue-500 ring-1 ring-blue-500/50' 
                        : 'border-zinc-800 hover:border-zinc-700'
                    }`}
                    data-testid={`asset-card-${asset.symbol}`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <div className={`text-xs font-mono ${ASSET_COLORS[asset.symbol]}`}>{asset.symbol}</div>
                        <div className="text-sm text-zinc-400">{asset.name}</div>
                      </div>
                      <div className="text-xs text-zinc-500">{asset.exchange}</div>
                    </div>
                    <div className="mt-2 font-mono text-xl font-bold">
                      ${(allAssetPrices[asset.symbol]?.last || asset.current_price)?.toFixed(asset.symbol === 'NG' ? 3 : 2)}
                    </div>
                    <div className="text-xs text-zinc-500 font-mono">
                      Spread: ${(allAssetPrices[asset.symbol]?.spread || 0.03).toFixed(4)}
                    </div>
                  </div>
                ))}
              </div>

              {/* Price Chart */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="price-chart">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="font-outfit text-lg font-semibold flex items-center gap-2">
                      <span className={ASSET_COLORS[currentSymbol]}>{currentSymbol}</span>
                      {assets.find(a => a.symbol === currentSymbol)?.name || 'WTI Crude Oil'}
                    </h2>
                    <div className="flex items-center gap-3 mt-1">
                      <span className="font-mono text-2xl font-bold">
                        ${marketData?.price?.toFixed(currentSymbol === 'NG' ? 3 : 2) || '—'}
                      </span>
                      <span className="font-mono text-sm text-zinc-400">
                        Spread: ${marketData?.spread?.toFixed(4) || '—'}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-zinc-400 font-mono">BID / ASK</div>
                    <div className="font-mono text-sm">
                      <span className="text-red-400">${marketData?.bid?.toFixed(2) || '—'}</span>
                      {' / '}
                      <span className="text-emerald-400">${marketData?.ask?.toFixed(2) || '—'}</span>
                    </div>
                  </div>
                </div>
                {renderPriceChart()}
              </div>

              {/* Spread Opportunity Alert */}
              {spreadOpportunity && (
                <div className="bg-purple-900/20 border border-purple-500/50 rounded-md p-4" data-testid="spread-alert">
                  <div className="flex items-center gap-2 mb-2">
                    <GitBranch className="w-5 h-5 text-purple-400" />
                    <h3 className="font-semibold text-purple-400">Spread Trading Opportunity</h3>
                  </div>
                  <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <div className="text-zinc-400">Signal</div>
                      <div className="font-mono font-bold">{spreadOpportunity.signal}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Spread</div>
                      <div className="font-mono">${spreadOpportunity.spread}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Z-Score</div>
                      <div className="font-mono">{spreadOpportunity.z_score}</div>
                    </div>
                    <div>
                      <div className="text-zinc-400">Confidence</div>
                      <div className="font-mono">{(spreadOpportunity.confidence * 100).toFixed(0)}%</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Indicators */}
              <div className="grid grid-cols-4 gap-4">
                <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="ema-indicator">
                  <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider mb-1">EMA 20/50</div>
                  <div className="font-mono text-lg">
                    <span className={marketData?.indicators?.ema_fast > marketData?.indicators?.ema_slow ? 'text-emerald-400' : 'text-red-400'}>
                      {marketData?.indicators?.ema_fast?.toFixed(2) || '—'}
                    </span>
                    <span className="text-zinc-500 mx-1">/</span>
                    <span className="text-zinc-300">{marketData?.indicators?.ema_slow?.toFixed(2) || '—'}</span>
                  </div>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="adx-indicator">
                  <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider mb-1">ADX</div>
                  <div className={`font-mono text-lg ${(marketData?.indicators?.adx || 0) > 28 ? 'text-blue-400' : 'text-zinc-300'}`}>
                    {marketData?.indicators?.adx?.toFixed(1) || '—'}
                  </div>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="atr-indicator">
                  <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider mb-1">ATR</div>
                  <div className="font-mono text-lg text-zinc-300">
                    {marketData?.indicators?.atr?.toFixed(4) || '—'}
                  </div>
                </div>
                <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="volatility-indicator">
                  <div className="text-xs text-zinc-400 font-mono uppercase tracking-wider mb-1">Volatility</div>
                  <div className={`font-mono text-lg ${(marketData?.indicators?.volatility_ratio || 0) > 1.8 ? 'text-amber-400' : 'text-zinc-300'}`}>
                    {marketData?.indicators?.volatility_ratio?.toFixed(2) || '—'}x
                  </div>
                </div>
              </div>

              {/* Positions */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="positions-panel">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <Target className="w-4 h-4 text-blue-400" />
                  Open Positions
                </h3>
                {positions.length === 0 ? (
                  <div className="text-center py-8 text-zinc-500 text-sm">No open positions</div>
                ) : (
                  <div className="space-y-2">
                    {positions.map(pos => (
                      <div key={pos.id} className="flex items-center justify-between bg-zinc-800/50 p-3 rounded">
                        <div className="flex items-center gap-4">
                          <div className={`font-mono font-bold ${DIRECTION_COLORS[pos.direction]}`}>
                            {pos.direction === 'long' ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className={`font-mono text-sm ${ASSET_COLORS[pos.symbol] || 'text-white'}`}>{pos.symbol}</span>
                              <span className="font-mono text-sm">
                                {pos.quantity}x @ ${pos.entry_price?.toFixed(2)}
                              </span>
                            </div>
                            <div className="text-xs text-zinc-400">
                              SL: ${pos.stop_loss?.toFixed(2)}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className={`font-mono text-lg ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)}
                          </div>
                          <button
                            data-testid={`close-position-${pos.id}`}
                            onClick={() => closePosition(pos.id)}
                            className="p-2 rounded bg-zinc-700 hover:bg-red-600 transition-colors"
                          >
                            <XCircle className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Trade History */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="trades-panel">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-outfit text-lg font-semibold flex items-center gap-2">
                    <Clock className="w-4 h-4 text-blue-400" />
                    Recent Trades
                  </h3>
                  <button
                    data-testid="export-csv-dashboard-btn"
                    onClick={exportTradesCSV}
                    className="text-xs px-2 py-1 bg-zinc-700 hover:bg-zinc-600 rounded transition-colors font-mono"
                  >
                    Export CSV
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left text-xs text-zinc-400 font-mono uppercase border-b border-zinc-800">
                        <th className="pb-2">Asset</th>
                        <th className="pb-2">Direction</th>
                        <th className="pb-2 text-right">Entry</th>
                        <th className="pb-2 text-right">Exit</th>
                        <th className="pb-2 text-right">P&L</th>
                        <th className="pb-2 text-right">Hold</th>
                        <th className="pb-2">Reason</th>
                      </tr>
                    </thead>
                    <tbody className="font-mono text-sm">
                      {trades.slice(0, 10).map(trade => (
                        <tr key={trade.id} className="border-b border-zinc-800/50">
                          <td className={`py-2 ${ASSET_COLORS[trade.symbol] || 'text-white'}`}>{trade.symbol}</td>
                          <td className={`py-2 ${DIRECTION_COLORS[trade.direction]}`}>
                            {trade.direction?.toUpperCase()}
                          </td>
                          <td className="py-2 text-right">${trade.entry_price?.toFixed(2)}</td>
                          <td className="py-2 text-right">${trade.exit_price?.toFixed(2)}</td>
                          <td className={`py-2 text-right ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {trade.pnl >= 0 ? '+' : ''}${trade.pnl?.toFixed(2)}
                          </td>
                          <td className="py-2 text-right text-zinc-400">{trade.hold_minutes?.toFixed(0)}m</td>
                          <td className="py-2 text-zinc-400">{trade.exit_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Side Panel - 4 columns */}
            <div className="col-span-4 space-y-4">
              {/* Account Summary */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="account-summary">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-emerald-400" />
                  Account
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400 text-sm">Equity</span>
                    <span className="font-mono text-lg font-bold">${systemStatus?.equity?.toFixed(2) || '50,000.00'}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400 text-sm">Daily P&L</span>
                    <span className={`font-mono ${(systemStatus?.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {(systemStatus?.daily_pnl || 0) >= 0 ? '+' : ''}${systemStatus?.daily_pnl?.toFixed(2) || '0.00'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400 text-sm">Open Positions</span>
                    <span className="font-mono">{systemStatus?.open_positions || 0}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400 text-sm">Total Trades</span>
                    <span className="font-mono">{systemStatus?.total_trades || 0}</span>
                  </div>
                </div>
              </div>

              {/* Risk Metrics */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="risk-metrics">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-amber-400" />
                  Risk Status
                </h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-zinc-400 text-sm">Status</span>
                    <span className={`font-mono text-sm px-2 py-1 rounded ${
                      systemStatus?.kill_switch 
                        ? 'bg-red-500/20 text-red-400' 
                        : systemStatus?.is_halted 
                          ? 'bg-amber-500/20 text-amber-400'
                          : 'bg-emerald-500/20 text-emerald-400'
                    }`}>
                      {systemStatus?.kill_switch ? 'KILLED' : systemStatus?.is_halted ? 'HALTED' : 'ACTIVE'}
                    </span>
                  </div>
                  {portfolioAnalysis && (
                    <>
                      <div className="flex justify-between items-center">
                        <span className="text-zinc-400 text-sm">VaR 95% (1D)</span>
                        <span className="font-mono text-red-400">${portfolioAnalysis.var_95_1d?.toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-zinc-400 text-sm">VaR 99% (1D)</span>
                        <span className="font-mono text-red-400">${portfolioAnalysis.var_99_1d?.toFixed(2)}</span>
                      </div>
                    </>
                  )}
                  {systemStatus?.is_halted && (
                    <button
                      data-testid="reset-halt-btn"
                      onClick={async () => {
                        await axios.post(`${API}/risk/reset`);
                        fetchData();
                      }}
                      className="w-full py-2 bg-amber-600 hover:bg-amber-500 rounded text-sm font-medium transition-colors"
                    >
                      Reset Halt
                    </button>
                  )}
                </div>
              </div>

              {/* ML Prediction */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="ml-prediction">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-outfit text-lg font-semibold flex items-center gap-2">
                    <Brain className="w-4 h-4 text-purple-400" />
                    AI Analysis
                  </h3>
                  <button
                    data-testid="refresh-ml-btn"
                    onClick={getMlPrediction}
                    className="p-1 rounded hover:bg-zinc-800 transition-colors"
                  >
                    <RefreshCw className="w-4 h-4 text-zinc-400" />
                  </button>
                </div>
                {mlPrediction ? (
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs text-zinc-400 font-mono uppercase mb-1">Predicted Regime</div>
                      <div className={`inline-block px-2 py-1 rounded text-sm font-mono ${REGIME_COLORS[mlPrediction.regime] || REGIME_COLORS.normal}`}>
                        {mlPrediction.regime?.toUpperCase()}
                      </div>
                      <span className="ml-2 font-mono text-sm text-zinc-400">
                        {(mlPrediction.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    {mlPrediction.signal_direction && (
                      <div>
                        <div className="text-xs text-zinc-400 font-mono uppercase mb-1">Signal</div>
                        <div className="flex items-center gap-2">
                          <span className={`font-mono font-bold ${DIRECTION_COLORS[mlPrediction.signal_direction]}`}>
                            {mlPrediction.signal_direction?.toUpperCase()}
                          </span>
                          <div className="flex-1 bg-zinc-800 rounded-full h-2 overflow-hidden">
                            <div 
                              className={`h-full ${mlPrediction.signal_direction === 'long' ? 'bg-emerald-500' : 'bg-red-500'}`}
                              style={{ width: `${mlPrediction.signal_confidence * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-sm text-zinc-400">
                            {(mlPrediction.signal_confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    )}
                    <div className="text-xs text-zinc-500 italic">
                      {mlPrediction.reasoning}
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-4 text-zinc-500 text-sm">
                    Click refresh to get AI analysis
                  </div>
                )}
              </div>

              {/* Regime Override */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="regime-override">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <Gauge className="w-4 h-4 text-blue-400" />
                  Regime Override
                </h3>
                {systemStatus?.regime_override ? (
                  <div className="space-y-3">
                    <div className="text-sm text-zinc-400">
                      Override active: <span className={REGIME_COLORS[systemStatus.regime_override]}>{systemStatus.regime_override}</span>
                    </div>
                    <button
                      data-testid="clear-override-btn"
                      onClick={clearOverride}
                      className="w-full py-2 bg-zinc-700 hover:bg-zinc-600 rounded text-sm transition-colors"
                    >
                      Clear Override
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {['normal', 'event', 'trend', 'blocked'].map(regime => (
                      <button
                        key={regime}
                        data-testid={`override-${regime}-btn`}
                        onClick={() => setRegimeOverride(regime, `Manual override to ${regime}`)}
                        className={`py-2 rounded text-xs font-mono uppercase border transition-colors hover:opacity-80 ${REGIME_COLORS[regime]}`}
                      >
                        {regime}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Upcoming Events */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="upcoming-events">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-blue-400" />
                  Upcoming Events
                </h3>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {calendarEvents.slice(0, 5).map(event => (
                    <div 
                      key={event.id}
                      className="p-3 bg-zinc-800/50 rounded cursor-pointer hover:bg-zinc-800 transition-colors"
                      onClick={() => triggerEvent(event.id)}
                      data-testid={`event-${event.id}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{event.event_name}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          event.importance === 'high' 
                            ? 'bg-red-500/20 text-red-400'
                            : event.importance === 'medium'
                              ? 'bg-amber-500/20 text-amber-400'
                              : 'bg-zinc-700 text-zinc-400'
                        }`}>
                          {event.importance}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-zinc-400">
                        <span>{event.country}</span>
                        <span>•</span>
                        <span>{new Date(event.date).toLocaleDateString()}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* ──── ADVANCED ANALYTICS ROW ──── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
              {/* Fragility Engine */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="fragility-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <Shield className="w-4 h-4 text-amber-400" />
                  Fragility Engine
                </h3>
                {fragility && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className={`text-3xl font-mono font-bold ${
                        fragility.score >= 80 ? 'text-red-500' :
                        fragility.score >= 60 ? 'text-orange-500' :
                        fragility.score >= 30 ? 'text-amber-500' : 'text-emerald-500'
                      }`}>
                        {fragility.score.toFixed(0)}
                      </div>
                      <span className={`text-xs px-2 py-1 rounded font-mono uppercase font-bold ${
                        fragility.level === 'extreme' ? 'bg-red-500/20 text-red-400 border border-red-500/50' :
                        fragility.level === 'high' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' :
                        fragility.level === 'moderate' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50' :
                        'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                      }`}>{fragility.level}</span>
                    </div>
                    {/* Component bars */}
                    <div className="space-y-1.5">
                      {Object.entries(fragility.components || {}).map(([key, val]) => (
                        <div key={key} className="flex items-center gap-2 text-xs">
                          <span className="w-16 text-zinc-500 capitalize">{key}</span>
                          <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                val > 15 ? 'bg-red-500' : val > 8 ? 'bg-amber-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min(100, val * 3.3)}%` }}
                            />
                          </div>
                          <span className="w-6 text-right font-mono text-zinc-400">{val.toFixed(0)}</span>
                        </div>
                      ))}
                    </div>
                    {fragility.triggers?.length > 0 && (
                      <div className="mt-2 flex gap-1 flex-wrap">
                        {fragility.triggers.map((t, i) => (
                          <span key={i} className="text-[10px] px-1.5 py-0.5 bg-red-500/10 text-red-400 rounded border border-red-500/30">{t}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Signal Score */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="signal-score-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <Target className="w-4 h-4 text-blue-400" />
                  Signal Score
                </h3>
                {signalScore && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className={`text-3xl font-mono font-bold ${
                        signalScore.score > 20 ? 'text-emerald-400' :
                        signalScore.score < -20 ? 'text-red-400' : 'text-zinc-300'
                      }`}>
                        {signalScore.score > 0 ? '+' : ''}{signalScore.score.toFixed(1)}
                      </div>
                      <span className={`text-xs px-2 py-1 rounded font-mono ${
                        signalScore.zone_color === 'emerald' ? 'bg-emerald-500/20 text-emerald-400' :
                        signalScore.zone_color === 'green' ? 'bg-green-500/20 text-green-400' :
                        signalScore.zone_color === 'red' ? 'bg-red-500/20 text-red-400' :
                        signalScore.zone_color === 'orange' ? 'bg-orange-500/20 text-orange-400' :
                        'bg-zinc-700 text-zinc-400'
                      }`}>{signalScore.zone}</span>
                    </div>
                    {/* Bull/Bear bar */}
                    <div className="flex h-3 rounded-full overflow-hidden mb-3">
                      <div className="bg-emerald-500 transition-all" style={{ width: `${signalScore.bullish_pct}%` }} />
                      <div className="bg-red-500 transition-all" style={{ width: `${signalScore.bearish_pct}%` }} />
                    </div>
                    <div className="flex justify-between text-[10px] text-zinc-500 mb-3">
                      <span>Bull {signalScore.bullish_pct?.toFixed(0)}%</span>
                      <span>Bear {signalScore.bearish_pct?.toFixed(0)}%</span>
                    </div>
                    {/* Component breakdown */}
                    <div className="grid grid-cols-2 gap-1">
                      {Object.entries(signalScore.components || {}).map(([key, val]) => (
                        <div key={key} className="flex items-center justify-between text-[10px] px-1.5 py-0.5 bg-zinc-800/50 rounded">
                          <span className="text-zinc-500 capitalize">{key.replace('_', ' ')}</span>
                          <span className={`font-mono ${val > 0 ? 'text-emerald-400' : val < 0 ? 'text-red-400' : 'text-zinc-500'}`}>
                            {val > 0 ? '+' : ''}{typeof val === 'number' ? val.toFixed(1) : val}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Execution Gate */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="execution-gate-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <Lock className="w-4 h-4 text-cyan-400" />
                  Execution Gate
                </h3>
                {executionGate && (
                  <div>
                    <div className={`text-center p-2 rounded mb-3 font-mono font-bold text-sm ${
                      executionGate.gate_status === 'OPEN' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50' :
                      executionGate.gate_status === 'CAUTION' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50' :
                      executionGate.gate_status === 'PARTIAL' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' :
                      'bg-red-500/20 text-red-400 border border-red-500/50'
                    }`}>
                      {executionGate.gate_status}
                    </div>
                    <p className="text-[10px] text-zinc-400 mb-3 text-center">{executionGate.message}</p>
                    <div className="space-y-1">
                      {(executionGate.checks || []).map((check, i) => (
                        <div key={i} className="flex items-center justify-between text-[10px] py-0.5">
                          <div className="flex items-center gap-1.5">
                            <span className={`w-1.5 h-1.5 rounded-full ${
                              check.status === 'pass' ? 'bg-emerald-500' :
                              check.status === 'warn' ? 'bg-amber-500' : 'bg-red-500'
                            }`} />
                            <span className="text-zinc-300">{check.name}</span>
                          </div>
                          <span className="font-mono text-zinc-500">{check.value}</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-2 text-[10px] text-center text-zinc-600">
                      {executionGate.pass_count}/{executionGate.total_checks} pass | {executionGate.warn_count} warn | {executionGate.fail_count} fail
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ──── RISK CONTROL & EVENTS ROW ──── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
              {/* Risk Control Center */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="risk-control-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                  Risk Control Center
                </h3>
                {riskControl && (
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span className={`text-xs px-3 py-1 rounded font-mono font-bold uppercase ${
                        riskControl.level === 'halted' ? 'bg-red-500/20 text-red-400 border border-red-500/50' :
                        riskControl.level === 'degraded' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' :
                        riskControl.level === 'reduced' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/50' :
                        'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50'
                      }`}>{riskControl.level}</span>
                      <span className="text-xs text-zinc-500 font-mono">Size: {(riskControl.size_multiplier * 100).toFixed(0)}%</span>
                    </div>
                    {/* Rules */}
                    <div className="space-y-1.5 mb-3">
                      {(riskControl.rules || []).map((rule, i) => (
                        <div key={i} className={`flex items-center justify-between text-xs p-1.5 rounded ${
                          rule.triggered ? 'bg-red-500/10 border border-red-500/30' : 'bg-zinc-800/50'
                        }`}>
                          <div className="flex items-center gap-1.5">
                            {rule.triggered ? <XCircle className="w-3 h-3 text-red-400" /> : <Check className="w-3 h-3 text-emerald-500" />}
                            <span className={rule.triggered ? 'text-red-300' : 'text-zinc-400'}>{rule.name}</span>
                          </div>
                          <span className="font-mono text-zinc-500">{rule.action}</span>
                        </div>
                      ))}
                    </div>
                    {/* Equity snapshot */}
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="bg-zinc-800/50 rounded p-2">
                        <div className="text-[10px] text-zinc-500">Equity</div>
                        <div className="text-sm font-mono">${riskControl.equity?.current?.toLocaleString()}</div>
                      </div>
                      <div className="bg-zinc-800/50 rounded p-2">
                        <div className="text-[10px] text-zinc-500">Drawdown</div>
                        <div className={`text-sm font-mono ${riskControl.equity?.drawdown_pct > 2 ? 'text-red-400' : 'text-zinc-300'}`}>
                          {riskControl.equity?.drawdown_pct?.toFixed(2)}%
                        </div>
                      </div>
                      <div className="bg-zinc-800/50 rounded p-2">
                        <div className="text-[10px] text-zinc-500">Today P&L</div>
                        <div className={`text-sm font-mono ${
                          riskControl.today_pnl?.total_pnl > 0 ? 'text-emerald-400' :
                          riskControl.today_pnl?.total_pnl < 0 ? 'text-red-400' : 'text-zinc-300'
                        }`}>
                          ${riskControl.today_pnl?.total_pnl?.toFixed(2)}
                        </div>
                      </div>
                    </div>
                    {/* Cooldown */}
                    {riskControl.cooldown?.active && (
                      <div className="mt-2 p-2 bg-amber-500/10 rounded border border-amber-500/30 text-xs text-amber-400 text-center">
                        Cooldown: {riskControl.cooldown.reason} ({riskControl.cooldown.remaining_sec}s)
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Economic Calendar / Events */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="event-calendar-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <Calendar className="w-4 h-4 text-purple-400" />
                  Oil Market Events
                </h3>
                {eventCalendar && (
                  <div>
                    {/* Event state bar */}
                    <div className={`flex items-center justify-between p-2 rounded mb-3 text-xs ${
                      eventCalendar.state?.cooldown_active ? 'bg-red-500/10 border border-red-500/30 text-red-400' :
                      eventCalendar.state?.upcoming_high_impact > 0 ? 'bg-amber-500/10 border border-amber-500/30 text-amber-400' :
                      'bg-zinc-800/50 text-zinc-400'
                    }`}>
                      <span>{eventCalendar.state?.cooldown_active ? `Cooldown: ${eventCalendar.state.cooldown_reason}` :
                             eventCalendar.state?.upcoming_high_impact > 0 ? `${eventCalendar.state.upcoming_high_impact} high-impact events upcoming` :
                             'No active events'}</span>
                      <span className="font-mono">Risk: {((eventCalendar.state?.risk_modifier || 1) * 100).toFixed(0)}%</span>
                    </div>
                    {/* Event list */}
                    <div className="space-y-1.5 max-h-52 overflow-y-auto">
                      {(eventCalendar.events || []).slice(0, 8).map(evt => (
                        <div key={evt.id} className={`p-2 rounded text-xs cursor-pointer hover:bg-zinc-700/50 transition-colors border-l-2 ${
                          evt.impact === 'high' ? 'border-l-red-500 bg-zinc-800/50' :
                          evt.impact === 'medium' ? 'border-l-amber-500 bg-zinc-800/30' :
                          'border-l-zinc-600 bg-zinc-800/20'
                        }`} onClick={async () => {
                          try {
                            await axios.post(`${API}/events/trigger/${evt.id}?actual=actual&direction=neutral`);
                            fetchAdvancedAnalytics();
                          } catch(e) { console.error(e); }
                        }}>
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-zinc-200">{evt.title}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              evt.phase === 'active' ? 'bg-red-500/20 text-red-400' :
                              evt.phase === 'upcoming' ? 'bg-blue-500/20 text-blue-400' :
                              'bg-zinc-700 text-zinc-500'
                            }`}>{evt.phase}</span>
                          </div>
                          <div className="text-[10px] text-zinc-500 mt-0.5">{evt.oil_relevance}</div>
                          {evt.forecast && (
                            <div className="text-[10px] text-zinc-600 mt-0.5">
                              Forecast: {evt.forecast} | Prev: {evt.previous}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ──── DAILY PNL & EXIT TIERS ROW ──── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
              {/* Daily PnL Chart */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="daily-pnl-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <BarChart3 className="w-4 h-4 text-emerald-400" />
                  Daily P&L (7 Days)
                </h3>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={dailyPnl}>
                      <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#71717a' }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 9, fill: '#71717a' }} axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 4, fontSize: 11 }} />
                      <Bar dataKey="total_pnl" name="P&L" fill="#22c55e" radius={[2, 2, 0, 0]}>
                        {dailyPnl.map((entry, idx) => (
                          <Cell key={idx} fill={entry.total_pnl >= 0 ? '#22c55e' : '#ef4444'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Slippage & Exit Tiers */}
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-4" data-testid="exit-tiers-panel">
                <h3 className="font-outfit font-semibold mb-3 flex items-center gap-2 text-sm">
                  <Layers className="w-4 h-4 text-rose-400" />
                  Multi-Tier Exit Structure
                </h3>
                <div className="space-y-1.5">
                  {[
                    { tier: 'WARNING', mult: '-50%', color: 'amber', action: 'Alert notification' },
                    { tier: 'PRE_REDUCE', mult: '-70%', color: 'orange', action: 'Reduce 50% position' },
                    { tier: 'MAIN_STOP', mult: '-100%', color: 'red', action: 'Close all positions' },
                    { tier: 'DISASTER', mult: '-150%', color: 'rose', action: 'Emergency flatten all' },
                  ].map((t, i) => (
                    <div key={i} className={`flex items-center justify-between p-2 rounded text-xs border-l-2 ${
                      t.color === 'amber' ? 'border-l-amber-500 bg-amber-500/5' :
                      t.color === 'orange' ? 'border-l-orange-500 bg-orange-500/5' :
                      t.color === 'red' ? 'border-l-red-500 bg-red-500/5' :
                      'border-l-rose-500 bg-rose-500/5'
                    }`}>
                      <div>
                        <span className="font-mono font-semibold text-zinc-300">{t.tier}</span>
                        <span className={`ml-2 font-mono ${
                          t.color === 'amber' ? 'text-amber-400' :
                          t.color === 'orange' ? 'text-orange-400' :
                          t.color === 'red' ? 'text-red-400' : 'text-rose-400'
                        }`}>{t.mult}</span>
                      </div>
                      <span className="text-zinc-500">{t.action}</span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 text-[10px] text-zinc-600 text-center">
                  Tiered exit structure protects against catastrophic losses
                </div>
              </div>
            </div>
          </div>
  );
};
