<#
一键启动脚本（前端 + API）：视频号微信小店全自动系统 · 管理控制台

用法（在脚本所在目录，即项目根）：
  powershell -ExecutionPolicy Bypass -File _management/scripts/start-dev.ps1

说明：
  - API   → http://localhost:8001（账号 admin，密码默认 admin123，可用 $env:ADMIN_PASSWORD 覆盖）
  - 前端  → http://localhost:3000/login
  - P-023 纪律：前后端统一 localhost（SameSite cookie 同站携带）
  - P-024 纪律：启动前清理 .next（防 build/dev 残留 chunk 冲突）
  - 停止：Ctrl+C（两个进程同时终止）
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)  # _management/scripts -> 项目根
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host "=== 视频号小店全自动系统 · 管理控制台启动 ===" -ForegroundColor Cyan

# 端口检查
foreach ($p in 3000, 8001) {
  $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
  if ($c) {
    $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    Write-Host "[warn] 端口 $p 已被 $($proc.ProcessName) 占用——请先停止或换端口" -ForegroundColor Yellow
    if ($p -eq 8001) { Write-Host "[hint] 8000 常被系统 svchost 占用，本项目固定用 8001" -ForegroundColor Yellow }
  }
}

# 账号注入（fixtures 模式）
$adminPass = if ($env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD } else { "admin123" }
$hashBytes = [System.Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($adminPass))
$env:M6_ADMIN_USERNAME = if ($env:M6_ADMIN_USERNAME) { $env:M6_ADMIN_USERNAME } else { "admin" }
$env:M6_ADMIN_PASSWORD_HASH = [BitConverter]::ToString($hashBytes).Replace("-", "").ToLower()
$env:M6_CORS_ORIGINS = "http://localhost:3000"
$env:NEXT_PUBLIC_API_BASE = "http://localhost:8001"

# P-024：启动前清理 .next（防 build/dev 残留）
$nextDir = Join-Path $Frontend ".next"
if (Test-Path $nextDir) {
  Write-Host "[clean] 清理 $nextDir（P-024 纪律）" -ForegroundColor DarkGray
  Remove-Item -Recurse -Force $nextDir
}

Write-Host "[api] 启动 FastAPI  http://localhost:8001（账号 $env:M6_ADMIN_USERNAME / $adminPass）" -ForegroundColor Green
Write-Host "[web] 启动 Next.js  http://localhost:3000/login" -ForegroundColor Green
Write-Host "浏览器打开 http://localhost:3000/login 登录；Ctrl+C 停止。" -ForegroundColor Cyan

Push-Location $Backend
$apiJob = Start-Job -ScriptBlock {
  param($envs, $work)
  Set-Location $work
  foreach ($k in $envs.Keys) { Set-Item -Path "Env:$k" -Value $envs[$k] }
  & python -X utf8 -m api --host localhost --port 8001
} -ArgumentList @{
  "M6_ADMIN_USERNAME" = $env:M6_ADMIN_USERNAME
  "M6_ADMIN_PASSWORD_HASH" = $env:M6_ADMIN_PASSWORD_HASH
  "M6_CORS_ORIGINS" = $env:M6_CORS_ORIGINS
}, $Backend

Push-Location $Frontend
$webJob = Start-Job -ScriptBlock {
  param($envs, $work)
  Set-Location $work
  foreach ($k in $envs.Keys) { Set-Item -Path "Env:$k" -Value $envs[$k] }
  & npm run dev
} -ArgumentList @{
  "NEXT_PUBLIC_API_BASE" = $env:NEXT_PUBLIC_API_BASE
}, $Frontend

Pop-Location

try {
  while ($true) {
    Receive-Job $apiJob, $webJob -Keep | ForEach-Object { Write-Host $_ }
    Start-Sleep -Seconds 2
    if ($apiJob.State -ne "Running") { Write-Host "[api] 进程退出：$($apiJob.State)" -ForegroundColor Red; break }
    if ($webJob.State -ne "Running") { Write-Host "[web] 进程退出：$($webJob.State)" -ForegroundColor Red; break }
  }
} finally {
  Stop-Job $apiJob, $webJob -ErrorAction SilentlyContinue
  Remove-Job $apiJob, $webJob -Force -ErrorAction SilentlyContinue
  Write-Host "已停止。" -ForegroundColor Cyan
}
