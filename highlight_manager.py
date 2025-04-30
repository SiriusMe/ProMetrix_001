from PyQt5.QtCore import Qt, QPointF
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QTableWidgetItem
from PyQt5.QtWidgets import QGraphicsPolygonItem, QGraphicsPathItem, QGraphicsTextItem, QGraphicsEllipseItem
from PyQt5.QtGui import QPen, QColor, QPainterPath, QPolygonF, QBrush

class HighlightManager:
    @staticmethod
    def create_highlight(view, bbox):
        """Create a highlighted bounding box with balloon"""
        try:
            highlight_polygon = QPolygonF([QPointF(x, y) for x, y in bbox])
            highlight_item = QGraphicsPolygonItem(highlight_polygon)
            
            highlight_pen = QPen(QColor(255, 0, 0))  # Red color
            highlight_pen.setWidth(2)
            highlight_pen.setCosmetic(True)
            highlight_item.setPen(highlight_pen)
            highlight_item.setZValue(2)  # Ensure highlight is on top
            
            return highlight_item

        except Exception as e:
            print(f"Error creating highlight: {str(e)}")
            return None

    @staticmethod
    def create_balloon(view, bbox, row_number, highlight_color=None):
        """Create a balloon with row number"""
        try:
            balloon_items = []
            balloon_color = highlight_color if highlight_color else QColor(30, 144, 255)

            x_coords = [p[0] for p in bbox]
            y_coords = [p[1] for p in bbox]
            balloon_x = max(x_coords)
            balloon_y = max(y_coords)

            balloon_radius = 29
            pointer_base = 16
            pointer_height = 20

            balloon_center_x = balloon_x + pointer_height + balloon_radius
            balloon_center_y = balloon_y

            circle_path = QPainterPath()
            circle_path.addEllipse(
                balloon_center_x - balloon_radius,
                balloon_center_y - balloon_radius,
                balloon_radius * 2,
                balloon_radius * 2
            )

            triangle_path = QPainterPath()
            triangle_points = [
                QPointF(balloon_center_x - balloon_radius, balloon_center_y - pointer_base/2),
                QPointF(balloon_center_x - balloon_radius - pointer_height, balloon_center_y),
                QPointF(balloon_center_x - balloon_radius, balloon_center_y + pointer_base/2)
            ]
            triangle_path.moveTo(triangle_points[0])
            for point in triangle_points[1:]:
                triangle_path.lineTo(point)
            triangle_path.closeSubpath()

            balloon_circle = QGraphicsPathItem(circle_path)
            circle_pen = QPen(balloon_color)
            circle_pen.setWidth(3)
            circle_pen.setCosmetic(True)
            balloon_circle.setPen(circle_pen)
            balloon_circle.setBrush(QBrush(Qt.NoBrush))
            balloon_circle.setZValue(3)
            balloon_items.append(balloon_circle)

            balloon_triangle = QGraphicsPathItem(triangle_path)
            triangle_pen = QPen(balloon_color)
            triangle_pen.setWidth(3)
            triangle_pen.setCosmetic(True)
            balloon_triangle.setPen(triangle_pen)
            balloon_triangle.setBrush(QBrush(balloon_color))
            balloon_triangle.setZValue(3)
            balloon_items.append(balloon_triangle)

            balloon_text = QGraphicsTextItem()
            balloon_text.setDefaultTextColor(balloon_color)
            balloon_text.setHtml(
                f'<div style="text-align: center;">'
                f'<span style="font-family: Segoe UI; font-size: 30px; font-weight: 900;">{row_number}</span>'
                f'</div>'
            )
            
            text_rect = balloon_text.boundingRect()
            text_x = balloon_center_x - text_rect.width()/2
            text_y = balloon_center_y - text_rect.height()/2
            balloon_text.setPos(text_x, text_y)
            balloon_text.setZValue(101)
            balloon_items.append(balloon_text)

            return balloon_items

        except Exception as e:
            print(f"Error creating balloon: {str(e)}")
            return []

    @staticmethod
    def highlight_bbox(view, bbox, row, from_table=True):
        """Create highlight and balloon for a bounding box"""
        try:
            highlight_polygon = QPolygonF([QPointF(x, y) for x, y in bbox])
            highlight_item = QGraphicsPolygonItem(highlight_polygon)
            
            highlight_pen = QPen(QColor(255, 140, 0))
            highlight_pen.setWidth(3)
            highlight_pen.setStyle(Qt.DashLine if from_table else Qt.SolidLine)
            highlight_item.setPen(highlight_pen)
            highlight_item.setZValue(2)

            x_coords = [p[0] for p in bbox]
            y_coords = [p[1] for p in bbox]
            balloon_x = max(x_coords)
            balloon_y = max(y_coords)

            balloon_radius = 29
            pointer_base = 16
            pointer_height = 20

            balloon_center_x = balloon_x + pointer_height + balloon_radius
            balloon_center_y = balloon_y

            circle_path = QPainterPath()
            circle_path.addEllipse(
                balloon_center_x - balloon_radius,
                balloon_center_y - balloon_radius,
                balloon_radius * 2,
                balloon_radius * 2
            )

            triangle_path = QPainterPath()
            triangle_points = [
                QPointF(balloon_center_x - balloon_radius, balloon_center_y - pointer_base/2),
                QPointF(balloon_center_x - balloon_radius - pointer_height, balloon_center_y),
                QPointF(balloon_center_x - balloon_radius, balloon_center_y + pointer_base/2)
            ]
            triangle_path.moveTo(triangle_points[0])
            for point in triangle_points[1:]:
                triangle_path.lineTo(point)
            triangle_path.closeSubpath()

            balloon_color = QColor(255, 0, 0) if from_table else QColor(30, 144, 255)

            balloon_circle = QGraphicsPathItem(circle_path)
            circle_pen = QPen(balloon_color)
            circle_pen.setWidth(3)
            circle_pen.setCosmetic(True)
            balloon_circle.setPen(circle_pen)
            balloon_circle.setBrush(QBrush(Qt.NoBrush))
            balloon_circle.setZValue(3)

            balloon_triangle = QGraphicsPathItem(triangle_path)
            triangle_pen = QPen(balloon_color)
            triangle_pen.setWidth(3)
            triangle_pen.setCosmetic(True)
            balloon_triangle.setPen(triangle_pen)
            balloon_triangle.setBrush(QBrush(balloon_color))
            balloon_triangle.setZValue(3)

            balloon_text = QGraphicsTextItem()
            balloon_text.setDefaultTextColor(balloon_color)
            balloon_text.setHtml(
                f'<div style="text-align: center;">'
                f'<span style="font-family: Segoe UI; font-size: 30px; font-weight: 900;">{row + 1}</span>'
                f'</div>'
            )
            
            text_rect = balloon_text.boundingRect()
            text_x = balloon_center_x - text_rect.width()/2
            text_y = balloon_center_y - text_rect.height()/2
            balloon_text.setPos(text_x, text_y)
            balloon_text.setZValue(4)

            return {
                'highlight': highlight_item,
                'circle': balloon_circle,
                'triangle': balloon_triangle,
                'text': balloon_text
            }

        except Exception as e:
            print(f"Error creating highlight elements: {str(e)}")
            return None
        
    
    @staticmethod
    def delete_balloons(view, row=None):
        """Delete balloons for a specific row or all balloons if row is None"""
        try:
            # Find all balloon items
            balloon_items = []
            
            # Look for all types of items that could be part of a balloon
            for item in view.scene().items():
                # Check for balloon_data attribute
                if hasattr(item, 'balloon_data'):
                    if row is None or item.balloon_data.get('table_row') == row:
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
            
            # Remove all balloon items
            for item in balloon_items:
                view.scene().removeItem(item)
                if hasattr(view, 'ocr_items') and item in view.ocr_items:
                    view.ocr_items.remove(item)
            
            print(f"Deleted {len(balloon_items)} balloon items")
            return len(balloon_items)  # Return number of balloons deleted
        
        except Exception as e:
            print(f"Error deleting balloons: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0
 