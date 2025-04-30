import cv2
import numpy as np
import math
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QRectF
import re
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QTableWidgetItem, QGraphicsPolygonItem
from PyQt5.QtWidgets import QGraphicsLineItem
from PyQt5.QtGui import QPen, QPolygonF, QColor
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QImage, QPainter

import os

from highlight_manager import HighlightManager


class DimensionParser:
    @staticmethod
    def is_dimensional_value(text):
        """Check if text likely represents a dimensional value"""
        text = text.strip().lower()

        # Skip single + or - characters
        if text in ['+', '-']:
            return False

        # Check if it's a tolerance value starting with + or -
        if text.startswith('+') or text.startswith('-'):
            try:
                float(text.replace(',', '.'))
                return True
            except ValueError:
                return False

        # Remove common prefixes for dimension check
        for prefix in ['ø', 'r', 'm', '±', '∅']:
            text = text.replace(prefix, '')

        if '°' in text:
            text = text.replace('°', '')
            try:
                float(text)
                return True
            except ValueError:
                return False

        dimensional_pattern = r'^-?\d*\.?\d+$|^-?\d+,\d+$'
        tolerance_pattern = r'±?\d*\.?\d+|\+\d*\.?\d+/-\d*\.?\d+'

        text = text.replace(',', '.')
        return bool(re.match(dimensional_pattern, text) or re.match(tolerance_pattern, text))

    @staticmethod
    def determine_dimension_type(text, nominal_value):
        """Determine the dimension type based on the text and nominal value"""
        # Check for Radius
        if text.startswith('R') or text.startswith('r'):
            return "Radius"

        # Check for Reference dimensions (in parentheses)
        if text.startswith("(") and text.endswith(")"):
            inner_text = text[1:-1].strip()
            if inner_text.startswith('R') or inner_text.startswith('r'):
                return "Radius-Reference"
            elif '°' in inner_text:
                return "Angular-Reference"
            else:
                return "Length-Reference"

        # Check for Angular dimensions
        if '°' in text:
            if 'x' in text.lower():
                return "Chamfer"
            return "Angular"

        # Check for Thread dimensions
        match = re.search(r'M(\d{1,2})', text)
        if match:
            return "Thread"

        # Default to Length
        return "Length"

    @staticmethod
    def parse_dimension(text):
        """Parse dimension text to extract nominal value, tolerances, and type"""
        try:
            text = text.strip()
            nominal_value = ""
            upper_tol = ""
            lower_tol = ""
            dim_type = "Length"  # default type

            # Remove spaces
            text = ''.join(text.split())

            # Handle pure tolerance values
            if text.startswith('+'):
                nominal_value = ""
                upper_tol = text  # Keep the entire text including +
                lower_tol = "0"
                dim_type = "Tolerance"
                return dim_type, upper_tol, lower_tol, nominal_value

            # Handle THRU dimensions
            if "THRU" in text.upper():
                numeric_part = text.upper().split("THRU")[0].strip()
                return "THRU", "0", "0", numeric_part

            if '±' in text:
                parts = text.split('±')
                nominal_value = parts[0].strip()
                if len(parts) > 1:
                    tol = parts[1].strip().split()[0]
                    upper_tol = f"+{tol}"
                    lower_tol = f"-{tol}"

            elif '+' in text and not text.startswith('+'):
                # Handle + similar to ± symbol
                parts = text.split('+')
                nominal_value = parts[0].strip()
                if len(parts) > 1:
                    tol = parts[1].strip().split()[0]
                    upper_tol = f"+{tol}"
                    lower_tol = f"0"

            elif '+' in text and text.startswith('+'):
                # Handle pure tolerance values
                nominal_value = ""
                upper_tol = text  # Keep the entire text including + as upper tolerance
                lower_tol = "0"
                dim_type = "Tolerance"

            else:
                nominal_value = text
                upper_tol = "0"
                lower_tol = "0"

            # Clean up nominal value
            nominal_value = ''.join(nominal_value.split())

            # Special handling for reference dimensions
            if text.startswith("(") and text.endswith(")"):
                nominal_value = text  # Keep the full text including parentheses
                upper_tol = ""
                lower_tol = ""

            # Determine dimension type
            dim_type = DimensionParser.determine_dimension_type(text, nominal_value)

            return dim_type, upper_tol, lower_tol, nominal_value

        except Exception as e:
            print(f"Error parsing dimension: {str(e)}")
            return "Length", "0", "0", text


