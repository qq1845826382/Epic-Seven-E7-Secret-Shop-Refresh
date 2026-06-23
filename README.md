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

### ADB 模式

1. 在模拟器中开启 ADB
2. 确认游戏分辨率为 `1920 x 1080`
3. 打开程序并切换到 `ADB 模式`
4. 刷新设备列表，或手动输入地址连接
5. 选择要购买的物品，并设置预算或目标数量
6. 按需开启 `随机点击偏移` 或 `ADB 调试模式`
7. 点击 `开始刷新`

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
