import { readMultilegdmV3File } from "../../_lib/read-multilegdm-v3";

export async function GET() {
  const data = readMultilegdmV3File("monthly.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
