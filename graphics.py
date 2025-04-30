import fitz
from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtWidgets import (QGraphicsItem, QGraphicsView, QGraphicsPolygonItem, QGraphicsTextItem,
                             QTableWidgetItem, QGraphicsEllipseItem, QGraphicsRectItem, QMessageBox, QPushButton)
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF, QImage
from ultralytics import YOLO
from events import EventHandler
import os
import cv2
import numpy as np

import types
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                             QLabel, QDialogButtonBox, QComboBox)
from PyQt5.QtGui import QBrush
from highlight_manager import HighlightManager  # Update this import
from algorithms import ClusterDetector, DimensionParser
from algorithms import ZoneDetector


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, main_window, parent=None):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.main_window = main_window
        self.pdf_items = []
        self.current_rect = None
        self.bboxEditRequested = QtCore.pyqtSignal(int, object)

        # Add mode flags
        self.stamp_mode = False
        self.selection_mode = False
        self.drawing_stamp = False
        self.drawing_selection = False
        self.stamp_start = None
        self.stamp_rect = None

        try:
            self.yolo_model = YOLO(r'D:\siri\calipers\prometrix\prometrix\best.pt')
        except Exception as e:
            print(f"Error loading YOLO model: {str(e)}")
            self.yolo_model = None

        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing |
            QPainter.HighQualityAntialiasing
        )

        self.dragging = False
        self.drag_start = None

        self.deleted_boxes = []

        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Add tracking for YOLO detections
        self.yolo_detection_boxes = []  # Store YOLO detection boxes

        # Initialize zoom modes
        self.dynamic_zoom = False
        self.zoom_area_mode = False
        self.zoom_area_start = None
        self.zoom_area_rect = None
        self.last_mouse_pos = None
        self.middle_button_pressed = False

        # Add editing flag
        self.is_editing = False

    def clearOCRItems(self, clear_all=True):
        """Safely clear OCR items"""
        if clear_all:
            items_to_remove = self.pdf_items.copy()
            for item in items_to_remove:
                try:
                    if item and not item.scene() is None:  # Check if item still exists in scene
                        self.scene().removeItem(item)
                except (RuntimeError, Exception) as e:
                    print(f"Error removing item: {str(e)}")
                    continue
            self.pdf_items.clear()

            # Also clear YOLO detection boxes
            self.yolo_detection_boxes.clear()

    def updateBBoxScaling(self):
        """Update the scaling of text items only"""
        try:
            transform = self.transform()
            scale = transform.m11()

            items_to_process = self.pdf_items.copy()
            for item in items_to_process:
                try:
                    if isinstance(item, QGraphicsTextItem):
                        # Update text size based on zoom level
                        font = item.font()
                        # Maintain minimum and maximum font size
                        base_size = 10
                        new_size = max(min(base_size / scale, 20), 4)
                        font.setPointSizeF(new_size)
                        item.setFont(font)
                except Exception:
                    continue

        except Exception as e:
            print(f"Error in updateBBoxScaling: {str(e)}")

    def clearYOLODetections(self):
        """Clear stored YOLO detections"""
        self.yolo_detection_boxes = []

    def compare_bboxes(self, bbox1, bbox2):
        """Compare two bounding boxes for approximate equality"""
        if len(bbox1) != len(bbox2):
            return False

        threshold = 1.0  # Adjust this value for comparison precision
        for p1, p2 in zip(bbox1, bbox2):
            if abs(p1[0] - p2[0]) > threshold or abs(p1[1] - p2[1]) > threshold:
                return False
        return True

    def mousePressEvent(self, event):
        EventHandler.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        EventHandler.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        EventHandler.mouseReleaseEvent(self, event)

    def wheelEvent(self, event):
        EventHandler.wheelEvent(self, event)

    def keyPressEvent(self, event):
        EventHandler.keyPressEvent(self, event)

    def is_similar_text(self, text1, text2):
        """Compare two texts to check if they are similar (ignoring spaces and case)"""
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

    def enterStampMode(self):
        """Enter stamp mode for creating custom bounding boxes"""
        self.stamp_mode = True
        self.setCursor(Qt.CrossCursor)

    def exitStampMode(self):
        """Exit stamp mode"""
        self.stamp_mode = False
        self.setCursor(Qt.ArrowCursor)

    def enterSelectionMode(self):
        """Enter selection mode for area detection"""
        # Check if user has admin rights
        if not hasattr(self.main_window, 'user_role') or self.main_window.user_role != 'admin':
            return

        self.selection_mode = True
        self.setCursor(Qt.CrossCursor)
        # Disable stamp mode when entering selection mode
        self.stamp_mode = False

    def exitSelectionMode(self):
        """Exit selection mode"""
        self.selection_mode = False
        self.setCursor(Qt.ArrowCursor)
        if self.current_rect:
            self.scene().removeItem(self.current_rect)
            self.current_rect = None

    def processSelectedArea(self, rect):
        """Process only the selected area for detection"""
        try:
            x0 = rect.x()
            y0 = rect.y()
            x1 = x0 + rect.width()
            y1 = y0 + rect.height()

            clip_rect = fitz.Rect(x0 / 2, y0 / 2, x1 / 2, y1 / 2)

            # Get existing bounding boxes from the table
            existing_boxes = []
            for row in range(self.main_window.ui.dimtable.rowCount()):
                item = self.main_window.ui.dimtable.item(row, 2)  # Nominal column
                if item:
                    bbox = item.data(Qt.UserRole)
                    if bbox:
                        existing_boxes.append(bbox)

            print(f"Found {len(existing_boxes)} existing bounding boxes")

            # Get text using PyMuPDF
            fitz_dict = self.main_window.loaded_page.get_text("dict", clip=clip_rect)['blocks']
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

                            # Check if this detection overlaps with existing boxes
                            is_overlapping = False
                            for existing_box in existing_boxes:
                                if self.calculate_iou(scene_box, existing_box) > 0.3:
                                    print(f"Skipping PDF detection - overlaps with existing box")
                                    is_overlapping = True
                                    break

                            if not is_overlapping:
                                pdf_results.append({
                                    'text': dimension,
                                    'box': scene_box,
                                    'confidence': 1.0,  # PyMuPDF doesn't provide confidence
                                    'rotation': 0
                                })

            # Process YOLO detection for the selected area
            yolo_results = []
            if self.yolo_model:
                try:
                    # Convert scene coordinates to image coordinates
                    scene_rect = QRectF(x0, y0, rect.width(), rect.height())

                    # Create a QImage of the selected area with RGBA format
                    width = int(rect.width())
                    height = int(rect.height())
                    image = QImage(width, height, QImage.Format_RGBA8888)
                    image.fill(Qt.white)

                    # Create painter to render the scene portion
                    painter = QPainter(image)
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setRenderHint(QPainter.SmoothPixmapTransform)

                    # Set up the viewport transformation to render only the selected area
                    self.scene().render(painter, QRectF(0, 0, width, height), scene_rect)
                    painter.end()

                    # Convert QImage to numpy array
                    bits = image.constBits()
                    bits.setsize(height * width * 4)  # 4 channels (RGBA)
                    arr = np.frombuffer(bits, np.uint8).reshape(height, width, 4)

                    # Convert RGBA to BGR for YOLO
                    img_np = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

                    # Save debug image
                    cv2.imwrite('selected_area_debug.png', img_np)

                    # Run YOLO detection
                    results = self.yolo_model(img_np)
                    for result in results:
                        boxes = result.boxes
                        for box in boxes:
                            if box.conf.item() >= 0.5:  # Confidence threshold
                                # Get coordinates
                                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                                # Convert coordinates to scene coordinates
                                scene_x1 = x0 + x1
                                scene_y1 = y0 + y1
                                scene_x2 = x0 + x2
                                scene_y2 = y0 + y2

                                yolo_box = [
                                    [scene_x1, scene_y1],
                                    [scene_x2, scene_y1],
                                    [scene_x2, scene_y2],
                                    [scene_x1, scene_y2]
                                ]

                                # Check if this detection overlaps with existing boxes
                                is_overlapping = False
                                for existing_box in existing_boxes:
                                    if self.calculate_iou(yolo_box, existing_box) > 0.3:
                                        print(f"Skipping YOLO detection - overlaps with existing box")
                                        is_overlapping = True
                                        break

                                if not is_overlapping:
                                    yolo_results.append({
                                        'box': yolo_box,
                                        'confidence': box.conf.item(),
                                        'class': int(box.cls),
                                        'class_name': result.names[int(box.cls)]
                                    })

                    print(f"Found {len(yolo_results)} new YOLO detections")

                except Exception as e:
                    print(f"Error in YOLO processing: {str(e)}")
                    import traceback
                    traceback.print_exc()

            # Only add new detections that don't overlap with existing ones
            if pdf_results or yolo_results:
                print(f"\n=== Processing New Detections ===")
                print(f"New PDF detections: {len(pdf_results)}")
                print(f"New YOLO detections: {len(yolo_results)}")

                # Update the main window's detections with only new detections
                self.main_window.ocr_results.extend(pdf_results)
                self.main_window.all_detections['yolo'].extend(yolo_results)

                # Process results with clustering
                ClusterDetector.cluster_detections(
                    self.main_window,
                    pdf_results,  # Only pass new PDF results
                    yolo_results,  # Only pass new YOLO results
                    DimensionParser,
                    clear_existing=False  # Don't clear existing items
                )

        except Exception as e:
            print(f"Error processing selected area: {str(e)}")
            import traceback
            traceback.print_exc()

    def calculate_iou(self, box1, box2):
        """Calculate Intersection over Union between two bounding boxes"""
        try:
            # Convert boxes to QRectF for easier calculation
            def box_to_rect(box):
                x_coords = [p[0] for p in box]
                y_coords = [p[1] for p in box]
                return QRectF(
                    min(x_coords),
                    min(y_coords),
                    max(x_coords) - min(x_coords),
                    max(y_coords) - min(y_coords)
                )

            rect1 = box_to_rect(box1)
            rect2 = box_to_rect(box2)

            # Calculate intersection
            intersection = rect1.intersected(rect2)
            if intersection.isEmpty():
                return 0.0

            intersection_area = intersection.width() * intersection.height()

            # Calculate areas
            area1 = rect1.width() * rect1.height()
            area2 = rect2.width() * rect2.height()

            # Calculate IoU
            union_area = area1 + area2 - intersection_area

            return intersection_area / union_area if union_area > 0 else 0.0

        except Exception as e:
            print(f"Error calculating IoU: {str(e)}")
            return 0.0

    def addCustomBBox(self, points, dimension_data):
        """Add custom bounding box with dimension data"""
        try:
            row_count = self.main_window.ui.dimtable.rowCount()
            self.main_window.ui.dimtable.insertRow(row_count)

            # Set serial number (1-based)
            serial_number = row_count + 1
            self.main_window.ui.dimtable.setItem(row_count, 0,
                                                 QtWidgets.QTableWidgetItem(str(serial_number)))

            # Calculate midpoint for zone detection
            midpoint_x = sum(p[0] for p in points) / len(points)
            midpoint_y = sum(p[1] for p in points) / len(points)
            midpoint = (midpoint_x, midpoint_y)

            # Get zone for this midpoint
            zone = ZoneDetector.get_zone_for_midpoint(self.main_window, midpoint)

            # Set zone value
            self.main_window.ui.dimtable.setItem(row_count, 1,
                                                 QtWidgets.QTableWidgetItem(zone))

            # Set nominal value and store bbox with stamped flag
            nominal_item = QtWidgets.QTableWidgetItem(dimension_data.get('nominal', ''))
            nominal_item.setData(QtCore.Qt.UserRole, points)
            nominal_item.setData(QtCore.Qt.UserRole + 1, "stamped")  # Mark as stamped
            self.main_window.ui.dimtable.setItem(row_count, 2, nominal_item)

            # Set tolerance values
            self.main_window.ui.dimtable.setItem(row_count, 3,
                                                 QtWidgets.QTableWidgetItem(dimension_data.get('upper_tol', '')))
            self.main_window.ui.dimtable.setItem(row_count, 4,
                                                 QtWidgets.QTableWidgetItem(dimension_data.get('lower_tol', '')))
            self.main_window.ui.dimtable.setItem(row_count, 5,
                                                 QtWidgets.QTableWidgetItem(dimension_data.get('dim_type', '')))

            # Add visualization bbox with distinct color for stamped items
            bbox_item = QtWidgets.QGraphicsPolygonItem(
                QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points])
            )
            pen = QtGui.QPen(QtGui.QColor(255, 165, 0))  # Orange color for stamped items
            pen.setWidth(2)
            pen.setCosmetic(True)
            bbox_item.setPen(pen)
            bbox_item.setZValue(10)

            self.scene().addItem(bbox_item)
            self.pdf_items.append(bbox_item)

            # Add balloon for the new bbox with correct serial number
            from highlight_manager import HighlightManager
            balloon_items = HighlightManager.create_balloon(self, points, serial_number)  # Adjust for 1-based index
            for balloon_item in balloon_items:
                balloon_item.balloon_data = {'table_row': serial_number, 'bbox': points}
                self.scene().addItem(balloon_item)
                # self.ocr_items.append(balloon_item)  # Add to ocr_items for tracking

            print(f"Added custom bbox at {midpoint} in zone {zone}")

        except Exception as e:
            print(f"Error adding custom bbox: {str(e)}")
            import traceback
            traceback.print_exc()

    def highlight_bbox(self, bbox, row_number):
        """Highlight a bounding box and show its row number"""
        try:
            # Clear any existing highlights
            self.main_window.clear_highlighted_bbox()

            # Create balloon elements with red color (no highlight for bbox)
            balloon_items = HighlightManager.create_balloon(self, bbox, row_number, highlight_color=QColor(255, 0, 0))

            if balloon_items:
                self.main_window.balloon_circle = balloon_items[0]
                self.main_window.balloon_triangle = balloon_items[1]
                self.main_window.balloon_text = balloon_items[2]

                for item in balloon_items:
                    self.scene().addItem(item)

        except Exception as e:
            print(f"Error in highlight_bbox: {str(e)}")

    def get_balloon_bboxes(self, row):
        """Get all balloon bboxes for a specific row"""
        balloon_bboxes = []

        for item in self.scene().items():
            if hasattr(item, 'balloon_data'):
                balloon_data = item.balloon_data
                if balloon_data.get('table_row') == row:
                    bbox = balloon_data['bbox']
                    try:
                        if isinstance(bbox[0], list):  # Format: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                            # Convert to 8-point format
                            converted_bbox = [
                                float(bbox[0][0]), float(bbox[0][1]),  # Top-left
                                float(bbox[1][0]), float(bbox[1][1]),  # Top-right
                                float(bbox[2][0]), float(bbox[2][1]),  # Bottom-right
                                float(bbox[3][0]), float(bbox[3][1])  # Bottom-left
                            ]
                        elif len(bbox) == 8:  # Already in correct format
                            converted_bbox = [float(x) for x in bbox]
                        elif len(bbox) == 4:  # Format: [x1,y1,x2,y2]
                            converted_bbox = [
                                float(bbox[0]), float(bbox[1]),  # Top-left
                                float(bbox[2]), float(bbox[1]),  # Top-right
                                float(bbox[2]), float(bbox[3]),  # Bottom-right
                                float(bbox[0]), float(bbox[3])  # Bottom-left
                            ]
                        else:
                            print(f"Invalid bbox format: {bbox}")
                            continue
                        balloon_bboxes.append(converted_bbox)
                        print(f"Converted balloon bbox: {converted_bbox}")
                    except (TypeError, ValueError, IndexError) as e:
                        print(f"Error converting balloon bbox: {e}")
                        print(f"Balloon bbox format: {bbox}")
                        continue

        return balloon_bboxes

    def get_all_bboxes_for_row(self, row):
        """Get all bboxes (detection and balloon) for a specific row"""
        bboxes = []

        # Get detection bboxes
        item = self.main_window.ui.dimtable.item(row, 2)  # Nominal column
        if item:
            detection_bbox = item.data(Qt.UserRole)
            if detection_bbox:
                try:
                    if isinstance(detection_bbox[0], list):  # Format: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                        converted_bbox = [
                            float(detection_bbox[0][0]), float(detection_bbox[0][1]),  # Top-left
                            float(detection_bbox[1][0]), float(detection_bbox[1][1]),  # Top-right
                            float(detection_bbox[2][0]), float(detection_bbox[2][1]),  # Bottom-right
                            float(detection_bbox[3][0]), float(detection_bbox[3][1])  # Bottom-left
                        ]
                    elif len(detection_bbox) == 8:  # Already in correct format
                        converted_bbox = [float(x) for x in detection_bbox]
                    else:
                        print(f"Invalid detection bbox format: {detection_bbox}")
                        return bboxes
                    bboxes.append(converted_bbox)
                    print(f"Converted detection bbox: {converted_bbox}")
                except (TypeError, ValueError, IndexError) as e:
                    print(f"Error converting detection bbox: {e}")
                    print(f"Detection bbox format: {detection_bbox}")

        # Get balloon bboxes
        balloon_bboxes = self.get_balloon_bboxes(row)
        bboxes.extend(balloon_bboxes)

        return bboxes

    def handle_cell_change(self, row, column):
        """Handle cell value changes and calculate mean"""
        # Only process measurement columns (M1, M2, M3)
        if column not in [7, 8, 9]:
            return

        try:
            # Get measurements
            measurements = []
            for col in [7, 8, 9]:
                item = self.main_window.ui.dimtable.item(row, col)
                if item and item.text().strip():
                    try:
                        value = float(item.text())
                        measurements.append(value)
                    except ValueError:
                        continue

            # Calculate and display mean if we have measurements
            if measurements:
                mean = sum(measurements) / len(measurements)
                mean_item = QtWidgets.QTableWidgetItem(f"{mean:.3f}")
                mean_item.setTextAlignment(Qt.AlignCenter)
                self.main_window.ui.dimtable.setItem(row, 10, mean_item)

        except Exception as e:
            print(f"Error calculating mean: {str(e)}")