@echo off
echo ============================================
echo    VozIA Desktop - Build
echo ============================================
echo.

:: Verifica se dotnet esta instalado
where dotnet >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERRO] .NET SDK nao encontrado!
    echo Baixe em: https://dotnet.microsoft.com/download/dotnet/8.0
    pause
    exit /b 1
)

echo [1/3] Restaurando pacotes...
dotnet restore
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha ao restaurar pacotes.
    pause
    exit /b 1
)

echo.
echo [2/3] Compilando em Release...
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o .\publish
if %ERRORLEVEL% neq 0 (
    echo [ERRO] Falha na compilacao.
    pause
    exit /b 1
)

echo.
echo [3/3] Copiando assets...
if not exist .\publish\Assets mkdir .\publish\Assets
copy /Y .\Assets\icon.png .\publish\Assets\ >nul 2>nul

echo.
echo ============================================
echo    BUILD CONCLUIDO!
echo    Executavel em: .\publish\VozIA.exe
echo ============================================
echo.
pause
