from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...config import AppSettings, SettingsStore


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, store: SettingsStore, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self._store = store

        self.api_key_edit = QLineEdit(settings.api_key)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.user_id_edit = QLineEdit(settings.user_id)

        self.website_username_edit = QLineEdit(settings.website_username)

        self.website_password_edit = QLineEdit(settings.website_password)
        self.website_password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.download_edit = QLineEdit(settings.download_directory or store.default_download_directory())
        self.download_browse_button = QPushButton("Browse")
        self.download_browse_button.clicked.connect(self._choose_directory)

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(1, 1000)
        self.page_size_spin.setValue(settings.page_size)

        self.flaresolverr_enabled_check = QCheckBox("Enable account favorites sync via FlareSolverr")
        self.flaresolverr_enabled_check.setChecked(settings.flaresolverr_enabled)

        self.flaresolverr_url_edit = QLineEdit(settings.flaresolverr_url)
        self.flaresolverr_url_edit.setPlaceholderText("http://127.0.0.1:8191")
        self.flaresolverr_url_edit.setEnabled(settings.flaresolverr_enabled)
        self.flaresolverr_enabled_check.toggled.connect(self.flaresolverr_url_edit.setEnabled)

        self.conflict_strategy_combo = QComboBox()
        self.conflict_strategy_combo.addItem("Merge local + remote", "merge")
        self.conflict_strategy_combo.addItem("Prefer local cache", "local_wins")
        self.conflict_strategy_combo.addItem("Prefer remote account", "remote_wins")
        selected_strategy = settings.sync_conflict_strategy or "merge"
        for index in range(self.conflict_strategy_combo.count()):
            if self.conflict_strategy_combo.itemData(index) == selected_strategy:
                self.conflict_strategy_combo.setCurrentIndex(index)
                break

        self.background_sync_interval_spin = QSpinBox()
        self.background_sync_interval_spin.setRange(0, 240)
        self.background_sync_interval_spin.setValue(max(0, int(settings.background_sync_interval_minutes)))
        self.background_sync_interval_spin.setSpecialValueText("Disabled")

        form = QFormLayout()
        form.addRow("User ID", self.user_id_edit)
        form.addRow("API key", self.api_key_edit)
        form.addRow("Website username", self.website_username_edit)
        form.addRow("Website password", self.website_password_edit)

        directory_row = QHBoxLayout()
        directory_row.addWidget(self.download_edit)
        directory_row.addWidget(self.download_browse_button)
        form.addRow("Download folder", directory_row)
        form.addRow("Results per page", self.page_size_spin)
        form.addRow(self.flaresolverr_enabled_check)
        form.addRow("FlareSolverr URL", self.flaresolverr_url_edit)
        form.addRow("Sync conflict strategy", self.conflict_strategy_combo)
        form.addRow("Background sync interval (minutes)", self.background_sync_interval_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

        self.resize(620, 340)

    def _choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose download folder", self.download_edit.text())
        if directory:
            self.download_edit.setText(directory)

    def current_settings(self) -> AppSettings:
        return AppSettings(
            user_id=self.user_id_edit.text().strip(),
            api_key=self.api_key_edit.text().strip(),
            website_username=self.website_username_edit.text().strip(),
            website_password=self.website_password_edit.text().strip(),
            download_directory=self.download_edit.text().strip(),
            page_size=self.page_size_spin.value(),
            flaresolverr_enabled=self.flaresolverr_enabled_check.isChecked(),
            flaresolverr_url=self.flaresolverr_url_edit.text().strip() or "http://127.0.0.1:8191",
            sync_conflict_strategy=str(self.conflict_strategy_combo.currentData() or "merge"),
            background_sync_interval_minutes=self.background_sync_interval_spin.value(),
        )
