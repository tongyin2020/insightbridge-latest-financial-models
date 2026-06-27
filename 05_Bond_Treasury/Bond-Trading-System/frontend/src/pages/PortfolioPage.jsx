import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Wallet, TrendingUp, TrendingDown, DollarSign,
  PieChart, BarChart3, RefreshCcw, Plus, Minus
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart as RechartsPie, Pie, Cell, Legend
} from 'recharts';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = ['#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];

const PortfolioPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [portfolio, setPortfolio] = useState(null);
  const [pnlHistory, setPnlHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tradeDialogOpen, setTradeDialogOpen] = useState(false);
  
  // Trade form
  const [tradeAsset, setTradeAsset] = useState('10Y_BOND');
  const [tradeQuantity, setTradeQuantity] = useState(10);
  const [tradeAction, setTradeAction] = useState('BUY');
  const [executing, setExecuting] = useState(false);

  useEffect(() => {
    fetchPortfolio();
    fetchPnlHistory();
  }, []);

  const fetchPortfolio = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/portfolio`, { withCredentials: true });
      setPortfolio(res.data);
    } catch (error) {
      toast.error('Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  };

  const fetchPnlHistory = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/portfolio/pnl`, { withCredentials: true });
      setPnlHistory(res.data.history || []);
    } catch (error) {
      console.error('Error fetching P&L history:', error);
    }
  };

  const executeTrade = async () => {
    setExecuting(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/portfolio/trade?asset=${tradeAsset}&quantity=${tradeQuantity}&action=${tradeAction}`,
        {},
        { withCredentials: true }
      );
      setPortfolio(res.data);
      toast.success(`${tradeAction} order executed successfully`);
      setTradeDialogOpen(false);
      fetchPnlHistory();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Trade execution failed');
    } finally {
      setExecuting(false);
    }
  };

  const pieData = portfolio?.positions?.map((pos, i) => ({
    name: pos.asset,
    value: Math.abs(pos.market_value),
    color: COLORS[i % COLORS.length]
  })) || [];

  // Add cash to pie chart
  if (portfolio?.cash > 0) {
    pieData.push({
      name: 'Cash',
      value: portfolio.cash,
      color: '#71717a'
    });
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <RefreshCcw className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

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
            Portfolio Management
          </h1>
        </div>
        
        <Dialog open={tradeDialogOpen} onOpenChange={setTradeDialogOpen}>
          <DialogTrigger asChild>
            <Button
              data-testid="new-trade-btn"
              size="sm"
              className="bg-blue-600 hover:bg-blue-500 text-white text-xs"
            >
              <Plus size={14} className="mr-2" />
              New Trade
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-800">
            <DialogHeader>
              <DialogTitle className="text-white">Execute Trade</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label className="text-xs text-zinc-500 uppercase">Asset</Label>
                <Select value={tradeAsset} onValueChange={setTradeAsset}>
                  <SelectTrigger className="mt-1 bg-zinc-950 border-zinc-800">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-zinc-900 border-zinc-800">
                    <SelectItem value="10Y_BOND">10Y Treasury Bond</SelectItem>
                    <SelectItem value="WTI">WTI Crude Oil</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label className="text-xs text-zinc-500 uppercase">Action</Label>
                <div className="flex gap-2 mt-1">
                  <Button
                    type="button"
                    onClick={() => setTradeAction('BUY')}
                    className={`flex-1 ${tradeAction === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-zinc-800 hover:bg-zinc-700'}`}
                  >
                    <TrendingUp size={14} className="mr-2" />
                    BUY
                  </Button>
                  <Button
                    type="button"
                    onClick={() => setTradeAction('SELL')}
                    className={`flex-1 ${tradeAction === 'SELL' ? 'bg-red-600 hover:bg-red-500' : 'bg-zinc-800 hover:bg-zinc-700'}`}
                  >
                    <TrendingDown size={14} className="mr-2" />
                    SELL
                  </Button>
                </div>
              </div>
              
              <div>
                <Label className="text-xs text-zinc-500 uppercase">Quantity</Label>
                <Input
                  type="number"
                  value={tradeQuantity}
                  onChange={(e) => setTradeQuantity(Number(e.target.value))}
                  className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono"
                />
              </div>
              
              <Button
                onClick={executeTrade}
                disabled={executing}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white"
              >
                {executing ? (
                  <RefreshCcw size={14} className="mr-2 animate-spin" />
                ) : (
                  <DollarSign size={14} className="mr-2" />
                )}
                Execute {tradeAction}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </header>

      <div className="p-4 sm:p-6">
        <div className="grid grid-cols-12 gap-4 sm:gap-6">
          {/* Portfolio Summary */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {/* Key Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Wallet size={16} className="text-blue-500" />
                  <span className="text-[10px] text-zinc-500 uppercase">Total Value</span>
                </div>
                <div className="text-xl font-bold font-mono text-white">
                  ${portfolio?.total_value?.toLocaleString() || '0'}
                </div>
              </div>
              
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <div className="flex items-center gap-2 mb-2">
                  <DollarSign size={16} className="text-zinc-500" />
                  <span className="text-[10px] text-zinc-500 uppercase">Cash</span>
                </div>
                <div className="text-xl font-bold font-mono text-zinc-300">
                  ${portfolio?.cash?.toLocaleString() || '0'}
                </div>
              </div>
              
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <div className="flex items-center gap-2 mb-2">
                  {portfolio?.total_pnl >= 0 ? (
                    <TrendingUp size={16} className="text-emerald-500" />
                  ) : (
                    <TrendingDown size={16} className="text-red-500" />
                  )}
                  <span className="text-[10px] text-zinc-500 uppercase">Total P&L</span>
                </div>
                <div className={`text-xl font-bold font-mono ${portfolio?.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {portfolio?.total_pnl >= 0 ? '+' : ''}${portfolio?.total_pnl?.toLocaleString() || '0'}
                </div>
              </div>
              
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <div className="flex items-center gap-2 mb-2">
                  <BarChart3 size={16} className="text-amber-500" />
                  <span className="text-[10px] text-zinc-500 uppercase">Return %</span>
                </div>
                <div className={`text-xl font-bold font-mono ${portfolio?.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {portfolio?.total_pnl_pct >= 0 ? '+' : ''}{portfolio?.total_pnl_pct?.toFixed(2) || '0'}%
                </div>
              </div>
            </div>

            {/* P&L Chart */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <TrendingUp size={14} className="text-cyan-500" /> P&L History
              </h3>
              <div className="h-64">
                {pnlHistory.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={pnlHistory}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#52525b" />
                      <YAxis tick={{ fontSize: 10 }} stroke="#52525b" tickFormatter={(v) => `$${v}`} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '11px' }}
                        formatter={(value) => [`$${value.toLocaleString()}`, 'P&L']}
                      />
                      <Line
                        type="monotone"
                        dataKey="pnl"
                        stroke="#06b6d4"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-600">
                    <p>No P&L history available</p>
                  </div>
                )}
              </div>
            </div>

            {/* Positions Table */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Wallet size={14} className="text-blue-500" /> Open Positions
              </h3>
              
              {portfolio?.positions?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-zinc-800">
                      <tr>
                        <th className="px-4 py-2 text-left text-zinc-400 uppercase">Asset</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">Quantity</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">Avg Price</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">Current</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">Value</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">P&L</th>
                        <th className="px-4 py-2 text-right text-zinc-400 uppercase">P&L %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {portfolio.positions.map((pos, i) => (
                        <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-800/50">
                          <td className="px-4 py-3 font-semibold">
                            <Badge className="bg-blue-500/20 text-blue-400 text-[9px]">
                              {pos.asset}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-zinc-300">{pos.quantity}</td>
                          <td className="px-4 py-3 text-right font-mono text-zinc-400">{pos.avg_price?.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right font-mono text-white">{pos.current_price?.toFixed(4)}</td>
                          <td className="px-4 py-3 text-right font-mono text-zinc-300">${pos.market_value?.toLocaleString()}</td>
                          <td className={`px-4 py-3 text-right font-mono font-semibold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)}
                          </td>
                          <td className={`px-4 py-3 text-right font-mono ${pos.unrealized_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct?.toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8 text-zinc-500">
                  <Wallet size={32} className="mx-auto mb-2 opacity-30" />
                  <p>No open positions</p>
                  <p className="text-xs mt-1">Execute a trade to open a position</p>
                </div>
              )}
            </div>
          </div>

          {/* Right Panel - Allocation */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            {/* Allocation Chart */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                <PieChart size={14} className="text-purple-500" /> Allocation
              </h3>
              <div className="h-64">
                {pieData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsPie>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={80}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{ backgroundColor: '#09090b', border: '1px solid #27272a', fontSize: '11px' }}
                        formatter={(value) => [`$${value.toLocaleString()}`, '']}
                      />
                      <Legend
                        formatter={(value) => <span className="text-zinc-400 text-xs">{value}</span>}
                      />
                    </RechartsPie>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-600">
                    <p>No allocation data</p>
                  </div>
                )}
              </div>
            </div>

            {/* Quick Stats */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Quick Stats</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-zinc-500">Positions</span>
                  <span className="text-sm font-mono text-white">{portfolio?.positions?.length || 0}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-zinc-500">Cash Allocation</span>
                  <span className="text-sm font-mono text-white">
                    {portfolio?.total_value > 0 ? ((portfolio.cash / portfolio.total_value) * 100).toFixed(1) : 0}%
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-xs text-zinc-500">Last Updated</span>
                  <span className="text-xs font-mono text-zinc-400">
                    {portfolio?.updated_at ? new Date(portfolio.updated_at).toLocaleTimeString() : '-'}
                  </span>
                </div>
              </div>
            </div>

            {/* Refresh Button */}
            <Button
              onClick={() => { fetchPortfolio(); fetchPnlHistory(); }}
              variant="outline"
              className="w-full border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              <RefreshCcw size={14} className="mr-2" />
              Refresh Portfolio
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPage;
