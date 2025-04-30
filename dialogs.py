from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QKeySequence, QDoubleValidator, QColor, QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel, 
    QLineEdit, QWidget, QHBoxLayout, QAbstractItemView, 
    QListWidgetItem, QShortcut, QStyle, QFrame, QStyledItemDelegate, 
    QMessageBox, QFormLayout, QComboBox, QGroupBox, QGridLayout,
    QProgressBar, QTreeView
)
import fitz
import requests
import json
from api_endpoints import api
from typing import Optional, Dict
import os
import tempfile
import uuid
from datetime import datetime
import asyncio
import nest_asyncio
from bleak import BleakScanner, BleakClient


class GDTSymbolButton(QtWidgets.QPushButton):
    def __init__(self, symbol, name, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 65)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setAlignment(Qt.AlignCenter)
        
        symbol_label = QtWidgets.QLabel(symbol)
        symbol_label.setAlignment(Qt.AlignCenter)
        symbol_label.setStyleSheet("font-size: 20px; color: #495057; background: none; border: none;")
        layout.addWidget(symbol_label)
        
        name_label = QtWidgets.QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 10px; color: #495057; background: none; border: none;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

class DimensionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimension Details")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(550)
        
        # Define GDT symbols with their abbreviations
        self.gdt_symbols = {
            '⏥': 'Flatness',
            '↗': 'Straightness',
            '⏤': 'Cylindricity',
            '○': 'Circularity',
            '⌭': 'Profile of a Line',
            '⌒': 'Profile of a Surface',
            '⌓': 'Perpendicularity',
            '⏊': 'Parallelism',
            '∠': 'Angularity',
            '⫽': 'Position',
            '⌯': 'Concentricity',
            '⌖': 'Symmetry',
            '◎': 'Circular Runout',
            '⌰': 'Total Runout'
        }

        self.selected_gdt_symbol = None
        
        # Modern styling
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #495057;
                font-size: 13px;
                font-weight: 500;
                font-family: 'Segoe UI', sans-serif;
                padding: 4px 0;
                background: transparent;
                border: none;
            }
            QLineEdit {
                padding: 10px;
                border: 2px solid #e9ecef;
                border-radius: 6px;
                background-color: white;
                color: #212529;
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
                margin: 4px 0;
            }
            QLineEdit:focus {
                border: 2px solid #4dabf7;
                background-color: white;
            }
            QLineEdit:hover {
                border: 2px solid #adb5bd;
                background-color: #f8f9fa;
            }
            QComboBox {
                padding: 10px;
                border: 2px solid #e9ecef;
                border-radius: 6px;
                background-color: white;
                color: #212529;
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
                min-width: 200px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox:focus {
                border: 2px solid #4dabf7;
            }
            QComboBox:hover {
                border: 2px solid #adb5bd;
                background-color: #f8f9fa;
            }
            QPushButton {
                padding: 10px 24px;
                border-radius: 6px;
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: 500;
            }
            QPushButton#okButton {
                background-color: #4dabf7;
                color: white;
                border: none;
                min-width: 120px;
            }
            QPushButton#okButton:hover {
                background-color: #339af0;
            }
            QPushButton#cancelButton {
                background-color: #f8f9fa;
                color: #495057;
                border: 2px solid #e9ecef;
                min-width: 120px;
            }
            QPushButton#cancelButton:hover {
                background-color: #e9ecef;
                border: 2px solid #dee2e6;
            }
            QFrame#gdtFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                padding: 16px;
                margin: 8px 0;
                border: 2px solid #e9ecef;
            }
            QPushButton[isGDTButton="true"] {
                background-color: white;
                border: 2px solid #e9ecef;
                border-radius: 8px;
                padding: 8px;
                text-align: center;
            }
            QPushButton[isGDTButton="true"]:checked {
                background-color: #e7f5ff;
                border: 2px solid #4dabf7;
            }
            QPushButton[isGDTButton="true"]:hover {
                background-color: #f8f9fa;
                border: 2px solid #adb5bd;
            }
        """)
        
        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(12)
        
        # Form layout
        form_layout = QtWidgets.QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Create input fields with validators
        self.nominal_edit = QtWidgets.QLineEdit()
        self.nominal_edit.setPlaceholderText("Enter nominal value")
        self.nominal_edit.setValidator(QtGui.QDoubleValidator())
        
        self.upper_tol_edit = QtWidgets.QLineEdit()
        self.upper_tol_edit.setPlaceholderText("Enter upper tolerance")
        self.upper_tol_edit.setValidator(QtGui.QDoubleValidator())
        
        self.lower_tol_edit = QtWidgets.QLineEdit()
        self.lower_tol_edit.setPlaceholderText("Enter lower tolerance")
        self.lower_tol_edit.setValidator(QtGui.QDoubleValidator())
        
        self.dim_type_combo = QtWidgets.QComboBox()
        self.dim_type_combo.addItems([
            "Length", "Diameter", "Radius", "Angular", 
            "Position", "Profile", "GDT", "Other"
        ])
        
        # Add fields to form layout
        form_layout.addRow(QtWidgets.QLabel("Nominal Value"), self.nominal_edit)
        form_layout.addRow(QtWidgets.QLabel("Upper Tolerance"), self.upper_tol_edit)
        form_layout.addRow(QtWidgets.QLabel("Lower Tolerance"), self.lower_tol_edit)
        form_layout.addRow(QtWidgets.QLabel("Dimension Type"), self.dim_type_combo)
        
        main_layout.addLayout(form_layout)
        
        # GDT frame
        self.gdt_symbol_frame = QtWidgets.QFrame()
        self.gdt_symbol_frame.setObjectName("gdtFrame")
        self.gdt_symbol_frame.setVisible(False)
        self.gdt_symbol_frame.setSizePolicy(QtWidgets.QSizePolicy.Preferred, 
                                          QtWidgets.QSizePolicy.Fixed)
        
        gdt_layout = QtWidgets.QVBoxLayout(self.gdt_symbol_frame)
        gdt_layout.setContentsMargins(8, 8, 8, 8)
        gdt_layout.setSpacing(8)
        
        gdt_label = QtWidgets.QLabel("Select GDT Symbol")
        gdt_layout.addWidget(gdt_label)
        
        # Create grid layout for GDT symbols
        gdt_grid = QtWidgets.QGridLayout()
        gdt_grid.setSpacing(4)
        self.gdt_button_group = QtWidgets.QButtonGroup()
        self.gdt_button_group.setExclusive(True)
        
        row = 0
        col = 0
        for symbol, name in self.gdt_symbols.items():
            button = GDTSymbolButton(symbol, name)
            button.setProperty("isGDTButton", True)
            self.gdt_button_group.addButton(button)
            gdt_grid.addWidget(button, row, col)
            col += 1
            if col > 3:  # 4 columns
                col = 0
                row += 1
        
        gdt_layout.addLayout(gdt_grid)
        main_layout.addWidget(self.gdt_symbol_frame)
        
        # Connect GDT button group
        self.gdt_button_group.buttonClicked.connect(self.on_gdt_symbol_selected)
        
        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(12)
        
        ok_button = QtWidgets.QPushButton("Save")
        ok_button.setObjectName("okButton")
        cancel_button = QtWidgets.QPushButton("Cancel")
        cancel_button.setObjectName("cancelButton")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        main_layout.addLayout(button_layout)
        
        # Set initial size
        self.setMinimumWidth(400)  # Reduced minimum width
        self.adjustSize()

        # Connect dimension type change event
        self.dim_type_combo.currentTextChanged.connect(self.on_dim_type_changed)

    def on_dim_type_changed(self, text):
        """Handle dimension type change"""
        if (text == "GDT"):
            self.gdt_symbol_frame.setVisible(True)
            # Delay the resize slightly to ensure proper layout
            QtCore.QTimer.singleShot(10, self.adjustSize)
        else:
            self.gdt_symbol_frame.setVisible(False)
            self.selected_gdt_symbol = None
            for button in self.gdt_button_group.buttons():
                button.setChecked(False)
            # Delay the resize slightly to ensure proper layout
            QtCore.QTimer.singleShot(10, self.adjustSize)

    def on_gdt_symbol_selected(self, button):
        """Handle GDT symbol selection"""
        # Find the symbol and name from the button's labels
        symbol_label = button.findChild(QtWidgets.QLabel)
        if symbol_label:
            symbol = symbol_label.text()
            self.selected_gdt_symbol = symbol

    def getDimensionData(self):
        """Return the entered dimension data"""
        data = {
            'nominal': self.nominal_edit.text(),
            'upper_tol': self.upper_tol_edit.text(),
            'lower_tol': self.lower_tol_edit.text(),
            'dim_type': self.dim_type_combo.currentText()
        }
        
        if self.dim_type_combo.currentText() == "GDT" and self.selected_gdt_symbol:
            data['gdt_symbol'] = f"{self.selected_gdt_symbol} - {self.gdt_symbols[self.selected_gdt_symbol]}"
            
        return data

class PDFPreviewDialog(QtWidgets.QDialog):
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.current_page = 0
        self.rotation = 0
        self.pdf_doc = fitz.open(pdf_path)
        
        self.setup_ui()
        self.load_current_page()

    def setup_ui(self):
        self.setWindowTitle("PDF Preview")
        self.setMinimumSize(800, 600)
        
        # Apply modern styling
        self.setStyleSheet("""
            QDialog {
                background-color: #fafafa;
            }
            QLabel {
                color: #555555;
                font-size: 11px;
            }
            QSpinBox {
                padding: 4px;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
                color: #333333;
                font-size: 11px;
                min-width: 60px;
            }
            QSpinBox:focus {
                border: 1px solid #bdbdbd;
                background-color: #fafafa;
            }
            QPushButton {
                padding: 6px 14px;
                border-radius: 3px;
                border: 1px solid #e0e0e0;
                background-color: #f5f5f5;
                color: #424242;
                font-size: 11px;
                min-width: 90px;
            }
            QPushButton:hover {
                background-color: #eeeeee;
                border: 1px solid #bdbdbd;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton[text="OK"] {
                background-color: #f5f5f5;
                border: 1px solid #2196f3;
                color: #2196f3;
            }
            QPushButton[text="OK"]:hover {
                background-color: #e3f2fd;
            }
            QPushButton[text="OK"]:pressed {
                background-color: #bbdefb;
            }
            QGraphicsView {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                background-color: white;
            }
        """)

        # Main layout with margins
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Preview area with shadow effect
        preview_frame = QtWidgets.QFrame()
        preview_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        preview_layout = QtWidgets.QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scene = QtWidgets.QGraphicsScene()
        self.view = QtWidgets.QGraphicsView(self.scene)
        
        # Add shadow effect to preview
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setColor(QtGui.QColor(0, 0, 0, 25))
        shadow.setOffset(0, 2)
        self.view.setGraphicsEffect(shadow)
        
        preview_layout.addWidget(self.view)
        layout.addWidget(preview_frame)

        # Controls layout
        controls_frame = QtWidgets.QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
            }
        """)
        
        controls_layout = QtWidgets.QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(15, 10, 15, 10)

        # Page navigation with modern icons
        nav_layout = QtWidgets.QHBoxLayout()
        nav_layout.setSpacing(8)
        
        self.page_label = QtWidgets.QLabel("Page:")
        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(len(self.pdf_doc))
        self.page_spin.setValue(1)
        self.page_spin.valueChanged.connect(self.page_changed)

        self.total_pages_label = QtWidgets.QLabel(f"of {len(self.pdf_doc)}")

        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.page_spin)
        nav_layout.addWidget(self.total_pages_label)

        # Rotation controls with icons
        rotation_layout = QtWidgets.QHBoxLayout()
        rotation_layout.setSpacing(12)
        
        # Create tool buttons for rotation
        self.rotate_left_btn = QtWidgets.QToolButton()
        self.rotate_right_btn = QtWidgets.QToolButton()
        
        # Set icons (replace with your icon paths)
        self.rotate_left_btn.setIcon(QIcon(r"D:\siri\calipers\prometrix\prometrix\Smart_Metrology_19082024\icons8-rotate-left-24.png"))
        self.rotate_right_btn.setIcon(QIcon(r"D:\siri\calipers\prometrix\prometrix\Smart_Metrology_19082024\icons8-rotate-right-24.png"))
        
        # Set icon size
        icon_size = QtCore.QSize(20, 20)
        self.rotate_left_btn.setIconSize(icon_size)
        self.rotate_right_btn.setIconSize(icon_size)
        
        # Style the tool buttons
        tool_button_style = """
            QToolButton {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                padding: 4px;
                background-color: #f5f5f5;
            }
            QToolButton:hover {
                background-color: #eeeeee;
                border: 1px solid #bdbdbd;
            }
            QToolButton:pressed {
                background-color: #e0e0e0;
            }
        """
        self.rotate_left_btn.setStyleSheet(tool_button_style)
        self.rotate_right_btn.setStyleSheet(tool_button_style)
        
        # Set tooltips
        self.rotate_left_btn.setToolTip("Rotate Left")
        self.rotate_right_btn.setToolTip("Rotate Right")
        
        # Connect signals
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_page(-90))
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_page(90))
        
        rotation_layout.addWidget(self.rotate_left_btn)
        rotation_layout.addWidget(self.rotate_right_btn)

        # Add layouts to controls
        controls_layout.addLayout(nav_layout)
        controls_layout.addStretch()
        controls_layout.addLayout(rotation_layout)

        layout.addWidget(controls_frame)

        # Button layout
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        
        ok_button = QtWidgets.QPushButton("OK")
        cancel_button = QtWidgets.QPushButton("Cancel")
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)

    def load_current_page(self):
        page = self.pdf_doc[self.current_page]
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72).prerotate(self.rotation))
        
        # Convert to QImage
        img = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride, QtGui.QImage.Format_RGB888)
        
        # Create pixmap and add to scene
        self.scene.clear()
        pixmap = QtGui.QPixmap.fromImage(img)
        self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        
        # Fit view to page
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def page_changed(self, value):
        self.current_page = value - 1
        self.load_current_page()

    def rotate_page(self, angle):
        self.rotation = (self.rotation + angle) % 360
        self.load_current_page()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene.items():
            self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def get_selected_page(self):
        return self.current_page

    def get_rotation(self):
        return self.rotation 
    
