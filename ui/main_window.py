from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QTabWidget,
    QToolBox,
    QSpinBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.controller import RuntimeController
from ui.view_models import StatusViewModel


class CollapsibleBox(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.toggle_button = QPushButton(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setObjectName("collapsibleButton")
        self.toggle_button.toggled.connect(self._on_toggled)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(4, 4, 4, 4)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        self.content_area.setVisible(False)

    def _on_toggled(self, checked: bool) -> None:
        self.content_area.setVisible(checked)

    def addWidget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def addLayout(self, layout) -> None:
        self.content_layout.addLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self, controller: RuntimeController | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Desktop Automation Agent")
        self.controller = controller
        self._validation_active = False
        self.window_refresh_timer = QTimer(self)
        self.window_refresh_timer.setInterval(1500)
        self.window_refresh_timer.timeout.connect(self.refresh_window_catalog)

        container = QWidget()
        root_layout = QVBoxLayout(container)
        self.settings_tabs = QTabWidget()

        control_page = QWidget()
        control_layout = QVBoxLayout(control_page)

        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)

        controls = QHBoxLayout()
        self.window_selector = QComboBox()
        self.window_selector.setMinimumWidth(150)
        self.dry_run_checkbox = QCheckBox("Dry Run")
        self.start_button = QPushButton("Start/Resume")
        self.start_button.setObjectName("primaryButton")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.task_instructions_input = QLineEdit()
        self.task_instructions_input.setPlaceholderText("What should the app do? (e.g. 'Search for a music video on YouTube')")
        self.task_instructions_input.setMinimumHeight(35)
        self.task_instructions_input.setObjectName("taskInput")

        controls.addWidget(QLabel("Target Window:"))
        controls.addWidget(self.window_selector)
        controls.addWidget(self.dry_run_checkbox)
        controls.addStretch(1)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)

        task_row = QVBoxLayout()
        task_label = QLabel("Task Instructions")
        task_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        task_row.addWidget(task_label)
        task_row.addWidget(self.task_instructions_input)

        self.provider_selector = QComboBox()
        self.provider_selector.addItems(["gemini", "openai"])
        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("Model")
        self.model_validation_label = QLabel("")
        self.model_validation_label.setObjectName("validationLabel")
        self.openai_api_key_input = QLineEdit()
        self.openai_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.openai_api_key_input.setPlaceholderText("OpenAI API key")
        self.gemini_api_key_input = QLineEdit()
        self.gemini_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_api_key_input.setPlaceholderText("Gemini API key")
        self.provider_key_validation_label = QLabel("")
        self.provider_key_validation_label.setObjectName("validationLabel")
        self.confidence_spinbox = QSpinBox()
        self.confidence_spinbox.setRange(0, 100)
        self.cycle_interval_spinbox = QDoubleSpinBox()
        self.cycle_interval_spinbox.setRange(0.1, 60.0)
        self.cycle_interval_spinbox.setSingleStep(0.1)
        self.retry_spinbox = QSpinBox()
        self.retry_spinbox.setRange(1, 10)
        self.backoff_spinbox = QDoubleSpinBox()
        self.backoff_spinbox.setRange(0.0, 30.0)
        self.backoff_spinbox.setSingleStep(0.25)
        self.llm_max_width_spinbox = QSpinBox()
        self.llm_max_width_spinbox.setRange(256, 4096)
        self.llm_max_width_spinbox.setSingleStep(64)
        self.llm_max_height_spinbox = QSpinBox()
        self.llm_max_height_spinbox.setRange(256, 4096)
        self.llm_max_height_spinbox.setSingleStep(64)
        self.llm_jpeg_quality_spinbox = QSpinBox()
        self.llm_jpeg_quality_spinbox.setRange(30, 95)
        self.operator_goal_input = QLineEdit()
        self.operator_goal_input.setPlaceholderText("Operator goal")
        self.operator_goal_validation_label = QLabel("")
        self.operator_goal_validation_label.setObjectName("validationLabel")

        self.settings_groups = QToolBox()

        provider_group = QWidget()
        provider_layout = QVBoxLayout(provider_group)
        self.provider_help_label = QLabel("Provider and credentials used for vision analysis. API keys remain session-only unless you save them elsewhere.")
        self.provider_help_label.setWordWrap(True)
        provider_form = QFormLayout()
        provider_form.addRow("Provider", self.provider_selector)
        provider_form.addRow("Model", self._row_with_validation(self.model_input, self.model_validation_label))
        provider_form.addRow("OpenAI Key", self.openai_api_key_input)
        provider_form.addRow("Gemini Key", self.gemini_api_key_input)
        provider_form.addRow("Validation", self.provider_key_validation_label)
        provider_actions = QHBoxLayout()
        self.test_connection_button = QPushButton("Test Connection")
        self.connection_progress = QProgressBar()
        self.connection_progress.setRange(0, 0)
        self.connection_progress.setMaximumWidth(80)
        self.connection_progress.hide()
        self.settings_feedback_label = QLabel("Settings ready")
        provider_actions.addWidget(self.test_connection_button)
        provider_actions.addWidget(self.connection_progress)
        provider_actions.addWidget(self.settings_feedback_label)
        provider_actions.addStretch(1)
        provider_layout.addWidget(self.provider_help_label)
        provider_layout.addLayout(provider_form)
        provider_layout.addLayout(provider_actions)

        runtime_group = QWidget()
        runtime_layout = QVBoxLayout(runtime_group)
        self.runtime_help_label = QLabel("Adjust timing and retries for slower apps or flaky provider responses.")
        self.runtime_help_label.setWordWrap(True)
        runtime_form = QFormLayout()
        runtime_form.addRow("Confidence", self.confidence_spinbox)
        runtime_form.addRow("Interval", self.cycle_interval_spinbox)
        runtime_form.addRow("Retries", self.retry_spinbox)
        runtime_form.addRow("Backoff", self.backoff_spinbox)
        runtime_form.addRow("LLM Max Width", self.llm_max_width_spinbox)
        runtime_form.addRow("LLM Max Height", self.llm_max_height_spinbox)
        runtime_form.addRow("LLM JPEG Quality", self.llm_jpeg_quality_spinbox)
        runtime_layout.addWidget(self.runtime_help_label)
        runtime_layout.addLayout(runtime_form)

        automation_group = QWidget()
        automation_layout = QVBoxLayout(automation_group)
        self.automation_help_label = QLabel("Describe the operator goal so the model knows what outcome to look for.")
        self.automation_help_label.setWordWrap(True)
        automation_form = QFormLayout()
        automation_form.addRow("Goal", self._row_with_validation(self.operator_goal_input, self.operator_goal_validation_label))
        automation_layout.addWidget(self.automation_help_label)
        automation_layout.addLayout(automation_form)

        self.settings_groups.addItem(provider_group, "Provider")
        self.settings_groups.addItem(runtime_group, "Runtime")
        self.settings_groups.addItem(automation_group, "Automation")

        actions_row = QHBoxLayout()
        self.settings_state_label = QLabel("All changes saved")
        self.import_profile_button = QPushButton("Import Profile")
        self.export_profile_button = QPushButton("Export Profile")
        self.save_settings_button = QPushButton("Save")
        self.reset_settings_button = QPushButton("Reset")
        actions_row.addWidget(self.settings_state_label)
        actions_row.addStretch(1)
        actions_row.addWidget(self.import_profile_button)
        actions_row.addWidget(self.export_profile_button)
        actions_row.addWidget(self.save_settings_button)
        actions_row.addWidget(self.reset_settings_button)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("statusBadge")
        self.mode_label = QLabel("Dry Run")
        self.mode_label.setObjectName("modeBadge")
        self.last_action_label = QLabel("Waiting for action...")
        self.last_action_label.setObjectName("actionLabel")
        self.pinned_hwnd_label = QLabel("Pinned HWND: --")
        self.pinned_hwnd_label.setObjectName("debugBadge")
        self.result_label = QLabel("Result: --")
        self.result_label.setObjectName("resultBadge")
        self.confidence_label = QLabel("Confidence: --")
        self.reason_label = QLabel("Reason: --")
        self.error_label = QLabel("Error: --")
        self.error_label.setObjectName("errorBadge")
        self.copy_error_button = QPushButton("Copy Error")
        self.error_details_output = QPlainTextEdit()
        self.error_details_output.setReadOnly(True)
        self.error_details_output.setMaximumHeight(80)
        self.goal_inferred_label = QLabel("Goal: --")
        self.goal_completion_trend_label = QLabel("Completion trend: --")
        self.goal_completion_reasons_output = QPlainTextEdit()
        self.goal_completion_reasons_output.setReadOnly(True)
        self.goal_completion_reasons_output.setMaximumHeight(100)
        self.preview_label = QLabel("Screenshot preview unavailable")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(400)
        self.preview_label.setObjectName("previewLabel")
        
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)

        self.status_panel = QFrame()
        self.status_panel.setObjectName("statusPanel")
        status_layout = QVBoxLayout(self.status_panel)
        status_layout.addWidget(self.pinned_hwnd_label)
        status_layout.addWidget(self.result_label)
        status_layout.addWidget(self.confidence_label)
        status_layout.addWidget(self.reason_label)
        status_layout.addWidget(self.error_label)
        status_layout.addWidget(self.copy_error_button)
        status_layout.addWidget(self.error_details_output)

        self.goal_panel = QFrame()
        self.goal_panel.setObjectName("goalPanel")
        goal_layout = QVBoxLayout(self.goal_panel)
        goal_layout.addWidget(self.goal_inferred_label)
        goal_layout.addWidget(self.goal_completion_trend_label)
        goal_layout.addWidget(QLabel("Completion Reasoning:"))
        goal_layout.addWidget(self.goal_completion_reasons_output)

        # Build the main control layout
        top_bar = QHBoxLayout()
        top_bar.addWidget(self.status_label)
        top_bar.addWidget(self.mode_label)
        top_bar.addWidget(self.last_action_label, 1)

        preview_frame = QFrame()
        preview_frame.setObjectName("previewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview_label)

        details_box = CollapsibleBox("🔍 Advanced Details & Errors")
        details_box.addWidget(self.status_panel)
        details_box.addWidget(self.goal_panel)

        logs_box = CollapsibleBox("📝 Execution Logs")
        logs_box.addWidget(self.log_output)

        control_layout.addLayout(top_bar)
        control_layout.addSpacing(10)
        control_layout.addLayout(task_row)
        control_layout.addSpacing(10)
        control_layout.addWidget(preview_frame, 1)  # Expandable
        control_layout.addSpacing(10)
        control_layout.addLayout(controls)
        control_layout.addSpacing(10)
        control_layout.addWidget(details_box)
        control_layout.addWidget(logs_box)

        settings_layout.addWidget(self.settings_groups)
        settings_layout.addLayout(actions_row)
        settings_layout.addStretch(1)

        self.settings_tabs.addTab(control_page, "Control")
        self.settings_tabs.addTab(settings_page, "Settings")
        root_layout.addWidget(self.settings_tabs)

        self.setCentralWidget(container)
        self.setStyleSheet(
            """
            QMainWindow { background-color: #f7f9fc; }
            QTabWidget::pane { border: 1px solid #e2e8f0; border-radius: 8px; background: white; }
            QTabBar::tab { background: #edf2f7; border: 1px solid #e2e8f0; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: bold; color: #2b6cb0; }
            
            QPushButton { background-color: #edf2f7; border: 1px solid #cbd5e0; padding: 6px 16px; border-radius: 6px; color: #2d3748; font-weight: 600; }
            QPushButton:hover { background-color: #e2e8f0; }
            QPushButton#primaryButton { background-color: #3182ce; color: white; border: none; }
            QPushButton#primaryButton:hover { background-color: #2b6cb0; }
            QPushButton#collapsibleButton { text-align: left; background-color: transparent; border: 1px solid #e2e8f0; color: #4a5568; }
            QPushButton#collapsibleButton:checked { background-color: #edf2f7; border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
            
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 6px; border: 1px solid #cbd5e0; border-radius: 6px; background: white; }
            QLineEdit#taskInput { font-size: 14px; border: 2px solid #63b3ed; }
            
            #previewFrame { background: #2d3748; border-radius: 8px; }
            #previewLabel { color: #a0aec0; font-size: 16px; }
            
            #statusPanel { background: #fffaf0; border: 1px solid #fbd38d; border-radius: 8px; padding: 10px; }
            #goalPanel { background: #f0fff4; border: 1px solid #9ae6b4; border-radius: 8px; padding: 10px; margin-top: 8px; }
            
            #statusBadge { background: #c6f6d5; color: #22543d; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }
            #modeBadge { background: #e2e8f0; color: #4a5568; border-radius: 12px; padding: 4px 12px; font-weight: bold; font-size: 11px; }
            #actionLabel { color: #2d3748; font-size: 14px; font-weight: 500; padding: 0 10px; }
            
            #debugBadge { background: #edf2f7; color: #718096; border-radius: 6px; padding: 2px 6px; font-size: 10px; }
            #resultBadge { color: #2b6cb0; font-weight: 600; }
            #errorBadge { color: #e53e3e; font-weight: 600; }
            #validationLabel { color: #e53e3e; padding-left: 6px; font-size: 11px; }
            
            QPlainTextEdit { border: 1px solid #e2e8f0; border-radius: 6px; background: #f7fafc; color: #4a5568; font-family: monospace; }
            """
        )

        if self.controller is not None:
            self.bind_controller(self.controller)

    def bind_controller(self, controller: RuntimeController) -> None:
        self.controller = controller
        self.start_button.clicked.connect(controller.start)
        self.pause_button.clicked.connect(controller.pause)
        self.stop_button.clicked.connect(controller.stop)
        self.window_selector.currentIndexChanged.connect(self._on_window_selection_changed)
        self.provider_selector.currentTextChanged.connect(controller.set_provider)
        self.model_input.textChanged.connect(controller.set_model)
        self.openai_api_key_input.textChanged.connect(controller.set_openai_api_key)
        self.gemini_api_key_input.textChanged.connect(controller.set_gemini_api_key)
        self.confidence_spinbox.valueChanged.connect(controller.set_confidence_threshold)
        self.cycle_interval_spinbox.valueChanged.connect(controller.set_cycle_interval_seconds)
        self.retry_spinbox.valueChanged.connect(controller.set_max_retries)
        self.backoff_spinbox.valueChanged.connect(controller.set_retry_backoff_seconds)
        self.llm_max_width_spinbox.valueChanged.connect(controller.set_llm_max_width)
        self.llm_max_height_spinbox.valueChanged.connect(controller.set_llm_max_height)
        self.llm_jpeg_quality_spinbox.valueChanged.connect(controller.set_llm_jpeg_quality)
        self.operator_goal_input.textChanged.connect(controller.set_operator_goal)
        self.task_instructions_input.textChanged.connect(controller.set_operator_goal)
        self.dry_run_checkbox.toggled.connect(controller.set_dry_run)
        self.provider_selector.currentTextChanged.connect(self.mark_settings_dirty)
        self.model_input.textChanged.connect(self.mark_settings_dirty)
        self.openai_api_key_input.textChanged.connect(self.mark_settings_dirty)
        self.gemini_api_key_input.textChanged.connect(self.mark_settings_dirty)
        self.confidence_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.cycle_interval_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.retry_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.backoff_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.llm_max_width_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.llm_max_height_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.llm_jpeg_quality_spinbox.valueChanged.connect(self.mark_settings_dirty)
        self.operator_goal_input.textChanged.connect(self.mark_settings_dirty)
        self.task_instructions_input.textChanged.connect(self.mark_settings_dirty)
        self.dry_run_checkbox.toggled.connect(self.mark_settings_dirty)
        self.task_instructions_input.textChanged.connect(self._sync_goal_to_settings)
        self.operator_goal_input.textChanged.connect(self._sync_goal_to_control)
        self.copy_error_button.clicked.connect(self.copy_error_details)
        self.dry_run_checkbox.setChecked(controller.state.dry_run)
        controller.subscribe(self.apply_status_view_model)
        self.refresh_window_catalog()
        self.window_refresh_timer.start()
        self.update_validation_state()

    def apply_status_view_model(self, view_model: StatusViewModel) -> None:
        self.status_label.setText(view_model.status_label)
        self.mode_label.setText(view_model.mode_label)
        self.last_action_label.setText(f"Last action: {view_model.last_action or 'none'}")
        hwnd_text = "--" if view_model.selected_hwnd is None else str(view_model.selected_hwnd)
        self.pinned_hwnd_label.setText(f"Pinned HWND: {hwnd_text}")
        self.result_label.setText(f"Result: {view_model.result_text or '--'}")
        confidence_text = "--" if view_model.confidence is None else str(view_model.confidence)
        self.confidence_label.setText(f"Confidence: {confidence_text}")
        self.reason_label.setText(f"Reason: {view_model.reason_text or '--'}")
        self.error_label.setText(f"Error: {view_model.error_text or '--'}")
        self.error_details_output.setPlainText(view_model.error_text or "")
        self.goal_inferred_label.setText(f"Goal: {view_model.inferred_goal or '--'}")
        self.goal_completion_trend_label.setText(
            f"Completion trend: {self._format_completion_trend(view_model.completion_confidence_trend)}"
        )
        self.goal_completion_reasons_output.setPlainText(
            "\n".join(view_model.completion_reason_history) if view_model.completion_reason_history else "--"
        )
        self.dry_run_checkbox.setChecked(view_model.mode_label == "Dry Run")
        self._set_preview_image(view_model.preview_image)
        self.log_output.setPlainText("\n".join(view_model.log_lines))

    def _format_completion_trend(self, values: list[int]) -> str:
        if not values:
            return "--"
        tail = values[-8:]
        return " -> ".join(f"{value}%" for value in tail)

    def set_available_windows(self, window_titles: list[str] | list[dict[str, object]]) -> None:
        selected_hwnd = self.window_selector.currentData()
        selected_title = self.window_selector.currentText()

        normalized_items: list[tuple[str, object | None]] = []
        for item in window_titles:
            if isinstance(item, dict):
                title = str(item.get("title", ""))
                hwnd = item.get("hwnd")
                if title:
                    normalized_items.append((title, hwnd))
            else:
                title = str(item)
                if title:
                    normalized_items.append((title, None))

        self.window_selector.blockSignals(True)
        self.window_selector.clear()
        for title, hwnd in normalized_items:
            self.window_selector.addItem(title, hwnd)

        index_to_select = -1
        if selected_hwnd is not None:
            for idx in range(self.window_selector.count()):
                if self.window_selector.itemData(idx) == selected_hwnd:
                    index_to_select = idx
                    break
        if index_to_select == -1 and selected_title:
            index_to_select = self.window_selector.findText(selected_title)
        if index_to_select == -1 and self.window_selector.count() > 0:
            index_to_select = 0

        if index_to_select >= 0:
            self.window_selector.setCurrentIndex(index_to_select)

        self.window_selector.blockSignals(False)

        if index_to_select >= 0 and self.controller is not None:
            self.controller.set_selected_window(
                self.window_selector.itemText(index_to_select),
                self.window_selector.itemData(index_to_select),
            )

    def _row_with_validation(self, field: QWidget, label: QLabel) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field)
        layout.addWidget(label)
        return container

    def append_log(self, message: str) -> None:
        self.log_output.appendPlainText(message)

    def mark_settings_dirty(self, *_args) -> None:
        self._validation_active = True
        self.settings_state_label.setText("Unsaved changes")
        self.update_validation_state()

    def set_settings_dirty(self, is_dirty: bool) -> None:
        self.settings_state_label.setText("Unsaved changes" if is_dirty else "All changes saved")

    def reset_validation_state(self) -> None:
        self._validation_active = False
        self.model_validation_label.setText("")
        self.provider_key_validation_label.setText("")
        self.operator_goal_validation_label.setText("")
        self.save_settings_button.setEnabled(True)
        self.test_connection_button.setEnabled(True)

    def set_settings_feedback(self, message: str) -> None:
        self.settings_feedback_label.setText(message)

    def set_connection_testing(self, is_testing: bool) -> None:
        if is_testing:
            self.test_connection_button.setEnabled(False)
        else:
            self.update_validation_state()
        self.connection_progress.setVisible(is_testing)
        if is_testing:
            self.settings_feedback_label.setText("Testing connection...")

    def set_error_details(self, message: str) -> None:
        self.error_details_output.setPlainText(message)

    def copy_error_details(self) -> None:
        QApplication.clipboard().setText(self.error_details_output.toPlainText())

    def refresh_window_catalog(self) -> None:
        if self.controller is None:
            return
        window_items = self.controller.refresh_available_windows()
        if window_items:
            self.set_available_windows(window_items)

    def _on_window_selection_changed(self, index: int) -> None:
        if index < 0 or self.controller is None:
            return
        self.controller.set_selected_window(
            self.window_selector.itemText(index),
            self.window_selector.itemData(index),
        )
        self.mark_settings_dirty()

    def update_validation_state(self) -> None:
        model_error = ""
        provider_key_error = ""
        goal_error = ""

        if self._validation_active and not self.model_input.text().strip():
            model_error = "Model is required"
        provider = self.provider_selector.currentText().strip().lower()
        api_key = self.openai_api_key_input.text() if provider == "openai" else self.gemini_api_key_input.text()
        if self._validation_active and provider and not api_key.strip():
            provider_name = "OpenAI" if provider == "openai" else "Gemini"
            provider_key_error = f"{provider_name} API key is required to test the connection"
        if self._validation_active and not self.operator_goal_input.text().strip():
            goal_error = "Operator goal is required"

        self.model_validation_label.setText(model_error)
        self.provider_key_validation_label.setText(provider_key_error)
        self.operator_goal_validation_label.setText(goal_error)

        save_valid = not model_error and not goal_error
        connection_valid = save_valid and not provider_key_error
        self.save_settings_button.setEnabled(save_valid)
        if not self.connection_progress.isVisible():
            self.test_connection_button.setEnabled(connection_valid)

    def _sync_goal_to_settings(self, value: str) -> None:
        if self.operator_goal_input.text() == value:
            return
        blocker = QSignalBlocker(self.operator_goal_input)
        self.operator_goal_input.setText(value)
        del blocker

    def _sync_goal_to_control(self, value: str) -> None:
        if self.task_instructions_input.text() == value:
            return
        blocker = QSignalBlocker(self.task_instructions_input)
        self.task_instructions_input.setText(value)
        del blocker

    def _set_preview_image(self, preview_image) -> None:
        if preview_image is None:
            self.preview_label.setText("Screenshot preview unavailable")
            self.preview_label.setPixmap(QPixmap())
            return
        image = preview_image.convert("RGB")
        data = image.tobytes("raw", "RGB")
        qimage = QImage(data, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimage.copy())
        scaled = pixmap.scaled(
            self.preview_label.size() if self.preview_label.size().width() > 0 else pixmap.size(),
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)
