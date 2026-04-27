import { existsSync, readFileSync } from "fs";
import path from "path";
import { NextRequest } from "next/server";

const DATA_DIR = process.env.VANILLA_DATA_DIR!;

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ date: string }> }
) {
  const { date } = await params;
  const filePath = path.join(DATA_DIR, "days", `${date}.json`);

  if (!existsSync(filePath)) {
    return Response.json({ error: "Not found" }, { status: 404 });
  }

  const raw = readFileSync(filePath, "utf-8");
  return Response.json(JSON.parse(raw));
}
