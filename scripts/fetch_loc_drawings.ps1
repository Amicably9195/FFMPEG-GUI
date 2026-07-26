<#
.SYNOPSIS
  Download public-domain measured drawings from the Library of Congress
  (Historic American Buildings Survey / Engineering Record) into the
  Drawing2CAD dataset folder.

.DESCRIPTION
  US Government works are public domain. This pulls from the LoC's official
  JSON API only, politely (descriptive User-Agent, a pause between requests,
  a hard cap) - a curated fetch, not a scrape. It writes each image plus a
  small .json with its source, license, and LoC URL so provenance is kept.

  This is the PowerShell twin of `python dataset_builder.py fetch --source
  loc_habs_haer`; use whichever you prefer.

.EXAMPLE
  ./fetch_loc_drawings.ps1 -Count 40

.NOTES
  Requires PowerShell 5+ (Windows 10/11 built-in). Respect the LoC's terms;
  keep the count modest and the delay >= 2s.
#>
param(
  [int]$Count = 25,
  # Combined HABS/HAER/HALS collection slug (confirmed working against the live
  # LoC JSON API; the older per-survey slugs 404).
  [string]$Collection = "historic-american-buildings-landscapes-and-engineering-records",
  [string]$OutDir = "$env:USERPROFILE\.drawing2cad_dataset\architectural",
  [double]$DelaySeconds = 2.0
)

$ua = "Drawing2CAD-fetch/1.0 (personal research; public-domain Library of Congress content)"
$raw  = Join-Path $OutDir "raw"
$meta = Join-Path $OutDir "meta"
New-Item -ItemType Directory -Force -Path $raw, $meta | Out-Null

$got = 0
$page = 1
while ($got -lt $Count) {
  $api = "https://www.loc.gov/collections/$Collection/?fo=json&at=results&c=25&sp=$page&fa=online-format:image"
  try {
    $data = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = $ua } -TimeoutSec 30
  } catch {
    Write-Warning "LoC page $page failed: $_"
    break
  }
  if (-not $data.results) { break }

  foreach ($item in $data.results) {
    if ($got -ge $Count) { break }
    $urls = @($item.image_url)             # force to an array (may be 1 string)
    if ($urls.Count -eq 0) { continue }
    $img = [string]$urls[$urls.Count - 1]  # largest offered
    if ($img.StartsWith("//")) { $img = "https:" + $img }

    $name = "loc_{0:D4}.jpg" -f $got
    $imgPath = Join-Path $raw $name
    try {
      Invoke-WebRequest -Uri $img -Headers @{ "User-Agent" = $ua } -OutFile $imgPath -TimeoutSec 60
    } catch {
      Write-Warning ("skip {0}: {1}" -f $name, $_)   # -f avoids the $name: parse trap
      continue
    }

    $rec = [ordered]@{
      source     = "loc_habs_haer"
      license    = "US Government work - public domain"
      collection = $Collection
      loc_url    = $item.id
      title      = ($item.title | Out-String).Trim()
      image_url  = $img
      category   = "architectural"
    }
    $rec | ConvertTo-Json | Set-Content -Path (Join-Path $meta "$name.json") -Encoding UTF8

    $got++
    Write-Host "[$got/$Count] $name"
    Start-Sleep -Seconds $DelaySeconds
  }
  $page++
}

Write-Host ""
Write-Host "Downloaded $got public-domain drawing(s) into $raw"
Write-Host "Next: python dataset_builder.py split   (assigns train/val/benchmark)"
