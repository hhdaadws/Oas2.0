const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const http = require('http')

// --- Configuration ---
const BACKEND_PORT = 9001
const FRONTEND_PORT = 9000
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`

const ROOT_DIR = path.resolve(__dirname, '..')
const FRONTEND_DIR = path.join(ROOT_DIR, 'frontend')

let mainWindow = null
let backendProcess = null
let frontendProcess = null

// --- Utility: wait for a port to respond ---
function waitForPort(url, timeoutMs = 30000) {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(url, (res) => {
        res.resume()
        resolve()
      })
      req.on('error', () => {
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Timeout waiting for ${url}`))
        } else {
          setTimeout(check, 500)
        }
      })
      req.setTimeout(2000, () => {
        req.destroy()
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Timeout waiting for ${url}`))
        } else {
          setTimeout(check, 500)
        }
      })
    }
    check()
  })
}

// --- Start FastAPI backend ---
function startBackend() {
  const CONDA_ENV = 'D:\\Users\\ASUS\\anaconda3\\envs\\timeocr'
  const condaPython = path.join(CONDA_ENV, 'python.exe')
  const uvicornModule = path.join(CONDA_ENV, 'Scripts', 'uvicorn.exe')

  // Try uvicorn.exe first, fall back to python -m uvicorn
  const fs = require('fs')
  let cmd, args

  if (fs.existsSync(uvicornModule)) {
    cmd = uvicornModule
    args = ['app.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)]
  } else {
    cmd = condaPython
    args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)]
  }

  console.log(`[Backend] Starting: ${cmd} ${args.join(' ')}`)

  backendProcess = spawn(cmd, args, {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      PYTHONPATH: path.join(ROOT_DIR, 'src'),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })
  backendProcess.stderr.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`)
  })
  backendProcess.on('error', (err) => {
    console.error(`[Backend] Failed to start: ${err.message}`)
  })
  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`)
    backendProcess = null
  })
}

// --- Start Vite frontend dev server ---
function startFrontend() {
  console.log(`[Frontend] Starting vite dev server on port ${FRONTEND_PORT}...`)

  frontendProcess = spawn('npx', ['vite', '--port', String(FRONTEND_PORT)], {
    cwd: FRONTEND_DIR,
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    shell: true,
  })

  frontendProcess.stdout.on('data', (data) => {
    console.log(`[Frontend] ${data.toString().trim()}`)
  })
  frontendProcess.stderr.on('data', (data) => {
    console.log(`[Frontend] ${data.toString().trim()}`)
  })
  frontendProcess.on('error', (err) => {
    console.error(`[Frontend] Failed to start: ${err.message}`)
  })
  frontendProcess.on('exit', (code) => {
    console.log(`[Frontend] Exited with code ${code}`)
    frontendProcess = null
  })
}

// --- Create Electron window ---
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 700,
    title: 'YYS Automation',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  mainWindow.setMenuBarVisibility(false)
  mainWindow.loadURL(FRONTEND_URL)

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// --- Cleanup child processes ---
function killChildren() {
  if (backendProcess) {
    console.log('[Cleanup] Stopping backend...')
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(backendProcess.pid), '/f', '/t'], {
          windowsHide: true,
          shell: true,
        })
      } else {
        backendProcess.kill('SIGTERM')
      }
    } catch (e) { /* ignore */ }
    backendProcess = null
  }
  if (frontendProcess) {
    console.log('[Cleanup] Stopping frontend...')
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(frontendProcess.pid), '/f', '/t'], {
          windowsHide: true,
          shell: true,
        })
      } else {
        frontendProcess.kill('SIGTERM')
      }
    } catch (e) { /* ignore */ }
    frontendProcess = null
  }
}

// --- App lifecycle ---
app.whenReady().then(async () => {
  console.log('[App] Starting services...')

  // Start both backend and frontend
  startBackend()
  startFrontend()

  try {
    // Wait for both services to be ready
    console.log('[App] Waiting for backend...')
    await waitForPort(`${BACKEND_URL}/health`, 60000)
    console.log('[App] Backend is ready')

    console.log('[App] Waiting for frontend...')
    await waitForPort(FRONTEND_URL, 30000)
    console.log('[App] Frontend is ready')

    // Create the window
    createWindow()
  } catch (err) {
    console.error(`[App] Failed to start services: ${err.message}`)
    dialog.showErrorBox(
      'Startup Error',
      `Failed to start services:\n${err.message}\n\nPlease check that dependencies are installed.`
    )
    app.quit()
  }
})

app.on('window-all-closed', () => {
  killChildren()
  app.quit()
})

app.on('before-quit', () => {
  killChildren()
})

process.on('exit', () => {
  killChildren()
})
