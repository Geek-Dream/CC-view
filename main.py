#!/usr/bin/env python3
"""Claude Code 桌面助手 — PyQt6 版本，跨平台兼容 (Windows/Mac/Linux)。"""
import sys
import os
import json
import uuid
import subprocess
import random
from datetime import datetime
import threading
import anyio

from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    PermissionResultAllow, PermissionResultDeny,
    SystemMessage, AssistantMessage, ResultMessage, StreamEvent,
    TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock,
)

try:
    import mistune
except ImportError:
    mistune = None

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QInputDialog,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QDialog, QFileDialog, QMessageBox, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, pyqtSlot, QPropertyAnimation, QEasingCurve, QPoint, QRect, QMetaObject, Qt as Qt_Type
from PyQt6.QtGui import QFont, QColor, QIcon, QPalette, QPainter, QTextOption

from claude_client import ClaudeClient

# ==================== 数据目录 ====================

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "conversations")
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 主题系统 ====================

# 深色主题（参考 Gemini/ChatGPT/Claude 暖灰风格）
DARK_THEME = {
    "bg_primary": "#212121",     # 暖灰 主背景/消息区（参考 ChatGPT/千问）
    "bg_secondary": "#1A1A1A",   # 深灰 侧边栏背景（比主背景略深，形成层次）
    "bg_card": "#2A2A2A",        # 卡片/气泡背景（比主背景略亮）
    "bg_input": "#2A2A2A",       # 输入框背景（同卡片，区分于消息区）
    "border": "#333333",         # 淡灰边框（暖色调）
    "border_focus": "#818CF8",   # 紫蓝聚焦边框
    "primary": "#818CF8",        # 紫蓝主题色（参考千问/Claude）
    "primary_hover": "#A5B4FC",  # 悬停色
    "red": "#EF4444",            # 停止/错误
    "red_hover": "#DC2626",
    "green": "#34D399",          # 翠绿（提高对比度）
    "green_hover": "#10B981",
    "orange": "#FBBF24",
    "purple": "#A78BFA",
    "teal": "#5EEAD4",
    "text_primary": "#EAEAEA",   # 亮灰主文字（接近白色，高对比）
    "text_secondary": "#A0A0A0", # 中灰次要文字
    "text_tertiary": "#666666",  # 弱提示
    "user_bubble": "#2A2A2A",    # 用户气泡（同卡片）
    "user_bubble_gradient_end": "#1A3A2A",  # 用户气泡渐变结束色（深绿）
    "user_text": "#EAEAEA",
    "ai_bubble": "#2A2A2A",      # AI 气泡（同卡片）
    "ai_text": "#EAEAEA",
    "system_bubble": "#3A2A1A",  # 系统气泡（暖棕色调）
    "system_text": "#FBBF24",
    "thinking_bg": "#1E1E1E",    # 思考块背景（比主背景略深）
    "thinking_border": "#333333",
    "switch_track": "#333333",   # Switch轨道
    "switch_thumb": "#818CF8",   # Switch按钮
    "switch_thumb_disabled": "#555555",
    "shadow": "rgba(0, 0, 0, 0.4)", # 阴影色
    "gradient_start": "#818CF8", # 渐变起始
    "gradient_end": "#A78BFA",   # 渐变结束
}

# 浅色主题（现代化高级设计）
LIGHT_THEME = {
    "bg_primary": "#FAFBFC",    # 极浅灰 主背景
    "bg_secondary": "#FFFFFF",  # 纯白 侧边栏背景
    "bg_card": "#FFFFFF",       # 纯白 卡片背景
    "bg_input": "#F8FAFC",      # 输入框背景
    "border": "#E5E7EB",        # 淡边框色
    "border_focus": "#6366F1",  # 紫蓝聚焦边框
    "primary": "#6366F1",       # 紫蓝主题色
    "primary_hover": "#818CF8", # 悬停色
    "red": "#EF4444",           # 停止/错误
    "red_hover": "#DC2626",
    "green": "#10B981",         # 翠绿成功
    "green_hover": "#059669",
    "orange": "#F59E0B",
    "purple": "#8B5CF6",
    "teal": "#14B8A6",
    "text_primary": "#111827",  # 深灰主文字
    "text_secondary": "#6B7280",# 中灰次要文字
    "text_tertiary": "#9CA3AF", # 浅灰弱提示
    "user_bubble": "#EEF2FF",   # 淡紫用户气泡
    "user_bubble_gradient_end": "#C7D2FE",  # 用户气泡渐变结束色（浅紫）
    "user_text": "#4338CA",
    "ai_bubble": "#F9FAFB",     # 极浅灰 AI 气泡
    "ai_text": "#111827",
    "system_bubble": "#FEF3C7", # 系统气泡
    "system_text": "#92400E",
    "thinking_bg": "#F3F4F6",   # 思考块背景
    "thinking_border": "#D1D5DB",
    "switch_track": "#D1D5DB",   # Switch轨道
    "switch_thumb": "#6366F1",   # Switch按钮
    "switch_thumb_disabled": "#9CA3AF",
    "shadow": "rgba(0, 0, 0, 0.05)", # 阴影色
    "gradient_start": "#6366F1", # 渐变起始
    "gradient_end": "#8B5CF6",   # 渐变结束
}

# ==================== 主题管理器 ====================

class ThemeManager(QObject):
    """主题管理器 - 负责主题切换和配色管理"""
    
    theme_changed = pyqtSignal(str)  # 主题变更信号
    
    def __init__(self):
        super().__init__()
        # 默认浅色主题
        self.current_theme = "light"
        self.themes = {
            "dark": DARK_THEME,
            "light": LIGHT_THEME
        }
    
    def get_current_theme(self):
        """获取当前主题配色"""
        return self.themes[self.current_theme]
    
    def switch_theme(self, theme_name=None):
        """切换主题"""
        if theme_name is None:
            # 自动切换到另一个主题
            self.current_theme = "dark" if self.current_theme == "light" else "light"
        else:
            if theme_name in self.themes:
                self.current_theme = theme_name
        
        # 更新全局THEME变量（兼容性）
        global THEME
        THEME = self.get_current_theme()
        
        # 发射主题变更信号
        self.theme_changed.emit(self.current_theme)
        return self.current_theme
    
    def get_color(self, color_name):
        """获取当前主题的指定颜色"""
        return self.get_current_theme().get(color_name, "#000000")

# 全局主题管理器实例
theme_manager = ThemeManager()

# 临时兼容性：为现有代码提供THEME变量
THEME = theme_manager.get_current_theme()

# ==================== 高级动画系统 ====================

