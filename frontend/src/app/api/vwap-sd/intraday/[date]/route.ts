import { readVwapSdFile } from "../../../_lib/read-vwap-sd";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ date: string }> },
) {
  const { date } = await ctx.params;
  // Basic validation to keep the path inside the intraday folder
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return Response.json({ error: "invalid date" }, { status: 400 });
  }
  const data = readVwapSdFile(`intraday/${date}.json`);
  if (data === null) {
    return Response.json({ error: "not found" }, { status: 404 });
  }
  return Response.json(data);
}
