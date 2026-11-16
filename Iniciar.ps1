param([int]$Porta = 8000, [switch]$Rede, [string]$Python = '')
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $Python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Ambiente .venv não encontrado. Siga a seção 'Instalar' do README ou informe -Python com o caminho do python.exe."
}
$argumentos = @('-u', (Join-Path $PSScriptRoot 'scripts/rodar.py'), '--porta', $Porta, '--abrir')
if ($Rede) { $argumentos += '--rede' }
& $Python @argumentos
exit $LASTEXITCODE