class AnimationManager(QObject):
    """高级动画管理器 - 实现GSAP级别的动画效果"""
    
    animation_completed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.animations = []
        self.easing_curves = {
            'ease': QEasingCurve.Type.OutQuad,
            'ease-in': QEasingCurve.Type.InQuad,
            'ease-out': QEasingCurve.Type.OutQuad,
            'ease-in-out': QEasingCurve.Type.InOutQuad,
            'ease-back': QEasingCurve.Type.OutBack,
            'ease-elastic': QEasingCurve.Type.OutElastic,
            'ease-bounce': QEasingCurve.Type.OutBounce,
            'power2-in': QEasingCurve.Type.InCubic,
            'power2-out': QEasingCurve.Type.OutCubic,
            'power2-in-out': QEasingCurve.Type.InOutCubic,
            'power3-in': QEasingCurve.Type.InQuart,
            'power3-out': QEasingCurve.Type.OutQuart,
            'power3-in-out': QEasingCurve.Type.InOutQuart,
            'power4-in': QEasingCurve.Type.InQuint,
            'power4-out': QEasingCurve.Type.OutQuint,
            'power4-in-out': QEasingCurve.Type.InOutQuint,
            'sine': QEasingCurve.Type.OutSine,
            'circ': QEasingCurve.Type.OutCirc,
            'expo': QEasingCurve.Type.OutExpo,
        }
    
    def fade_in(self, widget, duration=300, easing='ease', callback=None):
        """淡入动画 — 使用 QTimer 步进，不使用 QGraphicsEffect。"""
        if not widget.isVisible():
            widget.show()
        self._step_opacity(widget, duration, 0.0, 1.0, callback)

    def _step_opacity(self, widget, duration, start_val, end_val, callback):
        """用 QTimer 步进改变 setWindowOpacity。"""
        steps = 16
        interval = max(16, duration // steps)
        step_val = (end_val - start_val) / steps
        current = [0]
        widget.setWindowOpacity(start_val)

        def tick():
            current[0] += 1
            if current[0] >= steps:
                widget.setWindowOpacity(end_val)
                timer.stop()
                if callback:
                    callback()
            else:
                widget.setWindowOpacity(start_val + current[0] * step_val)

        timer = QTimer(widget)
        timer.timeout.connect(tick)
        timer.start(interval)

    def fade_out(self, widget, duration=300, easing='ease', callback=None):
        """淡出动画 — 使用 QTimer 步进，不使用 QGraphicsEffect。"""
        self._step_opacity(widget, duration, 1.0, 0.0, callback)
    
    def slide_in(self, widget, direction='left', distance=100, duration=400, easing='ease-back', callback=None):
        """滑入动画"""
        original_pos = widget.pos()
        
        # 设置起始位置
        if direction == 'left':
            start_pos = QPoint(original_pos.x() - distance, original_pos.y())
        elif direction == 'right':
            start_pos = QPoint(original_pos.x() + distance, original_pos.y())
        elif direction == 'top':
            start_pos = QPoint(original_pos.x(), original_pos.y() - distance)
        elif direction == 'bottom':
            start_pos = QPoint(original_pos.x(), original_pos.y() + distance)
        else:
            start_pos = original_pos
        
        widget.move(start_pos)
        widget.show()
        
        # 创建位移动画
        animation = QPropertyAnimation(widget, b"pos")
        animation.setDuration(duration)
        animation.setStartValue(start_pos)
        animation.setEndValue(original_pos)
        animation.setEasingCurve(self.easing_curves.get(easing, QEasingCurve.Type.OutBack))
        
        if callback:
            animation.finished.connect(callback)
        
        animation.start()
        self.animations.append(animation)
        return animation
    
    def slide_out(self, widget, direction='right', distance=100, duration=400, easing='ease-in', callback=None):
        """滑出动画"""
        original_pos = widget.pos()
        
        # 计算结束位置
        if direction == 'left':
            end_pos = QPoint(original_pos.x() - distance, original_pos.y())
        elif direction == 'right':
            end_pos = QPoint(original_pos.x() + distance, original_pos.y())
        elif direction == 'top':
            end_pos = QPoint(original_pos.x(), original_pos.y() - distance)
        elif direction == 'bottom':
            end_pos = QPoint(original_pos.x(), original_pos.y() + distance)
        else:
            end_pos = original_pos
        
        animation = QPropertyAnimation(widget, b"pos")
        animation.setDuration(duration)
        animation.setStartValue(original_pos)
        animation.setEndValue(end_pos)
        animation.setEasingCurve(self.easing_curves.get(easing, QEasingCurve.Type.InQuad))
        
        if callback:
            animation.finished.connect(callback)
        
        animation.start()
        self.animations.append(animation)
        return animation
    
    def scale(self, widget, from_scale=0.0, to_scale=1.0, duration=400, easing='ease-back', callback=None):
        """缩放动画"""
        original_geometry = widget.geometry()
        center = widget.geometry().center()
        
        # 计算起始和结束几何体
        start_width = int(original_geometry.width() * from_scale)
        start_height = int(original_geometry.height() * from_scale)
        start_x = center.x() - start_width // 2
        start_y = center.y() - start_height // 2
        
        end_width = int(original_geometry.width() * to_scale)
        end_height = int(original_geometry.height() * to_scale)
        end_x = center.x() - end_width // 2
        end_y = center.y() - end_height // 2
        
        start_rect = QRect(start_x, start_y, start_width, start_height)
        end_rect = QRect(end_x, end_y, end_width, end_height)
        
        widget.setGeometry(start_rect)
        widget.show()
        
        animation = QPropertyAnimation(widget, b"geometry")
        animation.setDuration(duration)
        animation.setStartValue(start_rect)
        animation.setEndValue(end_rect)
        animation.setEasingCurve(self.easing_curves.get(easing, QEasingCurve.Type.OutBack))
        
        if callback:
            animation.finished.connect(callback)
        
        animation.start()
        self.animations.append(animation)
        return animation
    
    def bounce(self, widget, duration=600, callback=None):
        """弹跳动画 - 使用安全的动画方案"""
        # 检查widget是否正在动画中
        if hasattr(widget, '_animating') and widget._animating:
            return
        
        original_pos = widget.pos()
        widget._animating = True
        
        from PyQt6.QtCore import QSequentialAnimationGroup, QTimer
        
        # 延迟执行以确保widget准备好
        def safe_bounce():
            try:
                self._do_bounce(widget, original_pos, duration, callback)
            except Exception:
                widget._animating = False
                if callback:
                    callback()
        
        QTimer.singleShot(10, safe_bounce)
        
    def _do_bounce(self, widget, original_pos, duration, callback):
        """执行实际的弹跳动画"""
        try:
            from PyQt6.QtCore import QSequentialAnimationGroup
            
            group = QSequentialAnimationGroup()
            
            # 向上
            up1 = QPropertyAnimation(widget, b"pos")
            up1.setDuration(duration // 4)
            up1.setStartValue(original_pos)
            up1.setEndValue(QPoint(original_pos.x(), original_pos.y() - 30))
            up1.setEasingCurve(QEasingCurve.Type.OutQuad)
            
            # 向下
            down1 = QPropertyAnimation(widget, b"pos")
            down1.setDuration(duration // 4)
            down1.setStartValue(QPoint(original_pos.x(), original_pos.y() - 30))
            down1.setEndValue(QPoint(original_pos.x(), original_pos.y() + 10))
            down1.setEasingCurve(QEasingCurve.Type.InQuad)
            
            # 向上
            up2 = QPropertyAnimation(widget, b"pos")
            up2.setDuration(duration // 4)
            up2.setStartValue(QPoint(original_pos.x(), original_pos.y() + 10))
            up2.setEndValue(QPoint(original_pos.x(), original_pos.y() - 15))
            up2.setEasingCurve(QEasingCurve.Type.OutQuad)
            
            # 回到原位
            down2 = QPropertyAnimation(widget, b"pos")
            down2.setDuration(duration // 4)
            down2.setStartValue(QPoint(original_pos.x(), original_pos.y() - 15))
            down2.setEndValue(original_pos)
            down2.setEasingCurve(QEasingCurve.Type.InQuad)
            
            group.addAnimation(up1)
            group.addAnimation(down1)
            group.addAnimation(up2)
            group.addAnimation(down2)
            
            # 动画结束时清除状态
            def on_finished():
                widget._animating = False
                if callback:
                    callback()
            
            group.finished.connect(on_finished)
            
            group.start()
            self.animations.append(group)
        except Exception:
            widget._animating = False
            if callback:
                callback()
    
    def shake(self, widget, duration=400, callback=None):
        """摇晃动画"""
        # 检查widget是否正在动画中
        if hasattr(widget, '_animating') and widget._animating:
            return
        
        original_pos = widget.pos()
        widget._animating = True
        
        from PyQt6.QtCore import QSequentialAnimationGroup
        group = QSequentialAnimationGroup()
        
        # 摇晃序列
        positions = [
            QPoint(original_pos.x() - 10, original_pos.y()),
            QPoint(original_pos.x() + 10, original_pos.y()),
            QPoint(original_pos.x() - 8, original_pos.y()),
            QPoint(original_pos.x() + 8, original_pos.y()),
            QPoint(original_pos.x() - 5, original_pos.y()),
            QPoint(original_pos.x() + 5, original_pos.y()),
            QPoint(original_pos.x() - 2, original_pos.y()),
            QPoint(original_pos.x() + 2, original_pos.y()),
            original_pos
        ]
        
        for pos in positions:
            shake = QPropertyAnimation(widget, b"pos")
            shake.setDuration(duration // len(positions))
            shake.setStartValue(widget.pos() if group.animationCount() > 0 else original_pos)
            shake.setEndValue(pos)
            shake.setEasingCurve(QEasingCurve.Type.Linear)
            group.addAnimation(shake)
        
        # 动画结束时清除状态
        def on_finished():
            widget._animating = False
            if callback:
                callback()
        
        group.finished.connect(on_finished)
        
        group.start()
        self.animations.append(group)
        return group
    
    def stagger(self, widgets, animation_func, stagger_delay=100, **kwargs):
        """交错动画 - 为多个widget创建延迟执行的相同动画"""
        animations = []
        
        for i, widget in enumerate(widgets):
            delay = QTimer()
            delay.setSingleShot(True)
            delay.timeout.connect(lambda w=widget, a=animation_func, k=kwargs: a(w, **k))
            delay.start(i * stagger_delay)
            animations.append(delay)
        
        return animations
    
    def timeline(self, animations):
        """时间轴动画 - 顺序执行多个动画"""
        from PyQt6.QtCore import QSequentialAnimationGroup
        
        group = QSequentialAnimationGroup()
        
        for animation in animations:
            if isinstance(animation, (QPropertyAnimation, QSequentialAnimationGroup)):
                group.addAnimation(animation)
        
        group.start()
        self.animations.append(group)
        return group
    
    def parallel(self, animations):
        """并行动画 - 同时执行多个动画"""
        from PyQt6.QtCore import QParallelAnimationGroup
        
        group = QParallelAnimationGroup()
        
        for animation in animations:
            if isinstance(animation, (QPropertyAnimation, QSequentialAnimationGroup)):
                group.addAnimation(animation)
        
        group.start()
        self.animations.append(group)
        return group

# 全局动画管理器实例
animation_manager = AnimationManager()

# ==================== 自定义Switch组件 ====================

class ModernSwitch(QWidget):
    """现代化Switch开关组件 — 支持平滑滑动动画"""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 26)
        self._is_checked = False
        self._anim_value = 0  # 0=关闭, 1=打开
        self._anim_progress = 0.0  # 动画进度 0.0-1.0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._anim_step)

    def setChecked(self, checked):
        """设置开关状态（带动画）"""
        if self._is_checked != checked:
            self._is_checked = checked
            self._anim_progress = 0.0
            self._anim_timer.start(1)
            self.toggled.emit(checked)

    def isChecked(self):
        """获取开关状态"""
        return self._is_checked

    def _anim_step(self):
        """动画步进"""
        self._anim_progress += 0.12
        if self._anim_progress >= 1.0:
            self._anim_progress = 1.0
            self._anim_timer.stop()
        self.update()

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._is_checked)

    def paintEvent(self, event):
        """绘制Switch组件"""
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            theme = theme_manager.get_current_theme()

            # 绘制轨道
            track_color = QColor(theme.get("switch_track", "#CBD5E1"))
            if self._is_checked:
                track_color = QColor(theme.get("primary", "#3B82F6"))
            painter.setBrush(track_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect(), 13, 13)

            # 绘制拇指 — 平滑过渡位置
            thumb_color = QColor(theme.get("switch_thumb", "#3B82F6"))
            if not self._is_checked:
                thumb_color = QColor(theme.get("switch_thumb_disabled", "#94A3B8"))
            painter.setBrush(thumb_color)

            # 用 ease-out 缓动计算平滑位置
            progress = min(max(self._anim_progress, 0.0), 1.0)
            eased = 1.0 - (1.0 - progress) ** 3  # easeOutCubic
            thumb_x = int(2 + eased * (self.width() - 26))
            thumb_rect = QRect(thumb_x, 3, 20, 20)
            painter.drawEllipse(thumb_rect)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            pass

    def sizeHint(self):
        """推荐尺寸"""
        return self.size()

# ==================== 内置数据 ====================

PROMPT_TEMPLATES = {
    "代码审查": "请审查以下代码，指出潜在问题和改进建议：",
    "写单元测试": "请为以下代码编写完整的单元测试：",
    "解释代码": "请详细解释以下代码的工作原理：",
    "性能优化": "请分析以下代码的性能瓶颈并提供优化方案：",
    "生成文档": "请为以下代码生成清晰的中文注释和文档：",
}

AGENT_LIST = [
    ("general-purpose", "通用智能体 — 处理复杂多步任务"),
    ("Explore", "快速探索 — 搜索和查找代码"),
    ("Plan", "软件架构师 — 设计实现方案"),
]

SKILLS_LIST = [
    ("commit", "创建 git 提交"),
    ("review-pr", "审查拉取请求"),
    ("simplify", "审查代码质量并优化"),
    ("security-review", "安全审查"),
]


# ==================== 对话持久化 ====================

def save_conversation(conv_id, title, messages, session_id=None):
    filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
    data = {
        "id": conv_id,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": messages,
    }
    if session_id is not None:
        data["session_id"] = session_id
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_conversation(conv_id):
    filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== Diff 解析器 ====================

class DiffParser:
    """解析 git diff 输出，提取文件和行变更。"""

    @staticmethod
    def parse(diff_text):
        """解析 git diff 文本，返回结构化数据。

        返回:
            list of dict: [
                {
                    "file": "main.py",
                    "additions": 5,
                    "deletions": 2,
                    "hunks": [
                        {
                            "old_start": 10, "old_count": 3,
                            "new_start": 10, "new_count": 6,
                            "lines": [
                                {"type": "unchanged", "text": "def foo():"},
                                {"type": "added", "text": "    pass"},
                                {"type": "removed", "text": "    return"},
                            ]
                        }
                    ]
                }
            ]
        """
        files = []
        current_file = None
        current_hunk = None

        for line in diff_text.split("\n"):
            # 文件头：diff --git a/xxx b/xxx
            if line.startswith("diff --git"):
                if current_file:
                    files.append(current_file)
                # 提取文件名
                parts = line.split(" ")
                file_path = parts[-1][2:]  # 去掉 "b/"
                current_file = {
                    "file": file_path,
                    "additions": 0,
                    "deletions": 0,
                    "hunks": [],
                }
                current_hunk = None
                continue

            # 二进制文件跳过
            if "Binary files" in line:
                if current_file:
                    files.append(current_file)
                    current_file = None
                continue

            # Hunk 头：@@ -old_start,old_count +new_start,new_count @@
            if line.startswith("@@"):
                try:
                    m = line.split("@@")[1].strip()
                    old_part, new_part = m.split(" ")[:2]
                    old_start, old_count = DiffParser._parse_range(old_part)
                    new_start, new_count = DiffParser._parse_range(new_part)
                    current_hunk = {
                        "old_start": old_start,
                        "old_count": old_count,
                        "new_start": new_start,
                        "new_count": new_count,
                        "lines": [],
                    }
                    if current_file:
                        current_file["hunks"].append(current_hunk)
                except (IndexError, ValueError):
                    current_hunk = None
                continue

            # 内容行
            if current_hunk and line:
                if line[0] == "+":
                    current_hunk["lines"].append({"type": "added", "text": line[1:]})
                    if current_file:
                        current_file["additions"] += 1
                elif line[0] == "-":
                    current_hunk["lines"].append({"type": "removed", "text": line[1:]})
                    if current_file:
                        current_file["deletions"] += 1
                elif line[0] == " ":
                    current_hunk["lines"].append({"type": "unchanged", "text": line[1:]})

        # 最后一个文件
        if current_file:
            files.append(current_file)

        return files

    @staticmethod
    def _parse_range(s):
        """解析 '-10,5' -> (10, 5)"""
        s = s[1:]  # 去掉前缀符号
        if "," in s:
            start, count = s.split(",")
            return int(start), int(count)
        return int(s), 1

    @staticmethod
    def get_diff_text(file_path, working_dir=None):
        """执行 git diff 获取文本。"""
        try:
            cmd = ["git", "diff", "--no-color", "--", file_path]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=5,
            )
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, Exception):
            return ""

    @staticmethod
    def get_all_diffs(working_dir=None):
        """获取所有已修改文件的 diff。"""
        try:
            cmd = ["git", "diff", "--no-color"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=10,
            )
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, Exception):
            return ""

def list_conversations():
    convs = []
    if not os.path.exists(DATA_DIR):
        return convs
    for fname in sorted(os.listdir(DATA_DIR), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(DATA_DIR, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                convs.append(data)
            except Exception:
                pass
    return convs


# ==================== 后台工作线程 ====================

class GitWorker(QObject):
    """后台执行 git 命令，不阻塞 UI。"""
    files_ready = pyqtSignal(list)
    status_ready = pyqtSignal(dict)

    def __init__(self, project_dir=None):
        super().__init__()
        self.project_dir = project_dir or os.getcwd()

    @pyqtSlot()
    def fetch_files(self):
        try:
            r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, timeout=5, cwd=self.project_dir)
            if r.returncode == 0:
                files = [f for f in r.stdout.strip().split("\n") if f]
                self.files_ready.emit(files)
                return
        except Exception:
            pass
        self.files_ready.emit([])

    @pyqtSlot()
    def fetch_status(self):
        try:
            r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, cwd=self.project_dir)
            if r.returncode == 0:
                result = {"modified": [], "added": [], "deleted": []}
                for line in r.stdout.strip().split("\n"):
                    if not line:
                        continue
                    status = line[:2].strip()
                    path = line[3:]
                    if status in ("M", "MM"):
                        result["modified"].append(path)
                    elif status in ("A", "??"):
                        result["added"].append(path)
                    else:
                        result["deleted"].append(path)
                self.status_ready.emit(result)
                return
        except Exception:
            pass
        self.status_ready.emit({"modified": [], "added": [], "deleted": []})


SDK_SAFE_TOOLS = {
    "ToolSearch", "Glob", "Grep", "Read", "LSP",
    "ListMcpResourcesTool", "ReadMcpResourceTool",
    "TodoWrite", "TaskCreate", "TaskGet", "TaskUpdate", "TaskList",
    "TaskStop", "TaskOutput",
    "AskUserQuestion", "EnterPlanMode", "ExitPlanMode",
    "SendMessage", "Sleep",
}


class SDKClaudeWorker(QObject):
    """基于 claude-agent-sdk 的后台 Worker，支持真正的权限拦截。

    替代旧 ClaudeWorker（subprocess CLI 方案）。
    信号接口与旧类完全一致，MainWindow 无需改动。
    """
    chunk_ready = pyqtSignal(str)
    result_ready = pyqtSignal(str)
    session_ready = pyqtSignal(str)
    thinking_started = pyqtSignal()
    thinking_ready = pyqtSignal(str, int)
    status_update = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    stopped = pyqtSignal()
    tool_update = pyqtSignal(object)
    # 新增：权限请求信号（主线程弹出权限条后调用 set_permission_decision）
    permission_request = pyqtSignal(str, dict)

    def __init__(self, prompt, model, session_id=None, permission_mode="default", project_dir=None):
        super().__init__()
        self.prompt = prompt
        self.model = model
        self.session_id = session_id
        self.permission_mode = permission_mode or "default"
        self.project_dir = project_dir or os.getcwd()
        self._stop_requested = False
        self._permission_decision = None
        self._permission_event = threading.Event()
        # SDK 权限回调由 SDK 内部线程调用，需要桥接到 Qt 主线程
        self._client = None

    def stop(self):
        self._stop_requested = True
        if self._client:
            # interrupt 必须在 async 上下文中调用，这里只设标志位
            # 实际中断由 _async_run 循环检测
            pass

    def set_permission_decision(self, decision: str):
        """由主线程调用，设置权限决策并唤醒等待中的 can_use_tool 回调。"""
        self._permission_decision = decision
        self._permission_event.set()

    def run(self):
        anyio.run(self._async_run)

    async def _async_run(self):

        # can_use_tool 要求 prompt 为 AsyncIterable，不能是纯字符串
        async def prompt_stream():
            return
            yield {}

        options = ClaudeAgentOptions(
            model=self.model,
            cwd=self.project_dir,
            permission_mode=self.permission_mode,
            can_use_tool=self._can_use_tool,
            include_partial_messages=True,
        )
        if self.session_id:
            options.resume = self.session_id
            options.continue_conversation = True

        self._client = ClaudeSDKClient(options=options)
        try:
            await self._client.connect(prompt_stream)
            # 发送用户消息
            await self._client.query(self.prompt)
            # 接收响应
            async for msg in self._client.receive_response():
                if self._stop_requested:
                    await self._client.interrupt()
                    self.stopped.emit()
                    return
                await self._handle_message(msg)
        except Exception as e:
            print(f"[SDKClaudeWorker] 错误: {e}")
            self.error_occurred.emit(str(e))
        finally:
            await self._client.disconnect()
            self._client = None

    async def _handle_message(self, msg):
        """将 SDK 消息映射到现有信号。"""
        import time

        if isinstance(msg, SystemMessage):
            if msg.subtype == "init":
                sid = msg.data.get("session_id", "")
                model_info = msg.data.get("model", "")
                print(f"[SYSTEM] session={sid} model={model_info}")
                if sid:
                    self.session_ready.emit(sid)
            elif msg.subtype == "status":
                status_text = msg.data.get("status", "")
                if status_text:
                    self.status_update.emit(f"状态: {status_text}")
            elif msg.subtype == "api_retry":
                attempt = msg.data.get("attempt", 0)
                max_retries = msg.data.get("max_retries", 0)
                self.status_update.emit(f"接口重试: 第{attempt}/{max_retries}次")

        elif isinstance(msg, StreamEvent):
            event = msg.event
            event_type = event.get("type", "")

            if event_type == "message_start":
                self.status_update.emit("开始生成回复")

            elif event_type == "content_block_start":
                block = event.get("content_block", {})
                block_type = block.get("type", "")
                if block_type == "thinking":
                    self.thinking_started.emit()
                    self.status_update.emit("正在深度思考")
                elif block_type == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_params = block.get("input", {})
                    self.tool_update.emit({
                        "index": event.get("index", 0),
                        "tool": tool_name,
                        "params": tool_params,
                        "status": "running",
                        "time": time.time(),
                    })
                    self.status_update.emit(f"正在调用 {tool_name}")
                elif block_type == "text":
                    self.status_update.emit("正在组织输出")

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type = delta.get("type", "")
                if delta_type == "text_delta":
                    self.chunk_ready.emit(delta.get("text", ""))

            elif event_type == "content_block_stop":
                pass  # 思考/工具的完成信息在 AssistantMessage 中处理

        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    self.chunk_ready.emit(block.text)
                elif isinstance(block, ThinkingBlock):
                    self.thinking_ready.emit(block.thinking, 0)

        elif isinstance(msg, ResultMessage):
            if msg.is_error:
                self.error_occurred.emit(msg.result or "未知错误")
            else:
                self.result_ready.emit(msg.result or "")

    async def _can_use_tool(self, tool_name, input_data, context):
        # 安全工具自动放行
        if tool_name in SDK_SAFE_TOOLS:
            return PermissionResultAllow()

        # 构建权限摘要
        summary = f"权限申请：{tool_name}"
        if tool_name == "Write":
            fp = input_data.get("file_path", "")
            if fp:
                summary += f"\n{fp}"
        elif tool_name == "Bash":
            cmd = input_data.get("command", "")
            if cmd:
                summary += f"\n{cmd}"

        print(f"[SDKClaudeWorker] {summary}")

        # 通过 pyqtSignal 通知主线程弹出权限条
        # 注意：这里在 async 上下文中，pyqtSignal 会通过 Qt 的 queued connection
        # 自动桥接到主线程
        self._permission_decision = None
        self._permission_event.clear()
        self.permission_request.emit(tool_name, input_data)

        # 等待用户决策（超时 5 分钟）
        allowed = await anyio.to_thread.run_sync(
            lambda: self._permission_event.wait(timeout=300)
        )

        if allowed and self._permission_decision == "allow":
            return PermissionResultAllow()
        else:
            return PermissionResultDeny(message="用户拒绝权限")


class TitleWorker(QThread):
    """后台生成对话标题，单次独立请求，不加入 session。"""
    title_ready = pyqtSignal(str)

    def __init__(self, user_message, ai_reply):
        super().__init__()
        self.user_message = user_message
        self.ai_reply = ai_reply
        self._timeout = 30

    def run(self):
        try:
            prompt = (
                f"请用一句话总结以下对话内容，作为对话标题，不超过15个字。\n"
                f"只输出标题文本，不要解释，不要加任何标点符号。\n\n"
                f"User: {self.user_message[:300]}\n"
                f"Assistant: {self.ai_reply[:500]}"
            )
            cmd = [
                "claude", "-p", prompt,
                "--model", "haiku",
                "--no-session-persistence",
            ]
            print(f"[TitleWorker] 启动")
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self._timeout)
            title = proc.stdout.strip()
            # 清理：去掉 markdown 符号、引号、前后缀
            title = title.lstrip("#*`- ").strip().strip('"').strip("'").strip()
            # 只取第一行
            title = title.split("\n")[0].strip()
            if title and len(title) > 15:
                title = title[:15] + "…"
            if title:
                print(f"[TitleWorker] 生成标题: {title}")
                self.title_ready.emit(title)
            else:
                print(f"[TitleWorker] 未生成有效标题, returncode={proc.returncode}")
        except subprocess.TimeoutExpired:
            print(f"[TitleWorker] 超时（{self._timeout}s）")
        except Exception as e:
            print(f"[TitleWorker] 异常: {e}")


