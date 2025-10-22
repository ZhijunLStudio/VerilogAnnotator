from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import Qt, QPointF

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_model, entity_model, parent_item):
        super().__init__(-5, -5, 10, 10, parent=parent_item)
        self.port_model = port_model
        self.entity_model = entity_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        
        color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
        self.setBrush(QBrush(color_map.get(port_model.direction, "#AAAAAA")))
        self.setPen(QPen(QColor("black"), 1))
        
        display_text = entity_model.label if entity_model.box is None else port_model.label
        self.label = QGraphicsTextItem(display_text, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B"))
        font = self.label.font(); font.setPointSize(8); self.label.setFont(font)
        self.label.setPos(10, -8)
        self.update_tooltip()

    def update_tooltip(self):
        self.setToolTip(f"Label: {self.port_model.label}\nID: {self.port_model.id}\nDirection: {self.port_model.direction}")

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            new_pos = self.pos()
            diagram = self.scene().parent().diagram
            diagram.update_port_position(self.entity_model.id, self.port_model.id, [new_pos.x(), new_pos.y()])
            for line in self.connection_lines: line.update_path()
        return result

    def hoverEnterEvent(self, event): self.setPen(QPen(QColor("gold"), 2)); super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event): self.setPen(QPen(QColor("black"), 1)); super().hoverLeaveEvent(event)
        
class EntityItem(QGraphicsRectItem):
    def __init__(self, entity_model):
        self.entity_model = entity_model
        if entity_model.box:
            super().__init__(0, 0, entity_model.box[0], entity_model.box[1])
            self.setPen(QPen(QColor(0, 0, 255, 200), 2)); self.setBrush(QBrush(QColor(0, 0, 255, 30)))
        else: # Terminals
            super().__init__(-5, -5, 10, 10)
            self.setPen(QPen(Qt.GlobalColor.transparent)); self.setBrush(QBrush(Qt.GlobalColor.transparent))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f"Label: {self.entity_model.label}\nType: {self.entity_model.type}\nID: {self.entity_model.id}")
        self.setZValue(0)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            new_pos = self.pos()
            self.scene().parent().diagram.update_entity_position(self.entity_model.id, [new_pos.x(), new_pos.y()])
            for child in self.childItems():
                if isinstance(child, PortItem):
                    for line in child.connection_lines: line.update_path()
        return result

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

class ConnectionLineItem(QGraphicsPathItem):
    def __init__(self, connection_model, source_port_item, dest_port_item):
        super().__init__()
        self.connection_model = connection_model
        self.source_port = source_port_item; self.dest_port = dest_port_item
        self.source_port.connection_lines.append(self); self.dest_port.connection_lines.append(self)
        self.setPen(QPen(QColor("#1E90FF"), 2.5)); self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.update_tooltip()

    def update_tooltip(self):
        self.setToolTip(f"ID: {self.connection_model['id']}\nLabel: {self.connection_model.get('label','')}")

    def update_path(self):
        if self.scene() and self.source_port.scene() and self.dest_port.scene():
            path = QPainterPath(); path.moveTo(self.source_port.scenePos()); path.lineTo(self.dest_port.scenePos()); self.setPath(path)
            
    def sceneEvent(self, event):
        if event.type() == 18:
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)