class ImageProcessor:
    @staticmethod
    def find_innermost_boundary(image):
        """Find the innermost boundary rectangle that contains the main technical drawing"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        # Find contours with RETR_TREE to get hierarchy
        contours, hierarchy = cv2.findContours(
            thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        height, width = image.shape[:2]
        valid_rectangles = []

        # Process each contour
        for i, cnt in enumerate(contours):
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)

            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            rect_area = w * h

            is_valid = (
                    len(approx) >= 4 and
                    w > width * 0.1 and h > height * 0.1 and
                    abs(area - rect_area) / rect_area < 0.4 and
                    x >= 0 and y >= 0
            )

            if is_valid:
                valid_rectangles.append({
                    'contour': cnt,
                    'area': area,
                    'rect': (x, y, w, h)
                })

        if not valid_rectangles:
            return None, None

        valid_rectangles.sort(key=lambda x: x['area'], reverse=True)
        main_rect = valid_rectangles[1]['rect'] if len(valid_rectangles) > 1 else valid_rectangles[0]['rect']
        main_cnt = valid_rectangles[1]['contour'] if len(valid_rectangles) > 1 else valid_rectangles[0]['contour']

        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(mask, [main_cnt], -1, 255, -1)

        return mask, main_rect

    @staticmethod
    def enhance_image(image):
        """Enhance the image for better OCR results"""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply CLAHE with adjusted parameters
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Apply bilateral filter to reduce noise while preserving edges
        filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)

        # Apply adaptive thresholding
        binary = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        return binary


class BoundingBoxUtils:
    @staticmethod
    def is_box_contained(inner_box, outer_box):
        """Check if one bbox is contained within another"""
        # Get bounds of inner box
        inner_x1 = min(p[0] for p in inner_box)
        inner_y1 = min(p[1] for p in inner_box)
        inner_x2 = max(p[0] for p in inner_box)
        inner_y2 = max(p[1] for p in inner_box)

        # Get bounds of outer box
        outer_x1 = min(p[0] for p in outer_box)
        outer_y1 = min(p[1] for p in outer_box)
        outer_x2 = max(p[0] for p in outer_box)
        outer_y2 = max(p[1] for p in outer_box)

        # Check if inner box is contained within outer box
        # Add small margin (1 pixel) for floating point comparison
        margin = 1
        return (inner_x1 >= outer_x1 - margin and inner_x2 <= outer_x2 + margin and
                inner_y1 >= outer_y1 - margin and inner_y2 <= outer_y2 + margin)

    @staticmethod
    def calculate_iou(box1, box2):
        """Calculate Intersection over Union (IoU) between two bounding boxes."""

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


class ClusterDetector:
    @staticmethod
    def check_yolo_association(pdf_box, yolo_box):
        """Check if PDF box and YOLO box are associated based on geometric rules"""
        CLUSTER_X = 30  # Horizontal clustering threshold
        CLUSTER_Y_HORIZONTAL = 20  # Vertical threshold for horizontal clustering
        CLUSTER_Y_VERTICAL = 40  # Increased vertical threshold for vertical GDT
        
        # Get box bounds
        pdf_x1 = min(p[0] for p in pdf_box)
        pdf_y1 = min(p[1] for p in pdf_box)
        pdf_x2 = max(p[0] for p in pdf_box)
        pdf_y2 = max(p[1] for p in pdf_box)
        
        yolo_x1 = min(p[0] for p in yolo_box)
        yolo_y1 = min(p[1] for p in yolo_box)
        yolo_x2 = max(p[0] for p in yolo_box)
        yolo_y2 = max(p[1] for p in yolo_box)

        # Calculate centers
        pdf_center_x = (pdf_x1 + pdf_x2) / 2
        pdf_center_y = (pdf_y1 + pdf_y2) / 2
        yolo_center_x = (yolo_x1 + yolo_x2) / 2
        yolo_center_y = (yolo_y1 + yolo_y2) / 2

        # Calculate box dimensions to determine if GDT is vertical
        pdf_height = pdf_y2 - pdf_y1
        pdf_width = pdf_x2 - pdf_x1
        is_vertical_gdt = pdf_height > pdf_width * 1.2  # GDT symbol is taller than wide

        if is_vertical_gdt:
            # For vertical GDT, check for text above only
            if pdf_y2 < yolo_y1:  # Text must be above GDT
                x_dist = abs(pdf_center_x - yolo_center_x)  # Horizontal alignment check
                y_dist = yolo_y1 - pdf_y2   # Vertical distance between text bottom and GDT top
                
                # Print debug information
                print(f"Vertical GDT check:")
                print(f"x_dist: {x_dist}, y_dist: {y_dist}")
                print(f"Text bounds: ({pdf_x1}, {pdf_y1}) to ({pdf_x2}, {pdf_y2})")
                print(f"GDT bounds: ({yolo_x1}, {yolo_y1}) to ({yolo_x2}, {yolo_y2})")
                
                # Stricter horizontal alignment for vertical GDT
                if (x_dist <= CLUSTER_X * 0.5 and  # Tighter horizontal alignment
                    0 <= y_dist <= CLUSTER_Y_VERTICAL):  # Vertical spacing check
                    print("Vertical GDT association found!")
                    return True, "vertical"
        else:
            # For horizontal symbols, check for text on right side only
            if pdf_x1 > yolo_x2:  # Text is on right side
                x_dist = pdf_x1 - yolo_x2  # Distance between symbol right edge and text left edge
                y_dist = abs(pdf_center_y - yolo_center_y)  # Vertical alignment
                
                if 0 <= x_dist <= CLUSTER_X and y_dist <= CLUSTER_Y_HORIZONTAL:
                    return True, "horizontal"

        return False, None

    @staticmethod
    def get_dimension_type(yolo_class):
        """Convert YOLO class to dimension type"""
        if yolo_class == 'A':
            return "Diameter"
        elif yolo_class in [chr(c) for c in range(ord('B'), ord('Z') + 1)]:
            return "Length"
        else:
            return f"GDT:{yolo_class}"

    @staticmethod
    def cluster_detections(window, pdf_results, yolo_detections, dimension_parser, clear_existing=True):
        try:
            # Initialize empty lists if inputs are None
            pdf_results = pdf_results or []
            yolo_detections = yolo_detections or []

            print("\n=== Starting Clustering Process ===")
            print(f"Processing {len(pdf_results)} PDF results and {len(yolo_detections)} YOLO detections")

            # Adjust clustering thresholds
            CLUSTER_X = 100  # Increased for better horizontal matching
            CLUSTER_Y = 20
            OVERLAP_THRESHOLD = 0.3  # IOU threshold for overlap detection

            # Store stamped items before clearing if needed
            stamped_items = []
            if clear_existing:
                for row in range(window.ui.dimtable.rowCount()):
                    item = window.ui.dimtable.item(row, 2)  # Nominal column
                    if item and item.data(Qt.UserRole + 1) == "stamped":
                        stamped_data = {
                            'bbox': item.data(Qt.UserRole),
                            'nominal': item.text(),
                            'upper_tol': window.ui.dimtable.item(row, 3).text() if window.ui.dimtable.item(row,
                                                                                                           3) else "",
                            'lower_tol': window.ui.dimtable.item(row, 4).text() if window.ui.dimtable.item(row,
                                                                                                           4) else "",
                            'dim_type': window.ui.dimtable.item(row, 5).text() if window.ui.dimtable.item(row,
                                                                                                          5) else ""
                        }
                        stamped_items.append(stamped_data)

                # Clear existing table and scene items
                window.ui.dimtable.setRowCount(0)
                window.ui.pdf_view.clearOCRItems()

                # Restore stamped items
                ClusterDetector._restore_stamped_items(window, stamped_items)

            # Store all bboxes for overlap checking
            all_bboxes = []
            merged_boxes = []

            # Normalize YOLO boxes to polygon format
            normalized_yolo = []
            for yolo_det in yolo_detections:
                box = yolo_det['box']
                if not isinstance(box[0], list):  # If box is in [x1,y1,x2,y2] format
                    x1, y1, x2, y2 = box
                    normalized_box = [
                        [x1, y1],
                        [x2, y1],
                        [x2, y2],
                        [x1, y2]
                    ]
                    normalized_yolo.append({
                        **yolo_det,
                        'box': normalized_box
                    })
                else:
                    normalized_yolo.append(yolo_det)

            # Process each PDF text detection
            for pdf_det in pdf_results:
                try:
                    text = pdf_det['text'].strip()
                    if not text:
                        continue

                    pdf_box = pdf_det['box']
                    if not pdf_box:
                        continue

                    # Skip if not a dimensional value
                    if not (text.startswith('+') or dimension_parser.is_dimensional_value(text)):
                        continue

                    print(f"\nProcessing PDF detection: {text}")
                    print(f"PDF box: {pdf_box}")

                    # Get PDF box bounds
                    pdf_x1 = min(p[0] for p in pdf_box)
                    pdf_y1 = min(p[1] for p in pdf_box)
                    pdf_x2 = max(p[0] for p in pdf_box)
                    pdf_y2 = max(p[1] for p in pdf_box)
                    pdf_center_x = (pdf_x1 + pdf_x2) / 2
                    pdf_center_y = (pdf_y1 + pdf_y2) / 2

                    # Handle potential tolerance values
                    if text in ['+', '-']:
                        pdf_center_y = sum(p[1] for p in pdf_box) / len(pdf_box)
                        pdf_center_x = sum(p[0] for p in pdf_box) / len(pdf_box)
                        
                        # Store info about all nearby text elements
                        nearby_texts = []
                        
                        # Look for text near this + symbol
                        for other_det in pdf_results:
                            if other_det == pdf_det:
                                continue
                                
                            other_text = other_det['text'].strip()
                            if other_text in ['+', '-']:
                                continue
                                
                            other_box = other_det['box']
                            other_center_y = sum(p[1] for p in other_box) / len(other_box)
                            other_center_x = sum(p[0] for p in other_box) / len(other_box)
                            
                            # Check both vertical and horizontal alignments
                            if abs(other_center_x - pdf_center_x) < CLUSTER_X:
                                # Vertical alignment check
                                y_dist = abs(other_center_y - pdf_center_y)
                                if y_dist < CLUSTER_Y:
                                    if dimension_parser.is_dimensional_value(other_text):
                                        nearby_texts.append({
                                            'text': other_text,
                                            'box': other_box,
                                            'center_y': other_center_y,
                                            'center_x': other_center_x,
                                            'distance': y_dist,
                                            'alignment': 'vertical'
                                        })
                            elif abs(other_center_y - pdf_center_y) < CLUSTER_Y:
                                # Horizontal alignment check
                                x_dist = abs(other_center_x - pdf_center_x)
                                if x_dist < CLUSTER_X:
                                    if dimension_parser.is_dimensional_value(other_text):
                                        nearby_texts.append({
                                            'text': other_text,
                                            'box': other_box,
                                            'center_y': other_center_y,
                                            'center_x': other_center_x,
                                            'distance': x_dist,
                                            'alignment': 'horizontal'
                                        })
                        
                        # Sort nearby texts based on their position
                        # For vertical alignment, sort by Y coordinate
                        vertical_texts = [t for t in nearby_texts if t['alignment'] == 'vertical']
                        vertical_texts.sort(key=lambda x: x['center_y'])
                        
                        # For horizontal alignment, sort by X coordinate
                        horizontal_texts = [t for t in nearby_texts if t['alignment'] == 'horizontal']
                        horizontal_texts.sort(key=lambda x: x['center_x'])
                        
                        # Use either vertical or horizontal texts based on which has more matches
                        nearby_texts = vertical_texts if len(vertical_texts) >= len(horizontal_texts) else horizontal_texts
                        
                        # First text found is nominal, second is tolerance
                        if len(nearby_texts) >= 2:
                            nominal_text = nearby_texts[0]['text']
                            upper_tol = f"+{nearby_texts[1]['text']}"
                            all_points = nearby_texts[0]['box'] + pdf_box + nearby_texts[1]['box']
                        elif len(nearby_texts) == 1:
                            nominal_text = ""
                            upper_tol = f"+{nearby_texts[0]['text']}"
                            all_points = pdf_box + nearby_texts[0]['box']
                        else:
                            continue
                        
                        # Create merged bbox containing all elements
                        x_coords = [p[0] for p in all_points]
                        y_coords = [p[1] for p in all_points]
                        
                        pdf_box = [
                            [min(x_coords), min(y_coords)],
                            [max(x_coords), min(y_coords)],
                            [max(x_coords), max(y_coords)],
                            [min(x_coords), max(y_coords)]
                        ]
                        
                        # Combine text appropriately
                        text = f"{nominal_text}{upper_tol}" if nominal_text else upper_tol
                        print(f"Combined dimension: {text}")

                    # Skip if not a dimensional value after potential merging
                    if not (text.startswith('+') or dimension_parser.is_dimensional_value(text)):
                        continue

                    # Find associated YOLO detection
                    associated_yolo = None
                    association_type = None

                    for yolo_det in normalized_yolo:
                        is_associated, assoc_type = ClusterDetector.check_yolo_association(
                            pdf_box, 
                            yolo_det['box']
                        )
                        
                        if is_associated:
                            associated_yolo = yolo_det
                            association_type = assoc_type
                            print(f"Found {association_type} association with YOLO class: {yolo_det['class_name']}")
                            break

                    # Create merged bounding box if there's a YOLO association
                    if associated_yolo:
                        merged_box = ClusterDetector._create_merged_box(pdf_box, associated_yolo['box'])
                        
                        # Convert YOLO class to dimension type
                        dim_type = ClusterDetector.get_dimension_type(associated_yolo['class_name'])
                        
                        # Check if this merged box overlaps with existing ones
                        is_overlapping = False
                        for existing_box in merged_boxes:
                            if BoundingBoxUtils.calculate_iou(merged_box, existing_box) > OVERLAP_THRESHOLD:
                                is_overlapping = True
                                break

                        if not is_overlapping:
                            print(f"Adding merged box with dimension type: {dim_type}")
                            all_bboxes.append((merged_box, (text, dim_type)))
                            merged_boxes.append(merged_box)
                    else:
                        # Check if this PDF box is contained within any merged box
                        if not any(
                                BoundingBoxUtils.is_box_contained(pdf_box, merged_box) for merged_box in merged_boxes):
                            print("Adding PDF-only box")
                            all_bboxes.append((pdf_box, (text, None)))

                except Exception as e:
                    print(f"Error processing detection: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    continue

            print(f"\nClustering complete:")
            print(f"- Found {len(all_bboxes)} valid detections")
            print(f"- Created {len(merged_boxes)} merged boxes")

            # Add visualizations and update table
            ClusterDetector._add_visualizations_and_update_table(window, all_bboxes, merged_boxes, dimension_parser)

        except Exception as e:
            print(f"Error in cluster_detections: {str(e)}")
            import traceback
            traceback.print_exc()

    @staticmethod
    def _restore_stamped_items(window, stamped_items):
        """Restore stamped items to the table and scene"""
        for stamped_data in stamped_items:
            row_count = window.ui.dimtable.rowCount()
            window.ui.dimtable.insertRow(row_count)

            # Set serial number
            window.ui.dimtable.setItem(row_count, 0,
                                       QTableWidgetItem(str(row_count + 1)))

            # Set nominal value and store bbox with stamped flag
            nominal_item = QTableWidgetItem(stamped_data['nominal'])
            nominal_item.setData(Qt.UserRole, stamped_data['bbox'])
            nominal_item.setData(Qt.UserRole + 1, "stamped")  # Mark as stamped
            window.ui.dimtable.setItem(row_count, 2, nominal_item)

            # Set tolerance values
            window.ui.dimtable.setItem(row_count, 3,
                                       QTableWidgetItem(stamped_data['upper_tol']))
            window.ui.dimtable.setItem(row_count, 4,
                                       QTableWidgetItem(stamped_data['lower_tol']))
            window.ui.dimtable.setItem(row_count, 5,
                                       QTableWidgetItem(stamped_data['dim_type']))

            # Add visualization bbox
            bbox_item = QGraphicsPolygonItem(
                QPolygonF([QPointF(x, y) for x, y in stamped_data['bbox']])
            )
            pen = QPen(QColor(255, 165, 0))  # Orange color for stamped items
            pen.setWidth(2)
            pen.setCosmetic(True)
            bbox_item.setPen(pen)
            bbox_item.setZValue(1)

            window.ui.pdf_view.scene().addItem(bbox_item)
            window.ui.pdf_view.pdf_items.append(bbox_item)

    @staticmethod
    def _create_merged_box(pdf_box, yolo_box):
        """Create a merged bounding box from PDF and YOLO boxes with padding"""
        try:
            # Extract all points from both boxes
            all_points = pdf_box + yolo_box
            
            # Get min/max coordinates
            x_coords = [p[0] for p in all_points]
            y_coords = [p[1] for p in all_points]
            
            # Add padding
            padding = 5
            merged_x1 = min(x_coords) - padding
            merged_y1 = min(y_coords) - padding
            merged_x2 = max(x_coords) + padding
            merged_y2 = max(y_coords) + padding
            
            # Create merged box in polygon format
            merged_box = [
                [merged_x1, merged_y1],
                [merged_x2, merged_y1],
                [merged_x2, merged_y2],
                [merged_x1, merged_y2]
            ]
            
            return merged_box
            
        except Exception as e:
            print(f"Error creating merged box: {str(e)}")
            return pdf_box  # Fall back to PDF box if merge fails
        

    @staticmethod
    def _add_visualizations_and_update_table(window, all_bboxes, merged_boxes, dimension_parser):
        """Add visualizations to scene and update table with detection results"""

        # First, sort bboxes by width (descending) to prioritize wider boxes
        def get_bbox_width(bbox_data):
            bbox = bbox_data[0]  # bbox is the first element in the tuple
            x_coords = [p[0] for p in bbox]
            return max(x_coords) - min(x_coords)

        all_bboxes = sorted(all_bboxes, key=get_bbox_width, reverse=True)

        # Keep track of used areas to avoid overlaps
        used_areas = []

        for bbox, (text, yolo_class) in all_bboxes:
            # Check if this bbox significantly overlaps with any existing bbox
            is_overlapping = False
            for used_bbox, _ in used_areas:
                iou = BoundingBoxUtils.calculate_iou(bbox, used_bbox)
                if iou > 0.3:  # 30% overlap threshold
                    is_overlapping = True
                    break

            if is_overlapping:
                continue  # Skip this bbox as it overlaps with a wider one

            # Add this bbox to used areas
            used_areas.append((bbox, text))

            # Process the text to separate nominal and tolerance
            if text.strip() in ['+', '-']:
                continue  # Skip single + or - characters

            # Check if this is already a combined dimension with + sign
            if '+' in text and not text.startswith('+'):
                parts = text.split('+')
                nominal_text = parts[0].strip()
                tol_part = parts[1].strip()
                dim_type = "Length"
                upper_tol = f"+{tol_part}"
                lower_tol = "0"
            # Handle pure tolerance values
            elif text.startswith('+'):
                nominal_text = ""
                dim_type = "Tolerance"
                upper_tol = text  # Keep full text including +
                lower_tol = "0"
            else:
                # Normal dimension parsing
                dim_type, upper_tol, lower_tol, nominal_text = dimension_parser.parse_dimension(text)

                # Skip if nominal value is 0 (parse_dimension returned None)
                if dim_type is None:
                    continue

            # Create highlight and balloon for each bbox
            highlight_elements = HighlightManager.highlight_bbox(
                window.ui.pdf_view,
                bbox,
                window.ui.dimtable.rowCount(),
                from_table=False
            )

            if highlight_elements:
                # Add all elements to scene
                window.ui.pdf_view.scene().addItem(highlight_elements['highlight'])
                window.ui.pdf_view.scene().addItem(highlight_elements['circle'])
                window.ui.pdf_view.scene().addItem(highlight_elements['triangle'])
                window.ui.pdf_view.scene().addItem(highlight_elements['text'])

                # Add to ocr_items for tracking
                window.ui.pdf_view.pdf_items.extend([
                    highlight_elements['highlight'],
                    highlight_elements['circle'],
                    highlight_elements['triangle'],
                    highlight_elements['text']
                ])

            # Add to table
            row_count = window.ui.dimtable.rowCount()
            window.ui.dimtable.insertRow(row_count)

            # Set serial number
            window.ui.dimtable.setItem(row_count, 0,
                                       QTableWidgetItem(str(row_count + 1)))

            # Calculate midpoint and get zone
            midpoint = ClusterDetector.calculate_merged_box_midpoint(bbox)
            if midpoint:
                zone = ZoneDetector.get_zone_for_midpoint(window, midpoint)
                window.ui.dimtable.setItem(row_count, 1, QTableWidgetItem(zone))
            else:
                window.ui.dimtable.setItem(row_count, 1, QTableWidgetItem("??"))

            # Set nominal value and store bbox
            if yolo_class:
                # Only use nominal_text for display in nominal column
                display_text = nominal_text
                # Set dimension type as GDT: yolo_class
                if yolo_class == 'A':
                    dim_type = "Diameter"
                elif yolo_class and yolo_class.startswith('GDT:'):
                    dim_type = yolo_class  # Keep as is if already in GDT format
                else:
                    dim_type = f"GDT: {yolo_class}"  # Add GDT prefix for other YOLO classes
            else:
                display_text = nominal_text

            nominal_item = QTableWidgetItem(display_text)
            nominal_item.setData(Qt.UserRole, bbox)
            window.ui.dimtable.setItem(row_count, 2, nominal_item)

            # Set tolerance values
            window.ui.dimtable.setItem(row_count, 3, QTableWidgetItem(upper_tol))
            window.ui.dimtable.setItem(row_count, 4, QTableWidgetItem(lower_tol))
            window.ui.dimtable.setItem(row_count, 5, QTableWidgetItem(dim_type))

    @staticmethod
    def calculate_merged_box_midpoint(merged_box):
        """Calculate the midpoint of a merged bounding box"""
        try:
            # Extract all x and y coordinates
            x_coords = [p[0] for p in merged_box]
            y_coords = [p[1] for p in merged_box]

            # Calculate midpoint
            midpoint_x = sum(x_coords) / len(merged_box)
            midpoint_y = sum(y_coords) / len(merged_box)

            return (midpoint_x, midpoint_y)
        except Exception as e:
            print(f"Error calculating merged box midpoint: {str(e)}")
            return None


class OCRProcessor:
    @staticmethod
    def populate_and_parse_ocr_results(window, results, rotation=0):
        """Process PDF text extraction results and populate the table"""
        try:
            # Clear existing results for this rotation
            window.all_detections['ocr'][rotation] = []

            # Process each text detection
            for result in results:
                # Skip empty text
                if not result['text'].strip():
                    continue

                bbox = result['box']
                text = result['text'].strip()

                # Check if this box overlaps with any existing box
                is_duplicate = False
                for existing_rotation, existing_results in window.all_detections['ocr'].items():
                    for existing in existing_results:
                        if window.calculate_iou(bbox, existing['box']) > 0.3:
                            is_duplicate = True
                            break
                    if is_duplicate:
                        break

                if not is_duplicate:
                    # Store the detection
                    window.all_detections['ocr'][rotation].append({
                        'text': text,
                        'box': bbox,
                        'confidence': 1.0,  # PyMuPDF doesn't provide confidence scores
                        'rotation': rotation
                    })

            return True

        except Exception as e:
            print(f"Error in populate_and_parse_ocr_results: {str(e)}")
            return False

    @staticmethod
    def is_vertical_text(bbox):
        """Check if the text is likely vertical based on bbox dimensions"""
        # Get bbox dimensions
        x_coords = [p[0] for p in bbox]
        y_coords = [p[1] for p in bbox]
        width = max(x_coords) - min(x_coords)
        height = max(y_coords) - min(y_coords)

        # If width is significantly smaller than height (e.g., width is less than 40% of height)
        # then consider it vertical text
        return width < (height * 0.4)


class ZoneDetector:
    @staticmethod
    def find_innermost_boundary(image):
        """Find the innermost boundary rectangle that contains the main technical drawing"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )

        # Find contours with RETR_TREE to get hierarchy
        contours, hierarchy = cv2.findContours(
            thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
        )

        height, width = image.shape[:2]
        valid_rectangles = []

        # Process each contour
        for i, cnt in enumerate(contours):
            epsilon = 0.01 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)

            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            rect_area = w * h

            is_valid = (
                    len(approx) >= 4 and
                    w > width * 0.1 and h > height * 0.1 and
                    abs(area - rect_area) / rect_area < 0.4 and
                    x >= 0 and y >= 0
            )

            if is_valid:
                valid_rectangles.append({
                    'contour': cnt,
                    'area': area,
                    'rect': (x, y, w, h)
                })

        if not valid_rectangles:
            return None, None

        valid_rectangles.sort(key=lambda x: x['area'], reverse=True)
        main_rect = valid_rectangles[1]['rect'] if len(valid_rectangles) > 1 else valid_rectangles[0]['rect']
        main_cnt = valid_rectangles[1]['contour'] if len(valid_rectangles) > 1 else valid_rectangles[0]['contour']

        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(mask, [main_cnt], -1, 255, -1)

        return mask, main_rect

    @staticmethod
    def extract_content_outside_boundary(image, boundary_rect):
        """Extract content outside the innermost boundary."""
        result_img = image.copy()
        x, y, w, h = boundary_rect
        height, width = image.shape[:2]

        # Define regions of interest: top margin and right margin
        top_margin = image[0:y, x:x + w].copy()
        right_margin = image[y:y + h, x + w:width].copy()

        # Create a mask to highlight these regions
        highlight_mask = np.zeros_like(image)
        highlight_mask[0:y, x:x + w] = (255, 0, 0)  # Blue for top margin
        highlight_mask[y:y + h, x + w:width] = (255, 0, 0)  # Blue for right margin

        # Apply the highlight: blend with original image
        alpha = 0.3  # Transparency factor
        result_img = cv2.addWeighted(result_img, 1, highlight_mask, alpha, 0)

        # Draw boundary lines to clearly show the innermost boundary
        cv2.line(result_img, (x, y), (x + w, y), (0, 0, 255), 5)  # Top line in red
        cv2.line(result_img, (x + w, y), (x + w, y + h), (0, 0, 255), 5)  # Right line in red

        return result_img, top_margin, right_margin

    @staticmethod
    def detect_isolated_text_labels(image):
        """Detect isolated text labels in the image."""
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply thresholding - try multiple approaches for better coverage
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        # Find connected components (CC)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

        # Filter components by size to find text-like objects
        min_area = 15  # Very small area threshold for single characters
        max_area = 1000  # Maximum area for text

        text_regions = []
        result_img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR) if len(image.shape) == 2 else image.copy()

        # Start from 1 to skip background (label 0)
        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            width = stats[i, cv2.CC_STAT_WIDTH]
            height = stats[i, cv2.CC_STAT_HEIGHT]
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]

            aspect_ratio = width / height if height > 0 else 0

            # Filter conditions for isolated text characters
            if (min_area <= area <= max_area and
                    0.2 <= aspect_ratio <= 5 and
                    width <= 100 and height <= 100):  # Size constraints

                text_regions.append((x, y, width, height))
                cv2.rectangle(result_img, (x, y), (x + width, y + height), (0, 255, 0), 2)

        return result_img, len(text_regions)

    @staticmethod
    def draw_grid_based_on_labels(image, top_label_count, right_label_count, output_folder):
        """Draw grid based on detected labels and return grid positions."""
        result_img = image.copy()
        height, width = image.shape[:2]

        vertical_lines = []
        horizontal_lines = []

        # Check if image is vertical (height > width)
        is_vertical = height > width

        if is_vertical:
            # Force 4 divisions for vertical drawings
            num_vertical_divisions = 4
            num_horizontal_divisions = 4

            # Get the boundary rectangle
            boundary_mask, boundary_rect = ZoneDetector.find_innermost_boundary(image)
            if boundary_rect is not None:
                x, y, w, h = boundary_rect

                horizontal_spacing = h / num_horizontal_divisions
                vertical_spacing = w / num_vertical_divisions
                # Create vertical lines starting from boundary left edge
                for i in range(num_vertical_divisions + 1):
                    grid_x = int(x + i * vertical_spacing)
                    vertical_lines.append(grid_x)
                    cv2.line(result_img, (grid_x, 0), (grid_x, height), (0, 0, 255), 2)

                # Create horizontal lines starting from boundary top
                for i in range(num_horizontal_divisions + 1):
                    grid_y = int(y + i * horizontal_spacing)
                    horizontal_lines.append(grid_y)
                    cv2.line(result_img, (0, grid_y), (width, grid_y), (0, 0, 255), 2)


        else:

            '''boundary_mask, boundary_rect = ZoneDetector.find_innermost_boundary(image)
            if boundary_rect is not None:
                x, y, w, h = boundary_rect
                print(boundary_rect)


                # Create a copy of the image to draw the boundary
                boundary_visualization = image.copy()

                # Draw the rectangle in red
                cv2.rectangle(boundary_visualization, (x, y), (x + w, y + h), (0, 0, 255), 2)

                # Add text to show coordinates
                text = f"x:{x}, y:{y}, w:{w}, h:{h}"
                cv2.putText(boundary_visualization, text, (x, y-10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

                # Save the visualization
                cv2.imwrite('innermost_boundary.png', boundary_visualization)
                print("Boundary visualization saved as 'innermost_boundary.png'")'''

            # Original logic for horizontal drawings
            if top_label_count > 0:
                vertical_spacing = width / top_label_count
                for i in range(top_label_count):
                    grid_x = int(width - i * vertical_spacing)
                    if grid_x > 0:
                        cv2.line(result_img, (grid_x, 0), (grid_x, height), (0, 0, 255), 2)
                        vertical_lines.append(grid_x)

            vertical_lines.append(0)
            vertical_lines.sort()

            if right_label_count > 0:
                horizontal_spacing = height / right_label_count
                for i in range(right_label_count):
                    grid_y = int(height - i * horizontal_spacing)
                    if grid_y > 0:
                        cv2.line(result_img, (0, grid_y), (width, grid_y), (0, 0, 255), 2)
                        horizontal_lines.append(grid_y)

            horizontal_lines.append(0)
            horizontal_lines.sort()

        # Save the grid image if output folder is provided
        if output_folder:
            grid_path = os.path.join(output_folder, "label_based_grid.png")
            cv2.imwrite(grid_path, result_img)
            print(f"Label-based grid image saved to {grid_path}")

            # Print the pixel positions
            print("Vertical grid lines (X positions):", vertical_lines)
            print("Horizontal grid lines (Y positions):", horizontal_lines)

        return result_img, vertical_lines, horizontal_lines

    @staticmethod
    def get_zone_for_midpoint(window, midpoint):
        try:
            # Get the PDF view scene
            scene = window.ui.pdf_view.scene()
            if not scene:
                print("No scene available")
                return "__"

            # Convert scene to image
            rect = scene.sceneRect()
            width = int(rect.width())
            height = int(rect.height())

            # Create QImage from scene
            qimage = QImage(width, height, QImage.Format_RGB32)
            qimage.fill(Qt.white)

            painter = QPainter(qimage)
            scene.render(painter)
            painter.end()

            # Convert QImage to numpy array
            ptr = qimage.constBits()
            ptr.setsize(height * width * 4)
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
            cv_image = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

            # Now use the converted image for zone detection
            boundary_mask, boundary_rect = ZoneDetector.find_innermost_boundary(cv_image)
            if not boundary_rect:
                print("Could not find boundary rectangle")
                return "__"

            # Extract content outside boundary
            result_img, top_margin, right_margin = ZoneDetector.extract_content_outside_boundary(
                cv_image, boundary_rect
            )

            # Check if margins are valid
            if top_margin is None or right_margin is None or top_margin.size == 0 or right_margin.size == 0:
                print("Invalid margins detected")
                return "__"

            # Detect isolated text labels from margins
            top_label_img, top_label_count = ZoneDetector.detect_isolated_text_labels(top_margin)
            right_label_img, right_label_count = ZoneDetector.detect_isolated_text_labels(right_margin)

            # Create grid based on labels
            grid_img, vertical_lines, horizontal_lines = ZoneDetector.draw_grid_based_on_labels(
                cv_image, top_label_count, right_label_count, None
            )

            if not vertical_lines or not horizontal_lines:
                print("Could not create grid lines")
                return "__"

            # Rest of the code remains exactly the same
            x, y = midpoint

            # Find column (numbered right to left)
            col_idx = next((i for i in range(len(vertical_lines) - 1)
                            if vertical_lines[i] <= x < vertical_lines[i + 1]),
                           len(vertical_lines) - 2)
            num_cols = len(vertical_lines) - 1
            col_number = num_cols - col_idx

            # Find row (lettered bottom to top)
            row_idx = next((i for i in range(len(horizontal_lines) - 1)
                            if horizontal_lines[i] <= y < horizontal_lines[i + 1]),
                           len(horizontal_lines) - 2)
            num_rows = len(horizontal_lines) - 1
            row_idx = num_rows - row_idx - 1
            row_letter = chr(65 + row_idx) if row_idx < 26 else '?'

            return f"{row_letter}{col_number}"

        except Exception as e:
            print(f"Error in get_zone_for_midpoint: {str(e)}")
            import traceback
            traceback.print_exc()
            return "__"

    @staticmethod
    def draw_field_division(window, show=True):
        """Draw or hide field division grid lines on the PDF view"""
        try:
            # If hiding the grid, remove existing grid line items
            if not show:
                # Find and remove all grid line items
                for item in window.ui.pdf_view.scene().items():
                    if hasattr(item, 'grid_line'):
                        window.ui.pdf_view.scene().removeItem(item)
                return True

            # Get the scene dimensions
            scene = window.ui.pdf_view.scene()
            if not scene:
                print("No scene available")
                return False

            rect = scene.sceneRect()
            width = int(rect.width())
            height = int(rect.height())

            # Convert scene to image for analysis
            qimage = QImage(width, height, QImage.Format_RGB32)
            qimage.fill(Qt.white)

            painter = QPainter(qimage)
            scene.render(painter)
            painter.end()

            # Convert QImage to numpy array
            ptr = qimage.constBits()
            ptr.setsize(height * width * 4)
            arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
            cv_image = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

            # Find innermost boundary
            boundary_mask, boundary_rect = ZoneDetector.find_innermost_boundary(cv_image)
            if not boundary_rect:
                print("Could not find boundary rectangle")
                return False

            # Extract content outside boundary
            result_img, top_margin, right_margin = ZoneDetector.extract_content_outside_boundary(
                cv_image, boundary_rect
            )

            # Detect isolated text labels
            top_label_img, top_label_count = ZoneDetector.detect_isolated_text_labels(top_margin)
            right_label_img, right_label_count = ZoneDetector.detect_isolated_text_labels(right_margin)

            # Create grid based on labels
            _, vertical_lines, horizontal_lines = ZoneDetector.draw_grid_based_on_labels(
                cv_image, top_label_count, right_label_count, None
            )

            # Draw grid lines on the scene
            for x in vertical_lines:
                line = QtWidgets.QGraphicsLineItem(x, 0, x, height)
                pen = QPen(QColor(0, 200, 0))  # Green color
                pen.setWidth(2)
                pen.setCosmetic(True)  # Ensures consistent width regardless of zoom
                line.setPen(pen)
                line.setZValue(0)  # Draw behind other elements
                line.grid_line = True  # Mark as grid line for later removal
                scene.addItem(line)

            for y in horizontal_lines:
                line = QtWidgets.QGraphicsLineItem(0, y, width, y)
                pen = QPen(QColor(0, 200, 0))  # Green color
                pen.setWidth(2)
                pen.setCosmetic(True)
                line.setPen(pen)
                line.setZValue(0)  # Draw behind other elements
                line.grid_line = True  # Mark as grid line for later removal
                scene.addItem(line)

            return True

        except Exception as e:
            print(f"Error drawing field division: {str(e)}")
            import traceback
            traceback.print_exc()
            return False



