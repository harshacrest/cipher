import { readFileSync, existsSync } from "fs";
import path from "path";

const DATA_DIR = process.env.MULTILEGDM_V4_DATA_DIR;

export function readMultilegdmV4File(filename: string): unknown {
  if (!DATA_DIR) return null;
  const filePath = path.join(DATA_DIR, filename);
  if (!existsSync(filePath)) return null;
  const raw = readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}
