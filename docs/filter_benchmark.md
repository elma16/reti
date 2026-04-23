# CQL filter benchmark: runtime ranking

Benchmark of 84 CQL filters on **88,843 games** (LumbrasGigaBase OTB 1900-1949,
62 MB) using CQLi 1.0.6 (arm64), single-threaded, averaged over 3 runs.

Baseline (`cql()` + `true`, matching every position): **4.226 s**

## Ranking by average runtime

Filters slower than baseline have a positive marginal cost; filters faster
than baseline terminate early because they reject most positions/games.

| Rank | Filter | Avg (s) | Marginal (s) | Slowdown | Matches | Category |
|------|--------|---------|--------------|----------|---------|----------|
| 1 | standardfen | 165.115 | +160.889 | 39.07x | 1,980 | FEN regex |
| 2 | currentfen | 160.894 | +156.668 | 38.07x | 1,980 | FEN regex |
| 3 | find_all | 14.431 | +10.206 | 3.42x | 1,861,392 | inter-position |
| 4 | reachableposition | 11.940 | +7.714 | 2.83x | 6,963,747 | position validation |
| 5 | shift | 8.682 | +4.456 | 2.05x | 52,085 | transform |
| 6 | find_mate | 8.310 | +4.084 | 1.97x | 172,704 | inter-position |
| 7 | str_concat | 8.134 | +3.908 | 1.92x | 6,963,747 | string ops |
| 8 | find_check | 6.870 | +2.644 | 1.63x | 5,727,291 | inter-position |
| 9 | line_consec_knight | 6.158 | +1.932 | 1.46x | 284,630 | line sequence |
| 10 | ray_bishop | 5.455 | +1.229 | 1.29x | 4,621,390 | ray |
| 11 | zobristkey | 5.349 | +1.124 | 1.27x | 6,963,747 | hash |
| 12 | lowercase | 5.301 | +1.075 | 1.25x | 6,963,747 | string ops |
| 13 | uppercase | 5.287 | +1.061 | 1.25x | 6,963,747 | string ops |
| 14 | line_captures | 5.076 | +0.850 | 1.20x | 96,878 | line sequence |
| 15 | diagonal | 4.828 | +0.602 | 1.14x | 6,963,747 | direction ray |
| 16 | connectedpawns | 4.798 | +0.572 | 1.14x | 6,791,517 | pawn structure |
| 17 | orthogonal | 4.795 | +0.569 | 1.13x | 6,963,747 | direction ray |
| 18 | up | 4.746 | +0.520 | 1.12x | 6,957,863 | direction ray |
| 19 | max_min | 4.743 | +0.517 | 1.12x | 6,963,747 | math |
| 20 | horizontal | 4.740 | +0.515 | 1.12x | 6,963,747 | direction ray |
| 21 | vertical | 4.709 | +0.483 | 1.11x | 6,963,747 | direction ray |
| 22 | legalposition | 4.707 | +0.482 | 1.11x | 6,963,747 | position validation |
| 23 | left | 4.693 | +0.468 | 1.11x | 6,918,431 | direction ray |
| 24 | power | 4.672 | +0.447 | 1.11x | 6,962,669 | material |
| 25 | abs | 4.653 | +0.427 | 1.10x | 6,963,747 | math |
| 26 | if_filter | 4.652 | +0.426 | 1.10x | 6,599,341 | control flow |
| 27 | right | 4.637 | +0.411 | 1.10x | 6,348,441 | direction ray |
| 28 | northeast | 4.620 | +0.394 | 1.09x | 6,343,002 | direction ray |
| 29 | sqrt | 4.589 | +0.364 | 1.09x | 6,963,747 | math |
| 30 | colortype | 4.576 | +0.350 | 1.08x | 6,334,600 | piece type |
| 31 | depth | 4.561 | +0.335 | 1.08x | 6,963,747 | game tree |
| 32 | positionid | 4.555 | +0.329 | 1.08x | 6,963,747 | position |
| 33 | sort_power | 4.544 | +0.318 | 1.08x | 6,963,747 | sort |
| 34 | mainline | 4.534 | +0.308 | 1.07x | 6,963,747 | game tree |
| 35 | ray_rook | 4.483 | +0.257 | 1.06x | 362,235 | ray |
| 36 | dark | 4.357 | +0.132 | 1.03x | 5,569,651 | board geometry |
| 37 | between | 4.222 | -0.003 | 1.00x | 3,686,714 | board geometry |
| 38 | move_any | 4.210 | -0.016 | 1.00x | 1,232,641 | move |
| 39 | isolatedpawns | 4.132 | -0.094 | 0.98x | 3,465,960 | pawn structure |
| 40 | attackedby_basic | 4.121 | -0.104 | 0.98x | 3,549,599 | attacks |
| 41 | move_capture | 4.057 | -0.169 | 0.96x | 659,832 | move |
| 42 | sidetomove | 4.026 | -0.200 | 0.95x | 3,502,392 | board state |
| 43 | pieceid | 4.006 | -0.220 | 0.95x | 2,704,592 | piece tracking |
| 44 | passedpawns | 3.928 | -0.298 | 0.93x | 1,898,729 | pawn structure |
| 45 | btm | 3.844 | -0.381 | 0.91x | 3,461,355 | board state |
| 46 | move_castles | 3.805 | -0.420 | 0.90x | 139,687 | move |
| 47 | wtm | 3.779 | -0.446 | 0.89x | 3,502,392 | board state |
| 48 | doubledpawns | 3.751 | -0.474 | 0.89x | 1,638,238 | pawn structure |
| 49 | xray | 3.730 | -0.496 | 0.88x | 227,126 | ray |
| 50 | makesquare | 3.719 | -0.507 | 0.88x | 1,930,013 | board geometry |
| 51 | type | 3.676 | -0.550 | 0.87x | 1,930,013 | piece type |
| 52 | stalemate | 3.553 | -0.673 | 0.84x | 40 | board state |
| 53 | down | 3.532 | -0.694 | 0.84x | 1,660,139 | direction ray |
| 54 | pin | 3.347 | -0.879 | 0.79x | 162,299 | ray |
| 55 | terminal | 3.345 | -0.881 | 0.79x | 88,843 | game tree |
| 56 | initial | 3.340 | -0.885 | 0.79x | 88,843 | game tree |
| 57 | light | 3.310 | -0.916 | 0.78x | 1,394,096 | board geometry |
| 58 | piece_count_rooks | 3.297 | -0.929 | 0.78x | 1,121,857 | piece count |
| 59 | line_short | 3.291 | -0.935 | 0.78x | 7 | line sequence |
| 60 | check | 3.264 | -0.962 | 0.77x | 367,315 | board state |
| 61 | piece_count_queens | 3.228 | -0.997 | 0.76x | 1,788,750 | piece count |
| 62 | result_white | 3.191 | -1.035 | 0.76x | 2,914,144 | metadata |
| 63 | movenumber | 3.048 | -1.178 | 0.72x | 1,057,935 | move number |
| 64 | piece_iter | 3.036 | -1.190 | 0.72x | 534,363 | iteration |
| 65 | ply | 3.008 | -1.217 | 0.71x | 979,761 | move number |
| 66 | flip | 2.803 | -1.423 | 0.66x | 25,063 | transform |
| 67 | rotate90 | 2.795 | -1.431 | 0.66x | 25,063 | transform |
| 68 | result_draw | 2.792 | -1.434 | 0.66x | 1,793,495 | metadata |
| 69 | halfmoveclock | 2.757 | -1.468 | 0.65x | 209,328 | move number |
| 70 | move_promotion | 2.706 | -1.520 | 0.64x | 5,158 | move |
| 71 | move_enpassant | 2.688 | -1.538 | 0.64x | 4,554 | move |
| 72 | flipvertical | 2.674 | -1.552 | 0.63x | 365,871 | transform |
| 73 | file_rank | 2.660 | -1.566 | 0.63x | 242,127 | board geometry |
| 74 | flipcolor | 2.642 | -1.584 | 0.63x | 1,651 | transform |
| 75 | piece_count_all | 2.613 | -1.613 | 0.62x | 98,131 | piece count |
| 76 | square_iter | 2.555 | -1.671 | 0.60x | 44,900 | iteration |
| 77 | piece_count_pawns | 2.531 | -1.694 | 0.60x | 85,114 | piece count |
| 78 | promotedpieces | 2.383 | -1.843 | 0.56x | 28,445 | piece tracking |
| 79 | fliphorizontal | 2.376 | -1.850 | 0.56x | 15,000 | transform |
| 80 | attacks_basic | 2.279 | -1.947 | 0.54x | 0 | attacks |
| 81 | rotate45 | 2.255 | -1.971 | 0.53x | 360 | transform |
| 82 | mate | 2.233 | -1.993 | 0.53x | 2,909 | board state |
| 83 | gamenumber | 2.199 | -2.027 | 0.52x | 72,811 | metadata |

