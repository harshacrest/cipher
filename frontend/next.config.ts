import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/atm_straddle_sell/api",
    DAY_HIGH_DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/day_high_otm_sell/api",
  },
};

export default nextConfig;
