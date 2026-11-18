import './style.css';
import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Haptics, ImpactStyle } from '@capacitor/haptics';
import { Network } from '@capacitor/network';
import { Preferences } from '@capacitor/preferences';
import { Share } from '@capacitor/share';
import { SplashScreen } from '@capacitor/splash-screen';
import { StatusBar, Style } from '@capacitor/status-bar';

const SERVER_KEY = 'biointel_server_url';
const DEFAULT_SERVER = '';

type Bootstrap = {
  app_name: string;
  version: string;
  status: string;
  workspace_url?: string;
  legal: { privacy: string; terms: string; support: string };
  scientific_boundary: string;
};

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('Application root is unavailable.');

app.innerHTML = `
  <main class="shell">
    <header class="brand"><img src="./icon-192.png" alt="BioIntel AI icon"><div><div class="eyebrow">Scientific Intelligence for Life Sciences</div><h1>BioIntel AI</h1><div class="brand-tagline">Biology, Engineered into Intelligence.</div><div class="sub">Securely connect this device to your organisation's hosted BioIntel workspace.</div><div class="brand-founder">Created and developed by Lavesh Dobriyal</div></div></header>
    <section class="card connection-card" aria-labelledby="connectionTitle">
      <strong id="connectionTitle" class="section-title">Workspace connection</strong>
      <label for="serverUrl">Workspace HTTPS address</label>
      <input id="serverUrl" type="url" inputmode="url" autocomplete="url" placeholder="https://biointel.your-organisation.com" aria-describedby="serverHelp">
      <div id="serverHelp" class="notice">Mobile editions do not store the full scientific database on the phone. They connect to the server your organisation controls.</div>
      <div class="actions">
        <button id="test" class="secondary" data-idle-label="Test connection" data-busy-label="Testing…"><span class="button-label">Test connection</span><span class="button-spinner" aria-hidden="true"></span></button>
        <button id="connect" class="primary" data-idle-label="Open workspace" data-busy-label="Opening…"><span class="button-label">Open workspace</span><span class="button-spinner" aria-hidden="true"></span></button>
      </div>
      <div class="status" role="status" aria-live="polite" aria-atomic="true"><span id="statusDot" class="dot working"></span><span id="statusText">Checking device network…</span></div>
    </section>
    <section class="grid">
      <div class="tile"><strong>Privacy first</strong><span>No advertising SDKs, cross-app tracking or automatic scientific-file sharing.</span></div>
      <div class="tile"><strong>Research boundary</strong><span>Outputs support research and education; they are not diagnosis or treatment advice.</span></div>
      <div class="tile"><strong>Native connection tools</strong><span>Network awareness, deep links, secure URL validation, sharing and haptic status feedback.</span></div>
      <div class="tile"><strong>Operator controlled</strong><span>Your organisation selects the server, access policy, providers and retention configuration.</span></div>
    </section>
    <section class="card">
      <strong>Connection details</strong><p id="details" class="notice">No server has been verified on this device.</p>
      <div class="legal"><button id="privacy" class="ghost">Privacy</button><button id="terms" class="ghost">Terms</button><button id="support" class="ghost">Support</button><button id="share" class="ghost">Share workspace</button></div>
    </section>
  </main>`;

const input = document.querySelector<HTMLInputElement>('#serverUrl')!;
const statusText = document.querySelector<HTMLSpanElement>('#statusText')!;
const statusDot = document.querySelector<HTMLSpanElement>('#statusDot')!;
const details = document.querySelector<HTMLParagraphElement>('#details')!;
const testButton = document.querySelector<HTMLButtonElement>('#test')!;
const connectButton = document.querySelector<HTMLButtonElement>('#connect')!;
let bootstrap: Bootstrap | null = null;
let busyAction: 'test' | 'connect' | 'legal' | null = null;
let deviceOnline = true;

function normalizeServer(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '');
  if (!trimmed) throw new Error('Enter your organisation\'s BioIntel server address.');
  const url = new URL(trimmed);
  const local = ['localhost', '127.0.0.1', '10.0.2.2'].includes(url.hostname);
  if (url.protocol !== 'https:' && !local) throw new Error('A secure HTTPS server is required.');
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('Only HTTP or HTTPS addresses are supported.');
  return url.toString().replace(/\/$/, '');
}

function setStatus(message: string, state: 'idle' | 'working' | 'ok' | 'bad' = 'idle') {
  statusText.textContent = message;
  statusDot.className = `dot ${state === 'idle' ? '' : state}`;
}

function updateButton(button: HTMLButtonElement, isBusy: boolean) {
  const label = button.querySelector<HTMLSpanElement>('.button-label');
  if (label) label.textContent = isBusy ? (button.dataset.busyLabel ?? 'Working…') : (button.dataset.idleLabel ?? 'Continue');
  button.classList.toggle('is-loading', isBusy);
  button.setAttribute('aria-busy', String(isBusy));
}

