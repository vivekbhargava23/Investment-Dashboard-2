"""
Pure statistical primitives for the Analytics page.
Zero I/O, Decimal arithmetic, deterministic.
A1–A5 consume these functions.

Functions:
  daily_returns        – period-over-period fractional returns from a close series
  volatility_annualised – sample-std of daily returns scaled by √252
  drawdown_series      – running peak-to-trough fraction at each point
  max_drawdown         – minimum value in drawdown_series
  sharpe               – annualised Sharpe ratio from daily returns
  sma                  – simple moving average with None padding for warm-up
  rsi                  – Wilder's smoothed RSI with None padding for warm-up period
  detect_recent_cross  – find most recent golden/death cross in an SMA pair
  correlation_matrix   – Pearson correlation matrix for a set of return series
  correlation_clusters – connected components above a correlation threshold
  herfindahl_index     – concentration score from percent weights
"""
from decimal import Decimal, getcontext
from typing import Literal

getcontext().prec = 28

# ── daily_returns ──────────────────────────────────────────────────────────────


def daily_returns(closes: list[Decimal]) -> list[Decimal]:
    """
    Period-over-period fractional returns from a close-price series.

    Input: close prices (any units).
    Output: list of n-1 fractional returns; 0.05 means +5%, not 5.

    len(closes) < 2 → [].
    """
    if len(closes) < 2:
        return []
    return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]


# ── volatility_annualised ─────────────────────────────────────────────────────


def volatility_annualised(returns: list[Decimal]) -> Decimal:
    """
    Annualised volatility: sample standard deviation of daily returns × √252.

    Input: daily fractional returns.
    Output: annualised volatility as a fraction.

    Uses n-1 (Bessel's correction) denominator.
    Raises ValueError if len(returns) < 2 (need at least 2 for variance).
    """
    if len(returns) < 2:
        raise ValueError("at least 2 returns required")
    n = len(returns)
    mean = sum(returns, Decimal(0)) / n
    sq_diffs: list[Decimal] = [(r - mean) ** 2 for r in returns]
    variance = sum(sq_diffs, Decimal(0)) / (n - 1)
    return variance.sqrt() * Decimal(252).sqrt()


# ── drawdown_series ───────────────────────────────────────────────────────────


def drawdown_series(navs: list[Decimal]) -> list[Decimal]:
    """
    Running peak-to-trough drawdown at each point in the NAV series.

    Input: NAV values in any consistent units.
    Output: fractions ≤ 0; (nav[i] - peak[i]) / peak[i] where peak[i] = max(navs[0..i]).

    Empty input → []. Single value → [Decimal(0)].
    """
    if not navs:
        return []
    result: list[Decimal] = []
    peak = navs[0]
    for nav in navs:
        if nav > peak:
            peak = nav
        result.append((nav - peak) / peak)
    return result


# ── max_drawdown ──────────────────────────────────────────────────────────────


def max_drawdown(navs: list[Decimal]) -> Decimal:
    """
    Maximum drawdown: the most negative value in drawdown_series(navs).

    Input: NAV values.
    Output: fraction ≤ 0.

    Empty input → raises ValueError.
    Single value → Decimal(0).
    """
    if not navs:
        raise ValueError("navs must not be empty")
    return min(drawdown_series(navs))


# ── sharpe ────────────────────────────────────────────────────────────────────


def sharpe(returns: list[Decimal], risk_free: Decimal = Decimal(0)) -> Decimal:
    """
    Annualised Sharpe ratio.

    Formula: (mean(returns) - risk_free) / stdev(returns) × √252.
    Input: daily fractional returns; risk_free is a *daily* rate (caller converts from annual).
    Output: annualised Sharpe as a unitless Decimal.

    Uses sample standard deviation (n-1 denominator).
    Raises ValueError if len(returns) < 2 or stdev is zero (flat returns).
    """
    if len(returns) < 2:
        raise ValueError("at least 2 returns required")
    n = len(returns)
    mean = sum(returns, Decimal(0)) / n
    sq_diffs: list[Decimal] = [(r - mean) ** 2 for r in returns]
    variance = sum(sq_diffs, Decimal(0)) / (n - 1)
    if variance == 0:
        raise ValueError("zero variance: cannot compute Sharpe ratio for flat returns")
    return (mean - risk_free) / variance.sqrt() * Decimal(252).sqrt()


# ── sma ───────────────────────────────────────────────────────────────────────


