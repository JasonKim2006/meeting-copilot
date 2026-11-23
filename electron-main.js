const { app, BrowserWindow, session, systemPreferences, screen, ipcMain } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const PORT = 8765;
let server = null;
let fullSize = null;

function startServer() {
  const py = path.join(__dirname, '.venv', 'bin', 'python');
  server = spawn(py, ['-m', 'uvicorn', 'main:app', '--port', String(PORT)], { cwd: __dirname, stdio: 'inherit' });
}

function waitForServer(cb, tries = 0) {
  http.get({ host: '127.0.0.1', port: PORT, path: '/' }, (res) => { res.resume(); cb(); })
    .on('error', () => {
      if (tries > 240) { app.quit(); return; }
      setTimeout(() => waitForServer(cb, tries + 1), 500);
    });
}

async function createWindow() {
  if (process.platform === 'darwin') await systemPreferences.askForMediaAccess('microphone');
  const ses = session.defaultSession;
  ses.setPermissionRequestHandler((wc, permission, cb) => cb(permission === 'media'));
  ses.setPermissionCheckHandler((wc, permission) => permission === 'media');

  const wa = screen.getPrimaryDisplay().workArea;
  const win = new BrowserWindow({
    width: 420, height: 600, minWidth: 320, minHeight: 44,
    x: wa.x + wa.width - 440, y: wa.y + 40,
    frame: false, transparent: true, hasShadow: true,
    vibrancy: 'hud', visualEffectState: 'active',
    backgroundColor: '#00000000', title: 'Meeting Copilot',
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });
  win.setAlwaysOnTop(true, 'floating');
  win.loadURL(`http://127.0.0.1:${PORT}/`);
}

ipcMain.on('close', () => app.quit());
ipcMain.on('collapse', (e, collapsed) => {
  const w = BrowserWindow.fromWebContents(e.sender);
  if (!w) return;
  if (collapsed) { fullSize = w.getSize(); w.setSize(fullSize[0], 44, true); }
  else if (fullSize) { w.setSize(fullSize[0], fullSize[1], true); }
});

app.whenReady().then(() => { startServer(); waitForServer(createWindow); });
app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => { if (server) server.kill(); });