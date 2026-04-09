import { execSync } from "child_process";
import path from "path";

const PROJECT_ROOT = process.cwd().replace(/\/frontend$/, "");
const MANAGER = path.join(PROJECT_ROOT, "scripts", "live_manager.py");
const PYTHON = "uv";

function runManager(args: string): string {
  return execSync(`${PYTHON} run python ${MANAGER} ${args}`, {
    cwd: PROJECT_ROOT,
    encoding: "utf-8",
    timeout: 15000,
  });
}

export async function GET() {
  try {
    const out = runManager("status");
    return Response.json(JSON.parse(out));
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const { action } = await request.json();
    if (action !== "start" && action !== "stop") {
      return Response.json({ error: "Invalid action" }, { status: 400 });
    }
    const out = runManager(action);
    return Response.json(JSON.parse(out));
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
