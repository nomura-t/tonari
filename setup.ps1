# となりの初回の用意（Windows）。このフォルダの PowerShell で:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
# 入れるもの（入っていれば入れ直さない）: uv（Python の実行・astral.sh の公式の入れ方）、ffmpeg（録音の変換・winget の
# Gyan.FFmpeg。winget の同意を自動で受ける）、speech.cpp（端末内の聞き取り Haas を動かす道具・GitHub の nyosegawa/speech.cpp の
# install.ps1。GPU のドライバの Vulkan が要る）。そのあと uv sync と prepare.py（場所の記録・モデルの取得・確かめ・ショートカット）。
# 2026-11-03 に作った。Mac では確かめていない（Windows の PC で初めて流す）。止まったら、その行と表示を見て直す。
# このファイルは UTF-8（BOM つき）。BOM が無いと Windows PowerShell 5.1 が日本語を cp932 で読んで壊す。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Test-Command([string] $Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Update-PathFromRegistry {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

if (-not (Test-Command 'uv')) {
    Write-Host 'uv を入れます（https://astral.sh/uv/install.ps1）'
    powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    Update-PathFromRegistry
    if (-not (Test-Command 'uv')) { $env:Path = "$env:USERPROFILE\.local\bin;$env:Path" }
}

if (-not (Test-Command 'ffmpeg')) {
    Write-Host 'ffmpeg を入れます（winget install --id Gyan.FFmpeg -e）'
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    Update-PathFromRegistry
}

$speech = Join-Path $env:LOCALAPPDATA 'Programs\speech.cpp\current\speech.exe'
if (-not (Test-Command 'speech') -and -not (Test-Path -LiteralPath $speech)) {
    if (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\vulkan-1.dll')) {
        Write-Host 'speech.cpp を入れます（端末内の聞き取り Haas を動かす道具）'
        irm https://raw.githubusercontent.com/nyosegawa/speech.cpp/main/install.ps1 | iex
        Update-PathFromRegistry
    } else {
        Write-Warning 'この PC には Vulkan（vulkan-1.dll）が無いので speech.cpp を入れられません。GPU のドライバを入れ直すか、となりの「設定を開く」で ElevenLabs の鍵を入れてください。'
    }
}

uv sync
if ($LASTEXITCODE -ne 0) { throw 'uv sync に失敗しました' }
uv run python prepare.py @args
exit $LASTEXITCODE
