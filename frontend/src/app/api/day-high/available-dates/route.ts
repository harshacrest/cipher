import { readDayHighFile } from "../../_lib/read-day-high-json";

export async function GET() {
  const data = readDayHighFile("available_dates.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
