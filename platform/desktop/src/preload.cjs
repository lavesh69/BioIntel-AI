'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('biointelDesktop', Object.freeze({
  platform: process.platform,
  packaged: true,
  onBackendExit: callback => ipcRenderer.on('backend-exit', (_event, code) => callback(code)),
  onLaunchRequest: callback => ipcRenderer.on('biointel-launch-request', (_event, request) => callback(request)),
  onUpdateNotice: callback => ipcRenderer.on('biointel-update-notice', (_event, notice) => callback(notice)),
}));
