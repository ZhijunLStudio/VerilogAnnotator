# src/graphics_items.py
from PyQt6.QtWidgets import (
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem, 
    QGraphicsItem, QGraphicsTextItem, QGraphicsSimpleTextItem,
    QGraphicsPolygonItem
)
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF


class PortItem(QGraphicsEllipseItem):
    """端口图形项"""
    def __init__(self, port_model, component_model, parent_item=None):
        self.radius = 4 if parent_item else 8  # 减小端口大小，避免遮挡组件
        super().__init__(-self.radius, -self.radius, self.radius*2, self.radius*2, parent=parent_item)

        self.port_model = port_model
        self.component_model = component_model
        self.connection_lines = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, parent_item is not None)  # 只有内部端口可拖动
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(5)  # 提高Z值，但组件点击区域会更大
        
        # 颜色：外部端口用金色，内部端口用蓝色
        if parent_item is None:
            self.setBrush(QBrush(QColor("#FFD700")))
            self.setPen(QPen(QColor("#B8860B"), 2))
        else:
            self.setBrush(QBrush(QColor("#1E90FF")))
            self.setPen(QPen(QColor("#000080"), 1))
        
        # 标签
        display_text = port_model.id
        self.label = QGraphicsTextItem(display_text, parent=self)
        self.label.setDefaultTextColor(QColor("white"))
        font = self.label.font()
        font.setPointSize(9 if parent_item else 11)
        font.setBold(parent_item is None)
        self.label.setFont(font)
        
        # 标签位置
        rect = self.label.boundingRect()
        if parent_item is None:
            # 外部端口：标签在上方
            self.label.setPos(-rect.width()/2, -self.radius - rect.height() - 2)
        else:
            # 内部端口：标签在右侧
            self.label.setPos(self.radius + 3, -rect.height()/2)
        
        self.update_tooltip()

    def shape(self):
        path = QPainterPath()
        click_radius = self.radius + 5
        path.addEllipse(-click_radius, -click_radius, click_radius*2, click_radius*2)
        return path

    def update_tooltip(self):
        comp_name = self.component_model.id if self.component_model else "External"
        self.setToolTip(f"Component: {comp_name}\nPort: {self.port_model.id}")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # 限制端口在父组件内部（可以到边缘）
            new_pos = value
            if self.parentItem():
                parent_rect = self.parentItem().boundingRect()
                # 限制在父组件边界内（端口中心可以到边界）
                x = max(0, min(new_pos.x(), parent_rect.width()))
                y = max(0, min(new_pos.y(), parent_rect.height()))
                value = QPointF(x, y)
        
        result = super().itemChange(change, value)
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            # 更新模型中的坐标（绝对坐标）
            new_pos = self.scenePos()
            self.port_model.coord = [int(new_pos.x()), int(new_pos.y())]
            
            # 更新连线，过滤掉已被删除的线段
            valid_lines = []
            for line in self.connection_lines:
                try:
                    if line.scene():  # 检查线段是否仍在场景中
                        line.update_path()
                        valid_lines.append(line)
                except RuntimeError:
                    # 线段已被删除，跳过
                    pass
            self.connection_lines = valid_lines
        
        return result

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("lime"), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.parentItem() is None:
            self.setPen(QPen(QColor("#B8860B"), 2))
        else:
            self.setPen(QPen(QColor("#000080"), 1))
        super().hoverLeaveEvent(event)


