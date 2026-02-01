const { spawn } = require('child_process')
const fs = require('fs')
const path = require('path')

const rootDir = process.cwd()
const backendDir = path.join(rootDir, 'backend')

const pythonCandidates = [
  path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
  path.join(backendDir, '.venv', 'bin', 'python'),
]

const pythonCmd = pythonCandidates.find((candidate) => fs.existsSync(candidate)) || 'python'
const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm'

const backendPort = process.env.BACKEND_PORT || '8000'
const frontendPort = process.env.FRONTEND_PORT

const backendArgs = [
  '-m',
  'uvicorn',
  'main:app',
  '--reload',
  '--host',
  '0.0.0.0',
  '--port',
  backendPort,
]

const frontendArgs = ['run', 'dev', ...(frontendPort ? ['--', '--port', frontendPort] : [])]

const backendProc = spawn(pythonCmd, backendArgs, {
  cwd: backendDir,
  stdio: 'inherit',
})

const frontendProc = spawn(npmCmd, frontendArgs, {
  cwd: rootDir,
  stdio: 'inherit',
})

const shutdown = (signal) => {
  backendProc.kill(signal)
  frontendProc.kill(signal)
}

process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))

backendProc.on('exit', (code) => {
  if (code && code !== 0) {
    console.error(`Backend exited with code ${code}`)
  }
})

frontendProc.on('exit', (code) => {
  if (code && code !== 0) {
    console.error(`Frontend exited with code ${code}`)
  }
})
