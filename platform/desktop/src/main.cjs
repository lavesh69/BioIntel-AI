'use strict';

const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const net = require('net');
const path = require('path');
const http = require('http');
const https = require('https');

const APP_VERSION = require('../package.json').version;
let backend = null;
let mainWindow = null;
let splashWindow = null;
let workspacePath = null;
let pendingLaunchRequest = null;


function logDesktopEvent(kind, payload) {
  try {
    const directory = app.isReady() ? app.getPath('logs') : path.join(process.cwd(), 'logs');
    fs.mkdirSync(directory, { recursive: true });
    const row = JSON.stringify({
      timestamp_utc: new Date().toISOString(),
      kind,
      payload: payload instanceof Error ? { name: payload.name, message: payload.message, stack: payload.stack } : payload,
      version: APP_VERSION,
      platform: process.platform,
    });
    fs.appendFileSync(path.join(directory, 'desktop-events.jsonl'), `${row}\n`, 'utf8');
  } catch { /* logging must never crash startup */ }
}

function parseLaunchRequest(argv) {
  const values = Array.isArray(argv) ? argv : [];
  const deepLink = values.find(value => typeof value === 'string' && value.startsWith('biointel://'));
  if (deepLink) {
    try {
      const parsed = new URL(deepLink);
      return { kind: 'deep_link', url: parsed.toString(), route: parsed.hostname, parameters: Object.fromEntries(parsed.searchParams.entries()) };
    } catch (error) {
      logDesktopEvent('invalid-deep-link', error);
    }
  }
  const supported = new Set(['.fasta', '.fa', '.fna', '.faa', '.fastq', '.fq', '.vcf', '.csv', '.tsv', '.pdb', '.cif', '.mmcif']);
  const candidate = values.find(value => {
    if (typeof value !== 'string' || value.startsWith('-')) return false;
    try { return fs.existsSync(value) && supported.has(path.extname(value).toLowerCase()); } catch { return false; }
  });
  return candidate ? { kind: 'file', path: path.resolve(candidate), extension: path.extname(candidate).toLowerCase() } : null;
}

function persistLaunchRequest(request) {
  if (!request || !workspacePath) return;
  try {
    const target = path.join(workspacePath, 'reports', 'desktop_launch_request.json');
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, JSON.stringify({ ...request, received_at_utc: new Date().toISOString() }, null, 2), 'utf8');
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('biointel-launch-request', request);
  } catch (error) { logDesktopEvent('launch-request-write-failed', error); }
}

function focusMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function registerDeepLinkProtocol() {
  try {
    if (process.defaultApp && process.argv.length >= 2) {
      app.setAsDefaultProtocolClient('biointel', process.execPath, [path.resolve(process.argv[1])]);
    } else {
      app.setAsDefaultProtocolClient('biointel');
    }
  } catch (error) { logDesktopEvent('protocol-registration-failed', error); }
}

function checkSecureUpdateNotice() {
  const manifestUrl = String(process.env.BIOINTEL_UPDATE_MANIFEST_URL || '').trim();
  if (!manifestUrl) return;
  let parsed;
  try { parsed = new URL(manifestUrl); } catch (error) { logDesktopEvent('update-url-invalid', error); return; }
  if (parsed.protocol !== 'https:') {
    logDesktopEvent('update-url-rejected', { reason: 'HTTPS required', url: manifestUrl });
    return;
  }
  const request = https.get(parsed, { timeout: 8000, headers: { Accept: 'application/json', 'User-Agent': `BioIntel-AI/${APP_VERSION}` } }, response => {
    if (response.statusCode !== 200) { response.resume(); logDesktopEvent('update-check-http', { status: response.statusCode }); return; }
    let body = '';
    response.setEncoding('utf8');
    response.on('data', chunk => { if (body.length < 256000) body += chunk; });
    response.on('end', () => {
      try {
        const payload = JSON.parse(body);
        if (payload && payload.version && payload.version !== APP_VERSION && mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('biointel-update-notice', {
            version: String(payload.version),
            notes: String(payload.notes || ''),
            url: typeof payload.url === 'string' && payload.url.startsWith('https://') ? payload.url : '',
          });
        }
      } catch (error) { logDesktopEvent('update-manifest-invalid', error); }
    });
  });
  request.on('timeout', () => request.destroy(new Error('Update check timed out')));
  request.on('error', error => logDesktopEvent('update-check-failed', error));
}

function isSafeNavigation(url, port) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(parsed.hostname) && Number(parsed.port) === port;
  } catch { return false; }
}

