import { readVwapSdFile } from "../../_lib/read-vwap-sd";

export async function GET() {
  const data = readVwapSdFile("metrics.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
