# Run after: gh auth login
# Creates a PRIVATE GitHub repo and pushes the current preli branch.

$ErrorActionPreference = "Stop"
$repoName = "gridwise-llm-preli"

gh auth status
gh repo create $repoName --private --source=. --remote=origin --disable-wiki --disable-issues
git push -u origin preli
gh repo edit $repoName --default-branch preli

Write-Host ""
Write-Host "Private repo:"
gh repo view $repoName --json url -q .url
Write-Host "After 11:00 PM make it public:"
Write-Host "  gh repo edit $repoName --visibility public --accept-visibility-change-consequences"
Write-Host ""
Write-Host "Docker fallback tag after GitHub Actions:"
Write-Host "  ghcr.io/<your-user>/gridwise-llm-preli:preli"
Write-Host "Live API: connect this repo to Render using render.yaml and set GROQ_API_KEY."
