[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$TargetRepoPath,

  [string]$ProjectName = "Project Name",
  [string]$ProjectSummary = "One-line project summary.",

  [string[]]$ZoneMap = @(
    "src|core|Core domain logic",
    "web|frontend|Frontend application",
    "tests|testing|Verification workflows"
  ),

  [string]$BuildCommand = "npm run build",
  [string]$TestCommand = "npm test",
  [string]$LintCommand = "npm run lint"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-ToTitleCase {
  param([Parameter(Mandatory = $true)][string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) { return $Value }

  $parts = $Value -split "[-_ ]+"
  $textInfo = (Get-Culture).TextInfo
  $mapped = foreach ($part in $parts) {
    if ([string]::IsNullOrWhiteSpace($part)) { continue }
    $textInfo.ToTitleCase($part.ToLowerInvariant())
  }
  return ($mapped -join " ")
}

if (-not (Test-Path -LiteralPath $TargetRepoPath)) {
  throw "TargetRepoPath does not exist: $TargetRepoPath"
}

$resolvedTarget = (Resolve-Path -LiteralPath $TargetRepoPath).Path
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$templateRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..\templates")).Path
$targetClaude = Join-Path $resolvedTarget ".claude"

Copy-Item -LiteralPath (Join-Path $templateRoot "AGENTS.md") -Destination (Join-Path $resolvedTarget "AGENTS.md") -Force
Copy-Item -LiteralPath (Join-Path $templateRoot ".claude") -Destination $resolvedTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $templateRoot "ZONE-README-template.md") -Destination (Join-Path $targetClaude "ZONE-README-template.md") -Force

$zoneRows = New-Object System.Collections.Generic.List[string]
$seenSkills = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$zoneTemplatePath = Join-Path $targetClaude "skills\soft\_zone-template.md"
$zoneTemplate = Get-Content -LiteralPath $zoneTemplatePath -Raw

foreach ($entry in $ZoneMap) {
  $parts = $entry -split "\|", 3
  if ($parts.Count -lt 2) {
    throw "Invalid ZoneMap entry '$entry'. Use '<path>|<skill>|<description>'."
  }

  $zonePath = $parts[0].Trim()
  $skillName = $parts[1].Trim()
  $zoneDescription = if ($parts.Count -eq 3 -and -not [string]::IsNullOrWhiteSpace($parts[2])) {
    $parts[2].Trim()
  } else {
    "$skillName zone"
  }

  if ([string]::IsNullOrWhiteSpace($zonePath) -or [string]::IsNullOrWhiteSpace($skillName)) {
    throw "Invalid ZoneMap entry '$entry'. Path and skill cannot be empty."
  }

  $zoneRows.Add("| ``$zonePath/**`` | ``.claude/skills/soft/$skillName.md`` | $zoneDescription |")

  if ($skillName -ieq "testing") {
    continue
  }

  if ($seenSkills.Add($skillName)) {
    $zoneFilePath = Join-Path $targetClaude "skills\soft\$skillName.md"
    if (-not (Test-Path -LiteralPath $zoneFilePath)) {
      $zoneFile = $zoneTemplate
      $zoneFile = $zoneFile.Replace("{{ZONE_NAME}}", (Convert-ToTitleCase -Value $skillName))
      $zoneFile = $zoneFile.Replace("{{ZONE_PATH}}", $zonePath)
      $zoneFile = $zoneFile.Replace("{{ZONE_DESCRIPTION}}", $zoneDescription)
      $zoneFile = $zoneFile.Replace("{{FILL_FROM_REPO_SCAN}}", "<annotated files>")
      $zoneFile = $zoneFile.Replace("{{CONVENTION_1}}", "Match existing boundaries and naming patterns.")
      $zoneFile = $zoneFile.Replace("{{CONVENTION_2}}", "Favor small changes with explicit validation.")
      $zoneFile = $zoneFile.Replace("{{HARD_SKILLS}}", "<add hard skill references>")
      Set-Content -LiteralPath $zoneFilePath -Value $zoneFile
    }
  }
}

if ($zoneRows.Count -eq 0) {
  throw "ZoneMap cannot be empty."
}

$claudePath = Join-Path $targetClaude "CLAUDE.md"
$claudeContent = Get-Content -LiteralPath $claudePath -Raw
$claudeContent = $claudeContent.Replace("{{PROJECT_NAME}}", $ProjectName)
$claudeContent = $claudeContent.Replace("{{PROJECT_SUMMARY}}", $ProjectSummary)
$claudeContent = $claudeContent.Replace("{{ZONE_DISPATCH_ROWS}}", ($zoneRows -join "`r`n"))
$claudeContent = $claudeContent.Replace("{{BUILD_COMMAND}}", $BuildCommand)
$claudeContent = $claudeContent.Replace("{{TEST_COMMAND}}", $TestCommand)
$claudeContent = $claudeContent.Replace("{{LINT_COMMAND}}", $LintCommand)
Set-Content -LiteralPath $claudePath -Value $claudeContent

$qualityPath = Join-Path $targetClaude "brain\QUALITY.md"
$qualityContent = Get-Content -LiteralPath $qualityPath -Raw
$qualityContent = $qualityContent.Replace("{{BUILD_COMMAND}}", $BuildCommand)
$qualityContent = $qualityContent.Replace("{{TEST_COMMAND}}", $TestCommand)
$qualityContent = $qualityContent.Replace("{{LINT_COMMAND}}", $LintCommand)
Set-Content -LiteralPath $qualityPath -Value $qualityContent

Write-Host ""
Write-Host "Abstracted template was applied to: $resolvedTarget"
Write-Host "Generated zone dispatch rows:"
foreach ($row in $zoneRows) {
  Write-Host "  $row"
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Fill each generated soft skill file map from the real repo tree."
Write-Host "2. Add hard skills for recurring workflows."
Write-Host "3. Add command dispatchers that target soft + hard skills."
Write-Host "4. Add agent-context breadcrumbs to each zone README."
