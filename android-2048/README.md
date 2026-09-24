# 2048 · Android

用手写的 Android 工程实现的 2048，**不依赖 Gradle / AndroidX / 任何第三方库**——
布局、动画、图标全部自己画，构建走 `javac + aapt2 + d8 + apksigner` 的手工链路。
APK 只有 **33 KB**，而且**不申请任何权限**。

## 安装

仓库里已经带了编译好的 `2048.apk`（调试签名，个人装没问题）：

1. 把 `2048.apk` 传到手机（微信/数据线/网盘都行）
2. 手机上点开它，按提示允许"安装未知来源应用"
3. 或者用数据线：

```powershell
D:\android-sdk\platform-tools\adb.exe install -r .\2048.apk
```

支持 Android 5.0（API 21）及以上。

## 玩法

- **滑动**合并相同数字，目标是凑出 2048
- 顶部实时显示**分数**与**最高分**（存本地，关掉再开还在）
- **撤销**按钮可退回上一步（只能退一步）
- **新游戏**重开一局
- 凑出 2048 后可以选"继续玩"冲更高分
- 无路可走时点任意位置重开

细节都按 2048 的标准规则：每次滑动后只生成一个新方块（90% 是 2、10% 是 4），
合并过的方块当次不能再合并（`2 2 2 2` 一次左滑得到 `4 4` 而不是 `8`），
方块数值始终是 2 的幂。

## 界面

全部是 Canvas 手绘（没有布局 XML、没有图片资源，连图标都是脚本生成的 PNG）：

- 深色背景 + 经典 2048 配色（奶油色 → 橙色 → 金黄色的阶梯）
- 卡片式分数框、圆角按钮
- **两段式动画**：方块先滑到目标格（110ms），再让合并/新生的方块弹一下（90ms）
- 屏幕常亮、锁定竖屏

## 构建

```powershell
# 1) 一次性准备工具链（下载 Android SDK 的 cmdline-tools + platform + build-tools）
powershell -ExecutionPolicy Bypass -File ..\.build\setup_android_sdk.ps1

# 2) 编译 + 跑自测 + 出 APK
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

需要：JDK（用 `javac`/`keytool`/`jar`）+ Android SDK 的 `platforms;android-34` 与
`build-tools;36.1.0`。**不需要 Gradle、不需要 AGP、不需要联网解析 Maven 依赖**。

构建流程（每一步都在 `build.ps1` 里，带错误检查）：

```
自测       javac + java 跑 GameTest            → 逻辑层的 2979 项断言
资源       aapt2 compile res                   → build\res.zip
清单/资源  aapt2 link -I android.jar           → R.java + 未签名 APK
源码       javac -source 8 -bootclasspath ...  → .class
转 dex     jar + d8                            → classes.dex
打包       把 classes.dex 塞进 APK + zipalign
签名       keytool 生成调试密钥 + apksigner（v1/v2/v3 三套签名）
```

> ⚠️ **踩到的坑**：`build-tools;34.0.0` 自带的 d8（R8 8.2.2）遇到 **enum 类**会内部崩溃
> （`java.lang.NullPointerException: Cannot invoke "String.length()"`），
> 换 `build-tools;36.1.0` 就好了。脚本里默认用 36.1.0，注释也写了原因。

## 代码结构

```
src/com/dsh/g2048/
  Game.java         2048 核心逻辑 —— 不引用任何 Android API，可直接用 java 跑测试
  GameTest.java     单元测试（纯 Java，不需要 JUnit）
  GameView.java     棋盘视图：Canvas 绘制 + 手势 + 动画状态机
  MainActivity.java 唯一的 Activity：生命周期、最高分与局面的持久化
AndroidManifest.xml 清单（minSdk 21 / targetSdk 34，未申请任何权限）
res/values/strings.xml
res/mipmap-*/ic_launcher.png   5 个密度的图标（由脚本生成）
build.ps1           手工构建脚本
```

逻辑与界面分层的好处是：**换 UI 不用碰规则，改规则不用开模拟器**——
`Game.java` 可以在任何装了 JDK 的机器上用一秒跑完全部测试。

## 自测

`build.ps1` 会先跑自测，不通过就中止打包。共 8 组用例、**2979 项断言**：

| 用例 | 校验内容 |
|---|---|
| 初始局面 | 恰好两个方块、值只能是 2 或 4、分数为 0 |
| 合并规则 | `2244→4,8`（+12 分）、`222→4,2`（不连锁合并）、`2222→4,4`、`4488` 右移 |
| 无效移动 | 无可动时不改变棋盘、不计分、**不生成新方块** |
| 数值守恒 | 400 步随机对局：总和只增加新方块那一个、方块数合法、得分不减 |
| **与朴素实现对拍** | 另写一个"一眼就对"的参考实现，随机棋盘 × 四个方向 **1200 组**逐格比对 |
| 撤销 | 恢复棋盘与分数、只能退一步 |
| 胜负判定 | 凑出 2048 报胜、死局判定、有空格不算死局 |
| 滑动动画数据 | 起终点在界内、不产生"原地不动"的动画 |

"与朴素实现对拍"这组当场就抓出了一个真 bug：我最初的合并逻辑比较的是**原数组里相邻的两格**，
当相同方块中间夹着空格时就漏合并（`[64,0,64,128]` 上移只压缩不合并）。正确做法是跟
"已经写出去的最后那个值"比较。这个 bug 单看 `2 2 4 4` 这类用例是测不出来的。

## 已知限制

- **只在代码层面验证过，没有在真机/模拟器上跑过**：本机没有 Android 设备，
  也没有装模拟器（要额外下载 1.5 GB 系统镜像）。逻辑有 2979 项断言保证，
  APK 的结构、签名、清单、dex 都逐项校验过，但**真机运行效果请以你装上后为准**。
- 调试签名（不能上应用商店，个人安装没问题）
- 仅竖屏、无音效、无深色/浅色主题切换
- 最高分和局面存在 SharedPreferences 里，清数据会丢
