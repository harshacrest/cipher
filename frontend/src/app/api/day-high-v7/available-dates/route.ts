import { readVersionedDayHighFile } from "../../_lib/read-versioned-day-high";

export async function GET() {
  const data = readVersionedDayHighFile("v7", "available-dates.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