def sma(closes: list[Decimal], period: int) -> list[Decimal | None]:
    """
    Simple moving average with None padding for the warm-up period.

    Input: close prices; period ≥ 1.
    Output: list of the same length as closes. result[i] is None for i < period - 1,
    else mean(closes[i - period + 1 : i + 1]).

    period < 1 → raises ValueError.
    Empty input → [].
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    if not closes:
        return []
    result: list[Decimal | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            result.append(sum(window, Decimal(0)) / period)
    return result


# ── rsi ───────────────────────────────────────────────────────────────────────


def rsi(closes: list[Decimal], period: int = 14) -> list[Decimal | None]:
    """
    Wilder's Relative Strength Index.

    Input: close prices; period (default 14).
    Output: list of the same length as closes.
      - First `period` entries are None (warm-up period).
      - Remaining entries are RSI values in [0, 100].
      - If len(closes) < period + 1, returns [].

    Wilder's smoothing:
      Seed: simple mean of the first `period` gains and losses.
      Update: avg = (prev_avg × (period-1) + current) / period.
    """
    if len(closes) < period + 1:
        return []
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [c if c > Decimal(0) else Decimal(0) for c in changes]
    losses = [-c if c < Decimal(0) else Decimal(0) for c in changes]

    avg_gain = sum(gains[:period], Decimal(0)) / period
    avg_loss = sum(losses[:period], Decimal(0)) / period

    result: list[Decimal | None] = [None] * period

    def _rsi_value(ag: Decimal, al: Decimal) -> Decimal:
        if al == Decimal(0):
            return Decimal(100)
        rs = ag / al
        return Decimal(100) - Decimal(100) / (1 + rs)

    result.append(_rsi_value(avg_gain, avg_loss))

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result.append(_rsi_value(avg_gain, avg_loss))

    return result


# ── detect_recent_cross ───────────────────────────────────────────────────────


def detect_recent_cross(
    sma_short: list[Decimal | None],
    sma_long: list[Decimal | None],
    *,
    lookback: int = 90,
) -> tuple[Literal["golden", "death", "none"], int | None]:
    """Find the most recent golden/death cross within the last *lookback* valid index pairs.

    Input shape: two equal-length lists; entries may be None during SMA warm-up.
    lookback: only the last *lookback* valid (non-None in both inputs) pairs are scanned.
    "Days ago" = index distance from the last element of the input lists (not valid-pair count).

    Returns:
      ("golden", days_ago) — most recent cross was sma_short crossing above sma_long
      ("death",  days_ago) — most recent cross was sma_short crossing below sma_long
      ("none",   None)     — no cross found in the lookback window

    A cross is detected when consecutive valid pairs (i-1 → i) show:
      golden: diff[i-1] < 0 and diff[i] > 0  (short crossed above long)
      death:  diff[i-1] > 0 and diff[i] < 0  (short crossed below long)

    Raises ValueError:
      - sma_short and sma_long have different lengths (message names both lengths)
      - fewer than 2 valid pairs exist across the entire input
      - both inputs are empty
    """
    if len(sma_short) != len(sma_long):
        raise ValueError(
            f"sma_short and sma_long must have equal length; "
            f"got {len(sma_short)} and {len(sma_long)}"
        )
    n = len(sma_short)
    if n == 0:
        raise ValueError("sma_short and sma_long must not be empty")

    # Collect all valid pairs across the full input
    valid_pairs: list[tuple[int, Decimal]] = []
    for i in range(n):
        s, lo = sma_short[i], sma_long[i]
        if s is not None and lo is not None:
            valid_pairs.append((i, s - lo))

    if len(valid_pairs) < 2:
        raise ValueError(
            f"insufficient SMA history for cross detection: "
            f"need at least 2 valid pairs, got {len(valid_pairs)}"
        )

    # Consider only the last *lookback* valid pairs
    window = valid_pairs[-lookback:]

    # Walk forward to find the most recent cross (last cross wins)
    most_recent_kind: Literal["golden", "death"] | None = None
    most_recent_days_ago: int | None = None

    for j in range(1, len(window)):
        _, prev_diff = window[j - 1]
        curr_raw_idx, curr_diff = window[j]

        if prev_diff < Decimal(0) and curr_diff > Decimal(0):
            kind: Literal["golden", "death"] = "golden"
        elif prev_diff > Decimal(0) and curr_diff < Decimal(0):
            kind = "death"
        else:
            continue

        most_recent_kind = kind
        most_recent_days_ago = (n - 1) - curr_raw_idx

    if most_recent_kind is None:
        return ("none", None)
    return (most_recent_kind, most_recent_days_ago)


# ── correlation_matrix ────────────────────────────────────────────────────────


def correlation_matrix(
    returns_by_ticker: dict[str, list[Decimal]],
) -> dict[str, dict[str, Decimal]]:
    """
    Pearson correlation matrix for a set of return series.

    Input: dict mapping ticker → list of daily fractional returns.
    Output: nested dict where result[A][B] is Pearson correlation of A and B.
      - Diagonal: exactly Decimal(1).
      - Off-diagonal: symmetric (result[A][B] == result[B][A]).
      - All input series must have equal length; raises ValueError on mismatch.

    Empty input ({}) → {}.
    Single ticker → {T: {T: Decimal(1)}}.

    Implementation note: correlation values are computed with float arithmetic
    internally and converted back to Decimal at the boundary. This is deliberate:
    the Decimal sqrt chain for matrix-scale inputs accumulates more error than
    a single float→Decimal boundary conversion.
    """
    if not returns_by_ticker:
        return {}
    tickers = list(returns_by_ticker.keys())
    ref_len = len(returns_by_ticker[tickers[0]])
    for t in tickers[1:]:
        n = len(returns_by_ticker[t])
        if n != ref_len:
            raise ValueError(
                f"series length mismatch: {tickers[0]} has {ref_len}, {t} has {n}"
            )

    # Convert to float for efficient dot-product math; result is Decimal
    float_series = {t: [float(v) for v in returns_by_ticker[t]] for t in tickers}

    result: dict[str, dict[str, Decimal]] = {}
    for a in tickers:
        result[a] = {}
        for b in tickers:
            if a == b:
                result[a][b] = Decimal(1)
                continue
            xs = float_series[a]
            ys = float_series[b]
            n = len(xs)
            if n == 0:
                result[a][b] = Decimal(0)
                continue
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            var_x = sum((x - mean_x) ** 2 for x in xs)
            var_y = sum((y - mean_y) ** 2 for y in ys)
            denom = (var_x * var_y) ** 0.5
            if denom == 0.0:
                result[a][b] = Decimal(0)
            else:
                result[a][b] = Decimal(str(round(cov / denom, 10)))
    return result


# ── correlation_clusters ─────────────────────────────────────────────────────


def correlation_clusters(
    matrix: dict[str, dict[str, Decimal]],
    threshold: Decimal,
    min_size: int = 3,
) -> list[list[str]]:
    """
    Return connected ticker clusters whose pairwise edges exceed ``threshold``.

    Input shape: square nested dict where ``matrix[A][B]`` is the correlation
    between tickers A and B. Off-diagonal edges are included only when the
    correlation is strictly greater than ``threshold`` (``>``, not ``>=``).
    Components with fewer than ``min_size`` tickers are omitted.

    Edge cases: empty matrix -> ``[]``; single ticker -> ``[]``; no edges above
    threshold -> ``[]``. Tickers inside each cluster are sorted alphabetically.
    Output clusters are sorted by descending size, then alphabetically by the
    first ticker.
    """
    if len(matrix) < min_size or min_size < 1:
        return []

    tickers = sorted(matrix)
    parent = {ticker: ticker for ticker in tickers}

    def find(ticker: str) -> str:
        root = parent[ticker]
        if root != ticker:
            parent[ticker] = find(root)
        return parent[ticker]

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for index, left in enumerate(tickers):
        row = matrix.get(left, {})
        for right in tickers[index + 1 :]:
            if row.get(right, Decimal("-Infinity")) > threshold:
                union(left, right)

    components: dict[str, list[str]] = {}
    for ticker in tickers:
        root = find(ticker)
        components.setdefault(root, []).append(ticker)

    clusters = [sorted(group) for group in components.values() if len(group) >= min_size]
    return sorted(clusters, key=lambda group: (-len(group), group[0]))


# ── herfindahl_index ──────────────────────────────────────────────────────────


def herfindahl_index(weights_pct: list[Decimal]) -> Decimal:
    """
    Return the Herfindahl-Hirschman Index from weights expressed in percent.

    Input: weights on a 0-100 scale, e.g. [35, 25, 10, 30].
    Formula: sum(w_i ** 2).

    A fully diversified 10-position portfolio at 10% each returns 1000.
    A single-position portfolio at 100% returns 10000.

    Empty input raises ValueError. Negative weights raise ValueError.
    Weights need not sum to 100; callers own normalisation.
    """
    if not weights_pct:
        raise ValueError("weights_pct must not be empty")
    if any(weight < 0 for weight in weights_pct):
        raise ValueError("weights_pct must be non-negative")
    return sum((weight * weight for weight in weights_pct), Decimal("0"))