# Add this new class for background loading
class DataLoaderThread(QThread):
    data_loaded = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    
    def run(self):
        try:
            data = api.get_all_orders()
            if data is not None:
                self.data_loaded.emit(data)
            else:
                self.error_occurred.emit("Failed to fetch data from API")
        except Exception as e:
            self.error_occurred.emit(f"Error loading data: {str(e)}")

class PartNumberDialog(QDialog):
    def __init__(self, parent=None):
        """Initialize dialog and load data from API"""
        super(PartNumberDialog, self).__init__(parent)
        self.setWindowTitle("Select Part Number")
        self.setFixedSize(400, 480)  # Reduced size
        
        # Main layout with smaller margins
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)  # Reduced margins
        layout.setSpacing(6)  # Reduced spacing
        
        # Header section - more compact
        title_label = QLabel("Select a Part")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title_label)
        
        # Search box with icon - more compact
        search_container = QWidget()
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)  # Reduced spacing
        
        search_icon = QLabel()
        search_icon.setPixmap(self.style().standardPixmap(QStyle.SP_FileDialogContentsView).scaled(14, 14))
        search_layout.addWidget(search_icon)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search part numbers...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: #f8f9fa;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
                background-color: white;
            }
        """)
        self.search_box.textChanged.connect(self.filter_items)
        search_layout.addWidget(self.search_box)
        layout.addWidget(search_container)
        
        # List widget with improved styling
        self.list_widget = QListWidget(self)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 2px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                border-bottom: 1px solid #bbdefb;
            }
            QListWidget::item:hover:!selected {
                background-color: #f5f9ff;
            }
        """)
        
        # Loading indicator with improved styling
        self.loading_label = QLabel("Loading data...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 13px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.loading_label)
        
        self.list_widget.setVisible(False)
        layout.addWidget(self.list_widget)
        
        # Status bar with improved styling
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 11px;
                padding: 2px;
            }
        """)
        layout.addWidget(self.status_label)
        
        # Button container with improved styling
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        
        self.cancel_button = QPushButton("Cancel", self)
        self.ok_button = QPushButton("Select", self)
        
        button_style = """
            QPushButton {
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 80px;
            }
        """
        
        self.cancel_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #f8f9fa;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
        """)
        
        self.ok_button.setStyleSheet(button_style + """
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.handle_item_activation)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addWidget(button_container)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence("Return"), self, self.handle_return_key)
        QShortcut(QKeySequence("Escape"), self, self.reject)
        
        # Connect double-click signal
        self.list_widget.itemDoubleClicked.connect(self.handle_item_activation)
        
        # Initialize attributes for PDF handling
        self.downloaded_file = None
        self.selected_page = 0
        self.selected_rotation = 0
        self.selected_production_order = None  # Add this line
        
        # Start loading data
        self.load_data()

    def load_data(self):
        """Start loading data from API in background"""
        self.loader_thread = DataLoaderThread()
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.start()
        
    def on_data_loaded(self, data):
        """Handle the loaded data"""
        self.loading_label.hide()
        self.list_widget.setVisible(True)
        
        for order in data:
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(8, 4, 8, 4)
            item_layout.setSpacing(12)
            
            # Part number container
            part_container = QWidget()
            part_layout = QVBoxLayout(part_container)
            part_layout.setContentsMargins(0, 0, 0, 0)
            part_layout.setSpacing(0)
            
            part_label = QLabel("Part Number")
            part_label.setStyleSheet("color: #666; font-size: 10px;")
            part_number_value = QLabel(order.get('part_number', ''))
            part_number_value.setStyleSheet("font-size: 13px; font-weight: bold; color: #2c3e50;")
            
            part_layout.addWidget(part_label)
            part_layout.addWidget(part_number_value)
            item_layout.addWidget(part_container)
            
            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            separator.setStyleSheet("color: #e0e0e0;")
            item_layout.addWidget(separator)
            
            # Production order container
            order_container = QWidget()
            order_layout = QVBoxLayout(order_container)
            order_layout.setContentsMargins(0, 0, 0, 0)
            order_layout.setSpacing(0)
            
            order_label = QLabel("Production Order")
            order_label.setStyleSheet("color: #666; font-size: 10px;")
            order_value = QLabel(order.get('production_order', ''))
            order_value.setStyleSheet("font-size: 13px; color: #2c3e50;")
            
            order_layout.addWidget(order_label)
            order_layout.addWidget(order_value)
            item_layout.addWidget(order_container)
            
            # Add to list widget
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, (order.get('part_number', ''), order.get('production_order', '')))
            
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, item_widget)
        
        self.update_status()
        
    def on_loading_error(self, error_message):
        """Handle loading errors"""
        self.loading_label.setText(f"Error: {error_message}\nPlease try again later.")
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #dc3545;
                font-size: 14px;
                padding: 20px;
            }
        """)

    def filter_items(self):
        """Filter items based on search text"""
        search_text = self.search_box.text().lower()
        visible_count = 0
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            part_number, production_order = item.data(Qt.UserRole)
            matches = (search_text in part_number.lower() or 
                      search_text in production_order.lower())
                
            item.setHidden(not matches)
            if matches:
                visible_count += 1
        
        if search_text:
            self.status_label.setText(f"Found {visible_count} matching items")
        else:
            self.update_status()
    
    def update_status(self):
        """Update status label"""
        total_items = self.list_widget.count()
        visible_items = sum(1 for i in range(total_items) if not self.list_widget.item(i).isHidden())
        self.status_label.setText(f"Showing {visible_items} of {total_items} items")
    
    def handle_item_activation(self, item=None):
        """Handle item selection via double-click or select button"""
        if not item:
            item = self.list_widget.currentItem()
        if not item:
            return
            
        selected_data = item.data(Qt.UserRole)
        if not selected_data:
            return
            
        self.selected_part_number = selected_data[0]  # Get part number
        self.selected_production_order = selected_data[1]  # Get production order
        self.accept()

    def handle_return_key(self):
        """Handle Return/Enter key press"""
        if self.list_widget.currentItem():
            self.handle_item_activation()

    def get_selected_part_number(self):
        """Get the selected part number"""
        return self.selected_part_number

    def get_selected_production_order(self):
        """Get the selected production order"""
        return self.selected_production_order

    def keyPressEvent(self, event):
        """Handle keyboard navigation"""
        if event.key() == Qt.Key_Up and self.list_widget.currentRow() == 0:
            self.search_box.setFocus()
        elif event.key() == Qt.Key_Down and self.search_box.hasFocus():
            self.list_widget.setFocus()
            self.list_widget.setCurrentRow(0)
        else:
            super().keyPressEvent(event)

    def get_downloaded_file(self):
        return self.downloaded_file

    def get_selected_page(self):
        return self.selected_page

    def get_selected_rotation(self):
        return self.selected_rotation

class DocumentVersionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Document Version")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title label
        title_label = QLabel("Select Document Version")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                padding-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search versions...")
        self.search_box.textChanged.connect(self.filter_versions)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196f3;
                background-color: #fff;
            }
        """)
        layout.addWidget(self.search_box)
        
        # Version list
        self.version_list = QListWidget()
        self.version_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
                border: none;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.version_list)
        
        # Selection info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("Select")
        
        for button in [cancel_button, ok_button]:
            button.setMinimumWidth(100)
            button.setMinimumHeight(36)
        
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
            QPushButton:pressed {
                background-color: #1976d2;
            }
        """)
        
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)

    def filter_versions(self, text):
        """Filter versions based on search text"""
        for i in range(self.version_list.count()):
            item = self.version_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def load_versions(self, production_order: str):
        """Load document versions for the production order"""
        try:
            versions = api.get_document_versions(production_order)
            self.loading_label.hide()
            
            if versions:
                for version in versions:
                    item = QListWidgetItem()
                    
                    # Extract version information
                    version_num = version.get('version_number', 'N/A')
                    created_at = version.get('created_at', '').split('T')[0]
                    status = version.get('status', '').title()
                    doc_id = version.get('document_id')
                    version_id = version.get('id')
                    
                    # Debug print
                    print(f"Version data: doc_id={doc_id}, version_id={version_id}")
                    
                    # Build version text
                    version_text = f"Version {version_num}"
                    if created_at:
                        version_text += f" - {created_at}"
                    if status:
                        version_text += f" ({status})"
                    
                    item.setText(version_text)
                    # Store full version data including IDs
                    item.setData(Qt.UserRole, version)
                    self.version_list.addItem(item)
                
                # Sort versions by version number (newest first)
                self.version_list.sortItems(Qt.DescendingOrder)
                
                # Select the latest version by default
                self.version_list.setCurrentRow(0)
                
                # Enable buttons
                self.ok_button.setEnabled(True)
            else:
                self.loading_label.setText("No versions found")
                self.loading_label.show()
                self.ok_button.setEnabled(False)
                
        except Exception as e:
            print(f"Error loading versions: {str(e)}")
            self.loading_label.setText(f"Error loading versions: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
    
    def select_latest_version(self):
        """Download and open the latest version"""
        try:
            # Create temporary directory if it doesn't exist
            temp_dir = os.path.join(os.path.expanduser("~"), ".smartmetrology", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate temp file path
            temp_file = os.path.join(temp_dir, f"drawing_{self.production_order}.pdf")
            
            # Show download progress
            self.loading_label.setText("Downloading latest version...")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
            QtWidgets.QApplication.processEvents()
            
            # Download the file
            if api.download_latest_document(self.production_order, temp_file):
                self.loading_label.hide()
                self.ok_button.setEnabled(True)
                
                # Store the file path
                self.downloaded_file = temp_file
                self.accept()
            else:
                self.loading_label.setText("Failed to download document")
                self.loading_label.show()
                
        except Exception as e:
            print(f"Error downloading latest version: {str(e)}")
            self.loading_label.setText(f"Error: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(True)

    def accept(self):
        """Handle the OK button click - download selected version"""
        selected_version = self.get_selected_version()
        if not selected_version:
            return
            
        try:
            # Create temporary directory if it doesn't exist
            temp_dir = os.path.join(os.path.expanduser("~"), ".smartmetrology", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Generate temp file path
            temp_file = os.path.join(temp_dir, f"drawing_{self.production_order}.pdf")
            
            # Show download progress
            self.loading_label.setText("Downloading selected version...")
            self.loading_label.show()
            self.ok_button.setEnabled(False)
            QtWidgets.QApplication.processEvents()
            
            # Get document and version IDs
            doc_id = selected_version.get('document_id')
            version_id = selected_version.get('id')
            
            if not doc_id or not version_id:
                raise ValueError("Missing document or version ID")
            
            # Download the specific version
            if api.download_specific_version(doc_id, version_id, temp_file):
                self.loading_label.hide()
                
                # Show PDF Preview Dialog
                preview_dialog = PDFPreviewDialog(temp_file, self)
                if preview_dialog.exec_() == QtWidgets.QDialog.Accepted:
                    # Store the file path and preview dialog results
                    self.downloaded_file = temp_file
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()
                    super().accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file)
                    except:
                        pass
                    self.reject()
            else:
                self.loading_label.setText("Failed to download document")
                self.loading_label.show()
                self.ok_button.setEnabled(True)
                
        except Exception as e:
            print(f"Error downloading version: {str(e)}")
            self.loading_label.setText(f"Error: {str(e)}")
            self.loading_label.show()
            self.ok_button.setEnabled(True)

    def get_selected_version(self) -> Optional[Dict]:
        """Get the selected version data"""
        current_item = self.version_list.currentItem()
        if current_item:
            return current_item.data(Qt.UserRole)
        return None

    def get_downloaded_file(self) -> Optional[str]:
        """Get the path to the downloaded file"""
        return getattr(self, 'downloaded_file', None)

    def get_selected_page(self) -> int:
        """Get the selected page number"""
        return getattr(self, 'selected_page', 0)

    def get_selected_rotation(self) -> int:
        """Get the selected rotation"""
        return getattr(self, 'selected_rotation', 0)

    def download_latest_version(self):
        """Download the latest version of the document"""
        try:
            # Create temporary file
            temp_file_path = os.path.join(tempfile.gettempdir(), f"drawing_{uuid.uuid4()}.pdf")
            
            if api.download_latest_document(self.production_order, temp_file_path):
                self.downloaded_file = temp_file_path
                self.accept()  # Just accept directly, preview will be shown by parent dialog
            else:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Download Error",
                    "Failed to download the document."
                )
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to download document: {str(e)}"
            )

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        self.setFixedSize(300, 200)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Login")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        layout.addWidget(title_label)
        
        # Username
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Username")
        self.username_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        layout.addWidget(self.username_edit)
        
        # Password
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setStyleSheet(self.username_edit.styleSheet())
        layout.addWidget(self.password_edit)
        
        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-size: 12px;
            }
        """)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        # Login button
        self.login_button = QPushButton("Login")
        self.login_button.setStyleSheet("""
            QPushButton {
                padding: 8px;
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.login_button.clicked.connect(self.try_login)
        layout.addWidget(self.login_button)
        
        # Enter key triggers login
        QShortcut(QKeySequence("Return"), self, self.try_login)
        
    def try_login(self):
        """Attempt to login with provided credentials"""
        username = self.username_edit.text()
        password = self.password_edit.text()
        
        if not username or not password:
            self.error_label.setText("Please enter both username and password")
            self.error_label.show()
            return
            
        self.login_button.setEnabled(False)
        self.login_button.setText("Logging in...")
        
        if api.login(username, password):
            # Get the role from the API handler
            role = getattr(api, 'user_role', None)
            if role:
                # Pass both username and role to parent
                self.parent().handle_login_success(username, role)
            self.accept()
        else:
            self.error_label.setText("Invalid username or password")
            self.error_label.show()
            self.login_button.setEnabled(True)
            self.login_button.setText("Login")

    def handle_login_response(self, response):
        if response.status_code == 200:
            # Get user role
            username = self.username_edit.text()
            role_response = requests.get(
                f"{api.base_url}/auth/users/{username}/role",
                headers={"Authorization": f"Bearer {api.token}"}
            )
            
            if role_response.status_code == 200:
                role = role_response.json().get('role', '')
                self.parent().handle_login_success(username, role)
                self.accept()
            else:
                print(f"Error getting user role: {role_response.text}")
                self.show_error("Failed to get user role")
        else:
            self.show_error("Invalid credentials")

class OperationsDialog(QDialog):
    def __init__(self, part_number, production_order, parent=None):
        super().__init__(parent)
        self.part_number = part_number
        self.production_order = production_order
        self.downloaded_file = None
        self.selected_page = None
        self.selected_rotation = 0
        self.selected_operation = None
        
        # Setup UI
        self.setup_ui()
        
        # Load operations
        self.load_operations()
        
    def setup_ui(self):
        self.setWindowTitle("Select Operation")
        self.setMinimumSize(800, 600)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title section
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("Operations List")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        """)
        
        part_number_label = QLabel(f"Part Number: {self.part_number}")
        part_number_label.setStyleSheet("""
            color: #0066cc;
            font-size: 14px;
        """)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(part_number_label)
        layout.addWidget(title_widget)
        
        # Operations list
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            QListWidget::item {
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Add Final Inspection Drawing button
        self.final_inspection_button = QPushButton("Final Inspection Drawing")
        self.final_inspection_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #27ae60;  /* Green color */
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #a5d6a7;
            }
        """)
        self.final_inspection_button.clicked.connect(self.open_final_inspection)
        button_layout.addWidget(self.final_inspection_button)
        
        self.view_drawing_button = QPushButton("View Drawing")
        self.view_drawing_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
            QPushButton:disabled {
                background-color: #90caf9;
            }
        """)
        self.view_drawing_button.clicked.connect(self.view_drawing)
        self.view_drawing_button.setEnabled(False)  # Initially disabled
        
        button_layout.addWidget(self.view_drawing_button)
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                padding: 10px 20px;
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connect selection changed signal
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        
        self.selected_operation = None
        self.downloaded_file = None
        
        # Load operations data
        self.load_operations()

    def load_operations(self):
        try:
            operations = api.get_operations(self.part_number)
            
            for operation in operations:
                item = QListWidgetItem()
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.setContentsMargins(15, 15, 15, 15)
                layout.setSpacing(10)
                
                # Operation header
                header_widget = QWidget()
                header_layout = QHBoxLayout(header_widget)
                header_layout.setContentsMargins(0, 0, 0, 0)
                header_layout.setSpacing(10)
                
                op_number = QLabel(f"Operation {operation['operation_number']}")
                op_number.setStyleSheet("""
                    QLabel {
                        font-weight: bold;
                        color: #2c3e50;
                        font-size: 14px;
                        padding: 2px 0;
                        min-height: 20px;
                    }
                """)
                
                work_center = QLabel(f"Work Center: {operation['work_center']}")
                work_center.setStyleSheet("""
                    QLabel {
                        color: #666;
                        font-size: 13px;
                        padding: 2px 0;
                        min-height: 20px;
                    }
                """)
                
                header_layout.addWidget(op_number)
                header_layout.addStretch()
                header_layout.addWidget(work_center)
                
                desc = QLabel(operation['operation_description'])
                desc.setStyleSheet("""
                    QLabel {
                        color: #333;
                        font-size: 13px;
                        padding: 5px 0;
                        min-height: 20px;
                        background: transparent;
                    }
                """)
                desc.setWordWrap(True)
                
                layout.addWidget(header_widget)
                layout.addWidget(desc)
                
                widget.setMinimumHeight(80)
                
                item.setSizeHint(widget.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, widget)
                
                # Store operation data
                item.setData(Qt.UserRole, operation)
                
        except Exception as e:
            print(f"Error loading operations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load operations: {str(e)}")

    def on_selection_changed(self):
        self.view_drawing_button.setEnabled(self.list_widget.currentItem() is not None)

    def view_drawing(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            return
            
        operation_data = current_item.data(Qt.UserRole)
        operation_number = operation_data['operation_number']
        
        # Add detailed debug prints
        print(f"\nView Drawing Details:")
        print(f"Part Number: {self.part_number}")
        print(f"Production Order: {self.production_order}")
        print(f"Operation Number: {operation_number}")
        print(f"Operation Data: {operation_data}")
        
        # Store the operation number
        self.op_no = operation_number
        
        try:
            print(f"\nMaking API request:")
            print(f"URL will be: {api.base_url}/document-management/documents/download-latest_new/{self.production_order}/ENGINEERING_DRAWING")
            
            pdf_content = api.get_ipid_drawing(
                self.production_order,
                operation_number
            )
            
            if pdf_content:
                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(pdf_content)
                temp_file.close()
                
                # Show PDF Preview Dialog
                preview_dialog = PDFPreviewDialog(temp_file.name, self)
                if preview_dialog.exec_() == QDialog.Accepted:
                    self.downloaded_file = temp_file.name
                    self.selected_operation = operation_data
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()
                    # Generate IPID string using part number for the identifier
                    self.ipid = f"IPID-{self.part_number}-{operation_number}"
                    self.accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file.name)
                    except:
                        pass
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    f"Failed to download drawing for Operation {operation_number}"
                )
                
        except Exception as e:
            print(f"Error downloading drawing: {e}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to download drawing for Operation {operation_number}: {str(e)}"
            )

    def open_final_inspection(self):
        """Open final inspection drawing"""
        try:
            # Set operation number for final inspection
            self.op_no = "999"
            
            # Use the new endpoint format with part number
            endpoint = f"/document-management/documents/download-latest_new/{self.part_number}/ENGINEERING_DRAWING"
            print(f"Downloading final inspection drawing from: {endpoint}")
            
            # Make the request with stream=True
            pdf_content = api._make_request(endpoint, stream=True)
            
            if pdf_content:
                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(pdf_content)
                temp_file.close()
                
                # Show PDF Preview Dialog
                preview_dialog = PDFPreviewDialog(temp_file.name, self)
                if preview_dialog.exec_() == QDialog.Accepted:
                    self.downloaded_file = temp_file.name
                    self.selected_page = preview_dialog.get_selected_page()
                    self.selected_rotation = preview_dialog.get_rotation()  # Fixed method name
                    
                    # Create a dummy operation for final inspection
                    self.selected_operation = {
                        "operation_number": "999",
                        "operation_description": "Final Inspection",
                        "work_center": "QC"
                    }
                    
                    self.accept()
                else:
                    # Clean up temp file if preview was cancelled
                    try:
                        os.remove(temp_file.name)
                    except:
                        pass
            else:
                QMessageBox.warning(
                    self, 
                    "Error", 
                    "Failed to download final inspection drawing"
                )
                
        except Exception as e:
            print(f"Error opening final inspection: {e}")
            QMessageBox.critical(
                self, 
                "Error", 
                f"Failed to open final inspection drawing: {str(e)}"
            )

    def handle_item_activation(self, item=None):
        """Handle double-click or Enter key on list item"""
        if not item:
            item = self.list_widget.currentItem()
        if not item:
            return
            
        selected_data = item.data(Qt.UserRole)
        if not selected_data:
            return
            
        self.selected_part_number = selected_data[0]  # Get part number
        self.selected_production_order = selected_data[1]  # Get production order
        self.accept()

    def get_operation_number(self):
        return self.op_no

    def get_measurement_instrument(self):
        """Get the measurement instrument"""
        return ["Not Specified"]  # Always return default value

    def get_selected_operation(self):
        """Get the selected operation data"""
        return self.selected_operation

    def get_downloaded_file(self):
        """Get the path to the downloaded file"""
        return self.downloaded_file

    def get_selected_page(self):
        """Get the selected page number"""
        return getattr(self, 'selected_page', 0)

    def get_selected_rotation(self):
        """Get the selected rotation"""
        return getattr(self, 'selected_rotation', 0)

    def get_order_id(self):
        """Get the order ID from the operation data"""
        try:
            if self.selected_operation:
                return self.selected_operation.get('order_id') or self.production_order
            return self.production_order
        except Exception as e:
            print(f"Error getting order ID: {e}")
            return self.production_order

    def get_document_id(self):
        """Get document ID - using production order as fallback"""
        try:
            if self.selected_operation:
                return self.selected_operation.get('document_id') or self.production_order
            return self.production_order
        except Exception as e:
            print(f"Error getting document ID: {e}")
            return self.production_order

    def download_drawing(self):
        """Download the engineering drawing"""
        try:
            # Use the new endpoint format with part number
            endpoint = f"/document-management/documents/download-latest_new/{self.part_number}/ENGINEERING_DRAWING"
            print(f"Downloading drawing from: {endpoint}")
            
            # Make the request
            response = api._make_request(endpoint, stream=True)
            
            if response:
                # Create temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_file.write(response)
                temp_file.close()
                
                self.downloaded_file = temp_file.name
                print(f"Drawing downloaded to: {self.downloaded_file}")
                
                # Load PDF preview
                self.load_pdf_preview()
            else:
                raise Exception("Failed to download drawing")
                
        except Exception as e:
            print(f"Error downloading drawing: {e}")
            QMessageBox.critical(self, "Error", f"Failed to download drawing: {str(e)}")

class MeasurementInstrumentDialog(QDialog):
    def __init__(self, parent=None, allow_multiple=False, is_admin=False):
        super().__init__(parent)
        self.allow_multiple = allow_multiple
        self.is_admin = is_admin
        self.setup_ui()
        self.load_instruments()

    def setup_ui(self):
        """Setup the UI elements"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header layout for title and count
        header_layout = QHBoxLayout()
        
        # Title label
        title_label = QLabel("Select Measurement Instrument")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        header_layout.addWidget(title_label)
        
        # Count label
        self.count_label = QLabel()
        self.count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                padding: 2px 8px;
                background-color: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
        """)
        header_layout.addWidget(self.count_label, alignment=Qt.AlignRight)
        
        layout.addLayout(header_layout)
        
        # Filter section
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        # Subcategory dropdown
        subcategory_label = QLabel("Category:")
        subcategory_label.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 13px;
                font-weight: bold;
                min-width: 70px;
            }
        """)
        filter_layout.addWidget(subcategory_label)
        
        self.subcategory_combo = QComboBox()
        self.subcategory_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #2196f3;
            }
            QComboBox:focus {
                border-color: #2196f3;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        self.subcategory_combo.addItem("All Categories")
        self.subcategory_combo.currentIndexChanged.connect(self.filter_by_subcategory)
        filter_layout.addWidget(self.subcategory_combo)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search instruments...")
        self.search_box.textChanged.connect(self.filter_instruments)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196f3;
                background-color: #fff;
            }
        """)
        
        # Add search box with stretch
        filter_layout.addWidget(self.search_box)
        filter_layout.setStretchFactor(self.search_box, 1)
        
        layout.addLayout(filter_layout)
        
        # Loading indicator
        self.loading_label = QLabel("Loading instruments...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 13px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.loading_label)
        
        # Instruments list
        self.instrument_list = QListWidget()
        self.instrument_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 2px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        layout.addWidget(self.instrument_list)
        self.instrument_list.setVisible(False)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("Select")
        
        for button in [cancel_button, ok_button]:
            button.setMinimumWidth(100)
            button.setMinimumHeight(36)
        
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e88e5;
            }
            QPushButton:pressed {
                background-color: #1976d2;
            }
        """)
        
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # Load instruments
        self.load_instruments()

    def showEvent(self, event):
        """Override showEvent to load data when dialog is shown"""
        super().showEvent(event)
        self.refresh_data()
        
    def refresh_data(self):
        """Refresh the instruments data"""
        self.search_box.clear()  # Clear search box
        self.load_instruments()  # Reload instruments

    def filter_by_subcategory(self, index):
        """Filter instruments by selected subcategory"""
        if not hasattr(self, 'instrument_list'):
            return
            
        selected_text = self.subcategory_combo.currentText().strip()
        search_text = self.search_box.text().strip().lower()
        
        for i in range(self.instrument_list.count()):
            item = self.instrument_list.item(i)
            widget = self.instrument_list.itemWidget(item)
            if widget:
                # Get instrument data
                instrument_data = widget.property("instrument_data")
                if instrument_data:
                    # For admin, match by category name
                    if self.is_admin:
                        category_name = instrument_data['name']
                        category_match = (selected_text == "All Categories" or 
                                       selected_text.lower() in category_name.lower())
                        search_match = not search_text or search_text in category_name.lower()
                    else:
                        # For operator, match by full name and code
                        name = instrument_data['name']
                        code = instrument_data['instrument_code']
                        category_match = (selected_text == "All Categories" or 
                                       selected_text.lower() in name.split(" - ")[0].lower())
                        search_match = (not search_text or 
                                      search_text in name.lower() or 
                                      search_text in code.lower())
                    
                    # Show/hide based on both conditions
                    item.setHidden(not (category_match and search_match))
        
        # Update count label
        visible_count = sum(1 for i in range(self.instrument_list.count()) 
                          if not self.instrument_list.item(i).isHidden())
        total_count = self.instrument_list.count()
        
        if selected_text == "All Categories":
            if search_text:
                self.count_label.setText(f"Showing {visible_count} of {total_count}")
            else:
                self.count_label.setText(f"Total: {total_count}")
        else:
            self.count_label.setText(f"Showing {visible_count} of {total_count} ({selected_text})")

    def filter_instruments(self, text):
        """Filter instruments based on search text"""
        self.filter_by_subcategory(self.subcategory_combo.currentIndex())

    def create_instrument_widget(self, instrument_data):
        """Create a custom widget for instrument list item"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 8, 10, 8)  # Increased padding
        
        # Instrument info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        if self.is_admin:
            # For admin, show only the category name in a clean format
            name_label = QLabel(instrument_data['name'])
            name_label.setStyleSheet("""
                QLabel {
                    font-size: 13px;
                    color: #2c3e50;
                    font-weight: bold;
                    padding: 4px 0;
                }
            """)
            info_layout.addWidget(name_label)
        else:
            # For operator, show full instrument details
            name_label = QLabel(instrument_data['name'])
            name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
            code_label = QLabel(f"Code: {instrument_data['instrument_code']}")
            code_label.setStyleSheet("color: #666; font-size: 12px;")

            info_layout.addWidget(name_label)
            info_layout.addWidget(code_label)

            # Add calibration info if available
            calibration = instrument_data.get('calibration')
            if calibration:
                cal_layout = QVBoxLayout()
                cal_layout.setSpacing(2)

                last_cal_date = calibration.get('last_calibration', '').split('T')[0] if calibration.get('last_calibration') else 'Unknown'
                last_cal_label = QLabel(f"Last Cal: {last_cal_date}")
                last_cal_label.setStyleSheet("color: #555; font-size: 11px;")

                next_cal_date = calibration.get('next_calibration', '').split('T')[0] if calibration.get('next_calibration') else 'Unknown'
                next_cal_label = QLabel(f"Next Cal: {next_cal_date}")
                next_cal_label.setStyleSheet("color: #555; font-size: 11px;")

                status = calibration.get('status', 'unknown')
                status_text = status.upper() if status else 'UNKNOWN'
                status_label = QLabel(f"Status: {status_text}")

                if status == 'overdue':
                    status_label.setStyleSheet("color: #d32f2f; font-weight: bold; font-size: 11px;")
                elif status == 'due':
                    status_label.setStyleSheet("color: #e65100; font-weight: bold; font-size: 11px;")
                else:
                    status_label.setStyleSheet("color: #2e7d32; font-size: 11px;")

                cal_layout.addWidget(last_cal_label)
                cal_layout.addWidget(next_cal_label)
                cal_layout.addWidget(status_label)

                layout.addLayout(info_layout)
                layout.addStretch()
                layout.addLayout(cal_layout)
            else:
                layout.addLayout(info_layout)
                layout.addStretch()

        # For admin view, just add the info layout and stretch
        if self.is_admin:
            layout.addLayout(info_layout)
            layout.addStretch()

        # Add hover effect to the widget
        widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 4px;
            }
            QWidget:hover {
                background-color: #f0f7ff;
            }
        """)

        # Store the data in the widget for retrieval
        widget.setProperty("instrument_data", instrument_data)

        return widget

    def load_instruments(self):
        """Load instruments from the API"""
        try:
            # Show loading indicator
            self.loading_label.setText("Loading instruments...")
            self.loading_label.show()
            self.instrument_list.setVisible(False)

            # Use fixed category ID 5 for Instruments
            instruments_category_id = 5

            # Get subcategories for Instruments category
            subcategories = api.get_inventory_subcategories(instruments_category_id)
            if not subcategories:
                raise Exception("Failed to fetch subcategories")

            # Store subcategories for filtering
            self.subcategories = subcategories

            # Clear and repopulate subcategory combo
            self.subcategory_combo.clear()
            self.subcategory_combo.addItem("All Categories")
            for subcategory in subcategories:
                if subcategory.get('category_id') == instruments_category_id:
                    self.subcategory_combo.addItem(subcategory['name'], subcategory['id'])

            # For admin users, only show categories
            if self.is_admin:
                # Clear and populate list with unique categories
                self.instrument_list.clear()
                added_categories = set()
                
                for subcategory in subcategories:
                    if subcategory.get('category_id') == instruments_category_id:
                        category_name = subcategory['name']
                        if category_name not in added_categories:
                            added_categories.add(category_name)
                            
                            item = QListWidgetItem()
                            widget = self.create_instrument_widget({
                                'name': category_name,
                                'id': subcategory['id'],
                                'subcategory_id': subcategory['id'],
                                'instrument_code': category_name,
                                'item_code': None,
                                'dynamic_data': {},
                                'calibration': None
                            })
                            item.setSizeHint(widget.sizeHint())
                            self.instrument_list.addItem(item)
                            self.instrument_list.setItemWidget(item, widget)

                # Show list and hide loading
                self.loading_label.hide()
                self.instrument_list.setVisible(True)

                # Update count label
                total_categories = len(added_categories)
                self.count_label.setText(f"Total Categories: {total_categories}")
                return

            # For operators, show full instrument details
            # Get all calibration data
            calibrations = api.get_calibrations()
            if not calibrations:
                print("Warning: No calibration data found")
                calibrations = []

            # Create a lookup dictionary for calibrations by inventory_item_id
            calibration_lookup = {
                cal['inventory_item_id']: cal
                for cal in calibrations
            }

            # Process calibration data to add status
            from datetime import datetime
            current_date = datetime.now()

            for cal_id, cal_data in calibration_lookup.items():
                if cal_data.get('next_calibration'):
                    try:
                        next_cal_date = datetime.fromisoformat(cal_data['next_calibration'].replace('Z', '+00:00'))

                        # Calculate days remaining
                        days_remaining = (next_cal_date - current_date).days

                        # Set status based on days remaining
                        if days_remaining < 0:
                            cal_data['status'] = 'overdue'
                        elif days_remaining <= 10:  # Due within 10 days
                            cal_data['status'] = 'due'
                        else:
                            cal_data['status'] = 'valid'

                        # Add days remaining for sorting
                        cal_data['days_remaining'] = days_remaining

                    except Exception as e:
                        print(f"Error processing calibration date: {str(e)}")
                        cal_data['status'] = 'unknown'
                else:
                    cal_data['status'] = 'unknown'

            # Get items for each subcategory
            all_instruments = []
            for subcategory in subcategories:
                # Only process subcategories with category_id 5
                if subcategory.get('category_id') == instruments_category_id:
                    items = api.get_inventory_items(subcategory['id'])
                    if items:
                        for item in items:
                            # Get instrument code from dynamic_data
                            dynamic_data = item.get('dynamic_data', {})
                            instrument_code = dynamic_data.get('Instrument code')

                            # Skip items without an instrument code
                            if not instrument_code:
                                continue

                            # Get calibration info for this item
                            item_id = item.get('id')
                            calibration_info = calibration_lookup.get(item_id)

                            # Format display name
                            display_name = f"{subcategory['name']} - {instrument_code}"

                            all_instruments.append({
                                'name': display_name,
                                'id': item.get('id'),
                                'subcategory_id': subcategory['id'],
                                'instrument_code': instrument_code,
                                'item_code': item.get('item_code'),
                                'dynamic_data': dynamic_data,
                                'calibration': calibration_info
                            })

            # Sort instruments by instrument code
            all_instruments.sort(key=lambda x: x['instrument_code'])

            # Clear and populate list
            self.instrument_list.clear()
            for instrument in all_instruments:
                item = QListWidgetItem()
                widget = self.create_instrument_widget(instrument)
                item.setSizeHint(widget.sizeHint())
                self.instrument_list.addItem(item)
                self.instrument_list.setItemWidget(item, widget)

            # Show list and hide loading
            self.loading_label.hide()
            self.instrument_list.setVisible(True)

            # Update count label
            total_instruments = len(all_instruments)
            self.count_label.setText(f"Total: {total_instruments}")

        except Exception as e:
            error_msg = f"Error loading instruments: {str(e)}"
            self.loading_label.setText(error_msg)
            print(error_msg)

    def get_selected_instrument(self):
        """Get the selected instrument(s)"""
        selected = self.instrument_list.selectedItems()
        if not selected:
            return None
        if not self.allow_multiple:
            # Return the instrument code for single selection
            item = selected[0]
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if self.is_admin:
                    # For admin, return the category name
                    return instrument_data['name']
                # For operator, return the instrument code
                return instrument_data['instrument_code'] if instrument_data else None
            return None
        # Return list of instrument codes for multiple selection
        return [self.instrument_list.itemWidget(item).property("instrument_data")['instrument_code'] 
                for item in selected if self.instrument_list.itemWidget(item)]

    def accept(self):
        """Override accept to show warning for due/overdue instruments"""
        selected_items = self.instrument_list.selectedItems()
        if not selected_items:
            return
            
        # Check for due/overdue instruments
        due_instruments = []
        overdue_instruments = []
        
        for item in selected_items:
            widget = self.instrument_list.itemWidget(item)
            if widget:
                instrument_data = widget.property("instrument_data")
                if instrument_data and instrument_data.get('calibration'):
                    calibration = instrument_data['calibration']
                    if calibration.get('status') == 'overdue':
                        overdue_instruments.append(instrument_data['instrument_code'])
                    elif calibration.get('status') == 'due':
                        due_instruments.append(instrument_data['instrument_code'])
        
        if overdue_instruments or due_instruments:
            warning_msg = "Warning:\n\n"
            
            if overdue_instruments:
                warning_msg += "The following instruments are OVERDUE for calibration:\n"
                warning_msg += "\n".join(f"• {code}" for code in overdue_instruments)
                warning_msg += "\n\n"
                
            if due_instruments:
                warning_msg += "The following instruments are DUE for calibration within 10 days:\n"
                warning_msg += "\n".join(f"• {code}" for code in due_instruments)
                warning_msg += "\n\n"
                
            warning_msg += "Do you want to proceed with the selection?"
            
            # Create custom warning dialog
            warning_dialog = QtWidgets.QMessageBox(self)
            warning_dialog.setIcon(QtWidgets.QMessageBox.Warning)
            warning_dialog.setWindowTitle("Calibration Warning")
            warning_dialog.setText(warning_msg)
            warning_dialog.setStandardButtons(
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            warning_dialog.setDefaultButton(QtWidgets.QMessageBox.No)
            
            # Style the warning dialog
            warning_dialog.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                }
                QMessageBox QLabel {
                    color: #333;
                    font-size: 12px;
                    min-width: 400px;
                }
                QPushButton {
                    padding: 6px 14px;
                    border-radius: 4px;
                    font-size: 13px;
                    min-width: 70px;
                }
                QPushButton[text="&Yes"] {
                    background-color: #f44336;
                    color: white;
                    border: none;
                }
                QPushButton[text="&Yes"]:hover {
                    background-color: #d32f2f;
                }
                QPushButton[text="&No"] {
                    background-color: #f5f5f5;
                    color: #333;
                    border: 1px solid #ddd;
                }
                QPushButton[text="&No"]:hover {
                    background-color: #e0e0e0;
                }
            """)
            
            # Show the warning dialog
            if warning_dialog.exec_() != QtWidgets.QMessageBox.Yes:
                return
        
        # If no warning or user confirmed, proceed with accept
        super().accept()

class BluetoothDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bluetooth Connectivity")
        self.setMinimumWidth(600)
        self.setMinimumHeight(700)
        
        # Get screen size
        screen = QtWidgets.QApplication.desktop().screenGeometry()
        # Set maximum size to 80% of screen size
        self.setMaximumWidth(int(screen.width() * 0.8))
        self.setMaximumHeight(int(screen.height() * 0.8))
        
        # Center the dialog on screen
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2
        )
        
        # Initialize current_instrument
        self.current_instrument = None
        
        self.setup_ui()

    def connect_to_device(self, device, instrument_data):
        """Show device details dialog"""
        try:
            dialog = DeviceDetailsDialog(device, instrument_data, self)
            dialog.exec_()
        except Exception as e:
            print(f"Error showing device details: {str(e)}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to show device details: {str(e)}"
            )

    def filter_by_subcategory(self, index):
        """Filter instruments by selected subcategory"""
        if not hasattr(self, 'instrument_list'):
            return
            
        selected_text = self.subcategory_combo.currentText().strip()
        search_text = self.search_box.text().strip().lower()
        
        for i in range(self.instrument_list.count()):
            item = self.instrument_list.item(i)
            widget = self.instrument_list.itemWidget(item)
            if widget:
                # Find both the main name label and code label
                name_label = widget.findChild(QLabel)
                if name_label:
                    # Get the instrument name
                    instrument_name = name_label.text().strip()
                    
                    # For Plug Gauge Box L2 items, the category is the first part before the hyphen
                    base_category = instrument_name.split(" - ")[0] if " - " in instrument_name else instrument_name
                    
                    # Category matching - either "All Categories" or the base category contains the selected text
                    category_match = (
                        selected_text == "All Categories" or 
                        (selected_text.lower() in base_category.lower() if selected_text != "All Categories" else True)
                    )
                    
                    # Search matching - search in the full instrument name
                    search_match = not search_text or search_text in instrument_name.lower()
                    
                    # Show/hide based on both conditions
                    item.setHidden(not (category_match and search_match))
        
        # Update count label
        visible_count = sum(1 for i in range(self.instrument_list.count()) 
                          if not self.instrument_list.item(i).isHidden())
        total_count = self.instrument_list.count()
        
        if selected_text == "All Categories":
            if search_text:
                self.count_label.setText(f"Showing {visible_count} of {total_count}")
            else:
                self.count_label.setText(f"Total: {total_count}")
        else:
            self.count_label.setText(f"Showing {visible_count} of {total_count} ({selected_text})")
            
    def filter_instruments(self, text):
        """Filter instruments based on search text"""
        self.filter_by_subcategory(self.subcategory_combo.currentIndex())

    def setup_ui(self):
        """Setup the UI elements"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header layout for title and count
        header_layout = QHBoxLayout()
        
        # Title label
        title_label = QLabel("Bluetooth Configuration")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        header_layout.addWidget(title_label)
        
        # Count label
        self.count_label = QLabel()
        self.count_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 14px;
                padding: 2px 8px;
                background-color: #f8f9fa;
                border-radius: 10px;
                border: 1px solid #e0e0e0;
            }
        """)
        header_layout.addWidget(self.count_label, alignment=Qt.AlignRight)
        
        layout.addLayout(header_layout)
        
        # Filter section
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(10)
        
        # Subcategory dropdown
        subcategory_label = QLabel("Category:")
        subcategory_label.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 13px;
                font-weight: bold;
                min-width: 70px;
            }
        """)
        filter_layout.addWidget(subcategory_label)
        
        self.subcategory_combo = QComboBox()
        self.subcategory_combo.setStyleSheet("""
            QComboBox {
                padding: 6px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #2196f3;
            }
            QComboBox:focus {
                border-color: #2196f3;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
        """)
        self.subcategory_combo.addItem("All Categories")
        self.subcategory_combo.currentIndexChanged.connect(self.filter_by_subcategory)
        filter_layout.addWidget(self.subcategory_combo)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search instruments...")
        self.search_box.textChanged.connect(self.filter_instruments)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #2196f3;
                background-color: #fff;
            }
        """)
        
        # Add search box with stretch
        filter_layout.addWidget(self.search_box)
        filter_layout.setStretchFactor(self.search_box, 1)
        
        layout.addLayout(filter_layout)
        
        # Tab widget for different sections
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background: white;
                padding: 10px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border: 1px solid #e0e0e0;
                border-bottom: none;
                background: #f8f9fa;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: none;
                margin-bottom: -1px;
            }
            QTabBar::tab:hover:!selected {
                background: #e9ecef;
            }
        """)
        
        # Instruments tab
        instruments_tab = QWidget()
        instruments_layout = QVBoxLayout(instruments_tab)
        instruments_layout.setContentsMargins(0, 10, 0, 0)
        instruments_layout.setSpacing(10)
        
        # Loading indicator
        self.loading_label = QLabel("Loading instruments...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 13px;
                padding: 12px;
                background-color: #f8f9fa;
                border-radius: 4px;
            }
        """)
        instruments_layout.addWidget(self.loading_label)
        
 # Instruments list
        self.instrument_list = QListWidget()
        self.instrument_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                outline: none;
            }
            QListWidget::item {
                padding: 1px;
                border-bottom: 1px solid #f0f0f0;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        instruments_layout.addWidget(self.instrument_list)
        self.instrument_list.setVisible(False)
        
        # Bluetooth Devices tab
        bluetooth_tab = QWidget()
        bluetooth_layout = QVBoxLayout(bluetooth_tab)
        bluetooth_layout.setContentsMargins(0, 10, 0, 0)
        bluetooth_layout.setSpacing(10)
        
        # Scan button
        scan_button = QPushButton("Scan for Bluetooth Devices")
        scan_button.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #1976f3;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        scan_button.clicked.connect(self.scan_bluetooth_devices)
        bluetooth_layout.addWidget(scan_button)
        
        # Bluetooth devices list
        self.bluetooth_list = QListWidget()
        self.bluetooth_list.setStyleSheet(self.instrument_list.styleSheet())
        bluetooth_layout.addWidget(self.bluetooth_list)
        
        # Add tabs
        tab_widget.addTab(instruments_tab, "Instruments")
        tab_widget.addTab(bluetooth_tab, "Bluetooth Devices")
        
        layout.addWidget(tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.close_button = QPushButton("Close")
        self.close_button.setStyleSheet("""
            QPushButton {
                padding: 3px 12px;
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                font-size: 11px;
                min-width: 60px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.close_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        # Load instruments
        self.load_instruments()

    def create_instrument_widget(self, instrument_data):
        """Create a custom widget for instrument list item"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Instrument info
        info_layout = QVBoxLayout()
        name_label = QLabel(instrument_data['name'])
        name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        code_label = QLabel(f"Code: {instrument_data['instrument_code']}")
        code_label.setStyleSheet("color: #666; font-size: 12px;")
        
        info_layout.addWidget(name_label)
        info_layout.addWidget(code_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # Add Configure button
        configure_button = QPushButton("Configure")
        configure_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
        """)
        configure_button.clicked.connect(lambda: self.configure_instrument(instrument_data))
        layout.addWidget(configure_button)
        
        # Store the data in the widget for retrieval
        widget.setProperty("instrument_data", instrument_data)
        
        return widget

    def configure_instrument(self, instrument_data):
        """Handle configure button click for an instrument"""
        try:
            # Store the current instrument data
            self.current_instrument = instrument_data
            
            # Switch to Bluetooth tab
            tab_widget = self.findChild(QtWidgets.QTabWidget)
            if tab_widget:
                tab_widget.setCurrentIndex(1)  # Switch to Bluetooth tab
                # Trigger Bluetooth scan
                self.scan_bluetooth_devices()
                
        except Exception as e:
            print(f"Error configuring instrument: {str(e)}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to start configuration: {str(e)}"
            )

    async def discover_devices(self):
        """Discover Bluetooth devices using Bleak"""
        try:
            import asyncio
            import nest_asyncio
            from bleak import BleakScanner
            
            nest_asyncio.apply()
            
            async with BleakScanner() as scanner:
                devices = await scanner.discover()
                # Use moveToThread to safely update UI from the main thread
                self.devices_found.emit(devices)
                
        except Exception as e:
            print(f"Error discovering Bluetooth devices: {str(e)}")
            self.scan_error.emit(str(e))

    def scan_bluetooth_devices(self):
        """Start Bluetooth device scanning"""
        try:
            # Create and run the event loop in a separate thread
            from PyQt5.QtCore import QThread, pyqtSignal
            
            class ScannerThread(QThread):
                devices_found = pyqtSignal(list)
                scan_error = pyqtSignal(str)
                
                def __init__(self, parent=None):
                    super().__init__(parent)
                    self.devices_found.connect(parent.update_device_list)
                    self.scan_error.connect(parent.on_scan_error)
                
                def run(self):
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.parent().discover_devices())
                        loop.close()
                    except Exception as e:
                        self.scan_error.emit(str(e))
            
            # Show scanning status in main thread
            self.bluetooth_list.clear()
            scanning_item = QListWidgetItem("Scanning for devices...")
            scanning_item.setTextAlignment(Qt.AlignCenter)
            self.bluetooth_list.addItem(scanning_item)
            
            # Create and start the scanner thread
            self.scanner_thread = ScannerThread(self)
            self.devices_found = self.scanner_thread.devices_found
            self.scan_error = self.scanner_thread.scan_error
            self.scanner_thread.start()
            
        except Exception as e:
            print(f"Error starting Bluetooth scan: {str(e)}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to start Bluetooth scan: {str(e)}"
            )

    def update_device_list(self, devices):
        """Update the device list in the main thread"""
        try:
            self.bluetooth_list.clear()
            
            if not devices:
                no_devices_item = QListWidgetItem("No devices found")
                no_devices_item.setTextAlignment(Qt.AlignCenter)
                self.bluetooth_list.addItem(no_devices_item)
                return
            
            for device in devices:
                # Create list item
                item = QListWidgetItem()
                
                # Create widget for the item
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(10, 10, 10, 10)
                
                # Info container
                info_container = QWidget()
                info_layout = QVBoxLayout(info_container)
                info_layout.setContentsMargins(0, 0, 0, 0)
                info_layout.setSpacing(4)
                
                # Device name with larger font
                name_label = QLabel(str(device.name or "Unknown Device"))
                name_label.setStyleSheet("""
                    QLabel {
                        font-weight: bold;
                        font-size: 14px;
                        color: #2c3e50;
                    }
                """)
                name_label.setWordWrap(True)
                info_layout.addWidget(name_label)
                
                # MAC Address
                address_label = QLabel(f"MAC Address: {device.address}")
                address_label.setStyleSheet("color: #666; font-size: 12px;")
                info_layout.addWidget(address_label)
                
                # Add RSSI if available
                if hasattr(device, 'advertisement') and device.advertisement:
                    rssi = getattr(device.advertisement, 'rssi', None)
                    if rssi is not None:
                        rssi_label = QLabel(f"Signal Strength: {rssi} dBm")
                        rssi_label.setStyleSheet("color: #666; font-size: 12px;")
                        info_layout.addWidget(rssi_label)
                
                layout.addWidget(info_container)
                layout.addStretch()
                
                # Connect button
                connect_button = QPushButton("Configure")
                connect_button.setStyleSheet("""
                    QPushButton {
                        padding: 6px 12px;
                        background-color: #2196f3;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                        
                    }
                    QPushButton:hover {
                        background-color: #1976d2;
                    }
                """)
                
                # Store device and current_instrument in button's properties
                connect_button.setProperty("device", device)
                connect_button.setProperty("instrument_data", self.current_instrument)
                
                # Use a lambda to pass both device and current_instrument
                connect_button.clicked.connect(
                    lambda checked, d=device: self.connect_to_device(d, self.current_instrument)
                )
                layout.addWidget(connect_button)
                
                # Set minimum height for the widget
                widget.setMinimumHeight(80)
                
                # Set size hint and add to list
                item.setSizeHint(widget.sizeHint())
                self.bluetooth_list.addItem(item)
                self.bluetooth_list.setItemWidget(item, widget)
                
        except Exception as e:
            print(f"Error updating device list: {str(e)}")
            self.on_scan_error(str(e))

    def configure_instrument(self, instrument_data):
        """Handle configure button click for an instrument"""
        try:
            # Store the current instrument data
            self.current_instrument = instrument_data
            
            # Switch to Bluetooth tab
            tab_widget = self.findChild(QtWidgets.QTabWidget)
            if tab_widget:
                tab_widget.setCurrentIndex(1)  # Switch to Bluetooth tab
                # Start scanning
                self.scan_bluetooth_devices()
                
        except Exception as e:
            print(f"Error configuring instrument: {str(e)}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to start configuration: {str(e)}"
            )

    def on_scan_error(self, error_message):
        """Handle scan error"""
        try:
            self.bluetooth_list.clear()
            error_item = QListWidgetItem(f"Error: {error_message}")
            error_item.setTextAlignment(Qt.AlignCenter)
            self.bluetooth_list.addItem(error_item)
            
            QtWidgets.QMessageBox.critical(
                self,
                "Scan Error",
                f"Failed to scan for Bluetooth devices: {error_message}"
            )
        except Exception as e:
            print(f"Error handling scan error: {str(e)}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "An unexpected error occurred while handling the scan error."
            )

    def on_scan_complete(self):
        """Handle scan completion"""
        try:
            if self.bluetooth_list.count() == 0:
                no_devices_item = QListWidgetItem("No devices found")
                no_devices_item.setTextAlignment(Qt.AlignCenter)
                self.bluetooth_list.addItem(no_devices_item)
        except Exception as e:
            print(f"Error handling scan completion: {str(e)}")
            self.on_scan_error("Failed to update device list after scan completion")

    def load_instruments(self):
        """Load instruments from the API"""
        try:
            # Show loading indicator
            self.loading_label.setText("Loading instruments...")
            self.loading_label.show()
            self.instrument_list.setVisible(False)
            
            # Use fixed category ID 5 for Instruments
            instruments_category_id = 5
            
            # Get subcategories for Instruments category
            subcategories = api.get_inventory_subcategories(instruments_category_id)
            if not subcategories:
                raise Exception("Failed to fetch subcategories")
            
            # Store subcategories for filtering
            self.subcategories = subcategories
            
            # Clear and repopulate subcategory combo
            self.subcategory_combo.clear()
            self.subcategory_combo.addItem("All Categories")
            for subcategory in subcategories:
                if subcategory.get('category_id') == instruments_category_id:
                    self.subcategory_combo.addItem(subcategory['name'], subcategory['id'])
            
            # Get all calibration data
            calibrations = api.get_calibrations()
            if not calibrations:
                print("Warning: No calibration data found")
                calibrations = []
            
            # Create a lookup dictionary for calibrations by inventory_item_id
            calibration_lookup = {
                cal['inventory_item_id']: cal 
                for cal in calibrations
            }
            
            # Get items for each subcategory
            all_instruments = []
            for subcategory in subcategories:
                # Only process subcategories with category_id 5
                if subcategory.get('category_id') == instruments_category_id:
                    items = api.get_inventory_items(subcategory['id'])
                    if items:
                        for item in items:
                            # Get instrument code from dynamic_data
                            dynamic_data = item.get('dynamic_data', {})
                            instrument_code = dynamic_data.get('Instrument code')
                            
                            # Skip items without an instrument code
                            if not instrument_code:
                                continue
                            
                            # Get calibration info for this item
                            item_id = item.get('id')
                            calibration_info = calibration_lookup.get(item_id)
                            
                            # Format display name
                            display_name = f"{subcategory['name']} - {instrument_code}"
                            
                            all_instruments.append({
                                'name': display_name,
                                'id': item.get('id'),
                                'subcategory_id': subcategory['id'],
                                'instrument_code': instrument_code,
                                'item_code': item.get('item_code'),
                                'dynamic_data': dynamic_data,
                                'calibration': calibration_info
                            })
            
            # Sort instruments by instrument code
            all_instruments.sort(key=lambda x: x['instrument_code'])
            
            # Clear and populate list
            self.instrument_list.clear()
            for instrument in all_instruments:
                item = QListWidgetItem()
                widget = self.create_instrument_widget(instrument)
                item.setSizeHint(widget.sizeHint())
                self.instrument_list.addItem(item)
                self.instrument_list.setItemWidget(item, widget)
            
            # Show list and hide loading
            self.loading_label.hide()
            self.instrument_list.setVisible(True)
            
            # Update count label
            total_instruments = len(all_instruments)
            self.count_label.setText(f"Total: {total_instruments}")
            
        except Exception as e:
            error_msg = f"Error loading instruments: {str(e)}"
            self.loading_label.setText(error_msg)
            print(error_msg)

    def clean_path(self, path):
        """Clean up the path by removing duplicate folder names"""
        if not path:
            return path
            
        print(f"Original path: {path}")  # Debug log
            
        # Split path into components
        parts = path.split('/')
        print(f"Split parts: {parts}")  # Debug log
            
        # Remove all duplicates, not just consecutive ones
        seen = set()
        cleaned_parts = []
        for part in parts:
            if part not in seen:
                seen.add(part)
                cleaned_parts.append(part)
                
        cleaned_path = '/'.join(cleaned_parts)
        print(f"Cleaned path: {cleaned_path}")  # Debug log
        return cleaned_path
            
    def populate_tree_view(self, folders, parent_item=None):
        """Populate the tree view with folder structure"""
        model = self.tree_view.model()
        if parent_item is None:
            model.clear()
            parent_item = model.invisibleRootItem()
            
        for folder in folders:
            item = QStandardItem(folder['name'])
            item.setData(folder['id'], Qt.UserRole)
            # Clean the path before storing it
            if 'path' in folder:
                cleaned_path = self.clean_path(folder['path'])
                print(f"Storing cleaned path: {cleaned_path}")  # Debug log
                item.setData(cleaned_path, Qt.UserRole + 1)
            else:
                print(f"Warning: No path found in folder: {folder}")  # Debug log
                item.setData('', Qt.UserRole + 1)
                
            parent_item.appendRow(item)
            
            if 'children' in folder and folder['children']:
                self.populate_tree_view(folder['children'], item)

