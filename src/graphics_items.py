from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem, QGraphicsSimpleTextItem, QGraphicsPolygonItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QCursor, QPolygonF
from PyQt6.QtCore import Qt, QRectF, QPointF

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_model, parent_item=None):
        super().__init__(-5, -5, 10, 10, parent=parent_item)
        self.port_model = port_model
        self.connection_lines = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges); self.setAcceptHoverEvents(True)
        
        # --- NEW: Set Z-value to ensure ports are rendered and selected above lines ---
        self.setZValue(2)
        
        color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}
        color = color_map.get(port_model.direction, QColor("#F57C00"))
        self.setBrush(QBrush(color))
        
        if port_model.was_manually_positioned:
            self.setPen(QPen(QColor("black"), 1))
        else:
            self.setPen(QPen(QColor("cyan"), 1.5, Qt.PenStyle.DashLine))

        if port_model.component.module_type in ("InputPort", "OutputPort"):
            display_text = port_model.component.label
        else:
            display_text = port_model.name
        
        self.label = QGraphicsTextItem(display_text, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B")); font = self.label.font(); font.setPointSize(8); self.label.setFont(font)
        self.label.setPos(10, -8)
        
        self.update_tooltip()

    def update_tooltip(self):
        net_name = self.port_model.net.name if self.port_model.net else "N/A"
        pos_status = "Manual" if self.port_model.was_manually_positioned else "Auto"
        self.setToolTip(f"Label: {self.port_model.label}\nName: {self.port_model.name}\nNet: {net_name}\nType: {self.port_model.direction}\nPosition: {pos_status}")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.parentItem():
            parent_rect = self.parentItem().boundingRect()
            value.setX(max(parent_rect.left(), min(value.x(), parent_rect.right())))
            value.setY(max(parent_rect.top(), min(value.y(), parent_rect.bottom())))
        try: result = super().itemChange(change, value)
        except TypeError: result = value
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            new_scene_pos = self.scenePos()
            self.scene().parent().diagram.update_port_position(
                self.port_model.component.instance_name, self.port_model.name,
                [new_scene_pos.x(), new_scene_pos.y()]
            )
            self.setPen(QPen(QColor("black"), 1))
            self.update_tooltip()
            for line in self.connection_lines: line.update_path()
        return result

    def hoverEnterEvent(self, event): self.setPen(QPen(QColor("gold"), 2)); super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event):
        pen_color = QColor("black") if self.port_model.was_manually_positioned else QColor("cyan")
        pen_style = Qt.PenStyle.SolidLine if self.port_model.was_manually_positioned else Qt.PenStyle.DashLine
        self.setPen(QPen(pen_color, 1.5, pen_style))
        super().hoverLeaveEvent(event)

class GroupItem(QGraphicsPolygonItem):
    def __init__(self, group_model):
        super().__init__()
        self.group_model = group_model
        
        polygon = QPolygonF([QPointF(p[0], p[1]) for p in group_model.points])
        self.setPolygon(polygon)
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        self.setPen(QPen(QColor("#FFD700"), 2, Qt.PenStyle.DashLine))
        self.setBrush(QBrush(QColor(255, 215, 0, 20)))
        self.setZValue(-10)

        self.label = QGraphicsSimpleTextItem(group_model.label, self)
        self.label.setBrush(QBrush(QColor("#FFD700")))
        font = self.label.font(); font.setPointSize(12); font.setBold(True); self.label.setFont(font)
        self.update_label_position()

    def update_label_position(self):
        br = self.boundingRect()
        self.label.setPos(br.topLeft() + QPointF(5, 5))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # When the polygon itself is moved, its points are automatically in the new coordinate system.
            # We need to map them back to scene coordinates before saving.
            new_scene_polygon = self.mapToScene(self.polygon())
            new_points = [[p.x(), p.y()] for p in new_scene_polygon]
            self.scene().parent().diagram.update_group_polygon(self.group_model.name, new_points)
        return super().itemChange(change, value)
        
