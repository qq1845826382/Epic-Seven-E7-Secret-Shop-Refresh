# 第七史诗神秘商店助手

基于 `PySide6 + QFluentWidgets` 的统一中文桌面应用，用于自动刷新《第七史诗》神秘商店。

## 功能概览

- 单窗口整合 `鼠标模式` 与 `ADB 模式`
- 全中文界面与提示
- 统一的预算停止、目标数量停止、实时日志、结果统计
- ADB 设备选择、地址连接、随机偏移、调试模式、配置保存
- 统一写入 `ShopRefreshHistory/UnifiedHistory.csv`

## 运行要求

- Python `3.11+`
- Windows
- 鼠标模式需要模拟器窗口可见
- ADB 模式需要模拟器开启 ADB，并保持游戏分辨率为 `1920 x 1080`
- 价格识别依赖 `RapidOCR + onnxruntime`，通过 Python 依赖安装，不需要单独安装 Tesseract

## 安装依赖

```bash
pip install -r requirements.txt
```

## 启动方式

### 统一 GUI 主入口

```bash
python E7SecretShopRefresh.py
```

- 默认进入 `鼠标模式`
- 可在窗口内切换到 `ADB 模式`

### 兼容旧 ADB 入口

```bash
python E7ADBShopRefresh.py
```

- 仍然打开同一个统一 GUI
- 默认直接切换到 `ADB 模式`

## 使用说明

### 鼠标模式

1. 启动游戏并打开神秘商店所在模拟器
2. 打开程序后选择 `鼠标模式`
3. 选择或输入模拟器窗口标题
4. 勾选要购买的物品，并按需填写目标数量
5. 设置预算或目标数量
6. 点击 `开始刷新`
7. 按界面中的停止按钮或热键结束

#### 鼠标模式运行前提

- 仅支持桌面窗口自动化，模拟器窗口必须处于可见状态，不能被其他窗口遮挡。
- 界面中的窗口标题必须能精确匹配系统窗口标题；如果列表没有识别到，可以手动输入完整标题。
- 默认会把模拟器窗口恢复、移动到屏幕左上角并缩放到 `906 x 539`，用于稳定截图坐标和点击坐标。
- 需要本机允许 Python 控制鼠标、读取屏幕截图和监听停止热键。
- 首次运行建议只勾选一个低风险物品或设置较小预算，确认识别和点击位置正常后再长期运行。

#### 鼠标模式业务流程

1. GUI 在 `app/ui/main_window.py` 中收集运行参数，生成 `RunConfig(mode="mouse")` 和购买物品列表。
2. `RefreshWorker` 在独立 `QThread` 中启动 `RefreshEngine`，避免刷新过程阻塞界面。
3. `RefreshEngine` 根据 `mode="mouse"` 创建 `MouseBackend`，将已选物品映射为目标价格字符串。
4. `MouseBackend.prepare()` 通过窗口标题查找模拟器窗口，恢复窗口、移动窗口、调整窗口尺寸并尝试激活窗口。
5. `MouseBackend.open_shop()` 按固定窗口比例点击，进入神秘商店页面。
6. 引擎开始循环执行：截图识别第一页价格 -> 购买命中的物品 -> 向下滚动商店 -> 截图识别第二页价格 -> 购买命中的物品 -> 点击刷新商店。
7. 每次刷新后统计刷新次数、天空石消耗、金币消耗和各物品购买数量，并实时回传到 GUI。
8. 达到预算、达到全部目标数量、用户点击停止按钮或按下停止热键后结束运行。
9. 结束后写入 `ShopRefreshHistory/UnifiedHistory.csv`，并在日志区输出本次汇总。

#### 鼠标模式关键代码位置

- `E7SecretShopRefresh.py`：统一 GUI 主入口，默认进入鼠标模式。
- `app/ui/main_window.py`：窗口标题选择、鼠标速度、截图等待、预算、目标数量等配置采集。
- `app/ui/workers.py`：在后台线程运行刷新任务，并把统计结果发回界面。
- `app/core/engine.py`：通用刷新循环、停止条件、统计、历史写入。
- `app/backends/mouse_backend.py`：鼠标模式的窗口绑定、截图、价格识别、点击购买、滚动和刷新动作。
- `app/services/price_ocr_service.py`：RapidOCR 价格识别、价格区域裁剪、OCR 文本清洗。
- `app/core/constants.py`：默认窗口标题、物品定义、模板目录等常量。
- `assets/`：界面展示使用的物品图片。

### ADB 模式

1. 在模拟器中开启 ADB
2. 确认游戏分辨率为 `1920 x 1080`
3. 打开程序并切换到 `ADB 模式`
4. 刷新设备列表，或手动输入地址连接
5. 选择要购买的物品，并设置预算或目标数量
6. 按需开启 `随机点击偏移` 或 `ADB 调试模式`
7. 点击 `开始刷新`

#### ADB 模式运行前提

- 模拟器必须开启 ADB 调试，并能通过内置 `adb.exe` 执行 `adb devices` 检测到设备。
- 如果设备没有自动出现，需要在界面中输入地址，例如 `localhost:5555`，点击 `连接地址` 后再刷新设备列表。
- 当前 ADB 模式只支持游戏截图分辨率 `1920 x 1080`；启动前会截图校验，分辨率不一致会直接停止。
- 如果同时连接多个 ADB 设备，必须在界面中明确选择一个设备。
- ADB 模式不依赖模拟器窗口是否可见，但游戏必须已经运行到可以点击进入神秘商店的状态。
- `ADB 调试模式` 会弹出带红框的截图预览，用于确认点击区域；无人值守运行时不建议开启。
- `随机点击偏移` 会在购买、确认、滑动、刷新等非固定点击点附近增加随机偏移，降低重复点击轨迹。