# ==================== Markdown 渲染 ====================

class MarkdownRenderer:
    """将 Markdown 文本转换为 Qt 可渲染的 HTML。"""

    @classmethod
    def to_html(cls, text, theme=None):
        """将 Markdown 文本转为 HTML 字符串。"""
        if not text or not text.strip():
            return ""
        if mistune is None:
            return cls._escape_html(text)
        try:
            # 使用 mistune v3 API
            md = mistune.create_markdown()
            html = md(text)
            return cls._style_html(html, theme)
        except Exception:
            return cls._escape_html(text)

    @classmethod
    def _style_html(cls, html, theme=None):
        """为 HTML 添加主题样式。"""
        if theme is None:
            theme = theme_manager.get_current_theme()

        bg_code = theme.get('bg_card', '#2A2A2A')
        bg_code_block = theme.get('bg_secondary', '#1A1A1A')
        border_code = theme.get('border', '#333333')
        text_primary = theme.get('text_primary', '#EAEAEA')
        text_secondary = theme.get('text_secondary', '#A0A0A0')
        primary = theme.get('primary', '#818CF8')
        green = theme.get('green', '#34D399')

        # 替换代码块样式
        html = html.replace('<code>', f'<code style="background-color:{bg_code}; padding:2px 5px; border-radius:4px; font-family:Menlo,Monaco,Courier,monospace; font-size:12px;">')
        html = html.replace('<pre><code>', f'<pre style="background-color:{bg_code_block}; padding:12px; border-radius:8px; overflow-x:auto; border:1px solid {border_code}; margin:8px 0;"><code style="background:none; padding:0;">')
        html = html.replace('</code></pre>', '</code></pre>')

        # 标题样式
        html = html.replace('<h1>', f'<h1 style="font-size:20px; font-weight:bold; margin:12px 0 8px 0; color:{text_primary};">')
        html = html.replace('<h2>', f'<h2 style="font-size:18px; font-weight:bold; margin:10px 0 6px 0; color:{text_primary};">')
        html = html.replace('<h3>', f'<h3 style="font-size:16px; font-weight:bold; margin:8px 0 4px 0; color:{text_primary};">')

        # 链接样式
        html = html.replace('<a ', f'<a style="color:{primary}; text-decoration:underline;" ')

        # 引用块
        html = html.replace('<blockquote>', f'<blockquote style="border-left:3px solid {primary}; padding-left:12px; margin:8px 0; color:{text_secondary};">')

        # 列表
        html = html.replace('<ul>', '<ul style="padding-left:20px; margin:6px 0;">')
        html = html.replace('<ol>', '<ol style="padding-left:20px; margin:6px 0;">')
        html = html.replace('<li>', f'<li style="margin:3px 0; color:{text_primary};">')

        # 水平线
        html = html.replace('<hr />', f'<hr style="border:none; border-top:1px solid {border_code}; margin:10px 0;" />')

        # 表格
        html = html.replace('<table>', f'<table style="border-collapse:collapse; margin:8px 0; width:100%;">')
        html = html.replace('<th>', f'<th style="border:1px solid {border_code}; padding:6px 10px; background-color:{bg_code_block}; font-weight:bold; color:{text_primary};">')
        html = html.replace('<td>', f'<td style="border:1px solid {border_code}; padding:6px 10px; color:{text_primary};">')
        html = html.replace('<tr>', '<tr>')
        html = html.replace('</tr>', '</tr>')

        return html

    @classmethod
    def _escape_html(cls, text):
        """简单的 HTML 转义（mistune 不可用时使用）。"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('\n', '<br>'))


# ==================== 消息气泡 ====================

class MessageRow(QWidget):
    """消息气泡，支持 Markdown 渲染的文字选择复制。"""

    def __init__(self, role, text, parent=None):
        super().__init__(parent)
        self.role = role
        self._thinking_dots = 0
        self._is_thinking = False
        self._raw_text = text  # 保存原始 Markdown 文本

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        # 不设置固定宽度，让内容自然撑开
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(0, 0, 0, 0)
        bubble_layout.setSpacing(0)

        prefix = {"user": "你", "assistant": "AI", "system": "系统"}.get(role, "?")
        prefix_label = QLabel(prefix)
        prefix_label.setStyleSheet("font-weight: bold; font-size: 11px; padding: 4px 10px 0 10px;")
        bubble_layout.addWidget(prefix_label)

        # 使用 QTextEdit 替代 QLabel，支持 HTML/Markdown 渲染
        content = QTextEdit()
        content.setReadOnly(True)
        content.setFrameShape(QTextEdit.Shape.NoFrame)
        content.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        content.setMinimumWidth(180)
        content.setMaximumWidth(550)
        # 去掉 QTextEdit 默认的内边距
        content.document().setDocumentMargin(0)
        # 初始用纯文本显示（流式输出期间不渲染 Markdown）
        content.setPlainText(text)
        content.setStyleSheet("font-size: 13px; padding: 4px 10px 8px 10px; background-color: transparent;")
        content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        bubble_layout.addWidget(content)

        # 样式 — 根据当前主题动态配色
        if role == "user":
            bubble.setStyleSheet(f"""
                #bubble {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {THEME['user_bubble']}, stop:1 {THEME['user_bubble_gradient_end']});
                    border-radius: 12px;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {THEME['user_text']}; background: transparent; }}
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        elif role == "system":
            bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {THEME['system_bubble']}; border-radius: 12px;
                    border: 1px solid #2D3A4A;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {THEME['system_text']}; background: transparent; }}
            """)
            layout.addWidget(bubble)
            layout.addStretch()
        else:
            bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {THEME['ai_bubble']}; border-radius: 12px;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {THEME['ai_text']}; background: transparent; }}
            """)
            layout.addWidget(bubble)
            layout.addStretch()

        self._content_label = content
        self._bubble = bubble
        self._prefix_label = prefix_label

        # 如果是 AI 消息，启动思考动画
        if role == "assistant" and text == "思考中...":
            self._start_thinking_animation()

    def _start_thinking_animation(self):
        """启动思考动画。"""
        self._is_thinking = True
        self._thinking_dots = 0
        self._thinking_timer = QTimer()
        self._thinking_timer.timeout.connect(self._update_thinking)
        self._thinking_timer.start(400)

    def _update_thinking(self):
        """更新思考动画。"""
        if not self._is_thinking:
            return
        self._thinking_dots = (self._thinking_dots + 1) % 4
        dots = "." * self._thinking_dots
        self._content_label.setPlainText(f"🤔 思考中{dots}")

    def _start_processing_animation(self, base_text):
        """启动处理中动画（转圈）。"""
        self._processing_base_text = base_text
        self._processing_idx = 0
        self._processing_frames = ["◐", "◓", "◑", "◒"]
        if hasattr(self, "_processing_timer") and self._processing_timer:
            self._processing_timer.stop()
        self._processing_timer = QTimer()
        self._processing_timer.timeout.connect(self._update_processing)
        self._processing_timer.start(160)

    def _stop_processing_animation(self):
        if hasattr(self, "_processing_timer") and self._processing_timer:
            self._processing_timer.stop()
            self._processing_timer = None

    def _update_processing(self):
        frame = self._processing_frames[self._processing_idx % len(self._processing_frames)]
        self._processing_idx += 1
        # 展示 "◐ 处理中：xxx"
        self._content_label.setPlainText(f"{frame} {self._processing_base_text}")

    def _type_next_char(self):
        """打字机动画：每次显示 2-3 个字符，加速打字效果。"""
        if not hasattr(self, '_target_text'):
            return
        self._displayed_chars += random.randint(2, 3)
        if self._displayed_chars >= len(self._target_text):
            # 动画完成，渲染 Markdown
            self._displayed_chars = len(self._target_text)
            self._raw_text = self._target_text
            html = MarkdownRenderer.to_html(self._target_text)
            if html:
                self._content_label.setHtml(html)
            else:
                self._content_label.setPlainText(self._target_text)
            if hasattr(self, '_type_timer'):
                self._type_timer.stop()
                del self._type_timer
            return
        # 动画期间用纯文本
        self._content_label.setPlainText(self._target_text[:self._displayed_chars])

    def update_text(self, text):
        """更新消息文字（用于流式输出）。"""
        if not hasattr(self, '_content_label'):
            return
        # 处理中状态：持续动画提示（正文开始前的过程态）
        if self.role == "assistant" and isinstance(text, str) and text.startswith("处理中："):
            base = text
            # 避免重复启动 timer
            current = getattr(self, "_processing_base_text", None)
            if current != base:
                self._start_processing_animation(base)
            return
        else:
            self._stop_processing_animation()
        # 停止思考动画
        if self._is_thinking:
            self._is_thinking = False
            if hasattr(self, '_thinking_timer'):
                self._thinking_timer.stop()
            # 开始打字机动画，从第一个字开始
            self._target_text = text
            self._displayed_chars = 0
            if hasattr(self, '_type_timer'):
                self._type_timer.stop()
            self._type_timer = QTimer()
            self._type_timer.timeout.connect(self._type_next_char)
            self._type_timer.start(20)
            return
        # 非思考状态，直接显示或继续动画
        current_plain = self._content_label.toPlainText()
        if text == current_plain:
            return
        if len(text) <= len(current_plain):
            # 更短的文本，直接用 HTML 渲染
            self._raw_text = text
            html = MarkdownRenderer.to_html(text)
            if html:
                self._content_label.setHtml(html)
            else:
                self._content_label.setPlainText(text)
            return
        # 新的更长文本，继续动画
        self._target_text = text
        if not hasattr(self, '_type_timer') or not self._type_timer.isActive():
            self._displayed_chars = len(current_plain)
            self._type_timer = QTimer()
            self._type_timer.timeout.connect(self._type_next_char)
            self._type_timer.start(20)

    def get_text(self):
        """获取当前显示的原始文本。"""
        if not hasattr(self, '_content_label'):
            return ""
        return getattr(self, '_raw_text', '') or self._content_label.toPlainText()

    def update_theme(self):
        """更新消息气泡主题。"""
        theme = theme_manager.get_current_theme()
        if not hasattr(self, '_bubble') or self._bubble is None:
            return

        if self.role == "user":
            self._bubble.setStyleSheet(f"""
                #bubble {{
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {theme['user_bubble']}, stop:1 {theme['user_bubble_gradient_end']});
                    border-radius: 12px;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {theme['user_text']}; background: transparent; }}
            """)
        elif self.role == "system":
            self._bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {theme['system_bubble']}; border-radius: 12px;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {theme['system_text']}; background: transparent; }}
            """)
        else:
            self._bubble.setStyleSheet(f"""
                #bubble {{
                    background-color: {theme['ai_bubble']}; border-radius: 12px;
                }}
                #bubble QLabel, #bubble QTextEdit {{ color: {theme['ai_text']}; background: transparent; }}
            """)

        if hasattr(self, '_prefix_label') and self._prefix_label is not None:
            self._prefix_label.setStyleSheet(
                f"font-weight: bold; font-size: 11px; padding: 4px 10px 0 10px; "
                f"color: {theme['text_primary']};"
            )

        # 重新渲染 Markdown（仅对动画已完成的 AI 消息）
        if self.role == "assistant" and hasattr(self, '_raw_text') and self._raw_text:
            if not hasattr(self, '_type_timer') or not self._type_timer.isActive():
                html = MarkdownRenderer.to_html(self._raw_text, theme)
                if html and hasattr(self, '_content_label') and self._content_label is not None:
                    self._content_label.setHtml(html)
            if hasattr(self, '_prefix_label') and self._prefix_label is not None:
                self._prefix_label.setStyleSheet(
                    f"font-weight: bold; font-size: 11px; padding: 4px 10px 0 10px; "
                    f"color: {theme['text_primary']};"
                )


class ThinkingBlock(QFrame):
    """可折叠的思考内容块。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        self.setObjectName("thinkingBlock")
        self._expanded = False
        self._entries = []
        self._total_duration_ms = 0
        self._in_progress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏（可点击）
        header = QFrame()
        header.setObjectName("thinkingHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(6)

        icon_label = QLabel("[思考]")
        icon_label.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(icon_label)

        self._title_label = QLabel("深度思考中")
        self._title_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {THEME['text_secondary']};")
        h_layout.addWidget(self._title_label)

        self._duration_label = QLabel("（用时 0毫秒）")
        self._duration_label.setStyleSheet(f"font-size: 12px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(self._duration_label)

        h_layout.addStretch()

        self._arrow_label = QLabel("▶")
        self._arrow_label.setStyleSheet(f"font-size: 10px; color: {THEME['text_tertiary']};")
        h_layout.addWidget(self._arrow_label)

        layout.addWidget(header)

        # 内容区（默认折叠）
        self._content_frame = QFrame()
        self._content_frame.setObjectName("thinkingContent")
        c_layout = QVBoxLayout(self._content_frame)
        c_layout.setContentsMargins(10, 0, 10, 8)
        c_layout.setSpacing(0)

        self._content_label = QTextEdit()
        self._content_label.setReadOnly(True)
        self._content_label.setFrameShape(QTextEdit.Shape.NoFrame)
        self._content_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_label.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self._content_label.setStyleSheet(f"font-size: 12px; color: {THEME['text_secondary']}; background-color: transparent;")
        self._content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        c_layout.addWidget(self._content_label)

        self._content_frame.setVisible(False)
        layout.addWidget(self._content_frame)

        # 样式 — 深色主题（无边框）
        self.setStyleSheet(f"""
            #thinkingBlock {{
                background-color: {THEME['thinking_bg']};
                border-radius: 10px; margin: 2px 0;
            }}
            #thinkingHeader {{ background-color: transparent; }}
            #thinkingContent {{ background-color: transparent; }}
        """)

        # 点击切换展开/折叠
        def toggle():
            self._expanded = not self._expanded
            self._content_frame.setVisible(self._expanded)
            self._arrow_label.setText("▼" if self._expanded else "▶")

        header.mousePressEvent = lambda e: toggle()
        self.append_entry(text, duration_ms)

    def append_entry(self, text, duration_ms):
        """追加一段思考内容。"""
        clean_text = (text or "").strip()
        if not clean_text:
            return
        self._entries.append({"text": clean_text, "duration_ms": max(0, int(duration_ms or 0))})
        self._total_duration_ms += max(0, int(duration_ms or 0))
        self._refresh_content()

    def set_in_progress(self, in_progress):
        """更新思考状态。"""
        self._in_progress = bool(in_progress)
        self._refresh_header()

    def _refresh_content(self):
        parts = []
        for idx, entry in enumerate(self._entries, start=1):
            parts.append(f"[第{idx}段 | 用时 {self._format_duration(entry['duration_ms'])}]")
            parts.append(entry["text"])
            parts.append("")
        raw_text = "\n".join(parts).strip()
        html = MarkdownRenderer.to_html(raw_text)
        if html:
            self._content_label.setHtml(html)
        else:
            self._content_label.setPlainText(raw_text)
        self._refresh_header()

    def _refresh_header(self):
        count = len(self._entries)
        if self._in_progress:
            self._title_label.setText(f"深度思考中（已记录{count}段）")
        else:
            self._title_label.setText(f"深度思考已完成（共{count}段）")
        self._duration_label.setText(f"（累计用时 {self._format_duration(self._total_duration_ms)}）")

    @staticmethod
    def _format_duration(ms):
        """格式化时间为 分/秒/毫秒。"""
        try:
            ms = int(ms or 0)
        except Exception:
            ms = 0
        if ms < 0:
            ms = 0
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        millis = ms % 1000

        parts = []
        if minutes > 0:
            parts.append(f"{minutes}分")
        if seconds > 0 or minutes > 0:
            parts.append(f"{seconds}秒")
        # 低于 1 秒时显示毫秒；否则只在有毫秒余数时显示
        if minutes == 0 and seconds == 0:
            parts.append(f"{millis}毫秒")
        elif millis > 0:
            parts.append(f"{millis}毫秒")
        return "".join(parts) if parts else "0毫秒"

    def update_theme(self):
        """更新思考块主题。"""
        theme = theme_manager.get_current_theme()
        self.setStyleSheet(f"""
            #thinkingBlock {{
                background-color: {theme['thinking_bg']};
                border-radius: 10px; margin: 2px 0;
            }}
            #thinkingHeader {{ background-color: transparent; }}
            #thinkingContent {{ background-color: transparent; }}
        """)
        if hasattr(self, '_title_label') and self._title_label is not None:
            self._title_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme['text_secondary']};")
        if hasattr(self, '_duration_label') and self._duration_label is not None:
            self._duration_label.setStyleSheet(f"font-size: 12px; color: {theme['text_tertiary']};")
        if hasattr(self, '_arrow_label') and self._arrow_label is not None:
            self._arrow_label.setStyleSheet(f"font-size: 10px; color: {theme['text_tertiary']};")
        if hasattr(self, '_content_label') and self._content_label is not None:
            self._content_label.setStyleSheet(f"font-size: 12px; color: {theme['text_secondary']}; background-color: transparent;")
            # 重新渲染 Markdown
            if hasattr(self, '_entries') and self._entries:
                self._refresh_content()


class ThinkingRow(QWidget):
    """思考行容器，包含一个 ThinkingBlock。"""

    def __init__(self, text, duration_ms, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)
        self._block = ThinkingBlock(text, duration_ms)
        layout.addWidget(self._block)
        layout.addStretch()

    def append_thinking(self, text, duration_ms):
        self._block.append_entry(text, duration_ms)

    def set_in_progress(self, in_progress):
        self._block.set_in_progress(in_progress)

    def update_theme(self):
        """更新思考行主题。"""
        if hasattr(self, '_block') and self._block is not None and hasattr(self._block, 'update_theme'):
            self._block.update_theme()


# ==================== DiffCard（代码对比卡片）====================

class DiffFileCard(QFrame):
    """单个文件的 diff 卡片（可折叠）。"""

    def __init__(self, file_info, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("diffFileCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        self._title_bar = QFrame()
        self._title_bar.setFixedHeight(36)
        self._title_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_card']};
                border-radius: 8px;
            }}
        """)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(12, 4, 12, 4)
        title_layout.setSpacing(8)

        # 折叠箭头
        self._arrow = QLabel("▶")
        self._arrow.setStyleSheet(f"color: {THEME['text_tertiary']}; font-size: 12px;")
        title_layout.addWidget(self._arrow)

        # 文件名
        self._name_label = QLabel(file_info["file"])
        self._name_label.setStyleSheet(f"color: {THEME['text_primary']}; font-size: 13px; font-weight: bold;")
        title_layout.addWidget(self._name_label)

        # 变更统计
        self._add_label = None
        self._del_label = None
        if file_info["additions"] > 0:
            self._add_label = QLabel(f"+{file_info['additions']}")
            self._add_label.setStyleSheet(f"color: {THEME['green']}; font-size: 12px; font-weight: bold;")
            title_layout.addWidget(self._add_label)
        if file_info["deletions"] > 0:
            self._del_label = QLabel(f"-{file_info['deletions']}")
            self._del_label.setStyleSheet(f"color: {THEME['red']}; font-size: 12px; font-weight: bold;")
            title_layout.addWidget(self._del_label)

        title_layout.addStretch()
        layout.addWidget(self._title_bar)

        # 内容区（默认隐藏）
        self._content = QFrame()
        self._content.setVisible(False)
        self._content.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_primary']};
                border-radius: 0 0 8px 8px;
            }}
        """)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(1)

        # 构建 diff 行
        self._build_lines(content_layout, file_info["hunks"])

        layout.addWidget(self._content)

        # 点击标题栏切换
        self._title_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_bar.mousePressEvent = lambda e: self._toggle()

    def _build_lines(self, layout, hunks):
        """构建 diff 行列表。"""
        self._diff_lines = []  # 跟踪所有行 label，用于主题切换
        max_lines = 500  # 最大显示行数，避免卡死

        for hunk in hunks:
            # Hunk 头
            hunk_label = QLabel(
                f"@@ -{hunk['old_start']},{hunk['old_count']} "
                f"+{hunk['new_start']},{hunk['new_count']} @@"
            )
            self._diff_lines.append(hunk_label)
            hunk_label.setStyleSheet(
                f"color: {THEME['text_tertiary']}; font-size: 12px; "
                f"font-family: monospace; padding: 2px 0;"
            )
            layout.addWidget(hunk_label)

            for line_info in hunk["lines"]:
                if layout.count() > max_lines:
                    # 截断显示
                    more_label = QLabel("... (更多变更)")
                    self._diff_lines.append(more_label)
                    more_label.setStyleSheet(
                        f"color: {THEME['text_tertiary']}; font-size: 12px; "
                        f"font-style: italic; padding: 4px 0;"
                    )
                    layout.addWidget(more_label)
                    break

                line_label = QLabel()
                self._diff_lines.append(line_label)
                line_label.setWordWrap(False)
                line_label.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )

                if line_info["type"] == "added":
                    line_label.setText(f"+ {line_info['text']}")
                    bg = "#1A3320"
                    fg = THEME["green"]
                elif line_info["type"] == "removed":
                    line_label.setText(f"- {line_info['text']}")
                    bg = "#3B1F1F"
                    fg = THEME["red"]
                else:
                    line_label.setText(f"  {line_info['text']}")
                    bg = THEME["bg_secondary"]
                    fg = THEME["text_tertiary"]

                line_label.setStyleSheet(
                    f"background-color: {bg}; color: {fg}; "
                    f"font-family: monospace; font-size: 12px; "
                    f"padding: 1px 6px; border-radius: 2px; line-height: 18px;"
                )
                layout.addWidget(line_label)

            # Hunk 间加分隔
            layout.addSpacing(4)

        layout.addStretch()

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")
        # 通知父级重新计算滚动高度
        if self.parent():
            QTimer.singleShot(10, lambda: self.parent().adjustSize())

    def update_theme(self):
        """更新 diff 文件卡片主题。"""
        theme = theme_manager.get_current_theme()
        if hasattr(self, '_title_bar') and self._title_bar is not None:
            self._title_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme['bg_card']};
                    border-radius: 8px;
                }}
            """)
        if hasattr(self, '_arrow') and self._arrow is not None:
            self._arrow.setStyleSheet(f"color: {theme['text_tertiary']}; font-size: 12px;")
        if hasattr(self, '_name_label') and self._name_label is not None:
            self._name_label.setStyleSheet(f"color: {theme['text_primary']}; font-size: 13px; font-weight: bold;")
        if hasattr(self, '_add_label'):
            self._add_label.setStyleSheet(f"color: {theme['green']}; font-size: 12px; font-weight: bold;")
        if hasattr(self, '_del_label'):
            self._del_label.setStyleSheet(f"color: {theme['red']}; font-size: 12px; font-weight: bold;")
        if hasattr(self, '_content'):
            self._content.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme['bg_primary']};
                    border-radius: 0 0 8px 8px;
                }}
            """)
        # 更新所有 diff 行标签颜色
        if hasattr(self, '_diff_lines'):
            for label in self._diff_lines:
                text = label.text()
                if text.startswith("+ ") or text.startswith("+"):
                    label.setStyleSheet(f"""
                        background-color: #1A3320; color: {theme['green']};
                        font-family: monospace; font-size: 12px;
                        padding: 1px 6px; border-radius: 2px; line-height: 18px;
                    """)
                elif text.startswith("- ") or text.startswith("-"):
                    label.setStyleSheet(f"""
                        background-color: #3B1F1F; color: {theme['red']};
                        font-family: monospace; font-size: 12px;
                        padding: 1px 6px; border-radius: 2px; line-height: 18px;
                    """)
                elif text.startswith("@@"):
                    label.setStyleSheet(f"""
                        color: {theme['text_tertiary']}; font-size: 12px;
                        font-family: monospace; padding: 2px 0;
                    """)
                elif text.startswith("..."):
                    label.setStyleSheet(f"""
                        color: {theme['text_tertiary']}; font-size: 12px;
                        font-style: italic; padding: 4px 0;
                    """)
                else:
                    label.setStyleSheet(f"""
                        background-color: {theme['bg_secondary']}; color: {theme['text_tertiary']};
                        font-family: monospace; font-size: 12px;
                        padding: 1px 6px; border-radius: 2px; line-height: 18px;
                    """)


