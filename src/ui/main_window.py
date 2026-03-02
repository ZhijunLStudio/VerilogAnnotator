# src/ui/main_window.py
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QGraphicsView,
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter,
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog, QGroupBox, QMenu,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QDialog, QLineEdit, QFormLayout,
    QDialogButtonBox, QComboBox, QGraphicsPixmapItem
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap, QPen, QColor, QCursor, QBrush
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import Diagram
from ..graphics_items import ComponentItem, PortItem, ExternalPortItem, ConnectionCentroidItem, ConnectionSegmentItem
from .style import DARK_THEME


class EditableGraphicsView(QGraphicsView):
    """可编辑的图形视图"""
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.drawing_mode = None
        self.start_pos = None
        self.temp_shape = None
        self.temp_points = []

        # 状态标志
        self._is_panning = False

        # 优化绘制性能
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 设置缩放锚点为鼠标位置
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event):
        """处理滚轮事件进行缩放"""
        zoom_in_factor = 1.1
        zoom_out_factor = 1 / zoom_in_factor

        # 获取当前缩放比例
        current_transform = self.transform()
        current_scale = current_transform.m11()

        # 限制缩放范围
        min_scale = 0.1
        max_scale = 5.0

        if event.angleDelta().y() > 0:
            # 放大
            new_scale = current_scale * zoom_in_factor
            if new_scale <= max_scale:
                self.scale(zoom_in_factor, zoom_in_factor)
        else:
            # 缩小
            new_scale = current_scale * zoom_out_factor
            if new_scale >= min_scale:
                self.scale(zoom_out_factor, zoom_out_factor)

        event.accept()

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        # 1. 优先处理特殊的绘图模式
        if self.drawing_mode:
            if self.drawing_mode == 'draw_rect' and event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = scene_pos
                # 创建临时矩形
                from PyQt6.QtWidgets import QGraphicsRectItem
                self.temp_shape = self.scene().addRect(
                    QRectF(self.start_pos, self.start_pos),
                    QPen(QColor("lime"), 2, Qt.PenStyle.DashLine)
                )
            elif self.drawing_mode == 'draw_polygon' and event.button() == Qt.MouseButton.LeftButton:
                # 添加多边形点
                self.temp_points.append([scene_pos.x(), scene_pos.y()])
                # 绘制临时多边形
                if len(self.temp_points) >= 2:
                    self._update_temp_polygon()
            elif self.drawing_mode == 'draw_polygon' and event.button() == Qt.MouseButton.RightButton:
                # 右键完成多边形
                if len(self.temp_points) >= 3:
                    self.main_window.finish_polygon_drawing(self.temp_points)
                self._clear_temp_drawing()
            elif self.drawing_mode == 'add_port':
                self.main_window.handle_add_port_click(scene_pos)
            elif self.drawing_mode == 'add_external_port':
                self.main_window.handle_add_external_port_click(scene_pos)
            elif self.drawing_mode == 'connect':
                self.main_window.handle_connection_click(scene_pos)
            elif self.drawing_mode == 'add_reference':
                self.main_window.handle_reference_click(scene_pos)
            elif self.drawing_mode == 'select_area' and event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = scene_pos
                from PyQt6.QtWidgets import QGraphicsRectItem
                self.temp_shape = self.scene().addRect(
                    QRectF(self.start_pos, self.start_pos),
                    QPen(QColor("cyan"), 2, Qt.PenStyle.DashLine),
                    QColor(0, 255, 255, 30)
                )

            if self.drawing_mode not in ['draw_polygon']:
                event.accept()
                return

        # 2. 处理普通模式下的交互
        # 如果按住 Alt，获取所有项并选择最小的那个（方便选择被遮挡的小组件）
        if event.modifiers() == Qt.KeyboardModifier.AltModifier:
            items = self.items(event.pos())
            component_items = [i for i in items if isinstance(i, ComponentItem)]
            if component_items:
                # 选择面积最小的组件（最可能是想要选的小组件）
                smallest = min(component_items, key=lambda x: x.boundingRect().width() * x.boundingRect().height())
                smallest.setSelected(True)
                event.accept()
                return

        # 获取点击位置的所有项，按优先级选择
        items = self.items(event.pos())

        # 优先级：端口 > 组件 > 质心点 > 线段
        selected_item = None
        for item in items:
            if isinstance(item, PortItem) or isinstance(item, ExternalPortItem):
                selected_item = item
                break
            elif isinstance(item, ComponentItem) and selected_item is None:
                selected_item = item
            elif isinstance(item, ConnectionCentroidItem) and selected_item is None:
                selected_item = item
            elif isinstance(item, ConnectionSegmentItem) and selected_item is None:
                selected_item = item

        # 处理中键拖拽画布
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            event.accept()
            return

        # 如果是左键点击，且点击在空白区域，取消所有选中
        if event.button() == Qt.MouseButton.LeftButton and selected_item is None:
            # 取消所有选中
            self.scene().clearSelection()
            # 不进入拖拽模式，只是简单的点击
            event.accept()
        else:
            # 如果有选中的项，手动设置选中状态
            if selected_item:
                selected_item.setSelected(True)
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        # 处理中键拖拽画布
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        # 处理绘图过程中的鼠标移动
        if self.drawing_mode == 'draw_rect' and self.start_pos and self.temp_shape:
            self.temp_shape.setRect(QRectF(self.start_pos, scene_pos).normalized())
        elif self.drawing_mode == 'select_area' and self.start_pos and self.temp_shape:
            # 更新框选区域
            self.temp_shape.setRect(QRectF(self.start_pos, scene_pos).normalized())
        elif self.drawing_mode == 'draw_polygon' and len(self.temp_points) >= 1:
            # 更新临时多边形预览
            self._update_temp_polygon_preview(scene_pos)
        elif self.drawing_mode == 'connect' and self.main_window.pending_port:
            # 更新临时连线
            self._update_temp_connection_line(scene_pos)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # 1. 处理矩形绘制结束
        if self.drawing_mode == 'draw_rect' and self.start_pos and self.temp_shape:
            rect = self.temp_shape.rect()
            self.scene().removeItem(self.temp_shape)
            self.temp_shape = None
            self.start_pos = None

            if rect.width() > 10 and rect.height() > 10:
                self.main_window.create_new_component_from_rect(rect)

            self.main_window.exit_drawing_mode()

        # 2. 处理框选区域结束
        elif self.drawing_mode == 'select_area' and self.start_pos and self.temp_shape:
            rect = self.temp_shape.rect()
            self.scene().removeItem(self.temp_shape)
            self.temp_shape = None
            self.start_pos = None

            if rect.width() > 10 and rect.height() > 10:
                self.main_window.handle_select_area(rect)

            self.main_window.exit_drawing_mode()

        # 3. 处理中键拖拽结束
        elif self._is_panning:
            self._is_panning = False
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            event.accept()

        else:
            super().mouseReleaseEvent(event)

    def _update_temp_polygon(self):
        """更新临时多边形显示"""
        if self.temp_shape:
            self.scene().removeItem(self.temp_shape)

        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtWidgets import QGraphicsPolygonItem

        points = [QPointF(p[0], p[1]) for p in self.temp_points]
        polygon = QPolygonF(points)

        self.temp_shape = QGraphicsPolygonItem(polygon)
        self.temp_shape.setPen(QPen(QColor("lime"), 2, Qt.PenStyle.DashLine))
        self.scene().addItem(self.temp_shape)

    def _update_temp_polygon_preview(self, current_pos):
        """更新多边形预览（包含当前鼠标位置）"""
        if self.temp_shape:
            self.scene().removeItem(self.temp_shape)

        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtWidgets import QGraphicsPolygonItem

        points = [QPointF(p[0], p[1]) for p in self.temp_points]
        points.append(current_pos)
        polygon = QPolygonF(points)

        self.temp_shape = QGraphicsPolygonItem(polygon)
        self.temp_shape.setPen(QPen(QColor("lime"), 2, Qt.PenStyle.DashLine))
        self.scene().addItem(self.temp_shape)

    def _update_temp_connection_line(self, current_pos):
        """更新临时连线"""
        if not hasattr(self, '_temp_line') or self._temp_line is None:
            from PyQt6.QtWidgets import QGraphicsLineItem
            start_pos = self.main_window.pending_port.scenePos()
            self._temp_line = self.scene().addLine(
                start_pos.x(), start_pos.y(),
                current_pos.x(), current_pos.y(),
                QPen(QColor("lime"), 2, Qt.PenStyle.DashLine)
            )
            self._temp_line.setZValue(10)
        else:
            start_pos = self.main_window.pending_port.scenePos()
            self._temp_line.setLine(start_pos.x(), start_pos.y(),
                                   current_pos.x(), current_pos.y())

    def _clear_temp_drawing(self):
        """清除临时绘图元素"""
        if self.temp_shape:
            try:
                if self.temp_shape.scene():
                    self.scene().removeItem(self.temp_shape)
            except RuntimeError:
                pass  # 对象已被删除
            self.temp_shape = None
        if hasattr(self, '_temp_line') and self._temp_line:
            try:
                if self._temp_line.scene():
                    self.scene().removeItem(self._temp_line)
            except RuntimeError:
                pass
            self._temp_line = None
        self.start_pos = None
        self.temp_points = []

    def contextMenuEvent(self, event):
        if not self._is_panning:
            self.main_window.show_context_menu(self.mapToScene(event.pos()), event.globalPos())


