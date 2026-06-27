import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, TrendingUp, TrendingDown, Activity, RefreshCcw,
  AlertTriangle, Calendar, BarChart3, Clock, ChevronDown, Minus
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, Legend, ReferenceLine,
  ComposedChart, Bar
} from 'recharts';
import { Button } from '../components/ui/button';
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '../components/ui/tabs';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const YieldCurvePage = () => {
  const navigate = useNavigate();
  const [currentCurve, setCurrentCurve] = useState(null);
  const [historicalData, setHistoricalData] = useState([]);
  const [heatmapData, setHeatmapData] = useState([]);
  const [auctions, setAuctions] = useState([]);
  const [auctionResults, setAuctionResults] = useState([]);
  const [auctionCalendar, setAuctionCalendar] = useState(null);
  const [loading, setLoading] = useState(true);
  const [histPeriod, setHistPeriod] = useState('3mo');
  const [heatPeriod, setHeatPeriod] = useState('3mo');

  useEffect(() => {
    fetchAllData();
  }, []);

  useEffect(() => {
    fetchHistorical();
  }, [histPeriod]);

  useEffect(() => {
    fetchHeatmap();
  }, [heatPeriod]);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      const [curveRes, histRes, heatRes, auctionRes, resultsRes, calRes] = await Promise.all([
        axios.get(`${API_URL}/api/yield-curve/current`, { withCredentials: true }),
        axios.get(`${API_URL}/api/yield-curve/historical?period=${histPeriod}`, { withCredentials: true }),
        axios.get(`${API_URL}/api/yield-curve/heatmap?period=${heatPeriod}`, { withCredentials: true }),
        axios.get(`${API_URL}/api/auctions/upcoming`, { withCredentials: true }),
        axios.get(`${API_URL}/api/auctions/results`, { withCredentials: true }),
        axios.get(`${API_URL}/api/auctions/calendar`, { withCredentials: true }),
      ]);
      setCurrentCurve(curveRes.data);
      setHistoricalData(histRes.data);
      setHeatmapData(heatRes.data);
      setAuctions(auctionRes.data);
      setAuctionResults(resultsRes.data);
      setAuctionCalendar(calRes.data);
    } catch (error) {
      console.error('Error fetching yield curve data:', error);
      toast.error('Failed to load yield curve data');
    } finally {
      setLoading(false);
    }
  };

  const fetchHistorical = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/yield-curve/historical?period=${histPeriod}`, { withCredentials: true });
      setHistoricalData(res.data);
    } catch (e) { console.error(e); }
  };

  const fetchHeatmap = async () => {
    try {
      const res = await axios.get(`${API_URL}/api/yield-curve/heatmap?period=${heatPeriod}`, { withCredentials: true });
      setHeatmapData(res.data);
    } catch (e) { console.error(e); }
  };

  // Transform current curve data for the chart
  const curveChartData = currentCurve ? [
    { tenor: '3M', yield: currentCurve.curve?.['3M']?.yield || 0, change: currentCurve.curve?.['3M']?.change_1d || 0 },
    { tenor: '2Y', yield: currentCurve.curve?.['2Y']?.yield || 0, change: currentCurve.curve?.['2Y']?.change_1d || 0 },
    { tenor: '5Y', yield: currentCurve.curve?.['5Y']?.yield || 0, change: currentCurve.curve?.['5Y']?.change_1d || 0 },
    { tenor: '10Y', yield: currentCurve.curve?.['10Y']?.yield || 0, change: currentCurve.curve?.['10Y']?.change_1d || 0 },
    { tenor: '30Y', yield: currentCurve.curve?.['30Y']?.yield || 0, change: currentCurve.curve?.['30Y']?.change_1d || 0 },
  ] : [];

  const shapeColors = {
    NORMAL: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-400' },
    FLAT: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-400' },
    INVERTED: { bg: 'bg-red-500/10', border: 'border-red-500/30', text: 'text-red-400' },
    HUMPED: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-400' },
    UNKNOWN: { bg: 'bg-zinc-500/10', border: 'border-zinc-500/30', text: 'text-zinc-400' },
  };

  const impactColors = { HIGH: 'text-red-400 bg-red-500/10', MEDIUM: 'text-amber-400 bg-amber-500/10', LOW: 'text-zinc-400 bg-zinc-500/10' };
  const demandColors = { STRONG: 'text-emerald-400 bg-emerald-500/10', AVERAGE: 'text-amber-400 bg-amber-500/10', WEAK: 'text-red-400 bg-red-500/10' };

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <RefreshCcw className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  const shape = currentCurve?.shape || {};
  const sc = shapeColors[shape.type] || shapeColors.UNKNOWN;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-300">
      <Toaster position="bottom-right" theme="dark" />

      {/* Header */}
      <header className="h-14 border-b border-zinc-800 bg-black/40 backdrop-blur-xl flex items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')} className="text-zinc-400 hover:text-white" data-testid="back-btn">
            <ArrowLeft size={18} className="mr-2" /> Dashboard
          </Button>
          <div className="flex items-center gap-2">
            <Activity size={18} className="text-cyan-500" />
            <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">Yield Curve Analytics</h1>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAllData} className="border-zinc-700 text-zinc-300" data-testid="refresh-btn">
          <RefreshCcw size={14} className="mr-2" /> Refresh
        </Button>
      </header>

      <div className="p-4 sm:p-6 max-w-7xl mx-auto">
        <Tabs defaultValue="curve" className="w-full">
          <TabsList className="bg-zinc-900 border border-zinc-800 mb-4">
            <TabsTrigger value="curve" className="data-[state=active]:bg-zinc-800" data-testid="curve-tab">
              <Activity size={14} className="mr-2" /> Yield Curve
            </TabsTrigger>
            <TabsTrigger value="historical" className="data-[state=active]:bg-zinc-800" data-testid="hist-tab">
              <BarChart3 size={14} className="mr-2" /> Historical
            </TabsTrigger>
            <TabsTrigger value="auctions" className="data-[state=active]:bg-zinc-800" data-testid="auction-tab">
              <Calendar size={14} className="mr-2" /> Auctions
            </TabsTrigger>
          </TabsList>

          {/* Current Yield Curve */}
          <TabsContent value="curve" className="space-y-4">
            {/* Shape Analysis Banner */}
            <div className={`p-4 rounded-sm border ${sc.bg} ${sc.border}`} data-testid="shape-banner">
              <div className="flex items-center gap-3 mb-2">
                {shape.type === 'INVERTED' ? <AlertTriangle size={20} className={sc.text} /> :
                 shape.type === 'FLAT' ? <Minus size={20} className={sc.text} /> :
                 <TrendingUp size={20} className={sc.text} />}
                <span className={`text-sm font-bold uppercase tracking-widest ${sc.text}`}>
                  {shape.type} Curve
                </span>
                <Badge className={`text-[9px] ${
                  shape.risk_level === 'HIGH' ? 'bg-red-500/20 text-red-400' :
                  shape.risk_level === 'MODERATE' ? 'bg-amber-500/20 text-amber-400' :
                  'bg-emerald-500/20 text-emerald-400'
                }`}>
                  {shape.risk_level} RISK
                </Badge>
              </div>
              <p className="text-xs text-zinc-400">{shape.description}</p>
              <div className="flex gap-6 mt-2 text-xs">
                <span className="text-zinc-500">Slope (10Y-3M): <span className={`font-mono font-bold ${shape.slope_10y_3m >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{shape.slope_10y_3m?.toFixed(3)}%</span></span>
                <span className="text-zinc-500">Steepness: <span className="font-mono font-bold text-blue-400">{shape.steepness?.toFixed(3)}%</span></span>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Curve Chart */}
              <div className="lg:col-span-2 bg-zinc-900/50 border border-zinc-800 rounded-sm p-4" data-testid="curve-chart">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest">US Treasury Yield Curve</h3>
                <ResponsiveContainer width="100%" height={320}>
                  <ComposedChart data={curveChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="tenor" tick={{ fill: '#a1a1aa', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#a1a1aa', fontSize: 10 }} domain={['auto', 'auto']} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '2px' }}
                      labelStyle={{ color: '#fff', fontWeight: 'bold' }}
                    />
                    <Area type="monotone" dataKey="yield" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.1} strokeWidth={2} name="Yield %" />
                    <Bar dataKey="change" fill="#8b5cf6" name="1D Change" barSize={20} />
                    <Legend wrapperStyle={{ fontSize: '10px' }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Tenor Details */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest">Tenor Details</h3>
                <div className="space-y-2">
                  {curveChartData.map(item => (
                    <div key={item.tenor} className="flex items-center justify-between p-2.5 bg-zinc-950/50 border border-zinc-800/50 rounded-sm">
                      <div>
                        <span className="text-sm font-bold text-white">{item.tenor}</span>
                        <span className="text-xs text-zinc-500 ml-2">Treasury</span>
                      </div>
                      <div className="text-right">
                        <div className="font-mono font-bold text-sm text-cyan-400">{item.yield?.toFixed(3)}%</div>
                        <div className={`text-[10px] font-mono ${item.change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {item.change >= 0 ? '+' : ''}{item.change?.toFixed(3)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                {/* Key Spreads */}
                <div className="mt-4 space-y-2">
                  <h4 className="text-[9px] font-bold text-zinc-600 uppercase tracking-widest">Key Spreads</h4>
                  {currentCurve?.curve?.['10Y'] && currentCurve?.curve?.['3M'] && (
                    <div className="flex justify-between p-2 bg-zinc-950/50 rounded-sm text-xs">
                      <span className="text-zinc-500">10Y - 3M</span>
                      <span className={`font-mono font-bold ${
                        (currentCurve.curve['10Y'].yield - currentCurve.curve['3M'].yield) >= 0 ? 'text-emerald-400' : 'text-red-400'
                      }`}>
                        {(currentCurve.curve['10Y'].yield - currentCurve.curve['3M'].yield).toFixed(3)}%
                      </span>
                    </div>
                  )}
                  {currentCurve?.curve?.['30Y'] && currentCurve?.curve?.['10Y'] && (
                    <div className="flex justify-between p-2 bg-zinc-950/50 rounded-sm text-xs">
                      <span className="text-zinc-500">30Y - 10Y</span>
                      <span className="font-mono font-bold text-blue-400">
                        {(currentCurve.curve['30Y'].yield - currentCurve.curve['10Y'].yield).toFixed(3)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Historical */}
          <TabsContent value="historical" className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest">Historical Yield Trends</h3>
              <Select value={histPeriod} onValueChange={setHistPeriod}>
                <SelectTrigger className="w-32 bg-zinc-950 border-zinc-800 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800">
                  <SelectItem value="1mo">1 Month</SelectItem>
                  <SelectItem value="3mo">3 Months</SelectItem>
                  <SelectItem value="6mo">6 Months</SelectItem>
                  <SelectItem value="1y">1 Year</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Multi-tenor line chart */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4" data-testid="hist-chart">
              <ResponsiveContainer width="100%" height={360}>
                <LineChart data={historicalData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 9 }} interval={Math.floor(historicalData.length / 8)} />
                  <YAxis tick={{ fill: '#a1a1aa', fontSize: 10 }} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '2px', fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: '10px' }} />
                  <Line type="monotone" dataKey="3M" stroke="#f97316" strokeWidth={1.5} dot={false} name="3M" />
                  <Line type="monotone" dataKey="5Y" stroke="#a855f7" strokeWidth={1.5} dot={false} name="5Y" />
                  <Line type="monotone" dataKey="10Y" stroke="#06b6d4" strokeWidth={2} dot={false} name="10Y" />
                  <Line type="monotone" dataKey="30Y" stroke="#22c55e" strokeWidth={1.5} dot={false} name="30Y" />
                  <ReferenceLine y={0} stroke="#3f3f46" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Slope History */}
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
              <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest">Curve Slope (10Y - 3M) History</h3>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={historicalData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 9 }} interval={Math.floor(historicalData.length / 8)} />
                  <YAxis tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '2px', fontSize: 11 }} />
                  <ReferenceLine y={0} stroke="#ef4444" strokeDasharray="5 5" label={{ value: 'Inversion', fill: '#ef4444', fontSize: 9 }} />
                  <Area type="monotone" dataKey="slope" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.15} name="Slope" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Heatmap */}
            {heatmapData.length > 0 && (
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Daily Yield Changes</h3>
                  <Select value={heatPeriod} onValueChange={setHeatPeriod}>
                    <SelectTrigger className="w-28 bg-zinc-950 border-zinc-800 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      <SelectItem value="1mo">1M</SelectItem>
                      <SelectItem value="3mo">3M</SelectItem>
                      <SelectItem value="6mo">6M</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <ResponsiveContainer width="100%" height={200}>
                  <ComposedChart data={heatmapData.slice(-40)}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 8 }} interval={5} />
                    <YAxis tick={{ fill: '#a1a1aa', fontSize: 10 }} />
                    <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46', borderRadius: '2px', fontSize: 10 }} />
                    <Legend wrapperStyle={{ fontSize: '9px' }} />
                    <Bar dataKey="3M_change" fill="#f97316" name="3M" stackId="a" />
                    <Bar dataKey="5Y_change" fill="#a855f7" name="5Y" stackId="a" />
                    <Bar dataKey="10Y_change" fill="#06b6d4" name="10Y" stackId="a" />
                    <Bar dataKey="30Y_change" fill="#22c55e" name="30Y" stackId="a" />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}
          </TabsContent>

          {/* Auctions */}
          <TabsContent value="auctions" className="space-y-4">
            {/* Calendar Summary */}
            {auctionCalendar && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                  <span className="text-[9px] text-zinc-600 uppercase">This Week</span>
                  <div className="text-2xl font-mono font-black text-white">{auctionCalendar.auction_count_this_week}</div>
                  <span className="text-[10px] text-zinc-500">auctions scheduled</span>
                </div>
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                  <span className="text-[9px] text-zinc-600 uppercase">Supply This Week</span>
                  <div className="text-2xl font-mono font-black text-amber-400">${auctionCalendar.total_supply_this_week_bn}B</div>
                  <span className="text-[10px] text-zinc-500">estimated issuance</span>
                </div>
                <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                  <span className="text-[9px] text-zinc-600 uppercase">Next Major</span>
                  <div className="text-lg font-bold text-cyan-400">
                    {auctionCalendar.next_major_auction?.tenor || 'None'}
                  </div>
                  <span className="text-[10px] text-zinc-500">
                    {auctionCalendar.next_major_auction?.auction_date || 'No high-impact auctions'}
                  </span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Upcoming Auctions */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest flex items-center gap-2">
                  <Calendar size={12} className="text-cyan-500" /> Upcoming Auctions
                </h3>
                <ScrollArea className="h-96">
                  <div className="space-y-1.5 pr-2">
                    {auctions.filter(a => a.impact_level !== 'LOW').map((auction, i) => (
                      <div key={i} className="flex items-center justify-between p-2.5 bg-zinc-950/50 border border-zinc-800/50 rounded-sm" data-testid={`auction-${i}`}>
                        <div className="flex items-center gap-3">
                          <div className={`w-1.5 h-8 rounded-full ${
                            auction.status === 'TODAY' ? 'bg-red-400 animate-pulse' :
                            auction.days_away <= 3 ? 'bg-amber-400' : 'bg-zinc-600'
                          }`} />
                          <div>
                            <div className="text-xs font-semibold text-white">{auction.tenor}</div>
                            <div className="flex items-center gap-2 text-[10px] text-zinc-500">
                              <span>{auction.auction_date}</span>
                              <Badge className={`text-[8px] ${impactColors[auction.impact_level]}`}>
                                {auction.impact_level}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs font-mono text-zinc-300">${auction.estimated_size_bn}B</div>
                          <div className={`text-[10px] ${
                            auction.status === 'TODAY' ? 'text-red-400 font-bold' : 'text-zinc-500'
                          }`}>
                            {auction.status === 'TODAY' ? 'TODAY' : `${auction.days_away}d`}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>

              {/* Recent Results */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-[10px] font-bold text-zinc-500 mb-3 uppercase tracking-widest flex items-center gap-2">
                  <BarChart3 size={12} className="text-purple-500" /> Recent Auction Results
                </h3>
                <ScrollArea className="h-96">
                  <div className="space-y-1.5 pr-2">
                    {auctionResults.map((result, i) => (
                      <div key={i} className="p-2.5 bg-zinc-950/50 border border-zinc-800/50 rounded-sm" data-testid={`result-${i}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-semibold text-white">{result.tenor}</span>
                          <span className="text-[10px] text-zinc-500">{result.auction_date}</span>
                        </div>
                        <div className="grid grid-cols-4 gap-2 text-[10px]">
                          <div>
                            <span className="text-zinc-600">Yield</span>
                            <div className="font-mono font-bold text-cyan-400">{result.high_yield?.toFixed(3)}%</div>
                          </div>
                          <div>
                            <span className="text-zinc-600">B/C</span>
                            <div className="font-mono font-bold text-zinc-300">{result.bid_to_cover?.toFixed(2)}x</div>
                          </div>
                          <div>
                            <span className="text-zinc-600">Tail</span>
                            <div className={`font-mono font-bold ${result.tail > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                              {result.tail > 0 ? '+' : ''}{result.tail?.toFixed(3)}
                            </div>
                          </div>
                          <div>
                            <span className="text-zinc-600">Demand</span>
                            <Badge className={`text-[7px] ${demandColors[result.demand_rating]}`}>
                              {result.demand_rating}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
};

export default YieldCurvePage;
