"""Run ATM straddle sell strategy on MCX Crude Oil options via DhanHQ.

Same strategy class as NIFTY — only config differs.
MCX crude oil trades 9:00 AM - 11:30 PM IST.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from nautilus_trader.config import (
    InstrumentProviderConfig,
    LoggingConfig,
)
from nautilus_trader.live.config import LiveExecEngineConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode

from adapters.dhan.config import DhanDataClientConfig, DhanExecClientConfig
from adapters.dhan.constants import CRUDEOIL_FUT_SECURITY_ID
from adapters.dhan.factories import DhanLiveDataClientFactory, DhanLiveExecClientFactory
from strategies.atm_straddle_sell import ATMStraddleSell, ATMStraddleSellConfig


def load_config() -> dict:
    """Load config from env vars or config file."""
    config_path = Path(__file__).parent.parent / "config" / "dhan_live.toml"
    cfg = {}
    if config_path.exists():
        import tomllib
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)

    dhan_cfg = cfg.get("dhan", {})
    token = os.environ.get("DHAN_ACCESS_TOKEN", "") or dhan_cfg.get("access_token", "")
    client_id = os.environ.get("DHAN_CLIENT_ID", "") or dhan_cfg.get("client_id", "")

    if not token or not client_id:
        print("ERROR: Set DHAN_ACCESS_TOKEN and DHAN_CLIENT_ID env vars or config/dhan_live.toml")
        sys.exit(1)

    strategy_cfg = cfg.get("strategy", {})
    return {
        "token": token,
        "client_id": client_id,
        "entry_time": strategy_cfg.get("entry_time", "16:00:00"),
        "exit_time": strategy_cfg.get("exit_time", "23:00:00"),
        "num_lots": strategy_cfg.get("num_lots", 1),
    }


def main():
    cfg = load_config()
    token, client_id = cfg["token"], cfg["client_id"]

    instrument_filters = {
        "underlying": "CRUDEOIL",
        "exchange": "MCX",
        "max_expiries": 2,
        "spot_security_id": CRUDEOIL_FUT_SECURITY_ID,
        "lot_size": 100,
        "multiplier": 100,
        "price_increment": "1.00",
    }

    node_config = TradingNodeConfig(
        trader_id="CIPHER-CRUDE-001",
        logging=LoggingConfig(log_level="INFO"),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
        ),
        data_clients={
            "DHAN": DhanDataClientConfig(
                access_token=token,
                client_id=client_id,
                instrument_filters=instrument_filters,
                instrument_provider=InstrumentProviderConfig(load_all=True),
                exchange="MCX",
                spot_ws_segment="MCX_COMM",
                options_ws_segment="MCX_COMM",
                order_exchange_segment="MCX_COMM",
            ),
        },
        exec_clients={
            "DHAN": DhanExecClientConfig(
                access_token=token,
                client_id=client_id,
                product_type="INTRADAY",
                instrument_provider=InstrumentProviderConfig(load_all=True),
                order_exchange_segment="MCX_COMM",
            ),
        },
    )

    node = TradingNode(config=node_config)
    node.add_data_client_factory("DHAN", DhanLiveDataClientFactory)
    node.add_exec_client_factory("DHAN", DhanLiveExecClientFactory)
    node.build()

    # Same strategy class — only config changes
    strategy_config = ATMStraddleSellConfig(
        entry_time=cfg["entry_time"],
        exit_time=cfg["exit_time"],
        strike_step=50,
        lot_size=1,         # MCX crude oil: 1 lot = 1 contract = 100 barrels
        num_lots=cfg["num_lots"],
        underlying="CRUDEOIL",
        venue="MCX",
        spot_instrument_id="CRUDEOIL-SPOT.MCX",
    )
    node.trader.add_strategy(ATMStraddleSell(config=strategy_config))

    print("Starting live trading node (Crude Oil)...")
    print(f"  Strategy: ATM Straddle Sell")
    print(f"  Underlying: CRUDEOIL on MCX")
    print(f"  Entry: {strategy_config.entry_time} IST")
    print(f"  Exit: {strategy_config.exit_time} IST")
    print(f"  Lots: {strategy_config.num_lots}")
    print(f"  Lot size: {strategy_config.lot_size} barrels")
    print(f"  Broker: DhanHQ (client_id={client_id[:4]}...)")
    print()

    # Start dashboard WebSocket server
    from adapters.dhan.dashboard import start_dashboard_server
    start_dashboard_server(port=1157)  # Different port from NIFTY

    node.run()


if __name__ == "__main__":
    main()
