# 安装 Android SDK（只装动手工构建 APK 需要的最小集合，不装 Android Studio）
#   cmdline-tools  -> sdkmanager
#   platforms;android-34 -> android.jar（编译用）
#   build-tools;34.0.0   -> aapt2 / d8 / zipalign / apksigner（打包签名用）
$ErrorActionPreference = 'Continue'
$sdk = 'D:\android-sdk'
$jdk = 'C:\Program Files\Android\openjdk\jdk-21.0.8'
$url = 'https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip'
$zip = Join-Path $env:TEMP 'cmdline-tools.zip'

$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk

Write-Host "== 1) 下载 cmdline-tools =="
New-Item -ItemType Directory -Force -Path $sdk | Out-Null
if (-not (Test-Path $zip) -or (Get-Item $zip).Length -lt 100MB) {
    & curl.exe -L --fail --silent --show-error -o $zip $url
    if ($LASTEXITCODE -ne 0) { throw "下载失败（exit $LASTEXITCODE）" }
}
Write-Host ("   已下载 {0:N1} MB" -f ((Get-Item $zip).Length / 1MB))

Write-Host "== 2) 解压到 $sdk\cmdline-tools\latest =="
$tmp = Join-Path $sdk '_unzip'
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$latest = Join-Path $sdk 'cmdline-tools\latest'
Remove-Item -Recurse -Force $latest -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Split-Path $latest) | Out-Null
Move-Item (Join-Path $tmp 'cmdline-tools') $latest
Remove-Item -Recurse -Force $tmp
Write-Host "   sdkmanager: $(Test-Path (Join-Path $latest 'bin\sdkmanager.bat'))"

Write-Host "== 3) 接受许可 =="
$sdkmanager = Join-Path $latest 'bin\sdkmanager.bat'
('y' * 40) -split '' | Where-Object { $_ } | & $sdkmanager --sdk_root=$sdk --licenses 2>&1 |
    Select-Object -Last 3

Write-Host "== 4) 安装 platform + build-tools + platform-tools =="
& $sdkmanager --sdk_root=$sdk --install 'platform-tools' 'platforms;android-34' 'build-tools;34.0.0' 2>&1 |
    Select-Object -Last 6

Write-Host "== 5) 校验关键工具 =="
$checks = @(
    "$sdk\platforms\android-34\android.jar",
    "$sdk\build-tools\34.0.0\aapt2.exe",
    "$sdk\build-tools\34.0.0\d8.bat",
    "$sdk\build-tools\34.0.0\zipalign.exe",
    "$sdk\build-tools\34.0.0\apksigner.bat",
    "$sdk\platform-tools\adb.exe"
)
foreach ($c in $checks) { "   {0,-58} {1}" -f $c.Replace($sdk, '<sdk>'), (Test-Path $c) }
