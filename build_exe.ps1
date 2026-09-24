# 重新打包 Tetris.exe（单文件 / 无控制台窗口 / 带图标）
# 依赖：Python 3.14（py 启动器）+ PyInstaller       安装：py -m pip install pyinstaller
# 用法：右键“使用 PowerShell 运行”，或在终端执行  .\build_exe.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host '[1/2] 生成图标 tetris.ico ...'
& py -X utf8 "$root\.build\make_icon.py" "$root\tetris.ico"

Write-Host '[2/2] 打包 Tetris.exe ...'
& py -m PyInstaller --onefile --windowed --name Tetris `
    --icon "$root\tetris.ico" `
    --distpath "$root\dist" `
    --workpath "$root\.build\work" `
    --specpath "$root\.build" `
    --noconfirm "$root\tetris.py"

Write-Host ''
Write-Host "完成: $root\dist\Tetris.exe"
