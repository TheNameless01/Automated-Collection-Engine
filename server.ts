import { execSync, spawn, type ChildProcess } from 'child_process';
import express from 'express';
import fs from 'fs';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function getCliFlag(flag: string): string | undefined {
  const idx = process.argv.indexOf(flag);
  if (idx !== -1 && idx + 1 < process.argv.length) {
    return process.argv[idx + 1];
  }
  return undefined;
}

function parseValidPort(raw: string | undefined, fallback: number): number {
  const n = Number(raw?.trim());
  return Number.isInteger(n) && n > 0 && n <= 65535 ? n : fallback;
}

const PORT = parseValidPort(getCliFlag('--port') || process.env.APP_PORT, 3000);
// Never default to 8000 since hosted control planes often bind :8000
const PY_PORT = parseValidPort(process.env.DZ_PORT, 8765);
const PY_URL = `http://127.0.0.1:${PY_PORT}`;

let pythonProc: ChildProcess | null = null;
let backendStarting = false;
let backendLastError = '';

function resolvePythonBinary(): string {
  const venvUnix = path.join(__dirname, '.venv', 'bin', 'python');
  const venvWin = path.join(__dirname, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venvUnix)) return venvUnix;
  if (fs.existsSync(venvWin)) return venvWin;
  return process.platform === 'win32' ? 'python' : 'python3';
}

function hasRequiredPythonDeps(pyBin: string): boolean {
  try {
    execSync(`"${pyBin}" -c "import fastapi, uvicorn, multipart"`, {
      stdio: 'ignore',
      timeout: 15000,
    });
    return true;
  } catch {
    return false;
  }
}

async function bootstrapPythonVenv(): Promise<string> {
  const venvDir = path.join(__dirname, '.venv');
  const venvPy = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (fs.existsSync(venvPy) && hasRequiredPythonDeps(venvPy)) {
    return venvPy;
  }

  console.log('[python-bootstrap] Preparing local Python environment...');
  if (!fs.existsSync(venvPy)) {
    try {
      execSync(`python3 -m venv "${venvDir}"`, { cwd: __dirname, stdio: 'inherit' });
    } catch {
      execSync(`python3 -m venv --without-pip "${venvDir}"`, { cwd: __dirname, stdio: 'inherit' });
    }
  }

  try {
    execSync(`"${venvPy}" -m pip --version`, { stdio: 'ignore' });
  } catch {
    const getPipPath = path.join(venvDir, 'get-pip.py');
    execSync(`curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "${getPipPath}"`, { cwd: __dirname, stdio: 'inherit' });
    execSync(`"${venvPy}" "${getPipPath}"`, { cwd: __dirname, stdio: 'inherit' });
  }

  execSync(`"${venvPy}" -m pip install -r requirements.txt`, { cwd: __dirname, stdio: 'inherit' });
  return venvPy;
}

async function isPythonHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${PY_URL}/api/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

async function ensurePythonBackend(): Promise<void> {
  if (await isPythonHealthy()) {
    return;
  }
  backendStarting = true;
  backendLastError = '';
  let exitedEarly = false;
  let stderrTail = '';
  try {
    let pyBin = resolvePythonBinary();
    if (!hasRequiredPythonDeps(pyBin)) {
      pyBin = await bootstrapPythonVenv();
    }

    const backendDir = path.join(__dirname, 'backend');
    pythonProc = spawn(
      pyBin,
      ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(PY_PORT)],
      {
        cwd: backendDir,
        env: {
          ...process.env,
          PYTHONPATH: backendDir,
          DZ_ROOT_DIR: __dirname,
          DZ_HOST: '127.0.0.1',
          DZ_PORT: String(PY_PORT),
          DZ_LOG_LEVEL: 'INFO',
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );

    pythonProc.stdout?.on('data', (chunk) => {
      process.stdout.write(`[fastapi] ${chunk}`);
    });
    pythonProc.stderr?.on('data', (chunk) => {
      const text = chunk.toString();
      stderrTail = (stderrTail + text).slice(-1200);
      process.stderr.write(`[fastapi] ${text}`);
    });
    pythonProc.on('exit', (code) => {
      exitedEarly = true;
      if (code !== 0 && code !== null) {
        backendLastError = `FastAPI process exited with code ${code}: ${stderrTail.trim()}`;
      }
    });

    for (let i = 0; i < 120; i += 1) {
      if (exitedEarly) {
        return;
      }
      if (await isPythonHealthy()) {
        return;
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    backendLastError = `FastAPI backend did not respond within startup timeout. ${stderrTail.trim()}`.trim();
    console.warn(`Warning: ${backendLastError}`);
  } catch (err) {
    backendLastError = err instanceof Error ? err.message : String(err);
    console.error('Failed to start Python backend:', backendLastError);
  } finally {
    backendStarting = false;
  }
}

async function startServer(): Promise<void> {
  const app = express();

  // Proxy all /api requests directly to local Python FastAPI backend via Node http
  app.use('/api', (req, res) => {
    const targetPath = req.originalUrl || `/api${req.url}`;
    const proxyReq = http.request(
      {
        hostname: '127.0.0.1',
        port: PY_PORT,
        path: targetPath,
        method: req.method,
        headers: {
          ...req.headers,
          host: `127.0.0.1:${PY_PORT}`,
        },
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
        proxyRes.pipe(res, { end: true });
      },
    );

    proxyReq.on('error', (err) => {
      if (!res.headersSent) {
        res.status(503).json({
          detail: backendStarting
            ? 'Python backend is initializing; please retry in a few seconds.'
            : backendLastError || `Python FastAPI backend unavailable (${err.message}).`,
        });
      }
    });

    req.pipe(proxyReq, { end: true });
  });

  const isProd = process.env.NODE_ENV === 'production';
  if (isProd) {
    const distDir = path.join(__dirname, 'dist');
    app.use(express.static(distDir));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distDir, 'index.html'));
    });
  } else {
    const { createServer: createViteServer } = await import('vite');
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  }

  const server = app.listen(PORT, '0.0.0.0', () => {
    console.log(`DZ Car Rental Finder web server running at http://127.0.0.1:${PORT}`);
  });

  // Start or verify Python backend right away without blocking Express port binding
  void ensurePythonBackend();

  const shutdown = () => {
    server.close();
    if (pythonProc && !pythonProc.killed) {
      pythonProc.kill('SIGTERM');
    }
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

startServer().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
