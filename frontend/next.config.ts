import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/atm_straddle_sell/api",
    DAY_HIGH_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell/api",
    DAY_HIGH_V4_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell_v4/api",
    DAY_HIGH_V5_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell_v5/api",
    DAY_HIGH_V6_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell_v6/api",
    DAY_HIGH_V7_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell_v7/api",
    VANILLA_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/vanilla_straddle/api",
    ALLROUNDER_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/index_allrounder/api",
    MULTILEGDM_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/multi_leg_dm/api",
    MULTILEGDM_V2_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/multi_leg_dm_v2/api",
    MULTILEGDM_V3_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/multi_leg_dm_v3/api",
    MULTILEGDM_V4_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/multi_leg_dm_v4/api",
    VWAP_SD_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/vwap_sd_straddles/api",
  },
};

export default nextConfig;
