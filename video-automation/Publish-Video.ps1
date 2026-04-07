param(
    [Parameter(Mandatory=$true)]
    [string]$InputFile,
    
    [string]$Title = ([System.IO.Path]::GetFileNameWithoutExtension($InputFile)),
    
    [string]$Profile = "roadmap"
)

$scriptDir = Split-Path $PSCommandPath
$normalizeScript = Join-Path $scriptDir "Normalize-Video.py"
$uploadScript = Join-Path $scriptDir "Upload-YouTube.py"

# Calculate the expected normalized file path
$baseName = [System.IO.Path]::GetFileNameWithoutExtension($InputFile)
$dir = Split-Path $InputFile
$NormalizedFile = Join-Path $dir "$($baseName)_youtube.mp4"

# 1. Normalize (SKIP if already exists)
if (Test-Path $NormalizedFile) {
    Write-Host "--- Step 1: Normalized video found at $NormalizedFile. Skipping. ---" -ForegroundColor Yellow
} else {
    Write-Host "--- Step 1: Normalizing Video ---" -ForegroundColor Cyan
    $NormalizedFile = python $normalizeScript $InputFile | Select-Object -Last 1
}

if (-not $NormalizedFile -or -not (Test-Path $NormalizedFile)) {
    Write-Error "Normalization failed or output path not found."
    exit 1
}

# 2. Upload
Write-Host "--- Step 2: Uploading to YouTube ---" -ForegroundColor Green
python $uploadScript $NormalizedFile $Title

Write-Host "Process Complete!" -ForegroundColor Yellow
