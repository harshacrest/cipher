"""DhanHQ API constants."""

DHAN_WS_URL = "wss://api-feed.dhan.co"
DHAN_API_BASE = "https://api.dhan.co/v2"
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

# NIFTY spot index — always security ID 13 in Dhan
NIFTY_SPOT_SECURITY_ID = 13


class ExchangeSegment:
    """Dhan exchange segment codes for WebSocket and API."""
    IDX_I = 0       # Index
    NSE_EQ = 1      # NSE Equity
    NSE_FNO = 2     # NSE F&O
    BSE_EQ = 3      # BSE Equity
    BSE_FNO = 7     # BSE F&O


# Dhan WebSocket subscription request types
class FeedRequestCode:
    SUBSCRIBE = 15
    UNSUBSCRIBE = 16


# Dhan WebSocket response feed types
class FeedResponseCode:
    TICKER = 2
    QUOTE = 4
    FULL = 5
    OI = 7
