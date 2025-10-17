# src/graphics_items.py
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import Qt, QRectF

class PortItem(QGraphicsEllipseItem):
    """A graphical item representing a movable port, as a CHILD of a ComponentItem."""
    def __init__(self, port_model, parent_item):
        super().__init__(-5, -5, 10, 10, parent=parent_item)
        self.port_model = port_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        
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
        # This is called when the PORT itself is moved (in Port Mode)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for line in self.connection_lines:
                line.update_path()
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.parentItem():
            parent_rect = self.parentItem().boundingRect()
            new_pos = value
            new_pos.setX(max(parent_rect.left(), min(new_pos.x(), parent_rect.right())))
            new_pos.setY(max(parent_rect.top(), min(new_pos.y(), parent_rect.bottom())))
            return new_pos

        return super().itemChange(change, value)


class ComponentItem(QGraphicsRectItem):
    """A graphical item for the component box. It is a top-level item in the scene."""
    def __init__(self, component_model):
        if component_model.box and len(component_model.box) == 4:
            width = component_model.box[2] - component_model.box[0]
            height = component_model.box[3] - component_model.box[1]
            super().__init__(0, 0, width, height)
        else:
            super().__init__(0, 0, 0, 0); self.setVisible(False)

        self.component_model = component_model
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        self.setPen(QPen(QColor(0, 0, 255, 200), 2, Qt.PenStyle.SolidLine)) 
        self.setBrush(QBrush(QColor(0, 0, 255, 30)))
        self.setToolTip(f"Instance: {component_model.instance_name}\nType: {component_model.module_type}")

    def itemChange(self, change, value):
        # =========================================================================
        # === FIX: This is the critical fix for lines not following components. ===
        # =========================================================================
        # When the component (parent) moves, we must manually update the lines
        # connected to its child ports, because the children's ItemPositionHasChanged
        # signal is NOT emitted.
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for child in self.childItems():
                if isinstance(child, PortItem):
                    for line in child.connection_lines:
                        line.update_path()
                        
        return super().itemChange(change, value)


class ConnectionLineItem(QGraphicsPathItem):
    """A line connecting two PortItems."""
    def __init__(self, source_port_item, dest_port_item):
        super().__init__()
        self.source_port = source_port_item
        self.dest_port = dest_port_item
        
        self.source_port.connection_lines.append(self)
        self.dest_port.connection_lines.append(self)
        
        self.setPen(QPen(QColor("#4A4A4A"), 1.5, Qt.PenStyle.SolidLine))
        self.setZValue(1)

    def update_path(self):
        if self.scene():
            path = QPainterPath()
            path.moveTo(self.source_port.scenePos())
            path.lineTo(self.dest_port.scenePos())
            self.setPath(path)

    def sceneEvent(self, event):
        if event.type() == 18: # GraphicsSceneHelp (workaround for item removal notification)
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)