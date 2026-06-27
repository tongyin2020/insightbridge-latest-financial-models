import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, PlayCircle, TrendingUp, TrendingDown, DollarSign,
  RefreshCcw, RotateCcw, History, Wallet, Zap, BarChart3
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/ui/tabs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = ['#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

const PaperTradingPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [portfolio, setPortfolio] = useState(null);
  const [assets, setAssets] = useState([]);
  const [assetPrices, setAssetPrices] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tradeDialogOpen, setTradeDialogOpen] = useState(false);
  
  // Trade form
  const [tradeAsset, setTradeAsset] = useState('');
  const [tradeQuantity, setTradeQuantity] = useState(10);
  const [tradeAction, setTradeAction] = useState('BUY');
  const [executing, setExecuting] = useState(false);
  
  // Reset dialog
  const [resetDialogOpen, setResetDialogOpen] = useState(false);
  const [resetCapital, setResetCapital] = useState(100000);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [portfolioRes, assetsRes, pricesRes, historyRes] = await Promise.all([
        axios.get(`${API_URL}/api/paper-trading/portfolio`, { withCredentials: true }),
        axios.get(`${API_URL}/api/assets`, { withCredentials: true }),
        axios.get(`${API_URL}/api/assets/prices`, { withCredentials: true }),
        axios.get(`${API_URL}/api/paper-trading/history?limit=50`, { withCredentials: true })
      ]);
      
      setPortfolio(portfolioRes.data);
      setAssets(assetsRes.data);
      setAssetPrices(pricesRes.data);
      setTradeHistory(historyRes.data);
      
      if (assetsRes.data.length > 0 && !tradeAsset) {
        setTradeAsset(assetsRes.data[0].symbol);
      }
    } catch (error) {
      toast.error('Failed to load paper trading data');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const executeTrade = async () => {
    if (!tradeAsset) {
      toast.error('Please select an asset');
      return;
    }
    
    setExecuting(true);
    try {
      const res = await axios.post(
        `${API_URL}/api/paper-trading/trade?asset=${tradeAsset}&quantity=${tradeQuantity}&action=${tradeAction}`,
        {},
        { withCredentials: true }
      );
      setPortfolio(res.data);
      toast.success(`Paper ${tradeAction} order executed successfully`);
      setTradeDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Trade execution failed');
    } finally {
      setExecuting(false);
    }
  };

  const resetPortfolio = async () => {
    try {
      const res = await axios.post(
        `${API_URL}/api/paper-trading/reset?initial_capital=${resetCapital}`,
        {},
        { withCredentials: true }
      );
      setPortfolio(res.data);
      toast.success('Paper trading portfolio reset');
      setResetDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Reset failed');
    }
  };

  const getSelectedAssetPrice = () => {
    const price = assetPrices.find(p => p.symbol === tradeAsset);
    return price?.price || 0;
  };

  const pieData = portfolio?.positions?.map((pos, i) => ({
    name: pos.asset,
    value: Math.abs(pos.market_value),
    color: COLORS[i % COLORS.length]
  })) || [];

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
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
              Paper Trading
            </h1>
            <Badge className="bg-amber-500/20 text-amber-400 text-[9px]">SIMULATION</Badge>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Dialog open={resetDialogOpen} onOpenChange={setResetDialogOpen}>
            <DialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
              >
                <RotateCcw size={14} className="mr-2" />
                Reset
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle className="text-white">Reset Paper Portfolio</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-4">
                <p className="text-sm text-zinc-400">This will reset all positions and restore your starting capital.</p>
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Initial Capital ($)</Label>
                  <Input
                    type="number"
                    value={resetCapital}
                    onChange={(e) => setResetCapital(Number(e.target.value))}
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 font-mono"
                  />
                </div>
                <Button onClick={resetPortfolio} className="w-full bg-amber-600 hover:bg-amber-500 text-white">
                  Reset Portfolio
                </Button>
              </div>
            </DialogContent>
          </Dialog>
          
          <Dialog open={tradeDialogOpen} onOpenChange={setTradeDialogOpen}>
            <DialogTrigger asChild>
              <Button
                data-testid="new-paper-trade-btn"
                size="sm"
                className="bg-blue-600 hover:bg-blue-500 text-white text-xs"
              >
                <PlayCircle size={14} className="mr-2" />
                New Trade
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-zinc-900 border-zinc-800">
              <DialogHeader>
                <DialogTitle className="text-white">Execute Paper Trade</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-4">
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Asset</Label>
                  <Select value={tradeAsset} onValueChange={setTradeAsset}>
                    <SelectTrigger className="mt-1 bg-zinc-950 border-zinc-800">
                      <SelectValue placeholder="Select asset" />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800 max-h-64">
                      {assets.map(asset => (
                        <SelectItem key={asset.symbol} value={asset.symbol}>
                          <div className="flex items-center gap-2">
                            <Badge className="text-[8px] bg-zinc-700">{asset.asset_type}</Badge>
                            <span>{asset.name}</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {tradeAsset && (
                    <p className="text-xs text-zinc-500 mt-1">
                      Current Price: <span className="text-white font-mono">${getSelectedAssetPrice().toFixed(4)}</span>
                    </p>
                  )}
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
                  <p className="text-xs text-zinc-500 mt-1">
                    Est. Total: <span className="text-white font-mono">${(tradeQuantity * getSelectedAssetPrice()).toLocaleString()}</span>
                  </p>
                </div>
                
                <Button
                  onClick={executeTrade}
                  disabled={executing || !tradeAsset}
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white"
                >
                  {executing ? (
                    <RefreshCcw size={14} className="mr-2 animate-spin" />
                  ) : (
                    <DollarSign size={14} className="mr-2" />
                  )}
                  Execute Paper {tradeAction}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </header>

      <div className="p-4 sm:p-6">
        <Tabs defaultValue="portfolio" className="w-full">
          <TabsList className="bg-zinc-900 border border-zinc-800 mb-4">
            <TabsTrigger value="portfolio" className="data-[state=active]:bg-zinc-800">
              <Wallet size={14} className="mr-2" />
              Portfolio
            </TabsTrigger>
            <TabsTrigger value="markets" className="data-[state=active]:bg-zinc-800">
              <BarChart3 size={14} className="mr-2" />
              Markets
            </TabsTrigger>
            <TabsTrigger value="history" className="data-[state=active]:bg-zinc-800">
              <History size={14} className="mr-2" />
              History
            </TabsTrigger>
          </TabsList>

          <TabsContent value="portfolio">
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
                      <Zap size={16} className="text-amber-500" />
                      <span className="text-[10px] text-zinc-500 uppercase">Trades</span>
                    </div>
                    <div className="text-xl font-bold font-mono text-white">
                      {portfolio?.trade_count || 0}
                    </div>
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
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Qty</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Avg Price</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Current</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">Value</th>
                            <th className="px-4 py-2 text-right text-zinc-400 uppercase">P&L</th>
                          </tr>
                        </thead>
                        <tbody>
                          {portfolio.positions.map((pos, i) => (
                            <tr key={i} className="border-t border-zinc-800 hover:bg-zinc-800/50">
                              <td className="px-4 py-3">
                                <div className="flex flex-col">
                                  <span className="font-semibold text-white">{pos.asset}</span>
                                  <span className="text-[10px] text-zinc-500">{pos.asset_name}</span>
                                </div>
                              </td>
                              <td className="px-4 py-3 text-right font-mono text-zinc-300">{pos.quantity}</td>
                              <td className="px-4 py-3 text-right font-mono text-zinc-400">${pos.avg_price?.toFixed(4)}</td>
                              <td className="px-4 py-3 text-right font-mono text-white">${pos.current_price?.toFixed(4)}</td>
                              <td className="px-4 py-3 text-right font-mono text-zinc-300">${pos.market_value?.toLocaleString()}</td>
                              <td className={`px-4 py-3 text-right font-mono font-semibold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl?.toFixed(2)} ({pos.unrealized_pnl_pct?.toFixed(2)}%)
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
                      <p className="text-xs mt-1">Execute a paper trade to open a position</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Panel */}
              <div className="col-span-12 lg:col-span-4 space-y-4">
                {/* Allocation Chart */}
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                  <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Allocation</h3>
                  <div className="h-48">
                    {pieData.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <RechartsPie>
                          <Pie
                            data={pieData}
                            cx="50%"
                            cy="50%"
                            innerRadius={40}
                            outerRadius={60}
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
                          <Legend formatter={(value) => <span className="text-zinc-400 text-xs">{value}</span>} />
                        </RechartsPie>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-full flex items-center justify-center text-zinc-600">
                        <p className="text-sm">No allocation data</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Performance Card */}
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-sm p-4">
                  <h3 className="text-xs font-bold text-amber-400 uppercase tracking-widest mb-3">Paper Trading Stats</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Initial Capital</span>
                      <span className="font-mono text-white">${portfolio?.initial_capital?.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Return</span>
                      <span className={`font-mono ${portfolio?.total_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {portfolio?.total_pnl_pct >= 0 ? '+' : ''}{portfolio?.total_pnl_pct?.toFixed(2)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-zinc-500">Total Trades</span>
                      <span className="font-mono text-white">{portfolio?.trade_count}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="markets">
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Live Market Prices</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {assetPrices.map(asset => (
                  <div key={asset.symbol} className="bg-zinc-950/50 border border-zinc-800 rounded-sm p-3 hover:border-zinc-700 transition-colors">
                    <div className="flex items-center justify-between mb-2">
                      <Badge className="text-[9px] bg-zinc-700">{asset.asset_type}</Badge>
                      <span className={`text-xs font-mono ${asset.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {asset.change_pct >= 0 ? '+' : ''}{asset.change_pct}%
                      </span>
                    </div>
                    <div className="font-semibold text-white">{asset.symbol}</div>
                    <div className="text-xs text-zinc-500">{asset.name}</div>
                    <div className="text-lg font-mono font-bold text-white mt-1">
                      ${asset.price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}
                    </div>
                    <div className="text-[10px] text-zinc-600 mt-1">{asset.source}</div>
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="history">
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-4">Trade History</h3>
              <ScrollArea className="h-96">
                {tradeHistory.length > 0 ? (
                  <div className="space-y-2">
                    {tradeHistory.map((trade, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-zinc-950/50 border border-zinc-800 rounded-sm">
                        <div className="flex items-center gap-3">
                          <Badge className={`text-[9px] ${trade.action === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                            {trade.action}
                          </Badge>
                          <div>
                            <div className="font-semibold text-white">{trade.asset}</div>
                            <div className="text-[10px] text-zinc-500">
                              {new Date(trade.timestamp).toLocaleString()}
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-sm text-white">{trade.quantity} @ ${trade.price?.toFixed(4)}</div>
                          <div className="text-[10px] text-zinc-500">Total: ${trade.total_value?.toLocaleString()}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8 text-zinc-500">
                    <History size={32} className="mx-auto mb-2 opacity-30" />
                    <p>No trade history</p>
                  </div>
                )}
              </ScrollArea>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default PaperTradingPage;
