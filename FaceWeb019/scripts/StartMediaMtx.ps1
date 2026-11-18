param(
  [Parameter(Mandatory = $true)]
  [string]$CameraIp
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$toolRoot = Join-Path $projectRoot '.local\tools\mediamtx'
$runtimeRoot = Join-Path $projectRoot '.local\mediamtx'
$logs = Join-Path $projectRoot '.local\logs'
$exe = Join-Path $toolRoot 'mediamtx.exe'
$template = Join-Path $projectRoot 'mediamtx\mediamtx.yml.template'
$config = Join-Path $runtimeRoot 'mediamtx.yml'

$parsed = [System.Net.IPAddress]::None
if (-not [System.Net.IPAddress]::TryParse($CameraIp, [ref]$parsed) -or $parsed.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
  throw 'CameraIp must be an IPv4 address.'
}
if (-not (Test-Path -LiteralPath $exe)) { throw 'MediaMTX executable is missing from .local/tools/mediamtx.' }
if (Get-NetTCPConnection -LocalPort 8888,8889,9997 -State Listen -ErrorAction SilentlyContinue) { throw 'A MediaMTX service may already be listening on port 8888, 8889, or 9997.' }

New-Item -ItemType Directory -Force -Path $runtimeRoot,$logs | Out-Null
$source = "rtsp://$CameraIp`:554/"
(Get-Content -Raw -LiteralPath $template).Replace('__RTSP_SOURCE__', $source) | Set-Content -LiteralPath $config -NoNewline
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$out = Join-Path $logs "mediamtx-$stamp.stdout.log"
$err = Join-Path $logs "mediamtx-$stamp.stderr.log"
$process = Start-Process -FilePath $exe -ArgumentList "`"$config`"" -WorkingDirectory $runtimeRoot -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
"MEDIAMTX_PID=$($process.Id)"
"WEBRTC=http://127.0.0.1:8889/camera-01"
"HLS=http://127.0.0.1:8888/camera-01/index.m3u8"
