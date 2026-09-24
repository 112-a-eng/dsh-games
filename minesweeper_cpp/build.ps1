# 一键编译扫雷（MSVC x64 / C++20 / 静态链接 CRT）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\build.ps1
#   powershell -ExecutionPolicy Bypass -File .\build.ps1 -Clean     # 先清理
#
# 依赖：Visual Studio 2022/2026（需勾选"使用 C++ 的桌面开发"）
# 产物：build\Minesweeper.exe（GUI）与 build\tests.exe（单元测试）

param([switch]$Clean)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# ---- 定位 MSVC ----
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw '找不到 vswhere.exe，请先安装 Visual Studio（含 C++ 桌面开发负载）'
}
$vsPath = & $vswhere -latest -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    -property installationPath
if (-not $vsPath) { throw '找不到 MSVC 工具集（x64）' }
$vcvars = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $vcvars)) { throw "找不到 $vcvars" }
Write-Host "使用工具链: $vsPath" -ForegroundColor DarkGray

if ($Clean) {
    Write-Host '清理 build 目录 ...' -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$root\build" -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path "$root\build\obj_gui", "$root\build\obj_tests" | Out-Null

# 编译参数：/utf-8 让 MSVC 按 UTF-8 解析源码（源码里有中文注释），/MT 静态链接 CRT
$flags = '/nologo /utf-8 /std:c++20 /EHsc /W4 /O2 /MT'
$defs = '/DUNICODE /D_UNICODE'
$libs = 'user32.lib gdi32.lib advapi32.lib'

Write-Host '[1/3] 编译核心逻辑 + 单元测试 ...' -ForegroundColor Cyan
$step1 = "call `"$vcvars`" >nul && cd /d `"$root`" && " +
         "cl $flags /Fe:build\tests.exe /Fo:build\obj_tests\ src\tests.cpp src\game.cpp /link /SUBSYSTEM:CONSOLE"
cmd /c $step1
if ($LASTEXITCODE -ne 0) { throw '编译单元测试失败' }

Write-Host '[2/3] 编译资源 + 主程序 ...' -ForegroundColor Cyan
$step2 = "call `"$vcvars`" >nul && cd /d `"$root`" && " +
         "rc /nologo /fo build\app.res res\app.rc && " +
         "cl $flags $defs /Fe:build\Minesweeper.exe /Fo:build\obj_gui\ src\main.cpp src\game.cpp " +
         "/link /SUBSYSTEM:WINDOWS $libs build\app.res"
cmd /c $step2
if ($LASTEXITCODE -ne 0) { throw '编译主程序失败' }

Write-Host '[3/3] 运行核心逻辑自测 ...' -ForegroundColor Cyan
Write-Host ''
& "$root\build\tests.exe" -v
if ($LASTEXITCODE -ne 0) { throw '自测未通过' }

Write-Host ''
$exe = Get-Item "$root\build\Minesweeper.exe"
$test = Get-Item "$root\build\tests.exe"
Write-Host ('编译完成：' ) -NoNewline
Write-Host $exe.FullName -ForegroundColor Green
Write-Host ("  Minesweeper.exe  {0:N1} KB" -f ($exe.Length / 1KB))
Write-Host ("  tests.exe        {0:N1} KB" -f ($test.Length / 1KB))