class ComponentItem(QGraphicsItem):
    """组件图形项 - 支持矩形和多边形"""

    # 层级颜色配置 - 同层级框和端口使用同一色系
    # [框填充色, 框边框色, 端口填充色, 端口边框色]
    HIERARCHY_COLORS = [
        (QColor(255, 99, 71, 40), QColor("#FF6347"), QColor("#FF6347"), QColor("#CC4125")),      # 第0层: 番茄红系
        (QColor(30, 144, 255, 40), QColor("#1E90FF"), QColor("#1E90FF"), QColor("#000080")),    # 第1层: 道奇蓝系
        (QColor(50, 205, 50, 40), QColor("#32CD32"), QColor("#32CD32"), QColor("#228B22")),    # 第2层: 酸橙绿系
        (QColor(255, 165, 0, 40), QColor("#FFA500"), QColor("#FFA500"), QColor("#CC8400")),     # 第3层: 橙色系
        (QColor(147, 112, 219, 40), QColor("#9370DB"), QColor("#9370DB"), QColor("#6B3FA0")),  # 第4层: 中紫系
        (QColor(255, 105, 180, 40), QColor("#FF69B4"), QColor("#FF69B4"), QColor("#C71585")),  # 第5层: 热粉系
    ]
    
    def __init__(self, component_model, hierarchy_depth=0):
        super().__init__()
        self.component_model = component_model
        self.hierarchy_depth = hierarchy_depth
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(1)
        
        # 根据层级深度设置颜色
        self._setup_colors()
        
        self.pen_width = 2
        self.selected_pen_width = 3
        
        # 创建标签 - 使用深色背景上的白色文字
        self.label_item = QGraphicsTextItem(component_model.id, self)
        self.label_item.setDefaultTextColor(QColor("#1a1a2e"))  # 深色文字
        font = self.label_item.font()
        font.setPointSize(10)
        font.setBold(True)
        self.label_item.setFont(font)
        
        self.update_shape()
        self.update_tooltip()
    
    def _setup_colors(self):
        """根据层级和类型设置颜色"""
        if self.component_model.type == "container":
            # 容器使用虚线
            self.border_style = Qt.PenStyle.DashLine
        else:
            self.border_style = Qt.PenStyle.SolidLine

        # 根据层级深度选择颜色
        color_idx = self.hierarchy_depth % len(self.HIERARCHY_COLORS)
        colors = self.HIERARCHY_COLORS[color_idx]
        self.fill_color = colors[0]      # 框填充色
        self.border_color = colors[1]    # 框边框色
        self.port_fill_color = colors[2] # 端口填充色
        self.port_border_color = colors[3] # 端口边框色

    def update_shape(self):
        """根据模型更新形状"""
        shape = self.component_model.shape
        
        if shape["type"] == "rect":
            box = shape["box"]
            self.rect = QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1])
            # 设置位置为左上角
            self.setPos(box[0], box[1])
            # 标签放在顶部中央
            label_rect = self.label_item.boundingRect()
            self.label_item.setPos((self.rect.width() - label_rect.width()) / 2, -label_rect.height() - 2)
            
        elif shape["type"] == "polygon":
            points = shape["points"]
            # 计算边界框
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            min_x, min_y = min(xs), min(ys)
            
            # 转换为相对于左上角的坐标
            self.polygon_points = [QPointF(p[0] - min_x, p[1] - min_y) for p in points]
            self.setPos(min_x, min_y)
            
            # 标签放在多边形中心上方
            label_rect = self.label_item.boundingRect()
            center_x = sum(p.x() for p in self.polygon_points) / len(self.polygon_points)
            min_py = min(p.y() for p in self.polygon_points)
            self.label_item.setPos(center_x - label_rect.width()/2, min_py - label_rect.height() - 2)

    def boundingRect(self):
        shape = self.component_model.shape
        if shape["type"] == "rect":
            return QRectF(0, 0, self.rect.width(), self.rect.height())
        elif shape["type"] == "polygon":
            if self.polygon_points:
                polygon = QPolygonF(self.polygon_points)
                return polygon.boundingRect()
        return QRectF()

    def shape(self):
        """返回精确的形状用于点击检测"""
        path = QPainterPath()
        shape_type = self.component_model.shape["type"]
        
        if shape_type == "rect":
            rect = self.boundingRect()
            # 缩小一点，让边缘更容易点击到下面的组件
            rect = rect.adjusted(2, 2, -2, -2)
            path.addRect(rect)
        elif shape_type == "polygon" and self.polygon_points:
            polygon = QPolygonF(self.polygon_points)
            path.addPolygon(polygon)
        
        return path

    def paint(self, painter, option, widget):
        pen = QPen(self.border_color, self.pen_width, self.border_style)
        if self.isSelected():
            pen = QPen(QColor("lime"), self.selected_pen_width, Qt.PenStyle.SolidLine)
        
        painter.setPen(pen)
        painter.setBrush(QBrush(self.fill_color))
        
        shape = self.component_model.shape
        if shape["type"] == "rect":
            painter.drawRect(self.boundingRect())
        elif shape["type"] == "polygon":
            if self.polygon_points:
                polygon = QPolygonF(self.polygon_points)
                painter.drawPolygon(polygon)

    def update_tooltip(self):
        parent_info = f"\nParent: {self.component_model.parent}" if self.component_model.parent else ""
        children_info = f"\nChildren: {len(self.component_model.children)}" if self.component_model.children else ""
        self.setToolTip(f"ID: {self.component_model.id}\nType: {self.component_model.type}{parent_info}{children_info}")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            # 在位置变化前通知场景准备几何变化（避免拖影）
            self.prepareGeometryChange()
            self._old_pos = self.pos()
        
        result = super().itemChange(change, value)
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            new_pos = self.pos()
            
            # 更新模型中的 shape 坐标
            shape = self.component_model.shape
            if shape["type"] == "rect":
                box = shape["box"]
                width = box[2] - box[0]
                height = box[3] - box[1]
                shape["box"] = [int(new_pos.x()), int(new_pos.y()), 
                               int(new_pos.x() + width), int(new_pos.y() + height)]
            elif shape["type"] == "polygon":
                old_pos = getattr(self, '_old_pos', new_pos)
                delta_x = new_pos.x() - old_pos.x()
                delta_y = new_pos.y() - old_pos.y()
                shape["points"] = [[int(p[0] + delta_x), int(p[1] + delta_y)] 
                                  for p in shape["points"]]
            
            self._old_pos = QPointF(new_pos)
            
            # 更新子端口位置
            for child in self.childItems():
                if isinstance(child, PortItem):
                    child_pos = child.scenePos()
                    child.port_model.coord = [int(child_pos.x()), int(child_pos.y())]
                    # 更新连接线段位置，过滤掉已被删除的线段
                    valid_lines = []
                    for line in child.connection_lines:
                        try:
                            if line.scene():  # 检查线段是否仍在场景中
                                line.update_path()
                                valid_lines.append(line)
                        except RuntimeError:
                            # 线段已被删除，跳过
                            pass
                    child.connection_lines = valid_lines
            
            # 通知场景更新质心位置（使用延迟更新避免频繁刷新）
            if self.scene() and hasattr(self.scene(), 'parent'):
                main_window = self.scene().parent()
                if hasattr(main_window, 'update_connection_centroids'):
                    # 使用定时器延迟更新，避免拖动时的频繁刷新
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, main_window.update_connection_centroids)
            
            self.update_tooltip()
        
        return result

    def mouseDoubleClickEvent(self, event):
        """双击展开/收起容器"""
        if self.component_model.type == "container":
            # 通知主窗口切换展开状态
            if self.scene() and self.scene().parent():
                self.scene().parent().toggle_container_expansion(self.component_model.id)
        super().mouseDoubleClickEvent(event)