function setBusy(action: typeof busyAction) {
  busyAction = action;
  const isBusy = action !== null;
  input.disabled = isBusy;
  testButton.disabled = isBusy || !deviceOnline;
  connectButton.disabled = isBusy || !deviceOnline;
  updateButton(testButton, action === 'test');
  updateButton(connectButton, action === 'connect');
  document.querySelector('.connection-card')?.setAttribute('aria-busy', String(isBusy));
}

async function testConnection(manageBusy = true): Promise<Bootstrap> {
  if (!deviceOnline) throw new Error('This device is offline. Reconnect and try again.');
  if (manageBusy) setBusy('test');
  const server = normalizeServer(input.value);
  setStatus('Contacting BioIntel server…', 'working');
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`${server}/v1/mobile/bootstrap`, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Server returned HTTP ${response.status}.`);
    const payload = (await response.json()) as Bootstrap;
    if (payload.status !== 'ready' || !payload.version) throw new Error('This address is not a compatible BioIntel server.');
    bootstrap = payload;
    await Preferences.set({ key: SERVER_KEY, value: server });
    setStatus(`Connected · BioIntel AI ${payload.version}`, 'ok');
    details.textContent = `${payload.app_name} ${payload.version}. ${payload.scientific_boundary}`;
    await Haptics.impact({ style: ImpactStyle.Light });
    return payload;
  } catch (error) {
    bootstrap = null;
    const message = error instanceof Error && error.name === 'AbortError'
      ? 'Connection timed out after 10 seconds.'
      : error instanceof Error ? error.message : 'Connection failed.';
    setStatus(message, 'bad');
    await Haptics.impact({ style: ImpactStyle.Heavy });
    throw error;
  } finally {
    window.clearTimeout(timeout);
    if (manageBusy) setBusy(null);
  }
}

async function openWorkspace() {
  if (busyAction) return;
  setBusy('connect');
  try {
    await testConnection(false);
    const server = normalizeServer(input.value);
    setStatus('Opening secure workspace…', 'working');
    await Browser.open({ url: server });
    setStatus('Workspace opened securely.', 'ok');
  } catch { /* status already shown */ }
  finally { setBusy(null); }
}

async function legal(kind: 'privacy' | 'terms' | 'support') {
  if (busyAction) return;
  setBusy('legal');
  try {
    const payload = bootstrap ?? await testConnection(false);
    const server = normalizeServer(input.value);
    const configured = payload.legal?.[kind];
    const url = configured?.startsWith('http') ? configured : `${server}/legal/${kind}`;
    await Browser.open({ url });
  } catch { /* status already shown */ }
  finally { setBusy(null); }
}

testButton.addEventListener('click', () => void testConnection().catch(() => undefined));
connectButton.addEventListener('click', () => void openWorkspace());
document.querySelector('#privacy')?.addEventListener('click', () => void legal('privacy'));
document.querySelector('#terms')?.addEventListener('click', () => void legal('terms'));
document.querySelector('#support')?.addEventListener('click', () => void legal('support'));
document.querySelector('#share')?.addEventListener('click', async () => {
  try {
    const server = normalizeServer(input.value);
    await Share.share({ title: 'BioIntel AI workspace', text: 'BioIntel AI scientific workspace', url: server });
  } catch (error) { setStatus(error instanceof Error ? error.message : 'Unable to share.', 'bad'); }
});

Network.addListener('networkStatusChange', status => {
  deviceOnline = status.connected;
  setBusy(busyAction);
  setStatus(status.connected ? 'Device is online.' : 'Device is offline.', status.connected ? 'ok' : 'bad');
});
App.addListener('appUrlOpen', event => {
  try {
    const incoming = new URL(event.url);
    const server = incoming.searchParams.get('server');
    if (server) { input.value = server; void testConnection().catch(() => undefined); }
  } catch { setStatus('Invalid BioIntel deep link.', 'bad'); }
});
App.addListener('backButton', ({ canGoBack }) => { if (canGoBack) history.back(); else void App.minimizeApp(); });

async function init() {
  try { await StatusBar.setStyle({ style: Style.Light }); } catch { /* web preview */ }
  const saved = await Preferences.get({ key: SERVER_KEY });
  input.value = saved.value ?? DEFAULT_SERVER;
  const network = await Network.getStatus();
  deviceOnline = network.connected;
  setBusy(null);
  setStatus(network.connected ? 'Device is online.' : 'Device is offline.', network.connected ? 'ok' : 'bad');
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
  await SplashScreen.hide();
  if (saved.value && network.connected) void testConnection().catch(() => undefined);
}

void init();
