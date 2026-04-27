import { readAllrounderFile } from "../_lib/read-json";

export async function GET() {
  const data = readAllrounderFile("dow.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