class ResizeHandle(QGraphicsRectItem):
    def __init__(self, parent, position_flags):
        super().__init__(-4, -4, 8, 8, parent)
        self.parent = parent; self.position_flags = position_flags
        self._is_resizing = False
        self.setBrush(QBrush(QColor("white"))); self.setPen(QPen(QColor("black"), 1))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor({1: Qt.CursorShape.SizeFDiagCursor, 4: Qt.CursorShape.SizeFDiagCursor, 2: Qt.CursorShape.SizeBDiagCursor, 8: Qt.CursorShape.SizeBDiagCursor}.get(position_flags, Qt.CursorShape.ArrowCursor))

    def itemChange(self, change, value):
        if self._is_resizing: return value
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            self._is_resizing = True
            try: self.parent.resize_from_handle(self.position_flags, value)
            finally: self._is_resizing = False
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
        self.handle_positions = { self.Handle_TopLeft: rect.topLeft(), self.Handle_TopRight: rect.topRight(), self.Handle_BottomLeft: rect.bottomLeft(), self.Handle_BottomRight: rect.bottomRight() }
        for pos_flag in self.handle_positions.keys():
            self.handles[pos_flag] = ResizeHandle(self, pos_flag)
        self.update_handle_positions(); self.set_handles_visible(False)
        
    def set_handles_visible(self, visible):
        is_active = visible and self.scene() and self.scene().parent().edit_mode == 'component' and self.isSelected()
        for handle in self.handles.values(): handle.setVisible(is_active); handle.setEnabled(is_active)
    def update_handle_positions(self):
        rect = self.rect()
        self.handles[self.Handle_TopLeft].setPos(rect.topLeft()); self.handles[self.Handle_TopRight].setPos(rect.topRight()); self.handles[self.Handle_BottomLeft].setPos(rect.bottomLeft()); self.handles[self.Handle_BottomRight].setPos(rect.bottomRight())
    def resize_from_handle(self, handle_flag, new_pos):
        rect = self.rect()
        if handle_flag == self.Handle_TopLeft: rect.setTopLeft(new_pos)
        elif handle_flag == self.Handle_TopRight: rect.setTopRight(new_pos)
        elif handle_flag == self.Handle_BottomLeft: rect.setBottomLeft(new_pos)
        elif handle_flag == self.Handle_BottomRight: rect.setBottomRight(new_pos)
        self.prepareGeometryChange(); self.setRect(rect.normalized()); self.update_handle_positions()
        for child in self.childItems():
            if isinstance(child, PortItem):
                for line in child.connection_lines: line.update_path()
    def itemChange(self, change, value):
        try: result = super().itemChange(change, value)
        except TypeError: result = value
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            diagram = self.scene().parent().diagram
            pos = self.pos(); rect = self.rect()
            diagram.update_component_box(self.component_model.instance_name, [pos.x(), pos.y(), pos.x() + rect.width(), pos.y() + rect.height()])
            for child in self.childItems():
                if isinstance(child, PortItem):
                    child_scene_pos = child.scenePos()
                    diagram.update_port_position(child.port_model.component.instance_name, child.port_model.name, [child_scene_pos.x(), child_scene_pos.y()])
                    child.setPen(QPen(QColor("black"), 1)); child.update_tooltip()
                    for line in child.connection_lines: line.update_path()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged: self.set_handles_visible(bool(value))
        return result
    def hoverEnterEvent(self, event):
        if self.isSelected(): self.set_handles_visible(True)
        super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event):
        self.set_handles_visible(False)
        super().hoverLeaveEvent(event)
    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected(): painter.setPen(QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(self.boundingRect())

class ConnectionLabelItem(QGraphicsSimpleTextItem):
    def __init__(self, text, connection_line_item):
        super().__init__(text)
        self.connection_line = connection_line_item
        self.setBrush(QBrush(QColor("#E0E0E0"))); self.setZValue(2)
    def update_position(self):
        p1 = self.connection_line.source_port.scenePos(); p2 = self.connection_line.dest_port.scenePos()
        self.setPos(QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2))

class ConnectionLineItem(QGraphicsPathItem):
    def __init__(self, source_port_item, dest_port_item):
        super().__init__()
        self.source_port = source_port_item; self.dest_port = dest_port_item
        self.source_port.connection_lines.append(self); self.dest_port.connection_lines.append(self)
        self.setPen(QPen(QColor("#1E90FF"), 2.5, Qt.PenStyle.SolidLine, cap=Qt.PenCapStyle.RoundCap))
        self.setZValue(1) # Render below ports
        self.label_item = None
        # --- MODIFIED: Not selectable by default to make ports easier to click ---
        # self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        
    def update_path(self):
        if self.scene() and self.source_port.scene() and self.dest_port.scene():
            path = QPainterPath(); path.moveTo(self.source_port.scenePos()); path.lineTo(self.dest_port.scenePos()); self.setPath(path)
            if self.label_item: self.label_item.update_position()
    def sceneEvent(self, event):
        if event.type() == 18:
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)