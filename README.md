# 第七史诗神秘商店助手

面向 Windows 的纯鼠标桌面自动化工具，用于刷新《第七史诗》神秘商店并按价格识别目标物品。

## 功能

- 按窗口标题绑定模拟器
- 使用 Windows Graphics Capture 截取指定窗口
- 自动裁剪标题栏和窗口边框，只保留游戏客户区
- 使用客户区尺寸统一换算 OCR 区域和鼠标点击坐标
- RapidOCR 识别商品价格
- 自动购买、滚动和刷新
- 支持天空石预算、目标数量、停止按钮和停止热键
- 实时日志、运行统计和 CSV 历史记录

项目仅使用桌面鼠标控制。

## 运行要求

- Windows 10 或 Windows 11
- Python 3.11+
- 模拟器窗口不能最小化
- 系统需要允许 Python 控制鼠标和监听停止热键

Windows Graphics Capture 可以直接抓取目标窗口，不再依赖桌面区域截图；窗口被普通窗口遮挡时通常仍可截图。鼠标点击仍然是桌面输入，因此运行时不要移动、最小化模拟器或让其他窗口抢占点击位置。

## 安装与启动

```bash
pip install -r requirements.txt
python E7SecretShopRefresh.py
```

## 使用方法

1. 启动游戏和模拟器。
2. 选择或输入完整的模拟器窗口标题。
3. 选择要购买的物品，并按需设置目标数量。
4. 设置天空石预算或至少一个目标数量。
5. 点击“开始刷新”。
6. 使用停止按钮或配置的热键结束运行。

程序默认会恢复模拟器窗口、按需移动到左上角并调整为 `906 x 539`。截图会进一步裁剪到窗口客户区，OCR 和点击坐标都基于客户区实时换算。

## 主要结构

- `E7SecretShopRefresh.py`：应用入口
- `app/ui/main_window.py`：界面、配置和运行状态
- `app/core/engine.py`：刷新循环、停止条件和统计
- `app/backends/mouse_backend.py`：鼠标点击、滚动和窗口操作
- `app/services/window_capture_service.py`：Windows Graphics Capture 截图与客户区裁剪
- `app/services/price_ocr_service.py`：价格区域裁剪与 OCR
- `app/core/history.py`：CSV 历史记录
- `app_config.ini`：应用设置

## 截图测试

模拟器窗口标题为“第七史诗”时，可运行：

```bash
python -m app.test.test
```

截图会保存为当前目录下的 `test.png`。

### item1–item6 区域调试

先让游戏停留在神秘商店顶部，然后运行：

```bash
python debug_item_regions.py
```

脚本只执行一次：截取 item1–4，向上滑动，等待 1 秒，再截取
item5–6。它不会购买或刷新。各区域截图、滑动前后的完整截图和 OCR
结果会写入 `debug_item_regions/时间戳/`。

## 打包

```bash
python -m PyInstaller -F --noconsole -i assets/gui_icon.ico E7SecretShopRefresh.py
```

## 注意事项

- 第一次使用建议设置较小预算，先确认 OCR 与点击位置。
- Windows Graphics Capture 依赖 `windows-capture`。
- `PySide6-Fluent-Widgets` 不要与其他 Qt 绑定版本的 Fluent 包混装。
