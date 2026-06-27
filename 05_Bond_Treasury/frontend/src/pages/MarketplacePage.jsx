import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, Store, Star, Users, TrendingUp, Search,
  Plus, RefreshCcw, Heart, Trash2, Zap, Target, Clock,
  Play, Pause, FileText
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Badge } from '../components/ui/badge';
import { ScrollArea } from '../components/ui/scroll-area';
import { Textarea } from '../components/ui/textarea';
import { Slider } from '../components/ui/slider';
import { Switch } from '../components/ui/switch';
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

const MarketplacePage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  
  const [strategies, setStrategies] = useState([]);
  const [myStrategies, setMyStrategies] = useState([]);
  const [subscriptions, setSubscriptions] = useState([]);
  const [autoExecLogs, setAutoExecLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('subscribers');
  
  // Publish dialog
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');
  const [newStrategyDesc, setNewStrategyDesc] = useState('');
  const [newStrategyType, setNewStrategyType] = useState('AI_HYBRID');
  const [newIspreadUpper, setNewIspreadUpper] = useState(15);
  const [newIspreadLower, setNewIspreadLower] = useState(10);
  const [newStopLoss, setNewStopLoss] = useState(5);
  const [newTakeProfit, setNewTakeProfit] = useState(10);
  const [publishing, setPublishing] = useState(false);
  
  // Rating dialog
  const [ratingDialogOpen, setRatingDialogOpen] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');

  useEffect(() => {
    fetchData();
  }, [sortBy]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [strategiesRes, myStrategiesRes, subscriptionsRes, logsRes] = await Promise.all([
        axios.get(`${API_URL}/api/marketplace/strategies?sort_by=${sortBy}`, { withCredentials: true }),
        axios.get(`${API_URL}/api/marketplace/my-strategies`, { withCredentials: true }),
        axios.get(`${API_URL}/api/marketplace/subscriptions`, { withCredentials: true }),
        axios.get(`${API_URL}/api/auto-execute/logs`, { withCredentials: true })
      ]);
      
      setStrategies(strategiesRes.data);
      setMyStrategies(myStrategiesRes.data);
      setSubscriptions(subscriptionsRes.data);
      setAutoExecLogs(logsRes.data);
    } catch (error) {
      console.error('Error fetching marketplace data:', error);
    } finally {
      setLoading(false);
    }
  };

  const publishStrategy = async () => {
    if (!newStrategyName.trim()) {
      toast.error('Please enter a strategy name');
      return;
    }
    
    setPublishing(true);
    try {
      await axios.post(
        `${API_URL}/api/marketplace/strategies/publish?name=${encodeURIComponent(newStrategyName)}&description=${encodeURIComponent(newStrategyDesc)}&strategy_type=${newStrategyType}`,
        {
          ispread_upper: newIspreadUpper,
          ispread_lower: newIspreadLower,
          stop_loss_pct: newStopLoss / 100,
          take_profit_pct: newTakeProfit / 100
        },
        { withCredentials: true }
      );
      
      toast.success('Strategy published to marketplace');
      setPublishDialogOpen(false);
      setNewStrategyName('');
      setNewStrategyDesc('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to publish strategy');
    } finally {
      setPublishing(false);
    }
  };

  const subscribeToStrategy = async (strategyId) => {
    try {
      await axios.post(
        `${API_URL}/api/marketplace/strategies/${strategyId}/subscribe`,
        {},
        { withCredentials: true }
      );
      toast.success('Subscribed to strategy');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to subscribe');
    }
  };

  const unsubscribeFromStrategy = async (strategyId) => {
    try {
      await axios.delete(
        `${API_URL}/api/marketplace/strategies/${strategyId}/unsubscribe`,
        { withCredentials: true }
      );
      toast.success('Unsubscribed from strategy');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to unsubscribe');
    }
  };

  const deleteStrategy = async (strategyId) => {
    try {
      await axios.delete(
        `${API_URL}/api/marketplace/strategies/${strategyId}`,
        { withCredentials: true }
      );
      toast.success('Strategy deleted');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete strategy');
    }
  };

  const toggleAutoExecute = async (strategyId, enabled) => {
    try {
      await axios.post(
        `${API_URL}/api/auto-execute/toggle/${strategyId}?enabled=${enabled}`,
        {},
        { withCredentials: true }
      );
      toast.success(enabled ? 'Auto-execute enabled' : 'Auto-execute disabled');
      // Update local state
      setSubscriptions(prev => prev.map(s => 
        s.strategy_id === strategyId ? { ...s, auto_execute: enabled } : s
      ));
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to toggle auto-execute');
    }
  };

  const submitRating = async () => {
    if (!selectedStrategy) return;
    
    try {
      await axios.post(
        `${API_URL}/api/marketplace/strategies/${selectedStrategy.id}/rate?rating=${rating}&comment=${encodeURIComponent(comment)}`,
        {},
        { withCredentials: true }
      );
      toast.success('Rating submitted');
      setRatingDialogOpen(false);
      setSelectedStrategy(null);
      setComment('');
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to submit rating');
    }
  };

  const isSubscribed = (strategyId) => {
    return subscriptions.some(s => s.strategy_id === strategyId);
  };

  const getSubscription = (strategyId) => {
    return subscriptions.find(s => s.strategy_id === strategyId);
  };

  const filteredStrategies = strategies.filter(s => 
    s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.description?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.user_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const strategyTypes = [
    { value: 'MEAN_REVERSION', label: 'Mean Reversion' },
    { value: 'MOMENTUM', label: 'Momentum' },
    { value: 'SPREAD_ARBITRAGE', label: 'Spread Arbitrage' },
    { value: 'AI_HYBRID', label: 'AI Hybrid' }
  ];

  const StrategyCard = ({ strategy, showActions = true, isOwned = false }) => {
    const sub = getSubscription(strategy.id);
    
    return (
      <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4 hover:border-zinc-700 transition-colors">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h4 className="font-semibold text-white">{strategy.name}</h4>
            <p className="text-xs text-zinc-500">by {strategy.user_name}</p>
          </div>
          <Badge className="text-[9px] bg-blue-500/20 text-blue-400">{strategy.strategy_type}</Badge>
        </div>
        
        <p className="text-xs text-zinc-400 mb-3 line-clamp-2">{strategy.description || 'No description provided'}</p>
        
        {/* Performance Metrics */}
        <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
          <div className="bg-zinc-950/50 p-2 rounded-sm">
            <span className="text-zinc-500">Return</span>
            <span className={`block font-mono font-semibold ${strategy.performance?.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {strategy.performance?.total_return_pct >= 0 ? '+' : ''}{strategy.performance?.total_return_pct?.toFixed(1)}%
            </span>
          </div>
          <div className="bg-zinc-950/50 p-2 rounded-sm">
            <span className="text-zinc-500">Sharpe</span>
            <span className="block font-mono font-semibold text-blue-400">{strategy.performance?.sharpe_ratio?.toFixed(2)}</span>
          </div>
          <div className="bg-zinc-950/50 p-2 rounded-sm">
            <span className="text-zinc-500">Max DD</span>
            <span className="block font-mono font-semibold text-red-400">-{strategy.performance?.max_drawdown_pct?.toFixed(1)}%</span>
          </div>
          <div className="bg-zinc-950/50 p-2 rounded-sm">
            <span className="text-zinc-500">Win Rate</span>
            <span className="block font-mono font-semibold text-zinc-300">{strategy.performance?.win_rate?.toFixed(0)}%</span>
          </div>
        </div>
        
        {/* Stats */}
        <div className="flex items-center gap-4 mb-3 text-xs text-zinc-500">
          <span className="flex items-center gap-1">
            <Users size={12} /> {strategy.subscribers} subscribers
          </span>
          <span className="flex items-center gap-1">
            <Star size={12} className="text-amber-400" /> {strategy.rating?.toFixed(1)} ({strategy.total_ratings})
          </span>
        </div>

        {/* Auto-Execute Toggle for subscribed strategies */}
        {sub && !isOwned && (
          <div className="flex items-center justify-between p-2 mb-3 bg-zinc-950/50 border border-zinc-800/50 rounded-sm" data-testid={`auto-exec-toggle-${strategy.id}`}>
            <div className="flex items-center gap-2">
              <Zap size={12} className={sub.auto_execute ? 'text-amber-400' : 'text-zinc-600'} />
              <span className="text-[10px] text-zinc-400">Auto-Execute</span>
            </div>
            <Switch
              checked={sub.auto_execute || false}
              onCheckedChange={(checked) => toggleAutoExecute(strategy.id, checked)}
              data-testid={`auto-exec-switch-${strategy.id}`}
            />
          </div>
        )}
        
        {/* Actions */}
        {showActions && (
          <div className="flex gap-2">
            {isOwned ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => deleteStrategy(strategy.id)}
                className="flex-1 border-red-900/50 text-red-400 hover:bg-red-950/30"
              >
                <Trash2 size={12} className="mr-1" /> Delete
              </Button>
            ) : isSubscribed(strategy.id) ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => unsubscribeFromStrategy(strategy.id)}
                  className="flex-1 border-zinc-700 text-zinc-300"
                >
                  Unsubscribe
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => { setSelectedStrategy(strategy); setRatingDialogOpen(true); }}
                  className="border-amber-900/50 text-amber-400"
                >
                  <Star size={12} />
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                onClick={() => subscribeToStrategy(strategy.id)}
                className="flex-1 bg-blue-600 hover:bg-blue-500 text-white"
              >
                <Heart size={12} className="mr-1" /> Subscribe
              </Button>
            )}
          </div>
        )}
      </div>
    );
  };

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
            <Store size={18} className="text-purple-500" />
            <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
              Strategy Marketplace
            </h1>
          </div>
        </div>
        
        <Dialog open={publishDialogOpen} onOpenChange={setPublishDialogOpen}>
          <DialogTrigger asChild>
            <Button
              data-testid="publish-strategy-btn"
              size="sm"
              className="bg-purple-600 hover:bg-purple-500 text-white text-xs"
            >
              <Plus size={14} className="mr-2" />
              Publish Strategy
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-zinc-900 border-zinc-800 max-w-md">
            <DialogHeader>
              <DialogTitle className="text-white">Publish Your Strategy</DialogTitle>
            </DialogHeader>
            <ScrollArea className="max-h-[70vh]">
              <div className="space-y-4 mt-4 pr-4">
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Strategy Name</Label>
                  <Input
                    value={newStrategyName}
                    onChange={(e) => setNewStrategyName(e.target.value)}
                    placeholder="My Winning Strategy"
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50"
                  />
                </div>
                
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Description</Label>
                  <Textarea
                    value={newStrategyDesc}
                    onChange={(e) => setNewStrategyDesc(e.target.value)}
                    placeholder="Describe your strategy..."
                    className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50 min-h-[80px]"
                  />
                </div>
                
                <div>
                  <Label className="text-xs text-zinc-500 uppercase">Strategy Type</Label>
                  <Select value={newStrategyType} onValueChange={setNewStrategyType}>
                    <SelectTrigger className="mt-1 bg-zinc-950 border-zinc-800">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-zinc-900 border-zinc-800">
                      {strategyTypes.map(st => (
                        <SelectItem key={st.value} value={st.value}>{st.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500">Ispread Upper</span>
                      <span className="text-white font-mono">{newIspreadUpper}</span>
                    </div>
                    <Slider
                      value={[newIspreadUpper]}
                      onValueChange={([v]) => setNewIspreadUpper(v)}
                      min={12}
                      max={20}
                      step={0.5}
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500">Ispread Lower</span>
                      <span className="text-white font-mono">{newIspreadLower}</span>
                    </div>
                    <Slider
                      value={[newIspreadLower]}
                      onValueChange={([v]) => setNewIspreadLower(v)}
                      min={5}
                      max={12}
                      step={0.5}
                    />
                  </div>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500">Stop Loss</span>
                      <span className="text-red-400 font-mono">{newStopLoss}%</span>
                    </div>
                    <Slider
                      value={[newStopLoss]}
                      onValueChange={([v]) => setNewStopLoss(v)}
                      min={1}
                      max={20}
                      step={1}
                    />
                  </div>
                  <div>
                    <div className="flex justify-between text-xs mb-2">
                      <span className="text-zinc-500">Take Profit</span>
                      <span className="text-emerald-400 font-mono">{newTakeProfit}%</span>
                    </div>
                    <Slider
                      value={[newTakeProfit]}
                      onValueChange={([v]) => setNewTakeProfit(v)}
                      min={1}
                      max={30}
                      step={1}
                    />
                  </div>
                </div>
                
                <Button
                  onClick={publishStrategy}
                  disabled={publishing}
                  className="w-full bg-purple-600 hover:bg-purple-500 text-white"
                >
                  {publishing ? <RefreshCcw size={14} className="mr-2 animate-spin" /> : <Store size={14} className="mr-2" />}
                  Publish to Marketplace
                </Button>
              </div>
            </ScrollArea>
          </DialogContent>
        </Dialog>
      </header>

      <div className="p-4 sm:p-6">
        <Tabs defaultValue="browse" className="w-full">
          <TabsList className="bg-zinc-900 border border-zinc-800 mb-4">
            <TabsTrigger value="browse" className="data-[state=active]:bg-zinc-800">
              <Store size={14} className="mr-2" />
              Browse
            </TabsTrigger>
            <TabsTrigger value="subscriptions" className="data-[state=active]:bg-zinc-800">
              <Heart size={14} className="mr-2" />
              Subscriptions ({subscriptions.length})
            </TabsTrigger>
            <TabsTrigger value="my-strategies" className="data-[state=active]:bg-zinc-800">
              <Target size={14} className="mr-2" />
              My Strategies ({myStrategies.length})
            </TabsTrigger>
            <TabsTrigger value="auto-execute" className="data-[state=active]:bg-zinc-800" data-testid="auto-exec-tab">
              <Zap size={14} className="mr-2" />
              Auto-Execute
            </TabsTrigger>
          </TabsList>

          <TabsContent value="browse">
            {/* Search and Filter */}
            <div className="flex flex-col sm:flex-row gap-4 mb-6">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                <Input
                  placeholder="Search strategies..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 bg-zinc-950 border-zinc-800 text-zinc-50"
                />
              </div>
              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="w-full sm:w-48 bg-zinc-950 border-zinc-800">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent className="bg-zinc-900 border-zinc-800">
                  <SelectItem value="subscribers">Most Popular</SelectItem>
                  <SelectItem value="rating">Highest Rated</SelectItem>
                  <SelectItem value="newest">Newest</SelectItem>
                  <SelectItem value="performance">Best Performance</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Strategy Grid */}
            {filteredStrategies.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredStrategies.map(strategy => (
                  <StrategyCard key={strategy.id} strategy={strategy} />
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-zinc-500">
                <Store size={48} className="mx-auto mb-4 opacity-30" />
                <p>No strategies found</p>
                <p className="text-xs mt-1">Be the first to publish a strategy!</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="subscriptions">
            {subscriptions.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {subscriptions.map(sub => {
                  const strategy = strategies.find(s => s.id === sub.strategy_id);
                  return strategy ? (
                    <StrategyCard key={sub.strategy_id} strategy={strategy} />
                  ) : (
                    <div key={sub.strategy_id} className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                      <h4 className="font-semibold text-white">{sub.strategy_name}</h4>
                      <p className="text-xs text-zinc-500">by {sub.creator_name}</p>
                      <div className="flex items-center gap-2 mt-2">
                        <Badge className={`text-[9px] ${sub.auto_execute ? 'bg-amber-500/20 text-amber-400' : 'bg-zinc-700 text-zinc-400'}`}>
                          {sub.auto_execute ? 'Auto-Execute ON' : 'Manual'}
                        </Badge>
                      </div>
                      <p className="text-xs text-zinc-600 mt-2">Subscribed {new Date(sub.subscribed_at).toLocaleDateString()}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 text-zinc-500">
                <Heart size={48} className="mx-auto mb-4 opacity-30" />
                <p>No subscriptions yet</p>
                <p className="text-xs mt-1">Subscribe to strategies to see them here</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="my-strategies">
            {myStrategies.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {myStrategies.map(strategy => (
                  <StrategyCard key={strategy.id} strategy={strategy} isOwned={true} />
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-zinc-500">
                <Target size={48} className="mx-auto mb-4 opacity-30" />
                <p>You haven't published any strategies</p>
                <p className="text-xs mt-1">Share your trading strategies with the community!</p>
              </div>
            )}
          </TabsContent>

          {/* Auto-Execute Logs Tab */}
          <TabsContent value="auto-execute">
            <div className="space-y-4">
              {/* Active Auto-Execute Strategies */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-xs font-bold text-amber-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <Zap size={14} /> Active Auto-Execute Strategies
                </h3>
                {subscriptions.filter(s => s.auto_execute).length > 0 ? (
                  <div className="space-y-2">
                    {subscriptions.filter(s => s.auto_execute).map(sub => (
                      <div key={sub.strategy_id} className="flex items-center justify-between p-3 bg-zinc-950/50 border border-zinc-800/50 rounded-sm">
                        <div className="flex items-center gap-3">
                          <div className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
                          <div>
                            <span className="text-sm font-semibold text-white">{sub.strategy_name}</span>
                            <span className="text-xs text-zinc-500 ml-2">by {sub.creator_name}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge className="text-[9px] bg-emerald-500/20 text-emerald-400">ACTIVE</Badge>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => toggleAutoExecute(sub.strategy_id, false)}
                            className="text-zinc-400 hover:text-red-400"
                            data-testid={`disable-auto-exec-${sub.strategy_id}`}
                          >
                            <Pause size={14} />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-zinc-500 text-center py-4">
                    No strategies with auto-execute enabled. Enable it from the Subscriptions tab.
                  </p>
                )}
              </div>

              {/* Execution History */}
              <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm p-4">
                <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <FileText size={14} /> Execution History
                </h3>
                <ScrollArea className="h-80">
                  {autoExecLogs.length > 0 ? (
                    <div className="space-y-2 pr-2">
                      {autoExecLogs.map((log, i) => (
                        <div 
                          key={log.id || i} 
                          className="flex items-start gap-3 p-3 bg-zinc-950/50 border border-zinc-800/50 rounded-sm"
                          data-testid={`auto-exec-log-${i}`}
                        >
                          <div className={`mt-0.5 w-2 h-2 rounded-full ${
                            log.status === 'EXECUTED' ? 'bg-emerald-400' : 
                            log.status === 'FAILED' ? 'bg-red-400' : 'bg-amber-400'
                          }`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold text-white text-xs">{log.strategy_name}</span>
                              <Badge className={`text-[8px] ${
                                log.status === 'EXECUTED' ? 'bg-emerald-500/20 text-emerald-400' :
                                log.status === 'FAILED' ? 'bg-red-500/20 text-red-400' :
                                'bg-amber-500/20 text-amber-400'
                              }`}>
                                {log.status}
                              </Badge>
                              <Badge className="text-[8px] bg-blue-500/20 text-blue-400">{log.signal_type}</Badge>
                            </div>
                            <div className="flex items-center gap-4 mt-1 text-[10px] text-zinc-500">
                              <span>Qty: {log.quantity}</span>
                              {log.execution_price > 0 && <span>Price: ${log.execution_price?.toFixed(2)}</span>}
                              {log.error_message && <span className="text-red-400">{log.error_message}</span>}
                            </div>
                            <div className="flex items-center gap-1 text-[10px] text-zinc-600 mt-1">
                              <Clock size={10} />
                              {new Date(log.created_at).toLocaleString()}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-12 text-zinc-600">
                      <Zap size={32} className="mx-auto mb-2 opacity-30" />
                      <p className="text-sm">No auto-execute history yet</p>
                      <p className="text-xs mt-1">Enable auto-execute on subscribed strategies to start</p>
                    </div>
                  )}
                </ScrollArea>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Rating Dialog */}
      <Dialog open={ratingDialogOpen} onOpenChange={setRatingDialogOpen}>
        <DialogContent className="bg-zinc-900 border-zinc-800">
          <DialogHeader>
            <DialogTitle className="text-white">Rate Strategy</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <Label className="text-xs text-zinc-500 uppercase">Rating</Label>
              <div className="flex gap-2 mt-2">
                {[1, 2, 3, 4, 5].map(r => (
                  <Button
                    key={r}
                    type="button"
                    size="sm"
                    onClick={() => setRating(r)}
                    className={`p-2 ${rating >= r ? 'bg-amber-500 text-black' : 'bg-zinc-800 text-zinc-400'}`}
                  >
                    <Star size={16} fill={rating >= r ? 'currentColor' : 'none'} />
                  </Button>
                ))}
              </div>
            </div>
            
            <div>
              <Label className="text-xs text-zinc-500 uppercase">Comment (Optional)</Label>
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Share your experience..."
                className="mt-1 bg-zinc-950 border-zinc-800 text-zinc-50"
              />
            </div>
            
            <Button onClick={submitRating} className="w-full bg-amber-600 hover:bg-amber-500 text-white">
              Submit Rating
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MarketplacePage;
