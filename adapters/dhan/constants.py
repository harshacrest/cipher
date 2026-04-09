"""DhanHQ API constants."""

DHAN_WS_URL = "wss://api-feed.dhan.co"
DHAN_API_BASE = "https://api.dhan.co/v2"
DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"

# NIFTY spot index — always security ID 13 in Dhan
NIFTY_SPOT_SECURITY_ID = 13


class ExchangeSegment:
    """Dhan exchange segment strings for WebSocket API."""
    IDX_I = "IDX_I"       # Index
    NSE_EQ = "NSE_EQ"     # NSE Equity
    NSE_FNO = "NSE_FNO"   # NSE F&O
    BSE_EQ = "BSE_EQ"     # BSE Equity
    BSE_FNO = "BSE_FNO"   # BSE F&O
    MCX_COMM = "MCX_COMM"  # MCX Commodity

# Crude oil futures nearest month — used as "spot" reference
CRUDEOIL_FUT_SECURITY_ID = 486502


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