#### ADB 模式业务流程

1. GUI 在 `app/ui/main_window.py` 中收集设备、手动连接地址、点击等待、随机偏移、调试模式等配置，生成 `RunConfig(mode="adb")`。
2. `RefreshWorker` 在独立 `QThread` 中启动 `RefreshEngine`。
3. `RefreshEngine` 根据 `mode="adb"` 创建 `ADBBackend`，将已选物品映射为目标价格字符串。
4. `ADBBackend.prepare()` 如有手动地址先执行 `adb connect`，再读取 `adb devices`，确定目标设备。
5. `ADBBackend._check_screen_dimension()` 通过 `adb exec-out screencap -p` 截图并校验分辨率是否为 `1920 x 1080`。
6. `ADBBackend.open_shop()` 使用固定屏幕比例坐标执行 `adb shell input tap`，进入神秘商店页面。
7. 引擎开始循环执行：ADB 截图 -> OCR 识别第一页价格 -> 点击购买和确认 -> ADB 滑动商店 -> OCR 识别第二页价格 -> 点击购买和确认 -> 点击刷新和确认。
8. 每轮刷新完成后更新刷新次数、天空石消耗、金币消耗和物品数量；预算按每次刷新 `3` 天空石计算。
9. 达到预算、达到全部目标数量、用户停止或热键停止后结束，并写入统一历史文件。

#### ADB 模式关键代码位置

- `E7ADBShopRefresh.py`：兼容旧入口，启动同一个 GUI，但默认切换到 ADB 模式。
- `app/ui/main_window.py`：ADB 设备列表、手动连接、配置读取/保存、随机偏移和调试开关。
- `app/services/adb_service.py`：封装 `adb devices`、`adb connect`、`ADBconfig.ini` 读取和保存。
- `app/core/engine.py`：通用刷新循环、停止条件、统计、历史写入。
- `app/backends/adb_backend.py`：ADB 截图、分辨率校验、价格识别、点击、滑动、刷新和调试红框预览。
- `app/services/price_ocr_service.py`：RapidOCR 价格识别、价格区域裁剪、OCR 文本清洗。
- `app/core/constants.py`：ADB 路径、支持分辨率、物品定义、模板目录等常量。
- `adb-assets/platform-tools/adb.exe`：项目内置 ADB 可执行文件。
- `adb-assets/`：ADB 可执行文件及兼容旧资源。

## 功能模块说明

### UI 与任务调度

- `app/bootstrap.py` 创建 Qt 应用和主窗口。
- `app/ui/main_window.py` 负责所有界面控件、配置采集、配置保存、设备/窗口刷新、运行状态切换和日志展示。
- `app/ui/workers.py` 使用 `QThread` 包装刷新任务，避免执行自动化动作时卡住 GUI。
- `app/ui/logging_bridge.py` 把 Python 日志桥接到界面日志区。

### 通用刷新引擎

- `app/core/engine.py` 是两种模式共用的业务核心。
- 引擎只关心抽象动作：准备环境、打开商店、截图、识别物品、购买、滚动、刷新、清理。
- 具体动作由 `app/backends/base.py` 定义接口，由鼠标模式和 ADB 模式分别实现。
- 停止条件统一在引擎中处理：没有选择物品会拒绝启动；没有预算且没有目标数量会拒绝启动；运行中会检查目标数量、预算、停止按钮和停止热键。

### 识别与购买

- 可购买物品定义在 `app/core/constants.py` 的 `ITEM_DEFINITIONS`。
- 每个物品包含 key、模板文件名、中文名、英文名、金币价格和默认是否勾选。
- 识别使用 `RapidOCR + onnxruntime` 读取商店右侧金币价格。
- OCR 文本只保留数字；识别价格必须完全等于已勾选物品的金币价格才会购买。
- 命中价格后，backend 返回对应商品行的购买坐标，引擎调用 `buy_item()` 完成购买并累计金币消耗。
- 统计含义保持不变：代表程序识别到目标价格并执行购买点击，不额外校验服务器实际购买成功。

### 配置与历史

- `app_config.ini` 保存统一 GUI 的常用设置，例如模式、窗口标题、等待时间、停止热键和物品目标数量。
- `ADBconfig.ini` 保存旧 ADB 配置项，主要用于兼容读取/保存 ADB 点击等待、预算、停止热键、随机偏移和调试开关。
- `app/core/history.py` 负责把运行结果写入 `ShopRefreshHistory/UnifiedHistory.csv`。

## 配置与数据

- ADB 配置文件：`ADBconfig.ini`
- 应用界面配置：`app_config.ini`
- 运行历史：`ShopRefreshHistory/UnifiedHistory.csv`

## 打包

推荐打包统一 GUI 入口：

```bash
python -m PyInstaller -F --noconsole -i assets/gui_icon.ico E7SecretShopRefresh.py
```

如果仍需保留旧 ADB 文件名入口，也可以单独打包：

```bash
python -m PyInstaller -F --noconsole -i assets/gui_icon.ico E7ADBShopRefresh.py
```

## 注意事项

- 鼠标模式运行时不要遮挡模拟器窗口
- ADB 模式仅首版支持 `1920 x 1080`
- 第一次使用建议先用小预算或友情书签验证识别是否正确
- `PySide6-Fluent-Widgets` 不要与其他 Qt 绑定版本的 fluent 包混装
