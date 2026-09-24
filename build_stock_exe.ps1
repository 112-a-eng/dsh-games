# 重新打包股票模拟交易游戏
# 依赖：Python 3.14（py 启动器）+ PyInstaller      安装：py -m pip install pyinstaller
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\build_stock_exe.ps1              # 默认 onedir（启动最快）
#   powershell -ExecutionPolicy Bypass -File .\build_stock_exe.ps1 -Mode onefile  # 单文件（启动慢 2 秒左右）
#   powershell -ExecutionPolicy Bypass -File .\build_stock_exe.ps1 -NoTest       # 跳过自测
#
# onedir 与 onefile 的区别：
#   onedir ：产出 dist\StockGame\ 文件夹（exe + _internal），启动约 0.4 秒，整个文件夹要一起移动
#   onefile：产出单个 dist\StockGame.exe，启动要先把 12MB 自解压到临时目录，约 2~3 秒

param(
    [ValidateSet('onedir', 'onefile')][string]$Mode = 'onedir',
    [switch]$NoTest
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $NoTest) {
    Write-Host '[0/4] 交易内核自测 ...'
    & py -X utf8 -m stock_game --self-test
    if ($LASTEXITCODE -ne 0) { throw '自测未通过，已中止打包' }
}

Write-Host '[1/4] 生成图标 stock_icon.ico / stock_icon.png ...'
& py -X utf8 "$root\.build\make_stock_icon.py" "$root\stock_icon.ico" "$root\stock_icon.png"

# 裁掉用不到的标准库：tkinter 桌面程序不需要网络、XML、邮件、多进程这些，
# 打包体积能小一截，onefile 的自解压也更快。
$excludes = @(
    'unittest', 'pydoc', 'doctest', 'difflib', 'email', 'http', 'urllib', 'xml', 'html',
    'sqlite3', 'bz2', 'lzma', 'decimal', 'fractions', 'statistics', 'multiprocessing',
    'asyncio', 'concurrent', 'tarfile', 'setuptools', 'pkg_resources', 'distutils',
    'lib2to3', 'idlelib', 'turtle', 'turtledemo', 'curses', 'test', 'venv', 'ensurepip',
    'ssl', 'socket', 'select', 'selectors', 'numpy', 'PIL', 'pandas', 'matplotlib',
    'scipy', 'tkinter.test', 'tkinter.tix'
)
$excludeArgs = @()
foreach ($m in $excludes) { $excludeArgs += @('--exclude-module', $m) }

Write-Host "[2/4] 打包（模式：$Mode）..."
$common = @(
    '--windowed', '--name', 'StockGame',
    '--icon', "$root\stock_icon.ico",
    '--add-data', "$root\stock_icon.png;.",
    '--distpath', "$root\dist",
    '--workpath', "$root\.build\work_stock",
    '--specpath', "$root\.build",
    '--noconfirm'
) + $excludeArgs
if ($Mode -eq 'onefile') { $common = @('--onefile') + $common } else { $common = @('--onedir') + $common }
$common += "$root\stock_game_gui.py"
& py -m PyInstaller @common
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }

Write-Host ''
if ($Mode -eq 'onefile') {
    $exe = Get-Item "$root\dist\StockGame.exe"
    Write-Host ("[3/4] 完成: {0}  ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB)) -ForegroundColor Green
} else {
    $dir = Get-Item "$root\dist\StockGame"
    $size = (Get-ChildItem $dir.FullName -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("[3/4] 完成: {0}\StockGame.exe  ({1:N1} MB，整个文件夹一起移动)" -f $dir.FullName, ($size / 1MB)) -ForegroundColor Green
}
Write-Host '[4/4] 建议用 -Mode onefile 时把 exe 单独拷走；onedir 模式请保留 _internal 目录。'
