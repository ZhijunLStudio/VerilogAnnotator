from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QCursor
from PyQt6.QtCore import Qt, QRectF

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_model, parent_item=None):
        super().__init__(-5, -5, 10, 10, parent=parent_item)
        self.port_model = port_model; self.connection_lines = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges); self.setAcceptHoverEvents(True)
        color = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}.get(port_model.direction, QColor("#F57C00"))
        self.setBrush(QBrush(color)); self.setPen(QPen(QColor("black"), 1))
        self.label = QGraphicsTextItem(port_model.name, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B")); font = self.label.font(); font.setPointSize(8); self.label.setFont(font)
        self.label.setPos(10, -8)
        net_name = port_model.net.name if port_model.net else "N/A"
        self.setToolTip(f"Port: {port_model.name}\nNet: {net_name}\nType: {port_model.direction}")

    # --- FINAL, ROBUST FIX ---
    def itemChange(self, change, value):
        # First, check for the dangerous notification. If it's found,
        # handle it and exit the function immediately. DO NOT call super().
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.scene():
                new_scene_pos = self.scenePos()
                self.scene().parent().diagram.update_port_position(
                    self.port_model.component.instance_name, self.port_model.name,
                    [new_scene_pos.x(), new_scene_pos.y()]
                )
                for line in self.connection_lines:
                    line.update_path()
            # The return value is ignored for this notification.
            return value

        # If the dangerous case was not met, proceed with other checks.
        # This one is safe to pass to super() later.
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.parentItem():
            parent_rect = self.parentItem().boundingRect()
            value.setX(max(parent_rect.left(), min(value.x(), parent_rect.right())))
            value.setY(max(parent_rect.top(), min(value.y(), parent_rect.bottom())))
            # The modified 'value' will be passed to super() below.

        # Finally, for all safe cases, call the base class implementation.
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event): self.setPen(QPen(QColor("gold"), 2)); super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event): self.setPen(QPen(QColor("black"), 1)); super().hoverLeaveEvent(event)


class ResizeHandle(QGraphicsRectItem):
    # This class is correct and does not need changes.
    def __init__(self, parent, position_flags):
        super().__init__(-4, -4, 8, 8, parent)
        self.parent = parent
        self.position_flags = position_flags
        self._is_resizing = False
        self.setBrush(QBrush(QColor("white"))); self.setPen(QPen(QColor("black"), 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(self.get_cursor())

    def get_cursor(self):
        if self.position_flags in (1, 4): return QCursor(Qt.CursorShape.SizeFDiagCursor)
        if self.position_flags in (2, 8): return QCursor(Qt.CursorShape.SizeBDiagCursor)
        return QCursor(Qt.CursorShape.ArrowCursor)

    def itemChange(self, change, value):
        if self._is_resizing: return value
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            self._is_resizing = True
            try:
                self.parent.resize_from_handle(self.position_flags, value)
            finally:
                self._is_resizing = False
            return self.pos()
        return super().itemChange(change, value)


class ComponentItem(QGraphicsRectItem):
    Handle_TopLeft = 1; Handle_TopRight = 2; Handle_BottomRight = 4; Handle_BottomLeft = 8

    def __init__(self, component_model):
        if component_model.box and len(component_model.box) == 4:
            width = component_model.box[2] - component_model.box[0]
            height = component_model.box[3] - component_model.box[1]
            super().__init__(0, 0, width, height)
        else:
            super().__init__(0, 0, 0, 0); self.setVisible(False)
        self.component_model = component_model
        self.handles = {}
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges); self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor(0, 0, 255, 200), 2, Qt.PenStyle.SolidLine)); self.setBrush(QBrush(QColor(0, 0, 255, 30)))
        self.setToolTip(f"Instance: {component_model.instance_name}\nType: {component_model.module_type}")
        
        rect = self.boundingRect()
        self.handle_positions = {
            self.Handle_TopLeft: rect.topLeft(), self.Handle_TopRight: rect.topRight(),
            self.Handle_BottomLeft: rect.bottomLeft(), self.Handle_BottomRight: rect.bottomRight()
        }
        for pos_flag in self.handle_positions.keys():
            self.handles[pos_flag] = ResizeHandle(self, pos_flag)
            
        self.update_handle_positions(); self.set_handles_visible(False)

    def set_handles_visible(self, visible):
        is_active = visible and self.scene() and self.scene().parent().edit_mode == 'component' and self.isSelected()
        for handle in self.handles.values():
            handle.setVisible(is_active)
            handle.setEnabled(is_active)

    def update_handle_positions(self):
        rect = self.rect()
        self.handles[self.Handle_TopLeft].setPos(rect.topLeft())
        self.handles[self.Handle_TopRight].setPos(rect.topRight())
        self.handles[self.Handle_BottomLeft].setPos(rect.bottomLeft())
        self.handles[self.Handle_BottomRight].setPos(rect.bottomRight())

    def resize_from_handle(self, handle_flag, new_pos):
        rect = self.rect()
        if handle_flag == self.Handle_TopLeft: rect.setTopLeft(new_pos)
        elif handle_flag == self.Handle_TopRight: rect.setTopRight(new_pos)
        elif handle_flag == self.Handle_BottomLeft: rect.setBottomLeft(new_pos)
        elif handle_flag == self.Handle_BottomRight: rect.setBottomRight(new_pos)
        
        self.prepareGeometryChange()
        self.setRect(rect.normalized())
        self.update_handle_positions()
        
        for child in self.childItems():
            if isinstance(child, PortItem):
                for line in child.connection_lines:
                    line.update_path()

    # --- FINAL, ROBUST FIX ---
    def itemChange(self, change, value):
        # First, check for the dangerous notification. If it's found,
        # handle it and exit the function immediately. DO NOT call super().
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.scene():
                diagram = self.scene().parent().diagram
                pos = self.pos(); rect = self.rect()
                diagram.update_component_box(self.component_model.instance_name, [pos.x(), pos.y(), pos.x() + rect.width(), pos.y() + rect.height()])
                for child in self.childItems():
                    if isinstance(child, PortItem):
                        child_scene_pos = child.scenePos()
                        diagram.update_port_position(
                            child.port_model.component.instance_name, child.port_model.name,
                            [child_scene_pos.x(), child_scene_pos.y()]
                        )
                        for line in child.connection_lines:
                            line.update_path()
            return value

        # If the dangerous case was not met, proceed with other checks.
        # This one is safe to pass to super() later.
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.set_handles_visible(bool(value))

        # Finally, for all safe cases, call the base class implementation.
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        if self.isSelected(): self.set_handles_visible(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.set_handles_visible(False)
        super().hoverLeaveEvent(event)
    
    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("gold"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


class ConnectionLineItem(QGraphicsPathItem):
    # This class is correct and unchanged
    def __init__(self, source_port_item, dest_port_item):
        super().__init__()
        self.source_port = source_port_item; self.dest_port = dest_port_item
        self.source_port.connection_lines.append(self); self.dest_port.connection_lines.append(self)
        pen = QPen(QColor("#1E90FF"), 2.5, Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen); self.setZValue(1)
    def update_path(self):
        if self.scene() and self.source_port.scene() and self.dest_port.scene():
            path = QPainterPath(); path.moveTo(self.source_port.scenePos()); path.lineTo(self.dest_port.scenePos()); self.setPath(path)
    def sceneEvent(self, event):
        if event.type() == 18:
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)