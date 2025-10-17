# src/graphics_items.py
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem, QGraphicsSceneMouseEvent
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QCursor
from PyQt6.QtCore import Qt, QRectF, QPointF

class PortItem(QGraphicsEllipseItem):
    """A graphical item representing a movable port."""
    def __init__(self, port_model, parent_item=None):
        # If parent_item is None, this is a top-level terminal port.
        super().__init__(-5, -5, 10, 10, parent=parent_item)
        self.port_model = port_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        
        color = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}.get(port_model.direction, QColor("#F57C00"))
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("black"), 1))

        self.label = QGraphicsTextItem(port_model.name, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B"))
        font = self.label.font(); font.setPointSize(8); self.label.setFont(font)
        self.label.setPos(10, -8)

        net_name = port_model.net.name if port_model.net else "N/A"
        self.setToolTip(f"Port: {port_model.name}\nNet: {net_name}\nType: {port_model.direction}")
        
        if port_model.position:
            self.setPos(*port_model.position)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # When moved, update the data model and mark it as manually positioned
            new_scene_pos = self.scenePos()
            # If it has a parent, position is relative to parent. Otherwise, it's absolute.
            pos_to_save = self.pos() if self.parentItem() else new_scene_pos
            
            self.port_model.position = [pos_to_save.x(), pos_to_save.y()]
            self.port_model.was_manually_positioned = True
            
            for line in self.connection_lines:
                line.update_path()
        
        # BUG FIX: Allow moving within parent, but don't constrain if it's a parentless terminal
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.parentItem():
            parent_rect = self.parentItem().boundingRect()
            new_pos = value
            # Simple boundary constraint
            new_pos.setX(max(parent_rect.left(), min(new_pos.x(), parent_rect.right())))
            new_pos.setY(max(parent_rect.top(), min(new_pos.y(), parent_rect.bottom())))
            return new_pos

        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("gold"), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("black"), 1))
        super().hoverLeaveEvent(event)


class ResizeHandle(QGraphicsRectItem):
    """A resize handle for a ComponentItem."""
    def __init__(self, parent, position_flags):
        super().__init__(-4, -4, 8, 8, parent)
        self.parent = parent
        self.position_flags = position_flags
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor("black"), 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(self.get_cursor())

    def get_cursor(self):
        if self.position_flags in (1, 4): return QCursor(Qt.CursorShape.SizeFDiagCursor)
        if self.position_flags in (2, 8): return QCursor(Qt.CursorShape.SizeBDiagCursor)
        if self.position_flags in (16, 64): return QCursor(Qt.CursorShape.SizeVerCursor)
        if self.position_flags in (32, 128): return QCursor(Qt.CursorShape.SizeHorCursor)
        return QCursor(Qt.CursorShape.ArrowCursor)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            self.parent.resize_from_handle(self.position_flags, value)
            return self.pos() # The parent will reposition us, so we stay put
        return super().itemChange(change, value)


class ComponentItem(QGraphicsRectItem):
    """A graphical item for a component, now with resize handles."""
    Handle_TopLeft = 1; Handle_TopRight = 2; Handle_BottomRight = 4; Handle_BottomLeft = 8
    Handle_Top = 16; Handle_Right = 32; Handle_Bottom = 64; Handle_Left = 128

    def __init__(self, component_model):
        if component_model.box and len(component_model.box) == 4:
            width = component_model.box[2] - component_model.box[0]
            height = component_model.box[3] - component_model.box[1]
            super().__init__(0, 0, width, height)
        else:
            super().__init__(0, 0, 0, 0); self.setVisible(False)

        self.component_model = component_model
        self.handles = {}
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        self.setPen(QPen(QColor(0, 0, 255, 200), 2, Qt.PenStyle.SolidLine)) 
        self.setBrush(QBrush(QColor(0, 0, 255, 30)))
        self.setToolTip(f"Instance: {component_model.instance_name}\nType: {component_model.module_type}")

        # Create handles
        self.handle_positions = {
            self.Handle_TopLeft: (0, 0),
            self.Handle_TopRight: (1, 0),
            self.Handle_BottomLeft: (0, 1),
            self.Handle_BottomRight: (1, 1),
        }
        for pos_flag, (x_ratio, y_ratio) in self.handle_positions.items():
            handle = ResizeHandle(self, pos_flag)
            self.handles[pos_flag] = handle
        self.update_handle_positions()
        self.set_handles_visible(False)

    def set_handles_visible(self, visible):
        for handle in self.handles.values():
            handle.setVisible(visible)

    def update_handle_positions(self):
        rect = self.rect()
        for pos_flag, (x_ratio, y_ratio) in self.handle_positions.items():
            x = rect.left() + rect.width() * x_ratio
            y = rect.top() + rect.height() * y_ratio
            self.handles[pos_flag].setPos(x, y)

    def resize_from_handle(self, handle_flag, new_pos):
        rect = self.rect()
        if handle_flag == self.Handle_TopLeft: rect.setTopLeft(new_pos)
        elif handle_flag == self.Handle_TopRight: rect.setTopRight(new_pos)
        elif handle_flag == self.Handle_BottomLeft: rect.setBottomLeft(new_pos)
        elif handle_flag == self.Handle_BottomRight: rect.setBottomRight(new_pos)
        
        self.prepareGeometryChange()
        self.setRect(rect.normalized())
        self.update_handle_positions()
        # Also update child ports' lines
        self.itemChange(self.GraphicsItemChange.ItemPositionHasChanged, self.pos())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for child in self.childItems():
                if isinstance(child, PortItem):
                    for line in child.connection_lines:
                        line.update_path()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        if self.isSelected():
            self.set_handles_visible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_handles_visible(False)
        super().hoverLeaveEvent(event)
    
    def paint(self, painter, option, widget):
        # Show selection rectangle clearly
        if self.isSelected():
            self.set_handles_visible(True)
            pen = QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self.boundingRect())
        
        super().paint(painter, option, widget)


class ConnectionLineItem(QGraphicsPathItem):
    """A line connecting two PortItems."""
    def __init__(self, source_port_item, dest_port_item):
        super().__init__()
        self.source_port = source_port_item
        self.dest_port = dest_port_item
        
        self.source_port.connection_lines.append(self)
        self.dest_port.connection_lines.append(self)
        
        # UI IMPROVEMENT: More visible line color
        pen = QPen(QColor("#1E90FF"), 2.5, Qt.PenStyle.SolidLine) # Dodger Blue, thicker
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(1) # Draw behind ports

    def update_path(self):
        if self.scene() and self.source_port.scene() and self.dest_port.scene():
            path = QPainterPath()
            path.moveTo(self.source_port.scenePos())
            path.lineTo(self.dest_port.scenePos())
            self.setPath(path)

    def sceneEvent(self, event):
        if event.type() == 18: # GraphicsSceneHelp (workaround for item removal notification)
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)