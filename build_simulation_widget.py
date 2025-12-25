# build_simulation_widget.py
import os
import sys
import re
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QPlainTextEdit, QLabel, QMenu, QMessageBox, QListWidget, 
    QListWidgetItem, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, 
    QTextEdit, QTabWidget, QDialogButtonBox, QApplication, QFrame
)
from PySide6.QtGui import (
    QAction, QTextCursor, QSyntaxHighlighter, QTextCharFormat, QPainter, 
    QColor, QTextBlock, QFont, QKeySequence, QShortcut, QClipboard, QTextFormat
)
from PySide6.QtCore import Qt, Signal, QRect, QSize

EDITOR_BACKGROUND = "#f0f0f0"

class LineNumberArea(QFrame):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

class MindesSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # ========== 深色彩虹渐变方案 (10种加深颜色) ==========
        # 从深红到深紫的渐变，确保在白色背景下有高对比度
        self.rainbow_colors = [
            QColor("#CC0000"),  # 深红色（原#FF3333）
            QColor("#CC5500"),  # 深橙红色（原#FF6600）
            QColor("#CC7700"),  # 深橙色（原#FF9900）
            QColor("#CC9900"),  # 深金黄色（原#FFCC00）
            QColor("#779900"),  # 深黄绿色（原#99CC00）
            QColor("#009900"),  # 深绿色（原#33CC33）
            QColor("#008866"),  # 深蓝绿色（原#00CC99）
            QColor("#006699"),  # 深蓝色（原#0099CC）
            QColor("#552299"),  # 深蓝紫色（原#6633CC）
            QColor("#772299"),  # 深紫色（原#9933CC）
        ]
        
        # 特殊符号格式（保持黑色，对比度最高）
        self.symbol_formats = {
            '.': self._create_format("#666666", False),           # 深灰点号
            '=': self._create_format("#000000", True),            # 黑色等号加粗
            ',': self._create_format("#000000", False),           # 黑色逗号
            '@': self._create_format("#000000", True),            # 黑色@加粗
            '$': self._create_format("#000000", True),            # 黑色$加粗
        }
        
        # 括号格式（加深处理）
        self.brace_formats = {
            '(': self._create_format("#993300", False),           # 深棕色（原#D35400）
            ')': self._create_format("#993300", False),
            '[': self._create_format("#006633", False),           # 深绿色（原#27AE60）
            ']': self._create_format("#006633", False),
            '{': self._create_format("#003366", False),           # 深蓝色（原#2980B9）
            '}': self._create_format("#003366", False),
        }
        
        # 注释格式（加深为深灰色）
        self.comment_format = self._create_format("#3E8E00", True)  # 深绿色斜体
        self.comment_format.setFontItalic(True)
        
        # 右侧值类型格式（全部加深）
        self.value_formats = {
            'macro': self._create_format("#990000", True),        # 深红加粗，宏变量
            'number': self._create_format("#004488", False),      # 深蓝色，数值
            'boolean': self._create_format("#660066", True),      # 深紫色加粗，布尔值
            'at_content': self._create_format("#006666", True),   # 深青色加粗，@...@内容
        }
        
        # 预编译正则表达式（提高性能）
        self.number_pattern = re.compile(r'\b\d+(\.\d+)?\b')
        self.boolean_pattern = re.compile(r'\b(true|false)\b', re.IGNORECASE)
        self.tuple_pattern = re.compile(r'\([^)]+\)')
        self.macro_pattern = re.compile(r'\$[^$]+\$')
        
    def _create_format(self, color, bold=False):
        """创建文本格式的辅助方法"""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt
    
    def _get_token_color_index(self, token_index):
        """根据token索引获取彩虹色索引"""
        if token_index < len(self.rainbow_colors):
            return token_index
        else:
            # 超过10个token，循环使用第10个颜色（深紫色）
            return len(self.rainbow_colors) - 1

    def highlightBlock(self, text):
        """高亮处理一个文本块"""
        line = text.rstrip()
        
        # 1. 注释行处理
        if line.startswith('#'):
            self.setFormat(0, len(text), self.comment_format)
            return
        
        # 2. 分割键值对
        if '=' in line:
            eq_pos = line.find('=')
            left_side = line[:eq_pos].rstrip()
            right_side = line[eq_pos + 1:].lstrip()
            
            # ========== 左侧键路径高亮 (深彩虹色渐变) ==========
            if left_side:
                # 按点号分割并高亮
                start = 0
                tokens = left_side.split('.')
                for i, token in enumerate(tokens):
                    if token:
                        # 使用深彩虹色，每个层级使用不同颜色
                        color_index = self._get_token_color_index(i)
                        fmt = self._create_format(
                            self.rainbow_colors[color_index], 
                            i == 0  # 第一级加粗
                        )
                        
                        self.setFormat(start, len(token), fmt)
                        start += len(token)
                    
                    # 高亮点号（深灰色）
                    if i < len(tokens) - 1:
                        self.setFormat(start, 1, self.symbol_formats['.'])
                        start += 1
            
            # 高亮等号（黑色加粗）
            self.setFormat(eq_pos, 1, self.symbol_formats['='])
            
            # ========== 右侧值高亮 ==========
            if right_side:
                right_start = eq_pos + 1 + line[eq_pos + 1:].find(right_side)
                
                # 先按类型高亮内容
                self._highlight_value_content(right_start, right_side)
                
                # 再高亮特殊符号（会覆盖内容颜色）
                self._highlight_symbols(right_start, right_side)
    
    def _highlight_value_content(self, start_pos, text):
        """高亮右侧值的具体内容"""
        # 1. 高亮宏变量 $...$
        for match in self.macro_pattern.finditer(text):
            macro_start = start_pos + match.start()
            macro_text = match.group()
            # $符号本身用黑色
            self.setFormat(macro_start, 1, self.symbol_formats['$'])
            self.setFormat(macro_start + len(macro_text) - 1, 1, self.symbol_formats['$'])
            # 宏内容用深红色
            self.setFormat(macro_start + 1, len(macro_text) - 2, self.value_formats['macro'])
        
        # 2. 高亮元组 (..., ...)
        for match in self.tuple_pattern.finditer(text):
            # 避免匹配宏内的括号
            match_start = match.start()
            match_end = match.end()
            if not any(m.start() < match_start < m.end() for m in self.macro_pattern.finditer(text)):
                # 使用括号的深棕色
                self.setFormat(start_pos + match_start, match_end - match_start, self.brace_formats['('])
        
        # 3. 高亮数值
        for match in self.number_pattern.finditer(text):
            # 避免匹配元组或宏内的数字
            num_start = match.start()
            if not self._is_inside_special(text, num_start, ['(', '$']):
                self.setFormat(start_pos + num_start, match.end() - num_start, self.value_formats['number'])
        
        # 4. 高亮布尔值
        for match in self.boolean_pattern.finditer(text):
            bool_start = match.start()
            if not self._is_inside_special(text, bool_start, ['(', '$']):
                self.setFormat(start_pos + bool_start, match.end() - bool_start, self.value_formats['boolean'])
        
        # 5. 高亮Define中的@...@内容
        if '@' in text:
            at_start = text.find('@')
            at_end = text.rfind('@')
            if at_start != -1 and at_end != -1 and at_start < at_end:
                # @符号本身
                self.setFormat(start_pos + at_start, 1, self.symbol_formats['@'])
                self.setFormat(start_pos + at_end, 1, self.symbol_formats['@'])
                # @之间的内容
                self.setFormat(start_pos + at_start + 1, at_end - at_start - 1, self.value_formats['at_content'])
    
    def _highlight_symbols(self, start_pos, text):
        """高亮特殊符号"""
        for i, char in enumerate(text):
            pos = start_pos + i
            if char in self.brace_formats:
                self.setFormat(pos, 1, self.brace_formats[char])
            elif char in [',', '@', '$']:
                # 确保符号颜色覆盖其他高亮
                if char == ',':
                    self.setFormat(pos, 1, self.symbol_formats[','])
                elif char == '@':
                    self.setFormat(pos, 1, self.symbol_formats['@'])
                elif char == '$':
                    self.setFormat(pos, 1, self.symbol_formats['$'])
    
    def _is_inside_special(self, text, position, symbols):
        """检查位置是否在特殊结构内"""
        for i in range(position):
            if text[i] in symbols:
                # 找到最近的配对符号
                pair_map = {'(': ')', '[': ']', '{': '}', '$': '$'}
                opening = text[i]
                closing = pair_map.get(opening)
                if closing:
                    # 查找配对的闭合符号
                    depth = 1
                    for j in range(i + 1, len(text)):
                        if text[j] == opening:
                            depth += 1
                        elif text[j] == closing:
                            depth -= 1
                            if depth == 0:
                                # 如果位置在这个配对内
                                if i < position < j:
                                    return True
                                break
        return False
    
