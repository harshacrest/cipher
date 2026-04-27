import { readAllrounderFile } from "../_lib/read-json";

export async function GET() {
  const data = readAllrounderFile("equity.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
