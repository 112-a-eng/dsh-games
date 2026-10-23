# 打包 112账务（Windows 桌面记账软件）
# 依赖：Python 3.14（py 启动器）+ PyInstaller      安装：py -m pip install pyinstaller
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\build_ledger_exe.ps1              # 默认 onedir（启动最快）
#   powershell -ExecutionPolicy Bypass -File .\build_ledger_exe.ps1 -Mode onefile   # 单文件
#   powershell -ExecutionPolicy Bypass -File .\build_ledger_exe.ps1 -NoTest          # 跳过自测

param(
    [ValidateSet('onedir', 'onefile')][string]$Mode = 'onedir',
    [switch]$NoTest
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $NoTest) {
    Write-Host '[0/4] 账务内核自测 ...'
    & py -X utf8 -m ledger --self-test
    if ($LASTEXITCODE -ne 0) { throw '自测未通过，已中止打包' }
}

Write-Host '[1/4] 生成图标 ledger_icon.ico / ledger_icon.png ...'
& py -X utf8 "$root\.build\make_ledger_icon.py" "$root\ledger_icon.ico" "$root\ledger_icon.png"

# 裁掉用不到的标准库。注意：本程序依赖 sqlite3 与 decimal，绝不能排除。
$excludes = @(
    'unittest', 'pydoc', 'doctest', 'difflib', 'email', 'http', 'urllib', 'xml', 'html',
    'multiprocessing', 'asyncio', 'concurrent', 'tarfile', 'setuptools', 'pkg_resources',
    'distutils', 'lib2to3', 'idlelib', 'turtle', 'turtledemo', 'curses', 'test', 'venv',
    'ensurepip', 'numpy', 'PIL', 'pandas', 'matplotlib', 'scipy', 'tkinter.test', 'tkinter.tix'
)
$excludeArgs = @()
foreach ($m in $excludes) { $excludeArgs += @('--exclude-module', $m) }

Write-Host "[2/4] 打包（模式：$Mode）..."
$common = @(
    '--windowed', '--name', '112账务',
    '--icon', "$root\ledger_icon.ico",
    '--add-data', "$root\ledger_icon.png;.",
    '--distpath', "$root\dist",
    '--workpath', "$root\.build\work_ledger",
    '--specpath', "$root\.build",
    '--noconfirm'
) + $excludeArgs
if ($Mode -eq 'onefile') { $common = @('--onefile') + $common } else { $common = @('--onedir') + $common }
$common += "$root\ledger_gui.py"
& py -m PyInstaller @common
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失败' }

Write-Host ''
if ($Mode -eq 'onefile') {
    $exe = Get-Item "$root\dist\112账务.exe"
    Write-Host ("[3/4] 完成: {0}  ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB)) -ForegroundColor Green
} else {
    $dir = Get-Item "$root\dist\112账务"
    $size = (Get-ChildItem $dir.FullName -Recurse -File | Measure-Object Length -Sum).Sum
    Write-Host ("[3/4] 完成: {0}\112账务.exe  ({1:N1} MB，整个文件夹一起移动)" -f $dir.FullName, ($size / 1MB)) -ForegroundColor Green
}
Write-Host '[4/4] 账套文件默认保存在「文档\112账务\账套.db」，可用 --db 指定其他位置。'