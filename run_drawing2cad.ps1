<#
.SYNOPSIS
  One-click: set up Drawing2CAD, download public-domain drawings, convert them
  all to CAD, and open the results. Run this once; it does the rest.

.DESCRIPTION
  From a clone of the repo, this single script:
    1. finds Python (tells you the one link if it's missing),
    2. builds a local virtual environment and installs the dependencies
       (including the opencv-contrib step that must win last),
    3. downloads N public-domain HABS/HAER/HALS drawings from the Library of
       Congress (US Government works - public domain),
    4. converts every downloaded drawing to DXF + an SVG preview + a
       missed-ink audit,
    5. writes a summary and opens the output folder.

  It is safe to re-run: setup steps are skipped when already done.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\run_drawing2cad.ps1
  powershell -ExecutionPolicy Bypass -File .\run_drawing2cad.ps1 -Count 40
#>
param(
  [int]$Count = 20,
  [string]$Collection = "historic-american-buildings-landscapes-and-engineering-records"
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
Set-Location $repo
$data = Join-Path $env:USERPROFILE ".drawing2cad_dataset\architectural"
$raw  = Join-Path $data "raw"
$meta = Join-Path $data "meta"
$out  = Join-Path $data "out"
New-Item -ItemType Directory -Force -Path $raw, $meta, $out | Out-Null
$ua = "Drawing2CAD-fetch/1.0 (personal research; public-domain Library of Congress content)"

function Say($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

# ---------------------------------------------------------------- 1. Python
Say "1/5  Checking Python"
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) {
  Write-Host "Python not found. Install it once from https://www.python.org/downloads/windows/" -ForegroundColor Yellow
  Write-Host "(tick 'Add python.exe to PATH' in the installer), then re-run this script." -ForegroundColor Yellow
  return
}
Write-Host ("Found " + (python --version 2>&1))

# ---------------------------------------------------------------- 2. Deps
Say "2/5  Setting up the environment (first run takes a few minutes)"
$py = Join-Path $repo ".venv\Scripts\python.exe"
# Build the venv with a Python the ecosystem fully supports if one is present
# (OpenCV / RapidOCR lag brand-new Python releases like 3.14). Prefer 3.12/3.11
# via the 'py' launcher; otherwise use whatever 'python' is.
if (-not (Test-Path $py)) {
  $made = $false
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("3.12", "3.11")) {
      py "-$v" -m venv .venv 2>$null
      if (($LASTEXITCODE -eq 0) -and (Test-Path $py)) {
        Write-Host "Using Python $v for the environment." ; $made = $true ; break
      }
    }
  }
  if (-not $made) { python -m venv .venv }
}
& $py -m pip install --quiet --upgrade pip setuptools wheel

$marker = Join-Path $repo ".venv\.deps_ok"
if (-not (Test-Path $marker)) {
  # core stack (geometry + Tesseract OCR) - install each so one failure doesn't
  # abort the rest
  foreach ($pkg in @("numpy", "ezdxf", "pytesseract", "pillow",
                     "opencv-contrib-python-headless")) {
    Write-Host "  installing $pkg ..."
    & $py -m pip install --quiet $pkg
  }
  # optional neural reader - not yet built for very new Python; skipping it is
  # fine (Tesseract still reads text; geometry is unaffected)
  & $py -m pip install --quiet rapidocr_onnxruntime 2>$null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  (RapidOCR unavailable on this Python - Tesseract only; geometry unaffected.)" -ForegroundColor Yellow
  }
  "ok" | Set-Content $marker
}

# essential-stack sanity check - if OpenCV/numpy have no wheels for this Python,
# stop with the one fix instead of failing deep in conversion
& $py -c "import cv2, numpy, ezdxf" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "The core libraries (OpenCV/numpy) have no wheels for your Python yet:" -ForegroundColor Yellow
  Write-Host ("  " + (python --version 2>&1)) -ForegroundColor Yellow
  Write-Host "One-time fix - install Python 3.12 (fully supported), tick 'Add python.exe to PATH':" -ForegroundColor Yellow
  Write-Host "  https://www.python.org/downloads/release/python-3129/" -ForegroundColor Yellow
  Write-Host "Then delete the .venv folder in this repo and re-run this script." -ForegroundColor Yellow
  Remove-Item $marker -ErrorAction SilentlyContinue
  return
}
# Tesseract is optional (OCR); geometry works without it
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue)) {
  Write-Host "Note: Tesseract not found - clean geometry, but no text/OCR." -ForegroundColor Yellow
  Write-Host "      Optional install: https://github.com/UB-Mannheim/tesseract/wiki" -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 3. Download
Say "3/5  Downloading $Count public-domain drawings from the Library of Congress"
$got = 0; $page = 1
while ($got -lt $Count) {
  $api = "https://www.loc.gov/collections/$Collection/?fo=json&at=results&c=25&sp=$page&fa=online-format:image"
  try { $resp = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = $ua } -TimeoutSec 30 }
  catch { Write-Warning ("LoC page {0} failed: {1}" -f $page, $_); break }
  if (-not $resp.results) { break }
  foreach ($item in $resp.results) {
    if ($got -ge $Count) { break }
    $urls = @($item.image_url); if ($urls.Count -eq 0) { continue }
    $img = [string]$urls[$urls.Count - 1]
    if ($img.StartsWith("//")) { $img = "https:" + $img }
    $name = "loc_{0:D4}.jpg" -f $got
    try { Invoke-WebRequest -Uri $img -Headers @{ "User-Agent" = $ua } -OutFile (Join-Path $raw $name) -TimeoutSec 60 }
    catch { Write-Warning ("skip {0}: {1}" -f $name, $_); continue }
    ([ordered]@{ source = "loc_habs_haer"; license = "US Gov - public domain"; loc_url = $item.id; image_url = $img } |
      ConvertTo-Json) | Set-Content -Path (Join-Path $meta "$name.json") -Encoding UTF8
    $got++; Write-Host ("  [{0}/{1}] {2}" -f $got, $Count, $name)
    Start-Sleep -Seconds 2
  }
  $page++
}
Write-Host "Downloaded $got drawing(s)."

# ---------------------------------------------------------------- 4. Convert
Say "4/5  Converting every drawing to CAD (DXF + SVG preview + missed-ink audit)"
$images = Get-ChildItem -Path $raw -Include *.jpg, *.jpeg, *.png, *.tif, *.tiff -Recurse
$done = 0
foreach ($f in $images) {
  $dxf = Join-Path $out ($f.BaseName + ".dxf")
  try {
    & $py scan2cad.py "$($f.FullName)" -o "$dxf" --svg --diff
    $done++
  } catch {
    Write-Warning ("convert failed for {0}: {1}" -f $f.Name, $_)
  }
}

# ---------------------------------------------------------------- 5. Done
Say "5/5  Done"
Write-Host "Converted $done drawing(s)."
Write-Host "Output (DXF / SVG / diff.png) is in:" -ForegroundColor Green
Write-Host "  $out" -ForegroundColor Green
if ($done -gt 0) { Invoke-Item $out }
