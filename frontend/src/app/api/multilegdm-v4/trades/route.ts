import { readMultilegdmV4File } from "../../_lib/read-multilegdm-v4";

export async function GET() {
  const data = readMultilegdmV4File("trades.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
