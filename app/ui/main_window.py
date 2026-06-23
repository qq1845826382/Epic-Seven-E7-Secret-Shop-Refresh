from __future__ import annotations

import configparser
import logging
import re
from pathlib import Path

import pygetwindow as gw
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QAbstractSpinBox,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CardWidget, ComboBox, LineEdit, PrimaryPushButton, PushButton, SubtitleLabel, TitleLabel

from app.core.constants import APP_CONFIG_PATH, ASSETS_DIR, DEFAULT_MOUSE_SLEEP, DEFAULT_SCREENSHOT_SLEEP, DEFAULT_STOP_KEY, DEFAULT_TITLES, ITEM_DEFINITIONS, WINDOW_ICON_PATH
from app.core.models import ItemSelection, RunConfig, RunResult, RunStatistics
from app.services.adb_service import ADBService
from app.ui.logging_bridge import QtLogHandler
from app.ui.workers import RefreshWorker


class MainWindow(QMainWindow):
    def __init__(self, default_mode: str = "mouse", from_legacy_entry: bool = False):
        super().__init__()
        self.default_mode = default_mode
        self.from_legacy_entry = from_legacy_entry
        self.adb_service = ADBService()
        self.worker_thread: QThread | None = None
        self.worker: RefreshWorker | None = None
        self.item_controls: dict[str, dict[str, object]] = {}
        self.status_labels: dict[str, BodyLabel] = {}
        self.item_grid: QGridLayout | None = None
        self.item_cards: list[QWidget] = []
        self.item_grid_columns = 0
        self.item_count_grid: QGridLayout | None = None
        self.item_count_columns = 0
        self.latest_item_counts: dict[str, int] = {}

        self.logger = logging.getLogger("e7shop")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%H:%M:%S"))
        self.log_handler.emitter.message_logged.connect(self.append_log)
        if self.log_handler not in self.logger.handlers:
            self.logger.addHandler(self.log_handler)

        self.setWindowTitle("第七史诗神秘商店助手")
        # 默认窗口从原来的大尺寸收窄，避免启动后占用过多桌面空间；内容通过选项卡分组承载。
        self.resize(980, 720)
        self.setMinimumSize(640, 520)
        if WINDOW_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(WINDOW_ICON_PATH)))

        self._build_ui()
        self.load_app_config()
        self.load_adb_config(show_message=False)
        self.refresh_windows()
        self.refresh_devices()
        self.mode_combo.setCurrentIndex(0 if self.default_mode == "mouse" else 1)
        self.update_mode_ui()

        if self.from_legacy_entry:
            self.logger.info("当前从旧 ADB 入口进入，已自动切换到统一界面的 ADB 模式。")

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_header_card())

        # QTabWidget 将“运行前配置”和“运行中观察”拆开：
        # 1. 配置页只保留启动前需要处理的内容，减少首屏纵向堆叠。
        # 2. 运行页合并鼠标/ADB 的共同统计指标，切换模式后依然只看同一组刷新数据。
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)
        self.main_tabs.addTab(self._build_setup_tab(), "运行前")
        self.main_tabs.addTab(self._build_running_tab(), "运行中")
        root_layout.addWidget(self.main_tabs, 1)

    def _build_setup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        self.setup_layout = QVBoxLayout(scroll_content)
        self.setup_layout.setContentsMargins(4, 4, 4, 4)
        self.setup_layout.setSpacing(10)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        self.setup_layout.addWidget(self._build_general_card())
        self.setup_layout.addWidget(self._build_mode_card())
        self.setup_layout.addWidget(self._build_items_card())
        self.setup_layout.addStretch(1)
        return tab

    def _build_running_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_content = QWidget()
        running_layout = QVBoxLayout(scroll_content)
        running_layout.setContentsMargins(4, 4, 4, 4)
        running_layout.setSpacing(10)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        running_layout.addWidget(self._build_status_card())
        running_layout.addWidget(self._build_log_card(), 1)
        return tab

    def _build_header_card(self) -> QWidget:
        card = CardWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        title = TitleLabel("第七史诗神秘商店助手")
        subtitle = SubtitleLabel("PySide6 + QFluentWidgets 统一界面，支持鼠标模式与 ADB 模式一键切换")
        title.setWordWrap(True)
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _build_general_card(self) -> QWidget:
        card = self._create_card("基础设置", "启动前只保留通用停止条件与控制按钮，模式专属参数放到下方选项页。")
        form = QFormLayout()
        self._configure_form_layout(form)
        card.layout().addLayout(form)

        self.mode_combo = ComboBox()
        self.mode_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.mode_combo.addItems(["鼠标模式", "ADB 模式"])
        self.mode_combo.currentIndexChanged.connect(self.update_mode_ui)
        form.addRow("运行模式", self.mode_combo)

        self.budget_spin = self._create_int_spin(0, 100000000, special_text="不限", suffix=" 天空石")
        form.addRow("天空石预算", self.budget_spin)

        self.stop_key_input = LineEdit()
        self.stop_key_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stop_key_input.setText(DEFAULT_STOP_KEY)
        form.addRow("停止热键", self.stop_key_input)


        buttons = QHBoxLayout()
        self.start_button = PrimaryPushButton("开始刷新")
        self.stop_button = PushButton("停止刷新")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_refresh)
        self.stop_button.clicked.connect(self.stop_refresh)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addStretch(1)
        card.layout().addLayout(buttons)
        return card

    def _build_mode_card(self) -> QWidget:
        card = self._create_card("模式设置", "仅显示当前运行方式需要的参数，避免鼠标模式与 ADB 模式设置混在一起。")
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_mouse_page())
        self.mode_stack.addWidget(self._build_adb_page())
        card.layout().addWidget(self.mode_stack)
        return card

    def _build_mouse_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self._configure_form_layout(form)
        self.window_combo = ComboBox()
        self.window_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.window_title_input = LineEdit()
        self.window_title_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.window_combo.currentTextChanged.connect(self.window_title_input.setText)
        self.window_refresh_button = PushButton("刷新窗口列表")
        self.window_refresh_button.clicked.connect(self.refresh_windows)
        self.auto_move_checkbox = QCheckBox("自动将模拟器移动到左上角")
        self.auto_move_checkbox.setChecked(True)
        self.mouse_sleep_spin = self._create_double_spin(0.01, 10.0, DEFAULT_MOUSE_SLEEP, step=0.05, suffix=" 秒")
        self.screenshot_sleep_spin = self._create_double_spin(0.01, 10.0, DEFAULT_SCREENSHOT_SLEEP, step=0.05, suffix=" 秒")

        row = QHBoxLayout()
        row.addWidget(self.window_combo)
        row.addWidget(self.window_refresh_button)
        form.addRow("检测到的窗口", self._wrap_layout(row))
        form.addRow("窗口标题（可手输）", self.window_title_input)
        form.addRow("窗口定位", self.auto_move_checkbox)
        form.addRow("鼠标速度", self.mouse_sleep_spin)
        form.addRow("截图等待", self.screenshot_sleep_spin)
        layout.addLayout(form)
        return page

    def _build_adb_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self._configure_form_layout(form)
        self.device_combo = ComboBox()
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh_devices_button = PushButton("刷新设备")
        self.refresh_devices_button.clicked.connect(self.refresh_devices)
        device_row = QHBoxLayout()
        device_row.addWidget(self.device_combo)
        device_row.addWidget(self.refresh_devices_button)
        form.addRow("ADB 设备", self._wrap_layout(device_row))

        self.manual_address_input = LineEdit()
        self.manual_address_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.manual_address_input.setPlaceholderText("例如 localhost:5555")
        self.connect_device_button = PushButton("连接地址")
        self.connect_device_button.clicked.connect(self.connect_manual_device)
        address_row = QHBoxLayout()
        address_row.addWidget(self.manual_address_input)
        address_row.addWidget(self.connect_device_button)
        form.addRow("手动连接", self._wrap_layout(address_row))

        self.adb_tap_sleep_spin = self._create_double_spin(0.01, 10.0, 0.3, step=0.05, suffix=" 秒")
        self.random_offset_checkbox = QCheckBox("启用随机点击偏移")
        self.adb_debug_checkbox = QCheckBox("启用 ADB 调试模式")
        form.addRow("点击等待", self.adb_tap_sleep_spin)
        form.addRow("随机偏移", self.random_offset_checkbox)
        form.addRow("调试模式", self.adb_debug_checkbox)

        actions = QHBoxLayout()
        self.load_adb_button = PushButton("读取 ADB 配置")
        self.save_adb_button = PushButton("保存 ADB 配置")
        self.load_adb_button.clicked.connect(self.load_adb_config)
        self.save_adb_button.clicked.connect(self.save_adb_config)
        actions.addWidget(self.load_adb_button)
        actions.addWidget(self.save_adb_button)
        actions.addStretch(1)

        layout.addLayout(form)
        layout.addLayout(actions)
        return page

    def _build_items_card(self) -> QWidget:
        card = self._create_card("购买物品", "勾选要购买的物品；目标数量为 0 表示不设上限。卡片会按窗口宽度自动排列。")
        self.item_grid = QGridLayout()
        self.item_grid.setHorizontalSpacing(12)
        self.item_grid.setVerticalSpacing(14)
        card.layout().addLayout(self.item_grid)

        for item in ITEM_DEFINITIONS:
            item_card = CardWidget()
            item_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            item_layout = QHBoxLayout(item_card)
            item_layout.setContentsMargins(12, 12, 12, 12)
            item_layout.setSpacing(12)

            enabled_checkbox = QCheckBox()
            enabled_checkbox.setChecked(item.default_enabled)
            item_layout.addWidget(enabled_checkbox)

            icon_label = QLabel()
            icon_path = Path(ASSETS_DIR) / item.file_name
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap.scaled(54, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item_layout.addWidget(icon_label)

            text_container = QVBoxLayout()
            display_name = SubtitleLabel(item.display_name)
            price_label = BodyLabel(f"{item.english_name} | 价格：{item.price:,} 金币")
            display_name.setWordWrap(True)
            price_label.setWordWrap(True)
            text_container.addWidget(display_name)
            text_container.addWidget(price_label)
            item_layout.addLayout(text_container, 1)

            target_spin = self._create_int_spin(0, 99999999, special_text="不限")
            item_layout.addWidget(BodyLabel("目标数量"))
            item_layout.addWidget(target_spin)

            self.item_cards.append(item_card)
            self.item_controls[item.key] = {
                "checkbox": enabled_checkbox,
                "target": target_spin,
            }
        self._relayout_item_cards(2)
        return card

    def _build_status_card(self) -> QWidget:
        card = self._create_card("统一运行统计", "鼠标模式与 ADB 模式共用同一组刷新指标，便于对比最终结果。")
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        card.layout().addLayout(grid)

        labels = [
            ("当前模式", "mode"),
            ("刷新次数", "refresh_count"),
            ("天空石消耗", "skystone_spent"),
            ("金币消耗", "gold_spent"),
            ("剩余刷新", "remaining"),
            ("结束原因", "reason"),
        ]
        for row, (title, key) in enumerate(labels):
            grid.addWidget(BodyLabel(title), row, 0)
            value_label = BodyLabel("-")
            grid.addWidget(value_label, row, 1)
            self.status_labels[key] = value_label

        item_count_title = SubtitleLabel("获得统计")
        card.layout().addWidget(item_count_title)
        self.item_count_grid = QGridLayout()
        self.item_count_grid.setHorizontalSpacing(12)
        self.item_count_grid.setVerticalSpacing(12)
        card.layout().addLayout(self.item_count_grid)
        self._refresh_item_count_labels({})
        return card

    def _build_log_card(self) -> QWidget:
        card = self._create_card("运行日志", "实时显示流程日志、进度和结束结果。")
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(260)
        clear_button = PushButton("清空日志")
        clear_button.clicked.connect(self.log_output.clear)
        card.layout().addWidget(self.log_output)
        card.layout().addWidget(clear_button, alignment=Qt.AlignRight)
        return card

    def _create_int_spin(self, minimum: int, maximum: int, special_text: str = "", suffix: str = "") -> QSpinBox:
        # QSpinBox 是整数输入框。这里集中设置按钮、步进和宽度，避免不同位置的数值框表现不一致。
        # setButtonSymbols(UpDownArrows) 会强制显示上下箭头，修复部分主题下增减按钮不明显或无法点击的问题。
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(1)
        spin.setAccelerated(True)
        spin.setKeyboardTracking(False)
        spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        spin.setMinimumWidth(120)
        if special_text:
            # specialValueText 会在最小值时显示“无限/不限”，底层数值仍为 0，便于保存配置和停止条件判断。
            spin.setSpecialValueText(special_text)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _create_double_spin(self, minimum: float, maximum: float, value: float, step: float, suffix: str = "") -> QDoubleSpinBox:
        # QDoubleSpinBox 是小数输入框，用于等待时间等秒级参数；统一保留两位小数并禁用实时键盘追踪。
        # 禁用实时追踪可避免用户输入中间态（例如只输入小数点）时立即触发校验导致数值跳回。
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setAccelerated(True)
        spin.setKeyboardTracking(False)
        spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        spin.setMinimumWidth(120)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _create_card(self, title: str, description: str) -> CardWidget:
        card = CardWidget()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title_label = SubtitleLabel(title)
        description_label = BodyLabel(description)
        title_label.setWordWrap(True)
        description_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        return card

    def _wrap_layout(self, layout: QHBoxLayout) -> QWidget:
        wrapper = QWidget()
        wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.setContentsMargins(0, 0, 0, 0)
        wrapper.setLayout(layout)
        return wrapper

    def _configure_form_layout(self, form: QFormLayout) -> None:
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)

    def _item_grid_column_count(self) -> int:
        width = self.centralWidget().width() if self.centralWidget() else self.width()
        if width >= 1180:
            return 3
        if width >= 820:
            return 2
        return 1

    def _item_count_column_count(self) -> int:
        return 3 if self.width() >= 760 else 1

    def _relayout_item_cards(self, columns: int | None = None) -> None:
        if self.item_grid is None:
            return
        columns = columns or self._item_grid_column_count()
        if columns == self.item_grid_columns and self.item_grid.count() == len(self.item_cards):
            return

        while self.item_grid.count():
            self.item_grid.takeAt(0)

        for index, item_card in enumerate(self.item_cards):
            self.item_grid.addWidget(item_card, index // columns, index % columns)

        for column in range(3):
            self.item_grid.setColumnStretch(column, 1 if column < columns else 0)
        self.item_grid_columns = columns

    def _clear_layout(self, layout: QGridLayout | QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                self._clear_layout(child.layout())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout_item_cards()
        if self.item_count_grid is not None and self._item_count_column_count() != self.item_count_columns:
            self._refresh_item_count_labels(self.latest_item_counts)

    def update_mode_ui(self) -> None:
        index = self.mode_combo.currentIndex()
        self.mode_stack.setCurrentIndex(index)
        is_mouse = index == 0
        self.mouse_sleep_spin.setEnabled(is_mouse)
        self.screenshot_sleep_spin.setEnabled(is_mouse)
        self.adb_tap_sleep_spin.setEnabled(not is_mouse)
        self.status_labels["mode"].setText("鼠标模式" if is_mouse else "ADB 模式")

    def refresh_windows(self) -> None:
        available_titles = [title for title in gw.getAllTitles() if title.strip()]
        preferred = [title for title in DEFAULT_TITLES if title in available_titles]
        pattern = re.compile(r"^(Epic Seven|에픽세븐) - .+$")
        matched = [title for title in available_titles if pattern.fullmatch(title)]
        titles = []
        for title in preferred + matched:
            if title not in titles:
                titles.append(title)
        self.window_combo.clear()
        self.window_combo.addItems(titles)
        if titles and not self.window_title_input.text().strip():
            self.window_title_input.setText(titles[0])

    def refresh_devices(self) -> None:
        devices = self.adb_service.list_devices()
        self.device_combo.clear()
        self.device_combo.addItems(devices)
        if not devices:
            self.append_log("未检测到任何 ADB 设备。")
        else:
            self.append_log(f"已检测到 {len(devices)} 个 ADB 设备。")

    def connect_manual_device(self) -> None:
        address = self.manual_address_input.text().strip()
        if not address:
            self.show_error("请输入要连接的 ADB 地址。")
            return
        success, message = self.adb_service.connect_device(address)
        self.append_log(message or "ADB 连接命令已执行。")
        if success:
            self.refresh_devices()
        else:
            self.show_error("ADB 地址连接失败，请检查模拟器调试配置。")

    def collect_run_config(self) -> RunConfig:
        budget = self.budget_spin.value() or None
        mode = "mouse" if self.mode_combo.currentIndex() == 0 else "adb"
        return RunConfig(
            mode=mode,
            budget=budget,
            stop_key=self.stop_key_input.text().strip() or DEFAULT_STOP_KEY,
            mouse_window_title=self.window_title_input.text().strip(),
            auto_move_window=self.auto_move_checkbox.isChecked(),
            mouse_sleep=self.mouse_sleep_spin.value(),
            screenshot_sleep=self.screenshot_sleep_spin.value(),
            adb_device_id=self.device_combo.currentText().strip(),
            adb_manual_address=self.manual_address_input.text().strip(),
            adb_random_offset=self.random_offset_checkbox.isChecked(),
            adb_debug=self.adb_debug_checkbox.isChecked(),
            adb_tap_sleep=self.adb_tap_sleep_spin.value(),
            from_legacy_entry=self.from_legacy_entry,
        )

    def collect_selections(self) -> list[ItemSelection]:
        selections: list[ItemSelection] = []
        for item in ITEM_DEFINITIONS:
            controls = self.item_controls[item.key]
            target_spin: QSpinBox = controls["target"]
            selection = ItemSelection(
                item=item,
                enabled=controls["checkbox"].isChecked(),
                target_count=target_spin.value() or None,
            )
            selections.append(selection)
        return selections

    def start_refresh(self) -> None:
        config = self.collect_run_config()
        selections = self.collect_selections()

        if config.mode == "mouse" and not config.mouse_window_title:
            self.show_error("鼠标模式必须先选择或输入模拟器窗口标题。")
            return
        if not any(selection.enabled for selection in selections):
            self.show_error("请至少选择一个要购买的物品。")
            return
        if config.budget is None and not any(selection.target_count for selection in selections if selection.enabled):
            self.show_error("请至少设置一个停止条件：预算或目标数量。")
            return

        self.save_app_config()
        self.set_running_state(True)
        self.main_tabs.setCurrentIndex(1)
        self.append_log("准备开始新一轮刷新，已切换到运行中统计页。")

        self.worker_thread = QThread(self)
        self.worker = RefreshWorker(config=config, selections=selections, logger=self.logger)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.statistics_changed.connect(self.update_statistics)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.failed.connect(self.on_worker_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def stop_refresh(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()
            self.append_log("已发送停止请求，等待当前动作安全结束。")

    def on_worker_finished(self, result: RunResult) -> None:
        self.set_running_state(False)
        self.update_statistics(result.statistics)
        if result.error_message:
            self.show_error(result.error_message)
        self.append_log("本次运行已结束。")
        self.worker = None
        self.worker_thread = None

    def on_worker_failed(self, message: str) -> None:
        self.set_running_state(False)
        self.show_error(message)
        self.worker = None
        self.worker_thread = None

    def update_statistics(self, statistics: RunStatistics) -> None:
        self.status_labels["mode"].setText("鼠标模式" if statistics.mode == "mouse" else "ADB 模式")
        self.status_labels["refresh_count"].setText(str(statistics.refresh_count))
        self.status_labels["skystone_spent"].setText(str(statistics.skystone_spent))
        self.status_labels["gold_spent"].setText(f"{statistics.gold_spent:,}")
        remaining = "不限" if statistics.remaining_refresh_count is None else str(statistics.remaining_refresh_count)
        self.status_labels["remaining"].setText(remaining)
        self.status_labels["reason"].setText(statistics.stop_reason)
        self._refresh_item_count_labels(statistics.item_counts)

    def _refresh_item_count_labels(self, item_counts: dict[str, int]) -> None:
        if self.item_count_grid is None:
            return
        self.latest_item_counts = dict(item_counts)
        self._clear_layout(self.item_count_grid)

        columns = self._item_count_column_count()
        self.item_count_columns = columns
        for index, item in enumerate(ITEM_DEFINITIONS):
            panel = QWidget()
            panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            panel.setStyleSheet(
                """
                QWidget {
                    background-color: #1b1b1b;
                    border: 1px solid #3a3a3a;
                    border-radius: 8px;
                }
                QLabel {
                    background-color: transparent;
                    border: 0;
                }
                """
            )

            layout = QHBoxLayout(panel)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(12)

            icon_label = QLabel()
            icon_label.setFixedSize(48, 48)
            icon_label.setAlignment(Qt.AlignCenter)
            icon_path = Path(ASSETS_DIR) / item.file_name
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap.scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            layout.addWidget(icon_label)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            name_label = QLabel(item.display_name)
            name_label.setStyleSheet("color: #d8d8d8; font-size: 13px;")
            count_label = QLabel(str(item_counts.get(item.key, 0)))
            count_label.setStyleSheet("color: #ffffff; font-size: 24px; font-weight: 700;")
            text_layout.addWidget(name_label)
            text_layout.addWidget(count_label)
            layout.addLayout(text_layout, 1)

            self.item_count_grid.addWidget(panel, index // columns, index % columns)

    def set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.mode_combo.setEnabled(not running)

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def show_error(self, message: str) -> None:
        QMessageBox.critical(self, "错误", message)

    def save_adb_config(self) -> None:
        values = {
            "tap_sleep": str(self.adb_tap_sleep_spin.value()),
            "budget": str(self.budget_spin.value()),
            "stop_refresh_key": self.stop_key_input.text().strip() or DEFAULT_STOP_KEY,
            "random_offset": str(self.random_offset_checkbox.isChecked()),
            "debug": str(self.adb_debug_checkbox.isChecked()),
        }
        path = self.adb_service.save_config(values)
        self.append_log(f"ADB 配置已保存到：{path}")

    def load_adb_config(self, show_message: bool = True) -> None:
        values = self.adb_service.load_config()
        if not values:
            if show_message:
                self.append_log("未找到 ADB 配置文件，将使用当前界面设置。")
            return
        self.adb_tap_sleep_spin.setValue(float(values.get("tap_sleep", 0.3)))
        self.budget_spin.setValue(int(float(values.get("budget", 0))))
        self.stop_key_input.setText(values.get("stop_refresh_key", DEFAULT_STOP_KEY))
        self.random_offset_checkbox.setChecked(values.get("random_offset", "False").lower() == "true")
        self.adb_debug_checkbox.setChecked(values.get("debug", "False").lower() == "true")
        if show_message:
            self.append_log("已读取 ADB 配置。")

    def load_app_config(self) -> None:
        path = Path(APP_CONFIG_PATH)
        if not path.exists():
            return
        config = configparser.ConfigParser()
        config.read(path, encoding="utf-8")
        general = config["general"] if config.has_section("general") else {}
        self.mode_combo.setCurrentIndex(0 if general.get("mode", self.default_mode) == "mouse" else 1)
        self.window_title_input.setText(general.get("mouse_window_title", ""))
        self.auto_move_checkbox.setChecked(general.get("auto_move_window", "True").lower() == "true")
        self.mouse_sleep_spin.setValue(float(general.get("mouse_sleep", DEFAULT_MOUSE_SLEEP)))
        self.screenshot_sleep_spin.setValue(float(general.get("screenshot_sleep", DEFAULT_SCREENSHOT_SLEEP)))
        self.adb_tap_sleep_spin.setValue(float(general.get("adb_tap_sleep", 0.3)))
        self.stop_key_input.setText(general.get("stop_key", DEFAULT_STOP_KEY))
        self.manual_address_input.setText(general.get("adb_manual_address", ""))

        for item in ITEM_DEFINITIONS:
            if not config.has_section(item.key):
                continue
            section = config[item.key]
            self.item_controls[item.key]["checkbox"].setChecked(section.get("enabled", str(item.default_enabled)).lower() == "true")
            self.item_controls[item.key]["target"].setValue(int(section.get("target_count", "0")))

    def save_app_config(self) -> None:
        config = configparser.ConfigParser()
        config["general"] = {
            "mode": "mouse" if self.mode_combo.currentIndex() == 0 else "adb",
            "mouse_window_title": self.window_title_input.text().strip(),
            "auto_move_window": str(self.auto_move_checkbox.isChecked()),
            "mouse_sleep": str(self.mouse_sleep_spin.value()),
            "screenshot_sleep": str(self.screenshot_sleep_spin.value()),
            "adb_tap_sleep": str(self.adb_tap_sleep_spin.value()),
            "stop_key": self.stop_key_input.text().strip() or DEFAULT_STOP_KEY,
            "adb_manual_address": self.manual_address_input.text().strip(),
        }
        for item in ITEM_DEFINITIONS:
            config[item.key] = {
                "enabled": str(self.item_controls[item.key]["checkbox"].isChecked()),
                "target_count": str(self.item_controls[item.key]["target"].value()),
            }
        with Path(APP_CONFIG_PATH).open("w", encoding="utf-8") as file:
            config.write(file)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.save_app_config()
        if self.worker is not None:
            self.worker.request_stop()
        super().closeEvent(event)
