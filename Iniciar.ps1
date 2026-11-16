param([int]$Porta = 8000, [switch]$Rede, [string]$Python = '')
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    # .venv do projeto primeiro; o do TEMP serve quando o caminho do OneDrive é longo demais.
    $candidatos = @(
        (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'),
        (Join-Path $env:TEMP 'duas-marias-venv/Scripts/python.exe')
    )
    $Python = $candidatos | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw "Ambiente Python não encontrado. Siga a seção 'Instalar' do README ou informe -Python com o caminho do python.exe."
}
$argumentos = @('-u', (Join-Path $PSScriptRoot 'scripts/rodar.py'), '--porta', $Porta, '--abrir')
if ($Rede) { $argumentos += '--rede' }
& $Python @argumentos
exit $LASTEXITCODE
