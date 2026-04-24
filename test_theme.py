#!/usr/bin/env python3
"""主题切换功能测试"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QColor
from PyQt6.QtCore import QRect

# 简化的主题系统
LIGHT_THEME = {
    "bg_primary": "#FFFFFF",
    "bg_secondary": "#F8FAFC", 
    "primary": "#3B82F6",
    "text_primary": "#1E293B",
    "switch_track": "#CBD5E1",
    "switch_thumb": "#3B82F6",
}

DARK_THEME = {
    "bg_primary": "#0F0F14",
    "bg_secondary": "#1A1A2E",
    "primary": "#6366F1", 
    "text_primary": "#E2E8F0",
    "switch_track": "#2D2D4A",
    "switch_thumb": "#6366F1",
}

class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_theme = "light"
        self.themes = {"light": LIGHT_THEME, "dark": DARK_THEME}
    
    def get_current_theme(self):
        return self.themes[self.current_theme]
    
    def switch_theme(self, theme_name=None):
        if theme_name is None:
            self.current_theme = "dark" if self.current_theme == "light" else "light"
        else:
            if theme_name in self.themes:
                self.current_theme = theme_name
        
        self.theme_changed.emit(self.current_theme)
        return self.current_theme
    
    def get_color(self, color_name):
        return self.get_current_theme().get(color_name, "#000000")

class ModernSwitch(QWidget):
    toggled = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 26)
        self._is_checked = False
    
    def setChecked(self, checked):
        if self._is_checked != checked:
            self._is_checked = checked
            self.toggled.emit(checked)
            self.update()
    
    def isChecked(self):
        return self._is_checked
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._is_checked)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        theme = theme_manager.get_current_theme()
        
        # 轨道
        track_color = QColor(theme.get("switch_track", "#CBD5E1"))
        if self._is_checked:
            track_color = QColor(theme.get("primary", "#3B82F6"))
        
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        track_rect = self.rect()
        painter.drawRoundedRect(track_rect, 13, 13)
        
        # 拇指
        thumb_color = QColor(theme.get("switch_thumb", "#3B82F6"))
        if not self._is_checked:
            thumb_color = QColor("#94A3B8")
        
        painter.setBrush(thumb_color)
        thumb_x = self.width() - 24 if self._is_checked else 2
        thumb_rect = QRect(thumb_x, 3, 20, 20)
        painter.drawEllipse(thumb_rect)

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("主题切换测试")
        self.setGeometry(100, 100, 400, 200)
        
        # 连接主题信号
        theme_manager.theme_changed.connect(self.update_theme)
        
        # 构建界面
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # 主题切换区域
        theme_widget = QWidget()
        theme_layout = QHBoxLayout(theme_widget)
        theme_layout.setContentsMargins(0, 0, 0, 0)
        theme_layout.setSpacing(8)
        
        theme_label = QLabel("主题")
        theme_label.setStyleSheet(f"font-size: 13px; color: {theme_manager.get_color('text_primary')};")
        
        self.switch = ModernSwitch()
        self.switch.toggled.connect(self.on_theme_toggled)
        
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.switch)
        theme_layout.addStretch()
        
        layout.addWidget(theme_widget)
        
        # 测试标签
        self.test_label = QLabel("测试主题切换")
        self.test_label.setStyleSheet(f"font-size: 16px; color: {theme_manager.get_color('text_primary')};")
        layout.addWidget(self.test_label)
        
        self.update_theme()
    
    def on_theme_toggled(self, is_dark):
        try:
            if is_dark:
                theme_manager.switch_theme("dark")
            else:
                theme_manager.switch_theme("light")
        except Exception as e:
            print(f"主题切换错误: {e}")
    
    def update_theme(self):
        theme = theme_manager.get_current_theme()
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme['bg_primary']};
            }}
            QLabel {{
                color: {theme['text_primary']};
            }}
        """)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 全局主题管理器
    theme_manager = ThemeManager()
    
    window = TestWindow()
    window.show()
    
    sys.exit(app.exec())
