# =============================================================================
#  Run the MOSYS tool ONLINE against the live STAAMP_DB (reads are LIVE).
#  Launch from the project root on the RDP where DSN=STAAMP_DB is reachable:
#
#      .\scripts\run_online.ps1
#
#  Reads:  LIVE (offline demo is forced off below).
#  Writes: OFF by default. They stay dry-run until you explicitly opt in AND
#          have passed the supervised one-row smoke test (see PHASE B below).
# =============================================================================

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# --- Read side (safe) --------------------------------------------------------
$env:MOSYS_OFFLINE_DEMO     = ''      # OFF -> serve REAL data from STAAMP_DB
$env:FLASK_DEBUG            = ''      # OFF -> no Werkzeug RCE console / reloader
$env:MOSYS_DB_CONNECT_TIMEOUT = '15' # fail fast if the DSN is unreachable
# Volume guard (default shown; raise only if you know the selection is safe):
# $env:MOSYS_SPC_MAX_ROWS   = '50000'

# --- PHASE B: production writes -----------------------------------------------
# ENABLED. The supervised one-row smoke test (scripts\mosys_cli.py --commit)
# round-tripped and verified on 2026-07-03, so /spc-tweaks "Apply" now performs
# REAL UPDATEs on STAAMP_DB through the safe-write path (journal -> atomic ->
# rowcount==1 -> post-commit verify -> rollback on any anomaly).
# The config.py DEFAULT remains fail-closed; writes are opted in HERE, per-launch.
# To run read-only again, comment this single line out.
$env:MOSYS_WRITE_ENABLED = 'true'

Write-Host "MOSYS online server" -ForegroundColor Cyan
Write-Host ("  reads : LIVE (STAAMP_DB)")
Write-Host ("  writes: " + $(if ($env:MOSYS_WRITE_ENABLED) { "ENABLED (LIVE UPDATES)" } else { "dry-run (disabled)" }))
Write-Host ("  debug : " + $(if ($env:FLASK_DEBUG) { "on" } else { "off" }))
Write-Host ""

& "$root\venv\Scripts\python.exe" "$root\app.py"
