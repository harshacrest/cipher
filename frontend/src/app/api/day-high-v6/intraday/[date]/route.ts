import { readVersionedDayHighFile } from "../../../_lib/read-versioned-day-high";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ date: string }> }
) {
  const { date } = await params;
  const data = readVersionedDayHighFile("v6", `days/${date}.json`);
  if (data === null) return Response.json({ error: "not found" }, { status: 404 });
  return Response.json(data);
}
