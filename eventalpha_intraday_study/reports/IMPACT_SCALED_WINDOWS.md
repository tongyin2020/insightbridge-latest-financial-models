# Impact-scaled windows (per-bucket, live-ready parameters)

Bucket chosen at entry from the observed early-move magnitude (bps).
Small = stand down / size down; big = commit fast, hold long.

## CRYPTO  (bucket by |move|: small < 48.6 bps, mid < 106.9 bps, big >= 106.9 bps)

| bucket | n | move bps | min_wait | max_wait | time_stop |
|---|--:|--:|--:|--:|--:|
| small | 21 | 33.1 | 115 | 225 | 690 |
| mid | 21 | 79.7 | 35 | 225 | 1350 |
| big | 21 | 144.0 | 5 | 705 | 1800 |

## FX  (bucket by |move|: small < 21.1 bps, mid < 41.8 bps, big >= 41.8 bps)

| bucket | n | move bps | min_wait | max_wait | time_stop |
|---|--:|--:|--:|--:|--:|
| small | 42 | 11.6 | 105 | 345 | 1500 |
| mid | 42 | 30.9 | 30 | 330 | 1620 |
| big | 42 | 53.9 | 30 | 1110 | 1800 |

## OIL  (bucket by |move|: small < 22.8 bps, mid < 42.4 bps, big >= 42.4 bps)

| bucket | n | move bps | min_wait | max_wait | time_stop |
|---|--:|--:|--:|--:|--:|
| small | 21 | 16.1 | 60 | 360 | 690 |
| mid | 21 | 31.3 | 65 | 630 | 1650 |
| big | 21 | 59.0 | 60 | 1200 | 1800 |