class DiffCard(QFrame):
    """代码对比卡片容器，包含多个 DiffFileCard。"""

    def __init__(self, files_diff, parent=None):
        """
        Args:
            files_diff: DiffParser.parse() 返回的文件列表
        """
        super().__init__(parent)
        self.setObjectName("diffCard")

        total_add = sum(f["additions"] for f in files_diff)
        total_del = sum(f["deletions"] for f in files_diff)

        self.setStyleSheet(f"""
            #diffCard {{
                background-color: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)

        # 顶部标题
        header = QLabel(f"代码变更（{len(files_diff)} 个文件，+{total_add} -{total_del}）")
        header.setStyleSheet(
            f"color: {THEME['text_primary']}; font-size: 14px; "
            f"font-weight: bold; padding: 4px 4px 8px 4px;"
        )
        layout.addWidget(header)

        # 每个文件一个卡片
        for file_info in files_diff:
            if file_info["hunks"]:  # 只显示有变更的文件
                card = DiffFileCard(file_info)
                layout.addWidget(card)

        layout.addStretch()

    def update_theme(self):
        """更新 diff 卡片容器主题。"""
        theme = theme_manager.get_current_theme()
        self.setStyleSheet(f"""
            #diffCard {{
                background-color: transparent;
            }}
        """)
        # 更新子卡片
        for child in self.findChildren(DiffFileCard):
            if hasattr(child, 'update_theme'):
                child.update_theme()


class LandingPage(QFrame):
    """空状态引导页，无对话时显示 — 深色主题 + 浮动动画。"""

    send_clicked = pyqtSignal(str)  # 用户从着陆页发送消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("landingPage")
        self.setVisible(False)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"""
            #landingPage {{
                background-color: {THEME['bg_primary']};
            }}
        """)

        # 透明度效果
        self._opacity_effect = None
        self._fade_animation = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # 顶部渐变文字
        self._hint_top = QLabel("你好，我是 Claude")
        self._hint_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_top.setStyleSheet(f"""
            font-size: 30px; color: {THEME['text_primary']};
            font-weight: bold; margin-bottom: 6px;
        """)
        layout.addWidget(self._hint_top)

        self._hint_sub = QLabel("我可以帮你写代码、回答问题、分析文件")
        self._hint_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_sub.setStyleSheet(f"font-size: 15px; color: {THEME['text_tertiary']};")
        layout.addWidget(self._hint_sub)

        layout.addSpacing(30)
        layout.addStretch()

        # 居中容器
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setSpacing(20)

        # 图标区域 — 紫蓝渐变圆形 + 浮动动画
        icon_label = QLabel("✦")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setMinimumSize(96, 96)
        icon_label.setMaximumSize(96, 96)
        icon_label.setStyleSheet(f"""
            QLabel {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                border-radius: 48px; font-size: 44px; color: white;
            }}
        """)
        self._icon_label = icon_label  # 保存引用用于动画
        center_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # 文字提示
        self._hint_label = QLabel("请开始我们的对话吧")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet(f"font-size: 16px; color: {THEME['text_tertiary']};")
        center_layout.addWidget(self._hint_label)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)

        self._landing_input = QTextEdit()
        self._landing_input.setPlaceholderText("输入消息...")
        self._landing_input.setMinimumHeight(48)
        self._landing_input.setMaximumHeight(100)
        self._landing_input.setStyleSheet(f"""
            QTextEdit {{
                border-radius: 12px;
                padding: 10px 14px; font-size: 14px;
                background-color: {THEME['bg_primary']}; color: {THEME['text_primary']};
            }}
            QTextEdit::placeholder {{ color: {THEME['text_tertiary']}; }}
        """)
        input_layout.addWidget(self._landing_input)

        self._send_btn = QPushButton("发  送")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 12px;
                padding: 10px 24px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        self._send_btn.setMinimumHeight(48)
        input_layout.addWidget(self._send_btn)

        center_layout.addLayout(input_layout)

        layout.addWidget(center)
        layout.addStretch()

        # 信号
        self._send_btn.clicked.connect(self._on_send)
        self._landing_input.keyPressEvent = self._on_key_press

    def _on_send(self):
        text = self._landing_input.toPlainText().strip()
        if text:
            self._landing_input.clear()
            self.send_clicked.emit(text)

    def _on_key_press(self, event):
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._on_send()
            return
        QTextEdit.keyPressEvent(self._landing_input, event)

    def get_input_text(self):
        return self._landing_input.toPlainText().strip()

    def clear_input(self):
        self._landing_input.clear()

    def update_theme(self):
        """更新着陆页主题。"""
        theme = theme_manager.get_current_theme()
        gradient_start = theme.get('gradient_start', theme['primary'])
        gradient_end = theme.get('gradient_end', '#8B5CF6')

        self.setStyleSheet(f"""
            #landingPage {{
                background-color: {theme['bg_primary']};
            }}
        """)
        if hasattr(self, '_hint_top') and self._hint_top is not None:
            self._hint_top.setStyleSheet(f"font-size: 30px; color: {theme['text_primary']}; font-weight: bold; margin-bottom: 6px;")
        if hasattr(self, '_hint_sub') and self._hint_sub is not None:
            self._hint_sub.setStyleSheet(f"font-size: 15px; color: {theme['text_tertiary']};")
        if hasattr(self, '_icon_label') and self._icon_label is not None:
            self._icon_label.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {gradient_start}, stop:1 {gradient_end});
                    border-radius: 48px; font-size: 44px; color: white;
                }}
            """)
        if hasattr(self, '_hint_label') and self._hint_label is not None:
            self._hint_label.setStyleSheet(f"font-size: 16px; color: {theme['text_tertiary']};")
        if hasattr(self, '_landing_input') and self._landing_input is not None:
            self._landing_input.setStyleSheet(f"""
                QTextEdit {{
                    border: 1px solid {theme['border']}; border-radius: 12px;
                    padding: 10px 14px; font-size: 14px;
                    background-color: {theme['bg_input']}; color: {theme['text_primary']};
                }}
                QTextEdit:focus {{ border-color: {theme['border_focus']}; }}
                QTextEdit::placeholder {{ color: {theme['text_tertiary']}; }}
            """)
        if hasattr(self, '_send_btn') and self._send_btn is not None:
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {gradient_start}, stop:1 {gradient_end});
                    color: white; border: none; border-radius: 12px;
                    padding: 10px 24px; font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {theme['primary_hover']}, stop:1 #A78BFA);
                }}
                QPushButton:pressed {{ opacity: 0.85; }}
            """)

    def fade_in(self, duration=500):
        """淡入动画。"""
        self.setVisible(True)
        animation_manager._step_opacity(self, duration, 0.0, 1.0, None)

    def fade_out(self, duration=300, callback=None):
        """淡出动画。"""
        def on_done():
            self.setVisible(False)
            if callback:
                callback()
        animation_manager._step_opacity(self, duration, 1.0, 0.0, on_done)


class PopupList(QDialog):
    """弹出选择列表对话框。"""

    def __init__(self, title, items, parent=None):
        super().__init__(parent)
        self.selected = None
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setMinimumHeight(200)
        self.resize(380, 220)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {THEME['bg_secondary']};
            }}
        """)
        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 8px; color: {THEME['text_primary']};")
        layout.addWidget(title_label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_card']}; color: {THEME['text_secondary']};
            }}
            QListWidget::item {{
                padding: 8px 12px; border-bottom: 1px solid {THEME['border']};
                color: {THEME['text_secondary']};
            }}
            QListWidget::item:hover {{ background-color: {THEME['bg_secondary']}; }}
            QListWidget::item:selected {{
                background-color: {THEME['primary']}; color: white;
                border-radius: 4px;
            }}
        """)
        for name, desc in items:
            item = QListWidgetItem(f"{name}  —  {desc}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)
        self.list_widget.itemDoubleClicked.connect(self._on_select)

    def _on_select(self, item):
        self.selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


# ==================== 面板 ====================

class LeftPanel(QFrame):
    """左侧面板：新建对话 + 历史对话列表。"""

    rename_requested = pyqtSignal(str)  # conv_id
    delete_requested = pyqtSignal(str)  # conv_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"""
            LeftPanel {{
                background-color: {THEME['bg_secondary']};
            }}
        """)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(6)

        # 主题切换区域
        theme_widget = QWidget()
        theme_layout = QHBoxLayout(theme_widget)
        theme_layout.setContentsMargins(0, 0, 0, 0)
        theme_layout.setSpacing(8)
        
        theme_label = QLabel("主题")
        theme_label.setStyleSheet(f"font-size: 13px; color: {theme_manager.get_color('text_secondary')};")
        
        self.theme_switch = ModernSwitch()
        self.theme_switch.setChecked(False)  # 默认浅色主题
        
        # 主题切换事件
        self.theme_switch.toggled.connect(self._on_theme_toggled)
        
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_switch)
        theme_layout.addStretch()
        
        layout.addWidget(theme_widget)

        self.new_btn = QPushButton("✚ 新建对话")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 8px;
                padding: 10px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        layout.addWidget(self.new_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        layout.addWidget(line)

        title = QLabel("历史对话")
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px 0; color: {THEME['text_primary']};")
        layout.addWidget(title)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet(f"""
            QListWidget {{
                border: 1px solid {THEME['border']}; border-radius: 8px;
                background-color: {THEME['bg_secondary']}; color: {THEME['text_primary']};
            }}
            QListWidget::item {{
                padding: 8px; border-bottom: 1px solid {THEME['border']};
                color: {THEME['text_secondary']};
            }}
            QListWidget::item:hover {{ background-color: {THEME['bg_card']}; }}
            QListWidget::item:selected {{
                background-color: {THEME['primary']}; color: white;
                border-radius: 4px;
            }}
        """)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.conv_list)
    
    def _on_theme_toggled(self, is_dark):
        """主题切换处理"""
        try:
            if is_dark:
                theme_manager.switch_theme("dark")
            else:
                theme_manager.switch_theme("light")
        except Exception as e:
            print(f"主题切换错误: {e}")
            # 重置开关状态
            self.theme_switch.blockSignals(True)
            self.theme_switch.setChecked(not is_dark)
            self.theme_switch.blockSignals(False)
    
    def update_theme(self):
        """更新主题样式 — 只刷新顶层组件，子控件靠 Qt 样式表级联继承。"""
        try:
            theme = theme_manager.get_current_theme()
        except Exception:
            return

        gradient_start = theme.get('gradient_start', theme['primary'])
        gradient_end = theme.get('gradient_end', '#8B5CF6')

        self.setStyleSheet(f"""
            LeftPanel {{
                background-color: {theme['bg_secondary']};
                border-radius: 0px;
            }}
        """)

        # 新建按钮
        if hasattr(self, 'new_btn') and self.new_btn is not None:
            self.new_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {gradient_start}, stop:1 {gradient_end});
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 12px 16px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {theme['primary_hover']}, stop:1 #A78BFA);
                }}
                QPushButton:pressed {{
                    opacity: 0.9;
                }}
            """)

        # 对话列表
        if hasattr(self, 'conv_list') and self.conv_list is not None:
            self.conv_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {theme['bg_secondary']};
                    color: {theme['text_primary']};
                    padding: 8px;
                    outline: none;
                }}
                QListWidget::item {{
                    padding: 14px 16px;
                    border: none;
                    color: {theme['text_secondary']};
                    border-radius: 12px;
                    margin: 4px 2px;
                    background-color: transparent;
                    font-size: 13px;
                }}
                QListWidget::item:hover {{
                    background-color: {theme['bg_card']};
                    color: {theme['text_primary']};
                }}
                QListWidget::item:selected {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {theme['primary']}, stop:1 {gradient_end});
                    color: white;
                    border-radius: 12px;
                    font-weight: 500;
                }}
                QListWidget::item:focus {{
                    outline: none;
                    border: none;
                }}
            """)

    def _on_context_menu(self, pos):
        """右键菜单：重命名 / 删除。"""
        item = self.conv_list.itemAt(pos)
        if not item:
            return
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if not conv_id:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("重命名")
        menu.addSeparator()
        delete_action = menu.addAction("删除")

        action = menu.exec(self.conv_list.mapToGlobal(pos))
        if action == rename_action:
            self.rename_requested.emit(conv_id)
        elif action == delete_action:
            self.delete_requested.emit(conv_id)

    def clear_conversations(self):
        self.conv_list.clear()

    def add_conversation(self, title_text, preview, conv_id):
        item = QListWidgetItem(title_text)
        item.setData(Qt.ItemDataRole.UserRole, conv_id)
        self.conv_list.insertItem(0, item)


class CenterPanel(QFrame):
    """中间面板：模型选择 + 消息区 + 输入区。"""

    send_clicked = pyqtSignal(str)    # 用户点击发送（正常模式）
    stop_clicked = pyqtSignal()       # 用户点击停止（AI 回复中）
    permission_accept_clicked = pyqtSignal()
    permission_reject_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self._diff_cards = []  # 跟踪所有 DiffCard，用于主题切换
        self._message_rows = []  # 跟踪所有 MessageRow
        self._thinking_rows = []  # 跟踪所有 ThinkingRow
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 深色主题背景
        self.setStyleSheet(f"""
            CenterPanel {{
                background-color: {THEME['bg_primary']};
            }}
        """)

        # 顶部：模型选择 + 深色主题
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        combo_style = f"""
            QComboBox {{
                background-color: {THEME['bg_input']}; color: {THEME['text_primary']};
                border: 1px solid {THEME['border']}; border-radius: 6px;
                padding: 4px 12px; font-size: 12px; min-width: 120px;
            }}
            QComboBox:hover {{ border-color: {THEME['border_focus']}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {THEME['bg_card']}; color: {THEME['text_primary']};
                selection-background-color: {THEME['primary']};
            }}
        """

        model_label = QLabel("模型:")
        model_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        top_bar.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["opus (最强)", "sonnet (推荐)", "haiku (最快)"])
        self.model_combo.setCurrentIndex(1)
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.model_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["普通模式", "Agent 模式 (多步骤任务)"])
        self.mode_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.mode_combo)

        perm_label = QLabel("权限:")
        perm_label.setStyleSheet(f"color: {THEME['text_secondary']}; font-size: 12px;")
        top_bar.addWidget(perm_label)

        self.permission_combo = QComboBox()
        self.permission_combo.addItems(["default(逐次询问)", "acceptEdits(自动编辑)", "plan(只读)"])
        self.permission_combo.setCurrentIndex(0)
        self.permission_combo.setMinimumWidth(170)
        self.permission_combo.setStyleSheet(combo_style)
        top_bar.addWidget(self.permission_combo)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self._top_widgets = [top_bar.itemAt(i).widget() for i in range(top_bar.count()) if top_bar.itemAt(i).widget()]

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        self._separator_line = line
        layout.addWidget(line)

        # 消息区
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.msg_scroll.viewport().setAutoFillBackground(True)
        self.msg_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {THEME['bg_primary']};
            }}
        """)

        self.msg_container = QWidget()
        self.msg_container.setAutoFillBackground(True)
        self.msg_container.setStyleSheet(f"background-color: {THEME['bg_primary']};")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(4, 4, 4, 4)
        self.msg_layout.setSpacing(2)
        self.msg_layout.addStretch()
        self.msg_scroll.setWidget(self.msg_container)
        layout.addWidget(self.msg_scroll)

        # 快捷按钮行
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        btn_defs = [
            ("@ 引用文件", THEME["primary"]), ("# 智能体", THEME["green"]),
            ("! 提示词", THEME["orange"]), ("$ Skills", THEME["purple"]), (" 图片", THEME["teal"]),
        ]
        for text, color in btn_defs:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            key = text.strip().split()[0].replace("@", "ref").replace("#", "agent").replace("!", "prompt").replace("$", "skill").replace("图片", "image")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}22; color: {color}; border: 1px solid {color}44;
                    border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 500;
                }}
                QPushButton:hover {{ background-color: {color}33; border-color: {color}66; }}
                QPushButton:pressed {{ background-color: {color}44; }}
            """)
            setattr(self, f"btn_{key}", btn)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._toolbar_widgets = [toolbar.itemAt(i).widget() for i in range(toolbar.count()) if toolbar.itemAt(i).widget()]

        # 输入区
        # 权限请求条（输入框上方）
        self.permission_bar = QFrame()
        self.permission_bar.setVisible(False)
        self.permission_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_card']};
                border: 1px solid {THEME['border']};
                border-radius: 10px; padding: 6px;
            }}
            QLabel {{ color: {THEME['text_secondary']}; font-size: 12px; }}
        """)
        perm_layout = QHBoxLayout(self.permission_bar)
        perm_layout.setContentsMargins(10, 6, 10, 6)
        perm_layout.setSpacing(8)
        self.permission_label = QLabel("检测到权限请求")
        perm_layout.addWidget(self.permission_label)
        perm_layout.addStretch()
        self.permission_yes_btn = QPushButton("允许")
        self.permission_yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.permission_yes_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['green']}; color: white; border: none;
                border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME['green_hover']}; }}
        """)
        self.permission_no_btn = QPushButton("拒绝")
        self.permission_no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.permission_no_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME['red']}; color: white; border: none;
                border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {THEME['red_hover']}; }}
        """)
        perm_layout.addWidget(self.permission_yes_btn)
        perm_layout.addWidget(self.permission_no_btn)
        layout.addWidget(self.permission_bar)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.input_box.setStyleSheet(f"""
            QTextEdit {{
                border-radius: 10px;
                padding: 8px 12px; font-size: 14px;
                background-color: {THEME['bg_primary']}; color: {THEME['text_primary']};
            }}
            QTextEdit::placeholder {{ color: {THEME['text_tertiary']}; }}
        """)
        self.input_box.setMinimumHeight(40)
        self.input_box.setMaximumHeight(120)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("发  送")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                color: white; border: none; border-radius: 10px;
                padding: 8px 20px; font-size: 14px; font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
            }}
            QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
            QPushButton:pressed {{ opacity: 0.85; }}
        """)
        self.send_btn.setMinimumHeight(40)
        input_layout.addWidget(self.send_btn)
        layout.addLayout(input_layout)

        self._landing_input_widgets = [input_layout.itemAt(i).widget() for i in range(input_layout.count()) if input_layout.itemAt(i).widget()]

        # 着陆页（无对话时显示，初始隐藏）
        self.landing_page = LandingPage()
        layout.addWidget(self.landing_page)

        # 默认显示着陆页
        self.show_landing()

        # 信号：按钮点击根据模式发送不同信号
        self.send_btn.clicked.connect(self._on_btn_click)
        self._is_building_response = False  # 按钮模式标记
        self.permission_yes_btn.clicked.connect(lambda: self.permission_accept_clicked.emit())
        self.permission_no_btn.clicked.connect(lambda: self.permission_reject_clicked.emit())

    def show_permission_request(self, text):
        print(f"[PermissionUI] show_permission_request called with: {text}")
        self.permission_label.setText(text)
        self.permission_bar.setMinimumHeight(50)
        self.permission_bar.setVisible(True)
        self.permission_bar.show()
        self.permission_bar.raise_()
        self.permission_bar.update()
        print(f"[PermissionUI] permission_bar visibility: {self.permission_bar.isVisible()}")
        print(f"[PermissionUI] permission_bar parent: {self.permission_bar.parent()}")
        print(f"[PermissionUI] permission_bar geometry: {self.permission_bar.geometry()}")

    @pyqtSlot()
    def hide_permission_request(self):
        self.permission_bar.setVisible(False)

    def set_building_response(self, building):
        """切换按钮模式：AI 回复中显示"停止"，否则显示"发送"。"""
        self._is_building_response = building
        if building:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("停  止")
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['red']}, stop:1 #B91C1C);
                    color: white; border: none; border-radius: 10px;
                    padding: 8px 20px; font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['red_hover']}, stop:1 #991B1B);
                }}
                QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
                QPushButton:pressed {{ opacity: 0.85; }}
            """)
        else:
            self.send_btn.setEnabled(True)
            self.send_btn.setText("发  送")
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['primary']}, stop:1 #8B5CF6);
                    color: white; border: none; border-radius: 10px;
                    padding: 8px 20px; font-size: 14px; font-weight: bold;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {THEME['primary_hover']}, stop:1 #A78BFA);
                }}
                QPushButton:disabled {{ background-color: {THEME['text_tertiary']}; }}
                QPushButton:pressed {{ opacity: 0.85; }}
            """)

    def _on_btn_click(self):
        if self._is_building_response:
            self.stop_clicked.emit()
        else:
            self._on_send()

    def _on_send(self):
        text = self.input_box.toPlainText().strip()
        if text:
            self.send_clicked.emit(text)

    def clear_messages(self):
        """清空消息区。"""
        # 清空跟踪列表，防止主题切换时访问已删除的组件
        self._diff_cards.clear()
        self._message_rows.clear()
        self._thinking_rows.clear()
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def show_landing(self):
        """显示着陆页，带淡入动画。"""
        self.landing_page.fade_in(duration=500)
        self.msg_scroll.setVisible(False)
        self._separator_line.setVisible(False)
        for w in self._toolbar_widgets:
            w.setVisible(False)
        for w in self._landing_input_widgets:
            w.setVisible(False)

    def hide_landing(self):
        """隐藏着陆页，带淡出动画。"""
        def on_finished():
            self.landing_page.setVisible(False)
            self.landing_page.setWindowOpacity(1.0)
        self.landing_page.fade_out(duration=300, callback=on_finished)
        self.msg_scroll.setVisible(True)
        self._separator_line.setVisible(True)
        for w in self._toolbar_widgets:
            w.setVisible(True)
        for w in self._landing_input_widgets:
            w.setVisible(True)

    def _animate_widget_in(self, widget, duration=400):
        """给新添加的 widget 加淡入动画。"""
        widget.setVisible(False)

        def _start_fade():
            widget.setVisible(True)
            animation_manager._step_opacity(widget, duration, 0.0, 1.0, None)

        QTimer.singleShot(50, _start_fade)

    def add_message(self, role, text):
        """添加消息到聊天区，带淡入动画。"""
        row = MessageRow(role, text)
        self._message_rows.append(row)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, row)
        self._animate_widget_in(row)
        self._scroll_to_bottom()
        return row

    def _find_latest_thinking_row(self):
        if self.msg_layout.count() <= 1:
            return None
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ThinkingRow):
                return item.widget()
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                break
        return None

    def add_thinking_block(self, text, duration_ms, in_progress=True):
        """添加或更新当前轮次思考块。"""
        row = self._find_latest_thinking_row()
        if row is None:
            row = ThinkingRow(text, duration_ms)
            self._thinking_rows.append(row)
            spring_index = self.msg_layout.count() - 1
            self.msg_layout.insertWidget(spring_index, row)
            self._animate_widget_in(row)
        else:
            row.append_thinking(text, duration_ms)
        row.set_in_progress(in_progress)
        self._scroll_to_bottom()
        return row

    def set_thinking_block_state(self, in_progress):
        """更新当前轮次思考块状态。"""
        row = self._find_latest_thinking_row()
        if row:
            row.set_in_progress(in_progress)

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.msg_scroll.verticalScrollBar().setValue(
            self.msg_scroll.verticalScrollBar().maximum()
        ))

    def remove_thinking_placeholder(self):
        """移除最后的占位消息（"思考中..."）。"""
        if self.msg_layout.count() <= 1:
            return
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                widget = item.widget()
                # 检查是否是 assistant 的占位消息
                if widget.role == "assistant":
                    text = widget._content_label.text()
                    if "思考中" in text:
                        self.msg_layout.removeWidget(widget)
                        widget.deleteLater()
                break

    def update_last_message(self, text):
        """更新最后一条消息（用于流式输出）。"""
        if self.msg_layout.count() <= 1:
            return
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                widget = item.widget()
                widget.update_text(text)
                # 直接滚动
                self.msg_scroll.verticalScrollBar().setValue(
                    self.msg_scroll.verticalScrollBar().maximum()
                )
                break

    def update_processing_status(self, text):
        """更新处理中状态文案（不产生新气泡）。"""
        if not text:
            return
        self.update_last_message(f"处理中：{text}")

    def get_last_message_text(self):
        """获取最后一条消息文本。"""
        if self.msg_layout.count() <= 1:
            return ""
        for i in range(self.msg_layout.count() - 2, -1, -1):
            item = self.msg_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageRow):
                return item.widget().get_text()
        return ""

    def add_diff_card(self, files_diff):
        """添加代码对比卡片到消息区。

        Args:
            files_diff: DiffParser.parse() 返回的文件列表
        """
        card = DiffCard(files_diff)
        self._diff_cards.append(card)
        spring_index = self.msg_layout.count() - 1
        self.msg_layout.insertWidget(spring_index, card)
        self._scroll_to_bottom()

    def update_theme(self):
        """更新中心面板主题样式 — 只刷新顶层组件，子控件靠 Qt 样式表级联。"""
        try:
            theme = theme_manager.get_current_theme()
        except Exception:
            return

        gradient_start = theme.get('gradient_start', theme['primary'])
        gradient_end = theme.get('gradient_end', '#8B5CF6')

        # 面板背景
        self.setStyleSheet(f"""
            CenterPanel {{
                background-color: {theme['bg_primary']};
            }}
        """)

        # 下拉框样式
        combo_style = f"""
            QComboBox {{
                background-color: {theme['bg_input']};
                color: {theme['text_primary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 120px;
                font-weight: 500;
            }}
            QComboBox:hover {{
                border-color: {theme['border_focus']};
                background-color: {theme['bg_card']};
            }}
            QComboBox:focus {{
                border: 2px solid {theme['border_focus']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid {theme['text_secondary']};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme['bg_card']};
                color: {theme['text_primary']};
                selection-background-color: {theme['primary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 4px;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {theme['primary']};
                color: white;
            }}
        """

        if hasattr(self, 'model_combo') and self.model_combo is not None:
            self.model_combo.setStyleSheet(combo_style)
        if hasattr(self, 'mode_combo') and self.mode_combo is not None:
            self.mode_combo.setStyleSheet(combo_style)
        if hasattr(self, 'permission_combo') and self.permission_combo is not None:
            self.permission_combo.setStyleSheet(combo_style)

        # 快捷按钮
        is_dark = theme['bg_primary'] in ('#0D1117', '#212121', '#1A1A1A', '#1E1E1E')
        button_colors = [
            ("@ 引用文件", theme["primary"]),
            ("# 智能体", theme["green"]),
            ("! 提示词", theme["orange"]),
            ("$ Skills", theme["purple"]),
            (" 图片", theme["teal"])
        ]
        for i, (text, color) in enumerate(button_colors):
            btn = getattr(self, f"btn_{['ref', 'agent', 'prompt', 'skill', 'image'][i]}", None)
            if btn is not None:
                if is_dark:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {color}22;
                            color: {color};
                            border: 1px solid {color}44;
                            border-radius: 8px;
                            padding: 6px 12px;
                            font-size: 11px;
                            font-weight: 500;
                        }}
                        QPushButton:hover {{ background-color: {color}33; border-color: {color}66; }}
                        QPushButton:pressed {{ background-color: {color}44; }}
                    """)
                else:
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {color};
                            color: white;
                            border: none;
                            border-radius: 8px;
                            padding: 6px 12px;
                            font-size: 11px;
                            font-weight: 600;
                        }}
                        QPushButton:hover {{ opacity: 0.85; }}
                        QPushButton:pressed {{ opacity: 0.7; }}
                    """)

        # 消息区
        if hasattr(self, 'msg_scroll') and self.msg_scroll is not None:
            self.msg_scroll.setStyleSheet(f"""
                QScrollArea {{
                    background-color: {theme['bg_primary']};
                }}
            """)
            try:
                vp = self.msg_scroll.viewport()
                if vp is not None:
                    vp.setAutoFillBackground(True)
                    vp.setStyleSheet(f"background-color: {theme['bg_primary']};")
            except Exception:
                pass
        if hasattr(self, 'msg_container') and self.msg_container is not None:
            self.msg_container.setStyleSheet(f"background-color: {theme['bg_primary']};")

        # 权限请求栏
        if hasattr(self, 'permission_bar') and self.permission_bar is not None:
            self.permission_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme['bg_card']};
                    border: 1px solid {theme['border']};
                    border-radius: 12px;
                    padding: 8px;
                }}
                QLabel {{
                    color: {theme['text_secondary']};
                    font-size: 12px;
                    font-weight: 500;
                }}
            """)
            if hasattr(self, 'permission_yes_btn') and self.permission_yes_btn is not None:
                self.permission_yes_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {theme['green']};
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 6px 16px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{ background-color: {theme['green_hover']}; }}
                """)
            if hasattr(self, 'permission_no_btn') and self.permission_no_btn is not None:
                self.permission_no_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {theme['red']};
                        color: white;
                        border: none;
                        border-radius: 8px;
                        padding: 6px 16px;
                        font-size: 12px;
                        font-weight: 600;
                    }}
                    QPushButton:hover {{ background-color: {theme['red_hover']}; }}
                """)

        # 输入框
        if hasattr(self, 'input_box') and self.input_box is not None:
            self.input_box.setStyleSheet(f"""
                QTextEdit {{
                    border-radius: 12px;
                    padding: 12px 16px;
                    font-size: 14px;
                    background-color: {theme['bg_primary']};
                    color: {theme['text_primary']};
                    selection-background-color: {theme['primary']};
                }}
                QTextEdit::placeholder {{
                    color: {theme['text_tertiary']};
                    font-style: italic;
                }}
            """)

        # 发送按钮
        if hasattr(self, 'send_btn') and self.send_btn is not None:
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {gradient_start}, stop:1 {gradient_end});
                    color: white;
                    border: none;
                    border-radius: 12px;
                    padding: 10px 24px;
                    font-size: 14px;
                    font-weight: 600;
                    letter-spacing: 0.5px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {theme['primary_hover']}, stop:1 #A78BFA);
                }}
                QPushButton:disabled {{ background-color: {theme['text_tertiary']}; }}
                QPushButton:pressed {{ opacity: 0.9; }}
            """)

        # diff 卡片
        for card in list(self._diff_cards):
            try:
                if hasattr(card, 'update_theme'):
                    card.update_theme()
            except Exception:
                pass

        # 消息行
        for row in list(self._message_rows):
            try:
                if hasattr(row, 'update_theme'):
                    row.update_theme()
            except Exception:
                pass

        # 思考行
        for row in list(self._thinking_rows):
            try:
                if hasattr(row, 'update_theme'):
                    row.update_theme()
            except Exception:
                pass

        # 着陆页
        if hasattr(self, 'landing_page'):
            try:
                self.landing_page.update_theme()
            except Exception:
                pass


# ==================== TaskProgress（任务进度面板）====================

class TaskStepCard(QFrame):
    """单个任务步骤卡片（可折叠）。"""

    def __init__(self, index, tool_name, params=None, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._tool_name = tool_name
        self._index = index
        self.setObjectName("taskStepCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        self._title_bar = QFrame()
        self._title_bar.setFixedHeight(32)
        self._title_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_card']};
                border-radius: 6px;
            }}
        """)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(10, 2, 10, 2)
        title_layout.setSpacing(6)

        # 折叠箭头
        self._arrow = QLabel("▶")
        self._arrow.setStyleSheet(f"color: {THEME['text_tertiary']}; font-size: 10px;")
        title_layout.addWidget(self._arrow)

        # 工具名称
        self._name_label = QLabel(tool_name)
        self._name_label.setStyleSheet(
            f"color: {THEME['text_primary']}; font-size: 12px; font-weight: bold;"
        )
        title_layout.addWidget(self._name_label)

        # 状态标签（运行中）
        self._status_label = QLabel("进行中")
        self._status_label.setStyleSheet(
            f"background-color: {THEME['primary']}; color: white; "
            f"font-size: 10px; border-radius: 8px; padding: 1px 6px;"
        )
        title_layout.addWidget(self._status_label)

        title_layout.addStretch()

        # 用时
        self._time_label = QLabel("0ms")
        self._time_label.setStyleSheet(f"color: {THEME['text_tertiary']}; font-size: 11px;")
        title_layout.addWidget(self._time_label)

        title_layout.addWidget(self._arrow)

        self._title_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._title_bar.mousePressEvent = lambda e: self._toggle()
        layout.addWidget(self._title_bar)

        # 内容区（默认隐藏）
        self._content = QFrame()
        self._content.setVisible(False)
        self._content.setStyleSheet(f"""
            QFrame {{
                background-color: {THEME['bg_primary']};
                border-radius: 0 0 6px 6px;
            }}
        """)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(10, 8, 10, 8)
        content_layout.setSpacing(4)

        # 参数展示
        if params:
            param_text = json.dumps(params, ensure_ascii=False, indent=2)
            param_label = QLabel(param_text[:300])
            param_label.setWordWrap(True)
            param_label.setStyleSheet(
                f"color: {THEME['text_secondary']}; font-size: 11px; "
                f"font-family: monospace;"
            )
            content_layout.addWidget(param_label)

        # 结果区（动态更新）
        self._result_label = QLabel()
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet(
            f"color: {THEME['text_tertiary']}; font-size: 11px; "
            f"font-family: monospace;"
        )
        content_layout.addWidget(self._result_label)

        layout.addWidget(self._content)

    def set_done(self, result="", duration_ms=0):
        """标记为已完成。"""
        self._status_label.setText("已完成")
        self._status_label.setStyleSheet(
            f"background-color: {THEME['green']}; color: white; "
            f"font-size: 10px; border-radius: 8px; padding: 1px 6px;"
        )
        if duration_ms > 0:
            self._time_label.setText(f"{duration_ms}ms")
        if result:
            preview = result[:500].replace("\n", " ")
            self._result_label.setText(f"结果: {preview}")

    def set_running(self, duration_ms=0):
        """标记为进行中。"""
        self._status_label.setText("进行中")
        self._status_label.setStyleSheet(
            f"background-color: {THEME['primary']}; color: white; "
            f"font-size: 10px; border-radius: 8px; padding: 1px 6px;"
        )
        if duration_ms > 0:
            self._time_label.setText(f"{duration_ms}ms")

    def set_result(self, result):
        """更新结果文本。"""
        if result:
            preview = result[:500].replace("\n", " ")
            self._result_label.setText(f"结果: {preview}")

    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._arrow.setText("▼" if self._expanded else "▶")

    def update_theme(self):
        """更新任务卡片主题样式"""
        theme = theme_manager.get_current_theme()
        
        # 更新卡片背景
        self.setStyleSheet(f"""
            TaskStepCard {{
                background-color: {theme['bg_card']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 8px;
                margin: 2px 0;
            }}
        """)
        
        # 更新标题栏
        if hasattr(self, '_title_bar') and self._title_bar is not None:
            self._title_bar.setStyleSheet(f"""
                QFrame {{
                    background-color: {theme['bg_card']};
                    border: 1px solid {theme['border']};
                    border-radius: 6px;
                }}
            """)

        # 更新工具名称
        if hasattr(self, '_name_label') and self._name_label is not None:
            self._name_label.setStyleSheet(
                f"color: {theme['text_primary']}; font-size: 12px; font-weight: bold;"
            )

        # 更新标题
        if hasattr(self, '_title_label') and self._title_label is not None:
            self._title_label.setStyleSheet(f"""
                font-weight: 600;
                font-size: 13px;
                color: {theme['text_primary']};
            """)

        # 更新箭头
        if hasattr(self, '_arrow') and self._arrow is not None:
            self._arrow.setStyleSheet(f"""
                color: {theme['text_secondary']};
                font-size: 12px;
            """)

        # 更新状态标签（保持当前状态的颜色）
        if hasattr(self, '_status_label') and self._status_label is not None:
            status_text = self._status_label.text()
            if status_text == "已完成":
                color = theme['green']
            else:
                color = theme['primary']
            self._status_label.setStyleSheet(
                f"background-color: {color}; "
                f"color: white; "
                f"font-size: 10px; "
                f"border-radius: 6px; "
                f"padding: 2px 6px;"
                f"font-weight: 600;"
            )
        
        # 更新时间标签
        if hasattr(self, '_time_label') and self._time_label is not None:
            self._time_label.setStyleSheet(f"""
                color: {theme['text_tertiary']};
                font-size: 10px;
            """)

        # 更新结果标签
        if hasattr(self, '_result_label') and self._result_label is not None:
            self._result_label.setStyleSheet(f"""
                color: {theme['text_secondary']};
                font-size: 11px;
                padding: 4px;
                background-color: {theme['bg_input']};
                border-radius: 4px;
            """)

        # 更新内容区域
        if hasattr(self, '_content') and self._content is not None:
            self._content.setStyleSheet(f"""
                background-color: {theme['bg_input']};
                border-radius: 4px;
                padding: 8px;
                margin-top: 4px;
            """)


