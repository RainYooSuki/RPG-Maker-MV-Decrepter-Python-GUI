# RPG Maker MV/MZ Decrypter（Python）

<img src="rpgmv_decrypter/assets/logo-wordmark.svg" alt="RPG Maker MV/MZ Decrypter" width="420">

这是 [Petschko 的 RPG-Maker-MV-Decrypter](https://github.com/Petschko/RPG-Maker-MV-Decrypter) 的
Python 重写版：它用来解密、重新加密和还原 **RPG Maker MV** 与 **RPG Maker MZ** 在项目按
*“Encrypt game data”*（加密游戏数据）导出时生成的资源文件。

三种使用方式：

| 界面 | 说明 |
| --------- | ---------- |
| **桌面 GUI** | 原生的 PySide6 窗口：三个编号步骤（获取密钥、选择文件、开始处理），支持拖放，每次运行导出一个带时间戳的文件夹。中文和英文，运行中即可切换。 |
| **CLI** | `python -m rpgmv_decrypter`，子命令有 `decrypt`、`encrypt`、`restore`、`detect-key` 和 `info`。 |
| **库** | `import rpgmv_decrypter` —— 只用标准库；见 [`INTERFACE.md`](INTERFACE.md)。 |

为什么要有它：RPG Maker 自带的加密让人很难确认一个游戏是否在授权范围内使用你的素材，
也让「原始工程文件已经丢失，只想看一眼（或修一下）游戏里某张图」变得不可能。原版工具
在浏览器里解决了这个问题；这个重写版把它搬到命令行、Python 和本地桌面窗口里 ——
不启动服务器、不占端口、不上传任何东西。

快速开始：用 [`build_exe.py`](build_exe.py) 编译出 exe，**双击 exe** 即可（默认中文）。
完整的安装、编译与调用方式见下文。

```powershell
# 1) 装依赖（清华镜像）
python setup.py deps --mirror

# 2) 编译成 exe（文件夹形式）
python build_exe.py

# 3) 双击 dist\RPGMakerDecrypter\RPGMakerDecrypter.exe
```

也可以直接从源码运行，或当库用：

```powershell
cd RPG-Maker-MV-Decrepter-Python
python -m rpgmv_decrypter.gui            # 桌面界面（默认中文）
python -m rpgmv_decrypter.gui --lang en  # 需要英文界面时
python -m rpgmv_decrypter --help         # 命令行
python -c "import rpgmv_decrypter; print(rpgmv_decrypter.__version__)"   # 当库导入
```

> **`start.bat` 已淘汰。** 需要一个批处理文件去戳虚拟环境、再启动 Python，正是编译成 exe
> 要取代的事 —— 留着它等于同时维护「双击 bat」和「双击 exe」两条启动路径。现在只有 exe。


## 法律声明

本声明抄自原项目，在这里原样适用：

* 如果解密出来的文件**其原授权不允许**，你**不得使用**它们。请不要盗用和复用素材 ——
  这不是本工具的用途。
* 你可以**只把它们留作私人使用**。如果原授权允许复用，你当然可以复用 —— 但**请遵守
  授权条款**。
* **如果这是你自己的项目**，只是原始文件丢了，那么你拥有**和以前一样的权利**。

原作者保留其作品的全部权利。

## 支持范围

| 加密（MV） | 加密（MZ） | 明文格式 | 媒体类型 |
| -------------- | -------------- | ------------ | ---------- |
| `.rpgmvp`      | `.png_`        | `.png`       | image/png  |
| `.rpgmvo`      | `.ogg_`        | `.ogg`       | audio/ogg  |
| `.rpgmvm`      | `.m4a_`        | `.m4a`       | audio/mp4  |

MV 和 MZ 使用同一套加密算法和同样的 16 字节头，区别只在扩展名的命名方式。解密需要游戏
的加密密钥 —— 图片例外，**不需要任何密钥就能还原**。细节、注意事项以及*不*支持的内容
见 [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md)。

## 安装与运行

三条路，按你想做什么选：

| 你想 | 做什么 |
| ---- | ------ |
| **直接用** | 拿到 `dist/RPGMakerDecrypter/` 就双击里面的 exe，不需要 Python |
| **自己编译 exe** | `python setup.py deps --mirror` 然后 `python build_exe.py` |
| **当库用** | `pip install .`（库本身零第三方依赖），或直接在项目根目录 `import rpgmv_decrypter` |

### 免安装的打包版（不需要 Python）

`dist/RPGMakerDecrypter/` 是一个自包含目录 —— 双击里面的
**`RPGMakerDecrypter.exe`** 即可。它自带 Python 和 Qt，所以什么都不用装；它是用根目录的
`build_exe.py` 构建的（Nuitka，standalone 目录模式）。请保持整个目录完整：这个可执行文件
需要旁边的 DLL。

命令行也一样可用，不需要 `PATH` 上有 Python：

```bat
dist\RPGMakerDecrypter\decrypter-cli.bat --help
dist\RPGMakerDecrypter\decrypter-cli.bat decrypt -k 1234567890abcdef -o out game.rpgmvp
```

### 自己编译 exe

```powershell
python setup.py deps --mirror     # 装依赖（PySide6）
python build_exe.py               # 编译到 dist/RPGMakerDecrypter/
python build_exe.py --check       # 验证产物：exe 能跑、能解密、窗口能开
python build_exe.py --clean       # 先删掉 build/ 和 dist/ 再编译
```

`build_exe.py` 和 `setup.py` 分工明确：**`setup.py` 只装依赖，`build_exe.py` 只负责编译。**

第一次编译会下载 Nuitka 自带的 MinGW64（MSVC 不在 `PATH` 时），缓存在 `.tmp/nuitka-cache`，
之后不再下载。产物是**文件夹形式**而不是单文件：单文件每次启动都要把自己解压到临时目录，
对一个经常打开的程序是坏交易。

### 一条命令装好依赖

项目需要的一切都声明在 [`setup.py`](setup.py) 里，它同时也能安装这些依赖：

```powershell
python setup.py check                 # 看看缺什么
python setup.py deps --mirror         # 用清华镜像安装
python setup.py deps                  # 或者走官方 PyPI
python setup.py deps --runtime-only   # 不装 pytest
```

`--mirror` 接受 `tsinghua`（默认）、`aliyun` 或 `ustc`：

| 镜像源   | URL                                          |
| -------- | -------------------------------------------- |
| tsinghua | `https://pypi.tuna.tsinghua.edu.cn/simple`   |
| aliyun   | `https://mirrors.aliyun.com/pypi/simple/`    |
| ustc     | `https://pypi.mirrors.ustc.edu.cn/simple/`   |

或者手动装 —— 一个运行时依赖，一个开发依赖：

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyside6-essentials pytest
```

> **注意**：是 `pyside6-essentials`，不是 `PySide6`。完整的 `PySide6` 包会带上
> WebEngine、Multimedia 以及其余 Qt 模块 —— 大约 1 GB，而本项目根本不会 import 它们。

### 从源码运行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python setup.py deps --mirror          # 或者：python -m pip install -e ".[gui]"
python -m rpgmv_decrypter.gui
```

`pyproject.toml` 用两个可选 extra 声明这个包：

| Extra   | 内容                  | 用途                    |
| ------- | ------------------------- | ---------------------- |
| `gui`   | `pyside6-essentials>=6.5` | 桌面 GUI                |
| `test`  | `pytest>=7.0`             | 运行测试套件            |

库本身**不需要**任何第三方包 —— `[gui]` 只给桌面界面用，`[test]` 只给 pytest 用。
安装本项目还会给你两个 console script：

| 脚本                 | 入口点                    |
| ---------------------- | ------------------------------ |
| `rpgmv-decrypter`      | `rpgmv_decrypter.cli:main`     |
| `rpgmv-decrypter-gui`  | `rpgmv_decrypter.gui:main`     |

需要 Python 3.10 或更新版本（`requires-python = ">=3.10"`）；开发和验证用的是 3.12.9。

不安装、直接从 checkout 目录运行也可以，只要身处项目根目录，让 Python 能找到
`rpgmv_decrypter` 包：

```powershell
cd RPG-Maker-MV-Decrepter-Python
python -m rpgmv_decrypter --help
python -m rpgmv_decrypter.gui
```

## 桌面 GUI（PySide6）

### 启动

**双击 [`dist/RPGMakerDecrypter/RPGMakerDecrypter.exe`](build_exe.py)。** 它自带 Python 和
Qt，所以目标机器上什么都不用装；语言默认中文，窗口里随时可切换。

从源码启动（开发时用，等价）：

```powershell
cd RPG-Maker-MV-Decrepter-Python
.\.venv\Scripts\python.exe -m rpgmv_decrypter.gui             # 中文（默认）
.\.venv\Scripts\python.exe -m rpgmv_decrypter.gui --lang en   # 英文启动
```

窗口*就是*界面：没有服务器、没有端口、没有浏览器标签页，什么都不离开这台机器。
`--lang {zh,en}` 是唯一的命令行选项；它只决定窗口以什么语言打开，别的什么都不影响。

如果窗口起不来，那就是缺 PySide6：

```powershell
python setup.py deps --mirror     # 或：python -m pip install pyside6-essentials
```

执行过 `pip install -e .` 之后，console script `rpgmv-decrypter`（CLI）和
`rpgmv-decrypter-gui`（这个窗口）会启动同样的两个界面。

窗口中间是**三个编号步骤**，下面是**结果**（Results）区域（进度、运行按钮、日志）。

### 第 1 步 · 获取密钥

按**识别密钥**（Detect key，`Ctrl+D`），选*一个*文件来读取密钥：`System.json`
（MV 在 `www/data/`，MZ 在 `data/`）、`rpg_core.js`、普通的 `.json`/`.txt` 文件，或者一张
加密图片（`.rpgmvp` / `.png_`）。密钥会被填进**密钥（十六进制）**（Key (hex)）输入框，
日志行会说明它是怎么找到的（`read from the plain JSON file`、
`recovered from the encrypted image header`、`scanned from rpg_core.js`……），以及尝试过
哪些策略。密钥识别只针对单个文件，不能直接扫整个游戏目录 —— 要扫目录请用 CLI 的
`detect-key` 子命令，或者把目标指向 `www/data/System.json`。

你也可以自己输入或粘贴密钥。密钥会在任何处理开始之前被校验：必须是十六进制、位数为
偶数，并且至少和头一样长（默认 16 字节 = 32 个十六进制字符）。**复制**（Copy）把当前
密钥放进剪贴板，**清空**（Clear）清掉输入框。

密钥只在加解密时才需要；**还原图片不需要密钥**。如果识别出的密钥无法通过头校验，它
仍然会被填进去，只是日志里会注明这个密钥未经确认，建议先解密一张图片验证一下。

### 第 2 步 · 选择文件

用**添加文件…**（Add files…，`Ctrl+O`）或**添加文件夹…**（Add folder…，`Ctrl+Shift+O`）
添加输入，也可以**把文件或文件夹拖到窗口上**。文件夹会被展开进列表，第 3 步的
**递归处理子文件夹**开关会重新展开它：取消勾选后，列表只保留该文件夹第一层的文件。
窗口不认为可用的文件也会被列出来，只是标成**不适用**（Not usable），而不是被悄悄丢掉；
表格下面那一行会报告其中有多少是可用的（中文界面形如
`已选 3 个文件（其中 2 个可用于当前操作）`，英文界面形如
`3 file(s) selected (2 usable for this operation)`）。**移除选中**（Remove selected）
会永久删掉高亮的行 —— 被移除的文件不会因为重新展开它所在的文件夹而回来 ——
**清空列表**（Clear list，`Ctrl+L`）会清空全部。

表格的列是**文件**、**类型**、**大小**和**状态** —— 每个文件的结果在运行结束后出现在
状态列里。

加密文件（`.rpgmvp .rpgmvm .rpgmvo .png_ .ogg_ .m4a_`）和明文文件（`.png .ogg .m4a`）
都可以选；它们会被怎么处理，取决于你按的是哪个按钮。把目标指向 `www/img` 再按
**解密**（Decrypt），事情就办完了：文件夹会被递归遍历，里面每个可处理的文件都会被处理。

如果某个文件旁边已经有转换后的文件（半解密状态的文件夹），它会被**跳过**，所以重复
运行永远不会产生 `hero.png.png`。

### 第 3 步 · 开始处理

第三张卡片放的是高级设置和运行按钮：

| 控件                   | 默认值 | 作用                                                                    |
| ------------------------- | ------- | -------------------------------------------------------------------------- |
| **校验伪头**（Verify fake header）    | 开      | 关掉后不做头校验 —— 这是 "invalid header" 警告的解决办法。 |
| **头长度（字节）**（Header length） | 16      | 游戏 core script 里的 `Decrypter._headerlength`。                      |
| **Signature**（十六进制）       | `5250474d56000000` | core script 里的 `Decrypter.SIGNATURE`。                     |
| **Version**（十六进制）       | `000301` | `Decrypter.VER`。                                                           |
| **Remain**（十六进制）        | `0000000000` | `Decrypter.REMAIN`。                                                    |
| **恢复默认**（Reset to defaults）     | —       | 把上面四个值恢复成 RPG Maker 默认值，并重新勾选**校验伪头**。 |
| **递归处理子文件夹**（Include sub-folders）   | 开      | 递归展开文件夹输入；切换它会重新展开文件列表（对应 CLI 的 `--recursive` / `--no-recursive`）。 |
| **额外打包成 ZIP**（Also create a ZIP）     | 关     | 额外把本次运行的结果打包成一个压缩包。                |

然后按下面其中一个：

| 按钮                  | 作用                                                                    |
| ----------------------- | ------------------------------------------------------------------------------- |
| **解密**（Decrypt）             | 解密加密文件；明文输出的扩展名是转换后的扩展名。    |
| **加密为 MV**（Encrypt for MV）      | 把明文文件加密成 RPG Maker MV 格式（`.png` → `.rpgmvp`，`.ogg` → `.rpgmvo`，`.m4a` → `.rpgmvm`）。 |
| **加密为 MZ**（Encrypt for MZ）      | 同上，用于 RPG Maker MZ（`.png_`、`.ogg_`、`.m4a_`）。                           |
| **还原 PNG 头**（Restore PNG headers） | 重建 `.rpgmvp` / `.png_` 图片的 PNG 头 —— **不需要密钥**。       |
| **取消**（Cancel）              | 在当前处理中的文件结束后停止；本次运行报告「已取消」（Cancelled）。               |
| **查看导出结果**（View results）    | 在窗口内浏览上一次运行的导出目录：文件名/类型/大小，选中图片即预览（左列表、右预览）。 |
| **复制报告**（Copy report）         | 把日志面板（完整运行报告）复制到剪贴板。                      |

**还原 PNG 头**会忽略密钥输入框：它始终使用默认的 `Signature` / `Version` / `Remain`
值，并保持头校验开启，所以这张卡片上只有头长度对它生效。

#### 结果放在哪里

每次运行都会导出到它在 `<project>/output/` 下的**独立时间戳文件夹**：

```text
output/
└── 2025-01-31_204512/          <- one folder per run, named after the start time
    ├── hero.png                <- your files, extensions converted
    ├── face.png
    ├── _logs/
    │   └── report.txt          <- the same text the log pane shows
    └── _zip/                   <- only when "Also create a ZIP" was ticked
        └── 2025-01-31_204512.zip
<project>/.tmp/gui/             <- inputs are staged here, not delivered from here
```

结果导出到项目根目录的 `output/时间戳/`（例如 `output/2025-01-31_204512/`），每次运行
一个独立文件夹。已经存在的东西都不会被覆盖 —— 既不会覆盖游戏目录，也不会覆盖更早的
一次运行：同一秒内的两次运行会得到 `…_204512` 和 `…_204512_1`，也就是新建一个 `…_1`
后缀的文件夹，而不是共用一个文件夹。运行日志写在同一个文件夹的 `_logs/report.txt` 里。
状态行会汇总本次运行（`完成：3 个成功，1 个跳过，0 个失败`，英文界面下是
`Done: 3 succeeded, 1 skipped, 0 failed`），日志面板会写出结果写到了哪个目录，并逐个
列出文件、大小和处理结果。

#### 打包版的导出目录会自己挑地方

源码运行时就是 `<项目>/output/`。**打包版会先试着放在 exe 旁边** —— 拿到一个绿色版
工具，输出就在工具旁边，这是最不让人意外的位置 —— 但安装目录不一定是可写的（解压到
`Program Files` 就是典型的不可写）。所以选目录的顺序是：

| 顺序 | 位置 | 说明 |
| ---- | ---- | ---- |
| 1 | 界面里手选的目录 | 用户选的就是答案，不做二次判断 |
| 2 | `RPGMV_GUI_OUTPUTDIR` | 脚本化运行用 |
| 3 | **exe 旁边的 `output/`** | 可写时用这个 |
| 4 | `%LOCALAPPDATA%\RPGMakerDecrypter\output` | 安装目录不可写时改到这里 |
| 5 | 系统临时目录 | 最后兜底，并**明确提示这是临时目录、系统可能清理、请及时移走** |

**换了地方会在日志里说。** 悄悄把用户的输出挪到别处是另一种 bug，所以窗口一打开就会
写一行说明它把结果放到哪、为什么。界面上的「导出根目录」标签显示的也是解析后的真实
路径，不是那个理论上应该用的路径。

> 之前这里有个 bug：打包版用 `__file__` 推算项目根目录，而编译后那就是 exe 自己所在的
> 目录，于是它试图在安装目录里建 `output/`，失败时报一句 `[WinError 5] 拒绝访问`。
> 现在由 `tools/prove_packaged_output.py` 真的编译一个 Nuitka 程序来验证这两条路径
> （顺带发现 Nuitka **不设置** `sys.frozen`，而且 `sys.executable` 指向的是包内那个
> `python.exe`；所以要靠 `__compiled__` 和 `sys.argv[0]` 判断）。

**「打开导出目录」按钮已经删除。** 原因写在这里，因为它是这个项目里最值得记的一个教训。

这个按钮做的事情是「请操作系统的 shell 显示一个文件夹」。在受限会话里这个请求恒被拒绝，而
**没有任何写法能绕过它** —— 实测过九条路：

| # | 方式 | 结果 |
| - | ---- | ---- |
| 1 | Qt `QDesktopServices.openUrl` | 返回 false（内部 `ShellExecute` error 5） |
| 2 | `os.startfile` | `WinError 5` 拒绝访问 |
| 3–5 | PowerShell `Start-Process` / `Invoke-Item` / .NET `Process.Start` | `Access is denied` |
| 6 | 直接起 `explorer.exe` | 进程创建后立刻 `0xC0000142` 崩掉 |
| 7 | 直接调 `ShellExecuteExW` | `open` → error 5 |
| 8 | COM 自动化**正在运行的** explorer | `0x80040154` 类未注册 |
| 9 | 剪贴板 | ✅ 成功 |

1、2、7 是同一个 `ShellExecute`；3–5 是 .NET/PS 封装的同一个调用；6、8 是想绕开它，也失败。
`shell:Downloads` 返回 **1155**（没有关联）而普通路径返回 **5**（拒绝访问）—— 说明
`ShellExecute` 本身是正常求值的，只是「打开」这个动作在**系统边界上被拒绝**了。

**所以这个按钮在这个环境里注定不可用，用户也不再需要它**（原话：「删掉打开导出目录，我不需要
了，反正也用不了」）。现在结果面板上只有 **「查看导出结果」**，它完全在应用内部完成，不依赖
shell。

> **一条只会大声失败的路，比没有这条路更糟。** 中间还试过「直接启动 `explorer.exe`」这条路：
> 它不走 `ShellExecute`，看起来能绕过拒绝。但在 `explorer.exe` 起不来的机器上，它会被创建、
> 然后立刻以 `0xC0000142` 崩掉，而 **Windows 会为此弹出一个「Application Error」对话框** ——
> 用户每点一次按钮，屏幕上就多一个报错框，而那个目录本身完全正常。所以那条路被彻底删除，
> 连带它的存活检测辅助函数一起删掉了。

> **一个被推翻的错误结论也记在这里。** 曾经只看 `Get-Process` 就断言"这台机器没有桌面
> shell"。那是错的：该沙箱里 `Get-Process` 列不全进程，任务栏和 explorer 都在。**"我看不到"
> 不等于"不存在"** —— 所以现在这个探针改用窗口 API（`GetShellWindow`、`FindWindowW`）来
> 判断桌面是否存在，而不是靠进程列表。


复现脚本：`tools/probe_open_folder.py`。**它自己不启动任何东西** —— 早先那版会去启动
`explorer.exe`，等于诊断工具本身在制造它要诊断的那个弹框。

#### 「查看导出结果」——不依赖系统文件管理器

既然「让 shell 显示文件夹」在受限环境里注定失败，结果面板上提供的是**在窗口内浏览导出目录**。

它**不需要 shell** —— 这是关键。同一个会话里实测：

```text
QFileDialog 原生对话框   isVisible() = True    <- 能弹
QDesktopServices.openUrl(C:\) = False          <- 被拒
```

**被拦的只是"让 shell 打开"，不是"弹窗口"。** 所以：

| 在「查看导出结果」里可以 | 说明 |
| ------------------------ | ---- |
| 看到本次运行产出的文件 | 左侧列表：名称 / 类型 / 大小，文件夹在前 |
| **直接预览图片** | **右侧**按比例显示选中的 `.png`（左列表、右预览，预览不遮挡列表） |
| 单击文件 = 只看预览 | 不会启动任何外部程序 |
| **双击进入** `_zip/`、`_logs/` 子目录 | 有「上级目录」可退回 |
| **复制路径** | 任何环境下都能用；粘贴到文件管理器地址栏即可 |
| 「完成」关闭 | 二级界面，不干扰主窗口 |

它是一个**纯查看器**，不是启动器：没有「打开文件」，也没有「在文件管理器中打开」。要外部打开
某个文件，从列表里复制路径自己开 —— 这样在任何环境下行为都一致，不会出现"某个按钮在你这台
机器上不可用"的情况。

**打包是可选项。** **额外打包成 ZIP** 默认关闭，因为一个能直接翻的文件夹通常更有用；
想交付一个压缩包时再勾上，它会出现在同一次运行的 `_zip` 子目录里。导出根目录可以用
结果头部的**更改…**（Change…）改到别处（只对本次窗口有效，直到关闭窗口），也可以用
`RPGMV_GUI_OUTPUTDIR` 环境变量（每次启动都生效）。输入文件在被读取之前会复制到
`<project>\.tmp\gui\<job>\input`，所以只读的游戏目录也能用，原文件绝不会被动到；暂存
根目录可以用 `RPGMV_GUI_WORKDIR` 覆盖。

运行时会显示进度条和状态行；大文件夹是一个文件一个文件地处理。

#### Header 不匹配？

和原版工具一样：如果遇到 invalid-header 警告，先把**校验伪头**关掉再试一次 —— 前提是
确认这个文件真的是加密文件。如果游戏仍然不接受重新加密后的文件，那它很可能用了自定义
头值：打开 MV 的 `www/js/rpg_core.js`（MZ 是 `js/rpg_core.js`），搜索
`function Decrypter()`，把 `_headerlength`、`SIGNATURE`、`VER` 和 `REMAIN` 复制到上面的
输入框里。只有在默认值不生效时才改它们；**恢复默认**会把它们改回来。

#### 不用密钥还原图片

1. 选中一个或多个加密图片（`.rpgmvp` / `.png_`）。
2. 按**还原 PNG 头**（`Ctrl+R` 也会运行当前操作）。不需要密钥，密钥输入框会被忽略。

对于标准 PNG，这会逐字节重建原始文件（每个 PNG 的前 16 字节都是常量）。如果某个文件的
前 16 字节不是标准 PNG 头，那这 16 字节会被 PNG 头替换掉，并且无法找回 —— 见
[`docs/HEADER.md`](docs/HEADER.md)。第 3 步里的头长度在这里同样生效。

### 键盘快捷键

| 快捷键       | 操作                      |
| -------------- | --------------------------- |
| `Ctrl+O`       | 添加文件…                  |
| `Ctrl+Shift+O` | 添加文件夹…                 |
| `Ctrl+R`       | 运行当前操作   |
| `Ctrl+D`       | 从文件识别密钥  |
| `Ctrl+L`       | 清空文件列表         |

### 语言（中文 / English）

**窗口默认是中文**，头部有语言切换（`语言` + 下拉框）：选 **English** 会把整个窗口原地
重译成英文，选 **中文** 再切回来。每个标签、按钮、提示、对话框、状态行以及运行报告都会
跟着切换，不需要重启。

`--lang` 只决定窗口以什么语言打开（编译后的 exe 同理：`RPGMakerDecrypter.exe --lang en`）：

```powershell
.\.venv\Scripts\python.exe -m rpgmv_decrypter.gui --lang en   # start in English
.\.venv\Scripts\python.exe -m rpgmv_decrypter.gui --lang zh   # start in Chinese (default)
```

所有文案都放在一个地方 —— [`rpgmv_decrypter/i18n.py`](rpgmv_decrypter/i18n.py) 里的
`TEXT` 表 —— 每个条目都有 `zh` 和 `en` 两份，所以加一种语言或修一处翻译都只改一行。
如果新增了条目却漏掉某种语言，或者英文字符串里还留着中文，测试套件会失败。

### 标志

<img src="rpgmv_decrypter/assets/logo.svg" alt="" width="72" align="right">

一枚**盾牌**，上面镂空出一个**钥匙孔**，放在圆角方形底座上。盾牌是被保护的资源，钥匙孔
是进入它的途径，方形底座则是 RPG Maker 给自己素材和工具用的形状，所以这个图标和它所
服务的引擎放在一起很自然。配色取自界面本身，因此标志和窗口是一家人。

明暗结构是刻意设计的 —— **浅色底座**、其上的**深色盾牌**、盾牌上镂出的**浅色钥匙孔** ——
因为在任务栏 16px 下只有三个干净的层次能存活。第一版用的是渐变底座和中间调的盾牌，
底座的暗端正好落在盾牌顶部后面，于是盾牌融进底座，只剩钥匙孔还看得见。

一切都由一个 SVG 生成，脚本是 [`tools/make_logo.py`](tools/make_logo.py)：
[`logo.svg`](rpgmv_decrypter/assets/logo.svg)、
[wordmark](rpgmv_decrypter/assets/logo-wordmark.svg)、九个 PNG 尺寸（16-256px）以及一个
多尺寸 `.ico`。随后 [`tools/check_logo.py`](tools/check_logo.py) 会去*测量*它在每个尺寸
下是否还认得出来 —— 覆盖率、圆角留白、还能剩下几个色调分组、钥匙孔是否始终比盾牌更亮 ——
而不是假设它还认得出来。`tests/test_gui.py` 则确保 Windows 索要的每个尺寸都能加载图标。

### 外观与质感

外观是苹果的 **Liquid Glass**（苹果在 WWDC 2025 推出的材质），按桌面工具的尺度落地：
一扇深色、偏蓝的窗口，上面浮着半透明面板。这种材质的辨识度来自**光学**，而不是颜色：

* 受光顶边有一道锐利的**镜面高光边**，向两侧渐隐 —— 它在约 56 的填充色上测到约 235，
  所以看起来像打磨过的边缘在反光；
* 高光边内侧还有一圈柔和的**内晕**，光会往内渗，而不是在边界上戛然而止；
* 主体填充几乎透明，让窗口的色调透出来 —— 卡片的透光率约为背景变化的 40%，所以背景
  是**在**卡片**里**可见，而不只是待在卡片后面；
* 更大的连续圆角、胶囊形按钮，以及柔和的多层阴影。

配色是用户提供的蓝紫色系：`#BDD8FF`、`#3D91CC`、`#1E3663`、`#5D76BA`、`#A7A7D1`。
`#1E3663` 填在主操作上，较浅的蓝色给背景的光区定调，因此强调色和背景属于同一个色族。

Qt 无法让一条边框沿长度变色，所以高光边和内晕是*画*出来的（`gui.paint_glass_edges`），
而不是用样式表。所有设计变量都在
[`rpgmv_decrypter/gui_theme.py`](rpgmv_decrypter/gui_theme.py) 里，其中的数值由
[`tools/tune_liquid_glass.py`](tools/tune_liquid_glass.py) 和
[`tools/tune_backdrop_palette.py`](tools/tune_backdrop_palette.py) 拟合出来，而不是猜的。

窗口还可以向 DWM 申请真正的 Windows 11 Acrylic 背景（`apply_windows_backdrop()`）；
被接受时，画出来的背景会变成一层半透明蒙版，让系统模糊透出来；不被接受时（较老的
Windows、无头会话、拒绝配合的合成器），窗口保留自己不透明的颜色 —— 这样不支持的系统
得到的是同样的观感，而不是一个透明窟窿。`MainWindow.backdrop_kind` 记录了实际发生的
是哪种情况。

**可读性是强制校验的，不是「打算做到」。** 每种文字颜色都会针对它所在表面*实测*出的
像素做 WCAG AA 校验：主文字 7.7:1，次要 5.7:1，弱化文字在最差的卡片表面上 4.8:1，
强调按钮的白色标签在其渲染填充上 11.9:1（悬停时 8.1:1）。`tools/inspect_gui.py` 会打印
这些数字，`tests/test_gui.py` 在它们回退时会让测试失败。

这里刻意**不**声称的东西：苹果那套材质还会*折射*背后的内容（在边缘处对背景做透镜式
位移）。那需要逐像素 shader，而 Qt widget 跑不了 —— 所以这里没有。这里的玻璃做的是：
透传背景的色调和它的变化、带上镜面高光边和内晕、保持半透明；没有任何地方在弯折光线。

### 动效

界面会动，而且这些动效是**画出来的**，不是套 `QGraphicsEffect`。原因和上面一样：Qt 的
图形特效会把控件渲染进一张带缓存的离屏 pixmap，卡片里只要还有东西在重绘就会留下残影
（就是之前那个「伪影」）。所以动效改的是**绘制时读取的浮点数** —— 好处是它可测，也能被
实测出来真的动到了像素上。

| 动效 | 时长 | 做法 |
| ---- | ---- | ---- |
| **入场**：标题、三张步骤卡、结果面板依次淡入上浮 | 每面 420ms，间隔 55ms | 一个 `Stagger` 驱动全部，逐面把入场进度交给绘制；镜面高光边随进度变亮（实测 181 → 204 → 234） |
| **悬停**：指针移到卡片上时高光边和内晕更亮 | 140ms | 卡片画自己的 `intensity`，从 1.0 提到 1.7。阴影**不跟着变** —— 接光更多的面板不会投更多影，两者一起放大会像整张卡片在膨胀 |
| **拖放**：文件拖到列表上时虚线框点亮并轻微呼吸 | 每周期 900ms | 边框颜色与填充向强调色插值；静止的高亮看起来像「卡住了」，呼吸才表示这里还活着 |
| **状态行**：状态变化时闪一下再落回 | 320ms | 颜色在次要色与浅蓝之间插值，快起慢落 |
| 开关滑块 | 140ms | `QPropertyAnimation` 驱动滑块位置（见 `switch.py`） |

两件事是刻意做的：

* **空闲时零开销。** 动画自己会停，没有常驻定时器。实测：入场期间 114 次重绘，**空闲
  1 秒只有 1 次**（和没有任何动效的基线一样）。一个永远重绘的窗口比没有动效更糟。
* **可以关掉。** `RPGMV_NO_MOTION=1` 关闭；系统「减少动态效果」也会被读取
  （Windows 上是辅助功能的 `MinAnimate`，Qt 6.11 没有对应 API，所以直接读注册表）。
  关闭时所有动画**立刻落到终态** —— 界面看起来完全一样，只是不动。

测试默认在 offscreen 平台上跑，动效是**关**的，所以测试快且不依赖墙钟时间；动效本身由
`tests/test_motion.py` 显式打开后驱动来验证（14 项）—— 包括「入场真的让高光边变亮」和
「空闲时不许有任何东西还在跑」。截图见 `tools/render_motion.py`。

### 响应性

GUI 线程上不会跑任何耗时操作：

* **列目录**（遍历文件夹，逐个 `stat` 读取每个文件的大小和扩展名）跑在 `ScanWorker`
  线程上，分批把行推回来，所以表格是一边扫一边填的。
* **加/解密**跑在 `RunWorker` 线程上，运行中可以取消。
* **重绘**大表格（运行结束后或切换语言时）会被切片，每轮事件循环只做有限的工作量。

用 `tools/benchmark_ui_freeze.py` 在一个有 3000 个文件的文件夹上实测：添加整个文件夹
约 2 ms 返回，事件循环中最长的一次阻塞约 31 ms。同样的操作以前会阻塞长达 10.5 s。

### 速度

一批文件由库本身分发到线程池（`min(32, cores + 4)` 个 worker）上，时间也确实是花在这里：
还原 PNG 头就是*读 → 切片 → 写*，而切片会释放 GIL，所以即使 Python 代码很简单，线程也
确实有用。小于 `api.PARALLEL_MIN_FILES`（16）的批次仍然串行 —— 线程交接的代价比工作
本身还大，而且串行循环能在两个文件之间精确响应一次取消。

| 3000 个文件（47 MiB） | 之前 | 之后 |
| ------------------- | ------ | ----- |
| `api.restore_png_paths` | 5645 ms | **2592 ms** |
| GUI「还原 PNG 头」 | 11 552 ms | **5619 ms** |
| 500 个文件（31 MiB），GUI | 1707 ms | **756 ms** |

除了加线程池，还有两处必须改：

* GUI 以前**每个文件调用一次库**（`BatchRunner`），这让每次调用都只拿到一个单 worker 的
  池，完全没有加速 —— 现在它把整批一次性交给库；
* GUI 以前在处理之前会**把每个输入复制到暂存目录**。那一步复制在 2000 张图片上实测要
  3.9 s，比它保护的工作还慢：库只会读源文件并写入运行目录，输入从来就没有风险。暂存
  已经去掉了。

进度上报是合并过的（`BatchRunner.progress_interval`，50 ms），因为在这个规模下，每个
文件报一次状态比解密本身还贵；最后一步一定会上报，所以进度条仍然会走完。

`tools/benchmark_parallel.py`、`tools/benchmark_restore_speed.py` 和
`tools/benchmark_gui_overhead.py` 可以复现上面所有数字，
`tools/check_parallel.py` 则证明并行批次仍然按稳定顺序写出逐字节相同的文件，且不会互相
覆盖。

## 命令行

```powershell
cd D:\UGit\RPG-Maker-MV-Decrepter-Python
.\.venv\Scripts\python.exe -m rpgmv_decrypter --help
.\.venv\Scripts\python.exe -m rpgmv_decrypter --version
```

```text
rpgmv-decrypter 1.0.0
```

下面的例子假设有一个解包好的 RPG Maker MV 游戏在 `C:\Games\MyGame`（资源在 `www\` 下，
密钥在 `www\data\System.json` 里），密钥为 `1234567890abcdef1234567890abcdef`。下面每
条命令都在一个具有该目录结构的合成游戏上执行过；输出块是实际观察到的输出，只是把
fixture 路径换成了示例路径。

| 子命令   | 作用                                                        |
| ------------ | ------------------------------------------------------------------- |
| `decrypt`    | 解密 `.rpgmvp .rpgmvm .rpgmvo .png_ .ogg_ .m4a_` 文件。            |
| `encrypt`    | （重新）加密 `.png .ogg .m4a` 文件，MV 或 MZ 命名。                 |
| `restore`    | 重建 `.rpgmvp` / `.png_` 图片的 PNG 头 —— **不需要密钥**。    |
| `detect-key` | 打印某个文件或游戏目录中识别到的密钥（可以干净地管道传递）。      |
| `info`       | 只读报告：扩展名、头是否匹配、识别到的密钥。不写任何文件。   |

路径可以是文件也可以是目录（默认递归遍历），并且可以一次给多个路径。每个子命令都接受
[通用选项](#通用选项)表里的选项，放在子命令之前或之后都可以。

### decrypt

```powershell
# one file, key given on the command line
.\.venv\Scripts\python.exe -m rpgmv_decrypter decrypt -k 1234567890abcdef1234567890abcdef `
    "C:\Games\MyGame\www\img\pictures\hero.rpgmvp" -o C:\out\img
```

```text
OK  hero.rpgmvp -> hero.png (73 B)
1 processed
```

```powershell
# a whole game folder: detect the key from the game, keep a ZIP of the results
.\.venv\Scripts\python.exe -m rpgmv_decrypter decrypt --auto-key "C:\Games\MyGame" `
    -o C:\out --zip -v
#   -> files in C:\out\, archive in C:\out\_zip\out.zip
#   (pass a path instead: --zip C:\out\decrypted.zip)
```

```text
header len   : 16
signature    : 5250474d56000000
version      : 000301
remain       : 0000000000
rpg maker    : MV
recursive    : yes
output dir   : C:\out
key          : 1234567890abcdef1234567890abcdef (detected in C:\Games\MyGame\www\data\System.json (read from the plain JSON file))
OK  C:\Games\MyGame\www\audio\se\beep.rpgmvo -> C:\out\beep.ogg (1.0 KiB)
OK  C:\Games\MyGame\www\img\pictures\hero.rpgmvp -> C:\out\hero.png (73 B)
ZIP  C:\out\decrypted.zip (2 files, 559 B)
2 processed
```

加 `-v` 时，每个文件那一行会显示完整路径，并先打印解析出的头设置；不加时只显示文件名。

```powershell
# the key from a file (first line), and only the summary on stdout
.\.venv\Scripts\python.exe -m rpgmv_decrypter decrypt --key-file C:\keys\mygame.txt -q `
    "C:\Games\MyGame\www\audio\se" -o C:\out\se

# a game with a custom header: decrypt even though the header does not match
.\.venv\Scripts\python.exe -m rpgmv_decrypter decrypt -k 1234567890abcdef1234567890abcdef `
    --ignore-fake-header "C:\Games\MyGame\www\img"
```

如果伪头不匹配，该文件会被记为失败，整次运行以 `1` 退出 —— 只有在你确定这个文件确实是
加密文件时，才加 `--ignore-fake-header`：

```text
FAIL hero.rpgmvp: the fake header doesn't match the expected header; make sure the file is encrypted, or decrypt with ignore_fake_header=True
0 processed, 1 failed
```

### encrypt

```powershell
# .png -> .rpgmvp (MV, the default)
.\.venv\Scripts\python.exe -m rpgmv_decrypter encrypt -k 1234567890abcdef1234567890abcdef `
    "C:\Games\MyGame\www\img\pictures\hero.png" -o C:\out\mv

# .png -> .png_ (MZ)
.\.venv\Scripts\python.exe -m rpgmv_decrypter encrypt -k 1234567890abcdef1234567890abcdef `
    "C:\Games\MyGame\www\img\pictures\hero.png" --rpg-maker MZ -o C:\out\mz
```

```text
OK  hero.png -> hero.rpgmvp (89 B)
1 processed
OK  hero.png -> hero.png_ (89 B)
1 processed
```

加密后的文件比明文文件大 16 字节（就是那个伪头）。

### restore

```powershell
.\.venv\Scripts\python.exe -m rpgmv_decrypter restore "C:\Games\MyGame\www\img\pictures" -o C:\out\restored
```

```text
OK  hero.rpgmvp -> hero.png (73 B)
1 processed
```

不需要密钥；用 `-k`/`--key-file`/`--auto-key` 传进来的密钥会被接受但忽略（会打印一条
提示）。只有 `.rpgmvp` 和 `.png_` 会被还原 —— 音频会被跳过，因为它没有固定头可以重建。

### detect-key

```powershell
.\.venv\Scripts\python.exe -m rpgmv_decrypter detect-key "C:\Games\MyGame\www\data\System.json"
```

```text
1234567890abcdef1234567890abcdef
```

密钥是 stdout 上**唯一**的内容；说明写到 stderr：

```text
detected key in C:\Games\MyGame\www\data\System.json: read from the plain JSON file
```

所以它可以管道传递：

```powershell
$key = & .\.venv\Scripts\python.exe -m rpgmv_decrypter detect-key "C:\Games\MyGame"
.\.venv\Scripts\python.exe -m rpgmv_decrypter decrypt -k $key "C:\Games\MyGame\www\img" -o C:\out\img
```

它接受的来源：整个游戏目录、`System.json`、`rpg_core.js`（`this._encryptionKey = "..."`），
或者单张加密图片。

**`detect-key` 找不到密钥时，退出码为 `1`** —— 并把原因打印到 stderr。找不到密钥对它来说
是**正常的结果**而不是错误：成功时它只把密钥打到 stdout，所以可以直接管道传递（见上面的
例子），「没找到」并不代表用法用错了。

`decrypt` / `encrypt` 上的 `--auto-key` 在同样的情况下退出码为 `2`，因为这两个命令在开工
**之前**就必须拿到密钥，拿不到属于用法错误。

### info

```powershell
.\.venv\Scripts\python.exe -m rpgmv_decrypter info "C:\Games\MyGame\www\img\pictures\hero.rpgmvp"
```

```text
C:\Games\MyGame\www\img\pictures\hero.rpgmvp
  extension  : .rpgmvp -> plain .png (encrypted image, RPG Maker MV)
  size       : 89 B
  fake header: matches (5250474d560000000003010000000000)
  key        : 1234567890abcdef1234567890abcdef (recovered from the encrypted image header)
1 file(s) checked
```

`info` 从不写任何东西。给它一个目录，它会遍历该目录，并报告它能分类的每个资源和数据
文件（`.rpgmvp .rpgmvm .rpgmvo .png_ .ogg_ .m4a_ .png .ogg .m4a .json .txt .js`）。可以用
它在解密之前确认某个文件是否真的加密，或者看看哪种识别策略有效。

### 通用选项

| 选项                  | 适用命令                | 含义                                                                 |
| ----------------------- | ------------------------- | ----------------------------------------------------------------------- |
| `-k`, `--key HEX`       | decrypt, encrypt          | 密钥；只使用前 `--header-len` 个字节。                   |
| `--key-file PATH`       | decrypt, encrypt          | 从 `PATH` 的第一行读取密钥（兼容 BOM）。                   |
| `--auto-key`            | decrypt, encrypt          | 从给定路径识别密钥；识别失败时以 `2` 退出。       |
| `-o`, `--output-dir DIR`| 所有批量命令        | 把结果写入 `DIR`（不存在时创建）；默认写在每个输入文件旁边。 |
| `--zip [PATH]`          | decrypt, encrypt, restore | 额外写出一个包含所有成功输出的 ZIP。省略 `PATH` 时得到 `<output>/_zip/<name>.zip`。 |
| `--recursive` / `--no-recursive` | decrypt, encrypt, restore, info | 递归遍历目录（默认）或只处理一层。     |
| `--ignore-fake-header`  | decrypt                   | 即使头不匹配也解密。                             |
| `--rpg-maker {MV,MZ}`   | decrypt, encrypt          | 输出扩展名用哪个引擎的命名（加密时才有影响）。        |
| `--header-len N`        | 全部                       | 头长度，单位字节（默认 `16`）。                                   |
| `--signature HEX`       | 全部                       | 伪头 signature（默认 `5250474d56000000`）。                      |
| `--version HEX`         | 全部（子命令内） | 伪头 version（默认 `000301`）。                                  |
| `--remain HEX`          | 全部                       | 伪头 remain（默认 `0000000000`）。                            |
| `-q`, `--quiet`         | 全部                       | stdout 上只输出汇总；单个文件的问题仍然写到 stderr。        |
| `-v`, `--verbose`       | 全部                       | 每个文件一行、完整路径，外加解析出的设置。               |
| `-V`, `--version`       | 单独使用 / 放在子命令之前 | 打印包版本并退出。                                    |

> **`--version` 是两个不同的选项。** 放在子命令之前时，`--version`（或 `-V`）打印包的
> 版本号。放在子命令*内部*时，它设置伪头版本（`--version 000301`），和 `--signature`、
> `--remain` 完全一样。

### 退出码

| 代码  | 含义                                                                                   |
| ----- | ----------------------------------------------------------------------------------------- |
| `0`   | 所有被处理的文件都成功。被跳过的文件和「没有匹配到任何文件」都**不算**失败。 |
| `1`   | 至少有一个文件失败（例如头不匹配，或者 ZIP 写不出来）。 |
| `2`   | 用法或参数错误：路径不存在、密钥缺失/无效、头选项非法、`--auto-key` 什么都没找到。 |
| `130` | 被 Ctrl+C 中止。                                                                       |

```powershell
.\.venv\Scripts\python.exe -m rpgmv_decrypter info C:\Games\Nope\missing.rpgmvp
# error: path does not exist: C:\Games\Nope\missing.rpgmvp   (exit 2)
```

## Python API

库可以在字节、单个文件和整棵目录树上工作。完整契约（每个类、函数、dataclass 字段和
异常）冻结在 [`INTERFACE.md`](INTERFACE.md) 里；这里只是简版。

```python
from rpgmv_decrypter import (
    Decrypter,
    DecryptOptions,
    RpgMakerVersion,
    decrypt_paths,
    detect_key,
    encrypt_paths,
    restore_png_paths,
)

game = r"C:\Games\MyGame"

# 1) Find the encryption key (System.json, rpg_core.js or an encrypted image).
result = detect_key(game)
if not result.found:
    raise SystemExit(f"no key found: {result.detail}")
print(result.key, "-", result.description)

# 2) One file: decrypt next to the source (hero.rpgmvp -> hero.png).
Decrypter(result.key).decrypt_file(rf"{game}\www\img\pictures\hero.rpgmvp")

# 3) A whole tree, with an explicit output directory.
batch = decrypt_paths([rf"{game}\www\audio\se"], result.key, r"C:\out\se")
print(batch.summary())                     # e.g. "12 processed, 1 skipped"
for outcome in batch.outcomes:
    if not outcome.ok:
        print("failed:", outcome.source, outcome.error or outcome.reason)

# 4) Images without a key.
restore_png_paths([rf"{game}\www\img\pictures"], r"C:\out\img")

# 5) Re-encrypt for RPG Maker MZ - with custom header values if the game needs them.
options = DecryptOptions(
    header_len=16,                 # Decrypter._headerlength
    signature="5250474d56000000",  # Decrypter.SIGNATURE
    version="000301",              # Decrypter.VER
    remain="0000000000",           # Decrypter.REMAIN
    rpgmaker_version=RpgMakerVersion.MZ,
)
encrypt_paths([r"C:\out\img"], result.key, r"C:\out\mz", options=options)

# 6) Or let the library find the key itself (KeyNotFoundError when there is none).
decrypter = Decrypter.from_game_directory(game, ignore_fake_header=True)
print(decrypter.decrypt_file(rf"{game}\www\img\pictures\hero.rpgmvp", r"C:\out\hero.png"))
```

关于 API 的几个要点：

* `decrypt_file`、`encrypt_file` 和 `restore_png_file` 返回它们写出的 `pathlib.Path`；
  不给目标路径时，它们写在源文件旁边并转换扩展名。
* 批量辅助函数（`decrypt_paths`、`encrypt_paths`、`restore_png_paths`）不会因为单个坏
  文件而中止：每个输入产生一个 `FileOutcome`，带 `.ok`、`.error`、`.skipped` 和
  `.reason`，`RestoreResult.summary()` 给出一行式报告。
* 错误是分类型的（`rpgmv_decrypter.exceptions`）：`InvalidKeyError`、
  `InvalidFakeHeaderError`、`EmptyFileError`、`KeyNotFoundError`、
  `UnsupportedFormatError`，都派生自 `DecrypterError`。
* `Decrypter.decrypt_stream` / `encrypt_stream` 可以直接作用在文件对象上，用于不想把
  整个音频文件读进内存的场景。

## 工作原理

RPG Maker 的加密简单到可以完整描述 —— 逐字节的参考文档和完整算例在
[`docs/HEADER.md`](docs/HEADER.md) 里。

1. 明文文件的前 16 字节与游戏的 16 字节密钥做 XOR。
2. 一个 16 字节的**伪头**（`52 50 47 4d 56 00 00 00 00 03 01 00 00 00 00 00`，也就是
   `rpg_core.js` 里的十六进制字符串 `SIGNATURE` + `VER` + `REMAIN`）以**未加密**的形式
   加在最前面，好让游戏能认出自己的文件。
3. 前 16 字节之后的所有内容逐字节复制。

```text
plain      [ 16 bytes ][          rest of the file          ]
                | XOR key                    | copied unchanged
                v                            v
encrypted  [ fake header 16 ][ 16 bytes ][  rest of the file  ]
```

两个有用的推论：

* **图片可以不用密钥还原。** 每个 PNG 都以同样的已知 16 字节开头，所以去掉伪头、去掉那
  16 个被 XOR 的字节，再把标准 PNG 头放回去，就能重建文件 —— 对符合规范的 PNG 来说
  是完全精确的。
* **密钥可以从任意加密图片里恢复。** 第二个 16 字节块是 `plain_PNG_header XOR key`，
  而 PNG 头是常量，所以 `key = PNG_header XOR encrypted[16:32]`。

这就是 `detect_key()` 能只凭一个 `.rpgmvp`/`.png_` 文件找到密钥的原因，即使
`System.json` 和 `rpg_core.js` 都被混淆了。音频文件没有固定头，所以它们需要一个真正的
密钥来源。也只有前 16 字节被 XOR、后面的内容原样复制，所以**解密是可逆的**：改完素材
可以用同一把密钥重新加密回去。

## 项目结构

```text
RPG-Maker-MV-Decrepter-Python/
├── rpgmv_decrypter/          # the package: the only thing needed at runtime
│   ├── __init__.py           # public exports and __version__
│   ├── decrypter.py          # the XOR cipher: the Decrypter class
│   ├── filetypes.py          # extension/MIME mapping, RpgMakerVersion
│   ├── key_detect.py         # detect_key(), KeyDetector, DetectResult
│   ├── api.py                # batch helpers: decrypt_paths(), make_zip(), ...
│   ├── lzstring.py           # LZ-String decompression port (no compressor)
│   ├── exceptions.py         # DecrypterError and its subclasses
│   ├── cli.py                # argparse command line interface
│   ├── __main__.py           # `python -m rpgmv_decrypter`
│   ├── ui_logic.py           # UI-independent behaviour: validation, staging,
│   │                         #   RunResult/BatchRunner, output folders
│   ├── i18n.py               # the zh/en string table and tr() (default: zh)
│   ├── motion.py             # animation durations, easings and drivers
│   ├── gui.py                # the PySide6 desktop window (presentation only)
│   ├── gui_theme.py          # "liquid glass" design tokens + DWM backdrop
│   ├── switch.py             # the animated toggle control
│   ├── browse.py             # in-window browser for a run's results
│   └── assets/               # the project mark: .ico, .svg and .png sizes
├── launcher.py               # the entry point build_exe.py compiles
├── build_exe.py              # compiles dist/RPGMakerDecrypter with Nuitka
├── setup.py                  # installs the dependencies (and reports what is missing)
├── docs/
│   ├── HEADER.md             # the file format, byte by byte
│   └── COMPATIBILITY.md      # supported/unsupported, caveats
├── tests/                    # pytest suite and LZ-String test vectors
├── tools/                    # development and measurement scripts
├── verification/             # independent verification report and its harness
├── output/                   # GUI results: one <timestamp>/ folder per run
├── INTERFACE.md              # frozen API contract
├── pyproject.toml            # packaging, [gui] and [test] extras
├── pytest.ini                # pytest configuration (testpaths, pythonpath)
└── README.md
```

**发布版只包含运行和编译所需的部分**：`rpgmv_decrypter/`、`launcher.py`、`build_exe.py`、
`setup.py`、`pyproject.toml`、`docs/`、`INTERFACE.md`、`README.md`。
`tests/`、`tools/`、`verification/` 是开发与验证材料，不随发布版分发。


## 运行测试

```powershell
cd D:\UGit\RPG-Maker-MV-Decrepter-Python
.\.venv\Scripts\python.exe -m pytest -q
```

`pytest` 已经装在 `.venv` 里；测试配置在 `pytest.ini`（与 `pyproject.toml` 里的
`[tool.pytest.ini_options]` 保持一致）。测试套件是离线的，不需要任何游戏文件 —— 它会
自己构建 fixture。

> **注意**：测试套件留在**开发树**里，**不随发布版分发**。发布版只包含运行和编译所需的部分。
> 这直接影响 CI 的形状，见下一节。

## 持续集成（GitHub Actions）

`.github/workflows/build.yml` 在每次 push、每个 PR、以及打版本 tag 时运行。

### 它做什么

| 任务 | 触发 | 做什么 |
| ---- | ---- | ------ |
| **build** | 每次 push / PR / 手动 | 装依赖 → **编译 exe** → **验证产物** → 打包 ZIP → 上传为 artifact |
| **release** | 只有推 `v*` tag | 同上，再把 ZIP 附到 GitHub Release |

### 为什么没有测试任务

这是**刻意的**：发布版不含 `tests/`，所以没有测试可跑，一个调用 pytest 的任务会在第一次
push 时就红。取而代之的是**验证产物** —— `python build_exe.py --check` 会：

1. 启动 exe，跑 `--cli --version`
2. **用 exe 真的做一次加解密往返**，比对字节是否与原文件一致
3. 以 offscreen 方式打开窗口，确认它能起来

这能抓到"构建坏了"（Qt 插件缺失、入口点错、文件布局找不到），**但它不等于测试套件**。
如果你以后把 `tests/` 加回仓库，请同时在 workflow 里加一个测试任务。

### 怎么用

**1. 日常：什么都不用做。** push 之后到仓库的 **Actions** 页看结果；绿了就说明编译得过、产物可用。

**2. 拿一个测试用的 exe：**

- 打开 **Actions** → 点最新一次成功的 run
- 页面底部 **Artifacts** → 下载 `RPGMakerDecrypter-windows-x64`
- 得到 `RPGMakerDecrypter-1.0.0-windows-x64.zip`（约 27 MiB），解压后双击 exe

保留 14 天。

**3. 手动跑一次：** **Actions** → 左侧 `build` → 右上 **Run workflow** → 选分支 → Run。

**4. 发一个正式版本：**

```bash
# 版本号必须和 pyproject.toml 里的 version 一致，否则 release 任务会主动失败
git tag v1.0.0
git push origin v1.0.0
```

打 tag 后 `release` 任务会：编译 → 验证 → **核对 tag 与 `pyproject.toml` 的版本是否一致**
（不一致就停，避免"标签写一个版本、里面装另一个版本"）→ 打包 → 建 Release 并附上 ZIP。

**5. 本地先验一遍 workflow，不用推：**

```powershell
.\.venv\Scripts\python.exe tools\check_workflow.py
```

它会检查：YAML 能否解析、action 是否都锁了主版本号（且没停留在会触发 Node 弃用警告的旧版本）、
提到的文件是否存在、命令是否是 `setup.py` / `build_exe.py` 真有的开关、`steps.<id>` 与
`matrix.<name>` 是否都有定义，以及几条**工程不变量** —— 包括「只有 release 任务能写仓库」、
「没有 tag 不许发布」，和下面这条。

### 一个真实的构建约束

CI 里装 Nuitka 用的是：

```bash
python -m pip install --no-build-isolation setuptools wheel nuitka
```

**三个包必须一起装，不能只装 nuitka。** Nuitka 只发布源码包（sdist），而
`--no-build-isolation` 让 pip 用**当前环境**的后端去构建它 —— 那个后端就是 setuptools。少了它
pip 会直接停在：

```text
BackendUnavailable: Cannot import 'setuptools.build_meta'
```

`build_exe.py` 自己的安装器本来就是三个一起装，workflow 里那一步曾经只写了 `nuitka`，绕过了它。
现在两边一致，并且 `tools/check_workflow.py` 会**强制**这条配对：任何带
`--no-build-isolation` 的 pip 命令都必须同时出现 setuptools 和 wheel。

### 不需要配置任何东西

不用 secrets、不用 token、不用改仓库设置 —— 上传 Release 用的是 Actions 自带的
`GITHUB_TOKEN`。workflow 默认只有**只读**权限，只有 release 任务单独申请写权限。

### 关于打包方式

ZIP 由 `python build_exe.py --zip` 生成，用的是 Python 标准库的 `zipfile`，**不是**
`Compress-Archive` 也不是 `tar`。原因写在代码注释里：这两个都在本机失败过，而且失败原因与
归档本身无关（`Compress-Archive` 的进度条读不到控制台就崩；本机的 `tar.exe` 在写任何东西
之前就中止）。依赖宿主工具的发布步骤，就是一个会因为项目无法控制的原因而失败的步骤。这个
步骤还会**校验自己的产物**：CRC 检查 + 确认 exe 与 Qt 平台插件都在里面 —— 空包或截断的包
会在这里失败，而不是到用户手里才失败。

## 致谢

* [**Petschko**](https://github.com/Petschko) —— 原版
  [RPG-Maker-MV-Decrypter](https://github.com/Petschko/RPG-Maker-MV-Decrypter)（浏览器
  工具）的作者，也是本项目所记录的 `readKeyFromGame.js` 技巧的作者。本仓库是一个
  **非官方的 Python 重写版，与原作者没有隶属关系，也未经其背书或维护。**
* [**pieroxy**](https://github.com/pieroxy) ——
  [lz-string](https://github.com/pieroxy/lz-string) 的作者；
  `rpgmv_decrypter/lzstring.py` 是它的 `LZString._decompress` 的移植，测试向量是用参考
  实现生成的。
* 原项目致谢的那位匿名用户 —— 无密钥还原 PNG 的想法来自他。

原项目的完整贡献者名单（jszip、FileSaver.js、Bootstrap、r4sas……）请看原项目；这里没有
打包其中任何 JavaScript。

## 链接

* [原项目](https://github.com/Petschko/RPG-Maker-MV-Decrypter)
* [`INTERFACE.md`](INTERFACE.md) —— Python API 契约
* [`docs/HEADER.md`](docs/HEADER.md) —— 文件格式
* [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) —— 支持矩阵与注意事项
