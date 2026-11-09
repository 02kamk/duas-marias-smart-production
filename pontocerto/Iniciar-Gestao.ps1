param([int]$Porta = 8000, [string]$Python = '')
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $candidates = @(
        (Join-Path $env:USERPROFILE 'Documents/Codex/venvs/pc/Scripts/python.exe'),
        (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')
    )
    $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'Python do projeto nao encontrado. Informe -Python com o caminho do ambiente que ja roda o Ponto Certo.'
}
Write-Host "Inspecao original: http://127.0.0.1:$Porta/"
Write-Host "Gestao adicional: http://127.0.0.1:$Porta/gestao"
Write-Host 'Mantenha este terminal aberto. Ctrl+C encerra o servidor.'
& $Python -u (Join-Path $PSScriptRoot 'scripts/07_rodar_com_gestao.py') --porta $Porta
exit $LASTEXITCODE