class RightPanel(QFrame):
    """右侧面板：任务进度 + 项目文件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"""
            RightPanel {{
                background-color: {THEME['bg_secondary']};
            }}
        """)
        self._tool_cards = {}  # {index: TaskStepCard}
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        # === 任务进度区 ===
        task_title = QLabel("任务进度")
        task_title.setStyleSheet(
            f"font-weight: bold; font-size: 14px; padding: 2px 0; color: {THEME['text_primary']};"
        )
        layout.addWidget(task_title)

        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # viewport() 必须显式设置背景色，否则默认白色
        self.task_scroll.viewport().setAutoFillBackground(True)
        self.task_scroll.viewport().setStyleSheet(f"background-color: {THEME['bg_secondary']};")
        self.task_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {THEME['bg_secondary']};
            }}
        """)
        self.task_container = QWidget()
        self.task_container.setStyleSheet(f"background-color: {THEME['bg_secondary']};")
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(4, 4, 4, 4)
        self.task_layout.setSpacing(4)

        # 无任务时提示（添加到 task_layout 中）
        self._no_task_label = QLabel("等待 AI 执行任务...")
        self._no_task_label.setStyleSheet(
            f"color: {THEME['text_tertiary']}; font-size: 12px; "
            f"font-style: italic; padding: 20px;"
        )
        self._no_task_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.task_layout.addWidget(self._no_task_label)

        self.task_layout.addStretch()
        self.task_scroll.setWidget(self.task_container)
        layout.addWidget(self.task_scroll)

        # === 分隔线 ===
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {THEME['border']};")
        layout.addWidget(line)

        # === 项目文件区 ===
        file_title = QLabel("项目文件")
        file_title.setStyleSheet(
            f"font-weight: bold; font-size: 14px; padding: 2px 0; color: {THEME['text_primary']};"
        )
        layout.addWidget(file_title)

        self.file_list = QListWidget()
        self.file_list.setAutoFillBackground(True)
        self.file_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {THEME['bg_secondary']}; color: {THEME['text_secondary']};
                border: none;
            }}
            QListWidget::item {{ padding: 4px 8px; color: {THEME['text_secondary']}; }}
            QListWidget::item:selected {{ background-color: {THEME['primary']}; color: white; }}
        """)
        self.file_list.setMaximumHeight(200)
        layout.addWidget(self.file_list)

    def update_task(self, tool_info):
        """更新任务步骤。

        Args:
            tool_info: dict {index, tool, params/result, status, duration_ms}
        """
        index = tool_info.get("index", 0)
        tool = tool_info.get("tool", "unknown")
        status = tool_info.get("status", "")
        result = tool_info.get("result", "")
        params = tool_info.get("params", {})
        duration_ms = tool_info.get("duration_ms", 0)

        # 隐藏无任务提示
        if self._no_task_label:
            self._no_task_label.setVisible(False)

        if status == "running":
            # 新建步骤卡片
            if index not in self._tool_cards:
                card = TaskStepCard(index, tool, params)
                # 插入到倒数第二个位置（addStretch 之前）
                self.task_layout.insertWidget(self.task_layout.count() - 1, card)
                self._tool_cards[index] = card
            else:
                self._tool_cards[index].set_running()

        elif status == "done":
            # 标记完成
            if index in self._tool_cards:
                self._tool_cards[index].set_done(result, duration_ms)
            else:
                # 如果之前没收到 running 信号，直接创建已完成卡片
                card = TaskStepCard(index, tool, params)
                card.set_done(result, duration_ms)
                self.task_layout.insertWidget(self.task_layout.count() - 1, card)
                self._tool_cards[index] = card

        # 自动滚动到底部
        QTimer.singleShot(50, lambda: self.task_scroll.verticalScrollBar().setValue(
            self.task_scroll.verticalScrollBar().maximum()
        ))

    def clear_tasks(self):
        """清空所有任务步骤。"""
        for card in self._tool_cards.values():
            card.deleteLater()
        self._tool_cards.clear()
        if self._no_task_label:
            self._no_task_label.setVisible(True)

    def update_theme(self):
        """更新右侧面板主题样式 — 只刷新顶层组件。"""
        try:
            theme = theme_manager.get_current_theme()
        except Exception:
            return

        self.setStyleSheet(f"""
            RightPanel {{
                background-color: {theme['bg_secondary']};
            }}
        """)

        # 任务滚动区域
        if hasattr(self, 'task_scroll') and self.task_scroll is not None:
            self.task_scroll.setStyleSheet(f"""
                QScrollArea {{
                    background-color: {theme['bg_secondary']};
                }}
                QScrollBar:vertical {{
                    background: {theme['bg_input']};
                    width: 8px;
                    border-radius: 4px;
                }}
                QScrollBar::handle:vertical {{
                    background: {theme['border']};
                    border-radius: 4px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {theme['border_focus']};
                }}
            """)
            try:
                vp = self.task_scroll.viewport()
                if vp is not None:
                    vp.setAutoFillBackground(True)
                    vp.setStyleSheet(f"background-color: {theme['bg_secondary']};")
            except Exception:
                pass

        # 任务容器
        if hasattr(self, 'task_container') and self.task_container is not None:
            self.task_container.setStyleSheet(f"background-color: {theme['bg_secondary']};")

        # 无任务提示
        if hasattr(self, '_no_task_label') and self._no_task_label is not None:
            self._no_task_label.setStyleSheet(f"""
                color: {theme['text_tertiary']};
                font-size: 12px;
                font-style: italic;
                padding: 20px;
                text-align: center;
            """)

        # 文件列表
        if hasattr(self, 'file_list') and self.file_list is not None:
            self.file_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {theme['bg_secondary']};
                    color: {theme['text_secondary']};
                    padding: 4px;
                    outline: none;
                    border: none;
                }}
                QListWidget::item {{
                    padding: 8px 12px;
                    color: {theme['text_secondary']};
                    border-radius: 6px;
                    margin: 2px;
                    font-size: 12px;
                }}
                QListWidget::item:hover {{
                    background-color: {theme['bg_card']};
                    color: {theme['text_primary']};
                }}
                QListWidget::item:selected {{
                    background-color: {theme['primary']};
                    color: white;
                    border-radius: 6px;
                    font-weight: 500;
                }}
            """)
            try:
                vp = self.file_list.viewport()
                if vp is not None:
                    vp.setAutoFillBackground(True)
                    vp.setStyleSheet(f"background-color: {theme['bg_secondary']};")
            except Exception:
                pass

        # 任务卡片
        try:
            for card in list(self._tool_cards.values()):
                try:
                    if hasattr(card, 'update_theme'):
                        card.update_theme()
                except Exception:
                    pass
        except Exception:
            pass


