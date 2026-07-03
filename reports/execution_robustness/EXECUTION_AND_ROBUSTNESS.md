# Execution Model + Small-Sample Robustness

Net-of-cost replay of the 2024-2025 NFP/CPI/FOMC events on real intraday data (crypto: Binance aggTrades; FX/OIL: Dukascopy tick with real bid/ask). Answers: does the selectivity edge survive realistic spread+slippage+commission+latency, and is it statistically real at n~=60?

## 1. Cost assumptions (per side, bps)

FX half-spread and event-widening are **measured from real Dukascopy bid/ask** (see the measured table below). OIL and CRYPTO use venue-default spreads because their available archives carry no real L1 quotes (crypto = trades only; the WTI export is bid==ask 5-second bars). slippage/commission/latency are venue schedules.


**retail_conservative**

```
 asset  half_spread_bps  event_mult  event_secs  slippage_bps  commission_bps  latency_s
    FX           0.2015       2.115        60.0           0.2             0.2       0.75
   OIL           1.0000       5.000        60.0           1.0             0.5       0.75
CRYPTO           1.0000       4.000        60.0           3.0            10.0       1.00
```


**retail_optimistic**

```
 asset  half_spread_bps  event_mult  event_secs  slippage_bps  commission_bps  latency_s
    FX           0.2015       2.115        30.0           0.1             0.2        0.4
   OIL           1.0000       3.000        30.0           0.5             0.5        0.4
CRYPTO           1.0000       2.500        30.0           1.5             4.0        0.5
```


**Measured spreads (real Dukascopy bid/ask)**

```
asset  normal_spread_bps  event_spread_bps  half_spread_bps  event_spread_mult  n_normal  n_event
   FX              0.340             0.611            0.170               1.80     62070    35373
   FX              0.467             1.136            0.233               2.43     91590    37376
```


## 2. Gross vs net P&L, and the selectivity split

`ALL` = every event; `SMALL` = early move below the measured cutoff; `NONSMALL` = mid/big. Means in bps with bootstrap 95% CIs.

```
 asset            scenario   policy   n  mean_bps  mean_lo  mean_hi  win_rate  win_lo  win_hi
CRYPTO               gross      ALL  63       1.4     -3.8      5.9      74.6    63.5    84.1
CRYPTO               gross    SMALL  40      -0.3     -6.7      5.2      77.5    65.0    90.0
CRYPTO               gross NONSMALL  23       4.3     -3.9     12.2      69.6    52.2    87.0
CRYPTO retail_conservative      ALL  63     -29.8    -34.8    -25.4       4.8     0.0    11.1
CRYPTO retail_conservative    SMALL  40     -32.2    -38.4    -26.6       2.5     0.0     7.5
CRYPTO retail_conservative NONSMALL  23     -25.7    -32.7    -18.9       8.7     0.0    21.7
CRYPTO   retail_optimistic      ALL  63     -12.5    -17.4     -8.1      15.9     7.9    25.4
CRYPTO   retail_optimistic    SMALL  40     -15.0    -21.2     -9.5      10.0     2.5    20.0
CRYPTO   retail_optimistic NONSMALL  23      -8.2    -15.3     -1.6      26.1     8.7    43.5
    FX               gross      ALL 124       0.7     -0.7      1.9      86.3    79.8    91.9
    FX               gross    SMALL  45       0.7     -0.7      2.0      82.2    71.1    93.3
    FX               gross NONSMALL  79       0.6     -1.4      2.3      88.6    81.0    94.9
    FX retail_conservative      ALL 124      -0.8     -2.0      0.3      51.6    42.7    60.5
    FX retail_conservative    SMALL  45      -0.6     -2.1      0.7      57.8    42.2    71.1
    FX retail_conservative NONSMALL  79      -0.9     -2.7      0.6      48.1    36.7    59.5
    FX   retail_optimistic      ALL 124      -0.3     -1.5      0.8      64.5    55.6    72.6
    FX   retail_optimistic    SMALL  45      -0.2     -1.6      1.1      73.3    60.0    86.7
    FX   retail_optimistic NONSMALL  79      -0.3     -2.1      1.2      59.5    48.1    69.6
   OIL               gross      ALL  63      -0.8     -6.2      4.0      61.9    49.2    73.0
   OIL               gross    SMALL  55      -2.4     -8.1      2.2      61.8    49.1    74.5
   OIL               gross NONSMALL   8      10.3     -1.9     26.6      62.5    25.0    87.5
   OIL retail_conservative      ALL  63      -5.6    -10.8     -1.1      28.6    17.5    39.7
   OIL retail_conservative    SMALL  55      -7.0    -12.4     -2.6      25.5    14.5    38.2
   OIL retail_conservative NONSMALL   8       3.8    -11.2     21.5      50.0    12.5    87.5
   OIL   retail_optimistic      ALL  63      -4.6     -9.8     -0.1      33.3    22.2    44.4
   OIL   retail_optimistic    SMALL  55      -6.0    -11.4     -1.6      30.9    20.0    43.6
   OIL   retail_optimistic NONSMALL   8       4.8    -10.2     22.5      50.0    12.5    87.5
```


## 3. Is the selectivity edge statistically real? (net, retail_conservative)

Permutation test of NONSMALL vs SMALL net P&L per trade, Benjamini-Hochberg corrected across assets. `reject_H0=True` means the non-small edge is significant at FDR 5%.

```
 asset            scenario  mean_nonsmall  mean_small  diff_bps  p_value  n_nonsmall  n_small  q_value  reject_H0
CRYPTO retail_conservative          -25.7       -32.2       6.6   0.1952          23       40   0.2928      False
    FX retail_conservative           -0.9        -0.6      -0.3   0.8096          79       45   0.8096      False
   OIL retail_conservative            3.8        -7.0      10.8   0.1627           8       55   0.2928      False
```


**Bayesian win rate of the selective (non-small) net trades** (Beta-Binomial, uniform prior; posterior mean shrinks toward 50% when n is small):

```
 asset            scenario  raw_win_%  post_mean_%  cred_lo_%  cred_hi_%  n
CRYPTO retail_conservative        8.7         12.0        2.7       27.0 23
    FX retail_conservative       48.1         48.1       37.4       59.0 79
   OIL retail_conservative       50.0         50.0       21.2       78.8  8
```


## 4. Quantum-inspired threshold optimization

Simulated annealing (the classical analogue of quantum annealing) picks the early-move threshold that maximises a **robust** objective -- the bootstrap lower bound of net P&L, penalised below 8 trades -- so it cannot chase a lucky thin cell. Compared to the independently-measured small/mid cutoff:

```
 asset  annealed_theta_bps  measured_small_cut_bps  kept_trades  kept_mean_net_bps  kept_robust_lo_bps
CRYPTO                84.4                    48.6           10              -22.8               -30.4
    FX                 0.6                    21.1          120               -0.7                -2.0
   OIL                20.0                    22.8           10                2.8                -9.0
```


## 5. Honest reading

- Paper-account P&L is not used anywhere here; this is real-data replay with an explicit fill model, so the **net** columns are the trustworthy ones.

- The gross-vs-net gap is dominated by crypto commission (IBKR Zerohash 12-18 bps / Binance taker 5-10 bps round trip); FX is cheap (measured sub-bps spread), OIL in between.

- Selectivity is only worth claiming where the permutation test survives BH correction AND the Bayesian credible interval stays above 50%. Where it does not, n is simply too small to assert an edge -- which is the point of doing this honestly.

- No quantum hardware is used or needed: the annealer is a CPU algorithm. Quantum would not help the real bottleneck (only ~60 events per asset); more events would.
