import React, { useEffect, useRef, useState } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface PriceCardProps {
  pair: string;
  bid: number;
  ask: number;
  spread: number;
  timestamp?: string;
}

export default function PriceCard({ pair, bid, ask, spread, timestamp }: PriceCardProps) {
  const prevBidRef = useRef(bid);
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    if (bid > prevBidRef.current) {
      setFlash('up');
    } else if (bid < prevBidRef.current) {
      setFlash('down');
    }
    prevBidRef.current = bid;
    const timer = setTimeout(() => setFlash(null), 400);
    return () => clearTimeout(timer);
  }, [bid]);

  const isUp = flash === 'up';
  const isDown = flash === 'down';
  const pairLabel = pair.replace('_', '/').toUpperCase();

  return (
    <div className={`card relative overflow-hidden ${flash === 'up' ? 'flash-up' : flash === 'down' ? 'flash-down' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-bold text-white">{pairLabel}</h3>
        <div className="flex items-center gap-1">
          {isUp && <TrendingUp className="w-4 h-4 text-emerald-400" />}
          {isDown && <TrendingDown className="w-4 h-4 text-red-400" />}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 mb-2">
        <div>
          <span className="text-xs text-slate-400 block">Bid</span>
          <span className={`text-xl font-mono font-bold ${isUp ? 'text-emerald-400' : isDown ? 'text-red-400' : 'text-white'}`}>
            {bid.toFixed(5)}
          </span>
        </div>
        <div>
          <span className="text-xs text-slate-400 block">Ask</span>
          <span className={`text-xl font-mono font-bold ${isUp ? 'text-emerald-400' : isDown ? 'text-red-400' : 'text-white'}`}>
            {ask.toFixed(5)}
          </span>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-400">
          Spread: <span className={`font-mono ${spread > 3 ? 'text-amber-400' : 'text-slate-300'}`}>{spread.toFixed(1)} pips</span>
        </span>
        {timestamp && (
          <span className="text-slate-500">
            {new Date(timestamp).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
}
