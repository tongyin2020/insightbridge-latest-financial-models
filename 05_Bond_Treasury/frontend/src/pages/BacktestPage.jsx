import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Play, TrendingUp, TrendingDown, Calendar,
  BarChart3, Target, AlertTriangle, Download, RefreshCcw,
  Zap, Shield, LineChart as LineChartIcon, ChevronDown
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  ComposedChart, Legend
} from 'recharts';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Slider } from '../components/ui/slider';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/ui/tabs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const BacktestPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  // Backtest configuration
  const [strategyType, setStrategyType] = useState('MEAN_REVERSION');
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [initialCapital, setInitialCapital] = useState(100000);
  
  // Strategy parameters
  const [ispreadUpper, setIspreadUpper] = useState(15.0);
  const [ispreadLower, setIspreadLower] = useState(10.0);
  const [stopLoss, setStopLoss] = useState(5);
  const [takeProfit, setTakeProfit] = useState(10);
  const [positionSize, setPositionSize] = useState(100);
  
  // Results
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [compareResults, setCompareResults] = useState([]);
  const [backtestHistory, setBacktestHistory] = useState([]);
  
  const strategyTypes = [
    { value: 'MEAN_REVERSION', label: 'Mean Reversion', description: 'Trade based on Ispread deviation' },
    { value: 'MOMENTUM', label: 'Momentum', description: 'Follow price trend direction' },
    { value: 'SPREAD_ARBITRAGE', label: 'Spread Arbitrage', description: 'Exploit WTI-Bond spread anomalies' },
    { value: 'AI_HYBRID', label: 'AI Hybrid', description: 'Combine rules with GPT-5.2 analysis' }
  ];

  useEffect(() => {
    fetchBacktestHistory();
  }, []);

  const fetchBacktestHistory = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/backtest/history?limit=10`, { withCredentials: true });
      setBacktestHistory(res.data);
    } catch (error) {
      console.error('Error fetching backtest history:', error);
    }
  };

  const runBacktest = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_URL}/api/backtest/run`, {
        strategy_type: strategyType,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        strategy_params: {
          ispread_upper: ispreadUpper,
          ispread_lower: ispreadLower,
          stop_loss_pct: stopLoss / 100,
          take_profit_pct: takeProfit / 100,
          position_size: positionSize
        }
      }, { withCredentials: true });
      
      setResult(res.data);
      toast.success('Backtest completed successfully');
      fetchBacktestHistory();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Backtest failed');
    } finally {
      setLoading(false);
    }
  };

  const compareStrategies = async () => {
    setLoading(true);
    try {
      const strategies = strategyTypes.map(st => ({
        strategy_type: st.value,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        strategy_params: {
          ispread_upper: ispreadUpper,
          ispread_lower: ispreadLower,
          stop_loss_pct: stopLoss / 100,
          take_profit_pct: takeProfit / 100,
          position_size: positionSize
        }
      }));
      
      const res = await axios.post(`${API_URL}/api/backtest/compare`, strategies, { withCredentials: true });
      setCompareResults(res.data.comparison);
      toast.success('Strategy comparison completed');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Comparison failed');
    } finally {
      setLoading(false);
    }
  };

  const exportResults = () => {
    if (!result) return;
    
    const csvContent = [
      ['Metric', 'Value'],
      ['Strategy', result.strategy],
      ['Initial Capital', result.initial_capital],
      ['Final Capital', result.final_capital],
      ['Total Return', result.total_return],
      ['Total Return %', result.total_return_pct],
      ['Sharpe Ratio', result.sharpe_ratio],
      ['Max Drawdown', result.max_drawdown],
      ['Max Drawdown %', result.max_drawdown_pct],
      ['Win Rate', result.win_rate],
      ['Total Trades', result.total_trades],
      ['Volatility', result.volatility],
      ['', ''],
      ['Trades'],
      ['Date', 'Type', 'Price', 'Quantity', 'P&L', 'Capital'],
      ...result.trades.map(t => [t.date, t.type, t.price, t.quantity, t.pnl || '', t.capital])
    ].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_${result.strategy}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    toast.success('Results exported');
  };

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <Toaster position="bottom-right" theme="dark" />
      
      {/* Header */}
      <header className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/dashboard')}
            data-testid="back-btn"
            className="text-zinc-400 hover:text-white"
          >
            <ArrowLeft size={18} className="mr-2" />
            Dashboard
          </Button>
          <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
            Strategy Backtesting
          </h1>
        </div>
        
        {result && (
          <Button
            onClick={exportResults}
            data-testid="export-btn"
            size="sm"
            className="bg-blue-600 hover:bg-blue-500 text-white text-xs"
          >
            <Download size={14} className="mr-2" />
            Export
          </Button>
        )}
      </header>

      <div className="p-4 sm:p-6">
        <div className="grid grid-cols-12 gap-4 sm:gap-6">
          {/* Configuration Panel */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            {/* Strategy Selection */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Target size={14} className="text-blue-500" /> Strategy Configuration
              </h3>
              
              <div className="space-y-4">
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Strategy Type</Label>
                  <Select value={strategyType} onValueChange={setStrategyType}>
                    <SelectTrigger className="mt-1 bg-zinc-950 border-zinc-800" data-testid="strategy-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      {strategyTypes.map(st => (
                        <SelectItem key={st.value} value={st.value}>
                          <div>
                            <div className="font-semibold">{st.label}</div>
                            <div className="text-[10px] text-zinc-500">{st.description}</div>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-zinc-500 uppercase">Start Date</Label>
                    <Input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      data-testid="start-date"
                      className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-sm"
                    />
                  </div>
                  <div>
                    <Label className="text-xs text-zinc-500 uppercase">End Date</Label>
                    <Input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      data-testid="end-date"
                      className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-sm"
                    />
                  </div>
                </div>

                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Initial Capital ($)</Label>
                  <Input
                    type="number"
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(Number(e.target.value))}
                    data-testid="initial-capital"
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Strategy Parameters */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Zap size={14} className="text-amber-500" /> Parameters
              </h3>
              
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Ispread Upper</span>
                    <span className="text-white font-mono">{ispreadUpper.toFixed(1)}</span>
                  </div>
                  <Slider
                    value={[ispreadUpper]}
                    onValueChange={([v]) => setIspreadUpper(v)}
                    min={12}
                    max={20}
                    step={0.5}
                    className="cursor-pointer"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-2">
                    <span className="text-zinc-500 uppercase">Ispread Lower</span>
                    <span className="text-white font-mono">{ispreadLower.toFixed(1)}</span>
                  </div>
                  <Slider
                    value={[ispreadLower]}
                    onValueChange={([v]) => setIspreadLower(v)}
                    min={5}
                    max={12}
                    step={0.5}
                    className="cursor-pointer"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500 uppercase">Stop Loss</span>
                      <span className="text-red-400 font-mono">{stopLoss}%</span>
                    </div>
                    <Slider
                      value={[stopLoss]}
                      onValueChange={([v]) => setStopLoss(v)}
                      min={1}
                      max={20}
                      step={1}
                      className="cursor-pointer"
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500 uppercase">Take Profit</span>
                      <span className="text-emerald-400 font-mono">{takeProfit}%</span>
                    </div>
                    <Slider
                      value={[takeProfit]}
                      onValueChange={([v]) => setTakeProfit(v)}
                      min={1}
                      max={30}
                      step={1}
                      className="cursor-pointer"
                    />
                  </div>
                </div>

                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Position Size</Label>
                  <Input
                    type="number"
                    value={positionSize}
                    onChange={(e) => setPositionSize(Number(e.target.value))}
                    data-testid="position-size"
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <Button
                onClick={runBacktest}
                disabled={loading}
                data-testid="run-backtest-btn"
                className="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-semibold"
              >
                {loading ? (
                  <RefreshCcw size={14} className="mr-2 animate-spin" />
                ) : (
                  <Play size={14} className="mr-2" />
                )}
                Run Backtest
              </Button>
              <Button
                onClick={compareStrategies}
                disabled={loading}
                data-testid="compare-btn"
                variant="outline"
                className="flex-1 border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                <BarChart3 size={14} className="mr-2" />
                Compare All
              </Button>
            </div>
          </div>

          {/* Results Panel */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            <Tabs defaultValue="results" className="w-full">
              <TabsList className="bg-zinc-900 border border-zinc-800">
                <TabsTrigger value="results" className="data-[state=active]:bg-zinc-800">Results</TabsTrigger>
                <TabsTrigger value="comparison" className="data-[state=active]:bg-zinc-800">Comparison</TabsTrigger>
                <TabsTrigger value="history" className="data-[state=active]:bg-zinc-800">History</TabsTrigger>
              </TabsList>

              <TabsContent value="results" className="mt-4 space-y-4">
                {result ? (
                  <>
                    {/* Key Metrics */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3">
                        <div className="text-[10px] text-zinc-500 uppercase">Total Return</div>
                        <div className={`text-lg font-bold font-mono ${result.total_return >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {result.total_return >= 0 ? '+' : ''}{result.total_return_pct.toFixed(2)}%
                        </div>
                        <div className="text-xs text-zinc-500">${result.total_return.toLocaleString()}</div>
                      </div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3">
                        <div className="text-[10px] text-zinc-500 uppercase">Sharpe Ratio</div>
                        <div className={`text-lg font-bold font-mono ${result.sharpe_ratio >= 1 ? 'text-emerald-400' : result.sharpe_ratio >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
                          {result.sharpe_ratio.toFixed(3)}
                        </div>
                        <div className="text-xs text-zinc-500">Risk-adjusted</div>
                      </div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3">
                        <div className="text-[10px] text-zinc-500 uppercase">Max Drawdown</div>
                        <div className="text-lg font-bold font-mono text-red-400">
                          -{result.max_drawdown_pct.toFixed(2)}%
                        </div>
                        <div className="text-xs text-zinc-500">${result.max_drawdown.toLocaleString()}</div>
                      </div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3">
                        <div className="text-[10px] text-zinc-500 uppercase">Win Rate</div>
                        <div className={`text-lg font-bold font-mono ${result.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                          {result.win_rate.toFixed(1)}%
                        </div>
                        <div className="text-xs text-zinc-500">{result.profitable_trades}/{result.total_trades} trades</div>
                      </div>
                    </div>

                    {/* Equity Curve */}
                    <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                      <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                        <LineChartIcon size={14} className="text-cyan-500" /> Equity Curve
                      </h3>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={result.equity_curve}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                            <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#52525b" />
                            <YAxis tick={{ fontSize: 10 }} stroke="#52525b" tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '11px' }}
                              formatter={(value) => [`$${value.toLocaleString()}`, 'Equity']}
                            />
                            <Area
                              type="monotone"
                              dataKey="equity"
                              stroke="#06b6d4"
                              fill="#06b6d4"
                              fillOpacity={0.1}
                              strokeWidth={2}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Additional Metrics */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 text-center">
                        <div className="text-[10px] text-zinc-500 uppercase">Volatility</div>
                        <div className="text-base font-bold font-mono text-zinc-200">{result.volatility.toFixed(2)}%</div>
                      </div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 text-center">
                        <div className="text-[10px] text-zinc-500 uppercase">Avg Trade Return</div>
                        <div className={`text-base font-bold font-mono ${result.average_trade_return >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${result.average_trade_return.toFixed(2)}
                        </div>
                      </div>
                      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 text-center">
                        <div className="text-[10px] text-zinc-500 uppercase">Final Capital</div>
                        <div className="text-base font-bold font-mono text-white">${result.final_capital.toLocaleString()}</div>
                      </div>
                    </div>

                    {/* Trade List */}
                    <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                      <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Trade Log</h3>
                      <ScrollArea className="h-48">
                        <div className="space-y-2">
                          {result.trades.map((trade, i) => (
                            <div key={i} className="flex items-center justify-between text-xs p-2 bg-zinc-950/50 rounded-sm">
                              <div className="flex items-center gap-3">
                                <span className="text-zinc-500 font-mono">{trade.date}</span>
                                <Badge className={`text-[9px] ${
                                  trade.type === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' :
                                  trade.type === 'SELL' ? 'bg-red-500/20 text-red-400' :
                                  'bg-zinc-500/20 text-zinc-400'
                                }`}>
                                  {trade.type}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-4">
                                <span className="text-zinc-400 font-mono">@{trade.price.toFixed(3)}</span>
                                {trade.pnl !== undefined && (
                                  <span className={`font-mono font-semibold ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                    {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                    </div>
                  </>
                ) : (
                  <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-12 text-center">
                    <BarChart3 size={48} className="mx-auto mb-4 text-zinc-700" />
                    <p className="text-zinc-500">Configure parameters and run a backtest to see results</p>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="comparison" className="mt-4">
                {compareResults.length > 0 ? (
                  <div className="space-y-4">
                    {/* Comparison Chart */}
                    <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                      <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Strategy Comparison</h3>
                      <div className="h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={compareResults}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                            <XAxis dataKey="strategy" tick={{ fontSize: 10 }} stroke="#52525b" />
                            <YAxis tick={{ fontSize: 10 }} stroke="#52525b" />
                            <Tooltip contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '11px' }} />
                            <Legend />
                            <Bar dataKey="total_return_pct" name="Return %" fill="#10b981" />
                            <Bar dataKey="sharpe_ratio" name="Sharpe" fill="#3b82f6" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Comparison Table */}
                    <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm overflow-hidden">
                      <table className="w-full text-xs">
                        <thead className="bg-zinc-800">
                          <tr>
                            <th className="px-4 py-2 text-left text-zinc-400 uppercase">Strategy</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Return %</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Sharpe</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Max DD</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Win Rate</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Trades</th>
                          </tr>
                        </thead>
                        <tbody>
                          {compareResults.map((r, i) => (
                            <tr key={i} className={`border-t border-zinc-800 ${i === 0 ? 'bg-emerald-500/5' : ''}`}>
                              <td className="px-4 py-3 font-semibold">
                                {i === 0 && <Badge className="mr-2 bg-emerald-500/20 text-emerald-400 text-[9px]">BEST</Badge>}
                                {r.strategy}
                              </td>
                              <td className={`px-4 py-3 text-right font-mono ${r.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {r.total_return_pct >= 0 ? '+' : ''}{r.total_return_pct.toFixed(2)}%
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-blue-400">{r.sharpe_ratio.toFixed(3)}</td>
                              <td className="px-4 py-3 text-right font-mono text-red-400">-{r.max_drawdown_pct.toFixed(2)}%</td>
                              <td className="px-4 py-3 text-right font-mono text-zinc-300">{r.win_rate.toFixed(1)}%</td>
                              <td className="px-4 py-3 text-right font-mono text-zinc-500">{r.total_trades}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-12 text-center">
                    <Shield size={48} className="mx-auto mb-4 text-zinc-700" />
                    <p className="text-zinc-500">Click "Compare All" to compare all strategies</p>
                  </div>
                )}
              </TabsContent>

              <TabsContent value="history" className="mt-4">
                {backtestHistory.length > 0 ? (
                  <div className="space-y-2">
                    {backtestHistory.map((bt, i) => (
                      <div key={i} className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-3">
                            <Badge className="bg-blue-500/20 text-blue-400 text-[9px]">{bt.result?.strategy}</Badge>
                            <span className="text-xs text-zinc-500">{bt.request?.start_date} → {bt.request?.end_date}</span>
                          </div>
                          <span className="text-xs text-zinc-600">{new Date(bt.created_at).toLocaleString()}</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                          <div>
                            <span className="text-zinc-500">Return:</span>
                            <span className={`ml-2 font-mono font-semibold ${bt.result?.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {bt.result?.total_return_pct >= 0 ? '+' : ''}{bt.result?.total_return_pct?.toFixed(2)}%
                            </span>
                          </div>
                          <div>
                            <span className="text-zinc-500">Sharpe:</span>
                            <span className="ml-2 font-mono text-blue-400">{bt.result?.sharpe_ratio?.toFixed(3)}</span>
                          </div>
                          <div>
                            <span className="text-zinc-500">Max DD:</span>
                            <span className="ml-2 font-mono text-red-400">-{bt.result?.max_drawdown_pct?.toFixed(2)}%</span>
                          </div>
                          <div>
                            <span className="text-zinc-500">Win Rate:</span>
                            <span className="ml-2 font-mono text-zinc-300">{bt.result?.win_rate?.toFixed(1)}%</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-12 text-center">
                    <Calendar size={48} className="mx-auto mb-4 text-zinc-700" />
                    <p className="text-zinc-500">No backtest history yet</p>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BacktestPage;
