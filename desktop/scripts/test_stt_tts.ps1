param(
  [string]$WhisperExe = "C:\\tools\\whisper\\whisper.exe",
  [string]$ModelPath = "C:\\tools\\whisper\\ggml-large-v3.bin",
  [string]$Wav = "C:\\samples\\sample.wav",
  [string]$Server = "http://127.0.0.1:8000"
)

Write-Host "Transcription avec whisper.cpp..."
& $WhisperExe --model $ModelPath -f $Wav -l fr --no-timestamps --output-txt --output-dir $env:TEMP | Out-Null
$stem = [System.IO.Path]::GetFileNameWithoutExtension($Wav)
$txtPath = Join-Path $env:TEMP ("$stem.txt")
$text = Get-Content -Raw $txtPath
Write-Host "Texte:" $text

Write-Host "Envoi au serveur..."
$resp = Invoke-RestMethod -Uri "$Server/llm/infer" -Method Post -ContentType 'application/json' -Body (@{ prompt=$text } | ConvertTo-Json)
Write-Host "Réponse:" ($resp | ConvertTo-Json -Depth 4)

Write-Host "Synthèse vocale locale..."
tts --text "Bonjour, ceci est un test" --model_name "tts_models/fr/css10/vits" --out_path "$env:TEMP\ivy_tts.wav"
Start-Process "$env:TEMP\ivy_tts.wav"

