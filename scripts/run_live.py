"""Launch live trading with DhanHQ broker.

Usage:
    uv run python scripts/run_live.py

Requires:
    - DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID environment variables (or config/dhan_live.toml)
    - Static IP whitelisted with DhanHQ for order placement
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.config import (
    InstrumentProviderConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.config import LiveExecEngineConfig, RoutingConfig
from nautilus_trader.live.node import TradingNode

from adapters.dhan.config import DhanDataClientConfig, DhanExecClientConfig
from adapters.dhan.factories import DhanLiveDataClientFactory, DhanLiveExecClientFactory
from strategies.atm_straddle_sell import ATMStraddleSell, ATMStraddleSellConfig


def load_config() -> tuple[str, str]:
    """Load Dhan credentials from env vars or config file."""
    token = os.environ.get("DHAN_ACCESS_TOKEN", "")
    client_id = os.environ.get("DHAN_CLIENT_ID", "")

    if not token or not client_id:
        config_path = Path(__file__).parent.parent / "config" / "dhan_live.toml"
        if config_path.exists():
            import tomllib
            with open(config_path, "rb") as f:
                cfg = tomllib.load(f)
            dhan_cfg = cfg.get("dhan", {})
            token = token or dhan_cfg.get("access_token", "")
            client_id = client_id or dhan_cfg.get("client_id", "")

    if not token or not client_id:
        print("ERROR: Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID env vars or config/dhan_live.toml")
        sys.exit(1)

    return token, client_id


def main():
    token, client_id = load_config()

    instrument_filters = {"underlying": "NIFTY", "max_expiries": 2}

    node_config = TradingNodeConfig(
        trader_id="CIPHER-001",
        logging=LoggingConfig(log_level="INFO"),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=60,
        ),
        data_clients={
            "DHAN": DhanDataClientConfig(
                access_token=token,
                client_id=client_id,
                instrument_filters=instrument_filters,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            "DHAN": DhanExecClientConfig(
                access_token=token,
                client_id=client_id,
                product_type="INTRA",
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
    )

    node = TradingNode(config=node_config)
    node.add_data_client_factory("DHAN", DhanLiveDataClientFactory)
    node.add_exec_client_factory("DHAN", DhanLiveExecClientFactory)
    node.build()

    # Add the SAME strategy class used in backtest — zero changes
    strategy_config = ATMStraddleSellConfig(
        entry_time="09:21:00",
        exit_time="15:00:00",
        num_lots=1,
    )
    node.trader.add_strategy(ATMStraddleSell(config=strategy_config))

    print("Starting live trading node...")
    print(f"  Strategy: ATM Straddle Sell")
    print(f"  Entry: {strategy_config.entry_time} IST")
    print(f"  Exit: {strategy_config.exit_time} IST")
    print(f"  Lots: {strategy_config.num_lots}")
    print(f"  Broker: DhanHQ (client_id={client_id[:4]}...)")
    print()

    node.run()


if __name__ == "__main__":
    main()
