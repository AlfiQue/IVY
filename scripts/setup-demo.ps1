# Ce script prépare un jeu de données RAG minimal et une mise à jour Desktop factice
# Usage: powershell -ExecutionPolicy Bypass -File scripts\setup-demo.ps1

param(
  [string]$Server = "http://127.0.0.1:8000",
  [string]$Version = "0.1.1"
)

Write-Host "[RAG] Création de fichiers de démonstration..."
New-Item -ItemType Directory -Force app\data\knowledge | Out-Null
New-Item -ItemType Directory -Force app\data\inbox | Out-Null

Set-Content app\data\knowledge\note-paris.txt "Bonjour Paris. La météo est clémente aujourd’hui près de la Tour Eiffel." -Encoding UTF8
Set-Content app\data\knowledge\gpu.txt "GPU RTX 4070 Ti. CUDA/cuBLAS activés. Mémoire 12GB." -Encoding UTF8

Write-Host "[RAG] Reindex (full)..."
try {
  Invoke-RestMethod -Uri "$Server/rag/reindex" -Method Post -ContentType 'application/json' -Body '{"full":true}' | Out-Null
  Write-Host "[RAG] OK"
} catch {
  Write-Warning "Impossible d'appeler /rag/reindex (serveur non démarré ?). Les fichiers sont en place."
}

Write-Host "[UPDATE] Préparation de updates/desktop..."
New-Item -ItemType Directory -Force updates\desktop | Out-Null
$msi = Join-Path updates\desktop ("ivy-desktop-$Version.msi")
if (-not (Test-Path $msi)) {
  # crée un MSI factice vide (hash SHA256 connu après calcul)
  New-Item -ItemType File $msi | Out-Null
}

$hash = (Get-FileHash -Algorithm SHA256 $msi).Hash
$manifest = @{
  version = $Version
  url     = "$Server/updates/desktop/ivy-desktop-$Version.msi"
  sha256  = $hash
  notes   = "Mise à jour de démonstration"
} | ConvertTo-Json
Set-Content updates\desktop\manifest.json $manifest -Encoding UTF8
Write-Host "[UPDATE] manifest.json écrit. SHA256=$hash"

Write-Host "Terminé. Vérifiez: $Server/updates/desktop/manifest.json"

