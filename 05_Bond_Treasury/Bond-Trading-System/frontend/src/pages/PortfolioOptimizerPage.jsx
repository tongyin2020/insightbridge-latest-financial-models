import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Sigma, Play, Plus, Trash2, RefreshCcw, Target,
  TrendingUp, BarChart3, Layers
} from 'lucide-react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell, Legend, ReferenceLine
} from 'recharts';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Slider } from '../components/ui/slider';
import { Label } from '../components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CAT_COLORS = {
  short: '#22d3ee', medium: '#3b82f6', long: '#8b5cf6',
  tips: '#f59e0b', credit: '#ef4444', mbs: '#10b981',
};

const PortfolioOptimizerPage = () => {
  const navigate = useNavigate();
  const [assets, setAssets] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [riskAversion, setRiskAversion] = useState(2.5);
  const [views, setViews] = useState([]);

  useEffect(() => {
    axios.get(`${API_URL}/api/portfolio-optimizer/assets`, { withCredentials: true })
      .then(res => setAssets(res.data.assets))
      .catch(() => toast.error('Failed to load assets'));
  }, []);

  const addView = () => {
    setViews(prev => [...prev, { asset: 'UST_10Y', return_view: 5.0, confidence: 0.7 }]);
  };

  const removeView = (i) => setViews(prev => prev.filter((_, idx) => idx !== i));

  const updateView = (i, field, val) => {
    setViews(prev => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v));
  };

  const runOptimization = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_URL}/api/portfolio-optimizer/optimize`, {
        views: views.length > 0 ? views : [],
        risk_aversion: riskAversion,
      }, { withCredentials: true });
      setResult(res.data);
      toast.success(`Optimization complete — ${res.data.views_applied} views applied`);
    } catch (err) {
      toast.error('Optimization failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-300 overflow-hidden" data-testid="portfolio-optimizer-page">
      <Toaster position="bottom-right" theme="dark" />

      <nav className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6 shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')} className="p-1.5" data-testid="back-btn">
            <ArrowLeft size={18} />
          </Button>
          <div className="w-8 h-8 bg-indigo-600 rounded-sm flex items-center justify-center">
            <Sigma size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-xs font-black tracking-[0.15em] text-white uppercase">Portfolio Optimizer</h1>
            <p className="text-[9px] text-zinc-500">Black-Litterman Asset Allocation Engine</p>
          </div>
        </div>
        <Button onClick={runOptimization} disabled={loading} className="text-[10px] bg-indigo-600 hover:bg-indigo-500 gap-1.5" data-testid="run-optimize-btn">
          <Play size={12} className={loading ? 'animate-spin' : ''} /> {loading ? 'Optimizing...' : 'Run Optimization'}
        </Button>
      </nav>

      <ScrollArea className="flex-1">
        <div className="p-3 sm:p-6 space-y-4 sm:space-y-6">

          {/* Input Section: Views + Risk Aversion */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Investor Views */}
            <div className="lg:col-span-2 bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="views-panel">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                  <Target size={14} className="text-indigo-500" /> Investor Views
                </h3>
                <Button variant="outline" size="sm" onClick={addView} className="text-[10px] border-zinc-700 gap-1" data-testid="add-view-btn">
                  <Plus size={12} /> Add View
                </Button>
              </div>
              {views.length === 0 ? (
                <div className="text-center py-6 text-zinc-600">
                  <p className="text-[10px]">No views added — will use market equilibrium returns</p>
                  <p className="text-[9px] mt-1 text-zinc-700">Add views to express your return expectations for specific assets</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {views.map((v, i) => (
                    <div key={i} className="flex flex-col sm:flex-row gap-2 sm:items-end p-2 bg-zinc-950/50 border border-zinc-800/50 rounded-sm" data-testid={`view-${i}`}>
                      <div className="flex-1">
                        <Label className="text-[9px] text-zinc-600">Asset</Label>
                        <Select value={v.asset} onValueChange={(val) => updateView(i, 'asset', val)}>
                          <SelectTrigger className="bg-zinc-900 border-zinc-800 text-xs h-8">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="bg-zinc-900 border-zinc-800">
                            {assets.map(a => (
                              <SelectItem key={a.symbol} value={a.symbol}>{a.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="w-full sm:w-28">
                        <div className="flex justify-between text-[9px]">
                          <span className="text-zinc-600">Return</span>
                          <span className="text-emerald-400 font-mono">{v.return_view}%</span>
                        </div>
                        <Slider value={[v.return_view * 10]} onValueChange={([val]) => updateView(i, 'return_view', val / 10)} min={0} max={120} step={1} />
                      </div>
                      <div className="w-full sm:w-28">
                        <div className="flex justify-between text-[9px]">
                          <span className="text-zinc-600">Confidence</span>
                          <span className="text-blue-400 font-mono">{(v.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <Slider value={[v.confidence * 100]} onValueChange={([val]) => updateView(i, 'confidence', val / 100)} min={10} max={100} step={5} />
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => removeView(i)} className="p-1.5 text-zinc-600 hover:text-red-400">
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Risk Aversion */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="risk-aversion-panel">
              <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Layers size={14} className="text-amber-500" /> Parameters
              </h3>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-[10px] mb-1.5">
                    <span className="text-zinc-500">Risk Aversion (delta)</span>
                    <span className="text-amber-400 font-mono font-bold">{riskAversion.toFixed(1)}</span>
                  </div>
                  <Slider value={[riskAversion * 10]} onValueChange={([v]) => setRiskAversion(v / 10)} min={5} max={50} step={1} data-testid="risk-aversion-slider" />
                  <p className="text-[8px] text-zinc-700 mt-1">Low = aggressive, High = conservative</p>
                </div>
                <div className="pt-3 border-t border-zinc-800/50 text-[9px] text-zinc-600 space-y-1">
                  <p>Model: Black-Litterman</p>
                  <p>Tau: 0.05 (uncertainty scaling)</p>
                  <p>Constraints: -5% to 50% per asset</p>
                </div>
              </div>
            </div>
          </div>

          {result && (
            <>
              {/* Portfolio Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="portfolio-summary">
                <PortfolioCard title="BL Optimal" color="text-indigo-400" borderColor="border-indigo-900/50"
                  ret={result.optimal_portfolio.return} vol={result.optimal_portfolio.volatility}
                  sharpe={result.optimal_portfolio.sharpe} />
                <PortfolioCard title="Max Sharpe" color="text-emerald-400" borderColor="border-emerald-900/50"
                  ret={result.max_sharpe.return} vol={result.max_sharpe.volatility}
                  sharpe={result.max_sharpe.sharpe} />
                <PortfolioCard title="Min Variance" color="text-cyan-400" borderColor="border-cyan-900/50"
                  ret={result.min_variance.return} vol={result.min_variance.volatility}
                  sharpe={null} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                {/* Asset Allocation Bar Chart */}
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="allocation-chart">
                  <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest flex items-center gap-2">
                    <BarChart3 size={14} className="text-indigo-500" /> Optimal Asset Allocation
                  </h3>
                  <div className="h-64 sm:h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={result.allocations} layout="vertical" margin={{ left: 80 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
                        <XAxis type="number" tick={{ fill: '#52525b', fontSize: 9 }} tickFormatter={v => `${v}%`} />
                        <YAxis type="category" dataKey="symbol" tick={{ fill: '#71717a', fontSize: 9 }} width={70} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '10px' }}
                          formatter={(v) => [`${v}%`, 'Weight']}
                        />
                        <Legend wrapperStyle={{ fontSize: '10px' }} />
                        <Bar dataKey="optimal_weight" name="BL Optimal" radius={[0, 3, 3, 0]}>
                          {result.allocations.map((a, i) => (
                            <Cell key={i} fill={CAT_COLORS[a.category] || '#6366f1'} fillOpacity={0.8} />
                          ))}
                        </Bar>
                        <Bar dataKey="market_weight" name="Market Eq." fill="#475569" radius={[0, 3, 3, 0]} fillOpacity={0.4} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Efficient Frontier */}
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="efficient-frontier">
                  <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest flex items-center gap-2">
                    <TrendingUp size={14} className="text-emerald-500" /> Efficient Frontier
                  </h3>
                  <div className="h-64 sm:h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                        <XAxis type="number" dataKey="volatility" name="Volatility" unit="%" 
                          tick={{ fill: '#52525b', fontSize: 9 }} label={{ value: 'Volatility (%)', position: 'bottom', fill: '#52525b', fontSize: 9 }} />
                        <YAxis type="number" dataKey="return" name="Return" unit="%"
                          tick={{ fill: '#52525b', fontSize: 9 }} label={{ value: 'Return (%)', angle: -90, position: 'insideLeft', fill: '#52525b', fontSize: 9 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '10px' }}
                          formatter={(v, name) => [`${v}%`, name]}
                        />
                        <Scatter name="Efficient Frontier" data={result.efficient_frontier} fill="#6366f1" fillOpacity={0.6} />
                        <Scatter name="Optimal" data={[result.optimal_portfolio]} fill="#22c55e" shape="star" />
                        <Scatter name="Min Var" data={[result.min_variance]} fill="#06b6d4" shape="diamond" />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Detailed Allocations Table */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-3 sm:p-5" data-testid="allocation-table">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest">Detailed Allocations</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-zinc-600 border-b border-zinc-800">
                        <th className="text-left py-2 px-2">Asset</th>
                        <th className="text-right py-2 px-2">Category</th>
                        <th className="text-right py-2 px-2">BL Optimal</th>
                        <th className="text-right py-2 px-2">Max Sharpe</th>
                        <th className="text-right py-2 px-2">Min Var</th>
                        <th className="text-right py-2 px-2">Market Eq.</th>
                        <th className="text-right py-2 px-2">E[R]</th>
                        <th className="text-right py-2 px-2">Vol</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.allocations.map((a, i) => (
                        <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                          <td className="py-2 px-2 text-white font-mono">{a.symbol}</td>
                          <td className="py-2 px-2 text-right">
                            <Badge className={`text-[7px] border-0`} style={{ color: CAT_COLORS[a.category] }}>{a.category}</Badge>
                          </td>
                          <td className={`py-2 px-2 text-right font-mono font-bold ${a.optimal_weight > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {a.optimal_weight > 0 ? '+' : ''}{a.optimal_weight}%
                          </td>
                          <td className="py-2 px-2 text-right font-mono text-zinc-400">{a.ms_weight}%</td>
                          <td className="py-2 px-2 text-right font-mono text-zinc-400">{a.mv_weight}%</td>
                          <td className="py-2 px-2 text-right font-mono text-zinc-500">{a.market_weight}%</td>
                          <td className="py-2 px-2 text-right font-mono text-amber-400">{a.expected_return}%</td>
                          <td className="py-2 px-2 text-right font-mono text-cyan-400">{a.volatility}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
};

const PortfolioCard = ({ title, color, borderColor, ret, vol, sharpe }) => (
  <div className={`bg-zinc-900/50 border ${borderColor || 'border-zinc-800'} rounded-sm p-3 sm:p-4`}>
    <span className={`text-[10px] font-bold uppercase tracking-widest ${color}`}>{title}</span>
    <div className="grid grid-cols-3 gap-2 mt-2">
      <div>
        <span className="text-[8px] text-zinc-600 block">Return</span>
        <span className="text-sm font-mono font-bold text-white">{ret}%</span>
      </div>
      <div>
        <span className="text-[8px] text-zinc-600 block">Volatility</span>
        <span className="text-sm font-mono font-bold text-white">{vol}%</span>
      </div>
      <div>
        <span className="text-[8px] text-zinc-600 block">Sharpe</span>
        <span className={`text-sm font-mono font-bold ${sharpe !== null ? (sharpe > 0 ? 'text-emerald-400' : 'text-red-400') : 'text-zinc-500'}`}>
          {sharpe !== null ? sharpe : 'N/A'}
        </span>
      </div>
    </div>
  </div>
);

export default PortfolioOptimizerPage;