class DeviceDetailsDialog(QDialog):
    def __init__(self, device, instrument_data, parent=None):
        super().__init__(parent)
        self.device = device
        self.instrument_data = instrument_data
        self.uuid = None
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Configure Device")
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Device info section
        info_group = QtWidgets.QGroupBox("Device Information")
        info_layout = QVBoxLayout(info_group)
        
        # Device name
        name_label = QLabel(f"Name: {self.device.name or 'Unknown Device'}")
        name_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        info_layout.addWidget(name_label)
        
        # MAC Address
        address_label = QLabel(f"MAC Address: {self.device.address}")
        info_layout.addWidget(address_label)
        
        # Instrument info
        instrument_label = QLabel(f"Instrument: {self.instrument_data['instrument_code']}")
        info_layout.addWidget(instrument_label)
        
        # RSSI if available
        if hasattr(self.device, 'advertisement') and self.device.advertisement:
            rssi = getattr(self.device.advertisement, 'rssi', None)
            if rssi is not None:
                rssi_label = QLabel(f"Signal Strength: {rssi} dBm")
                info_layout.addWidget(rssi_label)
        
        layout.addWidget(info_group)
        
        # UUID Input section
        uuid_group = QtWidgets.QGroupBox("Configuration")
        uuid_layout = QVBoxLayout(uuid_group)
        
        uuid_label = QLabel("Nordic UART TX UUID:")
        self.uuid_input = QLineEdit()
        self.uuid_input.setPlaceholderText("Enter UUID")
        self.uuid_input.setText("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")  # Default Nordic UART TX UUID
        uuid_layout.addWidget(uuid_label)
        uuid_layout.addWidget(self.uuid_input)
        
        layout.addWidget(uuid_group)
        
        # Status section
        self.status_label = QLabel("Ready to save configuration")
        self.status_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                border-radius: 4px;
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
            }
        """)
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.save_button = QPushButton("Save Configuration")
        self.save_button.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:disabled {
                background-color: #90caf9;
            }
        """)
        self.save_button.clicked.connect(self.save_configuration)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                padding: 8px 24px;
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                font-size: 13px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)

    def save_configuration(self):
        """Save device configuration to database"""
        try:
            self.save_button.setEnabled(False)
            self.status_label.setText("Saving configuration...")
            
            # Get UUID from input
            self.uuid = self.uuid_input.text().strip()
            if not self.uuid:
                raise Exception("Please enter a UUID")
            
            # Debug print configuration data
            print("\nSaving configuration data:")
            print(f"Instrument Data: {self.instrument_data}")
            print(f"UUID: {self.uuid}")
            print(f"Device Address: {self.device.address}")
            
            payload = {
                "inventory_item_id": self.instrument_data['id'],
                "instrument": self.instrument_data['instrument_code'],
                "uuid": self.uuid,
                "address": self.device.address
            }
            
            print(f"\nSending payload to API: {payload}")
            
            # Make API request
            response = api._make_request(
                "/quality/connectivity/",
                method="POST",
                data=payload
            )
            
            print(f"\nAPI Response: {response}")
            
            if response:
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    "Device configuration saved successfully!"
                )
                self.accept()
            else:
                raise Exception("Failed to save configuration")
                
        except Exception as e:
            error_msg = f"Failed to save configuration: {str(e)}"
            print(f"\nError: {error_msg}")
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                error_msg
            )
            self.save_button.setEnabled(True)

class ReportFolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Report")
        self.setMinimumWidth(550)
        self.setMinimumHeight(650)
        
        self.folder_structure = None
        self.selected_folder = None
        self.new_folder_name = ""
        self.is_saving = False
        self.save_successful = False  # Add flag to track save success
        
        # Set window style
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QGroupBox {
                font-weight: 500;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 12px;
                color: #424242;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background-color: white;
            }
            QPushButton {
                background-color: #f5f5f5;
                color: #424242;
                border: 1px solid #e0e0e0;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #eeeeee;
                border-color: #bdbdbd;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #9e9e9e;
                border-color: #e0e0e0;
            }
            QPushButton#okButton {
                background-color: #1976d2;
                color: white;
                border: none;
            }
            QPushButton#okButton:hover {
                background-color: #1565c0;
            }
            QPushButton#okButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton#okButton:disabled {
                background-color: #90caf9;
            }
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
            QLineEdit:focus {
                border-color: #1976d2;
            }
            QTreeView {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            QTreeView::item {
                padding: 6px;
                color: #424242;
            }
            QTreeView::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
            QLabel {
                color: #424242;
            }
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                text-align: center;
                height: 4px;
            }
            QProgressBar::chunk {
                background-color: #1976d2;
            }
        """)
        
        self.setup_ui()
        self.load_folder_structure()
        
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 24, 24, 24)
        
        # Title and description
        title_label = QLabel("Save Report")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 500;
            color: #424242;
        """)
        description_label = QLabel("Select an existing folder or create a new one to save your report.")
        description_label.setStyleSheet("""
            font-size: 13px;
            color: #757575;
            margin-bottom: 16px;
        """)
        main_layout.addWidget(title_label)
        main_layout.addWidget(description_label)
        
        # Tree view section
        tree_group = QGroupBox("Existing Folders")
        tree_layout = QVBoxLayout()
        tree_layout.setSpacing(8)
        
        # Search box for folders
        search_layout = QHBoxLayout()
        search_icon = QLabel("🔍")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search folders...")
        self.search_box.textChanged.connect(self.filter_folders)
        search_layout.addWidget(search_icon)
        search_layout.addWidget(self.search_box)
        tree_layout.addLayout(search_layout)
        
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setModel(QStandardItemModel())
        self.tree_view.clicked.connect(self.on_folder_selected)
        self.tree_view.setMinimumHeight(300)
        tree_layout.addWidget(self.tree_view)
        
        tree_group.setLayout(tree_layout)
        main_layout.addWidget(tree_group)
        
        # New folder section
        new_folder_group = QGroupBox("New Folder")
        new_folder_layout = QVBoxLayout()
        new_folder_layout.setSpacing(12)
        
        # Input field with label
        input_layout = QHBoxLayout()
        label = QLabel("Folder Name:")
        label.setStyleSheet("font-weight: 500;")
        self.folder_name_edit = QLineEdit()
        self.folder_name_edit.setPlaceholderText("Enter folder name")
        input_layout.addWidget(label)
        input_layout.addWidget(self.folder_name_edit)
        new_folder_layout.addLayout(input_layout)
        
        # Select button
        select_button = QPushButton("Select New Folder")
        select_button.setMinimumHeight(36)
        select_button.clicked.connect(self.select_new_folder)
        new_folder_layout.addWidget(select_button)
        
        new_folder_group.setLayout(new_folder_layout)
        main_layout.addWidget(new_folder_group)
        
        # Status section
        self.status_label = QLabel()
        self.status_label.setStyleSheet("""
            padding: 8px;
            border-radius: 4px;
            background-color: #f5f5f5;
            color: #424242;
        """)
        self.status_label.hide()
        main_layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.handle_cancel)
        
        self.ok_button = QPushButton("Save")
        self.ok_button.setObjectName("okButton")
        self.ok_button.clicked.connect(self.handle_save)
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
    def filter_folders(self, text):
        """Filter folders in tree view based on search text"""
        if not text:
            # Show all items
            self.populate_tree_view(self.folder_structure)
            return
            
        def match_folder(folder, search_text):
            if search_text.lower() in folder['name'].lower():
                return True
            if 'children' in folder:
                return any(match_folder(child, search_text) for child in folder['children'])
            return False
            
        # Filter the folder structure
        filtered_structure = [
            folder for folder in self.folder_structure
            if match_folder(folder, text)
        ]
        
        # Update tree view with filtered results
        self.populate_tree_view(filtered_structure)
        
    def show_status(self, message, is_error=False):
        """Show status message with appropriate styling"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"""
            padding: 8px;
            border-radius: 4px;
            background-color: {'#ffebee' if is_error else '#e8f5e9'};
            color: {'#c62828' if is_error else '#2e7d32'};
        """)
        self.status_label.show()
        
    def handle_save(self):
        """Handle the save button click"""
        if not self.selected_folder and not self.new_folder_name:
            self.show_status("Please select a folder or enter a new folder name", True)
            return
            
        try:
            self.is_saving = True
            self.ok_button.setEnabled(False)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.progress_bar.show()
            self.show_status("Saving report...")
            
            # Get the folder path
            folder_path = self.get_selected_folder()
            if not folder_path:
                raise ValueError("No folder selected")
                
            # Set the save_successful flag to True - this will be checked by the caller
            self.save_successful = True
            
            # Accept the dialog to return to the caller
            self.accept()
            
        except Exception as e:
            print(f"Error during save: {str(e)}")
            self.show_status(f"Error saving report: {str(e)}", True)
            self.save_successful = False
            self.is_saving = False
            self.ok_button.setEnabled(True)
            self.progress_bar.hide()
            
    def handle_cancel(self):
        """Handle the cancel button click"""
        if self.is_saving:
            reply = QMessageBox.question(
                self,
                "Cancel Save",
                "Are you sure you want to cancel saving the report?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.reject()
        else:
            self.reject()
            
    def select_new_folder(self):
        """Select a new folder name"""
        folder_name = self.folder_name_edit.text().strip()
        if not folder_name:
            self.show_status("Please enter a folder name", True)
            return
            
        self.new_folder_name = folder_name
        self.selected_folder = None
        
        # Set active status
        self.folder_name_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #1976d2;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
        """)
        
        self.folder_name_edit.clear()
        self.show_status(f"Selected new folder: {folder_name}")
        
    def on_folder_selected(self, index):
        """Handle folder selection"""
        model = self.tree_view.model()
        item = model.itemFromIndex(index)
        
        # Get the full path of the selected item by traversing up the tree
        path_parts = []
        current_item = item
        while current_item and current_item != model.invisibleRootItem():
            path_parts.insert(0, current_item.text())
            current_item = current_item.parent()
            
        # Build the full path
        full_path = "/".join(path_parts)
        
        # If this is a file (has extension), get its parent folder
        if "." in path_parts[-1]:  # This is a file
            path_parts.pop()  # Remove the file
            full_path = "/".join(path_parts)
            
        # If this is under REPORT, make sure we select the proper subfolder
        if path_parts and path_parts[0] == "REPORT":
            if len(path_parts) >= 2:  # If we have at least one subfolder under REPORT
                # Select the first subfolder under REPORT
                full_path = path_parts[1]  # Just use the first subfolder name
                
                # Find and select the corresponding item in the tree
                for row in range(model.rowCount()):
                    root_item = model.item(row)
                    if root_item.text() == path_parts[1]:
                        item = root_item
                        break
        
        self.selected_folder = {
            'id': item.data(Qt.UserRole),
            'path': full_path
        }
        self.new_folder_name = ""
        
        # Reset input field style
        self.folder_name_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
                color: #424242;
            }
            QLineEdit:focus {
                border-color: #1976d2;
            }
        """)
        
        self.show_status(f"Selected folder: {self.selected_folder['path']}")
        
        # Highlight the selected folder in the tree view
        self.tree_view.setCurrentIndex(model.indexFromItem(item))
        
    def get_selected_folder(self):
        """Get the selected folder name"""
        if self.selected_folder:
            return self.selected_folder['path']
        elif self.new_folder_name:
            return self.new_folder_name
        return None

    def load_folder_structure(self):
        """Load the folder structure from the API"""
        try:
            self.folder_structure = api.get_report_structure()
            if self.folder_structure:
                print("Received folder structure:", self.folder_structure)
                self.populate_tree_view(self.folder_structure)
            else:
                self.show_status("No folder structure received from API", True)
        except Exception as e:
            print(f"Error loading folder structure: {str(e)}")
            self.show_status(f"Failed to load folder structure: {str(e)}", True)
            
    def populate_tree_view(self, folders, parent_item=None):
        """Populate the tree view with folder structure"""
        try:
            model = self.tree_view.model()
            if parent_item is None:
                model.clear()
                parent_item = model.invisibleRootItem()
                
            for folder in folders:
                try:
                    item = QStandardItem(folder['name'])
                    item.setData(folder['id'], Qt.UserRole)
                    path = folder.get('path', folder['name'])
                    item.setData(path, Qt.UserRole + 1)
                    parent_item.appendRow(item)
                    
                    if 'children' in folder and folder['children']:
                        self.populate_tree_view(folder['children'], item)
                except KeyError as e:
                    print(f"Error processing folder: {folder}, missing key: {str(e)}")
                    continue
        except Exception as e:
            print(f"Error populating tree view: {str(e)}")
            self.show_status("Error loading folders", True)
            
    def handle_save(self):
        """Handle the save button click"""
        if not self.selected_folder and not self.new_folder_name:
            self.show_status("Please select a folder or enter a new folder name", True)
            return
            
        try:
            self.is_saving = True
            self.ok_button.setEnabled(False)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress
            self.progress_bar.show()
            self.show_status("Saving report...")
            
            # Get the folder path
            folder_path = self.get_selected_folder()
            if not folder_path:
                raise ValueError("No folder selected")
                
            # Set the save_successful flag to True - this will be checked by the caller
            self.save_successful = True
            
            # Accept the dialog to return to the caller
            self.accept()
            
        except Exception as e:
            print(f"Error during save: {str(e)}")
            self.show_status(f"Error saving report: {str(e)}", True)
            self.save_successful = False
            self.is_saving = False
            self.ok_button.setEnabled(True)
            self.progress_bar.hide()
            
    def get_save_status(self):
        """Return whether the save was successful"""
        return self.save_successful
        
    def get_selected_folder(self):
        """Get the selected folder name"""
        if self.selected_folder:
            return self.selected_folder['path']
        elif self.new_folder_name:
            return self.new_folder_name
        return None


