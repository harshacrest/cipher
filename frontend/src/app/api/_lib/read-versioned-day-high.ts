import { readFileSync, existsSync } from "fs";
import path from "path";

const VERSION_DIRS: Record<string, string | undefined> = {
  v3: process.env.DAY_HIGH_DATA_DIR,
  v4: process.env.DAY_HIGH_V4_DATA_DIR,
  v5: process.env.DAY_HIGH_V5_DATA_DIR,
  v6: process.env.DAY_HIGH_V6_DATA_DIR,
};

export function readVersionedDayHighFile(version: string, filename: string): unknown {
  const dir = VERSION_DIRS[version];
  if (!dir) return null;
  const filePath = path.join(dir, filename);
  if (!existsSync(filePath)) return null;
  const raw = readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}
