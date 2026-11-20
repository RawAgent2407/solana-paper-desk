"""READ-ONLY public market data (DexScreener + RugCheck). HTTP GET only; no keys, no wallet.
This is the ONLY module allowed to touch the network."""
import json
import time
import urllib.request
from typing import Optional
from .models import Snapshot

DEX = "https://api.dexscreener.com"
RUG = "https://api.rugcheck.xyz/v1/tokens"
_last = {}


FEED_OF = {}   # token address -> which feed discovered it (recorded for later analysis)
GECKO = "https://api.geckoterminal.com/api/v2/networks/solana"
MAJORS = {"So11111111111111111111111111111111111111112",    # wrapped SOL
          "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",    # USDC
          "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"}    # USDT


def parse_gecko(payload):
    """Base-token mints from a GeckoTerminal pools response, excluding SOL/stablecoins."""
    out = []
    for r in (payload or {}).get("data", []):
        try:
            tid = r["relationships"]["base_token"]["data"]["id"]
        except (KeyError, TypeError):
            continue
        mint = tid.split("_", 1)[-1]
        if mint and mint not in MAJORS and mint not in out:
            out.append(mint)
    return out


def _get(url, min_gap=1.0, headers=None):
    host = url.split("/")[2]
    wait = min_gap - (time.time() - _last.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "paper-desk/1.0", "Accept": "application/json",
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except Exception:
        return None


def fetch_candidates():
    """New profiles + boosted tokens (boosts are PAID promotion: treat as hype, not evidence)."""
    out = []
    # 1) trending pools (already ranked by activity => far more likely to pass volume/liquidity filters)
    hdr = {"Accept": "application/json;version=20230302"}
    for page in (1, 2):
        for a in parse_gecko(_get(f"{GECKO}/trending_pools?page={page}", 2.2, hdr)):
            if a not in out:
                out.append(a)
                FEED_OF[a] = "gecko_trending"
    # 2) new profiles + boosted tokens
    for path in ("token-profiles/latest/v1", "token-boosts/top/v1", "token-boosts/latest/v1"):
        for x in _get(f"{DEX}/{path}", 1.1) or []:
            if x.get("chainId") == "solana" and x["tokenAddress"] not in out:
                out.append(x["tokenAddress"])
                FEED_OF[x["tokenAddress"]] = "dex_new_or_boosted"
    return out


def fetch_pairs(addrs):
    """Best pair (highest liquidity, else volume) per token address. Batches of 30."""
    best = {}
    for i in range(0, len(addrs), 30):
        d = _get(f"{DEX}/tokens/v1/solana/{','.join(addrs[i:i + 30])}", 0.3) or []
        for p in d:
            a = (p.get("baseToken") or {}).get("address")
            key = ((p.get("liquidity") or {}).get("usd") or 0, (p.get("volume") or {}).get("h24") or 0)
            if a and (a not in best or key > best[a][0]):
                best[a] = (key, p)
    return {a: v[1] for a, v in best.items()}


def fetch_rug(addr):
    return _get(f"{RUG}/{addr}/report", 1.0)


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def build_snapshot(addr, pair, rug, now) -> Snapshot:
    """Anything not verifiable becomes None (-> rejected by the filter, never assumed safe)."""
    rug = rug or {}
    tx = (pair.get("txns") or {}).get("h1") or {}
    buys, sells = tx.get("buys"), tx.get("sells")
    liq = (pair.get("liquidity") or {}).get("usd")
    mk = rug.get("markets") or []
    if liq is None and mk:  # bonding-curve pairs often lack DexScreener liquidity
        lp = [(m.get("lp") or {}) for m in mk]
        liq = max(((l.get("quoteUSD") or 0) + (l.get("baseUSD") or 0) for l in lp), default=None)
    pools = set()
    for m in mk:
        pools.add(m.get("pubkey"))
        for k in ("liquidityAAccount", "liquidityBAccount"):
            pools.add((m.get(k) or {}).get("owner"))
    holders = rug.get("topHolders") or []
    top10 = None
    if holders:
        non_pool = [h for h in holders if h.get("owner") not in pools and h.get("address") not in pools]
        top10 = sum(h.get("pct", 0) for h in non_pool[:10])
    locks = [(m.get("lp") or {}).get("lpLockedPct") for m in mk]
    locks = [x for x in locks if x is not None]
    # No sell simulation is available: sellable is only a PROXY from RugCheck flags.
    if rug.get("rugged") is True:
        sellable = False
    elif "rugged" in rug and (rug.get("transferFee") or {}).get("pct", 0) == 0:
        sellable = True
    else:
        sellable = None
    created = pair.get("pairCreatedAt")
    mom = (pair.get("priceChange") or {}).get("h1")
    return Snapshot(
        pool_id=addr, symbol=(pair.get("baseToken") or {}).get("symbol", "?"),
        observed_at=now, received_at=now, price=_f(pair.get("priceUsd")), liquidity_usd=_f(liq),
        volume_h1=_f((pair.get("volume") or {}).get("h1")), top10_pct=top10,
        mint_revoked=(rug.get("mintAuthority") is None) if "mintAuthority" in rug else None,
        freeze_revoked=(rug.get("freezeAuthority") is None) if "freezeAuthority" in rug else None,
        lp_locked_pct=max(locks) if locks else None, sellable=sellable,
        buy_sell_ratio=(buys / max(sells, 1)) if buys is not None and sells is not None else None,
        unique_buyers=buys,  # PROXY: buy count in last hour (unique buyers not available)
        momentum_1h=(mom / 100.0) if mom is not None else None,
        age_min=((now * 1000 - created) / 60000.0) if created else None)