class ExternalPortItem(QGraphicsEllipseItem):
    """外部端口图形项（独立在画布上）"""
    def __init__(self, port_model):
        self.radius = 10
        super().__init__(-self.radius, -self.radius, self.radius*2, self.radius*2)
        
        self.port_model = port_model
        self.connection_lines = []
        
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(3)
        
        # 外部端口用金色
        self.setBrush(QBrush(QColor("#FFD700")))
        self.setPen(QPen(QColor("#B8860B"), 2))
        
        # 标签
        self.label = QGraphicsTextItem(port_model.id, self)
        self.label.setDefaultTextColor(QColor("white"))
        font = self.label.font()
        font.setPointSize(11)
        font.setBold(True)
        self.label.setFont(font)
        
        # 标签位置
        rect = self.label.boundingRect()
        self.label.setPos(-rect.width()/2, -self.radius - rect.height() - 2)
        
        # 设置位置
        coord = port_model.coord
        self.setPos(coord[0], coord[1])
        
        self.update_tooltip()

    def update_tooltip(self):
        self.setToolTip(f"External Port: {self.port_model.id}\nType: {self.port_model.type}")

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            new_pos = self.scenePos()
            self.port_model.coord = [int(new_pos.x()), int(new_pos.y())]
            
            # 更新连接线段位置，过滤掉已被删除的线段
            valid_lines = []
            for line in self.connection_lines:
                try:
                    if line.scene():  # 检查线段是否仍在场景中
                        line.update_path()
                        valid_lines.append(line)
                except RuntimeError:
                    # 线段已被删除，跳过
                    pass
            self.connection_lines = valid_lines
            
            # 通知场景更新质心位置
            if self.scene() and hasattr(self.scene(), 'parent'):
                main_window = self.scene().parent()
                if hasattr(main_window, 'update_connection_centroids'):
                    main_window.update_connection_centroids()
        
        return result

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("lime"), 2))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("#B8860B"), 2))
        super().hoverLeaveEvent(event)


