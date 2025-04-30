from PyQt5.QtCore import Qt, QRectF, QEvent, QPointF
from PyQt5.QtGui import QPen, QMouseEvent, QBrush, QColor, QPainterPath, QPolygonF
from PyQt5.QtWidgets import QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsView, QDialog, QMenu, QGraphicsTextItem, \
    QTableWidgetItem, QGraphicsEllipseItem, QGraphicsPathItem
from dialogs import DimensionDialog
from highlight_manager import HighlightManager

class EventHandler:
    @staticmethod
    def mousePressEvent(view, event):
        """Handle mouse press events"""
        if event.button() == Qt.LeftButton:
            if view.dynamic_zoom:
                view.last_mouse_pos = event.pos()
                event.accept()
                return
            elif view.zoom_area_mode:
                view.zoom_area_start = view.mapToScene(event.pos())
                if view.zoom_area_rect:
                    view.scene().removeItem(view.zoom_area_rect)
                    view.zoom_area_rect = None
                event.accept()
                return
            elif view.stamp_mode:
                view.drawing_stamp = True
                view.stamp_start = view.mapToScene(event.pos())
                if view.stamp_rect:
                    view.scene().removeItem(view.stamp_rect)
                    view.stamp_rect = None
                event.accept()
                return
            elif view.selection_mode:
                view.drawing_selection = True
                view.drag_start = view.mapToScene(event.pos())
                if view.current_rect:
                    view.scene().removeItem(view.current_rect)
                    view.current_rect = None
                event.accept()
                return
            else:
                # Check if clicked on a bbox
                item = view.itemAt(event.pos())
                if isinstance(item, (QGraphicsPolygonItem, QGraphicsRectItem)):
                    # Get bbox coordinates
                    if isinstance(item, QGraphicsPolygonItem):
                        bbox_points = [[p.x(), p.y()] for p in item.polygon()]
                    else:  # QGraphicsRectItem
                        rect = item.rect()
                        bbox_points = [
                            [rect.x(), rect.y()],
                            [rect.x() + rect.width(), rect.y()],
                            [rect.x() + rect.width(), rect.y() + rect.height()],
                            [rect.x(), rect.y() + rect.height()]
                        ]

                    # Find and highlight corresponding table row
                    for row in range(view.main_window.ui.dimtable.rowCount()):
                        table_item = view.main_window.ui.dimtable.item(row, 2)  # Nominal column
                        if table_item:
                            stored_bbox = table_item.data(Qt.UserRole)
                            if stored_bbox and view.compare_bboxes(bbox_points, stored_bbox):
                                # Select the row
                                view.main_window.ui.dimtable.selectRow(row)
                                # Ensure the row is visible
                                view.main_window.ui.dimtable.scrollToItem(table_item)
                                # Highlight the bbox
                                view.main_window.highlight_bbox(row, 2)
                                break
                QGraphicsView.mousePressEvent(view, event)

        elif event.button() == Qt.MiddleButton:
            view.middle_button_pressed = True
            view.setDragMode(QGraphicsView.ScrollHandDrag)
            view.original_cursor = view.cursor()
            view.setCursor(Qt.ClosedHandCursor)
            fake_event = QMouseEvent(
                QEvent.MouseButtonPress, event.pos(),
                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
            )
            QGraphicsView.mousePressEvent(view, fake_event)
            event.accept()

    @staticmethod
    def mouseMoveEvent(view, event):
        """Handle mouse move events"""
        if view.dynamic_zoom and view.last_mouse_pos is not None:
            delta = event.pos().y() - view.last_mouse_pos.y()
            if abs(delta) > 5:
                if delta > 0:
                    view.main_window.zoom_in(use_mouse_position=True, mouse_pos=event.pos())
                else:
                    view.main_window.zoom_out(use_mouse_position=True, mouse_pos=event.pos())
                view.last_mouse_pos = event.pos()
            event.accept()
            return
        elif view.zoom_area_mode and view.zoom_area_start:
            if view.zoom_area_rect:
                view.scene().removeItem(view.zoom_area_rect)
            current_pos = view.mapToScene(event.pos())
            rect = QRectF(view.zoom_area_start, current_pos).normalized()
            pen = QPen(Qt.blue)
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            view.zoom_area_rect = view.scene().addRect(rect, pen)
            event.accept()
            return
        elif view.stamp_mode and view.drawing_stamp and view.stamp_start:
            if view.stamp_rect:
                view.scene().removeItem(view.stamp_rect)
            current_pos = view.mapToScene(event.pos())
            rect = QRectF(view.stamp_start, current_pos).normalized()
            pen = QPen(Qt.blue)
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            view.stamp_rect = view.scene().addRect(rect, pen)
            event.accept()
            return
        elif view.selection_mode and view.drawing_selection and view.drag_start:
            if view.current_rect:
                view.scene().removeItem(view.current_rect)
            current_pos = view.mapToScene(event.pos())
            rect = QRectF(view.drag_start, current_pos).normalized()
            pen = QPen(Qt.red)
            pen.setWidth(2)
            pen.setStyle(Qt.DashLine)
            view.current_rect = view.scene().addRect(rect, pen)
            event.accept()
            return
        elif view.middle_button_pressed:
            QGraphicsView.mouseMoveEvent(view, event)
            event.accept()
            return

        QGraphicsView.mouseMoveEvent(view, event)

    @staticmethod
    def mouseReleaseEvent(view, event):
        """Handle mouse release events"""
        if event.button() == Qt.LeftButton:
            if view.dynamic_zoom:
                view.last_mouse_pos = None
                event.accept()
                return
            elif view.zoom_area_mode and view.zoom_area_rect:
                rect = view.zoom_area_rect.rect().normalized()
                view.scene().removeItem(view.zoom_area_rect)
                view.zoom_area_rect = None
                view.zoom_area_start = None
                view.fitInView(rect, Qt.KeepAspectRatio)
                view.main_window.zoom_factor = view.transform().m11()
                event.accept()
                return
            elif view.stamp_mode and view.stamp_rect:
                rect = view.stamp_rect.rect().normalized()
                points = [
                    [rect.x(), rect.y()],
                    [rect.x() + rect.width(), rect.y()],
                    [rect.x() + rect.width(), rect.y() + rect.height()],
                    [rect.x(), rect.y() + rect.height()]
                ]
                dialog = DimensionDialog(view)
                if dialog.exec_() == QDialog.Accepted:
                    view.addCustomBBox(points, dialog.getDimensionData())
                view.scene().removeItem(view.stamp_rect)
                view.stamp_rect = None
                view.drawing_stamp = False
                event.accept()
                return
            elif view.selection_mode and view.current_rect:
                rect = view.current_rect.rect().normalized()
                view.processSelectedArea(rect)
                view.scene().removeItem(view.current_rect)
                view.current_rect = None
                view.drawing_selection = False
                event.accept()
                return
            else:
                QGraphicsView.mouseReleaseEvent(view, event)
        elif event.button() == Qt.MiddleButton:
            view.middle_button_pressed = False
            view.setDragMode(QGraphicsView.NoDrag)
            view.setCursor(view.original_cursor)
            fake_event = QMouseEvent(
                QEvent.MouseButtonRelease, event.pos(),
                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
            )
            QGraphicsView.mouseReleaseEvent(view, fake_event)
            event.accept()

    @staticmethod
    def wheelEvent(view, event):
        """Handle mouse wheel events for zooming"""
        try:
            if event.modifiers() == Qt.ControlModifier:
                # Convert wheel steps to a zoom factor
                num_degrees = event.angleDelta().y() / 8
                num_steps = num_degrees / 15  # Usually 15 degrees per step

                if num_steps > 0:
                    view.main_window.zoom_in(use_mouse_position=True, mouse_pos=event.pos())
                else:
                    view.main_window.zoom_out(use_mouse_position=True, mouse_pos=event.pos())

                # Update text scaling
                view.updateBBoxScaling()
                event.accept()
            else:
                QGraphicsView.wheelEvent(view, event)
        except Exception as e:
            print(f"Error in wheelEvent: {str(e)}")
            QGraphicsView.wheelEvent(view, event)

    @staticmethod
    def keyPressEvent(view, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Escape:
            # Clear editing mode if active
            if view.is_editing:
                view.is_editing = False

                # Remove finish editing action
                for action in view.actions():
                    if action.text() == "Finish Editing":
                        view.removeAction(action)
                        break
            
            # Clear all modes
            view.dynamic_zoom = False
            view.zoom_area_mode = False
            view.stamp_mode = False
            view.selection_mode = False
            
            # Clear any active rectangles
            if view.zoom_area_rect:
                view.scene().removeItem(view.zoom_area_rect)
                view.zoom_area_rect = None
            if view.stamp_rect:
                view.scene().removeItem(view.stamp_rect)
                view.stamp_rect = None
            if view.current_rect:
                view.scene().removeItem(view.current_rect)
                view.current_rect = None
            
            # Reset drag mode
            view.setDragMode(QGraphicsView.NoDrag)
            
            # Reset cursor
            view.setCursor(Qt.ArrowCursor)
            
            # Uncheck all toolbar actions
            view.main_window.ui.actionMoveView.setChecked(False)
            view.main_window.ui.actionZoomDynamic.setChecked(False)
            view.main_window.ui.actionZoomArea.setChecked(False)
            view.main_window.ui.actionStamp.setChecked(False)
            view.main_window.ui.actionSelectionTool.setChecked(False)
            
            event.accept()
        else:
            QGraphicsView.keyPressEvent(view, event)

class ViewEvents:
    @staticmethod
    def zoom_in(view, zoom_factor, max_zoom, zoom_step, use_mouse_position=False, mouse_pos=None):
        """Zoom in with smoother scaling"""
        if zoom_factor >= max_zoom:
            return zoom_factor

        # Calculate new zoom
        new_zoom = min(zoom_factor * zoom_step, max_zoom)
        scale_factor = new_zoom / zoom_factor

        if use_mouse_position and mouse_pos:
            # Store scene point under mouse
            scene_pos = view.mapToScene(mouse_pos)

            # Apply zoom
            view.scale(scale_factor, scale_factor)

            # Get new position and adjust to keep mouse point fixed
            new_pos = view.mapFromScene(scene_pos)
            delta = new_pos - mouse_pos
            view.horizontalScrollBar().setValue(
                view.horizontalScrollBar().value() + delta.x()
            )
            view.verticalScrollBar().setValue(
                view.verticalScrollBar().value() + delta.y()
            )
        else:
            # Zoom centered on viewport
            view.scale(scale_factor, scale_factor)

        return new_zoom

    @staticmethod
    def zoom_out(view, zoom_factor, min_zoom, zoom_step, use_mouse_position=False, mouse_pos=None):
        """Zoom out with smoother scaling"""
        if zoom_factor <= min_zoom:
            return zoom_factor

        # Calculate new zoom
        new_zoom = max(zoom_factor / zoom_step, min_zoom)
        scale_factor = new_zoom / zoom_factor

        if use_mouse_position and mouse_pos:
            # Store scene point under mouse
            scene_pos = view.mapToScene(mouse_pos)

            # Apply zoom
            view.scale(scale_factor, scale_factor)

            # Get new position and adjust to keep mouse point fixed
            new_pos = view.mapFromScene(scene_pos)
            delta = new_pos - mouse_pos
            view.horizontalScrollBar().setValue(
                view.horizontalScrollBar().value() + delta.x()
            )
            view.verticalScrollBar().setValue(
                view.verticalScrollBar().value() + delta.y()
            )
        else:
            # Zoom centered on viewport
            view.scale(scale_factor, scale_factor)

        return new_zoom

    @staticmethod
    def fit_to_view(view, scene):
        """Fit content to view"""
        view.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
        return 1.0  # Reset zoom factor to 1.0

    @staticmethod
    def toggle_move_mode(view, action):
        """Toggle pan/move mode"""
        if view.dragMode() == QGraphicsView.ScrollHandDrag:
            view.setDragMode(QGraphicsView.NoDrag)
            action.setChecked(False)
            return False
        else:
            view.setDragMode(QGraphicsView.ScrollHandDrag)
            action.setChecked(True)
            # Disable other modes
            view.exitSelectionMode()
            view.exitStampMode()
            return True

    @staticmethod
    def toggle_dynamic_zoom(view, action):
        """Toggle dynamic zoom mode"""
        if hasattr(view, 'dynamic_zoom'):
            view.dynamic_zoom = not view.dynamic_zoom
            action.setChecked(view.dynamic_zoom)
            
            if view.dynamic_zoom:
                # Disable other modes
                view.zoom_area_mode = False
                view.exitSelectionMode()
                view.exitStampMode()
                view.setCursor(Qt.SizeVerCursor)
            else:
                view.setCursor(Qt.ArrowCursor)
            return view.dynamic_zoom
        return False

    @staticmethod
    def toggle_zoom_area(view, action):
        """Toggle zoom area mode"""
        if hasattr(view, 'zoom_area_mode'):
            view.zoom_area_mode = not view.zoom_area_mode
            action.setChecked(view.zoom_area_mode)
            
            if view.zoom_area_mode:
                # Disable other modes
                view.dynamic_zoom = False
                view.exitSelectionMode()
                view.exitStampMode()
                view.setCursor(Qt.CrossCursor)
            else:
                view.setCursor(Qt.ArrowCursor)
            return view.zoom_area_mode
        return False

class TableEvents:
    @staticmethod
    def show_table_context_menu(window, position):
        """Show context menu for table rows"""
        menu = QMenu()
        delete_action = menu.addAction("Delete Row")
        
        # Get the row under the cursor
        row = window.ui.dimtable.rowAt(position.y())
        
        if row >= 0:  # Valid row
            action = menu.exec_(window.ui.dimtable.viewport().mapToGlobal(position))
            if action == delete_action:
                TableEvents.delete_table_row_and_bbox(window, row)
                
    @staticmethod
    def delete_table_row_and_bbox(window, row):
        """Delete the table row and its corresponding bbox"""
        try:
            # Get the bbox data from the table
            nominal_item = window.ui.dimtable.item(row, 2)
            if nominal_item:
                bbox_points = nominal_item.data(Qt.UserRole)
                
                # Find and remove all associated items from the scene
                items_to_remove = []
                
                # Find all items that need to be removed
                for item in window.ui.pdf_view.scene().items():
                    if isinstance(item, (QGraphicsPolygonItem, QGraphicsRectItem)):
                        if isinstance(item, QGraphicsPolygonItem):
                            item_points = [[p.x(), p.y()] for p in item.polygon()]
                        else:  # QGraphicsRectItem
                            rect = item.rect()
                            item_points = [
                                [rect.x(), rect.y()],
                                [rect.x() + rect.width(), rect.y()],
                                [rect.x() + rect.width(), rect.y() + rect.height()],
                                [rect.x(), rect.y() + rect.height()]
                            ]
                        
                        if window.ui.pdf_view.compare_bboxes(item_points, bbox_points):
                            items_to_remove.append(item)
                                                
                # Remove all collected items
                for item in items_to_remove:
                    window.ui.pdf_view.scene().removeItem(item)
                    if item in window.ui.pdf_view.pdf_items:
                        window.ui.pdf_view.pdf_items.remove(item)
                
                # Remove from YOLO tracking if it's there
                if bbox_points in window.ui.pdf_view.yolo_detection_boxes:
                    window.ui.pdf_view.yolo_detection_boxes.remove(bbox_points)
                
                # Remove the row from table
                window.ui.dimtable.removeRow(row)

                # Clear any highlight if present
                window.clear_highlighted_bbox()
                
               
                HighlightManager.delete_balloons(window.ui.pdf_view)
                
                
                for row_idx in range(window.ui.dimtable.rowCount()):
                    serial_number = row_idx + 1
                    sl_no_item = QTableWidgetItem(str(serial_number))
                    sl_no_item.setTextAlignment(Qt.AlignCenter)
                    window.ui.dimtable.setItem(row_idx, 0, sl_no_item)
                
              
                for row_idx in range(window.ui.dimtable.rowCount()):
                    item = window.ui.dimtable.item(row_idx, 2)  
                    if item:
                        bbox = item.data(Qt.UserRole)
                        if bbox:
                            serial_number = row_idx + 1
                            balloon_items = HighlightManager.create_balloon(window.ui.pdf_view, bbox, serial_number)
                            for balloon_item in balloon_items:
                                balloon_item.balloon_data = {'table_row': serial_number + 1, 'bbox': bbox}
                                window.ui.pdf_view.scene().addItem(balloon_item)
                                if hasattr(window.ui.pdf_view, 'pdf_items'):
                                    window.ui.pdf_view.pdf_items.append(balloon_item)
                                    

        except Exception as e:
            print(f"Error deleting table row and bbox: {str(e)}")
            import traceback
            traceback.print_exc()
        
 
    @staticmethod
    def highlight_bbox_for_row(window, row):
        """Highlight bounding box for selected row"""
        try:
            # Clear any existing highlight
            window.clear_highlighted_bbox()
            
            # Get bbox data from table
            nominal_item = window.ui.dimtable.item(row, 2)
            if not nominal_item:
                print("No nominal item found")
                return
                
            points = nominal_item.data(Qt.UserRole)  # Now getting points directly
            print(f"\nHighlight points data for row {row}: {points}")  # Debug print
            
            if not points:
                print("No points data found")
                return
                
            # Create highlight polygon
            try:
                # Create polygon for highlight
                polygon_points = [QPointF(float(p[0]), float(p[1])) for p in points]
                window.current_highlight = QGraphicsPolygonItem(QPolygonF(polygon_points))
                window.current_highlight.setPen(QPen(QColor(255, 0, 0), 2))
                window.current_highlight.setZValue(3)
                window.ui.pdf_view.scene().addItem(window.current_highlight)
                
                # Calculate balloon position
                try:
                    # Calculate center and top positions
                    x_coords = [float(p[0]) for p in points]
                    y_coords = [float(p[1]) for p in points]
                    
                    x_min = min(x_coords)
                    x_max = max(x_coords)
                    y_min = min(y_coords)
                    
                    center_x = (x_min + x_max) / 2
                    top_y = y_min - 50  # Position balloon above bbox
                    circle_radius = 12
                    
                    print(f"Balloon position: center_x={center_x}, top_y={top_y}")  # Debug print
                    
                    # Create balloon elements
                    window.balloon_circle = QGraphicsEllipseItem(
                        center_x - circle_radius,
                        top_y - circle_radius * 2,
                        circle_radius * 2,
                        circle_radius * 2
                    )
                    window.balloon_circle.setPen(QPen(Qt.black, 1))
                    window.balloon_circle.setBrush(QBrush(Qt.white))
                    window.balloon_circle.setZValue(4)
                    
                    window.balloon_triangle = QGraphicsPolygonItem(QPolygonF([
                        QPointF(center_x, y_min),  # Bottom point
                        QPointF(center_x - 5, top_y - circle_radius),  # Left point
                        QPointF(center_x + 5, top_y - circle_radius)   # Right point
                    ]))
                    window.balloon_triangle.setPen(QPen(Qt.black, 1))
                    window.balloon_triangle.setBrush(QBrush(Qt.white))
                    window.balloon_triangle.setZValue(4)
                    
                    window.balloon_text = QGraphicsTextItem(str(row + 1))
                    window.balloon_text.setDefaultTextColor(Qt.black)
                    text_rect = window.balloon_text.boundingRect()
                    window.balloon_text.setPos(
                        center_x - text_rect.width() / 2,
                        top_y - circle_radius * 2 + (circle_radius * 2 - text_rect.height()) / 2
                    )
                    window.balloon_text.setZValue(4)
                    
                    # Add balloon elements to scene
                    window.ui.pdf_view.scene().addItem(window.balloon_circle)
                    window.ui.pdf_view.scene().addItem(window.balloon_triangle)
                    window.ui.pdf_view.scene().addItem(window.balloon_text)
                    
                except Exception as balloon_error:
                    print(f"Error creating balloon: {balloon_error}")
                    print(f"Points: {points}")
                    
            except Exception as e:
                print(f"Error creating highlight polygon: {e}")
                print(f"Points data: {points}")
                
        except Exception as e:
            print(f"Error highlighting bbox: {str(e)}")

class VisualizationEvents:
    @staticmethod
    def add_to_table_and_scene(window, text, bbox, scene_box=None):
        """Add detected text and bbox to table and scene"""
        try:
            row_count = window.ui.dimtable.rowCount()
            window.ui.dimtable.insertRow(row_count)
            
            # Set serial number
            window.ui.dimtable.setItem(row_count, 0, 
                QTableWidgetItem(str(row_count + 1)))

            # Process the text to separate nominal and tolerance
            if text.startswith('+'):
                nominal_text = ""
                dim_type = "Tolerance"
                upper_tol = text
                lower_tol = ""
            else:
                # Remove all spaces from text first
                text = ''.join(text.split())
                
                # Parse the dimension
                dim_type, upper_tol, lower_tol, nominal_text = window.parse_dimension(text)

            # Set nominal value and store bbox
            nominal_item = QTableWidgetItem(nominal_text)
            nominal_item.setData(Qt.UserRole, bbox)
            window.ui.dimtable.setItem(row_count, 2, nominal_item)

            # Set tolerance values
            window.ui.dimtable.setItem(row_count, 3, QTableWidgetItem(upper_tol))
            window.ui.dimtable.setItem(row_count, 4, QTableWidgetItem(lower_tol))
            window.ui.dimtable.setItem(row_count, 5, QTableWidgetItem(dim_type))

            # Add bbox visualization if scene_box is provided
            if scene_box:
                bbox_item = QGraphicsPolygonItem(
                    QPolygonF([QPointF(x, y) for x, y in scene_box])
                )
                pen = QPen(QColor(0, 255, 0))
                pen.setWidth(2)
                pen.setCosmetic(True)
                bbox_item.setPen(pen)
                bbox_item.setZValue(1)
                
                window.ui.pdf_view.scene().addItem(bbox_item)
                window.ui.pdf_view.pdf_items.append(bbox_item)

            return True

        except Exception as e:
            print(f"Error adding to table and scene: {str(e)}")
            return False

    @staticmethod
    def highlight_bbox(window, row, column):
        """Highlight the selected bounding box and create a balloon with row number"""
        try:
            # Clear any existing highlight
            window.clear_highlighted_bbox()

            # Get the bbox data from the table
            item = window.ui.dimtable.item(row, 2)  # Nominal column
            if not item:
                return

            bbox = item.data(Qt.UserRole)
            if not bbox:
                return

            # Create highlight polygon
            highlight_polygon = QPolygonF([QPointF(x, y) for x, y in bbox])
            window.current_highlight = QGraphicsPolygonItem(highlight_polygon)
            
            # Set highlight appearance
            highlight_pen = QPen(QColor(255, 0, 0))  # Red color
            highlight_pen.setWidth(2)
            highlight_pen.setCosmetic(True)
            window.current_highlight.setPen(highlight_pen)
            window.current_highlight.setZValue(2)  # Ensure highlight is on top
            
            # Add highlight to scene
            window.ui.pdf_view.scene().addItem(window.current_highlight)

            # Only create balloons for admin users
            if window.user_role == 'admin':
                # Create balloon with row number
                balloon_color = QColor(30, 144, 255)  # Dodger Blue
                circle_pen = QPen(balloon_color)
                circle_pen.setWidth(3)

                # Calculate balloon position
                x_coords = [p[0] for p in bbox]
                y_coords = [p[1] for p in bbox]
                center_x = (min(x_coords) + max(x_coords)) / 2
                top_y = min(y_coords)

                # Create circle part of balloon
                circle_radius = 12
                circle_rect = QRectF(
                    center_x - circle_radius,
                    top_y - circle_radius * 2.5,
                    circle_radius * 2,
                    circle_radius * 2
                )
                window.balloon_circle = QGraphicsEllipseItem(circle_rect)
                window.balloon_circle.setPen(circle_pen)
                window.balloon_circle.setBrush(QBrush(balloon_color))
                window.balloon_circle.setZValue(3)
                
                # Store balloon data for database
                window.balloon_circle.balloon_data = {
                    'table_row': row,
                    'type': 'circle',
                    'bbox': [
                        [circle_rect.x(), circle_rect.y()],
                        [circle_rect.x() + circle_rect.width(), circle_rect.y()],
                        [circle_rect.x() + circle_rect.width(), circle_rect.y() + circle_rect.height()],
                        [circle_rect.x(), circle_rect.y() + circle_rect.height()]
                    ]
                }

                # Create triangle part of balloon
                triangle_path = QPainterPath()
                triangle_path.moveTo(center_x, top_y)
                triangle_path.lineTo(center_x - 6, top_y - 10)
                triangle_path.lineTo(center_x + 6, top_y - 10)
                triangle_path.lineTo(center_x, top_y)

                window.balloon_triangle = QGraphicsPathItem(triangle_path)
                window.balloon_triangle.setPen(circle_pen)
                window.balloon_triangle.setBrush(QBrush(balloon_color))
                window.balloon_triangle.setZValue(3)
                
                # Store balloon data for database
                window.balloon_triangle.balloon_data = {
                    'table_row': row,
                    'type': 'triangle',
                    'bbox': [
                        [center_x - 6, top_y - 10],
                        [center_x + 6, top_y - 10],
                        [center_x, top_y]
                    ]
                }

                # Add row number text
                window.balloon_text = QGraphicsTextItem(str(row + 1))
                window.balloon_text.setDefaultTextColor(Qt.white)
                
                # Center text in circle
                text_rect = window.balloon_text.boundingRect()
                text_x = center_x - text_rect.width() / 2
                text_y = top_y - circle_radius * 2.5 + (circle_radius * 2 - text_rect.height()) / 2
                window.balloon_text.setPos(text_x, text_y)
                window.balloon_text.setZValue(4)
                
                # Store balloon data for database
                window.balloon_text.balloon_data = {
                    'table_row': row,
                    'type': 'text',
                    'text': str(row + 1),
                    'bbox': [
                        [text_x, text_y],
                        [text_x + text_rect.width(), text_y],
                        [text_x + text_rect.width(), text_y + text_rect.height()],
                        [text_x, text_y + text_rect.height()]
                    ]
                }

                # Add balloon elements to scene
                window.ui.pdf_view.scene().addItem(window.balloon_circle)
                window.ui.pdf_view.scene().addItem(window.balloon_triangle)
                window.ui.pdf_view.scene().addItem(window.balloon_text)

        except Exception as e:
            print(f"Error highlighting bbox: {str(e)}") 