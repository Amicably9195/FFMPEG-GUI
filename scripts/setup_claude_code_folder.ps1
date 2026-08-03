<#
.SYNOPSIS
  Set up this project inside the Claude Code folder on your Desktop, and file
  its two Windows executables into the sibling Portable\ and Executable\
  folders.

.DESCRIPTION
  Target layout (created if missing):

      <Desktop>\Claude Code\
          03 - Drawing2CAD\      <- all project work/source lives here
          Portable\              <- 03 - Drawing2CAD Portable.exe
          Executable\            <- 03 - Drawing2CAD.exe

  What this does:
    1. creates the Claude Code root plus Portable\ and Executable\,
    2. clones (or updates) the project into "03 - Drawing2CAD",
    3. downloads the two executables from the latest successful GitHub Actions
       build and copies them into Portable\ and Executable\, replacing any
       existing files of the same name (no version suffixes).

  The executables are built in GitHub Actions on Windows runners because they
  cannot be cross-compiled from the Linux cloud session; this script is the
  last mile onto this PC.

.EXAMPLE
  .\setup_claude_code_folder.ps1
  .\setup_claude_code_folder.ps1 -ClaudeRoot "D:\Claude Code"
  .\setup_claude_code_folder.ps1 -SkipExecutables      # just set up the folders/source

.NOTES
  Needs git. For the executables it also needs the GitHub CLI (gh) -
  https://cli.github.com - and a one-time 'gh auth login'.
#>
param(
  [string]$ClaudeRoot = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Claude Code'),
  [string]$Prefix = "03",
  [string]$AppName = "Drawing2CAD",
  [string]$RepoUrl = "https://github.com/Amicably9195/FFMPEG-GUI.git",
  [string]$Branch = "claude/drawing-scan-to-cad-v1l3ff",
  [switch]$SkipExecutables
)

$ErrorActionPreference = "Stop"
function Say($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

$projectDir    = Join-Path $ClaudeRoot ("{0} - {1}" -f $Prefix, $AppName)
$portableDir   = Join-Path $ClaudeRoot "Portable"
$executableDir = Join-Path $ClaudeRoot "Executable"

# ------------------------------------------------------------ 1. structure
Say "1/3  Creating the Claude Code folder structure"
foreach ($d in @($ClaudeRoot, $portableDir, $executableDir)) {
  if (-not (Test-Path $d)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host ("  {0}" -f $d)
}

# ------------------------------------------------------------ 2. project
Say "2/3  Putting the project source in '$Prefix - $AppName'"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "git not found - install from https://git-scm.com/download/win" -ForegroundColor Yellow
  return
}
if (Test-Path (Join-Path $projectDir ".git")) {
  Push-Location $projectDir
  git fetch origin $Branch 2>&1 | Out-Null
  git checkout $Branch 2>&1 | Out-Null
  git pull origin $Branch
  Pop-Location
  Write-Host "  updated existing checkout" -ForegroundColor Green
} else {
  git clone -b $Branch $RepoUrl "$projectDir"
  Write-Host "  cloned into $projectDir" -ForegroundColor Green
}

if ($SkipExecutables) { Say "Done (executables skipped)"; return }

# ------------------------------------------------------------ 3. executables
Say "3/3  Filing the two executables"
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Write-Host "GitHub CLI not found - install from https://cli.github.com, then" -ForegroundColor Yellow
  Write-Host "run 'gh auth login' and re-run this script." -ForegroundColor Yellow
  Write-Host "(Or download the artifacts manually from the repo's Actions tab.)" -ForegroundColor Yellow
  return
}
gh auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Run 'gh auth login' first." -ForegroundColor Yellow; return }

Push-Location $projectDir
$runId = gh run list --workflow "build-drawing2cad.yml" --status success `
                     --limit 1 --json databaseId --jq ".[0].databaseId"
Pop-Location
if (-not $runId) {
  Write-Host "No successful build yet - check the repo's Actions tab, then re-run." -ForegroundColor Yellow
  return
}
Write-Host "  using build run $runId"

$tmp = Join-Path $env:TEMP ("d2c_{0}" -f $runId)
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

Push-Location $projectDir
gh run download $runId --dir $tmp
Pop-Location

$portableSrc  = Get-ChildItem -Path $tmp -Recurse -Filter "*Portable*.exe" | Select-Object -First 1
$installerSrc = Get-ChildItem -Path $tmp -Recurse -Filter "*.exe" |
                Where-Object { $_.Name -notlike "*Portable*" } | Select-Object -First 1

$portableDst  = Join-Path $portableDir   ("{0} - {1} Portable.exe" -f $Prefix, $AppName)
$installerDst = Join-Path $executableDir ("{0} - {1}.exe" -f $Prefix, $AppName)

if ($portableSrc)  { Copy-Item $portableSrc.FullName  $portableDst  -Force
                     Write-Host ("  portable  -> {0}" -f $portableDst)  -ForegroundColor Green }
else { Write-Warning "portable executable not found in the artifacts" }

if ($installerSrc) { Copy-Item $installerSrc.FullName $installerDst -Force
                     Write-Host ("  installer -> {0}" -f $installerDst) -ForegroundColor Green }
else { Write-Warning "installer executable not found in the artifacts" }

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Say "Done"
Write-Host "Layout ready under $ClaudeRoot" -ForegroundColor Green
Write-Host ("  {0} - {1}\   (project work)" -f $Prefix, $AppName)
Write-Host  "  Portable\    (portable exe)"
Write-Host  "  Executable\  (installer)"
