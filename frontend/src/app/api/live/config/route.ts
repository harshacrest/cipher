import { execSync } from "child_process";
import path from "path";

const PROJECT_ROOT = process.cwd().replace(/\/frontend$/, "");
const MANAGER = path.join(PROJECT_ROOT, "scripts", "live_manager.py");
const PYTHON = "uv";

function runManager(args: string): string {
  return execSync(`${PYTHON} run python ${MANAGER} ${args}`, {
    cwd: PROJECT_ROOT,
    encoding: "utf-8",
    timeout: 10000,
  });
}

export async function GET() {
  try {
    const out = runManager("config");
    return Response.json(JSON.parse(out));
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { execSync: exec } = await import("child_process");

    // Write config via Python
    const configJson = JSON.stringify(body);
    exec(
      `${PYTHON} run python -c "import sys, json; sys.path.insert(0, '.'); from scripts.live_manager import save_config; save_config(json.loads(sys.stdin.read()))"`,
      {
        cwd: PROJECT_ROOT,
        input: configJson,
        encoding: "utf-8",
        timeout: 10000,
      }
    );

    return Response.json({ status: "saved" });
  } catch (e: any) {
    return Response.json({ error: e.message }, { status: 500 });
  }
}
