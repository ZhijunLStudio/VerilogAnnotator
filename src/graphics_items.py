from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsItem, QGraphicsTextItem, QGraphicsSimpleTextItem
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath
from PyQt6.QtCore import Qt, QPointF

class PortItem(QGraphicsEllipseItem):
    def __init__(self, port_model, entity_model, parent_item=None):
        is_terminal = parent_item is None
        radius = 8 if is_terminal else 5
        super().__init__(-radius, -radius, radius*2, radius*2, parent=parent_item)
        
        self.port_model, self.entity_model = port_model, entity_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges); self.setAcceptHoverEvents(True)
        self.setZValue(2)
        
        color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
        color = color_map.get(port_model.direction, "#AAAAAA")
        if is_terminal:
            self.setBrush(QBrush(color.lighter(120))); self.setPen(QPen(color.darker(150), 2))
        else:
            self.setBrush(QBrush(color)); self.setPen(QPen(QColor("black"), 1))
        
        display_text = entity_model.label if is_terminal else port_model.label
        self.label = QGraphicsTextItem(display_text, parent=self)
        self.label.setDefaultTextColor(QColor("#00008B")); font = self.label.font(); font.setPointSize(10 if is_terminal else 8); self.label.setFont(font)
        if is_terminal:
            rect = self.label.boundingRect(); self.label.setPos(-rect.width()/2, -rect.height()/2)
        else:
            self.label.setPos(10, -8)
        self.update_tooltip()

    def update_tooltip(self): self.setToolTip(f"Entity: {self.entity_model.label}\nPort: {self.port_model.label}\nID: {self.entity_model.id}")

    def itemChange(self, change, value):
        # FIX: Restore boundary constraints for ports on components
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() and self.parentItem():
            parent_rect = self.parentItem().boundingRect()
            # Constrain 'value' (the proposed new position) within the parent's rectangle
            value.setX(max(parent_rect.left(), min(value.x(), parent_rect.right())))
            value.setY(max(parent_rect.top(), min(value.y(), parent_rect.bottom())))

        result = super().itemChange(change, value)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            diagram = self.scene().parent().diagram
            is_terminal = self.parentItem() is None
            if is_terminal:
                diagram.update_entity_position(self.entity_model.id, [self.pos().x(), self.pos().y()])
            else:
                diagram.update_port_position(self.entity_model.id, self.port_model.id, [self.pos().x(), self.pos().y()])
            for line in self.connection_lines: line.update_path()
        return result

    def hoverEnterEvent(self, event): self.setPen(QPen(QColor("gold"), 3)); super().hoverEnterEvent(event)
    def hoverLeaveEvent(self, event):
        is_terminal = self.parentItem() is None
        if is_terminal:
            color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
            self.setPen(QPen(color_map.get(self.port_model.direction, "#AAAAAA").darker(150), 2))
        else: self.setPen(QPen(QColor("black"), 1))
        super().hoverLeaveEvent(event)
        
class EntityItem(QGraphicsRectItem):
    def __init__(self, entity_model):
        self.entity_model = entity_model
        super().__init__(0, 0, entity_model.box[0], entity_model.box[1])
        self.setPen(QPen(QColor(0, 0, 255, 200), 2)); self.setBrush(QBrush(QColor(0, 0, 255, 30)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable); self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f"Label: {self.entity_model.label}\nType: {self.entity_model.type}\nID: {self.entity_model.id}")
        self.setZValue(0)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.scene().parent().diagram.update_entity_position(self.entity_model.id, [self.pos().x(), self.pos().y()])
            for child in self.childItems():
                if isinstance(child, PortItem):
                    for line in child.connection_lines: line.update_path()
        return result

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

class GroupItem(QGraphicsRectItem):
    def __init__(self, group_model):
        self.group_model = group_model
        # The box is [x, y, width, height]
        super().__init__(0, 0, group_model.box[2], group_model.box[3])
        self.setPos(group_model.box[0], group_model.box[1])
        
        self.setPen(QPen(QColor("#FFD700"), 3, Qt.PenStyle.DashDotLine)) # Gold, dashed line
        self.setBrush(QBrush(QColor(255, 215, 0, 20))) # Transparent yellow fill
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1) # Draw it behind components
        
        self.label = QGraphicsSimpleTextItem(group_model.label, self)
        self.label.setBrush(QBrush(QColor("#FFD700"))); font = self.label.font(); font.setPointSize(14); font.setBold(True); self.label.setFont(font)
        self.label.setPos(5, 5)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

class ConnectionLineItem(QGraphicsPathItem):
    def __init__(self, connection_model, source_port_item, dest_port_item):
        super().__init__()
        self.connection_model = connection_model; self.source_port = source_port_item; self.dest_port = dest_port_item
        self.source_port.connection_lines.append(self); self.dest_port.connection_lines.append(self)
        self.setPen(QPen(QColor("#1E90FF"), 2.5)); self.setZValue(1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.label_item = None
        self.update_tooltip()

    def update_tooltip(self): self.setToolTip(f"ID: {self.connection_model['id']}\nLabel: {self.connection_model.get('label','')}")

    def update_path(self):
        if self.scene() and self.source_port.scene() and self.dest_port.scene():
            path = QPainterPath(); path.moveTo(self.source_port.scenePos()); path.lineTo(self.dest_port.scenePos()); self.setPath(path)
            if self.label_item: self.label_item.setPos((self.source_port.scenePos() + self.dest_port.scenePos()) / 2)
            
    def sceneEvent(self, event):
        if event.type() == 18:
             if self in self.source_port.connection_lines: self.source_port.connection_lines.remove(self)
             if self in self.dest_port.connection_lines: self.dest_port.connection_lines.remove(self)
        return super().sceneEvent(event)