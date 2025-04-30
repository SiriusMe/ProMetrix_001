import sys
import traceback
import threading
import queue
from datetime import datetime
import weakref
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QPainter, QPen, QColor

# Thread-local storage for exception handling state
_exception_state = threading.local()
_exception_refs = weakref.WeakSet()

def safe_exception_hook(exctype, value, tb):
    """Thread-safe exception hook that prevents recursion"""
    # Check if we're already handling an exception in this thread
    if getattr(_exception_state, 'handling', False):
        return
        
    try:
        _exception_state.handling = True
        
        # Generate error message
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"\n[{timestamp}]\n{'-'*50}\n{error_msg}"
        
        # Print to stderr
        print(f"Uncaught exception:\n{error_msg}", file=sys.stderr)
        
        try:
            # Log to file with atomic write
            with open('error.log', 'a') as f:
                f.write(log_msg)
        except:
            pass
            
    finally:
        _exception_state.handling = False

# Install the safe exception hook
sys.excepthook = safe_exception_hook

class LoadingIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(40, 40)
        
    @QtCore.pyqtProperty(float)
    def angle(self):
        return self._angle
        
    @angle.setter
    def angle(self, angle):
        self._angle = angle % 360
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Set up the pen for the arc
        pen = QPen(QColor(0, 120, 215))  # Windows blue color
        pen.setWidth(3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        
        # Calculate the rectangle for the arc
        rect = QtCore.QRectF(3, 3, 34, 34)
        
        # Convert float angles to integers (QPainter uses 16th of a degree)
        start_angle = int(-self._angle * 16)  # Convert to int for drawArc
        span_angle = int(300 * 16)  # Convert to int for drawArc
        
        # Draw the arc using integer angles
        painter.drawArc(rect.toRect(), start_angle, span_angle)

class Ui_MainWindow(object):
    def __init__(self):
        self.mainwindow = None  # Store reference to main window

    def setupUi(self, MainWindow):
        self.mainwindow = MainWindow  # Store the main window reference
        # Base window setup with enhanced styling
        MainWindow.setObjectName("MainWindow")
        custom_font = QFont("Segoe UI", 10)
        # Set the font for the entire application (global font)
        QApplication.setFont(custom_font)
        # Set the font for the main window
        MainWindow.setFont(custom_font)
        
        # Get the screen geometry to open the window maximized
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # Set the window size to fullscreen and position it
        MainWindow.resize(screen_width, screen_height)
        MainWindow.move(0, 0)  # Move the window to the top-left corner

        # Set the minimum size to half of the screen size
        min_width = screen_width // 2
        min_height = screen_height // 2
        MainWindow.setMinimumSize(QSize(min_width, min_height))
        MainWindow.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
            QMenuBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e0e0e0;
            }
            QMenuBar::item {
                padding: 6px 10px;
                color: #424242;
                margin: 1px;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background-color: #f5f5f5;
            }
            QMenuBar::item:pressed {
                background-color: #e3f2fd;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 25px;
                color: #424242;
                border-radius: 3px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background-color: #f5f5f5;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 4px 8px;
            }
            QToolBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e0e0e0;
                spacing: 3px;
                padding: 3px;
            }
            QToolBar::separator {
                width: 1px;
                background-color: #e0e0e0;
                margin: 4px 2px;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px;
                margin: 1px;
            }
            QToolButton:hover {
                background-color: #f5f5f5;
            }
            QToolButton:pressed {
                background-color: #e3f2fd;
            }
            QToolButton:checked {
                background-color: #e3f2fd;
                border: 1px solid #90caf9;
            }
            QToolTip {
                background-color: #424242;
                color: white;
                padding: 5px;
                border: none;
                border-radius: 3px;
            }
        """)

        # Initialize main widget and layouts  
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setStyleSheet("""
            QWidget {
                background-color: #f5f6fa;
            }
        """)

        # Setup UI components
        self.setupCentralWidget()
        self.setupMenuBar(MainWindow)
        self.setupToolBar(MainWindow)
        self.setupStatusBar(MainWindow)

        # Set central widget
        MainWindow.setCentralWidget(self.centralwidget)

        # Connect signals
        self.connectSignals()

        # Translate UI
        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def setupCentralWidget(self):
        # Enhanced central widget styling
        main_layout = QtWidgets.QHBoxLayout(self.centralwidget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 20)

        # Create a container for toolbar and drawing
        self.drawing_container = QtWidgets.QWidget()
        drawing_container_layout = QtWidgets.QHBoxLayout(self.drawing_container)
        drawing_container_layout.setSpacing(0)
        drawing_container_layout.setContentsMargins(0, 0, 0, 0)

        # Create vertical toolbar
        self.toolBar = QtWidgets.QToolBar()
        self.toolBar.setObjectName("toolBar")
        self.toolBar.setOrientation(QtCore.Qt.Vertical)
        self.toolBar.setIconSize(QtCore.QSize(24, 24))
        
        # Modern vertical toolbar styling
        self.toolBar.setStyleSheet("""
            QToolBar {
                background-color: #f8f9fa;
                border: none;
                border-right: 1px solid #e0e0e0;
                spacing: 1px;
                padding: 2px;
            }

            QToolButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 2px;
                margin: 0px;
                min-width: 28px;
                min-height: 28px;
            }

            QToolButton:hover {
                background-color: #e8f0fe;
                border: 1px solid #e8f0fe;
            }

            QToolButton:pressed {
                background-color: #d2e3fc;
                border: 1px solid #d2e3fc;
            }

            QToolButton:checked {
                background-color: #d2e3fc;
                border: 1px solid #d2e3fc;
            }

            QToolButton:disabled {
                background-color: transparent;
                color: #bdbdbd;
            }

            QToolBar::separator {
                background-color: #e0e0e0;
                height: 1px;
                margin: 4px 2px;
            }
        """)

        # Drawing area with enhanced styling
        self.drawing = QtWidgets.QFrame()
        self.drawing.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.drawing.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QGraphicsView {
                border: none;
                background: #ffffff;
            }
            QGraphicsView:focus {
                border: none;
                outline: none;
            }
        """)

        # Enhanced shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QtGui.QColor(0, 0, 0, 40))
        shadow.setOffset(0, 3)
        self.drawing.setGraphicsEffect(shadow)

        # Graphics scene and view setup
        self.scene = QtWidgets.QGraphicsScene()
        self.drawing_layout = QtWidgets.QVBoxLayout(self.drawing)
        self.drawing_layout.setContentsMargins(0, 0, 0, 0)

        # Table area with enhanced styling
        self.table_frame = QtWidgets.QFrame(self.centralwidget)
        self.table_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.table_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QHeaderView {
                background-color: #e0e0e0;
                border: none;
            }
            QHeaderView::section {
                background-color: #e0e0e0;
                color: #585858;
                padding: 8px 8px;
                border: none;
                border-bottom: 2px solid #dde1e6;
                border-right: 1px solid #dde1e6;
                font-family: 'Segoe UI';
                font-weight: 550;
                font-size: 13px;
                text-transform: none;
                letter-spacing: 0.1px;
            }
            QHeaderView::section:first {
                border-top-left-radius: 6px;
            }
            QHeaderView::section:last {
                border-top-right-radius: 6px;
                border-right: none;
            }
            QHeaderView::section:hover {
                background-color: #f1f3f5;
            }
            QHeaderView::section:pressed {
                background-color: #e9ecef;
            }
            QTableWidget {
                background-color: #ffffff;
                border: none;
                border-radius: 6px;
                gridline-color: #f5f5f5;
                selection-background-color: #e3f2fd;
                selection-color: black;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd !important;
                color: black;
            }
            QTableWidget::item:focus {
                background-color: #e3f2fd;
                color: black;
                border: none;
                outline: none;
            }
            QTableWidget::item[valid="true"] {
                background-color: #D1FFBD;
            }
            QTableWidget::item[valid="false"] {
                background-color: #FFB6C1;
            }
            QTableWidget::item[valid="true"]:selected,
            QTableWidget::item[valid="false"]:selected {
                background-color: #e3f2fd !important;
                color: black;
            }
        """)
        table_shadow = QtWidgets.QGraphicsDropShadowEffect()
        table_shadow.setBlurRadius(15)
        table_shadow.setColor(QtGui.QColor(0, 0, 0, 25))
        table_shadow.setOffset(0, 2)
        self.table_frame.setGraphicsEffect(table_shadow)

        # Table layout
        table_layout = QtWidgets.QVBoxLayout(self.table_frame)
        table_layout.setContentsMargins(8, 8, 8, 8)
        table_layout.setSpacing(10)  # Add spacing between widgets

        # Create header widget placeholder - will be populated later
        self.header_placeholder = QtWidgets.QWidget()
        table_layout.addWidget(self.header_placeholder)

        # Create and configure table
        self.dimtable = QtWidgets.QTableWidget(self.table_frame)
        
        # Center align all column headers and content
        class AlignDelegate(QtWidgets.QStyledItemDelegate):
            def initStyleOption(self, option, index):
                super().initStyleOption(option, index)
                option.displayAlignment = Qt.AlignCenter

        delegate = AlignDelegate()
        self.dimtable.setItemDelegate(delegate)

        # Configure table selection behavior
        self.dimtable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)  # Allow multiple row selection
        self.dimtable.setFocusPolicy(Qt.StrongFocus)  # Changed from NoFocus to StrongFocus
        
        # Set row height and header height
        self.dimtable.verticalHeader().setDefaultSectionSize(23)  # For row height
        self.dimtable.horizontalHeader().setFixedHeight(35)  # Adjust this value to make headers shorter
        
        # Add bottom margin to ensure last row is visible
        self.dimtable.setContentsMargins(0, 0, 0, 10)  # Left, Top, Right, Bottom margins
        self.dimtable.setViewportMargins(0, 0, 0, 10)  # Add margin to viewport
        
        # Disable column selection when clicking headers
        header = self.dimtable.horizontalHeader()
        try:
            header.sectionPressed.disconnect()
        except TypeError:
            pass  # No connections to disconnect
        header.setSectionsClickable(False)
        
        # Add style to remove focus rectangle and improve row highlighting
        self.dimtable.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                border: none;
                border-radius: 6px;
                gridline-color: #f5f5f5;
                selection-background-color: #e3f2fd;
                selection-color: #000000;
                outline: none;
            }
            QTableWidget::item {
                border-right: 1px solid #d0d0d0;
                border-bottom: 1px solid #d0d0d0;
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #000000;
            }
            QTableWidget::item[valid="true"] {
                background-color: #D1FFBD;
            }
            QTableWidget::item[valid="false"] {
                background-color: #FFB6C1;
            }
            QTableWidget::item:alternate {
                background-color: #fafafa;
            }
            QTableWidget::item:alternate:selected {
                background-color: #e3f2fd;
                color: #000000;
            }
            QTableWidget::item:selected:active {
                background-color: #e3f2fd;
                color: #000000;
            }
            QTableWidget::item:selected:!active {
                background-color: #e3f2fd;
                color: #000000;
            }
        """)

        # Additional table settings
        self.dimtable.setAlternatingRowColors(True)
        self.dimtable.setShowGrid(False)
        self.dimtable.verticalHeader().setVisible(False)
        
        # Ensure table fills its container width
        self.dimtable.horizontalHeader().setStretchLastSection(True)
        
        # Enable row selection highlighting
        self.dimtable.setStyleSheet(self.dimtable.styleSheet() + """
            QTableWidget::item:selected {
                background-color: #e3f2fd !important;
                color: #000000;
            }
        """)

        # Add table to layout with a spacer below it
        table_layout.addWidget(self.dimtable)
        spacer = QtWidgets.QSpacerItem(20, 15, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)
        table_layout.addItem(spacer)

        # Add toolbar and drawing to container
        drawing_container_layout.addWidget(self.toolBar)
        drawing_container_layout.addWidget(self.drawing)

        # Add container and table to main layout
        main_layout.addWidget(self.drawing_container, stretch=7)
        main_layout.addWidget(self.table_frame, stretch=3)

        # Create and configure loading indicator
        self.loading_indicator = LoadingIndicator(self.drawing)
        self.loading_indicator.setVisible(False)
        self.loading_indicator.setStyleSheet("""
            LoadingIndicator {
                background-color: transparent;
            }
        """)
        self.center_loading_indicator()

    def center_loading_indicator(self):
        """Center the loading indicator in the drawing widget"""
        if hasattr(self, 'loading_indicator') and hasattr(self, 'drawing'):
            drawing_center_x = self.drawing.width() // 2
            drawing_center_y = self.drawing.height() // 2
            indicator_x = drawing_center_x - (self.loading_indicator.width() // 2)
            indicator_y = drawing_center_y - (self.loading_indicator.height() // 2)
            self.loading_indicator.move(indicator_x, indicator_y)

    def createAction(self, name, icon_path=None, text=None, shortcut=None, status_tip=None, triggered=None):
        """Helper method to create QAction with common properties"""
        action = QtWidgets.QAction(self.centralwidget)
        action.setObjectName(f"action{name.replace(' ', '_')}")

        if icon_path:
            icon = QtGui.QIcon()
            icon.addPixmap(
                QtGui.QPixmap(f"D:\\siri\\calipers\\prometrix\\prometrix\\Smart_Metrology_19082024\\{icon_path}"),
                
                QtGui.QIcon.Normal,
                QtGui.QIcon.Off
            )
            action.setIcon(icon)

        if text:
            action.setText(text)
        if shortcut:
            action.setShortcut(shortcut)
        if status_tip:
            action.setStatusTip(status_tip)
        if triggered:
            action.triggered.connect(triggered)

        return action

    def setupMenuBar(self, MainWindow):
        # Create menubar
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1042, 21))
        
        # Update menubar styling with reduced spacing
        self.menubar.setStyleSheet("""
            QMenuBar {
                background-color: #f8f9fa;
                color: #424242;
                border-bottom: 1px solid #e0e0e0;
                spacing: 1px;  /* Reduced from 2px */
            }

            QMenuBar::item {
                background-color: transparent;
                padding: 2px 6px;  /* Reduced from 4px 8px */
                margin: 0px;
                border-radius: 3px;  /* Reduced from 4px */
            }

            QMenuBar::item:selected {
                background-color: #e8f0fe;
            }

            QMenuBar::item:pressed {
                background-color: #d2e3fc;
            }

            QMenu {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 3px;  /* Reduced from 4px */
                padding: 2px;  /* Reduced from 4px */
            }

            QMenu::item {
                background-color: transparent;
                padding: 4px 24px 4px 8px;  /* Reduced from 6px 32px 6px 16px */
                border-radius: 3px;  /* Reduced from 4px */
                margin: 1px 2px;  /* Reduced from 2px 4px */
            }

            QMenu::item:selected {
                background-color: #e8f0fe;
            }

            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 2px 4px;  /* Reduced from 4px 8px */
            }
        """)

        # Define menu structure
        menu_structure = {
            'File': [
                ('New', 'New.png'),
                ('New from CAD', 'New from drawing….png'),
                ('New from Template', 'template open.png'),
                '-',
                ('Open Existing Project', 'Open.png'),
                ('Recently Opened Projects', 'Rec.png'),
                '-',
                ('Save', 'Save.png'),
                ('Save As', 'Save as.png'),
                '-',
                ('Close Project', 'Close project.png'),
                '-',
                ('Logout', 'logout.png'),
                'Exit'
            ],
            'Edit': {
                'Project Settings': [
                    'Tolerance tables',
                    'Labels',
                    'Stamp template'
                ],
                'Settings': [
                    'Characteristics',
                    'Dimension Stamping'
                ]
            },
            'Tools': [
                ('Bluetooth Connectivity', 'bluetooth.png'),
                '-',
                ('Project Overview', 'Project overview.png'),
                ('Characteristics Overview', 'Characteristics overview.png'),
                ('Characteristics Properties', 'Characteristics Properties.png'),
                ('Reset Window layout', 'Tool_Bar/Display Whole Drawing.png')
            ],
            'Help': [
                ('Online Manual', 'Online manual.png'),
                ('Show License', 'License.png'),
                'Diagnosis',
                'About'
            ]
        }
        
        # Create menus and actions
        self.actions = {}
        self.menus = {}

        for menu_name, items in menu_structure.items():
            menu = QtWidgets.QMenu(self.menubar)
            menu.setObjectName(f"menu{menu_name.replace(' ', '_')}")
            menu.setTitle(menu_name)
            self.menubar.addMenu(menu)
            self.menus[menu_name] = menu

            if isinstance(items, dict):
                for submenu_name, submenu_items in items.items():
                    submenu = menu.addMenu(submenu_name)
                    for item in submenu_items:
                        action = self.createAction(item, text=item)
                        submenu.addAction(action)
                        self.actions[item] = action
            else:
                for item in items:
                    if item == '-':
                        menu.addSeparator()
                    else:
                        if isinstance(item, tuple):
                            name, icon = item
                            action = self.createAction(name, icon, text=name)
                        else:
                            action = self.createAction(item, text=item)
                        menu.addAction(action)
                        self.actions[item if isinstance(item, str) else item[0]] = action

        MainWindow.setMenuBar(self.menubar)

    def setupToolBar(self, MainWindow):
        # Define toolbar groups with their items
        toolbar_groups = [
            # File operations group
            [
                ('NewProject', 'Tool_Bar/Create_new_Project.png', "New Project"),
                ('Open', 'Open.png', "Open"),
                ('Save', 'Save.png', "Save"),
            ],
            # View group
            [
                ('ProjectOverview', 'Project overview.png', "Project Overview"),
                ('CharacteristicsOverview', 'Characteristics overview.png', "Characteristics Overview"),
                ('CharacteristicsProperties', 'Characteristics Properties.png', "Properties"),
            ],
            # Tools group
            [
                ('SelectionTool', 'Tool_Bar/Selection tool.png', "Selection Tool"),
                ('Stamp', 'Tool_Bar/Stamp tool.png', "Stamp Tool"),
                #('Tag', 'Tool_Bar/Tag tool.png', "Tag Tool"),
                ('FieldDivision', 'Tool_Bar/Define_Field_Division.png', "Field Division"),
            ],
            # Visibility group
            [
                ('HideStamp', 'Tool_Bar/Hide stamp.png', "Hide Stamp"),
            ],
            # Navigation group
            [
                ('MoveView', 'Tool_Bar/Move View.png', "Move View"),
                ('ZoomIn', 'Tool_Bar/Zoom in.png', "Zoom In"),
                ('ZoomOut', 'Tool_Bar/Zoom out.png', "Zoom Out"),
                ('ZoomDynamic', 'Tool_Bar/Zoom Dynamically.png', "Dynamic Zoom"),
                ('ZoomArea', 'Tool_Bar/Zoom Tool Area.png', "Zoom Area"),
                ('DisplayWholeDrawing', 'Tool_Bar/Display Whole Drawing.png', "Fit to View"),
            ]
        ]

        # Add toolbar items with groups
        for group in toolbar_groups:
            # Add items in the group
            for item in group:
                name, icon, tooltip = item
                action = self.createAction(name, icon, text="")  # Remove text from button
                action.setToolTip(tooltip)  # Add tooltip instead
                self.toolBar.addAction(action)
                setattr(self, f'action{name}', action)
            
            # Add separator after each group (except the last one)
            if group != toolbar_groups[-1]:
                self.toolBar.addSeparator()

        # Make toolbar non-movable and non-floatable
        self.toolBar.setMovable(False)
        self.toolBar.setFloatable(False)

    def setupStatusBar(self, MainWindow):
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setStyleSheet("""
            QStatusBar {
                background-color: #fafafa;
                color: #757575;
                border-top: 1px solid #e0e0e0;
                padding: 3px;
                font-size: 11px;
            }
            QStatusBar::item {
                border: none;
                border-right: 1px solid #e0e0e0;
                padding: 2px 6px;
            }
        """)
        MainWindow.setStatusBar(self.statusbar)

    def connectSignals(self):
        """Connect signals to slots"""
        if 'Exit' in self.actions:
            self.actions['Exit'].triggered.connect(QtWidgets.qApp.quit)

    def retranslateUi(self, MainWindow):
        """Set up all the UI text elements"""
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Quality Management Tool"))
        self.menus['File'].setTitle(_translate("MainWindow", "File"))
        self.menus['Edit'].setTitle(_translate("MainWindow", "Edit"))
        self.menus['Tools'].setTitle(_translate("MainWindow", "Tools"))
        self.menus['Help'].setTitle(_translate("MainWindow", "Help"))
        self.toolBar.setWindowTitle(_translate("MainWindow", "Tools")) 

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        
        # Ensure window opens maximized
        self.showMaximized()
        
    def showEvent(self, event):
        super().showEvent(event)
        # Ensure window is maximized when shown
        self.setWindowState(Qt.WindowMaximized)