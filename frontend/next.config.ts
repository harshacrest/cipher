import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    DATA_DIR: process.cwd().replace(/\/frontend$/, "") + "/output/atm_straddle_sell/api",
  },
};

export default nextConfig;
