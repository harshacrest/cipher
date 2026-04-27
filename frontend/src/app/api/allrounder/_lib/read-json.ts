import { readFileSync, existsSync } from "fs";
import path from "path";

const DATA_DIR = process.env.ALLROUNDER_DATA_DIR!;

export function readAllrounderFile(filename: string): unknown {
  const filePath = path.join(DATA_DIR, filename);
  if (!existsSync(filePath)) return null;
  const raw = readFileSync(filePath, "utf-8");
  return JSON.parse(raw);
}