function copyTree(source, target, options = {}) {
  const { preserveExisting = false, insideReports = false } = options;
  if (!fs.existsSync(source)) return;
  fs.mkdirSync(target, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (['node_modules', '.git', '__pycache__', '.pytest_cache', 'test-results'].includes(entry.name)) continue;
    const src = path.join(source, entry.name);
    const dst = path.join(target, entry.name);
    const nextInsideReports = insideReports || entry.name === 'reports';
    if (entry.isDirectory()) {
      copyTree(src, dst, { preserveExisting, insideReports: nextInsideReports });
    } else if (!(preserveExisting && nextInsideReports && fs.existsSync(dst))) {
      fs.mkdirSync(path.dirname(dst), { recursive: true });
      fs.copyFileSync(src, dst);
    }
  }
}

function splashDocument() {
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
  <style>
  :root{color-scheme:dark;font-family:Inter,"Segoe UI",system-ui,sans-serif;background:#06111f;color:#f8fafc}
  *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;overflow:hidden;background:radial-gradient(circle at 18% 0,#163e61 0,#091526 43%,#050a12 100%)}
  main{width:100%;height:100%;padding:34px 38px;display:flex;flex-direction:column;justify-content:space-between;border:1px solid rgba(112,215,255,.18);background:linear-gradient(145deg,rgba(10,25,44,.95),rgba(5,12,23,.98))}
  .brand{display:flex;gap:16px;align-items:center}.mark{width:58px;height:58px;border-radius:17px;display:grid;place-items:center;font-weight:900;font-size:24px;color:#06111f;background:linear-gradient(135deg,#72e7ff,#a98aff);box-shadow:0 16px 42px rgba(54,205,255,.22)}
  .eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#70d7ff;font-weight:800}.title{font-size:27px;font-weight:850;letter-spacing:-.04em;margin-top:3px}.copy{color:#9fb3c8;line-height:1.55;font-size:13px;max-width:420px}
  .stage{display:flex;justify-content:space-between;gap:16px;align-items:center;font-size:13px;color:#dce8f5}.stage span:last-child{color:#87a0b8;font-variant-numeric:tabular-nums}
  .track{height:7px;border:1px solid rgba(124,195,255,.18);border-radius:999px;background:#071321;overflow:hidden;margin-top:12px}.fill{height:100%;width:8%;border-radius:inherit;background:linear-gradient(90deg,#72e7ff,#a98aff);transition:width 240ms cubic-bezier(.2,.8,.2,1)}
  .foot{display:flex;justify-content:space-between;color:#71869d;font-size:11px}.pulse{width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 18px rgba(52,211,153,.65);animation:pulse 2.2s ease-in-out infinite}@keyframes pulse{50%{opacity:.5;transform:scale(.86)}}
  @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}.pulse{transform:none!important}}
  </style></head><body><main role="status" aria-live="polite" aria-busy="true">
  <section><div class="brand"><div class="mark">B</div><div><div class="eyebrow">Local scientific workspace</div><div class="title">BioIntel AI</div></div></div><p class="copy">Preparing the local engine, protected workspace and scientific visualisation runtime.</p></section>
  <section><div class="stage"><span id="stage">Starting application…</span><span id="percent">8%</span></div><div class="track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="8"><div id="fill" class="fill"></div></div></section>
  <footer class="foot"><span>Version ${APP_VERSION}</span><span style="display:flex;gap:8px;align-items:center"><i class="pulse"></i>Local-first startup</span></footer>
  </main></body></html>`;
}

async function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 540,
    height: 360,
    minWidth: 540,
    minHeight: 360,
    maxWidth: 540,
    maxHeight: 360,
    frame: false,
    resizable: false,
    movable: true,
    show: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: '#06111f',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      devTools: false,
    },
  });
  await splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splashDocument())}`);
  splashWindow.once('ready-to-show', () => splashWindow && !splashWindow.isDestroyed() && splashWindow.show());
}

function updateSplash(stage, percent) {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  const safeStage = JSON.stringify(String(stage));
  const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
  void splashWindow.webContents.executeJavaScript(`
    document.getElementById('stage').textContent=${safeStage};
    document.getElementById('percent').textContent='${safePercent}%';
    document.getElementById('fill').style.width='${safePercent}%';
    document.querySelector('[role="progressbar"]').setAttribute('aria-valuenow','${safePercent}');
  `, true).catch(() => undefined);
}

function closeSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) splashWindow.close();
  splashWindow = null;
}

function ensureWorkspace() {
  const bundled = path.join(process.resourcesPath, 'workspace');
  const target = path.join(app.getPath('userData'), 'workspace');
  const marker = path.join(target, '.desktop_release_version');
  let current = '';
  try { current = fs.readFileSync(marker, 'utf8').trim(); } catch { /* first launch */ }
  if (current !== APP_VERSION) {
    copyTree(bundled, target, { preserveExisting: true });
    fs.writeFileSync(marker, APP_VERSION, 'utf8');
  }
  return target;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function waitForHealth(port, timeoutMs = 90000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const poll = () => {
      const req = http.get({ hostname: '127.0.0.1', port, path: '/_stcore/health', timeout: 2500 }, res => {
        res.resume();
        if (res.statusCode === 200) resolve();
        else retry();
      });
      const retry = () => {
        req.destroy();
        if (Date.now() - started > timeoutMs) reject(new Error('BioIntel backend did not become ready.'));
        else setTimeout(poll, 600);
      };
      req.on('error', retry);
      req.on('timeout', retry);
    };
    poll();
  });
}

