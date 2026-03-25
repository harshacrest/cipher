"""Data loading helpers for market data."""

from pathlib import Path

import pandas as pd

DATA_ROOT = Path("/Users/harsha/Desktop/Research/DATA/NSE/NIFTY")


def list_trading_days() -> list[str]:
    """Return sorted list of available trading day strings."""
    return sorted(d.name for d in DATA_ROOT.iterdir() if d.is_dir() and not d.name.startswith("."))


def load_spot(date_str: str) -> pd.DataFrame:
    """Load spot price for a given day."""
    path = DATA_ROOT / date_str / "Index" / "Cleaned_Spot.parquet"
    return pd.read_parquet(path, columns=["datetime", "ltp"]).rename(columns={"ltp": "spot"})


def get_nearest_expiry_file(date_str: str) -> Path | None:
    """Get the nearest expiry Cleaned options file for a given trading day."""
    opts_dir = DATA_ROOT / date_str / "Options"
    if not opts_dir.exists():
        return None
    cleaned = sorted(f for f in opts_dir.iterdir() if f.name.startswith("Cleaned_") and not f.name.startswith("Cleaned_Series"))
    return cleaned[0] if cleaned else None


def load_options_at_strike(date_str: str, strike: int) -> pd.DataFrame | None:
    """Load CE and PE LTP for a specific strike on a given day (nearest expiry)."""
    path = get_nearest_expiry_file(date_str)
    if path is None:
        return None

    df = pd.read_parquet(path, columns=["datetime", "option_type", "strike_price", "ltp"])
    df = df[df["strike_price"] == strike].copy()

    if df.empty:
        return None

    # Decode option_type if stored as bytes
    if df["option_type"].dtype == object:
        df["option_type"] = df["option_type"].apply(lambda x: x.decode() if isinstance(x, bytes) else x)

    # Pivot to get CE and PE as separate columns
    ce = df[df["option_type"] == "CE"][["datetime", "ltp"]].rename(columns={"ltp": "ce_ltp"})
    pe = df[df["option_type"] == "PE"][["datetime", "ltp"]].rename(columns={"ltp": "pe_ltp"})

    merged = ce.merge(pe, on="datetime", how="outer").sort_values("datetime").reset_index(drop=True)
    merged["straddle_price"] = merged["ce_ltp"] + merged["pe_ltp"]

    return merged
