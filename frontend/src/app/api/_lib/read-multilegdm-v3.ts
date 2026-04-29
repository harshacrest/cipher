import { readFileSync, existsSync } from "fs";
import path from "path";

const DATA_DIR = process.env.MULTILEGDM_V3_DATA_DIR;

export function readMultilegdmV3File(filename: string): unknown {
  if (!DATA_DIR) return null;
  const filePath = path.join(DATA_DIR, filename);
  if (!existsSync(filePath)) return null;
  const raw = readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}