## Cost tiers

### Expensive (>10x baseline)

| Filter | Slowdown | Notes |
|--------|----------|-------|
| `standardfen` | 39x | Regex on full standard FEN string. Avoid if possible. |
| `currentfen` | 38x | Regex on full FEN string. Use piece placement checks instead. |

### Moderate (2-4x baseline)

| Filter | Slowdown | Notes |
|--------|----------|-------|
| `find all` | 3.4x | Inter-position search across all positions. Necessary for game-wide aggregation. |
| `reachableposition` | 2.8x | Validates position reachability. CQLi only. |
| `shift` | 2.1x | Pattern matching across board translations. Often unavoidable for location-independent patterns. |
| `find` (mate) | 2.0x | Forward search for mate. Cheaper than `find all`. |

### Mild (1.2-2x baseline)

| Filter | Slowdown | Notes |
|--------|----------|-------|
| `str` concat / regex | 1.9x | String operations per position add up. |
| `find` (check) | 1.6x | Forward search for check. Cheaper than find(mate). |
| `line` (3+ steps) | 1.5x | Multi-step move sequence matching. Cost grows with step count. |
| `ray` (bishop diag) | 1.3x | Diagonal ray scanning. |
| `zobristkey` | 1.3x | Position hash computation. CQLi only. |
| `lowercase`/`uppercase` | 1.25x | String case conversion per position. |
| `line` (2 steps) | 1.2x | Short sequence matching. |

### Cheap (<1.2x baseline)

Everything else is essentially free — direction rays, pawn structure filters,
piece counts, attacks/attackedby, transforms (flipcolor, flip, rotate90),
move filters, power, board geometry (dark/light, file/rank), metadata
(result, gamenumber), iteration (square, piece), math (sqrt, abs), and
control flow (if).

Notably, most **transforms** (flipcolor, flip, rotate90, flipvertical,
fliphorizontal) are *cheaper* than baseline because they reject non-matching
positions early.

## Methodology

- Binary: CQLi 1.0.6 (arm64, macOS)
- PGN: LumbrasGigaBase_OTB_1900-1949.pgn (88,843 games, 62 MB)
- Mode: single-threaded (`-s`) for stable, reproducible timing
- Runs: 3 per filter, averaged
- Each filter tested in isolation: `cql()\n<filter expression>`
- Baseline: `cql()\ntrue` (matches every position in every game)
- Script: `scripts/benchmark_filters.py`

Filters that reject more positions run faster than baseline because CQLi
stops evaluating a game once no positions can match. The "marginal cost"
column (avg minus baseline) isolates the per-position compute cost of the
filter itself.
