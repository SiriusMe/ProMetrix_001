import math
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtGui import QMovie, QPolygonF, QImage, QPixmap
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QGraphicsView, QMessageBox, QDialog, QTableWidgetItem, \
    QGraphicsPolygonItem, QMenu, QWidget, QHBoxLayout, QLabel, QSpinBox
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPen, QColor
from PyQt5.QtWidgets import QGraphicsRectItem
import fitz  # PyMuPDF
import cv2
import os

from ultralytics import YOLO
from ui_smart_metrology import Ui_MainWindow
from dialogs import DimensionDialog, PDFPreviewDialog, PartNumberDialog, LoginDialog, OperationsDialog, MeasurementInstrumentDialog, BluetoothDialog, ReportFolderDialog
import re
from events import EventHandler, ViewEvents, TableEvents, VisualizationEvents
from graphics import CustomGraphicsView
from algorithms import DimensionParser, ImageProcessor, BoundingBoxUtils, ClusterDetector, OCRProcessor,ZoneDetector
import requests
from PyQt5.QtWidgets import QGraphicsPolygonItem, QGraphicsPathItem, QGraphicsTextItem, QGraphicsEllipseItem
from api_endpoints import APIEndpoints, api
import json
import asyncio
from bleak import BleakClient
import tempfile
import uuid
from PyQt5 import QtPrintSupport

