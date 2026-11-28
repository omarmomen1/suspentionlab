<#
.SYNOPSIS
    Automated shipping script for SuspensionLab PRO.
    Merges a branch or Instinct bundle onto master, validates benchmarks & frontend,
    and pushes to origin to trigger automated production deployment.

.PARAMETER Bundle
    Path to a git bundle file (e.g., .bundle or .bundle.txt) to verify, fetch, and merge.

.PARAMETER Branch
    Name of a local git branch to merge into master with --no-ff.

.EXAMPLE
    .\scripts\ship.ps1 -Branch wave-8-kinematics

.EXAMPLE
    .\scripts\ship.ps1 -Bundle .\instinct-export.bundle.txt

.EXAMPLE
    .\scripts\ship.ps1
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false, Position = 0)]
    [string]$Bundle,

    [Parameter(Mandatory = $false, Position = 1)]
    [string]$Branch
)

$ErrorActionPreference = "Stop"

# Ensure we operate in the repository root directory
$repoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $repoRoot) {
    $repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
}
Set-Location $repoRoot

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " SuspensionLab PRO — Automated Release Ship Engine" -ForegroundColor Cyan
Write-Host " Working Directory: $repoRoot" -ForegroundColor DarkGray
Write-Host "=================================================================" -ForegroundColor Cyan

# ── 1. Remote Origin Reconciliation ──────────────────────────────────────────
$originUrl = (git remote get-url origin 2>$null)
if ($originUrl -match "quarter-car-dashboard\.git") {
    $targetOrigin = "https://github.com/omarmomen1/suspentionlab.git"
    Write-Host "[Remote] Updating origin remote:" -ForegroundColor Yellow
    Write-Host "         $originUrl -> $targetOrigin" -ForegroundColor Yellow
    git remote set-url origin $targetOrigin
} else {
    Write-Host "[Remote] Origin remote verified: $originUrl" -ForegroundColor Green
}

# ── 2. Handle -Bundle or -Branch Merge ─────────────────────────────────────────
if ($Bundle -and $Branch) {
    Write-Error "Cannot specify both -Bundle and -Branch. Please specify only one target."
    exit 1
}

if ($Bundle) {
    # Check if bundle path needs .txt extension resolution or stripping
    if (-not (Test-Path $Bundle) -and (Test-Path "$Bundle.txt")) {
        $Bundle = "$Bundle.txt"
    }

    if (-not (Test-Path $Bundle)) {
        Write-Error "Bundle file not found: $Bundle"
        exit 1
    }

    $bundleFullPath = (Resolve-Path $Bundle).Path

    # If the bundle ends in .txt (e.g., download artifact), rename to .bundle
    if ($bundleFullPath.EndsWith(".txt", [System.StringComparison]::OrdinalIgnoreCase)) {
        $renamed = $bundleFullPath.Substring(0, $bundleFullPath.Length - 4)
        if (-not $renamed.EndsWith(".bundle", [System.StringComparison]::OrdinalIgnoreCase)) {
            $renamed = "$renamed.bundle"
        }
        Write-Host "[Bundle] Renaming bundle artifact:" -ForegroundColor Yellow
        Write-Host "         $bundleFullPath -> $renamed" -ForegroundColor Yellow
        Move-Item -Path $bundleFullPath -Destination $renamed -Force
        $bundleFullPath = $renamed
    }

    # Verify bundle integrity
    Write-Host "[Bundle] Verifying git bundle integrity: $bundleFullPath..." -ForegroundColor Cyan
    git bundle verify $bundleFullPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Git bundle verification failed for '$bundleFullPath'!"
        exit 1
    }

    # Extract heads from bundle
    $heads = git bundle list-heads $bundleFullPath
    if (-not $heads) {
        Write-Error "No branch refs found in bundle '$bundleFullPath'!"
        exit 1
    }

    # Extract first branch ref
    $refLine = ($heads | Where-Object { $_ -match 'refs/heads/' } | Select-Object -First 1)
    if (-not $refLine) {
        $refLine = $heads[0]
    }
    $ref = (-split $refLine.Trim())[1]
    $bundleBranch = $ref -replace '^refs/heads/', ''

    Write-Host "[Bundle] Fetching ref '$ref' ($bundleBranch)..." -ForegroundColor Cyan
    git fetch $bundleFullPath "$ref"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to fetch from bundle '$bundleFullPath'."
        exit 1
    }

    Write-Host "[Git] Checking out master..." -ForegroundColor Cyan
    git checkout master
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to checkout master."
        exit 1
    }

    Write-Host "[Git] Merging bundle ref into master with --no-ff..." -ForegroundColor Cyan
    git merge FETCH_HEAD --no-ff -m "Merge bundle '$bundleBranch' into master"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Merge conflict or error while merging bundle into master!"
        exit 1
    }
}
elseif ($Branch) {
    Write-Host "[Git] Checking out master..." -ForegroundColor Cyan
    git checkout master
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to checkout master."
        exit 1
    }

    Write-Host "[Git] Merging branch '$Branch' into master with --no-ff..." -ForegroundColor Cyan
    git merge $Branch --no-ff -m "Merge branch '$Branch' into master"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Merge conflict or error while merging branch '$Branch' into master!"
        exit 1
    }
}
else {
    $currentBranch = (git branch --show-current).Trim()
    if ($currentBranch -ne "master") {
        Write-Host "[Git] Switching from '$currentBranch' to master..." -ForegroundColor Cyan
        git checkout master
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to checkout master."
            exit 1
        }
    } else {
        Write-Host "[Git] Already on master branch." -ForegroundColor Green
    }
}

# ── 3. Run Pre-Ship Validation Suite ──────────────────────────────────────────
Write-Host ""
Write-Host "── Running Pre-Ship Verification Suite ──────────────────────────" -ForegroundColor Cyan

Write-Host "[Verify 1/3] Checking benchmark status consistency..." -ForegroundColor Yellow
python scripts/generate_benchmark_status.py --check
if ($LASTEXITCODE -ne 0) {
    Write-Error "Benchmark status check failed! Please run 'python scripts/generate_benchmark_status.py' to update benchmark-status.json."
    exit 1
}
Write-Host "             Benchmark status verified: PASS" -ForegroundColor Green

Write-Host "[Verify 2/3] Checking frontend TypeScript types..." -ForegroundColor Yellow
npm --prefix frontend run type-check
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend type-check failed!"
    exit 1
}
Write-Host "             TypeScript type check: PASS" -ForegroundColor Green

Write-Host "[Verify 3/3] Running frontend Vitest unit test suite..." -ForegroundColor Yellow
npm --prefix frontend test
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend unit tests failed!"
    exit 1
}
Write-Host "             Frontend unit tests: PASS" -ForegroundColor Green

# ── 4. Push Master to Origin ──────────────────────────────────────────────────
Write-Host ""
Write-Host "── Shipping to Remote ───────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Pushing master branch to origin..." -ForegroundColor Yellow
git push origin master
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to push master to origin."
    exit 1
}

# Determine GitHub Actions URL
$activeRemote = (git remote get-url origin 2>$null)
$repoPath = "omarmomen1/suspentionlab"
if ($activeRemote -match "github\.com[:/]([^/]+/[^/\.]+?)(\.git)?$") {
    $repoPath = $Matches[1]
}
$actionsUrl = "https://github.com/$repoPath/actions"

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host " Master successfully shipped!" -ForegroundColor Green
Write-Host " Production CI/CD workflow triggered on GitHub Actions." -ForegroundColor Green
Write-Host " Watch live deployment at: $actionsUrl" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Green
