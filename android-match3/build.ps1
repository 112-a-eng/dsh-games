# 手工构建「宝石三消」的 APK —— 不用 Gradle / AGP / AndroidX，**不需要任何 Maven 依赖**
#
# 流程：javac -> aapt2 compile/link -> jar -> d8 -> 塞进 APK -> zipalign -> apksigner
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\build.ps1              # 跑自测并打包
#   powershell -ExecutionPolicy Bypass -File .\build.ps1 -SkipTest    # 跳过自测
#
# 依赖：JDK（自带 javac/keytool/jar）+ Android SDK 的 platform-34 与 build-tools;36.1.0
#       （用 ..\.build\setup_android_sdk.ps1 安装）

param(
    [string]$Sdk = 'D:\android-sdk',
    [string]$Jdk = 'C:\Program Files\Android\openjdk\jdk-21.0.8',
    # 注意：build-tools 34.0.0 自带 d8 处理 enum 类会崩（R8 的内部 NPE），改用 36.1.0
    [string]$BuildToolsVersion = '36.1.0',
    [string]$PlatformVersion = 'android-34',
    [switch]$SkipTest,
    [string]$OutDir = '.'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$buildTools = Join-Path $Sdk "build-tools\$BuildToolsVersion"
$androidJar = Join-Path $Sdk "platforms\$PlatformVersion\android.jar"
$build = Join-Path $root 'build'
$dist = Join-Path $root $OutDir

foreach ($tool in @("$Jdk\bin\javac.exe", "$buildTools\aapt2.exe", "$buildTools\d8.bat",
                    "$buildTools\zipalign.exe", "$buildTools\apksigner.bat", $androidJar)) {
    if (-not (Test-Path $tool)) { throw "缺少工具：$tool（先跑 ..\.build\setup_android_sdk.ps1）" }
}

$env:JAVA_HOME = $Jdk
if (Test-Path "$build") { Remove-Item -Recurse -Force "$build" }
New-Item -ItemType Directory -Force -Path "$build\classes", "$build\dex", $dist | Out-Null

# ---------------------------------------------------------------- 1) 逻辑自测
if (-not $SkipTest) {
    Write-Host '[1/6] 逻辑自测（纯 Java，不需要 Android）...' -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path "$build\test" | Out-Null
    & "$Jdk\bin\javac.exe" -encoding UTF-8 -d "$build\test" `
        src\com\dsh\match3\Board.java src\com\dsh\match3\BoardTest.java
    if ($LASTEXITCODE -ne 0) { throw '自测代码编译失败' }
    & "$Jdk\bin\java.exe" '-Dstdout.encoding=UTF-8' -cp "$build\test" com.dsh.match3.BoardTest
    if ($LASTEXITCODE -ne 0) { throw '逻辑自测未通过，已中止打包' }
    Write-Host ''
} else {
    Write-Host '[1/6] 跳过自测' -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 2) 资源
Write-Host '[2/6] aapt2 compile（编译 res）...' -ForegroundColor Cyan
& "$buildTools\aapt2.exe" compile --dir res -o "$build\res.zip"
if ($LASTEXITCODE -ne 0) { throw 'aapt2 compile 失败' }

Write-Host '[3/6] aapt2 link（生成 R.java + 未签名 APK）...' -ForegroundColor Cyan
& "$buildTools\aapt2.exe" link `
    -o "$build\app-unsigned.apk" `
    -I $androidJar `
    --manifest AndroidManifest.xml `
    --java "$build\gen" `
    "$build\res.zip"
if ($LASTEXITCODE -ne 0) { throw 'aapt2 link 失败' }

# ---------------------------------------------------------------- 3) Java
Write-Host '[4/6] javac 编译源码...' -ForegroundColor Cyan
$sources = @(Get-ChildItem -Recurse src -Filter *.java | ForEach-Object { $_.FullName })
$sources += @(Get-ChildItem -Recurse "$build\gen" -Filter R.java | ForEach-Object { $_.FullName })
if ($sources.Count -lt 5) { throw "源码数量异常：$($sources.Count)" }
# 注意：不要写进 @argfile —— javac 会把路径里的反斜杠当转义符
& "$Jdk\bin\javac.exe" -encoding UTF-8 -source 8 -target 8 -bootclasspath $androidJar `
    -nowarn -d "$build\classes" @sources
if ($LASTEXITCODE -ne 0) { throw 'javac 编译失败' }

# ---------------------------------------------------------------- 4) dex
Write-Host '[5/6] d8 转 dex 并打包...' -ForegroundColor Cyan
& "$Jdk\bin\jar.exe" cf "$build\classes.jar" -C "$build\classes" .
if ($LASTEXITCODE -ne 0) { throw 'jar 打包失败' }
& "$buildTools\d8.bat" --release --min-api 21 --lib $androidJar --output "$build\dex" "$build\classes.jar"
if ($LASTEXITCODE -ne 0) { throw 'd8 转换失败' }
if (-not (Test-Path "$build\dex\classes.dex")) { throw 'd8 没有产出 classes.dex' }

Copy-Item "$build\app-unsigned.apk" "$build\app-dex.apk" -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open("$build\app-dex.apk", 'Update')
[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
    $zip, "$build\dex\classes.dex", 'classes.dex',
    [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
$zip.Dispose()

& "$buildTools\zipalign.exe" -f 4 "$build\app-dex.apk" "$build\app-aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'zipalign 失败' }

# ---------------------------------------------------------------- 5) 签名
Write-Host '[6/6] 签名并校验...' -ForegroundColor Cyan
$ks = Join-Path $build 'debug.keystore'
if (-not (Test-Path $ks)) {
    & "$Jdk\bin\keytool.exe" -genkeypair -keystore $ks -storepass android -keypass android `
        -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 `
        -dname 'CN=Android Debug,O=Android,C=US'
    if ($LASTEXITCODE -ne 0) { throw '生成调试密钥失败' }
}
$apk = Join-Path $dist 'match3.apk'
& "$buildTools\apksigner.bat" sign --ks $ks --ks-pass pass:android --key-pass pass:android `
    --out $apk "$build\app-aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'apksigner 签名失败' }

& "$buildTools\apksigner.bat" verify --print-certs $apk | Select-Object -First 3
Write-Host ''
& "$buildTools\aapt2.exe" dump badging $apk | Select-String -Pattern "^package|^application-label|^launchable-activity|^sdkVersion|^targetSdkVersion"
Write-Host ''
$info = Get-Item $apk
Write-Host ("完成：{0}  ({1:N1} KB)" -f $info.FullName, ($info.Length / 1KB)) -ForegroundColor Green
Write-Host ("安装：{0}\platform-tools\adb.exe install -r `"{1}`"" -f $Sdk, $apk)
exit 0