# ==================== 主窗口 ====================

class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Claude Code 桌面助手")
        # 启动时最大化窗口
        self.showMaximized()
        self.setMinimumSize(900, 500)

        self.claude_client = ClaudeClient()
        self.current_conv_id = None
        self._building_response = False
        self._pending_session_id = None
        self._is_first_send = False
        self._session_last_active = None  # session 最后活跃时间
        self._SESSION_TIMEOUT = 1800  # session 超时阈值（秒），30 分钟
        self._last_thinking_segments = []  # 当前轮次思考分段
        self._last_diff_data = None  # 当前轮次 diff 数据
        self._has_stream_text = False  # 当前轮次是否已收到正文流
        self._sdk_permission_waiting = False  # SDK 权限等待标志
        self._pending_new_conv_id = None  # 新建但未发送的对话 ID

        # 项目工作目录（优先使用环境变量，回退到当前目录）
        self._project_dir = os.environ.get("CCVIEW_PROJECT_DIR") or os.getcwd()
        print(f"[CC-view] 项目目录: {self._project_dir}")

        self._build()

        # 应用主题样式（在 _build 之后，确保面板已创建）
        self._apply_theme()

        # 连接主题变更信号
        theme_manager.theme_changed.connect(self._apply_theme)
        QTimer.singleShot(300, self._init_content)

    def _apply_theme(self):
        """应用主题样式到主窗口"""
        try:
            theme = theme_manager.get_current_theme()

            # 更新主窗口背景
            self.setStyleSheet(f"""
                QMainWindow {{ background-color: {theme['bg_primary']}; }}
            """)
        except Exception as e:
            print(f"主题应用错误: {e}")
            return

        # 更新左侧面板主题（独立 try-except）
        try:
            if hasattr(self, 'left_panel') and self.left_panel is not None:
                if hasattr(self.left_panel, 'update_theme'):
                    self.left_panel.update_theme()
        except Exception as e:
            print(f"主题应用错误: {e}")

        # 更新中心面板主题（独立 try-except）
        try:
            if hasattr(self, 'center_panel') and self.center_panel is not None:
                if hasattr(self.center_panel, 'update_theme'):
                    self.center_panel.update_theme()
        except Exception as e:
            print(f"主题应用错误: {e}")

        # 更新右侧面板主题（独立 try-except）
        try:
            if hasattr(self, 'right_panel') and self.right_panel is not None:
                if hasattr(self.right_panel, 'update_theme'):
                    self.right_panel.update_theme()
        except Exception as e:
            print(f"主题应用错误: {e}")

        # 后台 git 工作线程 - 临时禁用以调试线程问题
        # self._worker_thread = QThread()
        # self.git_worker = GitWorker()
        # self.git_worker.moveToThread(self._worker_thread)
        # self.git_worker.files_ready.connect(self._on_files_ready)
        # self.git_worker.status_ready.connect(self._on_status_ready)
        # self._worker_thread.start()

        # 定时刷新 - 临时禁用以调试线程问题
        # self.change_timer = QTimer()
        # self.change_timer.timeout.connect(self._schedule_git_status)
        # self.change_timer.start(8000)

        # session 超时检查定时器（每 60 秒检查一次）
        self._session_check_timer = QTimer()
        self._session_check_timer.timeout.connect(self._check_session_timeout)
        self._session_check_timer.start(60000)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        self.left_panel = LeftPanel()
        self.center_panel = CenterPanel()
        self.right_panel = RightPanel()

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.center_panel)
        main_layout.addWidget(self.right_panel)

        # 信号绑定
        self.center_panel.send_clicked.connect(self._on_send)
        self.center_panel.stop_clicked.connect(self._on_stop)
        self.center_panel.permission_accept_clicked.connect(self._on_permission_accept)
        self.center_panel.permission_reject_clicked.connect(self._on_permission_reject)
        self.left_panel.new_btn.clicked.connect(self._new_conversation)
        self.left_panel.conv_list.itemClicked.connect(self._on_select_conversation)
        self.left_panel.rename_requested.connect(self._on_rename_requested)
        self.left_panel.delete_requested.connect(self._on_delete_requested)
        self.center_panel.btn_ref.clicked.connect(self._insert_at)
        self.center_panel.btn_agent.clicked.connect(self._insert_hash)
        self.center_panel.btn_prompt.clicked.connect(self._insert_bang)
        self.center_panel.btn_skill.clicked.connect(self._insert_dollar)
        self.center_panel.btn_image.clicked.connect(self._upload_image)
        # 着陆页发送信号
        self.center_panel.landing_page.send_clicked.connect(self._on_landing_send)
        # 输入框回车发送
        self.center_panel.input_box.keyPressEvent = self._input_key_press

    def _init_content(self):
        self._load_saved_conversations()
        # 临时禁用git相关功能
        # self._schedule_git_files()
        # self._schedule_git_status()
        # 无对话时显示着陆页
        if not self.current_conv_id:
            self.center_panel.show_landing()

    def _load_saved_conversations(self):
        self.left_panel.clear_conversations()
        convs = list_conversations()
        for conv in convs:
            preview = ""
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:40]
                    break
            self.left_panel.add_conversation(conv["title"], preview, conv["id"])

        if convs:
            self._select_conversation(convs[0]["id"])

    def _select_conversation(self, conv_id):
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        # 淡出当前内容
        if hasattr(self.center_panel, 'msg_scroll') and self.center_panel.msg_scroll.isVisible():
            animation_manager.fade_out(self.center_panel.msg_scroll, 200, 'ease-out', 
                                      lambda: self._load_conversation_with_animation(conv_id))
        else:
            self._load_conversation_with_animation(conv_id)
    
    def _load_conversation_with_animation(self, conv_id):
        """带动画加载对话内容"""
        conv = load_conversation(conv_id)
        if not conv:
            return

        self.current_conv_id = conv_id
        self._is_first_send = False
        self.center_panel.clear_messages()
        self.center_panel.hide_landing()

        for msg in conv.get("messages", []):
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                continue
            self.center_panel.add_message(role, text)
            # 如果有 thinking 信息，在 AI 消息后面恢复思考块
            if role == "assistant" and "thinking" in msg:
                segments = msg.get("thinking_segments")
                if segments and isinstance(segments, list):
                    for seg in segments:
                        self.center_panel.add_thinking_block(seg.get("text", ""), seg.get("duration_ms", 0), in_progress=False)
                else:
                    thinking_text = msg["thinking"]
                    thinking_ms = msg.get("thinking_duration_ms", 0)
                    self.center_panel.add_thinking_block(thinking_text, thinking_ms, in_progress=False)
            # 如果有 diff 数据，恢复 DiffCard
            if role == "assistant" and "diff_data" in msg:
                diff_data = msg["diff_data"]
                if diff_data and isinstance(diff_data, list):
                    self.center_panel.add_diff_card(diff_data)

        # 高亮左侧列表项
        for i in range(self.left_panel.conv_list.count()):
            item = self.left_panel.conv_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == conv_id:
                self.left_panel.conv_list.setCurrentItem(item)
                break

        # 淡入新内容
        if hasattr(self.center_panel, 'msg_scroll'):
            animation_manager.fade_in(self.center_panel.msg_scroll, 300, 'ease-in')

    def _on_select_conversation(self, item):
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if conv_id:
            self._select_conversation(conv_id)

    def _schedule_git_files(self):
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self.git_worker, "fetch_files", Qt.ConnectionType.QueuedConnection)

    def _schedule_git_status(self):
        from PyQt6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self.git_worker, "fetch_status", Qt.ConnectionType.QueuedConnection)

    def _on_files_ready(self, files):
        self.right_panel.file_list.clear()
        if files:
            for f in files:
                self.right_panel.file_list.addItem(f)
        else:
            self.right_panel.file_list.addItem("（未找到 git 仓库）")

    def _on_status_ready(self, status):
        """文件变更状态更新（仅打印日志）。"""
        changes = []
        for path in status.get("modified", []):
            changes.append(f"[已修改] {path}")
        for path in status.get("added", []):
            changes.append(f"[已新增] {path}")
        for path in status.get("deleted", []):
            changes.append(f"[已删除] {path}")
        if changes:
            print(f"[GitStatus] {len(changes)} 个变更")

    def _input_key_press(self, event):
        """Enter 发送，Shift+Enter 换行。"""
        if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._on_send()
            return
        QTextEdit.keyPressEvent(self.center_panel.input_box, event)

    def _on_landing_send(self, text):
        """从着陆页发送消息：创建新对话并发送。"""
        if self._building_response:
            return
        # 创建新对话
        self._new_conversation(silent=True)
        # 用着陆页的文本发送
        self.center_panel.input_box.setText(text)
        self._on_send()

    def _on_send(self):
        """发送消息。"""
        if self._building_response:
            return

        text = self.center_panel.input_box.toPlainText().strip()
        if not text:
            return
        self.center_panel.input_box.clear()

        if not self.current_conv_id:
            self._new_conversation(silent=True)

        # 检查 session 是否超时，如果超时则清空 session_id
        if self._session_last_active:
            elapsed = (datetime.now() - self._session_last_active).total_seconds()
            if elapsed > self._SESSION_TIMEOUT:
                # session 已超时，清空 session_id，创建新 session
                conv = load_conversation(self.current_conv_id)
                if conv and conv.get("session_id"):
                    conv["session_id"] = None
                    save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                    print(f"[Session] session 已超时（{elapsed:.0f}秒），清空 session_id")
                self._session_last_active = None

        conv_id = self.current_conv_id
        conv = load_conversation(conv_id)
        if not conv:
            return
        messages = conv.get("messages", [])

        # 标记是否首次发送：已有对话但 messages 为空 = 第一次发消息
        is_first = (len(messages) == 0)
        if is_first:
            self._is_first_send = True

        # 添加并显示用户消息
        messages.append({"role": "user", "content": text})
        self.center_panel.add_message("user", text)

        save_conversation(conv_id, conv.get("title", "新增对话"), messages)

        # 更新按钮为停止模式
        self.center_panel.set_building_response(True)
        self._building_response = True

        # 添加 AI 占位消息（带表情 + 动画）
        self.center_panel.add_message("assistant", "🤔 思考中...")
        self._last_thinking_segments = []
        self._last_diff_data = None  # 清空上一轮的 diff 数据
        self._has_stream_text = False

        # 获取当前对话的 session_id（用于续接历史对话）
        session_id = conv.get("session_id") if conv else None
        self._pending_session_id = None  # 重置 pending

        # 构建对话上下文（只取最后一条用户消息，历史由 Claude session 管理）
        prompt = self.claude_client.build_prompt(messages)
        model_name = self.center_panel.model_combo.currentText()
        model = {"opus (最强)": "opus", "sonnet (推荐)": "sonnet", "haiku (最快)": "haiku"}.get(model_name, "sonnet")
        perm_ui = self.center_panel.permission_combo.currentText()
        permission_mode = "default"
        if perm_ui.startswith("acceptEdits"):
            permission_mode = "acceptEdits"
        elif perm_ui.startswith("plan"):
            permission_mode = "plan"

        # 创建 Claude 工作线程 — 使用 SDK 方案（真正的权限拦截）
        self._claude_thread = QThread()
        self._claude_worker = SDKClaudeWorker(prompt, model, session_id=session_id, permission_mode=permission_mode, project_dir=self._project_dir)
        self._claude_worker.moveToThread(self._claude_thread)
        self._claude_worker.chunk_ready.connect(self._on_chunk)
        self._claude_worker.result_ready.connect(self._on_claude_result)
        self._claude_worker.session_ready.connect(self._on_session_ready)
        self._claude_worker.thinking_started.connect(self._on_thinking_started)
        self._claude_worker.thinking_ready.connect(self._on_thinking_ready)
        self._claude_worker.status_update.connect(self._on_worker_status)
        self._claude_worker.error_occurred.connect(self._on_claude_error)
        self._claude_worker.stopped.connect(self._on_worker_stopped)
        self._claude_worker.tool_update.connect(self._on_tool_update)
        # SDK 权限请求信号
        self._claude_worker.permission_request.connect(self._on_sdk_permission_request)
        self._claude_thread.finished.connect(self._on_claude_thread_done)
        self._claude_thread.started.connect(self._claude_worker.run)
        self._claude_thread.start()

    def _on_session_ready(self, session_id):
        """收到 Claude 的 session_id（新对话首次创建）。"""
        self._pending_session_id = session_id

    def _on_thinking_started(self):
        """Claude 开始思考。"""
        self.center_panel.add_thinking_block("", 0, in_progress=True)
        if not self._has_stream_text:
            self.center_panel.update_processing_status("正在深度思考")

    def _on_thinking_ready(self, text, duration_ms):
        """收到一段完整思考内容。"""
        entry = {"text": text, "duration_ms": int(duration_ms or 0)}
        self._last_thinking_segments.append(entry)
        self.center_panel.add_thinking_block(text, duration_ms, in_progress=True)

    def _on_worker_status(self, status_text):
        """更新过程态状态，避免界面看起来无响应。"""
        if not self._has_stream_text:
            self.center_panel.update_processing_status(status_text)

    def _on_tool_update(self, tool_info):
        """收到工具调用更新。"""
        if hasattr(self, "right_panel"):
            self.right_panel.update_task(tool_info)

    def _on_claude_result(self, result):
        """Claude 执行完成。"""
        self._claude_thread.quit()
        self._claude_thread.wait(1000)
        self._building_response = False
        self._session_last_active = datetime.now()  # 更新活跃时间
        print(f"[Title] _on_claude_result, _is_first_send={self._is_first_send}, conv_id={self.current_conv_id}")
        self._finish_response(result)

    def _on_claude_error(self, error_msg):
        """Claude 执行出错。"""
        self._claude_thread.quit()
        self._claude_thread.wait(1000)
        self._building_response = False
        # 检测 session 相关错误（超时 / 超过最大 session 数）
        error_lower = error_msg.lower()
        if "session" in error_lower or "max" in error_lower or "limit" in error_lower or "timeout" in error_lower or "expire" in error_lower:
            # session 已失效，清空 session_id，下次发送时自动创建新 session
            if self.current_conv_id:
                conv = load_conversation(self.current_conv_id)
                if conv and conv.get("session_id"):
                    conv["session_id"] = None
                    save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                    print(f"[Session] 检测到 session 过期，已清空 session_id")
        self._handle_error(error_msg)

    def _on_worker_stopped(self):
        """Claude 被用户主动终止——只退出线程，清理在 _on_claude_thread_done 统一处理。"""
        print(f"[Stop] Worker 已停止，等待线程退出")
        self._claude_thread.quit()

    def _on_claude_thread_done(self):
        """Claude 线程已结束——统一清理入口。"""
        if self._building_response:
            # 非正常完成（非 result、非 error），做停止清理
            print(f"[Stop] 线程异常退出，执行清理")
            self._on_stop_cleanup()

    def _on_stop_cleanup(self):
        """停止后的清理工作。"""
        if not self._building_response:
            return  # 已经清理过了
        self._building_response = False
        self._last_thinking_segments = []
        self._last_diff_data = None
        self.center_panel.set_building_response(False)
        self.center_panel.set_thinking_block_state(False)
        # 移除最后的"思考中..."占位消息
        self.center_panel.remove_thinking_placeholder()

    def _on_chunk(self, text):
        """收到 AI 的流式回复片段（主线程）。"""
        self._has_stream_text = True
        self.center_panel.update_last_message(text)

    def _on_sdk_permission_request(self, tool_name, input_data):
        """SDKClaudeWorker 发来的权限请求（在主线程执行）。"""
        summary = f"权限申请：{tool_name}"
        if tool_name == "Write":
            fp = input_data.get("file_path", "")
            if fp:
                summary += f"\n{fp}"
        elif tool_name == "Bash":
            cmd = input_data.get("command", "")
            if cmd:
                summary += f"\n{cmd}"
        print(f"[SDK Permission] {summary}")
        # 设置 SDK 权限等待标志
        self._sdk_permission_waiting = True
        self.center_panel.show_permission_request(summary)

    def _on_permission_accept(self):
        """用户允许权限。"""
        if getattr(self, "_sdk_permission_waiting", False) and self._claude_worker:
            self._sdk_permission_waiting = False
            self._claude_worker.set_permission_decision("allow")
            self.center_panel.hide_permission_request()
            return
        self.center_panel.hide_permission_request()
        self.center_panel.input_box.setText("可以编辑，请继续")
        self._on_send()

    def _on_permission_reject(self):
        """用户拒绝权限。"""
        if getattr(self, "_sdk_permission_waiting", False) and self._claude_worker:
            self._sdk_permission_waiting = False
            self._claude_worker.set_permission_decision("deny")
            self.center_panel.hide_permission_request()
            return
        self.center_panel.hide_permission_request()

    def _finish_response(self, full_text):
        """在主线程完成回复处理。"""
        self.center_panel.set_thinking_block_state(False)

        # AI 回复完成后，自动获取 git diff 并添加到消息区
        self._add_diff_card_if_needed()

        # 多轮 tool_use 场景下，result 可能只含最后一段文本。
        # 若流式阶段已显示更完整内容，优先保留更完整版本，避免被覆盖。
        displayed_text = self.center_panel.get_last_message_text()
        final_text = full_text or ""
        if displayed_text and len(displayed_text.strip()) > len(final_text.strip()):
            final_text = displayed_text

        self.center_panel.update_last_message(final_text)
        self._session_last_active = datetime.now()  # 更新活跃时间

        if self.current_conv_id:
            conv = load_conversation(self.current_conv_id)
            if conv:
                messages = conv.get("messages", [])
                # 保存 assistant 消息，带上 thinking 信息
                assistant_msg = {"role": "assistant", "content": final_text}
                if self._last_thinking_segments:
                    thinking_text = "\n\n".join(
                        f"[第{idx}段 | 用时 {seg.get('duration_ms', 0)}毫秒]\n{seg.get('text', '')}"
                        for idx, seg in enumerate(self._last_thinking_segments, start=1)
                    )
                    thinking_ms = sum(max(0, int(seg.get("duration_ms", 0))) for seg in self._last_thinking_segments)
                    assistant_msg["thinking"] = thinking_text
                    assistant_msg["thinking_duration_ms"] = thinking_ms
                    assistant_msg["thinking_segments"] = self._last_thinking_segments
                    self._last_thinking_segments = []  # 消费后清空
                # 保存 diff 数据
                if self._last_diff_data:
                    assistant_msg["diff_data"] = self._last_diff_data
                    self._last_diff_data = None
                messages.append(assistant_msg)
                session_id = self._pending_session_id or conv.get("session_id")

                if self._is_first_send:
                    # 首次发送：先保存规则生成的临时标题，再后台调用 AI 生成
                    temp_title = self._generate_title(final_text)
                    save_conversation(self.current_conv_id, temp_title, messages, session_id)
                    self._is_first_send = False
                    self._pending_new_conv_id = None  # 已发送，清除 pending
                    self._refresh_sidebar_preview()
                    # 后台 AI 生成标题（不阻塞 UI）
                    self._start_ai_title_generation(final_text)
                else:
                    save_conversation(self.current_conv_id, conv.get("title", "新增对话"), messages, session_id)

                self._pending_session_id = None

        self.center_panel.set_building_response(False)

    def _add_diff_card_if_needed(self):
        """AI 回复完成后，检查 git diff 并添加到消息区。"""
        try:
            diff_text = DiffParser.get_all_diffs(
                working_dir=self._project_dir
            )
            if diff_text and diff_text.strip():
                files_diff = DiffParser.parse(diff_text)
                if files_diff:
                    self.center_panel.add_diff_card(files_diff)
                    # 保存 diff 数据，用于持久化
                    self._last_diff_data = [{
                        "file": f["file"],
                        "additions": f["additions"],
                        "deletions": f["deletions"],
                        "hunks": [{
                            "old_start": h["old_start"],
                            "old_count": h["old_count"],
                            "new_start": h["new_start"],
                            "new_count": h["new_count"],
                            "lines": h["lines"],
                        } for h in f["hunks"]]
                    } for f in files_diff if f["hunks"]]
                    print(f"[Diff] 检测到 {len(files_diff)} 个文件变更")
                else:
                    print("[Diff] git diff 输出无法解析")
            else:
                print("[Diff] 无文件变更")
        except Exception as e:
            print(f"[Diff] 获取 diff 失败: {e}")

    def _generate_title(self, ai_text):
        """规则生成临时标题——优先用用户第一条消息的关键词。"""
        # 优先取用户第一条消息
        if self.current_conv_id:
            conv = load_conversation(self.current_conv_id)
            if conv:
                for msg in conv.get("messages", []):
                    if msg.get("role") == "user":
                        text = msg.get("content", "").strip()
                        # 去掉特殊前缀（@ # ! $ 等命令符）
                        cleaned = text.lstrip("@#!$").strip()
                        # 如果用户消息很短（<6字），结合 AI 回复
                        if len(cleaned) < 6:
                            break
                        # 提取关键词：去掉常见无意义前缀
                        prefixes = ["请问", "帮我", "请帮我", "帮我写", "请写", "能不能", "如何", "为什么", "什么是", "解释一下", "分析一下"]
                        for p in prefixes:
                            if cleaned.startswith(p):
                                cleaned = cleaned[len(p):]
                                break
                        cleaned = cleaned.strip()
                        # 截断到 12 字
                        if len(cleaned) > 12:
                            return cleaned[:12] + "…"
                        return cleaned if cleaned else text
                        break
        # 降级：用 AI 回复的第一行关键词
        if ai_text and ai_text.strip():
            first_line = ai_text.strip().split("\n")[0].strip()
            # 去掉 markdown 符号
            first_line = first_line.lstrip("#*`- ").strip()
            if len(first_line) > 12:
                return first_line[:12] + "…"
            return first_line
        return "新增对话"

    def _start_ai_title_generation(self, ai_reply):
        """后台调用 AI 生成标题，失败自动降级。"""
        print(f"[Title] 开始 AI 标题生成，conv_id={self.current_conv_id}")
        # 获取用户第一条消息
        user_msg = ""
        conv = load_conversation(self.current_conv_id)
        if conv:
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    user_msg = msg.get("content", "")
                    break

        if not user_msg and not ai_reply:
            return

        self._title_worker = TitleWorker(user_msg, ai_reply)
        self._title_worker.title_ready.connect(self._on_title_ready)
        self._title_worker.finished.connect(self._on_title_worker_done)
        self._title_worker.start()

    def _on_title_ready(self, title):
        """AI 标题生成完成。"""
        print(f"[Title] AI 标题: '{title}'")
        if title and len(title) > 0 and self.current_conv_id:
            # 截断到 12 字
            if len(title) > 12:
                title = title[:12] + "…"
            conv = load_conversation(self.current_conv_id)
            if conv:
                # 用 AI 生成的标题替换当前标题（无论是否默认值）
                save_conversation(self.current_conv_id, title, conv.get("messages", []), conv.get("session_id"))
                self._refresh_sidebar_preview()
                print(f"[Title] AI 生成标题: {title}")

    def _on_title_worker_done(self):
        """TitleWorker 线程完成——无论成功失败都到此。"""
        print(f"[Title] TitleWorker 线程完成")

    def _on_stop(self):
        """用户主动终止 AI 回复。"""
        if not self._building_response or not hasattr(self, '_claude_worker'):
            return
        self._claude_worker.stop()
        print(f"[Stop] 已终止 Claude 回复")

    def _handle_error(self, error_msg):
        self.center_panel.update_last_message(f"[出错] {error_msg}")
        self.center_panel.set_building_response(False)
        self.center_panel.set_thinking_block_state(False)
        self._last_thinking_segments = []
        self._last_diff_data = None

    def _check_session_timeout(self):
        """定时检查 session 是否超时。"""
        if not self._session_last_active or not self.current_conv_id:
            return
        elapsed = (datetime.now() - self._session_last_active).total_seconds()
        if elapsed > self._SESSION_TIMEOUT:
            conv = load_conversation(self.current_conv_id)
            if conv and conv.get("session_id"):
                conv["session_id"] = None
                save_conversation(self.current_conv_id, conv.get("title", ""), conv.get("messages", []), session_id=None)
                print(f"[Session] 定时检查发现 session 超时（{elapsed:.0f}秒），已清空 session_id")
            self._session_last_active = None

    def _refresh_sidebar_preview(self):
        """只刷新侧边栏预览，不清空消息区。"""
        self.left_panel.clear_conversations()
        convs = list_conversations()
        for conv in convs:
            preview = ""
            for msg in conv.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg.get("content", "")[:40]
                    break
            self.left_panel.add_conversation(conv["title"], preview, conv["id"])

        # 高亮当前对话
        if self.current_conv_id:
            for i in range(self.left_panel.conv_list.count()):
                item = self.left_panel.conv_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == self.current_conv_id:
                    self.left_panel.conv_list.setCurrentItem(item)
                    break

    def _on_rename_requested(self, conv_id):
        """右键 → 重命名。"""
        conv = load_conversation(conv_id)
        if not conv:
            return
        old_title = conv.get("title", "未命名")
        new_title, ok = QInputDialog.getText(self, "重命名对话", "新标题：", text=old_title)
        if ok and new_title.strip():
            messages = conv.get("messages", [])
            save_conversation(conv_id, new_title.strip(), messages, conv.get("session_id"))
            self._refresh_sidebar_preview()

    def _on_delete_requested(self, conv_id):
        """右键 → 删除。"""
        if self._building_response:
            self._show_bounce_dialog("提示", "请等待当前对话完成", "warning")
            return

        conv = load_conversation(conv_id)
        if not conv:
            return
        title = conv.get("title", "未命名")
        
        # 使用QQ弹弹对话框
        dialog = self._create_bounce_dialog(
            "确认删除", 
            f"确定要删除对话「{title}」吗？\n此操作不可恢复。",
            "question"
        )
        
        def on_confirm():
            # 删除文件
            filepath = os.path.join(DATA_DIR, f"{conv_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)

            # 如果删除的是当前对话，切换或清空
            if self.current_conv_id == conv_id:
                self.current_conv_id = None
                self._pending_session_id = None
                if self._pending_new_conv_id == conv_id:
                    self._pending_new_conv_id = None
                # 尝试选中相邻对话
                convs = list_conversations()
                if convs:
                    self._select_conversation(convs[0]["id"])
                else:
                    self.center_panel.show_landing()

            self._refresh_sidebar_preview()
        
        dialog.accepted.connect(on_confirm)
        dialog.show()

    def _create_bounce_dialog(self, title, message, dialog_type="info"):
        """创建QQ弹弹对话框"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PyQt6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(400, 200)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        # 主题样式
        theme = theme_manager.get_current_theme()
        
        # 对话框布局
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 图标和消息
        message_layout = QHBoxLayout()
        
        # 图标
        icon_label = QLabel()
        icon_map = {
            "question": "❓",
            "warning": "⚠️", 
            "info": "ℹ️",
            "error": "❌"
        }
        icon_label.setText(icon_map.get(dialog_type, "ℹ️"))
        icon_label.setStyleSheet(f"font-size: 24px; padding: 10px;")
        message_layout.addWidget(icon_label)
        
        # 消息文本
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"""
            font-size: 14px;
            color: {theme['text_primary']};
            padding: 10px;
            line-height: 1.4;
        """)
        message_layout.addWidget(msg_label)
        
        layout.addLayout(message_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        if dialog_type == "question":
            # 取消按钮
            cancel_btn = QPushButton("取消")
            cancel_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme['bg_card']};
                    color: {theme['text_primary']};
                    border: 1px solid {theme['border']};
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {theme['bg_input']};
                }}
            """)
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)
            
            # 确认按钮
            confirm_btn = QPushButton("确认删除")
            confirm_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme['red']};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {theme['red_hover']};
                }}
            """)
            confirm_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(confirm_btn)
        else:
            # 确定按钮
            ok_btn = QPushButton("确定")
            ok_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {theme['primary']};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {theme['primary_hover']};
                }}
            """)
            ok_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # 对话框样式
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {theme['bg_card']};
                border: 1px solid {theme['border']};
                border-radius: 12px;
            }}
        """)
        
        # 应用弹跳动画
        dialog.show()
        animation_manager.bounce(dialog, 600)
        
        return dialog
    
    def _show_bounce_dialog(self, title, message, dialog_type="info"):
        """显示QQ弹弹对话框（仅显示，无需回调）"""
        dialog = self._create_bounce_dialog(title, message, dialog_type)
        dialog.exec()

    def _new_conversation(self, silent=False):
        if self._building_response:
            QMessageBox.warning(self, "提示", "请等待当前对话完成")
            return

        # 如果已有未发送的「新增对话」，直接跳转不新建
        if self._pending_new_conv_id:
            pending = load_conversation(self._pending_new_conv_id)
            if pending and pending.get("title") == "新增对话":
                self.current_conv_id = self._pending_new_conv_id
                self.center_panel.hide_landing()
                self.center_panel.clear_messages()
                if not silent:
                    self._refresh_sidebar_preview()
                return

        conv_id = str(uuid.uuid4())[:8]
        title = "新增对话"
        save_conversation(conv_id, title, [], session_id=None)
        self._pending_new_conv_id = conv_id
        self.current_conv_id = conv_id
        self._pending_session_id = None
        self._is_first_send = False
        self._session_last_active = None
        self.center_panel.hide_landing()
        self.center_panel.clear_messages()

        if not silent:
            self._refresh_sidebar_preview()

    def _insert_at(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "选择要引用的文件")
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read(2000)
                self.center_panel.input_box.setText(f"[引用: {os.path.basename(filepath)}] {content[:200]}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法读取文件: {e}")

    def _insert_hash(self):
        popup = PopupList("选择智能体", AGENT_LIST, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" #{popup.selected} ")

    def _insert_bang(self):
        items = [(n, t) for n, t in PROMPT_TEMPLATES.items()]
        popup = PopupList("插入提示词模板", items, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.setText(popup.selected)

    def _insert_dollar(self):
        popup = PopupList("调用 Skills", SKILLS_LIST, self)
        if popup.exec() and popup.selected:
            self.center_panel.input_box.insertPlainText(f" /{popup.selected} ")

    def _upload_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.gif *.webp);;所有文件 (*.*)"
        )
        if filepath:
            self.center_panel.add_message("user", f"[已上传图片: {os.path.basename(filepath)}]")

    def closeEvent(self, event):
        # 终止 Claude 子线程
        if hasattr(self, '_claude_thread') and self._claude_thread.isRunning():
            self._claude_thread.quit()
            self._claude_thread.wait(2000)
        # 终止标题生成线程
        if hasattr(self, '_title_worker') and self._title_worker.isRunning():
            self._title_worker.terminate()
            self._title_worker.wait(2000)
        self.claude_client.stop()
        # 临时禁用git线程清理
        # if hasattr(self, '_worker_thread'):
        #     self._worker_thread.quit()
        #     self._worker_thread.wait(2000)
        super().closeEvent(event)


def main():
    try:
        # 检查 claude CLI 是否已安装
        if subprocess.call(["claude", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
            print("错误: 未找到 claude 命令。")
            print("请先安装 Claude Code: https://docs.anthropic.com/zh-CN/docs/claude-code/CLI")
            sys.exit(1)

        app = QApplication([])
        app.setApplicationName("Claude Code 桌面助手")
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image", "ico.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        
        # 全局深色滚动条样式
        scrollbar_w = 8
        scrollbar_c = theme_manager.get_color('border_focus')
        scrollbar_bg = THEME.get('bg_primary', '#0F0F14')
        app.setStyleSheet(f"""
            QScrollBar:vertical {{
                background: {scrollbar_bg}; width: {scrollbar_w}px;
                border-radius: 4px; margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #3D3D5C; border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {scrollbar_c};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none; border: none;
            }}
            QScrollBar:horizontal {{
                background: {scrollbar_bg}; height: {scrollbar_w}px;
                border-radius: 4px; margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: #3D3D5C; border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {scrollbar_c};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none; border: none;
            }}
        """)
        
        window = MainWindow()
        window.show()

        # 处理 Ctrl+C 优雅退出
        import signal
        signal.signal(signal.SIGINT, lambda signum, frame: window.close())

        return app.exec()
        
    except Exception as e:
        print(f"程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
