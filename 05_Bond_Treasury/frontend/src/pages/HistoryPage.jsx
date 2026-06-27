import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Toaster, toast } from 'sonner';
import {
  ArrowLeft, TrendingUp, TrendingDown, Calendar,
  Filter, Download, Search, ChevronLeft, ChevronRight
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const HistoryPage = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const itemsPerPage = 20;

  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const endpoint = user?.role === 'admin' ? '/api/trades/all' : '/api/trades';
        const res = await axios.get(`${API_URL}${endpoint}?limit=200`, { withCredentials: true });
        setTrades(res.data);
      } catch (error) {
        toast.error('Failed to load trade history');
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();
  }, [user]);

  const filteredTrades = trades.filter(trade => {
    const matchesFilter = filter === 'ALL' || trade.signal_type?.includes(filter);
    const matchesSearch = trade.signal_type?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          trade.ai_reasoning?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const paginatedTrades = filteredTrades.slice((page - 1) * itemsPerPage, page * itemsPerPage);
  const totalPages = Math.ceil(filteredTrades.length / itemsPerPage);

  const exportCSV = () => {
    const headers = ['Timestamp', 'Signal Type', 'Price', 'Quantity', 'Confidence', 'Status', 'AI Reasoning'];
    const csvContent = [
      headers.join(','),
      ...filteredTrades.map(t => [
        new Date(t.timestamp).toISOString(),
        t.signal_type,
        t.price,
        t.quantity,
        t.confidence,
        t.status,
        `"${t.ai_reasoning || ''}"`
      ].join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `trade_history_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    toast.success('Trade history exported');
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
            Back to Dashboard
          </Button>
          <h1 className="text-sm font-bold text-white uppercase tracking-widest font-heading">
            Trade History
          </h1>
        </div>
        
        <Button
          onClick={exportCSV}
          data-testid="export-btn"
          size="sm"
          className="bg-blue-600 hover:bg-blue-500 text-white text-xs"
        >
          <Download size={14} className="mr-2" />
          Export CSV
        </Button>
      </header>

      {/* Filters */}
      <div className="p-4 sm:p-6 border-b border-zinc-800 bg-zinc-900/30">
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
          <div className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto">
            <div className="relative flex-1 sm:flex-none sm:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <Input
                placeholder="Search trades..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                data-testid="search-input"
                className="pl-10 bg-zinc-950 border-zinc-800 rounded-sm text-zinc-50 placeholder:text-zinc-600 font-mono text-sm"
              />
            </div>
            
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger 
                className="w-full sm:w-40 bg-zinc-950 border-zinc-800 rounded-sm"
                data-testid="filter-select"
              >
                <Filter size={14} className="mr-2 text-zinc-500" />
                <SelectValue placeholder="Filter by type" />
              </SelectTrigger>
              <SelectContent className="bg-zinc-900 border-zinc-800">
                <SelectItem value="ALL">All Types</SelectItem>
                <SelectItem value="BOND_BUY">Bond Buy</SelectItem>
                <SelectItem value="BOND_SELL">Bond Sell</SelectItem>
                <SelectItem value="RATE_LONG">Rate Long</SelectItem>
                <SelectItem value="RATE_SHORT">Rate Short</SelectItem>
              </SelectContent>
            </Select>
          </div>
          
          <div className="text-xs text-zinc-500">
            Showing {paginatedTrades.length} of {filteredTrades.length} trades
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="p-4 sm:p-6">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
          </div>
        ) : filteredTrades.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-zinc-500">
            <Calendar size={48} className="mb-4 opacity-30" />
            <p className="text-sm">No trades found</p>
            <p className="text-xs mt-1">Executed trades will appear here</p>
          </div>
        ) : (
          <>
            <div className="bg-zinc-900/50 border border-zinc-800 rounded-sm overflow-hidden">
              <ScrollArea className="w-full">
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800 hover:bg-transparent">
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Timestamp</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Signal Type</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Price</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Quantity</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Confidence</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Status</TableHead>
                      <TableHead className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">AI Reasoning</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedTrades.map((trade, i) => (
                      <TableRow 
                        key={i} 
                        data-testid={`trade-row-${i}`}
                        className="border-zinc-800 hover:bg-zinc-800/50"
                      >
                        <TableCell className="font-mono text-xs text-zinc-400">
                          {new Date(trade.timestamp).toLocaleString()}
                        </TableCell>
                        <TableCell>
                          <Badge className={`text-[9px] font-bold rounded-sm ${
                            trade.signal_type?.includes('BUY') || trade.signal_type?.includes('LONG')
                              ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                              : 'bg-red-500/20 text-red-400 border-red-500/30'
                          }`}>
                            {trade.signal_type?.includes('BUY') || trade.signal_type?.includes('LONG') ? (
                              <TrendingUp size={10} className="mr-1" />
                            ) : (
                              <TrendingDown size={10} className="mr-1" />
                            )}
                            {trade.signal_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono text-sm text-white">
                          {trade.price?.toFixed(3)}
                        </TableCell>
                        <TableCell className="font-mono text-sm text-zinc-300">
                          {trade.quantity}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                              <div 
                                className={`h-full ${
                                  trade.confidence > 0.9 ? 'bg-emerald-500' :
                                  trade.confidence > 0.8 ? 'bg-blue-500' :
                                  'bg-amber-500'
                                }`}
                                style={{ width: `${trade.confidence * 100}%` }}
                              />
                            </div>
                            <span className="font-mono text-xs text-zinc-400">
                              {(trade.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge className={`text-[9px] rounded-sm ${
                            trade.status === 'COMPLETED' 
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-amber-500/20 text-amber-400'
                          }`}>
                            {trade.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-xs">
                          <p className="text-xs text-zinc-500 truncate">
                            {trade.ai_reasoning || '-'}
                          </p>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </ScrollArea>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="bg-zinc-900 border-zinc-800 text-zinc-400 hover:bg-zinc-800"
                >
                  <ChevronLeft size={14} className="mr-1" />
                  Previous
                </Button>
                
                <div className="flex items-center gap-2">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    const pageNum = Math.min(
                      Math.max(page - 2, 1) + i,
                      totalPages
                    );
                    return (
                      <Button
                        key={pageNum}
                        variant={page === pageNum ? "default" : "outline"}
                        size="sm"
                        onClick={() => setPage(pageNum)}
                        className={`w-8 h-8 p-0 ${
                          page === pageNum 
                            ? 'bg-blue-600 text-white' 
                            : 'bg-zinc-900 border-zinc-800 text-zinc-400 hover:bg-zinc-800'
                        }`}
                      >
                        {pageNum}
                      </Button>
                    );
                  })}
                </div>
                
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="bg-zinc-900 border-zinc-800 text-zinc-400 hover:bg-zinc-800"
                >
                  Next
                  <ChevronRight size={14} className="ml-1" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default HistoryPage;