class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circuit Annotator")
        self.resize(1800, 1000)

        # 数据模型
        self.diagram = Diagram()

        # 状态
        self.image_files = []
        self.current_index = -1
        self.image_folder = None
        self.json_folder = None
        self.cache_folder = None

        # 图形项映射
        self.component_items = {}
        self.port_items = {}
        self.external_port_items = {}
        self.connection_items = []
        self.junction_items = []

        # 编辑状态
        self.pending_port = None
        self.connection_start_port = None
        self.expanded_containers = set()  # 展开的容器
        self.dimmed_components = set()    # 淡化的组件
        self.hidden_components = set()    # 隐藏的组件
        self.current_filter_level = -1    # 当前过滤的层级 (-1 表示全部)
        self.selected_component = None    # 当前选中的组件（用于高亮）

        self._init_ui()
        self._init_cache()

    def _init_cache(self):
        """初始化缓存文件夹"""
        if self.json_folder:
            self.cache_folder = self.json_folder / ".cache"
            self.cache_folder.mkdir(exist_ok=True)

    def _init_ui(self):
        """初始化UI"""
        self.setStyleSheet(DARK_THEME)

        # 工具栏
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        # 文件操作
        self.act_save = QAction("Save (Ctrl+S)", self, triggered=self.save_current, shortcut=QKeySequence.StandardKey.Save)
        toolbar.addAction(self.act_save)
        toolbar.addSeparator()

        # 绘制工具（带快捷键）
        self.act_draw_rect = QAction("Draw Rect (W)", self, triggered=lambda: self.enter_drawing_mode('draw_rect'))
        self.act_draw_rect.setShortcut(QKeySequence("W"))
        self.addAction(self.act_draw_rect)

        self.act_draw_polygon = QAction("Draw Polygon (E)", self, triggered=lambda: self.enter_drawing_mode('draw_polygon'))
        self.act_draw_polygon.setShortcut(QKeySequence("E"))
        self.addAction(self.act_draw_polygon)

        self.act_add_port = QAction("Add Port (R)", self, triggered=lambda: self.enter_drawing_mode('add_port'))
        self.act_add_port.setShortcut(QKeySequence("R"))
        self.addAction(self.act_add_port)

        self.act_add_external_port = QAction("Add External Port (T)", self, triggered=lambda: self.enter_drawing_mode('add_external_port'))
        self.act_add_external_port.setShortcut(QKeySequence("T"))
        self.addAction(self.act_add_external_port)

        self.act_connect = QAction("Connect (C)", self, triggered=lambda: self.enter_drawing_mode('connect'))
        self.act_connect.setShortcut(QKeySequence("C"))
        self.addAction(self.act_connect)

        self.act_add_reference = QAction("Add Reference (F)", self, triggered=lambda: self.enter_drawing_mode('add_reference'))
        self.act_add_reference.setShortcut(QKeySequence("F"))
        self.addAction(self.act_add_reference)

        toolbar.addAction(self.act_draw_rect)
        toolbar.addAction(self.act_draw_polygon)
        toolbar.addAction(self.act_add_port)
        toolbar.addAction(self.act_add_external_port)
        toolbar.addAction(self.act_connect)
        toolbar.addAction(self.act_add_reference)
        toolbar.addSeparator()

        # 删除
        self.act_delete = QAction("Delete (Del)", self, triggered=self.delete_selected, shortcut=QKeySequence.StandardKey.Delete)
        toolbar.addAction(self.act_delete)
        toolbar.addSeparator()

        # 快捷键说明
        shortcut_label = QLabel("Shortcuts: W-Rect E-Poly R-Port T-ExtPort C-Connect F-Ref Del-Delete")
        shortcut_label.setStyleSheet("color: #888; font-size: 10px;")
        toolbar.addWidget(shortcut_label)

        # 主分割器
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)

        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # 文件夹选择
        folder_group = QGroupBox("Folders")
        folder_layout = QVBoxLayout(folder_group)

        self.btn_img_folder = QPushButton("1. Select Image Folder")
        self.btn_img_folder.clicked.connect(lambda: self.select_folder('image'))

        self.btn_json_folder = QPushButton("2. Select JSON Folder")
        self.btn_json_folder.clicked.connect(lambda: self.select_folder('json'))

        folder_layout.addWidget(self.btn_img_folder)
        folder_layout.addWidget(self.btn_json_folder)
        left_layout.addWidget(folder_group)

        # 文件列表
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        left_layout.addWidget(self.file_list)

        # 层级树
        hierarchy_group = QGroupBox("Hierarchy")
        hierarchy_layout = QVBoxLayout(hierarchy_group)

        self.hierarchy_tree = QTreeWidget()
        self.hierarchy_tree.setHeaderLabel("Components")
        self.hierarchy_tree.itemClicked.connect(self.on_hierarchy_item_clicked)
        hierarchy_layout.addWidget(self.hierarchy_tree)

        # 视图控制按钮已移除（功能集成到选择逻辑中）
        # 选中组件自动高亮，点击空白处恢复

        left_layout.addWidget(hierarchy_group)

        # 图形视图
        self.scene = QGraphicsScene(self)
        self.view = EditableGraphicsView(self.scene, self)

        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 层级过滤器面板
        level_group = QGroupBox("Hierarchy Levels")
        level_layout = QVBoxLayout(level_group)

        self.level_list = QListWidget()
        self.level_list.setMaximumHeight(150)
        self.level_list.itemClicked.connect(self.on_level_item_clicked)
        level_layout.addWidget(self.level_list)

        # 层级颜色图例 - 同层级框和端口使用同一色系
        legend_layout = QVBoxLayout()
        self.level_colors = [
            ("Level 0", "#FF6347", "Tomato"),      # 番茄红系
            ("Level 1", "#1E90FF", "DodgerBlue"),  # 道奇蓝系
            ("Level 2", "#32CD32", "LimeGreen"),   # 酸橙绿系
            ("Level 3", "#FFA500", "Orange"),      # 橙色系
            ("Level 4+", "#9370DB", "MediumPurple"), # 中紫系
        ]
        for level_name, color, name in self.level_colors:
            label = QLabel(f"  {level_name}: {name}")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            legend_layout.addWidget(label)
        level_layout.addLayout(legend_layout)

        right_layout.addWidget(level_group)

        # 属性面板
        prop_group = QGroupBox("Properties")
        prop_layout = QVBoxLayout(prop_group)

        self.info_label = QLabel("Select an item...")
        self.info_label.setWordWrap(True)
        prop_layout.addWidget(self.info_label)

        # 操作按钮（精简）
        self.btn_rename = QPushButton("Rename (F2)")
        self.btn_rename.clicked.connect(self.rename_selected)
        prop_layout.addWidget(self.btn_rename)

        right_layout.addWidget(prop_group)
        right_layout.addStretch(1)

        # 添加到分割器
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(self.view)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([300, 1200, 250])

        # 状态栏
        self.setStatusBar(QStatusBar())

        # 选择变化信号
        self.scene.selectionChanged.connect(self.on_selection_changed)

    def select_folder(self, folder_type):
        """选择文件夹"""
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not path:
            return

        p = Path(path)

        if folder_type == 'image':
            self.image_folder = p
            self.btn_img_folder.setText(f"Images: ...{p.name}")
        elif folder_type == 'json':
            self.json_folder = p
            self.cache_folder = p / ".cache"
            self.cache_folder.mkdir(exist_ok=True)
            self.btn_json_folder.setText(f"JSON: ...{p.name}")

        if self.image_folder and self.json_folder:
            self.scan_and_load_files()

    def scan_and_load_files(self):
        """扫描并加载文件"""
        if not self.image_folder:
            return

        self.image_files = sorted([
            f for f in self.image_folder.iterdir()
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.bmp')
        ])

        self.file_list.clear()
        for f in self.image_files:
            self.file_list.addItem(f.name)

        if self.image_files:
            self.file_list.setCurrentRow(0)

    def on_file_selected(self, current, _):
        """文件选择变化"""
        if not current:
            return

        # 保存当前
        if self.current_index != -1:
            self.save_current()

        new_index = self.file_list.row(current)
        if new_index == self.current_index:
            return

        self.current_index = new_index
        self.load_current_file()

    def load_current_file(self):
        """加载当前文件"""
        if not (0 <= self.current_index < len(self.image_files)):
            return

        # 重置视图
        self.view.resetTransform()

        img_path = self.image_files[self.current_index]
        json_path = self.json_folder / (img_path.stem + ".json")

        self.diagram = Diagram()

        if json_path.exists():
            # 加载已有标注
            if self.diagram.load_from_json(img_path, json_path):
                self.statusBar().showMessage(f"Loaded: {json_path.name}", 3000)
            else:
                self.statusBar().showMessage(f"Failed to load: {json_path.name}", 3000)
                self.diagram.image_path = img_path
        else:
            # 新建标注
            self.diagram.image_path = img_path
            self.statusBar().showMessage(f"New file: {img_path.name}", 3000)

        # 加载视图状态
        self.load_view_state()

        # 刷新显示
        self.refresh_scene()
        self.update_hierarchy_tree()

    def save_current(self):
        """保存当前文件"""
        if not self.diagram or not self.diagram.image_path or not self.json_folder:
            return

        json_path = self.json_folder / (Path(self.diagram.image_path).stem + ".json")

        if self.diagram.save_to_json(json_path):
            self.statusBar().showMessage(f"Saved: {json_path.name}", 2000)
        else:
            self.statusBar().showMessage(f"Failed to save: {json_path.name}", 2000)

        # 保存视图状态
        self.save_view_state()

    def save_view_state(self):
        """保存视图状态到缓存"""
        if not self.cache_folder:
            return

        state = {
            "expanded_containers": list(self.expanded_containers),
            "dimmed_components": list(self.dimmed_components),
            "hidden_components": list(self.hidden_components),
            "view_transform": {
                "m11": self.view.transform().m11(),
                "m12": self.view.transform().m12(),
                "m21": self.view.transform().m21(),
                "m22": self.view.transform().m22(),
                "dx": self.view.transform().dx(),
                "dy": self.view.transform().dy()
            }
        }

        img_name = Path(self.diagram.image_path).stem
        state_path = self.cache_folder / f"{img_name}.view_state.json"

        try:
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Failed to save view state: {e}")

    def load_view_state(self):
        """加载视图状态"""
        if not self.cache_folder or not self.diagram.image_path:
            return

        img_name = Path(self.diagram.image_path).stem
        state_path = self.cache_folder / f"{img_name}.view_state.json"

        if not state_path.exists():
            return

        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)

            self.expanded_containers = set(state.get("expanded_containers", []))
            self.dimmed_components = set(state.get("dimmed_components", []))
            self.hidden_components = set(state.get("hidden_components", []))

            # 恢复视图变换
            transform = state.get("view_transform")
            if transform:
                from PyQt6.QtGui import QTransform
                t = QTransform(
                    transform["m11"], transform["m12"],
                    transform["m21"], transform["m22"],
                    transform["dx"], transform["dy"]
                )
                self.view.setTransform(t)

        except Exception as e:
            print(f"Failed to load view state: {e}")

    def refresh_scene(self):
        """刷新场景显示"""
        self.scene.clear()
        self.component_items.clear()
        self.port_items.clear()
        self.external_port_items.clear()
        self.connection_centroids = []
        self.connection_segments = []

        # 添加背景图
        if self.diagram.image_path:
            pixmap = QPixmap(str(self.diagram.image_path))
            bg_item = QGraphicsPixmapItem(pixmap)
            bg_item.setZValue(-1)
            # 背景图始终不透明
            bg_item.setOpacity(1.0)
            self.scene.addItem(bg_item)
            self.scene.setSceneRect(QRectF(pixmap.rect()))

        # 确定显示哪些组件
        if self.current_filter_level >= 0:
            # 层级过滤模式：显示该层级的所有组件（忽略展开/收起状态）
            visible_components = set()
            for comp_id, comp in self.diagram.components.items():
                if comp_id in self.hidden_components:
                    continue
                depth = self._get_component_level(comp)
                if self.current_filter_level == 4:
                    if depth >= 4:
                        visible_components.add(comp_id)
                elif depth == self.current_filter_level:
                    visible_components.add(comp_id)
        else:
            # All 模式：显示所有组件（不考虑展开/收起状态）
            visible_components = set()
            for comp_id, comp in self.diagram.components.items():
                if comp_id not in self.hidden_components:
                    visible_components.add(comp_id)

        # 按层级深度排序组件（先添加父级，再添加子级）
        def get_depth(comp_id):
            depth = 0
            comp = self.diagram.components.get(comp_id)
            while comp and comp.parent:
                depth += 1
                comp = self.diagram.components.get(comp.parent)
            return depth

        sorted_components = sorted(visible_components, key=get_depth)

        # 添加组件
        for comp_id in sorted_components:
            component = self.diagram.components[comp_id]

            # 计算层级深度
            depth = get_depth(comp_id)

            # 创建组件项，传递层级深度
            item = ComponentItem(component, hierarchy_depth=depth)
            self.component_items[comp_id] = item
            self.scene.addItem(item)

            # 设置 Z-Index：层级越深，Z-Index 越高
            item.setZValue(1 + depth * 10)

            # 应用淡化效果
            if comp_id in self.dimmed_components:
                item.setOpacity(0.3)

            # 添加端口 - 使用组件的颜色
            if comp_id in self.expanded_containers or component.type != "container":
                for port_id, port in component.ports.items():
                    port_item = PortItem(port, component, parent_item=item)
                    port_item.setPos(QPointF(port.coord[0] - item.pos().x(),
                                            port.coord[1] - item.pos().y()))
                    # 设置端口颜色为组件的同色系
                    port_item.setBrush(QBrush(item.port_fill_color))
                    port_item.setPen(QPen(item.port_border_color, 1))
                    self.port_items[(comp_id, port_id)] = port_item

        # 添加外部端口
        for port_id, port in self.diagram.external_ports.items():
            if port_id in self.hidden_components:
                continue

            item = ExternalPortItem(port)
            self.external_port_items[port_id] = item
            self.scene.addItem(item)

            if port_id in self.dimmed_components:
                item.setOpacity(0.3)

        # 添加连线
        print(f"[DEBUG] Creating connections...")
        self._create_connection_items_with_junctions()
        print(f"[DEBUG] refresh_scene completed")

    def _create_connection_items_with_junctions(self):
        """创建连线项，并检测交汇点创建枢纽"""
        from collections import defaultdict

        # 创建连接项（使用新的质心-线段模型）
        self.connection_centroids = []  # 质心点列表
        self.connection_segments = []   # 线段列表

        # 同层连接颜色（金色）
        same_level_color = QColor("#FFD700")

        # 跨层连接颜色映射（根据跨越的层级对来分配颜色）
        cross_level_colors = {
            # L0-L1: 粉色
            (0, 1): QColor("#FF6B9D"),
            (1, 0): QColor("#FF6B9D"),
            # L0-L2: 青色
            (0, 2): QColor("#4ECDC4"),
            (2, 0): QColor("#4ECDC4"),
            # L1-L2: 薄荷绿
            (1, 2): QColor("#95E1D3"),
            (2, 1): QColor("#95E1D3"),
            # L0-L3: 珊瑚红
            (0, 3): QColor("#F38181"),
            (3, 0): QColor("#F38181"),
            # L1-L3: 紫色
            (1, 3): QColor("#AA96DA"),
            (3, 1): QColor("#AA96DA"),
            # L2-L3: 浅粉
            (2, 3): QColor("#FCBAD3"),
            (3, 2): QColor("#FCBAD3"),
        }

        for conn in self.diagram.connections:
            # 收集端口项和层级信息（只要端口项存在就创建连接，不管组件是否"可见"）
            port_items = []
            component_levels = []

            for node in conn.nodes:
                comp_id = node.get("component")
                port_id = node.get("port")

                if comp_id == "external":
                    item = self.external_port_items.get(port_id)
                    if item and item.scene():
                        port_items.append(item)
                        component_levels.append(-1)
                else:
                    item = self.port_items.get((comp_id, port_id))
                    if item and item.scene():
                        port_items.append(item)
                        comp = self.diagram.components.get(comp_id)
                        if comp:
                            level = self._get_component_level(comp)
                            component_levels.append(level)
                        else:
                            component_levels.append(0)

            if len(port_items) >= 2 and component_levels:
                unique_levels = sorted(set(component_levels))
                is_cross_level = len(unique_levels) > 1

                # 确定连接颜色
                if is_cross_level:
                    # 跨层连接：根据跨越的层级对来分配颜色
                    level_pair = (unique_levels[0], unique_levels[-1])
                    connection_color = cross_level_colors.get(level_pair, QColor("#FF6B9D"))  # 默认粉色
                else:
                    # 同层连接：使用金色
                    connection_color = same_level_color

                try:
                    # 创建质心点
                    centroid = ConnectionCentroidItem(conn, port_items, is_cross_level=is_cross_level, color=connection_color)
                    self.scene.addItem(centroid)
                    self.connection_centroids.append(centroid)
                    # 添加到场景后再计算位置
                    centroid.update_centroid_position()

                    # 创建从质心到每个端口的线段
                    for port_item in port_items:
                        segment = ConnectionSegmentItem(conn, port_item, centroid, is_cross_level=is_cross_level, color=connection_color)
                        self.scene.addItem(segment)
                        self.connection_segments.append(segment)
                        centroid.segment_items.append(segment)
                        # 添加到场景后再更新路径
                        segment.update_path()
                except Exception as e:
                    import traceback
                    print(f"Error creating connection items: {e}")
                    print(f"Traceback: {traceback.format_exc()}")

    def _get_visible_components(self):
        """获取应该显示的组件列表"""
        visible = set()

        for comp_id, component in self.diagram.components.items():
            # 如果被隐藏，跳过
            if comp_id in self.hidden_components:
                continue

            # 检查是否在收起的容器内
            parent_id = component.parent
            is_hidden_by_parent = False

            while parent_id:
                if parent_id not in self.expanded_containers:
                    is_hidden_by_parent = True
                    break
                parent = self.diagram.components.get(parent_id)
                if not parent:
                    break
                parent_id = parent.parent

            if not is_hidden_by_parent:
                visible.add(comp_id)

        return visible

    def update_hierarchy_tree(self):
        """更新层级树"""
        self.hierarchy_tree.clear()

        # 获取顶层组件
        top_components = self.diagram.get_components_at_level(None)

        for comp_id in top_components:
            self._add_tree_item(None, comp_id)

        self.hierarchy_tree.expandAll()

        # 更新层级列表
        self._update_level_list()

    def _update_level_list(self):
        """更新层级列表（显示当前有多少层）"""
        self.level_list.clear()

        # 计算最大层级
        max_level = -1
        for comp_id, comp in self.diagram.components.items():
            depth = 0
            parent = comp.parent
            while parent:
                depth += 1
                parent = self.diagram.components.get(parent, {}).parent
            max_level = max(max_level, depth)

        # 添加 "All" 选项
        item = QListWidgetItem(f"All Levels ({len(self.diagram.components)} components)")
        item.setData(Qt.ItemDataRole.UserRole, -1)
        item.setSelected(True)
        self.level_list.addItem(item)

        # 添加每个层级
        for level in range(max_level + 1):
            count = sum(1 for comp in self.diagram.components.values()
                       if self._get_component_level(comp) == level)
            item = QListWidgetItem(f"Level {level} ({count} components)")
            item.setData(Qt.ItemDataRole.UserRole, level)
            # 设置颜色
            color = self.level_colors[min(level, 4)][1]
            item.setForeground(QColor(color))
            self.level_list.addItem(item)

    def _get_component_level(self, comp):
        """获取组件的层级深度"""
        depth = 0
        parent = comp.parent
        while parent:
            depth += 1
            parent = self.diagram.components.get(parent, {}).parent
        return depth

    def _update_items_opacity(self):
        """更新所有项的透明度（不刷新整个场景）"""
        # 背景图始终不透明（不更新）

        # 更新组件透明度
        for comp_id, item in list(self.component_items.items()):
            try:
                if comp_id in self.dimmed_components:
                    item.setOpacity(0.3)
                else:
                    item.setOpacity(1.0)
            except RuntimeError:
                # 项已被删除，从字典中移除
                del self.component_items[comp_id]

        # 更新外部端口透明度
        for port_id, item in list(self.external_port_items.items()):
            try:
                if port_id in self.dimmed_components:
                    item.setOpacity(0.3)
                else:
                    item.setOpacity(1.0)
            except RuntimeError:
                del self.external_port_items[port_id]

        # 更新质心点透明度
        for item in self.connection_centroids[:]:
            try:
                item.setOpacity(0.3 if self.dimmed_components else 1.0)
            except RuntimeError:
                self.connection_centroids.remove(item)

        # 更新线段透明度
        for item in self.connection_segments[:]:
            try:
                item.setOpacity(0.3 if self.dimmed_components else 1.0)
            except RuntimeError:
                self.connection_segments.remove(item)

    def on_level_item_clicked(self, item):
        """层级列表项点击"""
        level = item.data(Qt.ItemDataRole.UserRole)
        self.current_filter_level = level
        self.refresh_scene()

    def _add_tree_item(self, parent_item, comp_id):
        """递归添加树项"""
        component = self.diagram.components.get(comp_id)
        if not component:
            return

        # 创建树项
        if parent_item is None:
            tree_item = QTreeWidgetItem(self.hierarchy_tree)
        else:
            tree_item = QTreeWidgetItem(parent_item)

        tree_item.setText(0, comp_id)
        tree_item.setData(0, Qt.ItemDataRole.UserRole, comp_id)

        # 设置图标或样式
        if component.type == "container":
            tree_item.setForeground(0, QColor("#FFD700"))

        # 递归添加子组件
        for child_id in component.children:
            self._add_tree_item(tree_item, child_id)

    def on_hierarchy_item_clicked(self, item, column):
        """层级树项点击"""
        comp_id = item.data(0, Qt.ItemDataRole.UserRole)
        if comp_id and comp_id in self.component_items:
            item = self.component_items[comp_id]
            item.setSelected(True)
            self.view.centerOn(item)

    def update_connection_centroids(self):
        """更新所有连接质心的位置"""
        for centroid in getattr(self, 'connection_centroids', []):
            try:
                if centroid.scene():  # 检查质心点是否仍在场景中
                    centroid.update_centroid_position()
                    centroid.update_segments()
            except RuntimeError:
                # 质心点可能已被删除
                pass

    def enter_drawing_mode(self, mode):
        """进入绘图模式"""
        self.exit_drawing_mode()
        self.view.drawing_mode = mode
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(f"Mode: {mode}...")

    def exit_drawing_mode(self):
        """退出绘图模式"""
        self.view.drawing_mode = None
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.view._clear_temp_drawing()

        # 清除待连接端口
        if self.pending_port:
            self.pending_port = None

        # 清除待选引用源（只在引用模式下刷新）
        if hasattr(self, '_pending_reference_source') and self._pending_reference_source:
            self._pending_reference_source = None
            # 注意：不要在连接模式下调用refresh_scene，因为连接已经刷新过了
            # self.refresh_scene()  # 刷新以清除高亮

        self.statusBar().clearMessage()

    def create_new_component_from_rect(self, rect):
        """从矩形创建新组件 - 整合弹窗"""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QLineEdit, QComboBox, QPushButton, QGroupBox,
                                     QListWidget, QListWidgetItem)

        # 创建弹窗
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Component")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 基本信息
        layout.addWidget(QLabel("Component Type:"))
        type_input = QLineEdit("Res")
        layout.addWidget(type_input)

        layout.addWidget(QLabel("Base Name:"))
        name_input = QLineEdit("R")
        layout.addWidget(name_input)

        # 父级选择
        parent_group = QGroupBox("Parent (Container)")
        parent_layout = QVBoxLayout(parent_group)
        parent_combo = QComboBox()
        parent_combo.addItem("None (Top Level)")

        # 找到包含此区域的容器作为候选父级
        candidates = []
        for comp_id, comp in self.diagram.components.items():
            comp_box = comp.shape.get("box")
            if not comp_box:
                continue
            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])
            if comp_rect.contains(rect):
                candidates.append((comp_id, comp_rect.width() * comp_rect.height()))

        # 按面积排序，最小的（最直接的父级）排前面
        candidates.sort(key=lambda x: x[1])
        for comp_id, _ in candidates:
            parent_combo.addItem(comp_id)

        # 自动选择最合适的父级（面积最小的容器）
        if candidates:
            parent_combo.setCurrentIndex(1)  # 选择第一个候选（索引1，因为0是None）

        parent_layout.addWidget(parent_combo)
        layout.addWidget(parent_group)

        # 子级选择
        children_group = QGroupBox("Children (Components to include)")
        children_layout = QVBoxLayout(children_group)
        children_list = QListWidget()
        children_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        # 找到被此区域包含的组件作为候选子级
        child_candidates = []
        for comp_id, comp in self.diagram.components.items():
            comp_box = comp.shape.get("box")
            if not comp_box:
                continue
            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])
            if rect.contains(comp_rect):
                child_candidates.append(comp_id)

        for comp_id in child_candidates:
            item = QListWidgetItem(comp_id)
            children_list.addItem(item)
            item.setSelected(True)  # 默认选中

        children_layout.addWidget(children_list)
        layout.addWidget(children_group)

        # 引用选择
        ref_group = QGroupBox("References (Logical belonging)")
        ref_layout = QVBoxLayout(ref_group)
        ref_list = QListWidget()
        ref_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        for comp_id in self.diagram.components.keys():
            ref_list.addItem(comp_id)

        ref_layout.addWidget(ref_list)
        layout.addWidget(ref_group)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        type_name = type_input.text()
        base_name = name_input.text()

        if not type_name or not base_name:
            return

        # 创建 shape
        shape = {
            "type": "rect",
            "box": [int(rect.left()), int(rect.top()),
                   int(rect.right()), int(rect.bottom())]
        }

        # 添加组件
        component = self.diagram.add_component(base_name, type_name, shape)

        # 设置父级
        parent_text = parent_combo.currentText()
        if parent_text != "None (Top Level)":
            component.parent = parent_text
            parent_comp = self.diagram.components.get(parent_text)
            if parent_comp and component.id not in parent_comp.children:
                parent_comp.children.append(component.id)

        # 设置子级
        for i in range(children_list.count()):
            item = children_list.item(i)
            if item.isSelected():
                child_id = item.text()
                child_comp = self.diagram.components.get(child_id)
                if child_comp:
                    # 从旧父级移除
                    if child_comp.parent and child_comp.parent in self.diagram.components:
                        old_parent = self.diagram.components[child_comp.parent]
                        if child_id in old_parent.children:
                            old_parent.children.remove(child_id)
                    # 设置新父级
                    child_comp.parent = component.id
                    if child_id not in component.children:
                        component.children.append(child_id)

        # 设置引用
        for i in range(ref_list.count()):
            item = ref_list.item(i)
            if item.isSelected():
                ref_id = item.text()
                if ref_id not in component.references:
                    component.references.append(ref_id)

        # 刷新显示
        self.refresh_scene()
        self.update_hierarchy_tree()

        self.statusBar().showMessage(f"Created: {component.id}", 2000)

    def _assign_parent_by_level(self, new_component, rect):
        """根据当前层级模式分配父级"""
        target_level = self.current_filter_level

        if target_level == -1:
            # All 模式：自动检测层级关系
            self._auto_assign_hierarchy(new_component)
            return

        # 找到该层级下包含此区域的容器作为父级
        candidates = []
        for comp_id, comp in self.diagram.components.items():
            if comp_id == new_component.id:
                continue

            comp_level = self._get_component_level(comp)
            if comp_level != target_level - 1:
                continue  # 只找目标层级的上一层

            comp_box = comp.shape.get("box")
            if not comp_box:
                continue

            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])

            # 检查新组件是否在该组件内
            if comp_rect.contains(rect):
                candidates.append((comp_id, comp_rect.width() * comp_rect.height()))

        if candidates:
            # 选择面积最小的容器（最直接的父级）
            candidates.sort(key=lambda x: x[1])
            parent_id = candidates[0][0]
            new_component.parent = parent_id
            self.diagram.components[parent_id].children.append(new_component.id)

    def _auto_assign_hierarchy(self, new_component):
        """自动分配层级关系"""
        new_box = new_component.shape["box"]
        new_rect = QRectF(new_box[0], new_box[1], new_box[2] - new_box[0], new_box[3] - new_box[1])

        # 1. 检查新组件是否完全包含在某些组件内 -> 新组件成为父级
        for comp_id, comp in list(self.diagram.components.items()):
            if comp_id == new_component.id:
                continue

            comp_box = comp.shape.get("box")
            if not comp_box:
                continue

            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])

            # 如果新组件完全包含其他组件
            if new_rect.contains(comp_rect):
                # 新组件成为这些组件的父级
                if comp.parent:
                    # 从旧父级移除
                    old_parent = self.diagram.components.get(comp.parent)
                    if old_parent and comp_id in old_parent.children:
                        old_parent.children.remove(comp_id)

                comp.parent = new_component.id
                if comp_id not in new_component.children:
                    new_component.children.append(comp_id)

        # 2. 检查新组件是否完全包含在某些组件内 -> 这些组件成为父级
        for comp_id, comp in self.diagram.components.items():
            if comp_id == new_component.id:
                continue

            comp_box = comp.shape.get("box")
            if not comp_box:
                continue

            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])

            # 如果新组件完全在某个组件内
            if comp_rect.contains(new_rect):
                # 该组件成为新组件的父级
                new_component.parent = comp_id
                if new_component.id not in comp.children:
                    comp.children.append(new_component.id)
                break  # 只找最直接的父级

    def finish_polygon_drawing(self, points):
        """完成多边形绘制 - 整合弹窗"""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                     QLineEdit, QComboBox, QPushButton, QGroupBox,
                                     QListWidget, QListWidgetItem)

        if len(points) < 3:
            return

        # 计算边界框
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

        # 创建弹窗
        dialog = QDialog(self)
        dialog.setWindowTitle("Create Component (Polygon)")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # 基本信息
        layout.addWidget(QLabel("Component Type:"))
        type_input = QLineEdit("Block")
        layout.addWidget(type_input)

        layout.addWidget(QLabel("Base Name:"))
        name_input = QLineEdit("Block")
        layout.addWidget(name_input)

        # 父级选择
        parent_group = QGroupBox("Parent (Container)")
        parent_layout = QVBoxLayout(parent_group)
        parent_combo = QComboBox()
        parent_combo.addItem("None (Top Level)")

        # 找到包含此区域的容器作为候选父级
        candidates = []
        for comp_id, comp in self.diagram.components.items():
            comp_box = comp.shape.get("box")
            if not comp_box:
                continue
            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])
            if comp_rect.contains(rect):
                candidates.append((comp_id, comp_rect.width() * comp_rect.height()))

        candidates.sort(key=lambda x: x[1])
        for comp_id, _ in candidates:
            parent_combo.addItem(comp_id)

        if candidates:
            parent_combo.setCurrentIndex(1)

        parent_layout.addWidget(parent_combo)
        layout.addWidget(parent_group)

        # 子级选择
        children_group = QGroupBox("Children (Components to include)")
        children_layout = QVBoxLayout(children_group)
        children_list = QListWidget()
        children_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        child_candidates = []
        for comp_id, comp in self.diagram.components.items():
            comp_box = comp.shape.get("box")
            if not comp_box:
                continue
            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])
            if rect.contains(comp_rect):
                child_candidates.append(comp_id)

        for comp_id in child_candidates:
            item = QListWidgetItem(comp_id)
            children_list.addItem(item)
            item.setSelected(True)

        children_layout.addWidget(children_list)
        layout.addWidget(children_group)

        # 引用选择
        ref_group = QGroupBox("References (Logical belonging)")
        ref_layout = QVBoxLayout(ref_group)
        ref_list = QListWidget()
        ref_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

        for comp_id in self.diagram.components.keys():
            ref_list.addItem(comp_id)

        ref_layout.addWidget(ref_list)
        layout.addWidget(ref_group)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        type_name = type_input.text()
        base_name = name_input.text()

        if not type_name or not base_name:
            return

        # 创建 shape
        shape = {
            "type": "polygon",
            "points": [[int(p[0]), int(p[1])] for p in points]
        }

        # 添加组件
        component = self.diagram.add_component(base_name, type_name, shape)

        # 设置父级
        parent_text = parent_combo.currentText()
        if parent_text != "None (Top Level)":
            component.parent = parent_text
            parent_comp = self.diagram.components.get(parent_text)
            if parent_comp and component.id not in parent_comp.children:
                parent_comp.children.append(component.id)

        # 设置子级
        for i in range(children_list.count()):
            item = children_list.item(i)
            if item.isSelected():
                child_id = item.text()
                child_comp = self.diagram.components.get(child_id)
                if child_comp:
                    if child_comp.parent and child_comp.parent in self.diagram.components:
                        old_parent = self.diagram.components[child_comp.parent]
                        if child_id in old_parent.children:
                            old_parent.children.remove(child_id)
                    child_comp.parent = component.id
                    if child_id not in component.children:
                        component.children.append(child_id)

        # 设置引用
        for i in range(ref_list.count()):
            item = ref_list.item(i)
            if item.isSelected():
                ref_id = item.text()
                if ref_id not in component.references:
                    component.references.append(ref_id)

        # 刷新显示
        self.refresh_scene()
        self.update_hierarchy_tree()

        self.statusBar().showMessage(f"Created: {component.id}", 2000)

    def _auto_assign_hierarchy_polygon(self, new_component, points):
        """自动分配多边形层级关系"""
        # 计算多边形的边界框
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        new_rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

        # 1. 检查新组件是否完全包含在某些组件内 -> 新组件成为父级
        for comp_id, comp in list(self.diagram.components.items()):
            if comp_id == new_component.id:
                continue

            comp_box = comp.shape.get("box")
            if not comp_box:
                continue

            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])

            # 如果新组件完全包含其他组件
            if new_rect.contains(comp_rect):
                if comp.parent:
                    old_parent = self.diagram.components.get(comp.parent)
                    if old_parent and comp_id in old_parent.children:
                        old_parent.children.remove(comp_id)

                comp.parent = new_component.id
                if comp_id not in new_component.children:
                    new_component.children.append(comp_id)

        # 2. 检查新组件是否完全包含在某些组件内
        for comp_id, comp in self.diagram.components.items():
            if comp_id == new_component.id:
                continue

            comp_box = comp.shape.get("box")
            if not comp_box:
                continue

            comp_rect = QRectF(comp_box[0], comp_box[1], comp_box[2] - comp_box[0], comp_box[3] - comp_box[1])

            if comp_rect.contains(new_rect):
                new_component.parent = comp_id
                if new_component.id not in comp.children:
                    comp.children.append(new_component.id)
                break

    def handle_add_port_click(self, scene_pos):
        """处理添加端口点击 - 只能在当前层级的组件上添加"""
        # 查找点击的组件
        clicked_item = None
        for item in self.view.items(self.view.mapFromScene(scene_pos)):
            if isinstance(item, ComponentItem):
                clicked_item = item
                break

        if not clicked_item:
            return

        # 检查组件层级是否匹配当前标注层级
        comp_level = self._get_component_level(clicked_item.component_model)
        target_level = self.current_filter_level

        if target_level != -1 and comp_level != target_level:
            QMessageBox.warning(self, "Level Mismatch",
                              f"Current level is {target_level}, but this component is at level {comp_level}.\n"
                              f"Please select the correct level to annotate.")
            return

        # 获取端口名称
        port_name, ok = QInputDialog.getText(self, "Port Name", "Enter port name:",
                                            text="in")
        if not ok or not port_name:
            return

        # 添加端口
        coord = [int(scene_pos.x()), int(scene_pos.y())]
        port = self.diagram.add_port_to_component(
            clicked_item.component_model.id,
            port_name,
            coord
        )

        if port:
            self.refresh_scene()
            self.statusBar().showMessage(f"Added port: {port.id}", 2000)
        else:
            QMessageBox.warning(self, "Error", "Port must be inside component!")

    def handle_add_external_port_click(self, scene_pos):
        """处理添加外部端口点击"""
        # 获取端口名称和类型
        port_name, ok = QInputDialog.getText(self, "External Port Name", "Enter port name:",
                                            text="Vdd")
        if not ok or not port_name:
            return

        port_types = ["terminal", "label"]
        port_type, ok = QInputDialog.getItem(self, "Port Type", "Select type:",
                                            port_types, 0, False)
        if not ok:
            return

        # 添加外部端口
        coord = [int(scene_pos.x()), int(scene_pos.y())]
        port = self.diagram.add_external_port(port_name, port_type, coord)

        # 刷新显示
        self.refresh_scene()
        self.update_hierarchy_tree()

        self.statusBar().showMessage(f"Added external port: {port.id}", 2000)

    def handle_connection_click(self, scene_pos):
        """处理连接点击 - 支持端口吸附"""
        # 查找点击的端口（优先直接命中）
        clicked_port = None

        for item in self.view.items(self.view.mapFromScene(scene_pos)):
            if isinstance(item, PortItem) or isinstance(item, ExternalPortItem):
                clicked_port = item
                break

        # 如果没有直接命中，搜索附近最近的端口（吸附功能）
        if not clicked_port:
            snap_distance = 30  # 吸附距离（像素）- 增加容错范围
            nearest_port = None
            min_distance = float('inf')

            # 获取已选中的端口（避免重复选中同一个）
            pending_port_id = None
            if self.pending_port:
                if isinstance(self.pending_port, ExternalPortItem):
                    pending_port_id = ("external", self.pending_port.port_model.id)
                else:
                    pending_port_id = (self.pending_port.component_model.id, self.pending_port.port_model.id)

            # 搜索所有端口
            for (comp_id, port_id), port_item in self.port_items.items():
                # 跳过已选中的端口
                if pending_port_id and pending_port_id == (comp_id, port_id):
                    continue
                port_pos = port_item.scenePos()
                distance = ((port_pos.x() - scene_pos.x()) ** 2 +
                           (port_pos.y() - scene_pos.y()) ** 2) ** 0.5
                if distance < snap_distance and distance < min_distance:
                    min_distance = distance
                    nearest_port = port_item

            # 搜索外部端口
            for port_id, port_item in self.external_port_items.items():
                # 跳过已选中的端口
                if pending_port_id and pending_port_id == ("external", port_item.port_model.id):
                    continue
                port_pos = port_item.scenePos()
                distance = ((port_pos.x() - scene_pos.x()) ** 2 +
                           (port_pos.y() - scene_pos.y()) ** 2) ** 0.5
                if distance < snap_distance and distance < min_distance:
                    min_distance = distance
                    nearest_port = port_item

            clicked_port = nearest_port

        if not clicked_port:
            self.statusBar().showMessage("No port found nearby (click closer to a port)", 2000)
            return

        if not self.pending_port:
            # 第一个端口
            self.pending_port = clicked_port
            clicked_port.setBrush(QBrush(QColor("lime")))
            port_info = f"{clicked_port.component_model.id}.{clicked_port.port_model.id}" if hasattr(clicked_port, 'component_model') else f"external.{clicked_port.port_model.id}"
            self.statusBar().showMessage(f"First port: {port_info}. Select second port...")
        else:
            # 第二个端口
            if self.pending_port != clicked_port:
                # 创建连接 - 先保存端口信息，然后立即清除 pending_port
                try:
                    nodes = []

                    # 第一个端口
                    if isinstance(self.pending_port, ExternalPortItem):
                        nodes.append({"component": "external", "port": self.pending_port.port_model.id})
                    else:
                        nodes.append({
                            "component": self.pending_port.component_model.id,
                            "port": self.pending_port.port_model.id
                        })

                    # 第二个端口
                    if isinstance(clicked_port, ExternalPortItem):
                        nodes.append({"component": "external", "port": clicked_port.port_model.id})
                    else:
                        nodes.append({
                            "component": clicked_port.component_model.id,
                            "port": clicked_port.port_model.id
                        })

                    # 先清除 pending_port，避免 refresh_scene 时访问已删除的对象
                    self.pending_port = None

                    # 添加到模型
                    if self.diagram.add_connection(nodes):
                        self.refresh_scene()
                        self.statusBar().showMessage("Connection created", 2000)
                except Exception as e:
                    import traceback
                    print(f"Error creating connection: {e}")
                    print(f"Traceback: {traceback.format_exc()}")
                    self.statusBar().showMessage(f"Error: {str(e)}", 3000)

            # 清除待连接状态
            self.pending_port = None
            self.exit_drawing_mode()

    def handle_reference_click(self, scene_pos):
        """处理添加引用关系的点击"""
        # 查找点击的组件
        clicked_comp = None
        for item in self.view.items(self.view.mapFromScene(scene_pos)):
            if isinstance(item, ComponentItem):
                clicked_comp = item.component_model
                break

        if not clicked_comp:
            self.statusBar().showMessage("Please click on a component", 2000)
            return

        if not hasattr(self, '_pending_reference_source'):
            self._pending_reference_source = None

        if not self._pending_reference_source:
            # 第一个组件（源）
            self._pending_reference_source = clicked_comp
            # 高亮显示
            if clicked_comp.id in self.component_items:
                self.component_items[clicked_comp.id].setPen(QPen(QColor("magenta"), 4))
            self.statusBar().showMessage(f"Source: {clicked_comp.id}. Click on target component...")
        else:
            # 第二个组件（目标）
            source_comp = self._pending_reference_source
            target_comp = clicked_comp

            if source_comp.id == target_comp.id:
                self.statusBar().showMessage("Cannot reference self", 2000)
            else:
                # 添加引用关系
                if target_comp.id not in source_comp.references:
                    source_comp.references.append(target_comp.id)
                    self.refresh_scene()
                    self.statusBar().showMessage(f"Reference added: {source_comp.id} → {target_comp.id}", 2000)
                else:
                    self.statusBar().showMessage("Reference already exists", 2000)

            # 清除待选状态
            self._pending_reference_source = None
            self.exit_drawing_mode()

    def toggle_container_expansion(self, container_id):
        """切换容器展开状态"""
        if container_id in self.expanded_containers:
            self.expanded_containers.remove(container_id)
        else:
            self.expanded_containers.add(container_id)

        self.refresh_scene()

    def expand_all_containers(self):
        """展开所有容器"""
        for comp_id, comp in self.diagram.components.items():
            if comp.type == "container":
                self.expanded_containers.add(comp_id)
        self.refresh_scene()

    def collapse_all_containers(self):
        """收起所有容器"""
        self.expanded_containers.clear()
        self.refresh_scene()

    def dim_other_components(self):
        """淡化其他组件"""
        selected = self.scene.selectedItems()
        if not selected:
            return

        selected_ids = set()
        for item in selected:
            if isinstance(item, ComponentItem):
                selected_ids.add(item.component_model.id)
            elif isinstance(item, ExternalPortItem):
                selected_ids.add(item.port_model.id)

        # 淡化未选中的
        self.dimmed_components.clear()
        for comp_id in self.diagram.components:
            if comp_id not in selected_ids:
                self.dimmed_components.add(comp_id)
        for port_id in self.diagram.external_ports:
            if port_id not in selected_ids:
                self.dimmed_components.add(port_id)

        self.refresh_scene()

    def show_all_components(self):
        """显示所有组件"""
        self.dimmed_components.clear()
        self.hidden_components.clear()
        self.refresh_scene()

    def delete_selected(self):
        """删除选中的项"""
        # 先收集所有要删除的项，避免在遍历时修改
        items_to_delete = list(self.scene.selectedItems())

        # 检查是否选中了质心点或线段
        centroid_items_to_delete = [item for item in items_to_delete if isinstance(item, ConnectionCentroidItem)]
        segment_items_to_delete = [item for item in items_to_delete if isinstance(item, ConnectionSegmentItem)]

        # 处理质心点删除 - 删除整个连接
        connections_to_delete = set()
        for centroid in centroid_items_to_delete:
            connections_to_delete.add(id(centroid.connection_model))

        # 按索引从大到小删除连接
        indices_to_delete = []
        for i, conn in enumerate(self.diagram.connections):
            if id(conn) in connections_to_delete:
                indices_to_delete.append(i)
        for idx in sorted(indices_to_delete, reverse=True):
            self.diagram.delete_connection(idx)

        # 处理线段删除 - 只删除该线段对应的节点
        # 需要记录哪些连接已经被处理过（避免重复处理）
        processed_connections = set()
        for segment in segment_items_to_delete:
            conn = segment.connection_model
            conn_id = id(conn)

            # 如果这个连接已经被质心点删除，跳过
            if conn_id in connections_to_delete:
                continue

            # 如果这个连接已经有2个节点，删除整个连接
            # 如果有3个或更多节点，只删除该线段对应的节点
            if len(conn.nodes) <= 2:
                # 2个或更少节点，删除整个连接
                if conn_id not in processed_connections:
                    for i, c in enumerate(self.diagram.connections):
                        if id(c) == conn_id:
                            self.diagram.delete_connection(i)
                            processed_connections.add(conn_id)
                            break
            else:
                # 3个或更多节点，只删除该线段对应的节点
                if conn_id not in processed_connections:
                    # 找到该线段对应的节点
                    port_item = segment.port_item
                    if port_item:
                        if isinstance(port_item, ExternalPortItem):
                            node_to_remove = {"component": "external", "port": port_item.port_model.id}
                        else:
                            node_to_remove = {"component": port_item.component_model.id, "port": port_item.port_model.id}

                        # 找到连接在列表中的索引
                        for i, c in enumerate(self.diagram.connections):
                            if id(c) == conn_id:
                                self.diagram.remove_node_from_connection(i, node_to_remove)
                                processed_connections.add(conn_id)
                                break

        # 处理其他删除（组件、端口等）
        for item in items_to_delete:
            if isinstance(item, ComponentItem):
                self.diagram.delete_component(item.component_model.id)
            elif isinstance(item, ExternalPortItem):
                self.diagram.delete_external_port(item.port_model.id)
            elif isinstance(item, PortItem):
                self.diagram.delete_port(
                    item.component_model.id,
                    item.port_model.id
                )
            # ConnectionCentroidItem 和 ConnectionSegmentItem 已经在上面处理过了

        self.refresh_scene()
        self.update_hierarchy_tree()

    def rename_selected(self):
        """重命名选中的项"""
        selected = self.scene.selectedItems()
        if not selected:
            return

        item = selected[0]

        if isinstance(item, ComponentItem):
            old_id = item.component_model.id
            new_name, ok = QInputDialog.getText(self, "Rename", "Enter new base name:",
                                               text=old_id.split('_')[0])
            if ok and new_name:
                new_id = self.diagram.rename_component(old_id, new_name)
                if new_id:
                    self.refresh_scene()
                    self.update_hierarchy_tree()
                    self.statusBar().showMessage(f"Renamed to: {new_id}", 2000)

    def set_parent_for_selected(self):
        """为选中的组件设置父级"""
        selected = self.scene.selectedItems()
        if len(selected) != 1:
            QMessageBox.warning(self, "Error", "Please select exactly one component!")
            return

        item = selected[0]
        if not isinstance(item, ComponentItem):
            return

        comp_id = item.component_model.id

        # 获取可用的父级（不能是自己和子级）
        available_parents = ["None"]
        for cid, comp in self.diagram.components.items():
            if cid != comp_id and comp.type == "container":
                # 检查是否是自己的子级
                is_child = False
                parent = comp.parent
                while parent:
                    if parent == comp_id:
                        is_child = True
                        break
                    parent = self.diagram.components.get(parent, {}).parent

                if not is_child:
                    available_parents.append(cid)

        parent, ok = QInputDialog.getItem(self, "Set Parent", "Select parent:",
                                         available_parents, 0, False)
        if not ok:
            return

        # 更新父级
        component = self.diagram.components[comp_id]

        # 从旧父级中移除
        if component.parent and component.parent in self.diagram.components:
            old_parent = self.diagram.components[component.parent]
            if comp_id in old_parent.children:
                old_parent.children.remove(comp_id)

        # 设置新父级
        if parent == "None":
            component.parent = None
        else:
            component.parent = parent
            self.diagram.components[parent].children.append(comp_id)

        self.refresh_scene()
        self.update_hierarchy_tree()

    def add_selected_to_container(self):
        """将选中的组件添加到容器"""
        selected = self.scene.selectedItems()
        if len(selected) < 2:
            QMessageBox.warning(self, "Error", "Please select at least 2 components (container + items)!")
            return

        # 找出容器
        container_item = None
        child_items = []

        for item in selected:
            if isinstance(item, ComponentItem):
                if item.component_model.type == "container":
                    container_item = item
                else:
                    child_items.append(item)

        if not container_item:
            QMessageBox.warning(self, "Error", "Please select a container!")
            return

        container_id = container_item.component_model.id

        # 添加子级
        for child_item in child_items:
            child_id = child_item.component_model.id
            child = self.diagram.components[child_id]

            # 从旧父级移除
            if child.parent and child.parent in self.diagram.components:
                old_parent = self.diagram.components[child.parent]
                if child_id in old_parent.children:
                    old_parent.children.remove(child_id)

            # 添加到新父级
            child.parent = container_id
            if child_id not in container_item.component_model.children:
                container_item.component_model.children.append(child_id)

        self.refresh_scene()
        self.update_hierarchy_tree()

    def on_selection_changed(self):
        """选择变化 - 使用HTML高亮显示，并处理组件高亮"""
        selected = self.scene.selectedItems()

        if not selected:
            self.info_label.setText("Select an item...")
            # 清除高亮但不刷新场景（避免影响拖动）
            if self.selected_component is not None or self.dimmed_components:
                self.selected_component = None
                self.dimmed_components.clear()
                self._update_items_opacity()
            return

        item = selected[0]
        info_lines = []

        # 处理高亮逻辑 - 只更新透明度，不刷新整个场景
        if isinstance(item, ComponentItem):
            new_selection = item.component_model.id
            if self.selected_component != new_selection:
                self.selected_component = new_selection
                self.dimmed_components.clear()
                for comp_id in self.diagram.components:
                    if comp_id != self.selected_component:
                        self.dimmed_components.add(comp_id)
                self._update_items_opacity()
        elif isinstance(item, PortItem):
            new_selection = item.component_model.id
            if self.selected_component != new_selection:
                self.selected_component = new_selection
                self.dimmed_components.clear()
                for comp_id in self.diagram.components:
                    if comp_id != self.selected_component:
                        self.dimmed_components.add(comp_id)
                self._update_items_opacity()
        else:
            if self.selected_component is not None:
                self.selected_component = None
                self.dimmed_components.clear()
                self._update_items_opacity()

        # 定义键值颜色样式
        KEY_COLOR = "#4ECDC4"  # 青色键
        VALUE_COLOR = "#FFFFFF"  # 白色值
        HIGHLIGHT_COLOR = "#FFD700"  # 金色高亮

        if isinstance(item, ComponentItem):
            comp = item.component_model
            level = self._get_component_level(comp)
            color = self.level_colors[min(level, 4)][1]

            info_lines.append(f"<b style='color:{color};font-size:14px;'>📦 {comp.id}</b>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Type:</span> <span style='color:{VALUE_COLOR};'>{comp.type}</span>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Level:</span> <span style='color:{color};'>{level}</span>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Shape:</span> <span style='color:{VALUE_COLOR};'>{comp.shape['type']}</span>")

            if comp.parent:
                parent_comp = self.diagram.components.get(comp.parent)
                parent_level = self._get_component_level(parent_comp) if parent_comp else "?"
                parent_color = self.level_colors[min(parent_level, 4)][1] if isinstance(parent_level, int) else "#888"
                info_lines.append(f"<span style='color:{KEY_COLOR};'>Parent:</span> <span style='color:{parent_color};'>⬆ {comp.parent}</span>")
            else:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>Parent:</span> <span style='color:#888;'>None (Top Level)</span>")

            # 显示 Children（始终显示，即使没有）
            if comp.children:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>Children ({len(comp.children)}):</span>")
                for child_id in comp.children:
                    child_comp = self.diagram.components.get(child_id)
                    child_level = self._get_component_level(child_comp) if child_comp else "?"
                    child_color = self.level_colors[min(child_level, 4)][1] if isinstance(child_level, int) else "#888"
                    info_lines.append(f"  <span style='color:{child_color};'>⬇ {child_id}</span>")
            else:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>Children:</span> <span style='color:#888;'>None</span>")

            if comp.ports:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>Ports ({len(comp.ports)}):</span> <span style='color:{VALUE_COLOR};'>{', '.join(comp.ports.keys())}</span>")

            # 显示引用关系（始终显示，即使没有）
            if comp.references:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>References ({len(comp.references)}):</span>")
                for ref_id in comp.references:
                    ref_comp = self.diagram.components.get(ref_id)
                    if ref_comp:
                        ref_level = self._get_component_level(ref_comp)
                        ref_color = self.level_colors[min(ref_level, 4)][1]
                        info_lines.append(f"  <span style='color:{ref_color};'>↔ {ref_id}</span>")
                    else:
                        info_lines.append(f"  <span style='color:#888;'>↔ {ref_id}</span>")
            else:
                info_lines.append(f"<span style='color:{KEY_COLOR};'>References:</span> <span style='color:#888;'>None</span>")

        elif isinstance(item, PortItem):
            port_color = item.brush().color().name()
            info_lines.append(f"<b style='color:{port_color};'>🔌 {item.port_model.id}</b>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Component:</span> <span style='color:{VALUE_COLOR};'>{item.component_model.id}</span>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Coord:</span> <span style='color:{HIGHLIGHT_COLOR};'>{item.port_model.coord}</span>")

        elif isinstance(item, ExternalPortItem):
            info_lines.append(f"<b style='color:#FFD700;'>🔌 {item.port_model.id}</b>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Type:</span> <span style='color:{VALUE_COLOR};'>{item.port_model.type}</span>")
            info_lines.append(f"<span style='color:{KEY_COLOR};'>Coord:</span> <span style='color:{HIGHLIGHT_COLOR};'>{item.port_model.coord}</span>")

        elif isinstance(item, ConnectionCentroidItem):
            nodes = item.connection_model.nodes
            info_lines.append("<b>🔗 Connection (Centroid):</b>")
            for node in nodes:
                comp = node.get("component", "external")
                port = node.get("port", "")
                if comp == "external":
                    info_lines.append(f"  <span style='color:#FFD700;'>→ {comp}.{port}</span>")
                else:
                    comp_obj = self.diagram.components.get(comp)
                    if comp_obj:
                        level = self._get_component_level(comp_obj)
                        color = self.level_colors[min(level, 4)][1]
                        info_lines.append(f"  <span style='color:{color};'>→ {comp}.{port}</span>")
                    else:
                        info_lines.append(f"  → {comp}.{port}")

        self.info_label.setText("<br>".join(info_lines))

    def show_context_menu(self, scene_pos, global_pos):
        """显示右键菜单"""
        menu = QMenu(self)

        # 获取点击位置的组件
        clicked_item = None
        for item in self.view.items(self.view.mapFromScene(scene_pos)):
            if isinstance(item, ComponentItem):
                clicked_item = item
                break

        if clicked_item:
            # 在组件上右键
            comp = clicked_item.component_model

            # 层级操作
            hierarchy_menu = menu.addMenu("Hierarchy")

            if comp.parent:
                remove_parent_action = hierarchy_menu.addAction("Remove from Parent")
            else:
                remove_parent_action = None

            set_parent_action = hierarchy_menu.addAction("Set Parent...")

            # 引用关系管理
            hierarchy_menu.addSeparator()
            add_ref_action = hierarchy_menu.addAction("Add Reference...")
            if comp.references:
                remove_ref_menu = hierarchy_menu.addMenu("Remove Reference")
                for ref_id in comp.references:
                    remove_ref_menu.addAction(f"Remove {ref_id}")
            else:
                remove_ref_menu = None

            if comp.type == "container" and comp.children:
                hierarchy_menu.addSeparator()
                expand_action = hierarchy_menu.addAction("Expand" if comp.id not in self.expanded_containers else "Collapse")
            else:
                expand_action = None

            menu.addSeparator()

            # 组件操作
            rename_action = menu.addAction("Rename")
            delete_action = menu.addAction("Delete Component")

            menu.addSeparator()

            # 添加端口
            add_port_action = menu.addAction("Add Port Here")

            action = menu.exec(global_pos)

            if action == set_parent_action:
                self._quick_set_parent(comp.id)
            elif remove_parent_action and action == remove_parent_action:
                self._remove_from_parent(comp.id)
            elif action == add_ref_action:
                self._quick_add_reference(comp.id)
            elif remove_ref_menu and action in remove_ref_menu.actions():
                ref_id = action.text().replace("Remove ", "")
                self._quick_remove_reference(comp.id, ref_id)
            elif expand_action and action == expand_action:
                self.toggle_container_expansion(comp.id)
            elif action == rename_action:
                self._quick_rename(comp.id)
            elif action == delete_action:
                self.diagram.delete_component(comp.id)
                self.refresh_scene()
                self.update_hierarchy_tree()
            elif action == add_port_action:
                self._quick_add_port(comp.id, scene_pos)

        else:
            # 在空白处右键
            # 添加组件
            add_comp_menu = menu.addMenu("Add Component")
            add_rect_action = add_comp_menu.addAction("Rectangle")
            add_poly_action = add_comp_menu.addAction("Polygon")

            # 添加外部端口
            add_ext_port_action = menu.addAction("Add External Port Here")

            menu.addSeparator()

            # 视图控制
            expand_action = menu.addAction("Expand All")
            collapse_action = menu.addAction("Collapse All")
            show_all_action = menu.addAction("Show All")

            action = menu.exec(global_pos)

            if action == add_rect_action:
                self.enter_drawing_mode('draw_rect')
            elif action == add_poly_action:
                self.enter_drawing_mode('draw_polygon')
            elif action == add_ext_port_action:
                self._quick_add_external_port(scene_pos)
            elif action == expand_action:
                self.expand_all_containers()
            elif action == collapse_action:
                self.collapse_all_containers()
            elif action == show_all_action:
                self.show_all_components()

    def _quick_set_parent(self, child_id):
        """快速设置父级"""
        # 获取可用的容器（不能是自己和子级）
        available = ["None"]
        for cid, comp in self.diagram.components.items():
            if cid != child_id and comp.type == "container":
                # 检查是否是自己的子级
                is_child = False
                parent = comp.parent
                while parent:
                    if parent == child_id:
                        is_child = True
                        break
                    parent = self.diagram.components.get(parent, {}).parent
                if not is_child:
                    available.append(cid)

        parent, ok = QInputDialog.getItem(self, "Set Parent", "Select parent container:",
                                         available, 0, False)
        if not ok:
            return

        child = self.diagram.components[child_id]

        # 从旧父级移除
        if child.parent and child.parent in self.diagram.components:
            old_parent = self.diagram.components[child.parent]
            if child_id in old_parent.children:
                old_parent.children.remove(child_id)

        # 设置新父级
        if parent == "None":
            child.parent = None
        else:
            child.parent = parent
            self.diagram.components[parent].children.append(child_id)

        self.refresh_scene()
        self.update_hierarchy_tree()

    def _remove_from_parent(self, child_id):
        """从父级中移除"""
        child = self.diagram.components[child_id]
        if child.parent and child.parent in self.diagram.components:
            parent = self.diagram.components[child.parent]
            if child_id in parent.children:
                parent.children.remove(child_id)
        child.parent = None
        self.refresh_scene()
        self.update_hierarchy_tree()

    def _quick_add_reference(self, comp_id):
        """快速添加引用关系"""
        # 获取可用的组件（不能是自己和子级）
        available = []
        for cid, comp in self.diagram.components.items():
            if cid != comp_id:
                # 检查是否是自己的子级
                is_child = False
                parent = comp.parent
                while parent:
                    if parent == comp_id:
                        is_child = True
                        break
                    parent = self.diagram.components.get(parent, {}).parent
                if not is_child:
                    available.append(cid)

        if not available:
            QMessageBox.information(self, "No Available", "No available components to reference.")
            return

        ref_id, ok = QInputDialog.getItem(self, "Add Reference", "Select component to reference:",
                                         available, 0, False)
        if not ok:
            return

        comp = self.diagram.components[comp_id]
        if ref_id not in comp.references:
            comp.references.append(ref_id)
            self.refresh_scene()
            self.update_hierarchy_tree()
            self.statusBar().showMessage(f"Added reference: {comp_id} -> {ref_id}", 2000)

    def _quick_remove_reference(self, comp_id, ref_id):
        """快速移除引用关系"""
        comp = self.diagram.components[comp_id]
        if ref_id in comp.references:
            comp.references.remove(ref_id)
            self.refresh_scene()
            self.update_hierarchy_tree()
            self.statusBar().showMessage(f"Removed reference: {comp_id} -> {ref_id}", 2000)

    def _quick_rename(self, comp_id):
        """快速重命名"""
        old_id = comp_id
        new_name, ok = QInputDialog.getText(self, "Rename", "Enter new base name:",
                                           text=old_id.split('_')[0])
        if ok and new_name:
            new_id = self.diagram.rename_component(old_id, new_name)
            if new_id:
                self.refresh_scene()
                self.update_hierarchy_tree()
                self.statusBar().showMessage(f"Renamed to: {new_id}", 2000)

    def _quick_add_port(self, comp_id, scene_pos):
        """快速添加端口"""
        port_name, ok = QInputDialog.getText(self, "Port Name", "Enter port name:",
                                            text="in")
        if not ok or not port_name:
            return

        coord = [int(scene_pos.x()), int(scene_pos.y())]
        port = self.diagram.add_port_to_component(comp_id, port_name, coord)

        if port:
            self.refresh_scene()
            self.statusBar().showMessage(f"Added port: {port.id}", 2000)
        else:
            QMessageBox.warning(self, "Error", "Port must be inside component!")

    def _quick_add_external_port(self, scene_pos):
        """快速添加外部端口"""
        port_name, ok = QInputDialog.getText(self, "External Port Name", "Enter port name:",
                                            text="Vdd")
        if not ok or not port_name:
            return

        port_types = ["terminal", "label"]
        port_type, ok = QInputDialog.getItem(self, "Port Type", "Select type:",
                                            port_types, 0, False)
        if not ok:
            return

        coord = [int(scene_pos.x()), int(scene_pos.y())]
        port = self.diagram.add_external_port(port_name, port_type, coord)

        self.refresh_scene()
        self.update_hierarchy_tree()
        self.statusBar().showMessage(f"Added external port: {port.id}", 2000)

    def on_level_changed(self, index):
        """层级过滤改变"""
        self.refresh_scene()

    def reset_view(self):
        """重置视图"""
        self.view.resetTransform()

    def handle_select_area(self, rect):
        """处理框选区域 - 选择区域内的组件并弹出归属菜单"""
        # 找到区域内的所有组件
        selected_components = []

        for comp_id, component in self.diagram.components.items():
            shape = component.shape
            if shape["type"] == "rect":
                box = shape["box"]
                comp_rect = QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1])
            elif shape["type"] == "polygon":
                points = shape["points"]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                comp_rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            else:
                continue

            # 检查是否在框选区域内（完全包含或部分重叠）
            if rect.intersects(comp_rect):
                selected_components.append(comp_id)

        if not selected_components:
            self.statusBar().showMessage("No components selected in area", 2000)
            return

        # 显示归属菜单
        self._show_assign_to_container_menu(selected_components)

    def _show_assign_to_container_menu(self, component_ids):
        """显示归属容器选择菜单"""
        menu = QMenu(self)
        menu.setWindowTitle(f"Assign {len(component_ids)} components to:")

        # 获取可用的容器
        available_containers = []
        for cid, comp in self.diagram.components.items():
            if comp.type == "container" and cid not in component_ids:
                # 检查是否是自己的子级
                is_child = False
                for selected_id in component_ids:
                    parent = comp.parent
                    while parent:
                        if parent == selected_id:
                            is_child = True
                            break
                        parent = self.diagram.components.get(parent, {}).parent
                    if is_child:
                        break

                if not is_child:
                    available_containers.append(cid)

        # 添加选项
        none_action = menu.addAction("Remove from Parent (Top Level)")
        menu.addSeparator()

        container_actions = {}
        for cid in available_containers:
            action = menu.addAction(f"Container: {cid}")
            container_actions[action] = cid

        action = menu.exec(QCursor.pos())

        if action == none_action:
            # 从父级移除
            for comp_id in component_ids:
                comp = self.diagram.components[comp_id]
                if comp.parent and comp.parent in self.diagram.components:
                    parent = self.diagram.components[comp.parent]
                    if comp_id in parent.children:
                        parent.children.remove(comp_id)
                comp.parent = None
        elif action in container_actions:
            # 设置父级
            new_parent_id = container_actions[action]
            for comp_id in component_ids:
                comp = self.diagram.components[comp_id]

                # 从旧父级移除
                if comp.parent and comp.parent in self.diagram.components:
                    old_parent = self.diagram.components[comp.parent]
                    if comp_id in old_parent.children:
                        old_parent.children.remove(comp_id)

                # 设置新父级
                comp.parent = new_parent_id
                self.diagram.components[new_parent_id].children.append(comp_id)

        self.refresh_scene()
        self.update_hierarchy_tree()
        self.statusBar().showMessage(f"Updated hierarchy for {len(component_ids)} components", 2000)

    def _get_filtered_components_by_level(self):
        """根据层级过滤获取组件"""
        if self.current_filter_level == -1:
            return set(self.diagram.components.keys())

        filtered = set()
        for comp_id, comp in self.diagram.components.items():
            # 计算层级深度
            depth = self._get_component_level(comp)

            if self.current_filter_level == 4:
                # Level 4+ 显示4层及以上
                if depth >= 4:
                    filtered.add(comp_id)
            elif depth == self.current_filter_level:
                filtered.add(comp_id)

        return filtered

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.exit_drawing_mode()
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_S and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.save_current()
        elif event.key() == Qt.Key.Key_A:
            self.navigate_image(-1)
        elif event.key() == Qt.Key.Key_D:
            self.navigate_image(1)
        else:
            super().keyPressEvent(event)

    def navigate_image(self, direction):
        """导航图片"""
        if not self.image_files:
            return

        new_index = (self.current_index + direction) % len(self.image_files)
        self.file_list.setCurrentRow(new_index)
