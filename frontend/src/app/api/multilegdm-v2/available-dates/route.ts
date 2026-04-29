import { readMultilegdmV2File } from "../../_lib/read-multilegdm-v2";

export async function GET() {
  const data = readMultilegdmV2File("available-dates.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
