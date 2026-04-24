#!/usr/bin/env python3
"""高级动画系统测试"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

# 导入动画管理器
from main import animation_manager, theme_manager

class AnimationTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("高级动画系统测试")
        self.setGeometry(100, 100, 600, 400)
        
        # 应用主题
        theme_manager.switch_theme("light")
        
        # 构建界面
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title = QLabel("高级动画系统测试")
        title.setStyleSheet(f"""
            font-size: 24px; 
            font-weight: bold; 
            color: {theme_manager.get_color('text_primary')};
            padding: 20px;
        """)
        layout.addWidget(title)
        
        # 测试按钮区域
        button_layout = QHBoxLayout()
        
        # 淡入淡出测试
        fade_btn = QPushButton("淡入淡出测试")
        fade_btn.clicked.connect(self.test_fade)
        fade_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_manager.get_color('primary')};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {theme_manager.get_color('primary_hover')};
            }}
        """)
        button_layout.addWidget(fade_btn)
        
        # 滑动测试
        slide_btn = QPushButton("滑动测试")
        slide_btn.clicked.connect(self.test_slide)
        slide_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_manager.get_color('green')};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {theme_manager.get_color('green_hover')};
            }}
        """)
        button_layout.addWidget(slide_btn)
        
        # 缩放测试
        scale_btn = QPushButton("缩放测试")
        scale_btn.clicked.connect(self.test_scale)
        scale_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_manager.get_color('orange')};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {theme_manager.get_color('red_hover')};
            }}
        """)
        button_layout.addWidget(scale_btn)
        
        layout.addLayout(button_layout)
        
        # 第二行按钮
        button_layout2 = QHBoxLayout()
        
        # 弹跳测试
        bounce_btn = QPushButton("弹跳测试")
        bounce_btn.clicked.connect(self.test_bounce)
        bounce_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_manager.get_color('purple')};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)
        button_layout2.addWidget(bounce_btn)
        
        # 摇晃测试
        shake_btn = QPushButton("摇晃测试")
        shake_btn.clicked.connect(self.test_shake)
        shake_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {theme_manager.get_color('teal')};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)
        button_layout2.addWidget(shake_btn)
        
        # 组合动画测试
        combo_btn = QPushButton("组合动画")
        combo_btn.clicked.connect(self.test_combo)
        combo_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {theme_manager.get_color('gradient_start')}, 
                    stop:1 {theme_manager.get_color('gradient_end')});
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.8;
            }}
        """)
        button_layout2.addWidget(combo_btn)
        
        layout.addLayout(button_layout2)
        
        # 测试区域
        self.test_area = QWidget()
        self.test_area.setFixedSize(400, 100)
        self.test_area.setStyleSheet(f"""
            QWidget {{
                background-color: {theme_manager.get_color('bg_card')};
                border: 2px dashed {theme_manager.get_color('border')};
                border-radius: 12px;
            }}
        """)
        layout.addWidget(self.test_area)
        
        # 测试标签
        self.test_label = QLabel("动画测试区域")
        self.test_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {theme_manager.get_color('text_primary')};
        """)
        self.test_label.setParent(self.test_area)
        self.test_label.setGeometry(50, 25, 300, 50)
        
        # 应用主题样式
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme_manager.get_color('bg_primary')};
            }}
        """)
    
    def test_fade(self):
        """测试淡入淡出"""
        print("测试淡入淡出动画...")
        animation_manager.fade_out(self.test_label, 500, 'ease-out', 
                                  lambda: animation_manager.fade_in(self.test_label, 500, 'ease-in'))
    
    def test_slide(self):
        """测试滑动动画"""
        print("测试滑动动画...")
        animation_manager.slide_out(self.test_label, 'left', 200, 400, 'ease-in',
                                  lambda: animation_manager.slide_in(self.test_label, 'right', 200, 400, 'ease-back'))
    
    def test_scale(self):
        """测试缩放动画"""
        print("测试缩放动画...")
        animation_manager.scale(self.test_label, 0.0, 1.2, 400, 'ease-back',
                               lambda: animation_manager.scale(self.test_label, 1.2, 1.0, 300, 'ease-out'))
    
    def test_bounce(self):
        """测试弹跳动画"""
        print("测试弹跳动画...")
        animation_manager.bounce(self.test_label, 600)
    
    def test_shake(self):
        """测试摇晃动画"""
        print("测试摇晃动画...")
        animation_manager.shake(self.test_label, 400)
    
    def test_combo(self):
        """测试组合动画"""
        print("测试组合动画...")
        # 创建动画序列
        animations = [
            lambda: animation_manager.scale(self.test_label, 1.0, 0.8, 200, 'ease-in'),
            lambda: animation_manager.bounce(self.test_label, 600),
            lambda: animation_manager.fade_out(self.test_label, 300, 'ease-out'),
            lambda: animation_manager.fade_in(self.test_label, 300, 'ease-in'),
            lambda: animation_manager.scale(self.test_label, 0.8, 1.0, 300, 'ease-back')
        ]
        
        # 顺序执行动画
        self.execute_sequence(animations, 0)
    
    def execute_sequence(self, animations, index):
        """执行动画序列"""
        if index < len(animations):
            animation = animations[index]()
            if hasattr(animation, 'finished'):
                animation.finished.connect(lambda: self.execute_sequence(animations, index + 1))
            else:
                # 对于没有finished信号的动画，使用延迟
                QTimer.singleShot(500, lambda: self.execute_sequence(animations, index + 1))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    window = AnimationTestWindow()
    window.show()
    
    print("高级动画系统测试程序启动成功！")
    print("点击按钮测试不同的动画效果。")
    
    sys.exit(app.exec())
