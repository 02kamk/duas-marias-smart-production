param([int]$Porta=8000,[string]$Python='')
$ErrorActionPreference='Stop'
if(-not $Python){
    $candidates=@(
        (Join-Path $env:USERPROFILE 'Documents/Codex/venvs/pc/Scripts/python.exe'),
        (Join-Path $PSScriptRoot '.venv/Scripts/python.exe')
    )
    $Python=$candidates | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
}
if(-not $Python -or -not(Test-Path -LiteralPath $Python)){
    throw 'Informe -Python com o ambiente que ja executa o Ponto Certo.'
}
& $Python -u (Join-Path $PSScriptRoot 'scripts/11_rodar_completo.py') --porta $Porta
exit $LASTEXITCODE