function backendExecutable() {
  const name = process.platform === 'win32' ? 'biointel-desktop-server.exe' : 'biointel-desktop-server';
  return path.join(process.resourcesPath, 'backend', name);
}

async function startBackend(workspace, port) {
  const executable = backendExecutable();
  if (!fs.existsSync(executable)) throw new Error(`Packaged backend is missing: ${executable}`);
  const localSessionToken = require('crypto').randomBytes(32).toString('hex');
  const env = {
    ...process.env,
    BIOINTEL_ENVIRONMENT: 'desktop',
    BIOINTEL_UI_AUTH_REQUIRED: '0',
    BIOINTEL_LOCAL_SESSION_TOKEN: localSessionToken,
    BIOINTEL_USER_DATA_DIR: path.join(app.getPath('userData'), 'UserData'),
    BIOINTEL_DESKTOP: '1',
    STREAMLIT_BROWSER_GATHER_USAGE_STATS: 'false',
  };
  backend = spawn(executable, ['--workspace', workspace, '--port', String(port)], {
    cwd: workspace,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const logDir = path.join(app.getPath('logs'));
  fs.mkdirSync(logDir, { recursive: true });
  const log = fs.createWriteStream(path.join(logDir, 'backend.log'), { flags: 'a' });
  backend.stdout.pipe(log);
  backend.stderr.pipe(log);
  backend.on('exit', code => {
    logDesktopEvent('backend-exit', { code });
    if (code && mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('backend-exit', code);
  });
  await waitForHealth(port);
}

async function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    backgroundColor: '#06111f',
    title: 'BioIntel AI',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      devTools: !app.isPackaged,
    },
  });
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    logDesktopEvent('render-process-gone', details);
    dialog.showErrorBox('BioIntel AI renderer stopped', 'The interface process stopped safely. Restart BioIntel AI; your local workspace remains preserved.');
  });
  mainWindow.webContents.on('unresponsive', () => logDesktopEvent('renderer-unresponsive', {}));
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!isSafeNavigation(url, port)) { event.preventDefault(); if (url.startsWith('https://')) void shell.openExternal(url); }
  });
  mainWindow.once('ready-to-show', () => {
    updateSplash('Opening scientific workspace…', 100);
    mainWindow.show();
    closeSplash();
  });
  await mainWindow.loadURL(`http://127.0.0.1:${port}`);
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv) => {
    const request = parseLaunchRequest(argv);
    if (request) persistLaunchRequest(request);
    focusMainWindow();
  });

  app.on('open-url', (event, url) => {
    event.preventDefault();
    pendingLaunchRequest = parseLaunchRequest([url]);
    if (pendingLaunchRequest) persistLaunchRequest(pendingLaunchRequest);
    focusMainWindow();
  });

  app.on('open-file', (event, filePath) => {
    event.preventDefault();
    pendingLaunchRequest = parseLaunchRequest([filePath]);
    if (pendingLaunchRequest) persistLaunchRequest(pendingLaunchRequest);
    focusMainWindow();
  });

  app.whenReady().then(async () => {
    try {
      registerDeepLinkProtocol();
      pendingLaunchRequest = pendingLaunchRequest || parseLaunchRequest(process.argv);
      await createSplashWindow();
      updateSplash('Checking protected workspace…', 18);
      workspacePath = ensureWorkspace();
      if (pendingLaunchRequest) persistLaunchRequest(pendingLaunchRequest);
      updateSplash('Selecting local service port…', 34);
      const port = await freePort();
      updateSplash('Starting scientific engine…', 52);
      await startBackend(workspacePath, port);
      updateSplash('Loading visualisation runtime…', 82);
      await createWindow(port);
      checkSecureUpdateNotice();
    } catch (error) {
      logDesktopEvent('startup-failed', error);
      closeSplash();
      dialog.showErrorBox('BioIntel AI could not start', error instanceof Error ? error.message : String(error));
      app.quit();
    }
  });
}

process.on('uncaughtException', error => {
  logDesktopEvent('uncaught-exception', error);
  if (app.isReady()) dialog.showErrorBox('BioIntel AI desktop error', 'A desktop-shell error was recorded. Restart the application; the local workspace remains preserved.');
});
process.on('unhandledRejection', reason => logDesktopEvent('unhandled-rejection', reason instanceof Error ? reason : { reason: String(reason) }));

app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });
app.on('before-quit', () => { closeSplash(); if (backend && !backend.killed) backend.kill(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) app.relaunch(); });
