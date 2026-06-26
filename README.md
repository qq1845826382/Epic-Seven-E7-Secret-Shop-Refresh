# 第七史诗神秘商店助手

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-lightgrey)
![License](https://img.shields.io/badge/License-GPL--3.0-green)

面向 Windows 的《第七史诗》神秘商店自动刷新工具。程序通过 Windows Graphics Capture 获取模拟器窗口画面，使用 RapidOCR 识别商品价格，再通过桌面鼠标完成购买、滚动和刷新。

`test` 分支已经删除 ADB 后端，目前只保留窗口截图与鼠标控制方案。

> 本项目仅用于学习和个人研究。自动化操作可能违反游戏或模拟器的使用条款，使用者应自行判断风险。

## 主要功能

- 根据完整窗口标题连接游戏或模拟器窗口
- 自动恢复窗口，可将窗口移动到屏幕左上角
- 将窗口外框调整为 `906 × 539`
- 使用 Windows Graphics Capture 捕获指定窗口
- 自动裁剪标题栏和边框，只保留客户区
- 按客户区实际尺寸缩放 OCR 区域与鼠标坐标
- 使用 RapidOCR 识别六个商品槽位的价格
- 自动购买、滚动和刷新神秘商店
- 支持天空石预算、商品目标数量、停止按钮和停止热键
- 实时显示刷新次数、资源消耗、购买数量和运行日志
- 保存 CSV 历史记录和异常调试截图
- 提供独立的 OCR 区域调试脚本

## 支持的商品

| 标识 | 商品 | 固定价格 | 默认启用 |
| --- | --- | ---: | :---: |
| `cov` | 圣约书签 | 184,000 金币 | 是 |
| `mys` | 神秘奖牌 | 280,000 金币 | 是 |
| `fb` | 友情书签 | 18,000 金币 | 否 |

当前版本不通过商品图标匹配物品，而是将 OCR 识别出的价格与固定价格进行比较。

## 运行流程

1. 初始化 RapidOCR，查找目标窗口并启动窗口捕获。
2. 恢复窗口，按配置移动窗口，并调整窗口尺寸。
3. 通过固定鼠标路径进入神秘商店。
4. 截取顶部页面，校验 `item_1` 到 `item_4` 的价格。
5. 匹配并购买启用的目标商品。
6. 向上滑动列表，识别 `item_5` 和 `item_6`。
7. 检查商品目标数量和天空石预算。
8. 点击刷新，消耗 3 天空石。
9. 校验刷新后的顶部价格，成功后进入下一轮。

### 购买校验

每次购买依次进行以下检查：

1. 购买前识别按钮区域，要求包含 `1/1`。
2. 双击购买区域。
3. 比较点击前后的全画面灰度均值差，默认阈值为 `40.0`。
4. 双击确认区域。
5. 再次识别按钮区域，要求包含 `0/1`。

单次购买最多重试 3 次。失败后会保存截图，等待 5 秒，点击窗口中心恢复，再重新尝试。

### 刷新校验

刷新后必须重新识别顶部四个价格槽位。校验失败时会保存截图、等待 5 秒、点击窗口中心并重新刷新，最多重试 3 次。

## 运行要求

- Windows 10 或 Windows 11
- Python 3.11+
- 游戏运行在窗口化模拟器或 Windows 客户端中
- 目标窗口不能最小化
- 系统允许 Python 控制鼠标和监听停止热键
- 游戏商店布局与当前固定坐标一致

程序会优先列出以下窗口标题：

- `第七史诗`
- `Epic Seven`
- `에픽세븐`
- `BlueStacks App Player`
- `LDPlayer`
- `MuMu Player 12`
- `Google Play Games on PC Emulator`

同时支持 `Epic Seven - ...` 和 `에픽세븐 - ...` 形式的标题。未自动识别的窗口可以手动输入完整标题。

## 安装

在 PowerShell 中执行：

```powershell
git clone https://github.com/qq1845826382/Epic-Seven-E7-Secret-Shop-Refresh.git
cd Epic-Seven-E7-Secret-Shop-Refresh
git switch test

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

主要依赖包括 PySide6、PySide6-Fluent-Widgets、RapidOCR、ONNX Runtime、OpenCV、PyAutoGUI、PyGetWindow、PyWin32、keyboard 和 windows-capture。

## 启动

```powershell
python E7SecretShopRefresh.py
```

界面使用 PySide6 和 QFluentWidgets，默认启用深色主题。

## 使用方法

1. 启动游戏，并让游戏窗口处于可操作状态。
2. 启动本程序。
3. 选择检测到的窗口，或手动输入完整窗口标题。
4. 设置窗口定位、鼠标速度和截图等待时间。
5. 勾选需要购买的商品。
6. 设置天空石预算或商品目标数量。
7. 点击“开始刷新”。
8. 需要结束时点击“停止刷新”或按停止热键。

至少需要启用一个商品，并设置一种停止条件：天空石预算或任一商品目标数量。

## 配置说明

### 天空石预算

预算只计算刷新消耗，不包含购买商品的金币。每次刷新消耗 3 天空石：

```text
最大刷新次数 = 天空石预算 // 3
```

建议填写 3 的倍数。预算为 0 表示不限制预算。

### 商品目标数量

- 大于 0：达到指定数量后参与停止判断。
- 等于 0：该商品不设数量上限。
- 所有设置了目标数量的商品都达到目标后，程序结束。

### 窗口尺寸

程序调用 `resizeTo(906, 539)` 调整的是整个窗口外框。标题栏、边框、DPI 和模拟器工具栏会占用空间，因此客户区尺寸通常小于 `906 × 539`。

程序会读取真实客户区尺寸并缩放 OCR 和点击坐标，不要求客户区恰好等于设置尺寸。

### 等待时间

- 鼠标速度：连续鼠标动作之间的等待时间，默认 `0.3` 秒。
- 截图等待：刷新动作后的额外等待时间，默认 `0.3` 秒。
- 模拟器响应慢或动画较长时，应适当增加等待时间。

### 停止热键

默认热键为 `esc`。程序通过独立线程轮询全局按键。部分系统环境可能需要更高权限才能监听全局热键，也可以直接使用界面的停止按钮。

## 配置文件

配置保存在项目根目录的 `app_config.ini`。程序启动时读取，开始刷新或关闭窗口时写回。

```ini
[general]
mouse_window_title = 第七史诗
auto_move_window = True
mouse_sleep = 0.3
screenshot_sleep = 0.3
stop_key = esc

[cov]
enabled = True
target_count = 1

[mys]
enabled = True
target_count = 0

[fb]
enabled = False
target_count = 0
```

天空石预算不会保存到配置文件，需要在界面中填写。

## OCR 与坐标缩放

OCR 区域和购买区域以 `1920 × 1080` 为基准坐标：

```text
scale_x = 客户区截图宽度 / 1920
scale_y = 客户区截图高度 / 1080
```

顶部阶段识别 `item_1` 到 `item_4`，滚动后识别 `item_5` 和 `item_6`。

OCR 预处理流程：

1. RGB 转灰度图。
2. 使用三次插值放大 3 倍。
3. 使用 `3 × 3` 高斯滤波。
4. 使用 Otsu 自动阈值二值化。
5. 转换为三通道图像并交给 RapidOCR。
6. 删除非数字字符，得到价格字符串。

如果分辨率、UI 缩放、语言版本或模拟器渲染方式发生变化，固定槽位可能需要重新标定。

## 窗口截图与鼠标限制

截图通过 `windows-capture` 调用 Windows Graphics Capture：

- 捕获目标窗口句柄，不是普通桌面区域截图。
- 自动裁剪窗口装饰，只返回客户区 RGB 图像。
- 普通窗口遮挡目标窗口时通常仍能获取目标画面。
- 窗口最小化时可能无法获取有效客户区。

鼠标操作使用 PyAutoGUI，仍然是桌面级输入。运行时不要移动鼠标、操作其他窗口，或让弹窗抢占点击位置。能够后台截图，不等于能够后台点击。

## 运行历史

每轮运行结束后会写入：

```text
ShopRefreshHistory/History.csv
```

文件使用 `UTF-8 with BOM` 编码，可直接用 Excel 打开。字段包括开始时间、运行时长、结束原因、错误信息、刷新次数、天空石消耗、金币消耗和各启用商品的购买数量。

`History.csv` 首次创建时，会根据当时启用的商品生成表头。

## OCR 区域调试

让游戏停留在神秘商店顶部，然后执行：

```powershell
python debug_item_regions.py --window-title "第七史诗"
```

自定义输出目录：

```powershell
python debug_item_regions.py `
  --window-title "第七史诗" `
  --output debug_item_regions
```

脚本不会购买或刷新，只会截取顶部与底部完整画面、六个价格区域和对应购买按钮区域，并在终端输出 OCR 结果。

结果保存在：

```text
debug_item_regions/YYYYMMDD_HHMMSS/
```

## 异常截图

购买校验或刷新校验失败时，程序会将图片保存到：

```text
debug_captures/YYYYMMDD_HHMMSS_ffffff/
```

可能包含完整客户区截图、购买按钮区域和点击后的完整截图。排查 OCR 或点击问题时，应优先检查这些图片。

## 常见问题

### 找不到窗口

窗口标题必须完全匹配。先刷新窗口列表，仍未出现时，复制窗口标题并手动填写。

### 截图尺寸不是 906 × 539

`906 × 539` 是窗口外框尺寸，客户区需要扣除标题栏、边框和模拟器装饰，这是正常现象。

### 能截图但无法点击

Windows Graphics Capture 直接捕获窗口；PyAutoGUI 点击桌面坐标。运行时仍需保证窗口可交互并位于正确位置。

### 顶部价格识别失败

确认商店停留在顶部，并运行 `debug_item_regions.py` 检查 `item_1` 到 `item_4` 的裁剪图片是否完整覆盖价格。

### 无法识别 1/1 或 0/1

检查 `debug_captures` 中的按钮截图。如果区域偏移，需要修改 `PriceSlot` 的购买按钮坐标。

### 灰度变化不足

可能是点击位置偏移、窗口失去焦点、游戏卡顿或弹窗尚未出现。阈值位于：

```python
# app/backends/mouse_backend.py
GRAY_MEAN_DIFF_THRESHOLD = 40.0
```

## 项目结构

```text
Epic-Seven-E7-Secret-Shop-Refresh/
├─ E7SecretShopRefresh.py          # 程序入口
├─ app_config.ini                  # 持久化配置
├─ debug_item_regions.py           # OCR 调试脚本
├─ requirements.txt                # Python 依赖
├─ LICENSE                         # GPL-3.0
├─ assets/                         # 图标和商品图片
└─ app/
   ├─ bootstrap.py                 # Qt 应用启动与主题
   ├─ backends/
   │  ├─ base.py                   # 后端抽象接口
   │  └─ mouse_backend.py          # 鼠标操作、价格匹配和购买校验
   ├─ core/
   │  ├─ constants.py              # 路径、窗口标题和商品定义
   │  ├─ engine.py                 # 自动刷新主循环
   │  ├─ history.py                # CSV 历史记录
   │  └─ models.py                 # 配置和统计模型
   ├─ services/
   │  ├─ price_ocr_service.py      # OCR 槽位和预处理
   │  └─ window_capture_service.py # Windows Graphics Capture
   └─ ui/
      ├─ logging_bridge.py         # 日志与 Qt 信号桥接
      ├─ main_window.py            # 主界面和配置读写
      └─ workers.py                # QThread 工作线程
```

核心调用关系：

```text
E7SecretShopRefresh.py
  └─ MainWindow
      └─ RefreshWorker
          └─ RefreshEngine
              └─ MouseBackend
                  ├─ WindowCaptureService
                  └─ PriceOCRService
```

`BaseBackend` 仍保留抽象接口，但 `test` 分支当前只使用 `MouseBackend`。

## 修改商品或 OCR 槽位

商品和价格定义位于 `app/core/constants.py`，OCR 槽位位于 `app/services/price_ocr_service.py`。

每个 `PriceSlot` 包含价格裁剪区域和购买按钮范围，全部基于 `1920 × 1080` 坐标。修改后应先运行调试脚本，再使用小预算进行实际测试。

## 打包

基础 PyInstaller 命令：

```powershell
python -m PyInstaller `
  --name E7SecretShopRefresh `
  --onefile `
  --noconsole `
  --icon assets/gui_icon.ico `
  --add-data "assets;assets" `
  --collect-all rapidocr `
  E7SecretShopRefresh.py
```

生成文件位于 `dist/`。配置、历史记录和调试截图路径基于 `PROJECT_ROOT`，发布前需要验证打包环境中的写入位置和持久化行为。

## 许可证

本项目使用 [GNU General Public License v3.0](LICENSE)。分发修改版本时，需要遵守 GPL-3.0 的源代码公开和相同许可证要求。
