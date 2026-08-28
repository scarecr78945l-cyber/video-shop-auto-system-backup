# GitHub 备份仓库一键推送脚本（总控专用）

> 用途：用户提供 PAT 后，创建私有仓库 `video-shop-auto-system` 并推送全部备份。
> 用法：`powershell -File push-github.ps1 -Pat "ghp_xxx"`（令牌仅本次使用，用完即撤）。

param(
  [Parameter(Mandatory=$true)][string]$Pat,
  [string]$RepoName = "video-shop-auto-system",
  [string]$Visibility = "private"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Output "== 1/4 创建 GitHub 仓库: $RepoName ($Visibility) =="
$headers = @{ Authorization = "token $Pat"; "User-Agent" = "dsh-backup" }
$body = @{ name = $RepoName; private = ($Visibility -eq "private"); description = "视频号微信小店全自动系统 - 备份仓库" } | ConvertTo-Json
try {
  $resp = Invoke-RestMethod -Method Post -Uri "https://api.github.com/user/repos" -Headers $headers -ContentType "application/json" -Body $body
  Write-Output "仓库已创建: $($resp.html_url)"
} catch {
  $msg = $_.Exception.Message
  if ($msg -match "already exists") { Write-Output "仓库已存在，继续推送" }
  else { throw "创建仓库失败: $msg" }
}

Write-Output "== 2/4 配置 remote =="
git -C $root remote remove origin 2>$null | Out-Null
git -C $root remote add origin "https://x-access-token:$Pat@github.com/$($resp.owner.login)/$RepoName.git" 2>$null
if (-not $?) {
  # 仓库已存在时 resp 为 null，用默认账户名不可靠，改走可推送地址
  Write-Output "需要用户 GitHub 用户名。请手动执行："
  Write-Output "  git remote add origin https://x-access-token:<PAT>@github.com/<你的用户名>/$RepoName.git"
  Write-Output "  git push -u origin --all && git push --tags"
  exit 1
}

Write-Output "== 3/4 推送全部分支与标签 =="
git -C $root push -u origin --all 2>&1 | ForEach-Object { Write-Output $_ }
git -C $root push --tags 2>&1 | ForEach-Object { Write-Output $_ }

Write-Output "== 4/4 完成 =="
git -C $root remote set-url origin "https://github.com/$($resp.owner.login)/$RepoName.git"
Write-Output "已移除令牌，remote 已还原为 https://github.com/$($resp.owner.login)/$RepoName.git"