class ReportSyntaxHighlighter(QSyntaxHighlighter):
    """专门用于 input_report.txt 文件的高亮器（简化版）"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # ========== 颜色定义 ==========
        
        # 标题/分隔线格式
        self.title_format = QTextCharFormat()
        self.title_format.setForeground(QColor("#4A5568"))  # 深灰色
        self.title_format.setFontWeight(QFont.Weight.Bold)
        
        # 宏格式（深红色）
        self.macro_format = QTextCharFormat()
        self.macro_format.setForeground(QColor("#8B0000"))  # 深红色
        
        # Define 格式（深绿色）
        self.define_format = QTextCharFormat()
        self.define_format.setForeground(QColor("#006400"))  # 深绿色
        
        # 默认函数格式（灰色斜体）
        self.default_func_format = QTextCharFormat()
        self.default_func_format.setForeground(QColor("#666666"))
        self.default_func_format.setFontItalic(True)
        
        # DEBUG 表格标题格式（蓝色）
        self.debug_header_format = QTextCharFormat()
        self.debug_header_format.setForeground(QColor("#000080"))  # 深蓝色
        self.debug_header_format.setFontWeight(QFont.Weight.Bold)
        
        # DEBUG 表格内容格式（黑色）
        self.debug_content_format = QTextCharFormat()
        self.debug_content_format.setForeground(QColor("#000000"))
        
        # 参数标记格式
        self.tag_formats = {
            "[DEFAULT]": QTextCharFormat(),  # 默认蓝色
            "[-VALID-]": QTextCharFormat(),  # 有效绿色
        }
        self.tag_formats["[DEFAULT]"].setForeground(QColor("#0000FF"))  # 蓝色
        self.tag_formats["[-VALID-]"].setForeground(QColor("#E74C3C"))  # 红色
        
        # 参数名格式（深蓝色）
        self.param_name_format = QTextCharFormat()
        self.param_name_format.setForeground(QColor("#00008B"))
        
        # 参数值格式（深紫色）
        self.param_value_format = QTextCharFormat()
        self.param_value_format.setForeground(QColor("#4B0082"))
        
        # 注释格式（灰色）
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#007F2A"))  # 深绿色
        self.comment_format.setFontItalic(True)
        
        # 分隔符格式（黑色）
        self.separator_format = QTextCharFormat()
        self.separator_format.setForeground(QColor("#000000"))

    def highlightBlock(self, text):
        """高亮处理一个文本块"""
        text_line = text.rstrip()
        
        # 空行不处理
        if not text_line:
            return
            
        # 1. 处理标题/分隔线（以 = 开头或包含大量 =）
        if text_line.startswith('=') or text_line.replace('=', '') == '':
            self.setFormat(0, len(text), self.title_format)
            return
            
        # 2. 处理宏定义（包含 $...$ 的行）
        if '$' in text_line:
            # 高亮整个宏部分
            start_idx = text_line.find('$')
            end_idx = text_line.rfind('$') + 1
            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                self.setFormat(start_idx, end_idx - start_idx, self.macro_format)
        
        # 3. 处理 Define 行
        if text_line.startswith('Define.'):
            self.setFormat(0, len(text_line), self.define_format)
            # 高亮等号
            if '=' in text_line:
                eq_pos = text_line.find('=')
                self.setFormat(eq_pos, 1, self.separator_format)
        
        # 4. 处理默认函数说明行
        if 'default functions' in text_line.lower():
            self.setFormat(0, len(text_line), self.default_func_format)
            
        # 5. 处理 DEBUG 表格标题
        if text_line.startswith('LINE') or text_line.startswith('NO.'):
            self.setFormat(0, len(text_line), self.debug_header_format)
            
        # 6. 处理 DEBUG 表格内容（包含 | 的行）
        if '|' in text_line and not text_line.startswith('---'):
            # 高亮整个行
            self.setFormat(0, len(text_line), self.debug_content_format)
            # 高亮分隔符 |
            for i, char in enumerate(text_line):
                if char == '|':
                    self.setFormat(i, 1, self.separator_format)
        
        # 7. 处理参数定义行（以 > 开头）
        if text_line.startswith('>'):
            # 高亮标记 [TAG]
            tag_start = text_line.find('[')
            tag_end = text_line.find(']') + 1 if ']' in text_line else -1
            
            if tag_start != -1 and tag_end != -1:
                tag_content = text_line[tag_start:tag_end]
                for tag, fmt in self.tag_formats.items():
                    if tag in tag_content:
                        self.setFormat(tag_start, tag_end - tag_start, fmt)
                        break
                        
            # 高亮参数名（标记之后，等号之前）
            eq_pos = text_line.find('=')
            if eq_pos != -1:
                # 参数名从标记之后到等号之前
                name_start = tag_end if tag_end != -1 else text_line.find('>') + 1
                name_end = eq_pos
                if name_start < name_end:
                    self.setFormat(name_start, name_end - name_start, self.param_name_format)
                    
                # 高亮等号
                self.setFormat(eq_pos, 1, self.separator_format)
                
                # 高亮参数值（等号之后）
                value_start = eq_pos + 1
                if value_start < len(text_line):
                    self.setFormat(value_start, len(text_line) - value_start, self.param_value_format)
        
        # 8. 处理注释行（以 # 开头）
        if text_line.startswith('#'):
            self.setFormat(0, len(text_line), self.comment_format)

class BuildSimulationWidget(QWidget):
    # 信号：当构建/运行完成时，通知主窗口结果目录路径
    simulationFinished = Signal(str)  # 发送 .mindes 同名结果文件夹路径
    class CodeEditor(QPlainTextEdit):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.line_number_area = LineNumberArea(self)
            self.blockCountChanged.connect(self.update_line_number_area_width)
            self.updateRequest.connect(self.update_line_number_area)
            self.cursorPositionChanged.connect(self.highlight_current_line)
            self.update_line_number_area_width()
            self.highlight_current_line()

        def line_number_area_width(self):
            digits = 1
            max_num = max(1, self.blockCount())
            while max_num >= 10:
                max_num //= 10
                digits += 1
            space = 8 + self.fontMetrics().horizontalAdvance('9') * digits
            return space

        def update_line_number_area_width(self):
            self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

        def update_line_number_area(self, rect, dy):
            if dy:
                self.line_number_area.scroll(0, dy)
            else:
                self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
            if rect.contains(self.viewport().rect()):
                self.update_line_number_area_width()

        def resizeEvent(self, event):
            super().resizeEvent(event)
            cr = self.contentsRect()
            self.line_number_area.setGeometry(
                QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
            )

        def line_number_area_paint_event(self, event):
            painter = QPainter(self.line_number_area)
            painter.fillRect(event.rect(), QColor(EDITOR_BACKGROUND))  # 淡灰色背景

            block = self.firstVisibleBlock()
            block_number = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            bottom = top + self.blockBoundingRect(block).height()

            height = self.fontMetrics().height()
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(block_number + 1)
                    painter.setPen(QColor("#666666"))
                    painter.drawText(
                        0,
                        int(top),
                        self.line_number_area.width() - 4,
                        height,
                        Qt.AlignRight,
                        number
                    )
                block = block.next()
                top = bottom
                bottom = top + self.blockBoundingRect(block).height()
                block_number += 1

        def highlight_current_line(self):
            extra_selections = []
            if not self.isReadOnly():
                selection = QTextEdit.ExtraSelection()
                line_color = QColor("#ffffcc")  # 淡黄色高亮当前行
                selection.format.setBackground(line_color)
                selection.format.setProperty(QTextFormat.FullWidthSelection, True)
                selection.cursor = self.textCursor()
                selection.cursor.clearSelection()
                extra_selections.append(selection)
            self.setExtraSelections(extra_selections)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_mindes_file = None  # 当前加载的 .mindes 文件绝对路径
        self.selected_solver_path = None  # 当前选中的求解器 exe 的绝对路径
        self.solver_dir = Path(__file__).parent / "solver"  # 求解器根目录（相对主程序）

        # 高亮器管理
        self.mindes_highlighter = None  # .mindes 文件高亮器
        self.report_highlighter = None  # input_report.txt 高亮器
        self.current_highlighter = None  # 当前活跃的高亮器

        # input report 识别
        self.parsed_definitions = None

        self.setup_ui()
        self.save_btn.setEnabled(False)
        self.build_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.load_solvers()
        self.switch_to_report_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.switch_to_report_shortcut.activated.connect(self._switch_to_input_report_if_needed)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # === 第一部分：顶部控制栏 ===
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        # Solver 下拉框
        self.solver_combo = QComboBox()
        self.solver_combo.setPlaceholderText("Select Solver...")
        self.solver_combo.currentTextChanged.connect(self.on_solver_selected)
        top_layout.addWidget(QLabel("Solver:"))
        top_layout.addWidget(self.solver_combo)

        # Save 按钮（新增）
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_current_content)
        self.save_btn.setShortcut(QKeySequence("Ctrl+S"))
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #A5D6A7;
                color: black;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #81C784;  /* 可选：加边框更清晰 */
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #81C784;  /* 悬停稍深一点 */
            }
            QPushButton:pressed {
                background-color: #66BB6A;
            }
        """)
        top_layout.addWidget(self.save_btn)

        # Build 按钮
        self.build_btn = QPushButton("Build")
        self.build_btn.clicked.connect(lambda: self.execute_solver(mode="build"))
        self.build_btn.setShortcut(QKeySequence("Ctrl+B"))
        self.build_btn.setStyleSheet("""
            QPushButton {
                background-color: #90CAF9;
                color: black;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #64B5F6;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #64B5F6;
            }
            QPushButton:pressed {
                background-color: #42A5F5;
            }
        """)
        top_layout.addWidget(self.build_btn)

        # Run 按钮
        self.run_btn = QPushButton("Run")
        self.run_btn.clicked.connect(lambda: self.execute_solver(mode="run"))
        self.run_btn.setShortcut(QKeySequence("Ctrl+R"))
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF9A9A;
                color: black;
                font-weight: bold;
                padding: 4px 8px;
                border: 1px solid #E57373;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #E57373;
            }
            QPushButton:pressed {
                background-color: #EF5350;
            }
        """)
        top_layout.addWidget(self.run_btn)

        top_layout.addStretch()
        layout.addLayout(top_layout)

        # === 第二部分：文本编辑区 ===
        self.text_edit = self.CodeEditor()
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_edit.setTabChangesFocus(False)
        # 关键：启用列选择模式
        self.text_edit.setTextInteractionFlags(
            self.text_edit.textInteractionFlags() | Qt.TextEditable
        )
        # 并设置：
        self.text_edit.setCenterOnScroll(False)
         # 设置等宽字体以确保字符对齐
        font = QFont()
        # 尝试使用常见的等宽字体，按优先级排序
        font_families = ["Consolas", "Courier New", "Monaco", "DejaVu Sans Mono", "monospace"]
        for family in font_families:
            font.setFamily(family)
            if font.family() == family:  # 检查字体是否可用
                break
        font.setPointSize(10)
        self.text_edit.setFont(font)
        # 强制白色背景，不随系统主题变化
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {{
                background-color: {bg};  /* 淡灰色 */
                color: black;
                selection-background-color: #cce5ff;
                selection-color: black;
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }}
        """.format(bg=EDITOR_BACKGROUND))
        # 创建高亮器实例
        self.mindes_highlighter = MindesSyntaxHighlighter(self.text_edit.document())
        self.report_highlighter = ReportSyntaxHighlighter(self.text_edit.document())
        
        # 默认使用 .mindes 高亮器
        self.current_highlighter = self.mindes_highlighter
        self.mindes_highlighter.setDocument(self.text_edit.document())
        self.report_highlighter.setDocument(None)  # 禁用报告高亮器

        self.text_edit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.text_edit)

        # === 第三部分：状态提示栏 ===
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.note_label = QLabel("Note:")
        self.note_label.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: black;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)
        self.status_line = QLabel("Ready.")
        self.update_status("Ready.")  # 初始状态设置
        self.status_line.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.status_line.setCursor(Qt.IBeamCursor)
        status_layout.addWidget(self.note_label)
        status_layout.addWidget(self.status_line, 1)
        # status_layout.addStretch()
        layout.addLayout(status_layout)

        # 内部状态
        self.is_showing_report = False  # 是否正在显示 input_report.txt

    def _switch_to_input_report_if_needed(self):
        """ .mindes 文件 和 report 文件互相切换"""
        if self.current_mindes_file:
            if self.is_showing_report:
                self.show_mindes_file()
            else:
                self.save_current_content()
                self.show_input_report()

    def load_solvers(self):
        """扫描 solver/ 目录下的子文件夹，每个子文件夹视为一个求解器（含 MInDes.exe）"""
        if not self.solver_dir.exists():
            self.update_status("Error: solver directory not found.", error=True)
            return

        solvers = []
        for item in self.solver_dir.iterdir():
            if item.is_dir():
                exe_path = item / "MInDes.exe"
                if exe_path.exists():
                    solvers.append((item.name, str(exe_path.resolve())))
        solvers.sort(key=lambda x: x[0])

        self.solver_combo.clear()
        for name, path in solvers:
            self.solver_combo.addItem(name, path)

        if solvers:
            self.solver_combo.setCurrentIndex(0)
            self.selected_solver_path = solvers[0][1]
        else:
            self.update_status("No solvers found in 'solver/' directory.", warning=True)

    def on_solver_selected(self, name):
        data = self.solver_combo.currentData()
        if data:
            self.selected_solver_path = data
            self.update_status(f"Solver selected: {name}")

    def set_mindes_content(self, file_path: str, content: str):
        """由主窗口调用：设置当前 .mindes 文件路径和内容"""
        self.current_mindes_file = os.path.abspath(file_path)
        # 确保使用正确的 .mindes 高亮器
        self.switch_highlighter(False)
        self.text_edit.setPlainText(content)
        self.is_showing_report = False
        self.update_status(f"Loaded: {os.path.basename(file_path)}")
        self.save_btn.setEnabled(True)
        self.build_btn.setEnabled(True)
        self.run_btn.setEnabled(True)
        # TODO: 可在此处添加语法高亮/着色逻辑（预留）
        # self.highlight_text()

    def execute_solver(self, mode: str):
        if not self.current_mindes_file:
            QMessageBox.warning(self, "No File", "Please load a .mindes file first.")
            return
        if not self.selected_solver_path:
            QMessageBox.warning(self, "No Solver", "Please select a solver.")
            return
        # 保存 .mindes 文件
        self.save_current_content()
        mindes_abs = os.path.abspath(self.current_mindes_file)
        solver_dir = os.path.dirname(self.selected_solver_path)
        start_in_path = os.path.join(solver_dir, "start.in")

        # 准备 start.in 内容
        lines = [mindes_abs]
        if mode == "run":
            lines.append("SOLVER_RUN")
        
        try:
            # 写入 start.in（使用 LF 换行符）
            with open(start_in_path, 'w', newline='\n', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            # 计算结果文件夹路径（.mindes 文件同名文件夹）
            mindes_base = os.path.splitext(mindes_abs)[0]  # 去掉 .mindes 扩展名
            result_folder = mindes_base  # 这就是求解器会创建的结果文件夹
            
            self.update_status(f"Executing {mode}...", info=True)
            
            # 执行求解器
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                [self.selected_solver_path],
                cwd=solver_dir,
                startupinfo=startupinfo,   # 用于隐藏窗口
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.update_status(f"{mode.capitalize()} completed successfully.", success=True)
                mindes_base = os.path.splitext(mindes_abs)[0]
                report_path = os.path.join(mindes_base, "input_report.txt")
                if os.path.exists(report_path):
                    try:
                        self._refresh_parsed_definitions()
                        # 可选：打印调试信息
                        print(f"Parsed: {len(self.parsed_definitions['variables'])} vars, "
                              f"{len(self.parsed_definitions['functions'])} funcs")
                    except Exception as e:
                        self.update_status(f"Warning: Failed to parse input_report.txt: {e}", warning=True)
                        self.parsed_definitions = None
                else:
                    self.parsed_definitions = None
                # 发射信号通知主窗口结果文件夹路径
                self.simulationFinished.emit(result_folder)
            else:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unknown error"
                self.update_status(f"{mode.capitalize()} failed: {error_msg}", error=True)
                
        except Exception as e:
            self.update_status(f"Execution error: {str(e)}", error=True)

    def show_context_menu(self, pos):
        """右键菜单处理"""
        menu = QMenu(self)
        cursor = self.text_edit.textCursor()
        has_selection = not cursor.selectedText().strip() == ""
        
        if not self.is_showing_report:
            # 显示 .mindes 文件时的菜单
            save_action = menu.addAction("Save (Ctrl+S)")
            Build_action = menu.addAction("Build (Ctrl+B)")
            Run_action = menu.addAction("Run (Ctrl+R)")
            menu.addSeparator()
            if has_selection:
                copy_action = menu.addAction("Copy (Ctrl+C)")
                cut_action = menu.addAction("Cut (Ctrl+X)")
            else:
                menu.addAction("No Selection").setEnabled(False)
                copy_action = None
                cut_action = None
            paste_action = menu.addAction("Paste (Ctrl+V)")
            menu.addSeparator()
            custom_def_action = menu.addAction("Custom Definitions")
            input_helper_action = menu.addAction("Input Helper")
            if has_selection:
                selected_text = cursor.selectedText()
                if self._is_valid_for_input_helper(selected_text):
                    input_helper_action.setEnabled(True)
                else:
                    input_helper_action.setEnabled(False)
            else:
                input_helper_action.setEnabled(False)
            read_report_action = menu.addAction("Switch to Input Report (Ctrl+D)")
            action = menu.exec(self.text_edit.mapToGlobal(pos))
            if action == read_report_action:
                self.save_current_content()
                self.show_input_report()
            elif action == save_action:
                self.save_current_content()
            elif action == Build_action:
                self.execute_solver(mode="build")
            elif action == Run_action:
                self.execute_solver(mode="run")
            elif action == custom_def_action:
                self._refresh_parsed_definitions()
                self.show_custom_definitions_popup()
            elif action == copy_action:
                self.text_edit.copy()
            elif action == cut_action:
                self.text_edit.cut()
            elif action == paste_action:
                self.text_edit.paste()
            elif action == input_helper_action and has_selection:
                self._launch_input_helper(cursor.selectedText())
        else:
            if has_selection:
                copy_action = menu.addAction("Copy")
                action = menu.exec(self.text_edit.mapToGlobal(pos))
                if action == copy_action:
                    self.text_edit.copy()
            else:
                menu.addAction("No Selection").setEnabled(False)
            read_write_action = menu.addAction("Switch to Input File (Ctrl+D)")
            action = menu.exec(self.text_edit.mapToGlobal(pos))
            if action == read_write_action:
                self.show_mindes_file()

    def _refresh_parsed_definitions(self):
        """重新读取 input_report.txt 并更新 self.parsed_definitions"""
        if not self.current_mindes_file:
            self.parsed_definitions = None
            return

        mindes_base = os.path.splitext(self.current_mindes_file)[0]
        report_path = os.path.join(mindes_base, "input_report.txt")

        if not os.path.exists(report_path):
            self.parsed_definitions = None
            return

        try:
            self.parsed_definitions = self.parse_input_report(report_path)
            self.update_status("Custom definitions reloaded.", success=True)
        except Exception as e:
            self.update_status(f"Failed to reload definitions: {e}", error=True)
            self.parsed_definitions = None

    def show_input_report(self):
        """显示 input_report.txt 文件"""
        if not self.current_mindes_file:
            return
            
        # 构建 input_report.txt 路径
        mindes_base = os.path.splitext(self.current_mindes_file)[0]
        report_path = os.path.join(mindes_base, "input_report.txt")
        
        if os.path.exists(report_path):
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 切换高亮器
                self.switch_highlighter(True)

                self.text_edit.setPlainText(content)
                self.text_edit.setReadOnly(True)
                self.is_showing_report = True
                self.update_status("Showing input_report.txt (read-only)")
            except Exception as e:
                self.update_status(f"Failed to read input_report.txt: {str(e)}", error=True)
        else:
            self.update_status("input_report.txt not found", warning=True)

    def _replace_selected_text(self, new_text: str):
        """替换当前选中文本"""
        cursor = self.text_edit.textCursor()
        cursor.insertText(new_text)
        self.text_edit.setTextCursor(cursor)

    def show_mindes_file(self):
        """切换回 .mindes 文件显示"""
        if not self.current_mindes_file:
            return
            
        try:
            with open(self.current_mindes_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # 切换高亮器
            self.switch_highlighter(False)

            self.text_edit.setPlainText(content)
            self.text_edit.setReadOnly(False)
            self.is_showing_report = False
            self.update_status(f"Editing: {os.path.basename(self.current_mindes_file)}")
        except Exception as e:
            self.update_status(f"Failed to reload .mindes file: {str(e)}", error=True)

    def update_status(self, message: str, error: bool = False, warning: bool = False, success: bool = False, info: bool = False):
        """更新状态栏消息和颜色"""
        self.status_line.setText(message)

        if error:
            self.status_line.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;  /* 淡灰色 */
                    color: red;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)
        elif warning:
            self.status_line.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: orange;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)
        elif success:
            self.status_line.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: green;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)
        elif info:
            self.status_line.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: blue;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)
        else:
            self.status_line.setStyleSheet("""
                QLabel {
                    background-color: #f0f0f0;
                    color: gray;
                    padding: 2px 4px;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-weight: bold;
                }
            """)

    def get_current_content(self):
        """获取当前文本编辑器的内容"""
        return self.text_edit.toPlainText()

    def save_current_content(self):
        """保存当前内容到 .mindes 文件（如果存在）"""
        if self.current_mindes_file and not self.is_showing_report:
            try:
                content = self.get_current_content()
                with open(self.current_mindes_file, 'w', newline='\n', encoding='utf-8') as f:
                    f.write(content)
                self.update_status("File saved successfully.", success=True)
                return True
            except Exception as e:
                self.update_status(f"Save failed: {str(e)}", error=True)
                return False
        return False

    def parse_input_report(self, report_path: str):
        """增强版解析：通过定位权威区块位置，避免用户输入干扰"""
        with open(report_path, 'r', encoding='utf-8') as f:
            lines = [line.rstrip('\n') for line in f.readlines()]

        # === 第一阶段：扫描所有关键标题的行号 ===
        macro_first_line = None
        default_func_first_line = None
        var_last_line = None
        func_last_line = None
        param_last_line = None

        for i, line in enumerate(lines):
            if "M a c r o" in line and macro_first_line is None:
                macro_first_line = i
            if "default functions" in line and default_func_first_line is None:
                default_func_first_line = i
            if "NO.\t\tVARIABLE\t|VALUE" in line:
                var_last_line = i  # 覆盖之前的，保留最后一个
            if "NO.\t\tFUNCTIONS\t|CONTENT" in line:
                func_last_line = i
            if "Parameters Definition" in line:
                param_last_line = i

        # === 提取内置函数（从第一个 default functions 行）===
        builtin_funcs = self._extract_builtin_functions_from_line(
            lines[default_func_first_line] if default_func_first_line is not None else ""
        )

        # === 初始化结果容器 ===
        variables = []
        functions = []
        parameters = []
        macros = []
        func_names = set()

        # === 第二阶段：按区块位置解析 ===

        # ---- 1. Macros (从第一个 "M a c r o" 到下一个分隔线) ----
        if macro_first_line is not None:
            i = macro_first_line + 1
            while i < len(lines) and not self._is_section_separator(lines[i]):
                self._parse_macro_line(lines[i], macros)
                i += 1

        # ---- 2. Variables (从最后一个 "VARIABLE" 表头后开始，到分隔线结束) ----
        if var_last_line is not None:
            i = var_last_line + 2  # 跳过表头和分隔线（如 "-0| VarName|0.1" 前有一行 "----"）
            while i < len(lines) and not self._is_section_separator(lines[i]):
                self._parse_variable_line(lines[i], variables, func_names)
                i += 1

        # ---- 3. Functions (从最后一个 "FUNCTIONS" 表头后开始) ----
        if func_last_line is not None:
            i = func_last_line + 2
            while i < len(lines) and not self._is_section_separator(lines[i]):
                self._parse_function_line(lines[i], functions, func_names, builtin_funcs)
                i += 1

        # ---- 4. Parameters (从最后一个 "Parameters Definition" 后的第一个 "> ..." 行开始) ----
        if param_last_line is not None:
            i = param_last_line + 1
            # 跳过空行和注释，直到遇到以 "> " 开头的行
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('>'):
                    break
                i += 1
            # 从该行开始，一直解析到文件结束（参数区无显式结束标记）
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith('>'):
                    self._parse_parameter_line(stripped, parameters)
                i += 1

        return {
            "variables": variables,
            "functions": functions,
            "parameters": parameters,
            "macros": macros
        }

    def _extract_builtin_functions_from_line(self, line: str) -> set:
        """从单行 'default functions : "..."' 中提取函数名"""
        default_hardcoded = {
            "pow", "sin", "cos", "exp", "log", "sqrt", 
            "ln", "abs", "tan", "asin", "acos", "atan"
        }
        if not line or 'default functions' not in line:
            return default_hardcoded
        
        import re
        matches = re.findall(r'"([^"]+)"', line)
        builtin_set = set()
        for match in matches:
            func_name = match.split('(', 1)[0].strip()
            if func_name:
                builtin_set.add(func_name)
        return builtin_set if builtin_set else default_hardcoded

    def _is_section_separator(self, line: str) -> bool:
        """判断一行是否为区块分隔线（支持 ==== 或 ----- 等）"""
        s = line.strip()
        if not s:
            return False
        # 全是 = 或 -（允许中间有空格？但通常没有）
        if all(c == '=' for c in s) or all(c == '-' for c in s):
            return True
        # 或以多个 = / - 开头（如 debug 分隔线）
        if s.startswith('===') or s.startswith('---'):
            return True
        return False

    def _parse_function_line(self, line: str, functions: list, func_names: set, builtin_funcs: set):
        parts = [p.strip().replace('\t', ' ') for p in line.split('|')]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            no_str, name, expr = parts[0], parts[1], parts[2]
            if no_str.isdigit():
                no = int(no_str)
                if name not in builtin_funcs:
                    cleaned_expr = self.clean_function_expression(expr)
                    functions.append({"no": no, "name": name, "expr": cleaned_expr})
                    func_names.add(name)

    def _parse_variable_line(self, line: str, variables: list, func_names: set):
        parts = [p.strip().replace('\t', ' ') for p in line.split('|')]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            no_str, name, value = parts[0], parts[1], parts[2]
            if no_str.isdigit():
                no = int(no_str)
                # 跳过纯数字名 和 已知函数名
                if not name.isdigit() and name not in func_names:
                    variables.append({"no": no, "name": name, "value": value})

    def _parse_parameter_line(self, line: str, parameters: list):
        import re
        match = re.match(r'>\s*\[([^\]]+)\]\s*([^=]+?)\s*=\s*(.+)', line)
        if match:
            tag, name, value = match.groups()
            name = name.strip()
            value = value.strip()
            # 跳过带索引的参数名，如 a(1), b[2], c{3}
            if re.search(r'[\(\[\{]\d+[\)\]\}]$', name) or re.search(r'\w+\(\d+\)$', name):
                return
            parameters.append({"tag": tag, "name": name, "value": value})

    def _parse_macro_line(self, line: str, macros: list):
        """
        解析宏定义行，支持一行多个宏（以逗号分隔的 $...$ = ... 模式）
        示例：
          '1.tube , $TUBE[1,10,2]$ = 1,3,5,7,9'
          '2.rand , $RAND_INT[1,10]$ = 1 - 10 , $RAND_REAL[1,10]$ = 1.000000 - 10.000000'
        """
        import re

        # 移除行首编号（如 "1.", "2."）
        line = re.sub(r'^\d+\.\w*\s*,?\s*', '', line)

        # 分割逗号，但注意值中可能含逗号（如 "1,3,5"），所以不能简单 split(',')
        # 改为：用正则匹配所有 $NAME[...]$ = value 模式
        # 注意：value 可能包含空格、连字符、数字、小数等

        # 先找出所有 $...$ 部分
        macro_pattern = r'\$([A-Za-z_]\w*)$$([^$$]*)\$\s*=\s*(.*?)(?=\s*,\s*\$|$)'
        # 解释：
        # - \$([A-Za-z_]\w*)$$([^$$]*)\$  → 捕获 NAME 和 [...]（不含 $）
        # - \s*=\s*                        → 等号
        # - (.*?)                          → 非贪婪捕获值
        # - (?=\s*,\s*\$|$)               → 后瞻：直到下一个 ", $" 或行尾

        matches = re.findall(macro_pattern, line)
        for name, signature, value in matches:
            macros.append({
                "name": name,
                "signature": signature,      # 如 "[1,10,2]"
                "value": value.strip()
            })

    def switch_highlighter(self, is_report_file: bool):
        """切换语法高亮器
        
        Args:
            is_report_file: True 表示切换到 report 高亮器，False 表示切换到 mindes 高亮器
        """
        if is_report_file:
            if self.current_highlighter != self.report_highlighter:
                # 切换到报告高亮器
                self.mindes_highlighter.setDocument(None)
                self.report_highlighter.setDocument(self.text_edit.document())
                self.current_highlighter = self.report_highlighter
        else:
            if self.current_highlighter != self.mindes_highlighter:
                # 切换到 .mindes 高亮器
                self.report_highlighter.setDocument(None)
                self.mindes_highlighter.setDocument(self.text_edit.document())
                self.current_highlighter = self.mindes_highlighter

    def _build_merged_definitions_data(self, variables, functions):
        """
        将变量列表和函数列表按名称合并，生成用于表格显示的统一数据列表。
        
        返回: List[Dict]，每个 dict 包含:
            - no: int
            - name: str
            - expression: str ('-' if no function)
            - value: str ('-' if no variable)
            - has_var: bool
            - has_func: bool
        """
        name_map = {}

        # 处理变量
        for var in variables:
            name = var["name"]
            name_map[name] = {
                "no": var["no"],
                "name": name,
                "expression": "-",
                "value": var["value"],
                "has_var": True,
                "has_func": False
            }

        # 处理函数（可能与变量同名）
        for func in functions:
            name = func["name"]
            if name in name_map:
                # 同名：补充表达式
                name_map[name]["expression"] = func["expr"]
                name_map[name]["has_func"] = True
            else:
                # 纯函数
                name_map[name] = {
                    "no": func["no"],
                    "name": name,
                    "expression": func["expr"],
                    "value": "-",
                    "has_var": False,
                    "has_func": True
                }

        # 转为列表并排序
        all_items = list(name_map.values())
        all_items.sort(key=lambda x: x["no"])
        return all_items

    def _populate_definition_table(self, table: QTableWidget, items: list):
        """
        将合并后的定义项列表填充到 QTableWidget 中。
        
        :param table: 目标表格控件
        :param items: 来自 _build_merged_definitions_data 的列表
        """
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            name_item = QTableWidgetItem(item["name"])
            # 仅纯函数名称加粗（变量或合并项不加粗）
            if item["has_func"] and not item["has_var"]:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            elif item["has_func"] and item["has_var"]:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(item["value"]))
            table.setItem(row, 2, QTableWidgetItem(item["expression"]))

    def show_custom_definitions_popup(self):
        variables = self.parsed_definitions.get("variables", []) if self.parsed_definitions else []
        functions = self.parsed_definitions.get("functions", []) if self.parsed_definitions else []

        if not variables and not functions:
            QMessageBox.information(self, "Custom Definitions", "No custom variables or functions found.")
            return

        # 创建非模态浮动窗口
        popup = QWidget(self, Qt.Window)
        popup.setWindowTitle("Custom Definitions")
        popup.resize(500, 400)
        layout = QVBoxLayout(popup)

        # 创建表格
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Name", "Value", "Expression"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectItems)  # 允许选中单个单元格
        table.setSortingEnabled(True)

        all_items = self._build_merged_definitions_data(variables, functions)
        all_items.sort(key=lambda x: x["no"])

        self._populate_definition_table(table, all_items)

        # === 列宽调整策略 ===
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # Name
        header.setSectionResizeMode(1, QHeaderView.Interactive)        # Expression (可拖)
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Value (填充剩余)

        # 存储引用，用于刷新
        popup.table = table
        popup.all_items = all_items  # 初始数据（仅用于类型判断，实际刷新会重载）

        # === 右键菜单 ===
        def show_context_menu(pos):
            context_menu = QMenu(popup)
            copy_action = context_menu.addAction("Copy")
            refresh_action = context_menu.addAction("Refresh")

            action = context_menu.exec(table.viewport().mapToGlobal(pos))
            if action == copy_action:
                selected = table.selectedItems()
                if selected:
                    text = selected[0].text()
                    QApplication.clipboard().setText(text)
            elif action == refresh_action:
                self._refresh_custom_definitions_table(popup)

        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(show_context_menu)

        layout.addWidget(table)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(popup.close)
        layout.addWidget(close_btn)

        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _refresh_custom_definitions_table(self, popup_widget):
        """刷新弹窗中的表格内容，并保持与主弹窗一致的合并逻辑"""
        mindes_base = os.path.splitext(self.current_mindes_file)[0]
        report_path = os.path.join(mindes_base, "input_report.txt")

        if not os.path.exists(report_path):
            QMessageBox.warning(popup_widget, "Refresh Failed", "input_report.txt not found.")
            return

        try:
            new_parsed = self.parse_input_report(report_path)
            variables = new_parsed.get("variables", [])
            functions = new_parsed.get("functions", [])

            all_items = self._build_merged_definitions_data(variables, functions)
            all_items.sort(key=lambda x: x["no"])

            # 清空并重填表格
            table = popup_widget.table
            
            self._populate_definition_table(table, all_items)

            # 关键：同步主状态，确保下次打开弹窗也是最新合并数据
            self.parsed_definitions = new_parsed
            self.update_status("Custom Definitions refreshed.", success=True)

        except Exception as e:
            QMessageBox.critical(popup_widget, "Refresh Error", f"Failed to refresh: {str(e)}")
            self.update_status(f"Refresh failed: {e}", error=True)

    def clean_function_expression(self, expr: str) -> str:
        """
        清理函数表达式中的调试标记
        示例:
          输入: '+{+[(VarName)*pow(VarName,2)]}'
          输出: 'VarName * pow(VarName, 2)'
        """
        s = expr.strip()
        if not s:
            return expr

        # 移除最外层的 { } 或 [ ]（递归移除）
        while (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
            s = s[1:-1].strip()

        # 移除所有前导 '+'（包括 "+(" 和 "+Var"）
        import re
        # 处理 "+(...)" → "(...)"
        s = re.sub(r'\+\s*\(', '(', s)
        # 处理 "+变量" → "变量"
        s = re.sub(r'\+\s*([a-zA-Z_]\w*)', r'\1', s)
        # 处理 "+数字" → "数字"
        s = re.sub(r'\+\s*(\d+(?:\.\d+)?)', r'\1', s)
        # 移除孤立的 '+'（如结尾）
        s = re.sub(r'\+\s*', ' ', s)

        # 可选：美化运算符（增加空格）
        s = re.sub(r'(\w)\*', r'\1 * ', s)
        s = re.sub(r'\*(\w)', r' * \1', s)

        # 合并多余空格
        s = re.sub(r'\s+', ' ', s).strip()

        return s if s else expr
###################################################################################
# INPUT HELPER MANAGER
    def _is_valid_for_input_helper(self, text: str) -> bool:
        """判断选中文本是否符合任一 Input Helper 的触发条件"""
        return (
            self._is_tuple_pattern(text)
        )
    def _launch_input_helper(self, selected_text: str):
        """根据选中文本类型，启动对应的 Input Helper 弹窗"""
        text = selected_text.strip()

        if self._is_tuple_pattern(text):
            self._show_tuple_helper(text)
        else:
            QMessageBox.information(self, "Input Helper", "No helper available for this selection.")
#----------------------------------------------------------------------------------
    def _is_tuple_pattern(self, text: str) -> bool:
        # 匹配 (a, b, c) 形式的元组
        return re.fullmatch(r'\([^)]+\)', text.strip()) is not None
    def _show_tuple_helper(self, current_text: str):
        """辅助生成元组 (a, b, c)"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Tuple Helper")
        layout = QVBoxLayout(dialog)

        label = QLabel(f"Edit tuple elements:")
        layout.addWidget(label)

        text_edit = QTextEdit()
        # 解析当前值（如 "(1, 2, 3)" → ["1", "2", "3"]）
        inner = current_text.strip()[1:-1] if len(current_text) > 2 else ""
        items = [x.strip() for x in inner.split(',')] if inner else []
        text_edit.setPlainText('\n'.join(items))
        layout.addWidget(text_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.Accepted:
            lines = text_edit.toPlainText().splitlines()
            new_tuple = "(" + ", ".join(line.strip() for line in lines if line.strip()) + ")"
            self._replace_selected_text(new_tuple)

###################################################################################

