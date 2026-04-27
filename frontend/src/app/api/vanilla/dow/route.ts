import { readVanillaFile } from "../_lib/read-json";

export async function GET() {
  const data = readVanillaFile("dow.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
