import { readVersionedDayHighFile } from "../../_lib/read-versioned-day-high";

export async function GET() {
  const data = readVersionedDayHighFile("v6", "equity.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