class PDFProcessStatus:
    PREPARING = "Preparing document..."
    OPENING = "Opening document..."
    LOADING = "Loading page..."
    PROCESSING = "Processing page..."
    FINALIZING = "Finalizing..."

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.ocr_results = []
        self.worker = None
        self.loaded_page = None
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.user_role = None  # Store user role

        # Add header widget for order details
        self.setup_header_widget()

        # Create and set the CustomGraphicsView
        self.ui.pdf_view = CustomGraphicsView(self.ui.scene, self)
        self.ui.drawing_layout.addWidget(self.ui.pdf_view)

        # Connect stamp tool action
        self.ui.actionStamp.triggered.connect(self.toggleStampMode)

        # Connect Bluetooth action
        if 'Bluetooth Connectivity' in self.ui.actions:
            self.ui.actions['Bluetooth Connectivity'].triggered.connect(self.show_bluetooth_dialog)

        # Initialize loading timer
        self.loading_timer = QtCore.QTimer(self)
        self.loading_timer.timeout.connect(self.update_loading_animation)

        # Create progress bar in the drawing widget
        self.progress_bar = QtWidgets.QProgressBar(self.ui.drawing)
        self.progress_bar.setFixedSize(self.ui.drawing.width(), 2)  # Make it thin
        self.progress_bar.move(0, 0)  # Position at top

        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #F0F0F0;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0078D4;  /* Windows blue */
                width: 20px;
            }
        """)

        # Set up loading animation properties
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)

        # Initialize resize mode variables
        self.resize_mode = False
        self.resize_handles = []
        self.original_bbox = None
        self.original_bbox_item = None
        self.editing_row = None
        self.finish_button = None

        # Initialize animation position
        self.animation_position = 0
        self.animation_direction = 1
        self.loading_timer.setInterval(20)  # Faster animation

        # Add method to center progress bar when drawing widget is resized
        self.ui.drawing.resizeEvent = self.on_drawing_resize

        # Initialize variables
        self.current_pdf = None
        self.current_page = None
        self.zoom_factor = 1.0
        self.zoom_step = 1.15
        self.rotation = 0
        self.current_file = None
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.masked_image = None
        #self.reader = None
        self.pdf_results = None
        self.bbox_data = {'ocr': [], 'yolo': []}  # Dictionary to store bbox data

        # Initialize YOLO model
        try:
            self.yolo_model = YOLO(r'D:\siri\calipers\prometrix\prometrix\best.pt')
        except Exception as e:
            print(f"Error loading YOLO model: {str(e)}")
            self.yolo_model = None

        # Set the main window reference
        self.ui.pdf_view.main_window = self

        # Connect signals
        self.ui.actionNewProject.triggered.connect(self.open_pdf)
        self.ui.actionZoomIn.triggered.connect(lambda: self.zoom_in(use_mouse_position=False))
        self.ui.actionZoomOut.triggered.connect(lambda: self.zoom_out(use_mouse_position=False))
        self.ui.actionDisplayWholeDrawing.triggered.connect(self.fit_to_view)
        self.ui.actionSelectionTool.triggered.connect(self.toggleSelectionMode)
        self.ui.actionOpen.triggered.connect(self.open_part_number)

        # Setup graphics view
        self.setup_view()

        # Add new dictionaries for storing detections
        self.all_detections = {
            'ocr': {
                0: [],  # Original orientation
                90: [],  # 90 degree rotation
            },
            'yolo': []  # YOLO detections
        }

        # Connect view control actions
        self.ui.actionMoveView.triggered.connect(self.toggleMoveMode)
        self.ui.actionZoomIn.triggered.connect(lambda: self.zoom_in(use_mouse_position=False))
        self.ui.actionZoomOut.triggered.connect(lambda: self.zoom_out(use_mouse_position=False))
        self.ui.actionZoomDynamic.triggered.connect(self.toggleDynamicZoom)
        self.ui.actionZoomArea.triggered.connect(self.toggleZoomArea)
        self.ui.actionDisplayWholeDrawing.triggered.connect(self.fit_to_view)

        self.ui.actionNewProject.setEnabled(False)

        # Connect the Properties action
        self.ui.actionCharacteristicsProperties.triggered.connect(self.toggleCharacteristicsProperties)
        self.properties_mode_active = False
        self.properties_cursor = QtGui.QCursor(QtCore.Qt.PointingHandCursor)


        # Connect the HideStamp action
        self.ui.actionHideStamp.triggered.connect(self.toggleBalloonVisibility)
        self.balloons_hidden = False  # Track balloon visibility state

         # Connect the FieldDivision action
        self.ui.actionFieldDivision.triggered.connect(self.toggleFieldDivision)
        self.grid_visible = False  # Track grid visibility state

        self.ui.actionCharacteristicsOverview.triggered.connect(self.toggleCharacteristicsOverview)
        self.overview_mode_active = False  # Track grid visibility state

        self.ui.actionProjectOverview.triggered.connect(self.show_project_overview)

        # Update the table context menu connection
        self.ui.dimtable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.dimtable.customContextMenuRequested.connect(self.show_table_context_menu)

        # Ensure window opens maximized
        self.showMaximized()

        # Connect save action
        self.ui.actionSave.triggered.connect(self.save_to_database)

        # Connect logout action
        self.ui.actions['Logout'].triggered.connect(self.logout)

        # Initialize attributes
        self.current_order_details = {}

        # Add these attributes to store the current image
        self.current_image = None
        self.vertical_lines = None
        self.horizontal_lines = None

        # Connect cell changed signal to enable manual measurement entry
        self.ui.dimtable.cellChanged.connect(self.handle_cell_change)

        # Set table style to ensure proper display
        self.ui.dimtable.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                color: black;
                background-color: transparent;
            }
        """)

    def setup_header_widget(self):
        """Setup header widget to display order details"""
        # Create header widget
        self.header_widget = QtWidgets.QWidget()
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: transparent;
                border: none;
            }
            QLabel {
                background-color: transparent;
                border: none;
            }
            QLabel[class="label"] {
                color: #666666;
                font-size: 13px;
                padding-right: 5px;
                background: none;
            }
            QLabel[class="value"] {
                color: #1976d2;
                font-weight: bold;
                font-size: 13px;
                background: none;
            }
            QFrame#separator {
                color: #e0e0e0;
                background: none;
            }
        """)

        # Create layout with no margins
        header_layout = QtWidgets.QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 5, 0, 5)  # Reduced left/right margins to 0
        header_layout.setSpacing(15)

        # Create info sections with label: value format
        sections = [
            ('Part Number', 'part_number'),
            ('Production Order', 'production_order'),
            ('Required Qty', 'required_quantity')
        ]

        self.header_labels = {}

        for i, (label_text, key) in enumerate(sections):
            # Create horizontal layout for each section
            section_layout = QtWidgets.QHBoxLayout()
            section_layout.setSpacing(5)
            section_layout.setContentsMargins(0, 0, 0, 0)  # No margins

            # Add label
            label = QtWidgets.QLabel(f"{label_text}:")
            label.setProperty('class', 'label')
            section_layout.addWidget(label)

            # Add value
            value = QtWidgets.QLabel("-")
            value.setProperty('class', 'value')
            section_layout.addWidget(value)

            # Store reference to value label
            self.header_labels[key] = value

            # Add to main layout
            header_layout.addLayout(section_layout)

            # Add separator after each section except the last
            if i < len(sections) - 1:
                separator = QtWidgets.QFrame()
                separator.setFrameShape(QtWidgets.QFrame.VLine)
                separator.setObjectName("separator")
                separator.setStyleSheet("QFrame { color: #e0e0e0; background: none; }")
                header_layout.addWidget(separator)

        header_layout.addStretch()

        # Add header widget to table frame
        if hasattr(self.ui, 'header_placeholder'):
            self.ui.header_placeholder.setParent(None)
            table_layout = self.ui.table_frame.layout()
            table_layout.insertWidget(0, self.header_widget)

    def update_order_details(self, part_number: str):
        """Update header with order details"""
        try:
            # Get order details from API
            details = api.get_order_details(part_number)

            if details:
                # Update labels
                self.header_labels['part_number'].setText(details['part_number'])
                self.header_labels['production_order'].setText(details['production_order'])
                self.header_labels['required_quantity'].setText(str(details['required_quantity']))

                # Store order details
                self.current_order_details = details
            else:
                # Clear labels if no details found
                for label in self.header_labels.values():
                    label.setText("-")

        except Exception as e:
            print(f"Error updating order details: {str(e)}")
            # Clear labels on error
            for label in self.header_labels.values():
                label.setText("-")

    def center_progress_bar(self):
        """Center the progress bar in the drawing widget"""
        if self.progress_bar and self.ui.drawing:
            # Calculate center position
            drawing_center_x = self.ui.drawing.width() // 2
            drawing_center_y = self.ui.drawing.height() // 2
            progress_bar_x = drawing_center_x - (self.progress_bar.width() // 2)
            progress_bar_y = drawing_center_y - (self.progress_bar.height() // 2)

            # Move progress bar to center
            self.progress_bar.move(progress_bar_x, progress_bar_y)

    def on_drawing_resize(self, event):
        """Handle drawing widget resize events"""
        # Center the progress bar when the drawing widget is resized
        self.center_progress_bar()
        # Call the original resize event if it exists
        if hasattr(self.ui.drawing, 'original_resize_event'):
            self.ui.drawing.original_resize_event(event)

    def setup_view(self):
        """Setup the graphics view with optimal settings"""
        self.ui.pdf_view.setRenderHints(
            QtGui.QPainter.Antialiasing |
            QtGui.QPainter.SmoothPixmapTransform |
            QtGui.QPainter.TextAntialiasing |
            QtGui.QPainter.HighQualityAntialiasing
        )
        self.ui.pdf_view.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.ui.pdf_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pdf_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.ui.pdf_view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.ui.pdf_view.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.ui.dimtable.cellClicked.connect(self.highlight_bbox)

    def find_innermost_boundary(self, image):
        """
        Find the innermost boundary rectangle that contains the main technical drawing
        """
        return ImageProcessor.find_innermost_boundary(image)

    def process_pdf_page(self, page):
        """Process PDF page with text extraction and YOLO detection"""
        try:
            # Create rotation matrix based on selected rotation
            rotation_matrix = fitz.Matrix(300 / 72, 300 / 72).prerotate(self.rotation)

            # Get pixmap with selected rotation
            pix = page.get_pixmap(matrix=rotation_matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

            # Store the original rotated image
            processed_img = img.copy()

            # Get text using PyMuPDF
            fitz_dict = page.get_text("dict")['blocks']
            pdf_results = []

            # Process text blocks
            for block in fitz_dict:
                if 'lines' in block:
                    for line in block['lines']:
                        for span in line['spans']:
                            dimension = span['text'].strip()
                            if not dimension:  # Skip empty text
                                continue
                            bound_box = span['bbox']
                            # Scale coordinates
                            bound_box = [i * 2 for i in bound_box]
                            # Convert to our standard format
                            scene_box = [
                                [bound_box[0], bound_box[1]],  # top-left
                                [bound_box[2], bound_box[1]],  # top-right
                                [bound_box[2], bound_box[3]],  # bottom-right
                                [bound_box[0], bound_box[3]]  # bottom-left
                            ]
                            pdf_results.append({
                                'text': dimension,
                                'box': scene_box,
                                'confidence': 1.0,  # PyMuPDF doesn't provide confidence
                                'rotation': 0
                            })

            # Store results
            self.all_detections['ocr'][0] = pdf_results
            self.ocr_results = pdf_results

            # Process YOLO if model exists
            if self.yolo_model:
                marked_image = img.copy()
                mask, _ = self.find_innermost_boundary(img)
                if mask is not None:
                    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                    cv2.drawContours(marked_image, contours, -1, (0, 255, 0), 2)

                    detections = self.yolo_model(marked_image)[0]
                    yolo_results = [
                        {
                            'box': [int(x1), int(y1), int(x2), int(y2)],
                            'confidence': float(conf),
                            'class': int(cls),
                            'class_name': detections.names[int(cls)]
                        }
                        for x1, y1, x2, y2, conf, cls in detections.boxes.data
                        if conf >= 0.75
                    ]

                    self.all_detections['yolo'] = yolo_results
                    self.yolo_detections = yolo_results
                    processed_img = marked_image

            return self.convert_to_pixmap(processed_img)

        except Exception as e:
            print(f"Error in process_pdf_page: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def is_valid_detection(self, result):
        """Check if the detection is valid based on box dimensions and position"""
        try:
            box = result['box']
            # Get box dimensions
            x_coords = [p[0] for p in box]
            y_coords = [p[1] for p in box]
            width = max(x_coords) - min(x_coords)
            height = max(y_coords) - min(y_coords)

            # Skip if box dimensions are invalid
            if width <= 0 or height <= 0:
                return False

            # Skip if box is too small
            if width < 5 or height < 5:
                return False

            # Skip if box is outside image bounds
            if min(x_coords) < 0 or min(y_coords) < 0:
                return False

            return True
        except:
            return False

    def populate_and_parse_ocr_results(self, results, rotation=0):
        """Process OCR results and populate the table"""
        return OCRProcessor.populate_and_parse_ocr_results(self, results, rotation)

    # def process_image(self, img, rotation):
    #     """Process single image for OCR and YOLO detection"""
    #     try:
    #         mask, _ = self.find_innermost_boundary(img)
    #         if mask is None or not mask.any():
    #             return None
    #
    #         # Prepare image for OCR
    #         enhanced = self.enhance_image(img)
    #         masked = cv2.bitwise_and(enhanced, enhanced, mask=mask)
    #
    #         # Initialize OCR if needed
    #         if self.reader is None:
    #             self.reader = easyocr.Reader(['en'])
    #
    #         # Get OCR results
    #         ocr_results = [
    #             {
    #                 'box': box,
    #                 'text': text,
    #                 'confidence': conf,
    #                 'rotation': rotation
    #             }
    #             for box, text, conf in self.reader.readtext(masked)
    #             if conf >= 0.70
    #         ]
    #
    #         # Process YOLO if this is the selected rotation
    #         yolo_results = []
    #         if rotation == self.rotation and self.yolo_model:
    #             marked_image = img.copy()
    #             contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    #             cv2.drawContours(marked_image, contours, -1, (0, 255, 0), 2)
    #
    #             detections = self.yolo_model(marked_image)[0]
    #             yolo_results = [
    #                 {
    #                     'box': [int(x1), int(y1), int(x2), int(y2)],
    #                     'confidence': float(conf),
    #                     'class': int(cls),
    #                     'class_name': detections.names[int(cls)]
    #                 }
    #                 for x1, y1, x2, y2, conf, cls in detections.boxes.data
    #                 if conf >= 0.75
    #             ]
    #
    #             return {
    #                 'ocr': ocr_results,
    #                 'yolo': yolo_results,
    #                 'image': marked_image
    #             }
    #
    #         return {'ocr': ocr_results}
    #
    #     except Exception as e:
    #         print(f"Error processing image: {str(e)}")
    #         return None

    def convert_to_pixmap(self, img):
        """Convert numpy image to QPixmap"""
        if img is None:
            return None

        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 else img
        height, width = rgb_img.shape[:2]
        bytes_per_line = 3 * width

        qimage = QtGui.QImage(
            rgb_img.tobytes(),
            width,
            height,
            bytes_per_line,
            QtGui.QImage.Format_RGB888
        )
        return QtGui.QPixmap.fromImage(qimage)

    def get_best_ocr_results(self):
        """Get the OCR results with the highest confidence across all rotations"""
        all_results = []
        for rotation, results in self.all_detections['ocr'].items():
            for result in results:
                result['rotation'] = rotation
                all_results.append(result)

        # Sort by confidence
        all_results.sort(key=lambda x: x['confidence'], reverse=True)

        # Remove duplicates (keep highest confidence)
        seen_texts = set()
        best_results = []
        for result in all_results:
            text = result['text'].strip().lower()
            if text not in seen_texts:
                seen_texts.add(text)
                best_results.append(result)

        return best_results

    def add_to_table_and_scene(self, text, bbox, scene_box=None, is_selection=False):
        """Add detected text and bbox to table and scene"""
        return VisualizationEvents.add_to_table_and_scene(self, text, bbox, scene_box, is_selection)

    def highlight_bbox(self, row, column):
        """Highlight the selected bounding box and create a balloon with row number"""
        try:
            # Get the bbox data from the table
            item = self.ui.dimtable.item(row, 2)  # Nominal column
            if not item:
                return

            bbox = item.data(Qt.UserRole)
            if not bbox:
                return

            # Use the CustomGraphicsView's highlight_bbox method
            self.ui.pdf_view.highlight_bbox(bbox, row + 1)

        except Exception as e:
            print(f"Error highlighting bbox: {str(e)}")

    def is_dimensional_value(self, text):
        return DimensionParser.is_dimensional_value(text)

    def determine_dimension_type(self, text, nominal_value):
        """Determine the dimension type based on the text and nominal value"""
        return DimensionParser.determine_dimension_type(text, nominal_value)

    def parse_dimension(self, text):
        return DimensionParser.parse_dimension(text)

    def enhance_image(self, image):
        return ImageProcessor.enhance_image(image)

    def open_pdf(self, file_path=None):
        """Open and process PDF file"""
        try:
            # Show file dialog if no file path provided
            if file_path is None:
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Open PDF", "", "PDF files (*.pdf)"
                )

            if file_path:
                # Show preview dialog only for manual file opening
                if file_path is None:
                    preview_dialog = PDFPreviewDialog(file_path, self)
                    if preview_dialog.exec_() == QDialog.Accepted:
                        page_number = preview_dialog.get_selected_page()
                        rotation = preview_dialog.get_rotation()
                        self.process_pdf(file_path, page_number, rotation)
                else:
                    # For files from operations dialog, process directly
                    self.process_pdf(file_path, self.current_page, self.rotation)

        except Exception as e:
            print(f"Error opening PDF: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {str(e)}")

    def process_pdf(self, file_path, page_number, rotation):
        """Process PDF file with given parameters"""
        try:
            # Open the PDF document
            doc = fitz.open(file_path)
            self.loaded_page = doc.load_page(0)
            # Load the specified page
            self.current_page = doc[page_number]
            self.rotation = rotation

            # Apply rotation if needed
            if rotation:
                self.current_page.set_rotation(rotation)

            # Get the page pixmap
            pix = self.current_page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)

            # Clear existing scene and add new pixmap
            self.ui.pdf_view.scene().clear()
            self.ui.pdf_view.scene().addPixmap(pixmap)
            self.ui.pdf_view.setSceneRect(QRectF(pixmap.rect()))

            # For admin users, process the page with OCR/YOLO
            if self.user_role == 'admin':
                # Disable selection tool until OCR is complete
                self.ui.actionSelectionTool.setEnabled(False)
                self.process_page()

            # Fit view to content - do this for both admin and operator
            self.ui.pdf_view.fitInView(self.ui.pdf_view.sceneRect(), Qt.KeepAspectRatio)
            self.zoom_factor = 1.0  # Reset zoom factor after fitting

        except Exception as e:
            print(f"Error processing PDF: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to process PDF: {str(e)}")

    class PDFWorker(QtCore.QThread):
        """Worker thread for processing PDF files"""
        finished = QtCore.pyqtSignal()
        error = QtCore.pyqtSignal(str)
        progress_update = QtCore.pyqtSignal(str)  # Signal to update progress from worker thread

        def __init__(self, main_window, loading_params):
            super().__init__()
            self.main_window = main_window
            self.loading_params = loading_params

        def run(self):
            try:
                # Execute the processing steps without UI updates
                self.progress_update.emit(PDFProcessStatus.PREPARING)
                if not self.main_window.prepare_document():
                    raise Exception("Failed to prepare document")

                self.progress_update.emit(PDFProcessStatus.OPENING)
                if not self.main_window.open_document():
                    raise Exception("Failed to open document")

                self.progress_update.emit(PDFProcessStatus.LOADING)
                if not self.main_window.load_page():
                    raise Exception("Failed to load page")

                self.progress_update.emit(PDFProcessStatus.PROCESSING)
                if not self.main_window.process_page():
                    raise Exception("Failed to process page")

                self.progress_update.emit(PDFProcessStatus.FINALIZING)
                if not self.main_window.finalize_loading():
                    raise Exception("Failed to finalize")

                self.finished.emit()
            except Exception as e:
                self.error.emit(str(e))

    def start_loading_process(self):
        """Handle the PDF loading process with loading animation in a separate thread"""
        try:
            # Initialize loading UI with infinite progress
            self.start_loading()

            # Create and start worker thread
            self.worker = self.PDFWorker(self, self.loading_params)
            self.worker.finished.connect(self._on_pdf_processing_finished)
            self.worker.error.connect(self._on_pdf_processing_error)
            self.worker.progress_update.connect(self._on_progress_update)
            self.worker.start()

        except Exception as e:
            self.stop_loading()
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to start PDF processing: {str(e)}"
            )

    def _on_pdf_processing_finished(self):
        """Handle completion of PDF processing"""
        self.stop_loading()
        self.worker.deleteLater()

    def _on_pdf_processing_error(self, error_message):
        """Handle errors in PDF processing"""
        self.stop_loading()
        self.worker.deleteLater()
        QtWidgets.QMessageBox.critical(
            self,
            "Error",
            f"Failed to load PDF: {error_message}"
        )

    def _on_progress_update(self, message):
        """Update progress message from worker thread"""
        if hasattr(self, 'loading_label'):
            self.loading_label.setText(message)

    def prepare_document(self):
        """Step 1: Prepare for document loading"""
        try:
            self.reset_dimension_table()
            self.ui.pdf_view.clearYOLODetections()
            return True
        except Exception as e:
            print(f"Error in prepare_document: {str(e)}")
            return False

    def open_document(self):
        """Step 2: Open the PDF document"""
        try:
            self.current_pdf = fitz.open(self.loading_params['file_path'])
            self.current_file = self.loading_params['file_path']
            return True
        except Exception as e:
            print(f"Error in open_document: {str(e)}")
            return False

    def load_page(self):
        """Step 3: Load the selected page"""
        try:
            if self.current_pdf:
                self.current_page = self.current_pdf[self.loading_params['selected_page']]
                self.rotation = self.loading_params['rotation']
                return True
            return False
        except Exception as e:
            print(f"Error in load_page: {str(e)}")
            return False

    def process_page(self):
        """Process the current page with OCR and YOLO"""
        try:
            # Get pixmap of current page
            pix = self.current_page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

            # Initialize empty results
            self.pdf_results = []
            self.all_detections = {'yolo': []}

            # Enable selection tool for admin
            if self.user_role == 'admin':
                self.ui.actionSelectionTool.setEnabled(True)

            # Fit view to content
            self.ui.pdf_view.fitInView(self.ui.pdf_view.sceneRect(), Qt.KeepAspectRatio)
            self.zoom_factor = 1.0

            return True

        except Exception as e:
            print(f"Error processing page: {str(e)}")
            return False

    def finalize_loading(self):
        """Step 5: Finalize the loading process"""
        try:
            # Clean up loading parameters
            self.loading_params = None
            return True
        except Exception as e:
            print(f"Error in finalize_loading: {str(e)}")
            return False

    def start_loading(self):
        """Start the loading animation with circular progress indicator"""
        # Center the loading indicator
        self.ui.center_loading_indicator()

        self.ui.loading_indicator.setVisible(True)
        self.ui.loading_indicator.raise_()

        # Create rotation animation
        self.loading_animation = QtCore.QPropertyAnimation(self.ui.loading_indicator, b"angle")
        self.loading_animation.setStartValue(0)
        self.loading_animation.setEndValue(360)
        self.loading_animation.setDuration(1000)  # 1 second per rotation
        self.loading_animation.setLoopCount(-1)  # Infinite loop

        # Set curve shape for smooth continuous rotation
        self.loading_animation.setEasingCurve(QtCore.QEasingCurve.Linear)

        # Connect finished signal to restart animation
        self.loading_animation.finished.connect(self.restart_loading_animation)

        self.loading_animation.start()

    def restart_loading_animation(self):
        """Restart the loading animation to create continuous rotation"""
        if self.ui.loading_indicator.isVisible():
            self.loading_animation.setCurrentTime(0)
            self.loading_animation.start()

    def stop_loading(self):
        """Stop the loading animation"""
        if hasattr(self, 'loading_animation'):
            self.loading_animation.stop()
        if hasattr(self.ui, 'loading_indicator'):
            self.ui.loading_indicator.setVisible(False)

    def update_loading_animation(self, angle):
        """Update the circular loading animation"""
        if hasattr(self.ui, 'loading_indicator') and self.ui.loading_indicator.isVisible():
            self.ui.loading_indicator.setAngle(angle)

    def reset_dimension_table(self):
        """Clear all rows in the dimension table and clean up graphics items."""
        # Clear table rows
        self.ui.dimtable.setRowCount(0)

        # Clear any existing highlights
        self.clear_highlighted_bbox()

        # Clear all OCR items including balloons
        self.ui.pdf_view.clearOCRItems()

        # Reset all balloon-related attributes
        self.current_highlight = None
        self.balloon_circle = None
        self.balloon_triangle = None
        self.balloon_text = None

    def render_page(self):
        """Render the current page with masking, OCR and YOLO detection overlay"""
        if not self.current_page:
            return

        try:
            # Process the page with masking and get QPixmap
            pixmap = self.process_pdf_page(self.current_page)

            # Add to scene
            self.ui.scene.clear()
            self.ui.pdf_view.clearOCRItems()  # Clear previous items
            pixmap_item = self.ui.scene.addPixmap(pixmap)

            # Skip drawing individual OCR and YOLO boxes - they'll be handled by cluster_detections

            # Call cluster_detections to create merged boxes
            self.cluster_detections()

            # Adjust view if needed
            if self.zoom_factor == 1.0:
                self.fit_to_view()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Render Error",
                f"Failed to render PDF page: {str(e)}"
            )

    def zoom_in(self, use_mouse_position=False, mouse_pos=None):
        self.zoom_factor = ViewEvents.zoom_in(
            self.ui.pdf_view,
            self.zoom_factor,
            self.max_zoom,
            self.zoom_step,
            use_mouse_position,
            mouse_pos
        )

    def zoom_out(self, use_mouse_position=False, mouse_pos=None):
        self.zoom_factor = ViewEvents.zoom_out(
            self.ui.pdf_view,
            self.zoom_factor,
            self.min_zoom,
            self.zoom_step,
            use_mouse_position,
            mouse_pos
        )

    def fit_to_view(self):
        self.zoom_factor = ViewEvents.fit_to_view(self.ui.pdf_view, self.ui.scene)

    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)
        # Update table column widths if operator is logged in
        if hasattr(self, 'user_role') and self.user_role == 'operator':
            self.setupCentralWidget()

    def toggleStampMode(self):
        """Toggle stamp tool mode"""
        if self.user_role != 'admin':
            QMessageBox.warning(self, "Access Denied",
                              "Only administrators can use the stamp tool.")
            return

        if hasattr(self.ui, 'pdf_view'):
            self.ui.pdf_view.stamp_mode = not self.ui.pdf_view.stamp_mode
            self.ui.pdf_view.selection_mode = False
            self.ui.actionSelectionTool.setChecked(False)

    def toggleSelectionMode(self):
        """Toggle selection mode for OCR/YOLO detection"""
        if self.user_role != 'admin':
            QMessageBox.warning(self, "Access Denied",
                              "Only administrators can use the selection tool.")
            # Uncheck the action button if it was checked
            self.ui.actionSelectionTool.setChecked(False)
            return

        if self.ui.pdf_view.selection_mode:
            self.ui.pdf_view.exitSelectionMode()
            self.ui.actionSelectionTool.setChecked(False)
        else:
            self.ui.pdf_view.enterSelectionMode()
            self.ui.actionSelectionTool.setChecked(True)
            # Disable stamp mode when entering selection mode
            self.ui.pdf_view.stamp_mode = False
            self.ui.actionStamp.setChecked(False)

    def show_table_context_menu(self, position):
        """Show context menu for table rows"""
        menu = QMenu()

        # Get selected rows
        selected_rows = set(item.row() for item in self.ui.dimtable.selectedItems())

        if self.user_role == 'admin':
            # Admin menu options
            delete_action = menu.addAction("Delete Row")
            set_instrument_action = menu.addAction("Set Measurement Instrument")

            if selected_rows:  # Valid selection
                action = menu.exec_(self.ui.dimtable.viewport().mapToGlobal(position))
                if action == delete_action:
                    for row in sorted(selected_rows, reverse=True):
                        TableEvents.delete_table_row_and_bbox(self, row)
                elif action == set_instrument_action:
                    self.set_measurement_instrument(selected_rows)
        else:
            # Operator menu options
            filter_action = menu.addAction("Filter by Instrument")
            clear_filter_action = menu.addAction("Clear Filter")
            menu.addSeparator()
            connect_device_action = menu.addAction("Connect to Device")

            action = menu.exec_(self.ui.dimtable.viewport().mapToGlobal(position))
            if action == filter_action:
                self.filter_by_instrument()
            elif action == clear_filter_action:
                self.clear_instrument_filter()
            elif action == connect_device_action:
                if selected_rows:  # If there's a selected row
                    row = list(selected_rows)[0]  # Get the first selected row
                    self.connect_to_device(row)

    def filter_by_instrument(self):
        """Show dialog to filter table by instrument"""
        dialog = MeasurementInstrumentDialog(self, allow_multiple=True, is_admin=self.user_role == 'admin')  # Allow multiple selection
        if dialog.exec_() == QDialog.Accepted:
            instruments = dialog.get_selected_instrument()
            if instruments:
                # Hide rows that don't match any of the selected instruments
                for row in range(self.ui.dimtable.rowCount()):
                    instrument_item = self.ui.dimtable.item(row, 6)  # Instrument column
                    instrument_text = instrument_item.text() if instrument_item else ""
                    self.ui.dimtable.setRowHidden(row, instrument_text not in instruments)

                # Update status bar
                visible_rows = sum(1 for row in range(self.ui.dimtable.rowCount())
                                 if not self.ui.dimtable.isRowHidden(row))
                instruments_str = ", ".join(instruments)
                self.statusBar().showMessage(f"Showing {visible_rows} rows for {instruments_str}")

    def clear_instrument_filter(self):
        """Clear the instrument filter and show all rows"""
        for row in range(self.ui.dimtable.rowCount()):
            self.ui.dimtable.setRowHidden(row, False)
        self.statusBar().showMessage("Showing all rows")

    def set_measurement_instrument(self, rows):
        """Set measurement instrument for selected rows"""
        dialog = MeasurementInstrumentDialog(self, is_admin=self.user_role == 'admin')
        if dialog.exec_() == QDialog.Accepted:
            instrument = dialog.get_selected_instrument()
            if instrument:
                # Apply the selected instrument to all selected rows
                for row in rows:
                    item = QTableWidgetItem(instrument)
                    item.setTextAlignment(Qt.AlignCenter)
                    self.ui.dimtable.setItem(row, 6, item)  # Column 6 is Measurement Instrument

    def delete_table_row_and_bbox(self, row):
        """Delete the table row and its corresponding bbox"""
        TableEvents.delete_table_row_and_bbox(self, row)

    def toggleMoveMode(self):
        ViewEvents.toggle_move_mode(self.ui.pdf_view, self.ui.actionMoveView)

    def toggleDynamicZoom(self):
        ViewEvents.toggle_dynamic_zoom(self.ui.pdf_view, self.ui.actionZoomDynamic)

    def toggleZoomArea(self):
        ViewEvents.toggle_zoom_area(self.ui.pdf_view, self.ui.actionZoomArea)

    def cluster_detections(self):
        """Cluster OCR and YOLO detections based on proximity"""
        pdf_results = self.pdf_results if hasattr(self, 'pdf_results') else []
        yolo_detections = self.all_detections.get('yolo', [])
        ClusterDetector.cluster_detections(self, pdf_results, yolo_detections, DimensionParser)
        # print(f"YEEEEEEEET\n{ocr_results}\n{yolo_detections}")

    def is_box_contained(self, inner_box, outer_box):
        return BoundingBoxUtils.is_box_contained(inner_box, outer_box)

    def calculate_iou(self, box1, box2):
        return BoundingBoxUtils.calculate_iou(box1, box2)

    def open_part_number(self):
        """Open part number dialog and handle selected file"""
        try:
            # Show login dialog first if not authenticated
            if not api.token:
                try:
                    # Try to connect to the API server
                    print("Testing API connection...")
                    base_url = APIEndpoints.BASE_URL
                    response = requests.get(base_url, timeout=10)
                    print(f"API response status: {response.status_code}")

                    # Show login dialog if server is responding
                    login_dialog = LoginDialog(self)
                    if login_dialog.exec_() != QDialog.Accepted:
                        return

                    # Verify token was obtained
                    if not api.token:
                        QMessageBox.critical(
                            self,
                            "Login Error",
                            "Failed to obtain authentication token. Please try again."
                        )
                        return

                except requests.RequestException as e:
                    print(f"API connection error: {str(e)}")
                    QMessageBox.warning(
                        self,
                        "Connection Error",
                        f"Cannot connect to the server at {APIEndpoints.BASE_URL}\n\n"
                        f"Error: {str(e)}\n\n"
                        "Opening local file browser instead..."
                    )
                    self.open_pdf()
                    return

            # Show part number dialog
            dialog = PartNumberDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                file_path = dialog.get_downloaded_file()
                selected_page = dialog.get_selected_page()
                rotation = dialog.get_selected_rotation()

                # Store the operations dialog reference
                self.operations_dialog = dialog.operations_dialog

                if file_path and os.path.exists(file_path):
                    try:
                        # Start loading immediately
                        self.start_loading()
                        QtWidgets.QApplication.processEvents()

                        # Reset the dimension table and clear YOLO detections
                        self.reset_dimension_table()
                        self.ui.pdf_view.clearYOLODetections()

                        # Open PDF file
                        self.current_pdf = fitz.open(file_path)
                        self.current_file = file_path

                        # Set loading parameters
                        self.loading_params = {
                            'selected_page': selected_page,
                            'rotation': rotation
                        }

                        # Load and process the page
                        if self.load_page() and self.process_page():
                            self.finalize_loading()
                        else:
                            raise Exception("Failed to load or process the page")

                    except Exception as e:
                        QtWidgets.QMessageBox.critical(
                            self,
                            "Error",
                            f"Failed to open PDF: {str(e)}"
                        )
                    finally:
                        # Stop loading
                        self.stop_loading()
                        QtWidgets.QApplication.processEvents()

                        # Clean up temporary file
                        try:
                            os.remove(file_path)
                        except:
                            pass
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "No file was downloaded or the file is missing."
                    )

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"An unexpected error occurred: {str(e)}\n\nOpening local file browser instead..."
            )
            self.open_pdf()

    def clear_highlighted_bbox(self):
        """Clear any existing highlighted bbox and balloon"""
        try:
            # Clear highlight polygon
            if hasattr(self, 'current_highlight') and self.current_highlight:
                self.ui.pdf_view.scene().removeItem(self.current_highlight)
                self.current_highlight = None

            # Clear balloon objects
            balloon_objects = ['balloon_circle', 'balloon_triangle', 'balloon_text']
            for obj_name in balloon_objects:
                if hasattr(self, obj_name):
                    obj = getattr(self, obj_name)
                    if obj and obj.scene():  # Check if object exists and is in scene
                        self.ui.pdf_view.scene().removeItem(obj)
                    setattr(self, obj_name, None)  # Set attribute to None

        except Exception as e:
            print(f"Error clearing highlight: {str(e)}")

    def is_similar_text(self, text1, text2):
        """Compare two texts to check if they are similar (ignoring spaces and case)"""
        try:
            # Remove spaces and convert to lowercase for comparison
            clean_text1 = ''.join(text1.lower().split())
            clean_text2 = ''.join(text2.lower().split())

            # Check for exact match
            if clean_text1 == clean_text2:
                return True

            # Check for numeric values (handle cases like "12.5" and "12,5")
            try:
                num1 = float(clean_text1.replace(',', '.'))
                num2 = float(clean_text2.replace(',', '.'))
                return abs(num1 - num2) < 0.001  # Small threshold for floating point comparison
            except:
                pass

            return False
        except:
            return False

    def save_to_database(self):
        """Save dimension data to database and generate PDF report for operator"""
        try:
            operation_number = self.operations_dialog.get_operation_number()
            production_order = self.operations_dialog.production_order
            ipid = f"IPID-{self.operations_dialog.part_number}-{operation_number}"

            # Get order_id from all_orders endpoint
            try:
                response = api._make_request("/planning/all_orders")
                if response and isinstance(response, list):
                    order_id = None
                    for order in response:
                        if str(order.get('production_order')) == str(production_order):
                            order_id = order.get('id')
                            break

                    if not order_id:
                        raise Exception(f"Could not find order_id for production order {production_order}")
                else:
                    raise Exception("Invalid response from all_orders endpoint")
            except Exception as e:
                print(f"Error getting order_id: {e}")
                QMessageBox.critical(self, "Error", f"Failed to get order ID: {str(e)}")
                return

            # Get quantity for operator role
            quantity_no = self.quantity_input.value() if hasattr(self, 'quantity_input') else 1

            # Check for quantity completion before processing any rows
            if self.user_role == 'operator' and quantity_no > 1:
                # Check if previous quantity is completed
                if not api.check_quantity_completion(order_id, ipid):
                    QMessageBox.critical(self, "Quantity Error",
                        "Quantity 1 is not approved yet. Please wait for approval before proceeding with next quantity.")
                    return

            # If no quantity error, proceed with saving rows
            document_id = 7 if operation_number == "999" else 3
            success_count = 0
            failed_rows = []
            total_rows = self.ui.dimtable.rowCount()

            # Process all rows
            for row in range(total_rows):
                try:
                    if self.user_role == 'operator':
                        payload = self.prepare_stage_inspection_payload(row, operation_number, order_id, quantity_no)
                        result = api.create_stage_inspection(payload)
                    else:
                        payload = self.prepare_master_boc_payload(row, document_id, operation_number, order_id, ipid)
                        result = api.create_master_boc(payload)

                    if result is None:
                        failed_rows.append(row + 1)
                    else:
                        success_count += 1

                except Exception as e:
                    failed_rows.append(row + 1)

            # Save ballooned drawing for admin
            if self.user_role == 'admin' and success_count > 0:
                try:
                    temp_pdf = os.path.join(tempfile.gettempdir(), f"ballooned_{uuid.uuid4()}.pdf")
                    if self.save_scene_to_pdf(temp_pdf):
                        if not api.upload_ballooned_drawing(production_order, ipid, temp_pdf):
                            QMessageBox.warning(self, "Warning", "Failed to upload ballooned drawing")
                    try:
                        os.remove(temp_pdf)
                    except:
                        pass
                except Exception as e:
                    print(f"Error saving ballooned drawing: {str(e)}")

            # For operator role, save dimension table as PDF report
            if self.user_role == 'operator' and success_count > 0:
                try:
                    # Show folder selection dialog
                    folder_dialog = ReportFolderDialog(self)
                    if folder_dialog.exec_() == QDialog.Accepted:
                        selected_folder = folder_dialog.get_selected_folder()
                        if selected_folder:
                            # Generate dimension table PDF
                            report_pdf = os.path.join(tempfile.gettempdir(), f"dimension_report_{uuid.uuid4()}.pdf")

                            # Create PDF with dimension table data
                            from reportlab.lib import colors
                            from reportlab.lib.pagesizes import landscape, A4
                            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            from reportlab.lib.units import inch

                            # Create document with landscape orientation
                            doc = SimpleDocTemplate(
                                report_pdf,
                                pagesize=landscape(A4),
                                rightMargin=20,
                                leftMargin=20,
                                topMargin=20,
                                bottomMargin=20
                            )

                            # Define styles
                            styles = getSampleStyleSheet()
                            title_style = ParagraphStyle(
                                'CustomTitle',
                                parent=styles['Title'],
                                fontSize=14,
                                spaceAfter=20,
                                alignment=1  # Center alignment
                            )

                            elements = []

                            # Add title with production order and operation
                            title = Paragraph(
                                f"Dimension Report - {production_order} - Operation {operation_number}",
                                title_style
                            )
                            elements.append(title)
                            elements.append(Spacer(1, 10))

                            # Create table data
                            table_data = []
                            
                            # Add headers
                            headers = []
                            for col in range(self.ui.dimtable.columnCount()):
                                header_text = self.ui.dimtable.horizontalHeaderItem(col).text()
                                # Make headers more concise if needed
                                header_text = header_text.replace("Dimension ", "")
                                headers.append(header_text)
                            table_data.append(headers)

                            # Add data rows
                            for row in range(self.ui.dimtable.rowCount()):
                                row_data = []
                                for col in range(self.ui.dimtable.columnCount()):
                                    item = self.ui.dimtable.item(row, col)
                                    row_data.append(item.text() if item else "")
                                table_data.append(row_data)

                            # Calculate column widths based on content and available space
                            available_width = landscape(A4)[0] - doc.leftMargin - doc.rightMargin
                            col_widths = [None] * len(headers)  # Start with flexible widths
                            
                            # Fixed width columns (in inches)
                            fixed_widths = {
                                0: 0.4,   # Sl No.
                                1: 0.4,   # Zone
                                2: 0.6,   # Actual
                                3: 0.5,   # +Tol
                                4: 0.5,   # -Tol
                                5: 1.2,   # Dimension Type
                                6: 1.0,   # Instrument
                                7: 0.8,   # Used Inst.
                                8: 0.6,   # M1
                                9: 0.6,   # M2
                                10: 0.6,  # M3
                                11: 0.6,  # Mean
                                12: 0.6   # Quantity No.
                            }
                            
                            # Set fixed widths and ensure all columns have a width
                            for i in range(len(col_widths)):
                                col_widths[i] = fixed_widths.get(i, 0.6) * inch  # Default to 0.6 inch if not specified
                            
                            # Create table with calculated widths
                            table = Table(table_data, colWidths=col_widths, repeatRows=1)

                            # Define table style
                            table_style = TableStyle([
                                # Header styling
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E0E0E0')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#000000')),
                                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 8),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                                
                                # Cell styling
                                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFFFFF')),
                                ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#000000')),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                                ('FONTSIZE', (0, 1), (-1, -1), 8),
                                ('TOPPADDING', (0, 1), (-1, -1), 4),
                                ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
                                
                                # Word wrapping for text columns
                                ('WORDWRAP', (5, 0), (5, -1), True),  # Dimension Type
                                ('WORDWRAP', (6, 0), (6, -1), True),  # Instrument
                                ('WORDWRAP', (7, 0), (7, -1), True),  # Used Inst.
                                
                                # Grid styling
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#000000')),
                                
                                # Alternate row colors
                                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F5F5F5')])
                            ])

                            # Add conditional formatting for measurement status
                            for row_idx in range(1, len(table_data)):
                                item = self.ui.dimtable.item(row_idx-1, 0)  # Get first cell of the row
                                if item:
                                    if item.background().color().name() == '#d1ffbd':  # Valid measurement
                                        table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#D1FFBD'))
                                    elif item.background().color().name() == '#ffb6c1':  # Invalid measurement
                                        table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#FFB6C1'))

                            table.setStyle(table_style)
                            elements.append(table)

                            # Build PDF
                            doc.build(elements)

                            # Upload report
                            document_name = f"Dimension_Report_{production_order}_{operation_number}"
                            description = f"Dimension report for {production_order} - Operation {operation_number}"

                            if api.upload_inspection_report(
                                production_order=production_order,
                                operation_number=operation_number,
                                file_path=report_pdf,
                                folder_path=selected_folder,
                                document_name=document_name,
                                description=description
                            ):
                                print("Successfully uploaded dimension report")
                            else:
                                QMessageBox.warning(self, "Warning", "Failed to upload dimension report")

                            # Clean up temp file
                            try:
                                os.remove(report_pdf)
                            except:
                                pass
                        else:
                            QMessageBox.warning(self, "Warning", "No folder selected for report upload")
                except Exception as e:
                    print(f"Error saving and uploading report: {str(e)}")
                    QMessageBox.warning(self, "Warning", f"Failed to save and upload report: {str(e)}")

            # Show results dialog
            if failed_rows:
                msg = f"Failed to save {len(failed_rows)} rows: {', '.join(map(str, failed_rows))}"
                if success_count > 0:
                    msg += f"\nSuccessfully saved {success_count} rows"
                QMessageBox.warning(self, "Save Results", msg)
            else:
                QMessageBox.information(self, "Success", f"All {total_rows} rows saved successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save data: {str(e)}")

    def prepare_stage_inspection_payload(self, row, operation_number, order_id, quantity_no):
        """Prepare payload for stage inspection (operator role)"""
        def get_cell_text(row, col):
            item = self.ui.dimtable.item(row, col)
            return item.text() if item else ""

        measured_1 = float(get_cell_text(row, 8) or "0")  # M1 column
        measured_2 = float(get_cell_text(row, 9) or "0")  # M2 column
        measured_3 = float(get_cell_text(row, 10) or "0") # M3 column
        measured_mean = (measured_1 + measured_2 + measured_3) / 3 if any(
            [measured_1, measured_2, measured_3]) else 0

        return {
            "op_id": api.get_operator_id(),  # Use operator_id from api instance
            "nominal_value": get_cell_text(row, 2) or "0",  # Nominal column
            "uppertol": float(get_cell_text(row, 3) or "0"),  # Upper Tol column
            "lowertol": float(get_cell_text(row, 4) or "0"),  # Lower Tol column
            "zone": get_cell_text(row, 1) or "N/A",  # Zone column
            "dimension_type": get_cell_text(row, 5) or "Unknown",  # Type column
            "measured_1": measured_1,
            "measured_2": measured_2,
            "measured_3": measured_3,
            "measured_mean": measured_mean,
            "measured_instrument": get_cell_text(row, 6) or "Not Specified",  # Instrument column
            "used_inst": get_cell_text(row, 7) or "Not Specified",  # Used Inst. column
            "op_no": operation_number,
            "is_done": False,
            "order_id": order_id,
            "quantity_no": quantity_no
        }

    def prepare_master_boc_payload(self, row, document_id, operation_number, order_id, ipid):
        """Prepare payload for master BOC (admin role)"""
        def get_cell_text(row, col):
            item = self.ui.dimtable.item(row, col)
            return item.text() if item else ""

        # Get nominal and convert tolerances
        nominal = get_cell_text(row, 2)
        if not nominal or nominal.strip() == '':
            raise ValueError("Missing nominal value")

        try:
            upper_tol = float(get_cell_text(row, 3) or "0")
        except ValueError:
            upper_tol = 0.0

        try:
            lower_tol = float(get_cell_text(row, 4) or "0")
            if lower_tol > 0:  # If positive, make it negative
                lower_tol = -lower_tol
        except ValueError:
            lower_tol = 0.0

        # Get bounding boxes and validate
        bboxes = self.ui.pdf_view.get_all_bboxes_for_row(row)
        if not bboxes:
            raise ValueError("No bounding boxes found")

        validated_bboxes = []
        for bbox in bboxes:
            if isinstance(bbox, list):
                if len(bbox) == 8:  # Already in [x1,y1,x2,y1,x2,y2,x1,y2] format
                    validated_bboxes.extend([float(x) for x in bbox])
                elif len(bbox) == 4:  # Convert from [x1,y1,x2,y2] to 8-point format
                    x1, y1, x2, y2 = map(float, bbox)
                    validated_bboxes.extend([
                        x1, y1,  # Top-left
                        x2, y1,  # Top-right
                        x2, y2,  # Bottom-right
                        x1, y2   # Bottom-left
                    ])

        if not validated_bboxes:
            raise ValueError("No valid bounding boxes")

        return {
            "order_id": order_id,
            "document_id": document_id,
            "nominal": nominal,
            "uppertol": upper_tol,
            "lowertol": lower_tol,
            "zone": get_cell_text(row, 1) or "N/A",
            "dimension_type": get_cell_text(row, 5) or "Unknown",
            "measured_instrument": get_cell_text(row, 6) or "Not Specified",
            "op_no": operation_number,
            "bbox": validated_bboxes,
            "ipid": ipid,
            "part_number": self.operations_dialog.part_number
        }

    def save_scene_to_pdf(self, file_path):
        """Save the current scene with balloons to PDF"""
        try:
            # Create printer
            printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
            printer.setOutputFormat(QtPrintSupport.QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            printer.setPageSize(QtGui.QPageSize(self.ui.scene.sceneRect().size().toSize()))

            # Create painter
            painter = QtGui.QPainter()
            painter.begin(printer)

            # Render scene
            self.ui.scene.render(painter)
            painter.end()

            return True
        except Exception as e:
            print(f"Error saving scene to PDF: {str(e)}")
            return False

    def handle_login_success(self, username, role):
        """Handle successful login"""
        self.user_role = role.lower()
        print(f"Logged in as {username} with role: {self.user_role}")

        # Configure UI based on role
        self.configure_ui_for_role()

        # Show operations dialog
        self.show_operations_dialog()

    def configure_ui_for_role(self):
        """Configure UI elements based on user role"""
        is_admin = self.user_role == 'admin'

        # Enable/disable selection tool - initially disabled for admin until OCR completes
        if hasattr(self.ui, 'actionSelectionTool'):
            self.ui.actionSelectionTool.setEnabled(False)  # Start disabled

        # Enable/disable stamp tool
        if hasattr(self.ui, 'actionStamp'):
            self.ui.actionStamp.setEnabled(is_admin)

        # Update graphics view settings
        if hasattr(self.ui, 'pdf_view'):
            self.ui.pdf_view.selection_mode = False  # Start with selection mode off
            self.ui.pdf_view.stamp_mode = False  # Always start with stamp mode off

        # Update status bar with role info
        self.statusBar().showMessage(f"Logged in as: {self.user_role}")

        # Configure table with role-specific columns
        self.setupCentralWidget()

    def setupCentralWidget(self):
        """Setup central widget with role-specific table columns"""
        # Create base headers list
        base_headers = ["Sl No.", "Zone", "Actual", "+Tol", "-Tol", "Dimension Type", "Instrument"]
        operator_headers = ["Used Inst.", "M1", "M2", "M3", "Mean", "Quantity No."]

        # Determine total columns based on role
        if self.user_role == 'operator':
            headers = base_headers + operator_headers
            total_columns = len(headers)
            self.ui.dimtable.setColumnCount(total_columns)

            # Increase table frame width for operator view
            screen_width = QtWidgets.QApplication.desktop().screenGeometry().width()
            table_width = int(screen_width * 0.45)  # Use 45% of screen width
            self.ui.table_frame.setMinimumWidth(table_width)

            # Set fixed column widths for operator view
            column_widths = {
                0: 50,    # Sl No.
                1: 50,    # Zone
                2: 80,    # Actual
                3: 60,    # +Tol
                4: 60,    # -Tol
                5: 120,   # Dim.Type
                6: 120,   # Instrument
                7: 100,   # Used Inst.
                8: 80,    # M1
                9: 80,    # M2
                10: 80,   # M3
                11: 80,   # Mean
                12: 100,  # Quantity No.
            }

            # Apply column widths
            for col, width in column_widths.items():
                if col < total_columns:
                    self.ui.dimtable.setColumnWidth(col, width)

            # Print debug information
            print("\nOperator Table Setup:")
            print(f"Total columns: {self.ui.dimtable.columnCount()}")
            print("Headers:", headers)
            for i, header in enumerate(headers):
                print(f"Column {i}: {header}")
        else:
            headers = base_headers
            self.ui.dimtable.setColumnCount(len(headers))

            # Reset table frame width for admin view
            self.ui.table_frame.setMinimumWidth(0)

            # Set column widths for admin view
            self.ui.dimtable.setColumnWidth(0, 60)   # Sl No.
            self.ui.dimtable.setColumnWidth(1, 50)   # Zone
            self.ui.dimtable.setColumnWidth(2, 65)   # Actual
            self.ui.dimtable.setColumnWidth(3, 50)   # +Tol
            self.ui.dimtable.setColumnWidth(4, 50)   # -Tol
            self.ui.dimtable.setColumnWidth(5, 120)  # Dim.Type
            self.ui.dimtable.setColumnWidth(6, 100)  # Instrument

        # Set headers
        for i, header in enumerate(headers):
            item = QtWidgets.QTableWidgetItem(header)
            item.setTextAlignment(Qt.AlignCenter)
            self.ui.dimtable.setHorizontalHeaderItem(i, item)

        # Configure selection behavior based on role
        if self.user_role == 'admin':
            self.ui.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        else:
            self.ui.dimtable.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        self.ui.dimtable.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.ui.dimtable.setFocusPolicy(Qt.StrongFocus)

        # Connect selection change signal
        self.ui.dimtable.itemSelectionChanged.connect(self.on_table_selection_changed)

        # Set table style
        self.ui.dimtable.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
                selection-background-color: #e3f2fd;
                selection-color: black;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
        """)

    def on_table_selection_changed(self):
        """Handle table selection changes"""
        selected_rows = self.ui.dimtable.selectedItems()
        if selected_rows:
            row = selected_rows[0].row()
            self.highlight_bbox(row, 2)  # 2 is the nominal column

    def logout(self):
        """Handle user logout"""
        try:
            # Clear API token
            api.token = None
            api.user_role = None
            api.username = None

            # Clear current data
            self.reset_application_state()

            # Show login dialog
            login_dialog = LoginDialog(self)
            if login_dialog.exec_() == QDialog.Accepted:
                # Login successful, continue with application
                pass
            else:
                # Login cancelled, close application
                self.close()

        except Exception as e:
            print(f"Error during logout: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to logout: {str(e)}")

    def reset_application_state(self):
        """Reset application state after logout"""
        try:
            # Clear user-specific data
            self.user_role = None

            # Clear PDF view
            if hasattr(self.ui, 'pdf_view'):
                self.ui.pdf_view.clearOCRItems(clear_all=True)
                # Clear any existing highlights and balloons
                self.clear_highlighted_bbox()
                # Clear scene
                scene = self.ui.pdf_view.scene()
                if scene:
                    scene.clear()

            # Clear balloon object references
            self.balloon_circle = None
            self.balloon_triangle = None
            self.balloon_text = None
            self.current_highlight = None

            # Clear dimension table
            if hasattr(self.ui, 'dimtable'):
                self.ui.dimtable.setRowCount(0)

            # Reset status bar
            self.statusBar().clearMessage()

            # Clear any stored file paths or data
            self.current_pdf = None
            self.current_page = None
            self.rotation = 0
            self.loading_params = None

            # Disable tools that require login
            self.ui.actionSelectionTool.setEnabled(False)
            self.ui.actionStamp.setEnabled(False)

            # Reset window title
            self.setWindowTitle("Quality Management Tool")

            # Clear header labels
            if hasattr(self, 'header_labels'):
                for label in self.header_labels.values():
                    label.setText("-")

        except Exception as e:
            print(f"Error resetting application state: {str(e)}")

    def show_operations_dialog(self):
        """Show the operations dialog after successful login"""
        try:
            # Show part number dialog first
            part_dialog = PartNumberDialog(self)
            if part_dialog.exec_() == QDialog.Accepted:
                # Get selected part number and production order
                part_number = part_dialog.get_selected_part_number()
                production_order = part_dialog.get_selected_production_order()

                # Store current order details
                self.current_order_details = {
                    'part_number': part_number,
                    'production_order': production_order
                }

                # Update header with order details
                self.update_order_details(part_number)

                # Debug print current order details
                print(f"\nCurrent order details:")
                print(self.current_order_details)

                # Show operations dialog
                self.operations_dialog = OperationsDialog(
                    part_number,
                    production_order,  # Use production_order from current_order_details
                    self
                )
                if self.operations_dialog.exec_() == QDialog.Accepted:
                    # Get the downloaded file path and selected page/rotation
                    file_path = self.operations_dialog.get_downloaded_file()
                    selected_page = self.operations_dialog.get_selected_page()
                    selected_rotation = self.operations_dialog.get_selected_rotation()

                    if file_path:
                        # Store the current page and rotation
                        self.current_page = selected_page
                        self.rotation = selected_rotation

                        # Open the PDF directly without showing preview again
                        self.process_pdf(file_path, selected_page, selected_rotation)

                        # Store operation data
                        self.current_operation = self.operations_dialog.get_selected_operation()

                        # If operator, load data from API
                        if self.user_role == 'operator':
                            self.load_operator_data()

        except Exception as e:
            print(f"Error showing operations dialog: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to show operations dialog: {str(e)}")

    def load_operator_data(self):
        """Load operator data from API"""
        try:
            # Get order_id from all_orders endpoint
            response = api._make_request("/planning/all_orders")
            if response and isinstance(response, list):
                # Find the matching order
                order_id = None
                for order in response:
                    if str(order.get('production_order')) == str(self.operations_dialog.production_order):
                        order_id = order.get('id')
                        break

                if not order_id:
                    raise Exception(f"Could not find order_id for production order {self.operations_dialog.production_order}")
            else:
                raise Exception("Invalid response from all_orders endpoint")

            # Get operation number
            operation_number = self.operations_dialog.get_operation_number()

            # Use the new endpoint format
            endpoint = f"/quality/master-boc/order/{order_id}?op_no={operation_number}"
            print(f"Fetching operator data from: {endpoint}")

            response = api._make_request(endpoint)

            if response:
                print(f"Loaded operator data: {json.dumps(response, indent=2)}")

                # Clear existing data
                self.ui.dimtable.setRowCount(0)
                self.ui.pdf_view.scene().clear()

                # Add quantity input widget above table only for operator role
                if self.user_role == 'operator':
                    quantity_widget = QWidget()
                    quantity_layout = QHBoxLayout(quantity_widget)
                    quantity_layout.setContentsMargins(10, 5, 10, 5)

                    # Create a container widget for better alignment
                    container = QWidget()
                    container_layout = QHBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    container_layout.setSpacing(10)

                    quantity_label = QLabel("Quantity:")
                    quantity_label.setStyleSheet("""
                        QLabel {
                            font-size: 13px;
                            font-weight: bold;
                            color: #2c3e50;
                            background: transparent;
                        }
                    """)

                    self.quantity_input = QSpinBox()
                    self.quantity_input.setMinimum(1)
                    self.quantity_input.setMaximum(9999)
                    self.quantity_input.setValue(1)
                    self.quantity_input.setStyleSheet("""
                        QSpinBox {
                            padding: 5px;
                            border: none;
                            border-bottom: 1px solid #ccc;
                            min-width: 80px;
                            background: transparent;
                        }
                        QSpinBox::up-button, QSpinBox::down-button {
                            width: 16px;
                            border: none;
                            background: transparent;
                        }
                        QSpinBox:focus {
                            border-bottom: 2px solid #2196f3;
                        }
                    """)

                    container_layout.addWidget(quantity_label)
                    container_layout.addWidget(self.quantity_input)
                    container_layout.addStretch()

                    quantity_layout.addWidget(container)
                    quantity_layout.addStretch()

                    # Insert quantity widget above table
                    table_parent_layout = self.ui.dimtable.parent().layout()
                    table_index = table_parent_layout.indexOf(self.ui.dimtable)
                    table_parent_layout.insertWidget(table_index, quantity_widget)

                # Set correct column count for operator view
                base_headers = ["Sl No.", "Zone", "Actual", "+Tol", "-Tol", "Dimension Type", "Instrument"]
                operator_headers = ["Used Inst.", "M1", "M2", "M3", "Mean"]  # Quantity No. is handled separately
                headers = base_headers + operator_headers
                self.ui.dimtable.setColumnCount(len(headers))

                # Reload the PDF page
                if self.current_page:
                    pix = self.current_page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(img)
                    self.ui.pdf_view.scene().addPixmap(pixmap)
                    self.ui.pdf_view.setSceneRect(QRectF(pixmap.rect()))

                # Process each dimension
                for dimension in response:
                    row = self.ui.dimtable.rowCount()
                    self.ui.dimtable.insertRow(row)

                    # Set data in table (adjusted column indices)
                    self.ui.dimtable.setItem(row, 0, QTableWidgetItem(str(row + 1)))  # Serial number
                    self.ui.dimtable.setItem(row, 1, QTableWidgetItem(dimension.get('zone', 'N/A')))
                    self.ui.dimtable.setItem(row, 2, QTableWidgetItem(str(dimension.get('nominal', ''))))
                    self.ui.dimtable.setItem(row, 3, QTableWidgetItem(str(dimension.get('uppertol', 0))))
                    self.ui.dimtable.setItem(row, 4, QTableWidgetItem(str(dimension.get('lowertol', 0))))
                    self.ui.dimtable.setItem(row, 5, QTableWidgetItem(dimension.get('dimension_type', 'Unknown')))
                    self.ui.dimtable.setItem(row, 6, QTableWidgetItem(dimension.get('measured_instrument', 'Not Specified')))

                    # Add empty cells for operator columns (adjusted range)
                    for i in range(7, 12):  # Changed from 11 to 12 to include Mean column
                        item = QTableWidgetItem("")
                        item.setTextAlignment(Qt.AlignCenter)
                        self.ui.dimtable.setItem(row, i, item)

                    # Draw bounding box if bbox data exists
                    bbox = dimension.get('bbox', [])
                    print(f"\nRow {row} bbox data: {bbox}")  # Debug print

                    if bbox:
                        try:
                            # Convert bbox to list if it's not already
                            if not isinstance(bbox, list):
                                bbox = list(bbox)

                            # Ensure we have valid coordinates
                            if len(bbox) >= 8:
                                # Create points for polygon
                                points = []
                                for i in range(0, len(bbox), 2):
                                    x = float(bbox[i])
                                    y = float(bbox[i+1])
                                    points.append([x, y])

                                print(f"Converted points: {points}")  # Debug print

                                # Create and style the polygon
                                polygon = QGraphicsPolygonItem(QPolygonF([QPointF(p[0], p[1]) for p in points]))
                                pen = QPen(QColor(0, 255, 0))  # Green color
                                pen.setWidth(2)
                                pen.setCosmetic(True)
                                polygon.setPen(pen)
                                polygon.setZValue(1)

                                # Add polygon to scene
                                self.ui.pdf_view.scene().addItem(polygon)

                                # Store points data in table instead of raw bbox
                                nominal_item = self.ui.dimtable.item(row, 2)
                                if nominal_item:
                                    nominal_item.setData(Qt.UserRole, points)  # Store as points list
                                    print(f"Stored points data: {points}")  # Debug print

                        except Exception as bbox_error:
                            print(f"Error processing bbox for row {row}: {bbox_error}")
                            print(f"Original bbox data: {bbox}")

                print(f"Loaded {len(response)} dimensions from database")

                # Fit view to content
                self.ui.pdf_view.fitInView(self.ui.pdf_view.sceneRect(), Qt.KeepAspectRatio)

            else:
                print("No data returned from API")
                QMessageBox.warning(self, "Warning", "No dimension data found")

        except Exception as e:
            print(f"Error loading operator data: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def update_table_zones(self):
        """Update zones for all items in the table"""
        try:
            if self.current_image is None:
                return

            for row in range(self.ui.dimtable.rowCount()):
                # Get the bbox from the nominal column
                nominal_item = self.ui.dimtable.item(row, 2)
                if nominal_item and nominal_item.data(Qt.UserRole):
                    bbox = nominal_item.data(Qt.UserRole)

                    # Calculate midpoint and get zone
                    midpoint = ClusterDetector.calculate_merged_box_midpoint(bbox)
                    if midpoint:
                        zone = ZoneDetector.get_zone_for_midpoint(self.current_image, midpoint)
                        self.ui.dimtable.setItem(row, 1, QTableWidgetItem(zone))

        except Exception as e:
            print(f"Error updating table zones: {str(e)}")

    def update_highlight_box(self):
        """Update all bboxes and balloons based on current table rows"""
        try:
            # First clear any existing highlight
            self.clear_highlighted_bbox()

            # Remove all existing balloons
            balloon_items = []
            for item in self.ui.pdf_view.scene().items():
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)

            for item in balloon_items:
                self.ui.pdf_view.scene().removeItem(item)

            # Clear balloon references
            self.balloon_circle = None
            self.balloon_triangle = None
            self.balloon_text = None
            self.current_highlight = None

            # Update serial numbers for all rows
            for row_idx in range(self.ui.dimtable.rowCount()):
                sl_no_item = QTableWidgetItem(str(row_idx + 1))
                sl_no_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row_idx, 0, sl_no_item)

            # Re-apply balloons for all rows using VisualizationEvents.highlight_bbox
            from events import VisualizationEvents
            for row_idx in range(self.ui.dimtable.rowCount()):
                VisualizationEvents.highlight_bbox(self, row_idx, 2)  # 2 is nominal column

            # Clear the final highlight
            self.clear_highlighted_bbox()

        except Exception as e:
            print(f"Error updating highlight boxes: {str(e)}")
            import traceback
            traceback.print_exc()






    def toggleBalloonVisibility(self):
        """Toggle the visibility of balloons and annotation circles in the scene"""
        try:
            # Toggle the state
            self.balloons_hidden = not self.balloons_hidden

            # Update the icon/action to show the current state
            if self.balloons_hidden:
                self.ui.actionHideStamp.setText("Show Annotations")
                self.ui.actionHideStamp.setToolTip("Show Annotation Circles")
            else:
                self.ui.actionHideStamp.setText("Hide Annotations")
                self.ui.actionHideStamp.setToolTip("Hide Annotation Circles")

            # Find all balloon items using the same logic as in HighlightManager.delete_balloons
            balloon_items = []

            # Look for all types of items that could be part of a balloon
            for item in self.ui.pdf_view.scene().items():
                # Check for balloon_data attribute
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)
                    continue

                # Check for circle, triangle, and text items that might be balloons
                if isinstance(item, QtWidgets.QGraphicsEllipseItem):
                    # Circle part of balloon
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsPathItem):
                    # Path items used for balloon circles and triangles
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsPolygonItem):
                    # Check if it's a small triangle (likely part of a balloon)
                    polygon = item.polygon()
                    if len(polygon) == 3:  # Triangle has 3 points
                        # Calculate area of polygon
                        points = [(p.x(), p.y()) for p in polygon]
                        area = 0.5 * abs(sum(x0*y1 - x1*y0
                                            for ((x0, y0), (x1, y1)) in zip(points, points[1:] + [points[0]])))
                        if area < 500:  # Small triangle is likely a balloon pointer
                            balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsTextItem):
                    # Check if it's a single digit or small number (likely a balloon number)
                    text = item.toPlainText()
                    if text.isdigit() and len(text) <= 3:
                        balloon_items.append(item)

            # Toggle visibility of all balloon items
            for item in balloon_items:
                item.setVisible(not self.balloons_hidden)

            # Show status message
            status_msg = f"{'Hidden' if self.balloons_hidden else 'Shown'} {len(balloon_items)} annotation items"
            self.ui.statusbar.showMessage(status_msg, 3000)  # Show for 3 seconds

        except Exception as e:
            print(f"Error toggling annotation visibility: {str(e)}")
            import traceback
            traceback.print_exc()


    def toggleFieldDivision(self):
        """Toggle the visibility of field division grid lines"""
        try:
            # Check if grid is currently visible
            grid_visible = hasattr(self, 'grid_visible') and self.grid_visible

            # Toggle the state
            self.grid_visible = not grid_visible

            # Update the icon/action to show the current state
            if self.grid_visible:
                self.ui.actionFieldDivision.setText("Hide Field Division")
                self.ui.actionFieldDivision.setToolTip("Hide Field Division Grid")
                self.ui.actionDisplayWholeDrawing.trigger()


                # Disable selection and stamping features
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionCharacteristicsProperties.setEnabled(False)

                # Store current tool and switch to pan tool
                self.previous_tool = self.current_tool if hasattr(self, 'current_tool') else None
                self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                self.current_tool = 'pan'

            else:
                self.ui.actionFieldDivision.setText("Show Field Division")
                self.ui.actionFieldDivision.setToolTip("Show Field Division Grid")

                # Re-enable selection and stamping features
                self.ui.actionSelectionTool.setEnabled(True)
                self.ui.actionStamp.setEnabled(True)
                self.ui.actionCharacteristicsProperties.setEnabled(True)

                # Restore previous tool if available
                if hasattr(self, 'previous_tool') and self.previous_tool:
                    if self.previous_tool == 'selection':
                        self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
                        self.current_tool = 'selection'
                    else:
                        self.ui.pdf_view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
                        self.current_tool = self.previous_tool

            # Call the draw_field_division method
            from algorithms import ZoneDetector
            success = ZoneDetector.draw_field_division(self, self.grid_visible)


            # Make sure grid items are protected
            if self.grid_visible:
                for item in self.ui.pdf_view.scene().items():
                    if hasattr(item, 'is_grid_item') and item.is_grid_item:
                        # Make grid items not selectable and not movable
                        item.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
                        item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
                        # Set a high Z value to ensure grid stays on top
                        item.setZValue(100)

            # Show status message
            if success:
                status_msg = f"{'Shown' if self.grid_visible else 'Hidden'} field division grid"
            else:
                status_msg = "Failed to update field division grid"

            self.ui.statusbar.showMessage(status_msg, 3000)  # Show for 3 seconds

        except Exception as e:
            print(f"Error toggling field division: {str(e)}")
            import traceback
            traceback.print_exc()

    def toggleCharacteristicsProperties(self):
        """Toggle the properties editing mode for balloons"""
        try:
            # Toggle the properties mode state
            self.properties_mode_active = not getattr(self, 'properties_mode_active', False)

            if self.properties_mode_active:
                # Update UI to show active state
                self.ui.actionCharacteristicsProperties.setText("Exit Properties Mode")
                self.ui.actionCharacteristicsProperties.setToolTip("Exit Properties Mode")

                # Disable other tools
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionFieldDivision.setEnabled(False)

                # Change cursor to indicate clickable items
                self.ui.pdf_view.viewport().setCursor(self.properties_cursor)

                # Store original event handler
                self.original_mouse_press = self.ui.pdf_view.mousePressEvent

                # Set custom event handler
                self.ui.pdf_view.mousePressEvent = self.propertiesMousePressEvent

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Click on a balloon to edit its number", 5000)

            else:
                # Restore normal state
                self.ui.actionCharacteristicsProperties.setText("Properties")
                self.ui.actionCharacteristicsProperties.setToolTip("Edit Properties")

                # Re-enable other tools if user is admin
                if self.user_role == 'admin':
                    self.ui.actionSelectionTool.setEnabled(True)
                    self.ui.actionStamp.setEnabled(True)
                    self.ui.actionFieldDivision.setEnabled(True)

                # Restore cursor
                self.ui.pdf_view.viewport().setCursor(QtCore.Qt.ArrowCursor)

                # Restore original event handler
                if hasattr(self, 'original_mouse_press'):
                    self.ui.pdf_view.mousePressEvent = self.original_mouse_press

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Disabled", 3000)

        except Exception as e:
            print(f"Error toggling properties mode: {str(e)}")
            import traceback
            traceback.print_exc()

    def propertiesMousePressEvent(self, event):
        """Handle mouse press events in properties mode"""
        try:
            if getattr(self, 'properties_mode_active', False):
                # Convert mouse position to scene coordinates
                scene_pos = self.ui.pdf_view.mapToScene(event.pos())

                # Get items at the clicked position
                items = self.ui.pdf_view.scene().items(scene_pos)

                # Find balloon items
                balloon_item = None
                balloon_data = None

                for item in items:
                    # Check if item has balloon_data attribute
                    if hasattr(item, 'balloon_data'):
                        balloon_item = item
                        balloon_data = item.balloon_data
                        break

                    # Check for various balloon item types
                    if (isinstance(item, QtWidgets.QGraphicsEllipseItem) or
                        isinstance(item, QtWidgets.QGraphicsPathItem) or
                        isinstance(item, QtWidgets.QGraphicsPolygonItem) or
                        (isinstance(item, QtWidgets.QGraphicsTextItem) and
                        item.toPlainText().isdigit() and len(item.toPlainText()) <= 3)):
                        balloon_item = item
                        # Try to find related items to get balloon_data
                        for related_item in self.ui.pdf_view.scene().items():
                            if (hasattr(related_item, 'balloon_data') and
                                related_item.balloon_data.get('group_id') == getattr(item, 'group_id', None)):
                                balloon_data = related_item.balloon_data
                                break
                        break

                if balloon_item:
                    # Get current row number from balloon data
                    current_row = None
                    if balloon_data and 'row' in balloon_data:
                        current_row = balloon_data['row']
                    else:
                        # Try to get row from text item
                        for item in items:
                            if isinstance(item, QtWidgets.QGraphicsTextItem):
                                try:
                                    current_row = int(item.toPlainText()) - 1  # Convert to 0-based index
                                    break
                                except ValueError:
                                    pass

                    if current_row is not None:
                        # Show input dialog for new balloon number
                        current_text = str(current_row + 1)  # Convert to 1-based for display

                        dialog = QtWidgets.QInputDialog(self)
                        dialog.resize(400, 200)  # Set wider and taller size
                        font = dialog.font()
                        font.setPointSize(12)
                        dialog.setFont(font)

                        new_text, ok = QtWidgets.QInputDialog.getText(
                            dialog,  # Use our pre-sized dialog
                            "Change Balloon Number",
                            "Enter new number (1-" + str(self.ui.dimtable.rowCount()) + "):",
                            QtWidgets.QLineEdit.Normal,
                            current_text
                        )


                        if ok and new_text:
                            try:
                                new_row = int(new_text) - 1  # Convert to 0-based index

                                # Validate row number
                                if 0 <= new_row < self.ui.dimtable.rowCount():
                                    # Use HighlightManager to change the balloon number
                                    from highlight_manager import HighlightManager
                                    success = self.change_balloon_number(current_row, new_row)

                                    if success:
                                        self.ui.statusbar.showMessage(f"Balloon number updated from {current_row+1} to {new_row+1}", 3000)
                                    else:
                                        self.ui.statusbar.showMessage("Failed to update balloon number", 3000)
                                else:
                                    self.ui.statusbar.showMessage(f"Invalid row number. Must be between 1 and {self.ui.dimtable.rowCount()}", 3000)
                            except ValueError:
                                self.ui.statusbar.showMessage("Invalid input. Please enter a number.", 3000)

                        # Don't propagate the event further
                        return
                    else:
                        self.ui.statusbar.showMessage("Could not determine balloon row number", 3000)

            # Call original handler for other cases
            if hasattr(self, 'original_mouse_press'):
                self.original_mouse_press(event)

        except Exception as e:
            print(f"Error handling properties mouse press: {str(e)}")
            import traceback
            traceback.print_exc()

            # Call original handler if there's an error
            if hasattr(self, 'original_mouse_press'):
                self.original_mouse_press(event)


    def change_balloon_number(self, old_row, new_row):
        """ Change a balloon's number by swapping table data and updating visualizations """
        try:
            # Validate inputs
            if old_row == new_row:
                return True  # No change needed

            if old_row < 0 or new_row < 0 or old_row >= self.ui.dimtable.rowCount() or new_row >= self.ui.dimtable.rowCount():
                return False

            # Get the data from both rows
            def get_row_data(row_idx):
                data = {}
                for col in range(self.ui.dimtable.columnCount()):
                    item = self.ui.dimtable.item(row_idx, col)
                    if item:
                        data[col] = {
                            'text': item.text(),
                            'data': item.data(Qt.UserRole)
                        }
                return data

            old_row_data = get_row_data(old_row)
            new_row_data = get_row_data(new_row)

            # Swap data in the table
            for col in range(self.ui.dimtable.columnCount()):
                # Skip the serial number column (0)
                if col == 0:
                    continue

                # Update old row with new row data
                if col in new_row_data:
                    old_item = QTableWidgetItem(new_row_data[col]['text'])
                    if new_row_data[col]['data'] is not None:
                        old_item.setData(Qt.UserRole, new_row_data[col]['data'])
                    self.ui.dimtable.setItem(old_row, col, old_item)

                # Update new row with old row data
                if col in old_row_data:
                    new_item = QTableWidgetItem(old_row_data[col]['text'])
                    if old_row_data[col]['data'] is not None:
                        new_item.setData(Qt.UserRole, old_row_data[col]['data'])
                    self.ui.dimtable.setItem(new_row, col, new_item)

            # Update serial numbers for all rows
            for row_idx in range(self.ui.dimtable.rowCount()):
                sl_no_item = QTableWidgetItem(str(row_idx + 1))
                sl_no_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row_idx, 0, sl_no_item)

            # Find and remove all balloon items
            from highlight_manager import HighlightManager

            # Remove all existing balloons
            balloon_items = []
            for item in self.ui.pdf_view.scene().items():
                if hasattr(item, 'balloon_data'):
                    balloon_items.append(item)
                elif isinstance(item, QtWidgets.QGraphicsEllipseItem) or \
                    isinstance(item, QtWidgets.QGraphicsPathItem) or \
                    isinstance(item, QtWidgets.QGraphicsTextItem) and \
                    item.toPlainText().isdigit() and len(item.toPlainText()) <= 3:
                    balloon_items.append(item)

            for item in balloon_items:
                self.ui.pdf_view.scene().removeItem(item)

            # Recreate balloons for each row using the bounding box data from the table
            for row_idx in range(self.ui.dimtable.rowCount()):
                # Get the bbox data from the nominal column (column 2)
                item = self.ui.dimtable.item(row_idx, 2)
                if item and item.data(Qt.UserRole):
                    bbox = item.data(Qt.UserRole)

                    # Create new balloon with correct row number
                    balloon_items = HighlightManager.create_balloon(
                        self.ui.pdf_view,
                        bbox,
                        row_idx + 1  # Convert to 1-based for display
                    )

                    # Add balloon items to the scene
                    for balloon_item in balloon_items:
                        # Store row information in balloon_data
                        balloon_item.balloon_data = {'row': row_idx}
                        self.ui.pdf_view.scene().addItem(balloon_item)

            # Force scene update
            self.ui.pdf_view.scene().update()

            return True

        except Exception as e:
            print(f"Error changing balloon number: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def toggleCharacteristicsOverview(self):
        """Toggle the properties editing mode for balloons"""
        try:
            # Toggle the properties mode state
            self.properties_mode_active = not getattr(self, 'properties_mode_active', False)

            if self.properties_mode_active:
                # Update UI to show active state
                self.ui.actionCharacteristicsProperties.setText("Exit Overview Mode")
                self.ui.actionCharacteristicsProperties.setToolTip("Exit Overview Mode")

                # Disable other tools
                self.ui.actionSelectionTool.setEnabled(False)
                self.ui.actionStamp.setEnabled(False)
                self.ui.actionFieldDivision.setEnabled(False)
                self.ui.actionCharacteristicsProperties.setEnabled(False)

                # Set custom cursor for properties mode
                if not hasattr(self, 'properties_cursor'):
                    self.properties_cursor = QtCore.Qt.PointingHandCursor

                # Apply the cursor
                self.ui.pdf_view.viewport().setCursor(self.properties_cursor)

                # Store original event handler
                self.original_mouse_move = self.ui.pdf_view.mouseMoveEvent

                # Set custom event handlers
                self.ui.pdf_view.mouseMoveEvent = self.propertiesMouseMoveEvent

                # Show status message
                self.ui.statusbar.showMessage("Overview Mode: Hover on a balloon to overview it", 5000)

            else:
                # Restore normal state
                self.ui.actionCharacteristicsOverview.setText("Overview")
                self.ui.actionCharacteristicsOverview.setToolTip("Overview Properties")

                # Re-enable other tools if user is admin
                if self.user_role == 'admin':
                    self.ui.actionSelectionTool.setEnabled(True)
                    self.ui.actionStamp.setEnabled(True)
                    self.ui.actionFieldDivision.setEnabled(True)
                    self.ui.actionCharacteristicsProperties.setEnabled(True)

                # Restore cursor
                self.ui.pdf_view.viewport().setCursor(QtCore.Qt.ArrowCursor)

                if hasattr(self, 'original_mouse_move'):
                    self.ui.pdf_view.mouseMoveEvent = self.original_mouse_move

                # Hide any active tooltip
                if hasattr(self, 'balloon_tooltip') and self.balloon_tooltip:
                    self.balloon_tooltip.hide()
                    self.balloon_tooltip = None

                # Show status message
                self.ui.statusbar.showMessage("Properties Mode: Disabled", 3000)

        except Exception as e:
            print(f"Error toggling properties mode: {str(e)}")
            import traceback
            traceback.print_exc()

    def propertiesMouseMoveEvent(self, event):
        """Handle mouse move events in properties mode to show tooltips"""
        try:
            if getattr(self, 'properties_mode_active', False):
                # Convert mouse position to scene coordinates
                scene_pos = self.ui.pdf_view.mapToScene(event.pos())

                # Get items at the cursor position
                items = self.ui.pdf_view.scene().items(scene_pos)

                # Find balloon items
                balloon_item = None
                balloon_data = None
                balloon_row = None

                for item in items:
                    # Check if item has balloon_data attribute
                    if hasattr(item, 'balloon_data'):
                        balloon_item = item
                        balloon_data = item.balloon_data
                        # Get row from balloon_data - handle both formats
                        if 'row' in balloon_data:
                            balloon_row = balloon_data.get('row')
                        elif 'table_row' in balloon_data:
                            balloon_row = balloon_data.get('table_row') - 1  # Convert from 1-based to 0-based
                        break

                    # Check for text items that might be balloon numbers
                    if isinstance(item, QtWidgets.QGraphicsTextItem):
                        try:
                            number = int(item.toPlainText())
                            balloon_row = number - 1  # Convert from 1-based to 0-based
                            balloon_item = item
                            break
                        except ValueError:
                            pass

                    # Check for balloon components by type
                    if (isinstance(item, QtWidgets.QGraphicsEllipseItem) or
                        isinstance(item, QtWidgets.QGraphicsPathItem) or
                        isinstance(item, QtWidgets.QGraphicsPolygonItem)):
                        # Try to find related text item to get the row number
                        for related_item in self.ui.pdf_view.scene().items():
                            if isinstance(related_item, QtWidgets.QGraphicsTextItem):
                                try:
                                    if related_item.pos().x() >= item.boundingRect().left() and \
                                    related_item.pos().x() <= item.boundingRect().right() and \
                                    related_item.pos().y() >= item.boundingRect().top() and \
                                    related_item.pos().y() <= item.boundingRect().bottom():
                                        number = int(related_item.toPlainText())
                                        balloon_row = number - 1  # Convert from 1-based to 0-based
                                        balloon_item = item
                                        break
                                except (ValueError, AttributeError):
                                    pass

                # If we found a balloon, show tooltip with table data
                if balloon_item and balloon_row is not None:
                    # Validate row number is within range
                    if 0 <= balloon_row < self.ui.dimtable.rowCount():
                        # Create tooltip if it doesn't exist
                        if not hasattr(self, 'balloon_tooltip') or not self.balloon_tooltip:
                            self.balloon_tooltip = QtWidgets.QDialog(self)
                            self.balloon_tooltip.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
                            self.balloon_tooltip.setAttribute(Qt.WA_TranslucentBackground)
                            self.balloon_tooltip.setStyleSheet("""
                                QDialog {
                                    background-color: rgba(255, 255, 255, 240);
                                    border: 1px solid #aaa;
                                    border-radius: 5px;
                                }
                                QLabel {
                                    color: #333;
                                    font-size: 12px;
                                    padding: 2px;
                                }
                                QLabel.header {
                                    font-weight: bold;
                                    background-color: #f0f0f0;
                                    border-bottom: 1px solid #ddd;
                                }
                            """)

                            # Create layout
                            tooltip_layout = QtWidgets.QVBoxLayout(self.balloon_tooltip)
                            tooltip_layout.setContentsMargins(10, 10, 10, 10)
                            tooltip_layout.setSpacing(5)

                            # Create content widget
                            self.tooltip_content = QtWidgets.QWidget()
                            content_layout = QtWidgets.QVBoxLayout(self.tooltip_content)
                            content_layout.setContentsMargins(0, 0, 0, 0)
                            content_layout.setSpacing(5)

                            tooltip_layout.addWidget(self.tooltip_content)

                        # Update tooltip content
                        self.display_tooltip_content(balloon_row)

                        # Position tooltip near cursor but not under it
                        global_pos = self.ui.pdf_view.viewport().mapToGlobal(event.pos())
                        self.balloon_tooltip.move(global_pos + QtCore.QPoint(15, 15))

                        # Show tooltip
                        self.balloon_tooltip.show()

                        # Return without calling original handler
                        return
                    else:
                        print(f"Invalid balloon row: {balloon_row}, max rows: {self.ui.dimtable.rowCount()}")
                else:
                    # Hide tooltip if no balloon is under cursor
                    if hasattr(self, 'balloon_tooltip') and self.balloon_tooltip:
                        self.balloon_tooltip.hide()

            # Call original handler for other cases
            if hasattr(self, 'original_mouse_move'):
                self.original_mouse_move(event)

        except Exception as e:
            print(f"Error handling properties mouse move: {str(e)}")
            import traceback
            traceback.print_exc()

            # Call original handler if there's an error
            if hasattr(self, 'original_mouse_move'):
                self.original_mouse_move(event)

    def display_tooltip_content(self, row):
        """Update the tooltip content with table data for the given row"""
        try:
            # Clear existing content
            if hasattr(self, 'tooltip_content'):
                # Remove all widgets from layout
                layout = self.tooltip_content.layout()
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()

            # Add title
            title = QtWidgets.QLabel(f"Balloon {row + 1} Details")
            title.setAlignment(Qt.AlignCenter)
            title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
            self.tooltip_content.layout().addWidget(title)

            # Create table for data
            data_table = QtWidgets.QTableWidget()
            data_table.setColumnCount(2)
            data_table.setHorizontalHeaderLabels(["Field", "Value"])
            data_table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            data_table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            data_table.verticalHeader().setVisible(False)
            data_table.setStyleSheet("""
                QTableWidget {
                    border: 1px solid;
                    background-color: #add8e6;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 5px;
                    border: 1px solid #ddd;
                    font-weight: bold;
                }
            """)

            # Get column headers from main table
            headers = []
            for col in range(1, self.ui.dimtable.columnCount()):  # Skip serial number column
                header = self.ui.dimtable.horizontalHeaderItem(col)
                if header:
                    headers.append(header.text())
                else:
                    headers.append(f"Column {col}")

            # Add data rows
            data_rows = []
            for col in range(1, self.ui.dimtable.columnCount()):  # Skip serial number column
                item = self.ui.dimtable.item(row, col)
                if item:
                    field = headers[col-1]
                    value = item.text()
                    data_rows.append((field, value))

            # Set row count and populate table
            data_table.setRowCount(len(data_rows))
            for i, (field, value) in enumerate(data_rows):
                data_table.setItem(i, 0, QTableWidgetItem(field))
                data_table.setItem(i, 1, QTableWidgetItem(value))

            # Add table to tooltip
            self.tooltip_content.layout().addWidget(data_table)

            # Resize tooltip to fit content
            self.balloon_tooltip.adjustSize()

        except Exception as e:
            print(f"Error updating tooltip content: {str(e)}")
            import traceback
            traceback.print_exc()


    def show_project_overview(self):
        """Display project overview information in a styled message box"""
        try:
            if not self.current_order_details:
                QMessageBox.warning(self, "No Data", "No order details available")
                return

            # Create styled HTML message
            message = f"""
            <html>
            <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 20px;
                    padding: 10px
                }}
                .login-info {{
                    display: inline-block;
                }}
                .welcome-text {{
                    font-size: 24px;
                    margin-bottom: 8px;
                }}
                .username {{
                    color: #0078D4;
                    font-weight: bold;
                    font-size: 26px;
                }}
                .role {{
                    color: #666;
                    margin-top: 5px;
                    font-size: 16px;
                }}
                .section-title {{
                    color: #333;
                    font-weight: bold;
                    margin: 15px 0;
                    padding-bottom: 5px;
                    border-bottom: 2px solid #0078D4;
                }}
                .details-table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-top: 10px;
                    border: 2px solid #0078D4;
                }}
                .details-table td {{
                    padding: 8px;
                    border: 1px solid #ccc;
                }}
                .label {{
                    color: #666;
                    font-weight: bold;
                    width: 30%;
                    background-color: #f5f5f5;
                    border-right: 2px solid #0078D4;
                }}
                .value {{
                    color: #333;
                }}
            </style>
            </head>
            <body>
                <div class="header">
                    <div class="login-info">
                        <div class="welcome-text">Welcome <span class="username">{api.username}</span></div>
                        <div class="role">Logged in as: {api.user_role}</div>
                    </div>
                </div>
                <div class="section-title">Order Details</div>
                <table class="details-table">
            """

            # Get operation data if available
            operation_data = None
            operation_number = "N/A"
            operation_description = "N/A"
            work_center = "N/A"
            setup_time = "N/A"
            ideal_cycle_time = "N/A"

            if hasattr(self, 'operations_dialog'):
                if hasattr(self.operations_dialog, 'get_operation_number'):
                    operation_number = str(self.operations_dialog.get_operation_number() or 'N/A')

                if hasattr(self.operations_dialog, 'get_selected_operation'):
                    operation_data = self.operations_dialog.get_selected_operation()
                    if operation_data:
                        operation_description = operation_data.get('operation_description', 'N/A')
                        work_center = operation_data.get('work_center', 'N/A')
                        setup_time = str(operation_data.get('setup_time', 'N/A'))
                        ideal_cycle_time = str(operation_data.get('ideal_cycle_time', 'N/A'))

            # Add order details in table format
            details = [
                ("Part Number:", self.current_order_details.get('part_number', 'N/A')),
                ("Production Order:", self.current_order_details.get('production_order', 'N/A')),
                ("Required Quantity:", str(self.current_order_details.get('required_quantity', 'N/A'))),
                ("Part Description:", self.current_order_details.get('part_description', 'N/A')),
                ("Sale Order:", self.current_order_details.get('sale_order', 'N/A')),
                ("Total Operations:", str(self.current_order_details.get('total_operations', 'N/A')))
            ]

            # Add project details if available
            if 'project' in self.current_order_details:
                project = self.current_order_details['project']
                details.extend([
                    ("Project Name:", project.get('name', 'N/A')),
                    ("Priority:", str(project.get('priority', 'N/A'))),
                    ("Start Date:", project.get('start_date', 'N/A')),
                    ("End Date:", project.get('end_date', 'N/A'))
                ])

            # Add rows to table
            for label, value in details:
                message += f"""
                    <tr>
                        <td class="label">{label}</td>
                        <td class="value">{value}</td>
                    </tr>
                """

            # Add operation details section
            message += """
                </table>
                <div class="section-title">Operation Details</div>
                <table class="details-table">
            """

            # Add operation details
            operation_details = [
                ("Operation Number:", operation_number),
                ("Operation Description:", operation_description),
                ("Work Center:", work_center),
                ("Setup Time:", setup_time),
                ("Ideal Cycle Time:", ideal_cycle_time)
            ]

            # Add operation details rows
            for label, value in operation_details:
                message += f"""
                    <tr>
                        <td class="label">{label}</td>
                        <td class="value">{value}</td>
                    </tr>
                """

            # Close HTML
            message += """
                </table>
            </body>
            </html>
            """

            # Create custom dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Project Overview")
            dialog.setMinimumWidth(500)

            # Create layout
            layout = QtWidgets.QVBoxLayout(dialog)

            # Create QLabel with HTML content
            label = QtWidgets.QLabel()
            label.setTextFormat(Qt.RichText)
            label.setOpenExternalLinks(False)
            label.setText(message)
            label.setWordWrap(True)

            # Add label to layout
            layout.addWidget(label)

            # Add OK button
            button_box = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok
            )
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)

            # Style the dialog
            dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
                QDialogButtonBox {
                    margin-top: 15px;
                }
                QPushButton {
                    background-color: #D1FFBD;
                    color: black;
                    border: none;
                    padding: 6px 20px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #106EBE;
                }
            """)

            # Show dialog
            dialog.exec_()

        except Exception as e:
            print(f"Error showing project overview: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to display project overview: {str(e)}")

    def show_bluetooth_dialog(self):
        """Show the Bluetooth connectivity dialog"""
        dialog = BluetoothDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            # Handle successful connection if needed
            pass

    def connect_to_device(self, row):
        """Connect to Bluetooth device for measurements"""
        try:
            # First show the instrument selection dialog
            dialog = MeasurementInstrumentDialog(self, is_admin=False)  # Always show full list for device connection
            if dialog.exec_() == QDialog.Accepted:
                # Get selected item
                selected = dialog.instrument_list.selectedItems()
                if not selected:
                    QMessageBox.warning(self, "Error", "No instrument selected")
                    return

                # Get instrument data from the widget
                widget = dialog.instrument_list.itemWidget(selected[0])
                if not widget:
                    QMessageBox.warning(self, "Error", "Invalid selection")
                    return

                instrument_data = widget.property("instrument_data")
                if not instrument_data:
                    QMessageBox.warning(self, "Error", "No instrument data found")
                    return

                # Get instrument name and code
                instrument_name = instrument_data['name'].split(" - ")[0]  # Get category name part
                instrument_code = instrument_data['instrument_code']

                # Update the instrument name in the Instrument column
                instrument_item = QTableWidgetItem(instrument_name)
                instrument_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 6, instrument_item)  # Instrument column

                # Add the instrument code to the Used Inst. column
                used_inst_item = QTableWidgetItem(instrument_code)
                used_inst_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 7, used_inst_item)  # Used Inst. column

                # Show connecting dialog with cancel button
                self.connecting_dialog = QtWidgets.QProgressDialog("Connecting to device...", "Cancel", 0, 0, self)
                self.connecting_dialog.setWindowTitle("Connecting")
                self.connecting_dialog.setWindowModality(Qt.WindowModal)
                self.connecting_dialog.show()
                QtWidgets.QApplication.processEvents()

                try:
                    # Get device details from API
                    endpoint = f"/quality/connectivity/instrument/{instrument_code}"
                    device_data = api._make_request(endpoint)

                    if not device_data:
                        self.connecting_dialog.close()
                        QMessageBox.warning(self, "Error", "Device not found or not configured")
                        return

                    # Extract device details
                    address = device_data.get('address')
                    uuid = device_data.get('uuid')

                    if not address or not uuid:
                        self.connecting_dialog.close()
                        QMessageBox.warning(self, "Error", "Invalid device configuration")
                        return

                    # Create and start measurement thread
                    self.measurement_thread = MeasurementThread(address, uuid, row)
                    self.measurement_thread.measurement_received.connect(
                        lambda value, col: self.update_measurement(row, col, value)
                    )
                    self.measurement_thread.error_occurred.connect(self.handle_measurement_error)
                    self.measurement_thread.connection_status.connect(self.handle_connection_status)
                    self.measurement_thread.start()

                except Exception as e:
                    self.connecting_dialog.close()
                    QMessageBox.critical(self, "Error", f"Failed to connect to device: {str(e)}")

        except Exception as e:
            if hasattr(self, 'connecting_dialog'):
                self.connecting_dialog.close()
            QMessageBox.critical(self, "Error", f"Failed to start device connection: {str(e)}")

    def handle_connection_status(self, status):
        """Handle connection status updates"""
        self.statusBar().showMessage(status)
        if status == "Connected to device":
            if hasattr(self, 'connecting_dialog'):
                self.connecting_dialog.close()
            self.statusBar().showMessage("Connected. Receiving measurements...")

    def update_measurement(self, row, column, value):
        """Update measurement value and check if mean is in range"""
        try:
            # Adjust column index for measurement values (M1, M2, M3)
            # Since we added Used Inst. column, we need to shift measurement columns by 1
            adjusted_column = column + 1

            # Create new item with center alignment
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignCenter)
            
            # Set the item in the table
            self.ui.dimtable.setItem(row, adjusted_column, item)
            
            # Calculate mean after each measurement
            measurements = []
            for col in range(8, 11):  # M1, M2, M3 columns
                item = self.ui.dimtable.item(row, col)
                if item and item.text():
                    try:
                        measurements.append(float(item.text()))
                    except ValueError:
                        continue
            
            # Update mean if we have measurements
            if measurements:
                mean = sum(measurements) / len(measurements)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 11, mean_item)  # Mean column
            
            # Check tolerance and highlight immediately
            self.check_and_highlight_row(row)
                
        except Exception as e:
            print(f"Error updating measurement: {str(e)}")

    def handle_measurement_error(self, error_message):
        """Handle measurement errors"""
        QMessageBox.critical(self, "Measurement Error", error_message)
        self.stop_measurements()

    def stop_measurements(self):
        """Stop ongoing measurements"""
        if hasattr(self, 'measurement_thread') and self.measurement_thread.isRunning():
            self.measurement_thread.stop()
            self.measurement_thread.wait()

    def handle_cell_change(self, row, column):
        """Handle cell value changes and calculate mean"""
        # Only process measurement columns (M1, M2, M3)
        if column not in [7, 8, 9]:
            return

        try:
            # Check tolerance and highlight immediately
            self.check_and_highlight_row(row)

        except Exception as e:
            print(f"Error handling cell change: {str(e)}")

    def check_and_highlight_row(self, row):
        """Check tolerance and highlight row based on mean value"""
        try:
            # Get nominal, upper and lower tolerance values
            nominal_item = self.ui.dimtable.item(row, 2)  # Nominal column
            upper_tol_item = self.ui.dimtable.item(row, 3)  # Upper tolerance column
            lower_tol_item = self.ui.dimtable.item(row, 4)  # Lower tolerance column
            
            if not all([nominal_item, upper_tol_item, lower_tol_item]):
                return
                
            nominal = float(nominal_item.text())
            upper_tol = float(upper_tol_item.text())
            lower_tol = float(lower_tol_item.text())
            
            # Calculate mean from measurement columns (8-10 now, since we added Used Inst. column)
            measurements = []
            for col in range(8, 11):  # M1, M2, M3 columns
                item = self.ui.dimtable.item(row, col)
                if item and item.text():
                    try:
                        measurements.append(float(item.text()))
                    except ValueError:
                        continue
            
            if measurements:
                mean = sum(measurements) / len(measurements)
                
                # Update mean column (now column 11)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.ui.dimtable.setItem(row, 11, mean_item)
                
                # Calculate tolerance limits
                upper_limit = nominal + upper_tol
                lower_limit = nominal + lower_tol  # Note: lower_tol should already be negative
                
                # Check if mean is within tolerance range
                is_in_range = lower_limit <= mean <= upper_limit
                
                # Set background color for all cells in the row
                for col in range(self.ui.dimtable.columnCount()):
                    item = self.ui.dimtable.item(row, col)
                    if not item:
                        item = QtWidgets.QTableWidgetItem("")
                        self.ui.dimtable.setItem(row, col, item)
                    
                    # Set custom property for styling
                    item.setData(Qt.UserRole, "true" if is_in_range else "false")
                    
                    # Apply background color
                    if is_in_range:
                        item.setBackground(QtGui.QColor("#D1FFBD"))  # Light green for valid
                    else:
                        item.setBackground(QtGui.QColor("#FFB6C1"))  # Light red for invalid
                    
                    # Ensure text alignment is maintained
                    item.setTextAlignment(Qt.AlignCenter)
        
        except (ValueError, AttributeError) as e:
            print(f"Error checking tolerance range: {str(e)}")

# Add MeasurementThread class
class MeasurementThread(QtCore.QThread):
    measurement_received = QtCore.pyqtSignal(float, int)  # Value and column number
    error_occurred = QtCore.pyqtSignal(str)
    connection_status = QtCore.pyqtSignal(str)

    def __init__(self, address, uuid, row):
        super().__init__()
        self.address = address
        self.uuid = uuid
        self.row = row
        self.running = True
        self.measurement_count = 0

    def run(self):
        """Run the measurement thread"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def notification_handler(sender: int, data: bytearray):
                try:
                    if not self.running:
                        return

                    decoded_data = data.decode('utf-8')
                    value = float(decoded_data)

                    # Determine which column to update (M1, M2, or M3)
                    column = 7 + self.measurement_count  # 7 is M1 column

                    if column <= 9:  # Only process up to M3
                        self.measurement_received.emit(value, column)
                        self.measurement_count += 1

                        if self.measurement_count >= 3:
                            self.running = False

                except Exception as e:
                    self.error_occurred.emit(f"Error processing measurement: {str(e)}")
                    self.running = False

            async def monitor_data():
                try:
                    async with BleakClient(self.address) as client:
                        self.connection_status.emit("Connected to device")
                        await client.start_notify(self.uuid, notification_handler)

                        while self.running and self.measurement_count < 3:
                            await asyncio.sleep(0.1)

                except Exception as e:
                    self.error_occurred.emit(f"Connection error: {str(e)}")
                    self.running = False

            loop.run_until_complete(monitor_data())

        except Exception as e:
            self.error_occurred.emit(f"Thread error: {str(e)}")

    def stop(self):
        """Stop the measurement thread"""
        self.running = False

if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()  # Create instance of our MainWindow class
    window.show()
    sys.exit(app.exec_())
