[CmdletBinding()]
param(
  [string]$RepoPath = "."
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RepoPath)) {
  throw "RepoPath does not exist: $RepoPath"
}

$resolved = (Resolve-Path -LiteralPath $RepoPath).Path
$skip = @(
  ".git",
  ".claude",
  "node_modules",
  "dist",
  "build",
  "__pycache__",
  ".venv",
  "venv"
)

function Infer-SkillName {
  param([string]$DirectoryName)

  $name = $DirectoryName.ToLowerInvariant()
  switch ($name) {
    { $_ -in @("web", "frontend", "client", "ui") } { return "frontend" }
    { $_ -in @("src", "core", "domain", "engine", "backend", "api") } { return "core" }
    { $_ -in @("tests", "test", "__tests__", "e2e", "spec") } { return "testing" }
    { $_ -in @("data", "ingestion", "db", "database", "content") } { return "data" }
    default { return $name -replace "[^a-z0-9\-]+", "-" }
  }
}

Write-Host "Suggested ZoneMap entries for $resolved"
Write-Host ""

$dirs = Get-ChildItem -LiteralPath $resolved -Directory |
  Where-Object { $skip -notcontains $_.Name } |
  Sort-Object Name

if (-not $dirs) {
  Write-Host "No candidate directories found."
  exit 0
}

foreach ($dir in $dirs) {
  $skill = Infer-SkillName -DirectoryName $dir.Name
  $description = "$($dir.Name) zone"
  Write-Host "$($dir.Name)|$skill|$description"
}

