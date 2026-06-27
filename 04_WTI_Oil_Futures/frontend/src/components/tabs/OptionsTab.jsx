import { ResponsiveContainer, AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine, LineChart as RLineChart, Line, Legend } from "recharts";
import { Sparkles, PieChart, LineChart } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const OptionsTab = ({ ctx }) => {
  const {
    currentSymbol, optionChain, setOptionChain, optionStrategies,
    setOptionStrategies, volatilityAnalysis, setVolatilityAnalysis,
    autoStrategy, backtestResult, setBacktestResult, payoffData,
    payoffStrategy, fetchPayoff, setActiveTab,
    fetchAutoStrategy, isLoadingStrategy
  } = ctx;
  return (
          <div className="max-w-6xl mx-auto space-y-6">
            {/* Options Header */}
            <div className="flex items-center justify-between">
              <h2 className="font-outfit text-2xl font-bold">Options Trading</h2>
              <div className="flex gap-2">
                <button
                  data-testid="load-chain-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.get(`${API}/options/chain/${currentSymbol}?expiry_days=30`);
                      setOptionChain(res.data);
                    } catch (err) {
                      console.error("Error loading option chain:", err);
                    }
                  }}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
                >
                  Load Option Chain
                </button>
                <button
                  data-testid="load-vol-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.get(`${API}/options/volatility/${currentSymbol}`);
                      setVolatilityAnalysis(res.data);
                    } catch (err) {
                      console.error("Error loading volatility:", err);
                    }
                  }}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded text-sm font-medium transition-colors"
                >
                  Analyze Volatility
                </button>
              </div>
            </div>

            {/* Volatility Analysis */}
            {volatilityAnalysis && (
              <div className={`bg-zinc-900 border rounded-md p-6 ${
                volatilityAnalysis.recommendation === 'BUY VOLATILITY' ? 'border-emerald-500/50' :
                volatilityAnalysis.recommendation === 'SELL VOLATILITY' ? 'border-red-500/50' :
                'border-zinc-800'
              }`} data-testid="volatility-analysis">
                <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                  <PieChart className="w-5 h-5 text-purple-400" />
                  Volatility Analysis
                </h3>
                <div className="grid grid-cols-4 gap-4 mb-4">
                  <div>
                    <div className="text-xs text-zinc-400 font-mono">Current IV</div>
                    <div className="font-mono text-xl">{(volatilityAnalysis.current_iv * 100).toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400 font-mono">Historical Vol</div>
                    <div className="font-mono text-xl">{(volatilityAnalysis.historical_vol * 100).toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400 font-mono">IV Percentile</div>
                    <div className="font-mono text-xl">{volatilityAnalysis.iv_percentile?.toFixed(0)}th</div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400 font-mono">Confidence</div>
                    <div className="font-mono text-xl">{(volatilityAnalysis.confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>
                <div className={`p-4 rounded ${
                  volatilityAnalysis.recommendation === 'BUY VOLATILITY' ? 'bg-emerald-900/30' :
                  volatilityAnalysis.recommendation === 'SELL VOLATILITY' ? 'bg-red-900/30' :
                  'bg-zinc-800'
                }`}>
                  <div className="font-bold text-lg mb-1">{volatilityAnalysis.recommendation}</div>
                  <div className="text-sm text-zinc-400">{volatilityAnalysis.suggested_strategy}</div>
                  <div className="text-xs text-zinc-500 mt-2">{volatilityAnalysis.reasoning}</div>
                </div>
              </div>
            )}

            {/* Strategy Builder */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="strategy-builder">
              <h3 className="font-outfit text-lg font-semibold mb-4">Create Strategy</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <button
                  data-testid="create-straddle-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/straddle?symbol=${currentSymbol}&expiry_days=30`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating straddle:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-zinc-700"
                >
                  <div className="font-semibold mb-1">Straddle</div>
                  <div className="text-xs text-zinc-400">Long ATM Call + Put</div>
                  <div className="text-xs text-emerald-400 mt-2">High volatility</div>
                </button>
                <button
                  data-testid="create-strangle-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/strangle?symbol=${currentSymbol}&expiry_days=30`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating strangle:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-zinc-700"
                >
                  <div className="font-semibold mb-1">Strangle</div>
                  <div className="text-xs text-zinc-400">Long OTM Call + Put</div>
                  <div className="text-xs text-emerald-400 mt-2">Lower cost</div>
                </button>
                <button
                  data-testid="create-iron-condor-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/iron-condor?symbol=${currentSymbol}&expiry_days=30`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating iron condor:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-amber-700/50"
                >
                  <div className="font-semibold mb-1 text-amber-400">Iron Condor</div>
                  <div className="text-xs text-zinc-400">Sell spreads both sides</div>
                  <div className="text-xs text-amber-400 mt-2">Low volatility</div>
                </button>
                <button
                  data-testid="create-butterfly-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/butterfly?symbol=${currentSymbol}&expiry_days=30`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating butterfly:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-purple-700/50"
                >
                  <div className="font-semibold mb-1 text-purple-400">Butterfly</div>
                  <div className="text-xs text-zinc-400">Long wings, short center</div>
                  <div className="text-xs text-purple-400 mt-2">Pin to strike</div>
                </button>
                <button
                  data-testid="create-calendar-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/calendar-spread?symbol=${currentSymbol}&option_type=call&near_expiry_days=30&far_expiry_days=60`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating calendar spread:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-cyan-700/50"
                >
                  <div className="font-semibold mb-1 text-cyan-400">Calendar Spread</div>
                  <div className="text-xs text-zinc-400">Sell near, buy far term</div>
                  <div className="text-xs text-cyan-400 mt-2">Time decay play</div>
                </button>
                <button
                  data-testid="create-ratio-btn"
                  onClick={async () => {
                    try {
                      const res = await axios.post(`${API}/options/strategy/ratio-spread?symbol=${currentSymbol}&option_type=call&ratio=2&expiry_days=30`);
                      setOptionStrategies(prev => [...prev, res.data]);
                    } catch (err) {
                      console.error("Error creating ratio spread:", err);
                    }
                  }}
                  className="p-4 bg-zinc-800 hover:bg-zinc-700 rounded-md text-left transition-colors border border-rose-700/50"
                >
                  <div className="font-semibold mb-1 text-rose-400">Ratio Spread</div>
                  <div className="text-xs text-zinc-400">Buy 1 ATM, Sell 2 OTM</div>
                  <div className="text-xs text-rose-400 mt-2">Premium collection</div>
                </button>
              </div>
            </div>

            {/* AI Auto Strategy Selector */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="auto-strategy-panel">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-outfit text-lg font-semibold flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-amber-400" />
                  AI Strategy Selector
                </h3>
                <button
                  data-testid="run-auto-strategy-btn"
                  onClick={fetchAutoStrategy}
                  disabled={isLoadingStrategy}
                  className="px-4 py-2 bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 disabled:opacity-50 rounded text-sm font-medium transition-all"
                >
                  {isLoadingStrategy ? 'Analyzing...' : 'Get AI Recommendation'}
                </button>
              </div>
              <p className="text-xs text-zinc-500 mb-4">
                AI analyzes current IV, market regime, trend strength and volatility to recommend the optimal options strategy.
              </p>
              {autoStrategy && (
                <div className="space-y-4">
                  <div className={`p-4 rounded-md border ${
                    autoStrategy.confidence >= 0.7 ? 'bg-emerald-900/20 border-emerald-500/50' :
                    autoStrategy.confidence >= 0.5 ? 'bg-amber-900/20 border-amber-500/50' :
                    'bg-zinc-800 border-zinc-700'
                  }`}>
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="text-xs text-zinc-400 font-mono uppercase">Recommended Strategy</div>
                        <div className="text-xl font-bold mt-1 capitalize">
                          {autoStrategy.recommended_strategy?.replace('_', ' ')}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-zinc-400">Confidence</div>
                        <div className={`text-2xl font-mono font-bold ${
                          autoStrategy.confidence >= 0.7 ? 'text-emerald-400' : 'text-amber-400'
                        }`}>
                          {(autoStrategy.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-4 text-sm mb-3">
                      <div>
                        <div className="text-xs text-zinc-500">Direction Bias</div>
                        <div className={`font-mono font-semibold capitalize ${
                          autoStrategy.direction_bias === 'bullish' ? 'text-emerald-400' :
                          autoStrategy.direction_bias === 'bearish' ? 'text-red-400' : 'text-zinc-300'
                        }`}>{autoStrategy.direction_bias}</div>
                      </div>
                      <div>
                        <div className="text-xs text-zinc-500">Risk Level</div>
                        <div className={`font-mono font-semibold capitalize ${
                          autoStrategy.risk_level === 'low' ? 'text-emerald-400' :
                          autoStrategy.risk_level === 'high' ? 'text-red-400' : 'text-amber-400'
                        }`}>{autoStrategy.risk_level}</div>
                      </div>
                      <div>
                        <div className="text-xs text-zinc-500">Alternative</div>
                        <div className="font-mono text-zinc-300 capitalize">{autoStrategy.alternative_strategy?.replace('_', ' ')}</div>
                      </div>
                    </div>
                    <div className="text-sm text-zinc-300 mb-2">{autoStrategy.reasoning}</div>
                    {autoStrategy.key_factors && (
                      <div className="flex gap-2 flex-wrap mt-2">
                        {autoStrategy.key_factors.map((f, i) => (
                          <span key={i} className="px-2 py-0.5 bg-zinc-700/50 rounded text-[10px] text-zinc-400 font-mono">{f}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-[10px] text-zinc-600 flex items-center gap-1">
                    <span>Source: {autoStrategy.source === 'ai' ? 'GPT-4o Analysis' : 'Rule-based Engine'}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Options Payoff Diagram */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="payoff-diagram">
              <h3 className="font-outfit text-lg font-semibold mb-4 flex items-center gap-2">
                <LineChart className="w-5 h-5 text-blue-400" />
                P&L Payoff Diagram
              </h3>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mb-4">
                {['straddle', 'strangle', 'iron_condor', 'butterfly', 'calendar_spread', 'ratio_spread'].map(s => (
                  <button
                    key={s}
                    data-testid={`payoff-${s}-btn`}
                    onClick={() => fetchPayoff(s)}
                    className={`px-3 py-2 rounded text-xs font-mono transition-colors ${
                      payoffStrategy === s && payoffData ? 'bg-blue-600 text-white' : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400'
                    }`}
                  >
                    {s.replace('_', ' ')}
                  </button>
                ))}
              </div>
              {payoffData && (
                <div>
                  <div className="grid grid-cols-4 gap-3 mb-4 text-xs">
                    <div className="bg-zinc-800/50 rounded p-2 text-center">
                      <div className="text-zinc-500">Spot</div>
                      <div className="font-mono">${payoffData.spot_price?.toFixed(2)}</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2 text-center">
                      <div className="text-zinc-500">Max Profit</div>
                      <div className="font-mono text-emerald-400">${payoffData.max_profit?.toLocaleString()}</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2 text-center">
                      <div className="text-zinc-500">Max Loss</div>
                      <div className="font-mono text-red-400">${payoffData.max_loss?.toLocaleString()}</div>
                    </div>
                    <div className="bg-zinc-800/50 rounded p-2 text-center">
                      <div className="text-zinc-500">Breakeven</div>
                      <div className="font-mono text-zinc-300">{payoffData.breakeven_points?.map(b => `$${b}`).join(' / ')}</div>
                    </div>
                  </div>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={payoffData.data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                        <XAxis dataKey="price" tick={{ fontSize: 9, fill: '#71717a' }} tickFormatter={v => `$${v}`} />
                        <YAxis tick={{ fontSize: 9, fill: '#71717a' }} tickFormatter={v => `$${v}`} />
                        <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 4, fontSize: 11 }} formatter={v => [`$${v}`, '']} />
                        <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="3 3" />
                        <ReferenceLine x={payoffData.spot_price} stroke="#f59e0b" strokeDasharray="3 3" label={{ value: 'SPOT', fill: '#f59e0b', fontSize: 9 }} />
                        <Area type="monotone" dataKey="expiry_pnl" name="At Expiry" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} strokeWidth={2} />
                        <Area type="monotone" dataKey="current_pnl" name="Current" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.05} strokeWidth={1} strokeDasharray="4 4" />
                        <Legend wrapperStyle={{ fontSize: 10 }} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
              {!payoffData && (
                <div className="text-center text-sm text-zinc-500 py-8">
                  Select a strategy above to view its P&L payoff diagram
                </div>
              )}
            </div>

            {/* Options Strategy Backtest */}
            <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="options-backtest">
              <h3 className="font-outfit text-lg font-semibold mb-4">Strategy Backtest</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-4">
                {['straddle', 'strangle', 'iron_condor', 'butterfly', 'calendar_spread', 'ratio_spread'].map(strategy => (
                  <button
                    key={strategy}
                    data-testid={`backtest-${strategy}-btn`}
                    onClick={async () => {
                      try {
                        const res = await axios.post(`${API}/options/backtest?strategy_type=${strategy}&symbol=${currentSymbol}&num_simulations=50`);
                        setBacktestResult(res.data);
                        setActiveTab('backtest');
                      } catch (err) {
                        console.error("Error backtesting:", err);
                      }
                    }}
                    className="px-3 py-2 bg-zinc-800 hover:bg-blue-600 rounded text-xs font-mono uppercase transition-colors"
                  >
                    {strategy.replace('_', ' ')}
                  </button>
                ))}
              </div>
              <p className="text-xs text-zinc-500">
                Run historical backtests to compare strategy performance across different market conditions.
              </p>
            </div>

            {/* Active Strategies */}
            {optionStrategies.length > 0 && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="active-strategies">
                <h3 className="font-outfit text-lg font-semibold mb-4">Active Strategies</h3>
                <div className="space-y-4">
                  {optionStrategies.map((strategy, idx) => (
                    <div key={idx} className="bg-zinc-800/50 p-4 rounded-md">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <div className="font-semibold">{strategy.name}</div>
                          <div className="text-xs text-zinc-400">{strategy.type?.toUpperCase()}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs text-zinc-400">Max Loss</div>
                          <div className="font-mono text-red-400">${strategy.max_loss?.toFixed(2)}</div>
                        </div>
                      </div>
                      <div className="grid grid-cols-4 gap-4 text-sm">
                        <div>
                          <div className="text-xs text-zinc-500">Delta</div>
                          <div className="font-mono">{strategy.greeks?.delta?.toFixed(4)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-zinc-500">Gamma</div>
                          <div className="font-mono">{strategy.greeks?.gamma?.toFixed(6)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-zinc-500">Theta</div>
                          <div className="font-mono text-red-400">{strategy.greeks?.theta?.toFixed(4)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-zinc-500">Vega</div>
                          <div className="font-mono text-emerald-400">{strategy.greeks?.vega?.toFixed(4)}</div>
                        </div>
                      </div>
                      {strategy.breakeven_points && (
                        <div className="mt-3 text-xs text-zinc-400">
                          Breakeven: ${strategy.breakeven_points[0]?.toFixed(2)} / ${strategy.breakeven_points[1]?.toFixed(2)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Option Chain */}
            {optionChain && (
              <div className="bg-zinc-900 border border-zinc-800 rounded-md p-6" data-testid="option-chain">
                <h3 className="font-outfit text-lg font-semibold mb-4">
                  {optionChain.symbol} Option Chain
                  <span className="ml-2 text-sm text-zinc-400 font-normal">
                    Underlying: ${optionChain.underlying_price?.toFixed(2)}
                  </span>
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs text-zinc-400 font-mono uppercase border-b border-zinc-800">
                        <th className="pb-2 text-left" colSpan="4">CALLS</th>
                        <th className="pb-2 text-center">Strike</th>
                        <th className="pb-2 text-right" colSpan="4">PUTS</th>
                      </tr>
                      <tr className="text-xs text-zinc-500 border-b border-zinc-800">
                        <th className="pb-2">Delta</th>
                        <th className="pb-2">IV</th>
                        <th className="pb-2">Bid</th>
                        <th className="pb-2">Ask</th>
                        <th className="pb-2"></th>
                        <th className="pb-2 text-right">Bid</th>
                        <th className="pb-2 text-right">Ask</th>
                        <th className="pb-2 text-right">IV</th>
                        <th className="pb-2 text-right">Delta</th>
                      </tr>
                    </thead>
                    <tbody className="font-mono">
                      {optionChain.options && (() => {
                        const calls = optionChain.options.filter(o => o.type === 'call');
                        const puts = optionChain.options.filter(o => o.type === 'put');
                        const strikes = [...new Set(calls.map(c => c.strike))].sort((a, b) => a - b);
                        
                        return strikes.map(strike => {
                          const call = calls.find(c => c.strike === strike);
                          const put = puts.find(p => p.strike === strike);
                          const isATM = Math.abs(strike - optionChain.underlying_price) < 1;
                          
                          return (
                            <tr key={strike} className={`border-b border-zinc-800/50 ${isATM ? 'bg-blue-900/20' : ''}`}>
                              <td className="py-2 text-emerald-400">{call?.delta?.toFixed(2)}</td>
                              <td className="py-2 text-zinc-400">{(call?.iv * 100)?.toFixed(1)}%</td>
                              <td className="py-2">${(call?.premium * 0.98)?.toFixed(2)}</td>
                              <td className="py-2">${(call?.premium * 1.02)?.toFixed(2)}</td>
                              <td className={`py-2 text-center font-bold ${isATM ? 'text-blue-400' : ''}`}>${strike?.toFixed(2)}</td>
                              <td className="py-2 text-right">${(put?.premium * 0.98)?.toFixed(2)}</td>
                              <td className="py-2 text-right">${(put?.premium * 1.02)?.toFixed(2)}</td>
                              <td className="py-2 text-right text-zinc-400">{(put?.iv * 100)?.toFixed(1)}%</td>
                              <td className="py-2 text-right text-red-400">{put?.delta?.toFixed(2)}</td>
                            </tr>
                          );
                        });
                      })()}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
  );
};
