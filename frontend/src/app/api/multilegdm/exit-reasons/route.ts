import { readMultilegdmFile } from "../../_lib/read-multilegdm";

export async function GET() {
  const data = readMultilegdmFile("exit_reasons.json");
  if (data === null) return Response.json([], { status: 404 });
  return Response.json(data);
}
