from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import Qt, QPointF

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_model, entity_model, parent_item=None):
        # If it's a terminal (no parent_item), the PortItem is the main body.
        # Otherwise, it's a small dot on a component.
        is_terminal = parent_item is None
        radius = 8 if is_terminal else 5
        super().__init__(-radius, -radius, radius*2, radius*2, parent=parent_item)
        
        self.port_model = port_model
        self.entity_model = entity_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        
        color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
        brush_color = color_map.get(port_model.direction, "#AAAAAA")
        if is_terminal:
            # Terminals are larger and have a border
            self.setBrush(QBrush(brush_color.lighter(120)))
            self.setPen(QPen(brush_color.darker(150), 2))
        else:
            self.setBrush(QBrush(brush_color))
            self.setPen(QPen(QColor("black"), 1))
        
        # Display entity label for terminals, port label for components
        display_text = entity_model.label
        self.label = QGraphicsTextItem(display_text, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B"))
        font = self.label.font(); font.setPointSize(10 if is_terminal else 8); self.label.setFont(font)
        # Center the label if it's a terminal
        if is_terminal:
            rect = self.label.boundingRect()
            self.label.setPos(-rect.width()/2, -rect.height()/2)
        else:
            self.label.setPos(10, -8)
        
        self.update_tooltip()

    def update_tooltip(self):
        self.setToolTip(f"Label: {self.entity_model.label}\nPort: {self.port_model.label}\nID: {self.entity_model.id}")

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            diagram = self.scene().parent().diagram
            is_terminal = self.parentItem() is None

            if is_terminal:
                # If this is a terminal, moving it updates the ENTITY's position
                new_pos = self.pos()
                diagram.update_entity_position(self.entity_model.id, [new_pos.x(), new_pos.y()])
            else:
                # If this is a port on a component, moving it updates the PORT's relative position
                new_pos = self.pos()
                diagram.update_port_position(self.entity_model.id, self.port_model.id, [new_pos.x(), new_pos.y()])

            for line in self.connection_lines: line.update_path()
        return result

    def hoverEnterEvent(self, event): self.setPen(QPen(QColor("gold"), 3)); super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event):
        is_terminal = self.parentItem() is None
        if is_terminal:
            color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
            border_color = color_map.get(self.port_model.direction, "#AAAAAA").darker(150)
            self.setPen(QPen(border_color, 2))
        else:
            self.setPen(QPen(QColor("black"), 1))
        super().hoverLeaveEvent(event)
        
class EntityItem(QGraphicsRectItem):
    # This class is now ONLY for components with a box.
    def __init__(self, entity_model):
        self.entity_model = entity_model
        super().__init__(0, 0, entity_model.box[0], entity_model.box[1])
        self.setPen(QPen(QColor(0, 0, 255, 200), 2)); self.setBrush(QBrush(QColor(0, 0, 255, 30)))

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