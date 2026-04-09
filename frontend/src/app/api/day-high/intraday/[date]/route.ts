import { readFileSync, existsSync } from "fs";
import path from "path";
import type { NextRequest } from "next/server";

const DATA_DIR = process.env.DAY_HIGH_DATA_DIR!;

type RouteParams = { params: Promise<{ date: string }> };

export async function GET(_req: NextRequest, ctx: RouteParams) {
  const { date } = await ctx.params;
  const filePath = path.join(DATA_DIR, "days", `${date}.json`);

  if (!existsSync(filePath)) {
    return Response.json({ error: "Date not found" }, { status: 404 });
  }

  const raw = readFileSync(filePath, "utf-8");
  return new Response(raw, {
    headers: { "Content-Type": "application/json" },
  });
}