class ConnectionSegmentItem(QGraphicsPathItem):
    """连接线段的图形项（从质心到端口）"""
    def __init__(self, connection_model, port_item, centroid_item, is_cross_level=False, color=None):
        super().__init__()
        self.connection_model = connection_model
        self.port_item = port_item
        self.centroid_item = centroid_item
        self.is_cross_level = is_cross_level

        # 注册到端口
        if port_item:
            port_item.connection_lines.append(self)

        # 设置颜色
        if color:
            self.normal_color = color
        elif is_cross_level:
            self.normal_color = QColor("#FF6B9D")  # 粉色表示跨层
        else:
            self.normal_color = QColor("#FFD700")  # 金色表示同层
        self.normal_width = 2

        self.setPen(QPen(self.normal_color, self.normal_width))
        self.setZValue(2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

        # 不在__init__中调用update_path，因为此时centroid_item可能还没有被添加到场景中
        # 路径更新应该在添加到场景后由调用者完成

    def update_path(self):
        """更新路径"""
        if self.port_item and self.centroid_item:
            try:
                # 检查项是否仍然有效
                if not self.port_item.scene() or not self.centroid_item.scene():
                    return
                path = QPainterPath()
                path.moveTo(self.centroid_item.scenePos())
                path.lineTo(self.port_item.scenePos())
                self.setPath(path)
            except RuntimeError:
                # 项可能已被删除
                pass

    def paint(self, painter, option, widget):
        # 如果被选中，加粗显示
        if self.isSelected():
            self.setPen(QPen(QColor("lime"), 3))
        else:
            self.setPen(QPen(self.normal_color, self.normal_width))
        super().paint(painter, option, widget)


class ConnectionCentroidItem(QGraphicsEllipseItem):
    """连接质心点 - 表示一组连接的质心"""
    def __init__(self, connection_model, port_items, is_cross_level=False, color=None):
        self.radius = 6
        super().__init__(-self.radius, -self.radius, self.radius*2, self.radius*2)

        self.connection_model = connection_model
        self.port_items = port_items  # [port_item1, port_item2, ...]
        self.is_cross_level = is_cross_level
        self.segment_items = []  # 关联的线段项

        # 设置颜色
        if color:
            self.normal_color = color
        elif is_cross_level:
            self.normal_color = QColor("#FF6B9D")  # 粉色
        else:
            self.normal_color = QColor("#FFD700")  # 金色

        self.setBrush(QBrush(self.normal_color))
        self.setPen(QPen(QColor("#B8860B"), 2))
        self.setZValue(5)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        # 注意：不在__init__中调用update_centroid_position，因为此时可能还没有添加到场景中
        # 位置计算应该在添加到场景后由调用者完成

        self.update_tooltip()

    def update_centroid_position(self):
        """计算并更新质心位置"""
        if not self.port_items:
            return

        # 计算所有端口的平均位置（质心）
        total_x = 0
        total_y = 0
        count = 0

        for port_item in self.port_items:
            if port_item and port_item.scene():
                try:
                    pos = port_item.scenePos()
                    total_x += pos.x()
                    total_y += pos.y()
                    count += 1
                except RuntimeError:
                    # 端口项可能已被删除
                    pass

        if count > 0:
            self.setPos(total_x / count, total_y / count)

    def update_segments(self):
        """更新所有关联的线段"""
        for segment in self.segment_items:
            try:
                if segment.scene():
                    segment.update_path()
            except RuntimeError:
                pass

    def update_tooltip(self):
        nodes_info = " → ".join([
            f"{n.get('component', 'external')}.{n.get('port', '')}"
            for n in self.connection_model.nodes
        ])
        level_info = " (Cross-level)" if self.is_cross_level else " (Same level)"
        self.setToolTip(f"Connection: {nodes_info}{level_info}\nClick to select all segments")

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("lime"), 3))
        # 高亮所有关联的线段
        for segment in self.segment_items:
            try:
                if segment.scene():
                    segment.setPen(QPen(QColor("lime"), 3))
            except RuntimeError:
                pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("#B8860B"), 2))
        # 恢复线段颜色
        for segment in self.segment_items:
            try:
                if segment.scene():
                    if segment.is_cross_level:
                        segment.setPen(QPen(QColor("#FF6B9D"), 2))
                    else:
                        segment.setPen(QPen(QColor("#FFD700"), 2))
            except RuntimeError:
                pass
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # 当选中状态改变时，同步选中所有线段
            is_selected = value
            for segment in self.segment_items:
                try:
                    if segment.scene():
                        segment.setSelected(is_selected)
                except RuntimeError:
                    pass
        return super().itemChange(change, value)


class HierarchyLineItem(QGraphicsPathItem):
    """层级关系线（父组件到子组件的虚线）"""
    def __init__(self, parent_item, child_item):
        super().__init__()
        self.parent_item = parent_item
        self.child_item = child_item
        
        pen = QPen(QColor("#888888"), 1, Qt.PenStyle.DotLine)
        self.setPen(pen)
        self.setZValue(0)
        
        self.update_path()

    def update_path(self):
        if self.parent_item and self.child_item:
            path = QPainterPath()
            path.moveTo(self.parent_item.scenePos())
            path.lineTo(self.child_item.scenePos())
            self.setPath(path)
