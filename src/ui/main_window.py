# src/ui/main_window.py
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QListWidget, QGraphicsView, 
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter, 
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog, QGroupBox, QMenu,
    QGraphicsSimpleTextItem, QGraphicsPixmapItem,
    QComboBox, QDialog, QFormLayout, QDialogButtonBox, QLineEdit
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap, QPen, QColor, QCursor, QBrush
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import Diagram
from ..graphics_items import EntityItem, PortItem, ConnectionLineItem, GroupItem
from .style import DARK_THEME
import json

class EditableGraphicsView(QGraphicsView):
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.drawing_mode = None
        self.start_pos = None
        self.temp_rect = None
        self.temp_line = None
        
        # 状态标志：是否正在按住空白处拖动
        self._is_panning = False
        
        # 优化绘制性能
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 设置缩放锚点为鼠标位置，这样缩放时会以鼠标为中心
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event):
        """
        处理滚轮事件进行缩放
        """
        # 如果正在进行特定的绘图操作，可能不希望缩放，这里暂不限制
        
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        # 滚轮向上滚动 (delta > 0) -> 放大
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
            
        # 接受事件，不再传递给默认的滚动条处理
        event.accept()

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # 1. 优先处理特殊的绘图模式 (画框、连线、加点)
        if self.drawing_mode:
            if self.drawing_mode == 'connect': 
                self.main_window.handle_connection_click(self.get_item_at(event.pos(), PortItem))
            elif self.drawing_mode == 'add_port': 
                self.main_window.handle_add_port_click(scene_pos, self.get_item_at(event.pos(), EntityItem))
            elif self.drawing_mode == 'component_draw' and event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = scene_pos
                self.temp_rect = self.scene().addRect(
                    QRectF(self.start_pos, self.start_pos), 
                    QPen(QColor("gold"), 2, Qt.PenStyle.DashLine)
                )
            event.accept()
            return

        # 2. 处理普通模式下的交互
        # 检查鼠标下是否有物体
        item = self.itemAt(event.pos())
        
        # 如果是左键点击，且点击在空白区域（没有item），则进入拖拽画布模式
        if event.button() == Qt.MouseButton.LeftButton and item is None:
            self._is_panning = True
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # 调用父类以让 ScrollHandDrag 生效 (抓住画布)
            super().mousePressEvent(event)
            # 注意：这里不 return，因为 super() 处理了拖拽开始
        else:
            # 如果点击了物体，或者右键，交给父类处理（选择、移动物体、弹出菜单等）
            super().mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        # 处理绘图过程中的鼠标移动
        if self.drawing_mode == 'component_draw' and self.start_pos and self.temp_rect: 
            self.temp_rect.setRect(QRectF(self.start_pos, scene_pos).normalized())
        elif self.drawing_mode == 'connect' and self.main_window.pending_port_1:
            if not self.temp_line:
                start = self.main_window.pending_port_1.scenePos()
                self.temp_line = self.scene().addLine(
                    start.x(), start.y(), start.x(), start.y(), 
                    QPen(QColor("lime"), 2, Qt.PenStyle.DashLine)
                )
                self.temp_line.setZValue(10)
            line = self.temp_line.line()
            line.setP2(scene_pos)
            self.temp_line.setLine(line)
        else: 
            # 普通模式（包括拖拽画布）
            super().mouseMoveEvent(event)
        
    def mouseReleaseEvent(self, event):
        # 1. 处理绘图结束
        if self.drawing_mode == 'component_draw' and self.start_pos and self.temp_rect:
            box = self.temp_rect.rect()
            self.scene().removeItem(self.temp_rect)
            self.temp_rect, self.start_pos = None, None
            if box.width() > 5 and box.height() > 5: 
                self.main_window.create_new_drawn_item(box)
            self.main_window.exit_special_modes()
        
        # 2. 处理拖拽画布结束
        elif self._is_panning:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._is_panning = False
            super().mouseReleaseEvent(event)
            
        # 3. 其他情况
        else: 
            super().mouseReleaseEvent(event)
        
    def contextMenuEvent(self, event): 
        # 如果正在拖拽中，不显示右键菜单
        if not self._is_panning:
            self.main_window.show_context_menu(self.mapToScene(event.pos()), event.globalPos())
    
    def get_item_at(self, pos, item_type):
        item = self.itemAt(pos)
        if isinstance(item, item_type): return item
        # 特殊处理：如果在 PortItem 上但需要 EntityItem，且 Port 是子项
        if item_type == EntityItem and isinstance(item, PortItem) and item.parentItem(): 
            return item.parentItem()
        # 模糊搜索：如果点击精度不够，搜索周围小范围
        rect = QRectF(self.mapToScene(pos) - QPointF(5,5), self.mapToScene(pos) + QPointF(5,5))
        items = [i for i in self.scene().items(rect) if isinstance(i, item_type)]
        return items[0] if items else None

class ConfigManager:
    CONFIG_FILE = "annotation_config.json"
    
    # 你的标准列表
    DEFAULT_TYPES = [
        "block", "PMOS", "NMOS", "Voltage", "Current", 
        "NPN", "PNP", "Diode", "Diso_amp", "Siso_amp", 
        "Cap", "Gnd", "Vdd", "Ind", "Res"
    ]

    @classmethod
    def load_types(cls):
        if Path(cls.CONFIG_FILE).exists():
            try:
                with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    saved_types = data.get("component_types", [])
                    # 合并去重
                    combined = sorted(list(set(cls.DEFAULT_TYPES + saved_types)))
                    return combined
            except:
                pass
        return cls.DEFAULT_TYPES

    @classmethod
    def save_new_type(cls, new_type):
        # 只有当新类型不在默认列表里，且不为空时才保存
        if not new_type or new_type in cls.DEFAULT_TYPES:
            return

        current_types = cls.load_types()
        if new_type not in current_types:
            current_types.append(new_type)
            current_types.sort()
            try:
                with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump({"component_types": current_types}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Failed to save config: {e}")

class ComponentCreationDialog(QDialog):
    """
    整合弹窗：包含显式的“自定义”选项逻辑
    """
    def __init__(self, parent=None, default_types=[]):
        super().__init__(parent)
        self.setWindowTitle("Edit Component Details")
        self.setModal(True)
        self.resize(350, 150)
        
        layout = QFormLayout(self)
        
        # 1. Label 输入框
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. R1, Block_A")
        layout.addRow("Label:", self.label_edit)
        
        # 2. Type 选择框
        self.type_combo = QComboBox()
        self.type_combo.setEditable(False) # 平时不可编辑，只能选
        
        # 添加默认选项
        self.type_combo.addItems(default_types)
        
        # 添加显式的自定义选项
        self.CUSTOM_OPTION = "--- 自定义 (Custom) ---"
        self.type_combo.addItem(self.CUSTOM_OPTION)
        
        # 绑定选择改变事件
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        
        layout.addRow("Type:", self.type_combo)
        
        # 3. 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.label_edit.setFocus()

    def on_type_changed(self, index):
        """当用户选中 '自定义' 时触发"""
        current_text = self.type_combo.itemText(index)
        
        if current_text == self.CUSTOM_OPTION:
            # 弹出输入框询问新类型
            new_type, ok = QInputDialog.getText(self, "Custom Type", "Enter new component type name:")
            
            if ok and new_type.strip():
                clean_type = new_type.strip()
                
                # 检查是否已存在
                existing_index = self.type_combo.findText(clean_type)
                if existing_index != -1:
                    # 已存在，直接选中
                    self.type_combo.setCurrentIndex(existing_index)
                else:
                    # 不存在，插入到“自定义”选项的前面
                    insert_idx = self.type_combo.count() - 1
                    self.type_combo.insertItem(insert_idx, clean_type)
                    # 选中这个新插入的项
                    self.type_combo.setCurrentIndex(insert_idx)
            else:
                # 用户取消或输入为空，重置回第一个选项（防止停留在“自定义”上）
                self.type_combo.setCurrentIndex(0)

    def get_data(self):
        # 返回 Label 和 当前选中的Type
        # 注意：如果用户还停留在 "--- 自定义 ---" 选项上（比如点击了取消），我们要防止把这个字符串存进去
        type_text = self.type_combo.currentText()
        if type_text == self.CUSTOM_OPTION:
            type_text = "block" # 回退默认值
            
        return self.label_edit.text().strip(), type_text
    
    

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Generic Diagram Annotator")
        self.resize(1800, 1000)
        self.diagram = Diagram()
        self.pending_port_1 = None
        self.image_files, self.current_index = [], -1
        self.image_folder, self.raw_json_folder, self.project_folder = None, None, None
        self.scene = QGraphicsScene(self)
        self.entity_items, self.port_items = {}, {}
        self.edit_mode = 'component'
        self._init_ui()
        self.set_edit_mode('port')

    def _init_ui(self):
        self.setStyleSheet(DARK_THEME)
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        self.act_save = QAction("Save", self, triggered=self.save_current_changes, shortcut=QKeySequence.StandardKey.Save)
        self.act_port_mode = QAction("Port Mode (P)", self, checkable=True, triggered=lambda:self.set_edit_mode('port'))
        self.act_comp_mode = QAction("Component Mode (C)", self, checkable=True, triggered=lambda:self.set_edit_mode('component'))
        self.act_draw_comp = QAction("Draw...", self, triggered=lambda:self.enter_mode('component_draw'))
        self.act_add_port = QAction("Add Port", self, triggered=lambda:self.enter_mode('add_port'))
        self.act_connect = QAction("Connect", self, triggered=lambda:self.enter_mode('connect'))
        self.act_delete = QAction("Delete", self, triggered=self.delete_selected, shortcut=QKeySequence.StandardKey.Delete)
        
        toolbar.addAction(self.act_save)
        toolbar.addSeparator()
        toolbar.addAction(self.act_comp_mode)
        toolbar.addAction(self.act_port_mode)
        toolbar.addSeparator()
        toolbar.addAction(self.act_draw_comp)
        toolbar.addAction(self.act_add_port)
        toolbar.addAction(self.act_connect)
        toolbar.addSeparator()
        toolbar.addAction(self.act_delete)
        
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(main_splitter)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        folder_group = QGroupBox("Project Folders")
        folder_layout = QVBoxLayout(folder_group)
        self.btn_img_folder = QPushButton("1. Image Folder")
        self.btn_img_folder.clicked.connect(lambda:self.select_folder('image'))
        self.btn_raw_json_folder = QPushButton("2. Raw JSON Folder (Input)")
        self.btn_raw_json_folder.clicked.connect(lambda:self.select_folder('raw_json'))
        self.btn_project_folder = QPushButton("3. Project Folder (Output)")
        self.btn_project_folder.clicked.connect(lambda:self.select_folder('project'))
        folder_layout.addWidget(self.btn_img_folder)
        folder_layout.addWidget(self.btn_raw_json_folder)
        folder_layout.addWidget(self.btn_project_folder)
        left_layout.addWidget(folder_group)
        
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        left_layout.addWidget(self.file_list)
        
        self.view = EditableGraphicsView(self.scene, self)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        prop_group = QGroupBox("Properties")
        prop_layout = QVBoxLayout(prop_group)
        self.info_label = QLabel("Select an item...")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        prop_layout.addWidget(self.info_label)
        
        ops_group = QGroupBox("Operations")
        ops_layout = QVBoxLayout(ops_group)
        self.btn_rename = QPushButton("Rename/Edit Label")
        self.btn_rename.clicked.connect(self.rename_selected)
        ops_layout.addWidget(self.btn_rename)
        right_layout.addWidget(prop_group)
        right_layout.addWidget(ops_group)
        right_layout.addStretch(1)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(self.view)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([250, 1200, 350])
        
        self.setStatusBar(QStatusBar())
        self.scene.selectionChanged.connect(self.on_selection_changed)

    def select_folder(self, folder_type):
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not path: return
        p = Path(path)
        if folder_type == 'image': 
            self.image_folder = p
            self.btn_img_folder.setText(f"Images: ...{p.name}")
        elif folder_type == 'raw_json': 
            self.raw_json_folder = p
            self.btn_raw_json_folder.setText(f"Raw JSONs: ...{p.name}")
        elif folder_type == 'project': 
            self.project_folder = p
            self.btn_project_folder.setText(f"Projects: ...{p.name}")
            
        if self.image_folder and (self.raw_json_folder or self.project_folder): 
            self.scan_and_load_files()

    def scan_and_load_files(self):
        if not self.image_folder: return
        self.image_files = sorted([f for f in self.image_folder.iterdir() if f.suffix.lower() in ('.png','.jpg','.jpeg')])
        self.file_list.clear()
        [self.file_list.addItem(f.name) for f in self.image_files]
        if self.image_files: self.file_list.setCurrentRow(0)

    def on_file_selected(self, current, _):
        if not current: return
        if self.current_index != -1: self.save_current_changes()
        new_index = self.file_list.row(current)
        if new_index == self.current_index: return
        self.current_index = new_index
        self.load_diagram()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.exit_special_modes()
        elif event.key() == Qt.Key.Key_D: self.navigate_image(1)
        elif event.key() == Qt.Key.Key_A: self.navigate_image(-1)
        elif event.key() == Qt.Key.Key_P: self.set_edit_mode('port')
        elif event.key() == Qt.Key.Key_C: self.set_edit_mode('component')
        super().keyPressEvent(event)
    
    def navigate_image(self, direction):
        if not self.image_files: return
        new_index = (self.current_index + direction) % len(self.image_files)
        self.file_list.setCurrentRow(new_index)
        
    def zoom_to_fit(self):
        """强制将图片缩放至适应窗口大小"""
        if not self.scene.items():
            return
            
        # 获取场景内容的实际边界
        scene_rect = self.scene.itemsBoundingRect()
        # 设置场景的边界，确保没有多余空白
        self.scene.setSceneRect(scene_rect)
        
        # 核心：FitInView
        # KeepAspectRatio: 保持宽高比，不会拉伸变形
        self.view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    # === 更新 load_diagram ===
    def load_diagram(self):
        if not (0 <= self.current_index < len(self.image_files)): return
        
        # 1. 重置旧的缩放
        self.view.resetTransform()
        
        img_path = self.image_files[self.current_index]
        self.diagram = Diagram()
        project_path = self.project_folder / (img_path.stem + ".annot.json") if self.project_folder else None
        loaded = False
        
        if project_path and project_path.exists():
            if self.diagram.load_from_json(img_path, project_path): 
                self.statusBar().showMessage(f"Loaded project: {project_path.name}", 3000)
                loaded = True
                
        if not loaded and self.raw_json_folder:
            raw_path = self.raw_json_folder / (img_path.stem + ".json")
            if raw_path.exists():
                if self.diagram.load_from_raw_json(img_path, raw_path):
                    self.statusBar().showMessage(f"Imported raw JSON: {raw_path.name}", 3000)
                    self.auto_layout_component_ports()
                    self.auto_layout_terminals()
                    loaded = True
                    
        if loaded: 
            self.refresh_scene_from_model()
        else: 
            self.scene.clear()
            pixmap = QPixmap(str(img_path))
            self.scene.addItem(QGraphicsPixmapItem(pixmap))
            self.scene.setSceneRect(QRectF(pixmap.rect()))
            self.diagram.image_path = img_path

        # 2. 关键：加载完成后自动适配窗口
        self.zoom_to_fit()

    def save_current_changes(self):
        if not (self.diagram and self.diagram.image_path): return
        if not self.project_folder: return
        output_path = self.project_folder / (Path(self.diagram.image_path).stem + ".annot.json")
        if self.diagram.save_to_json(output_path): 
            self.statusBar().showMessage(f"Saved: {output_path.name}", 2000)
        else: 
            self.statusBar().showMessage(f"Failed to save {output_path.name}", 2000)

    def refresh_scene_from_model(self):
        self.scene.clear()
        self.entity_items.clear()
        self.port_items.clear()
        
        if self.diagram.image_path:
            pixmap = QPixmap(str(self.diagram.image_path))
            self.scene.addItem(QGraphicsPixmapItem(pixmap))
            self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        for group_id, group in self.diagram.groups.items():
            group_item = GroupItem(group)
            self.scene.addItem(group_item)
            
        for entity_id, entity in self.diagram.entities.items():
            if entity.box:
                entity_item = EntityItem(entity)
                self.entity_items[entity_id] = entity_item
                self.scene.addItem(entity_item)
                entity_item.setPos(QPointF(*entity.position))
                for port_id, port in entity.ports.items():
                    port_item = PortItem(port, entity, parent_item=entity_item)
                    self.port_items[(entity_id, port_id)] = port_item
                    port_item.setPos(QPointF(*port.position))
            else:
                port = next(iter(entity.ports.values()), None)
                if port:
                    port_item = PortItem(port, entity, parent_item=None)
                    self.port_items[(entity_id, port.id)] = port_item
                    self.scene.addItem(port_item)
                    port_item.setPos(QPointF(*entity.position))
                    
        for conn in self.diagram.connections:
            ep1, ep2 = conn['endpoints']
            key1, key2 = ((ep1['entity_id'], ep1['port_id']), (ep2['entity_id'], ep2['port_id']))
            p_item1, p_item2 = self.port_items.get(key1), self.port_items.get(key2)
            if p_item1 and p_item2:
                line_item = ConnectionLineItem(conn, p_item1, p_item2)
                self.scene.addItem(line_item)
                line_item.update_path()
                if conn.get("label"):
                    label_item = QGraphicsSimpleTextItem(conn["label"])
                    line_item.label_item = label_item
                    self.scene.addItem(label_item)
                    label_item.setBrush(QBrush(QColor("white")))
                    label_item.setZValue(line_item.zValue() + 1)
                    line_item.update_path()
                    
        self.set_edit_mode(self.edit_mode, force_update=True)

    def set_edit_mode(self, mode, force_update=False):
        if self.edit_mode == mode and not force_update: return
        self.exit_special_modes()
        self.edit_mode = mode
        self.act_comp_mode.setChecked(mode == 'component')
        self.act_port_mode.setChecked(mode == 'port')
        
        is_port_mode = mode == 'port'
        for item in self.scene.items():
            if isinstance(item, EntityItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_port_mode)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not is_port_mode)
            elif isinstance(item, PortItem):
                is_terminal = item.parentItem() is None
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_port_mode)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    
    def enter_mode(self, mode_name):
        self.set_edit_mode('port' if mode_name in ['connect', 'add_port'] else 'component')
        self.view.drawing_mode = mode_name
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(f"Mode: {mode_name.replace('_', ' ').title()}...")

    def exit_special_modes(self):
        self.view.drawing_mode = None
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        if self.view.temp_line: 
            self.scene.removeItem(self.view.temp_line)
            self.view.temp_line = None
        if self.view.temp_rect: 
            self.scene.removeItem(self.view.temp_rect)
            self.view.temp_rect = None
        if self.pending_port_1:
            color_map = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C"), 'inout': QColor("#F57C00")}
            color = color_map.get(self.pending_port_1.port_model.direction, "#AAAAAA")
            is_terminal = self.pending_port_1.parentItem() is None
            self.pending_port_1.setBrush(QBrush(color.lighter(120) if is_terminal else color))
            self.pending_port_1 = None
        self.statusBar().clearMessage()

    def delete_selected(self):
        for item in self.scene.selectedItems():
            if isinstance(item, EntityItem): 
                self.diagram.delete_entity(item.entity_model.id)
            elif isinstance(item, PortItem):
                if item.parentItem() is None: 
                    self.diagram.delete_entity(item.entity_model.id)
                else: 
                    self.diagram.delete_port(item.entity_model.id, item.port_model.id)
            elif isinstance(item, ConnectionLineItem): 
                self.diagram.delete_connection(item.connection_model['id'])
            elif isinstance(item, GroupItem): 
                self.diagram.delete_group(item.group_model.id)
        self.refresh_scene_from_model()

    def handle_connection_click(self, port_item):
        if not port_item: 
            self.exit_special_modes()
            return
        if not self.pending_port_1: 
            self.pending_port_1 = port_item
            port_item.setBrush(QBrush(QColor("lime")))
        else:
            if self.pending_port_1 != port_item:
                key1 = (self.pending_port_1.entity_model.id, self.pending_port_1.port_model.id)
                key2 = (port_item.entity_model.id, port_item.port_model.id)
                self.diagram.create_connection(key1, key2)
            self.exit_special_modes()
            self.refresh_scene_from_model()
            
    # 替换原有的 handle_add_port_click
    def handle_add_port_click(self, scene_pos, entity_item):
        """
        处理添加端口/节点的点击事件
        - 如果点击在组件上: 添加该组件的一个端口
        - 如果点击在空白处: 创建一个新的 Terminal (外部端口)
        """
        if entity_item:
            # === Case A: 给现有组件添加端口 ===
            label, ok = QInputDialog.getText(self, "New Port", "Enter port label:")
            if ok and label:
                direction, ok2 = QInputDialog.getItem(self, "Port Direction", "Select direction:", ["input", "output", "inout"], 0, False)
                if ok2:
                    rel_pos = entity_item.mapFromScene(scene_pos)
                    self.diagram.add_port(entity_item.entity_model.id, label, direction, [rel_pos.x(), rel_pos.y()])
        else:
            # === Case B: 在空白处创建 Terminal (修复点) ===
            label, ok = QInputDialog.getText(self, "New Terminal", "Enter terminal label (e.g., Vin, Gnd):")
            if ok and label:
                # 1. 创建 Terminal Entity (box=None)
                # 使用 scene_pos 作为绝对坐标
                entity = self.diagram.add_entity(label, "Terminal", None, [scene_pos.x(), scene_pos.y()])
                
                # 2. 自动给 Terminal 添加一个默认端口 (通常位于 0,0)
                self.diagram.add_port(entity.id, "io", "inout", [0, 0])
                
        self.exit_special_modes()
        self.refresh_scene_from_model()

    # 替换原有的 create_new_drawn_item
    def create_new_drawn_item(self, box):
        """
        处理画框结束后的逻辑
        - 弹出自定义对话框选择类型
        - 保存新的自定义类型
        """
        # 1. 先询问是 Component 还是 Group (这一步保留，因为是两种完全不同的实体)
        # 使用 getItem 比较简洁，也不会在左上角乱跳
        choice, ok = QInputDialog.getItem(self, "Select Entity Type", "Create:", ["Component", "Group"], 0, False)
        if not ok: return

        if choice == "Group":
            label, ok = QInputDialog.getText(self, "New Group", "Enter group label:")
            if ok and label:
                self.diagram.add_group(label, [box.x(), box.y(), box.width(), box.height()])
                self.refresh_scene_from_model()
                
        else: # Choice is Component
            # 2. 弹出整合对话框
            # 加载历史类型列表
            current_types = ConfigManager.load_types()
            dialog = ComponentCreationDialog(self, current_types)
            
            # exec() 会阻塞直到用户关闭窗口
            if dialog.exec():
                label, type_name = dialog.get_data()
                
                if label:
                    # 如果用户没填类型，默认给个 block
                    if not type_name: 
                        type_name = "block"
                    
                    # 3. 如果是新输入的类型，保存到配置文件
                    ConfigManager.save_new_type(type_name)
                    
                    # 4. 创建实体
                    self.diagram.add_entity(label, type_name, [box.width(), box.height()], [box.x(), box.y()])
                    self.refresh_scene_from_model()
            
    def auto_layout_component_ports(self):
        for entity in self.diagram.entities.values():
            if not entity.box: continue
            inputs = sorted([p for p in entity.ports.values() if p.direction == 'input'], key=lambda p: p.label)
            outputs = sorted([p for p in entity.ports.values() if p.direction == 'output'], key=lambda p: p.label)
            w, h = entity.box
            for i, p in enumerate(inputs):
                if p.position == [0, 0]: p.position = [0, (i + 1) * h / (len(inputs) + 1)]
            for i, p in enumerate(outputs):
                if p.position == [0, 0]: p.position = [w, (i + 1) * h / (len(outputs) + 1)]
    
    def auto_layout_terminals(self):
        rect = self.scene.sceneRect()
        terminals = [e for e in self.diagram.entities.values() if e.box is None]
        inputs = [e for e in terminals if any(p.direction == 'output' for p in e.ports.values())]
        outputs = [e for e in terminals if any(p.direction == 'input' for p in e.ports.values())]
        for i, e in enumerate(inputs): 
            e.position = [rect.left() - 30, rect.top() + (i + 1) * rect.height() / (len(inputs) + 1)]
        for i, e in enumerate(outputs): 
            e.position = [rect.right() + 30, rect.top() + (i + 1) * rect.height() / (len(outputs) + 1)]

    def on_selection_changed(self):
        items = self.scene.selectedItems()
        self.btn_rename.setEnabled(len(items) == 1)
        if len(items) != 1: 
            self.info_label.setText("Select a single item to see details.")
            return
        item = items[0]
        text = ""
        if isinstance(item, EntityItem): 
            m = item.entity_model
            text = f"<b>Component</b><br>Label: {m.label}<br>Type: {m.type}<br>ID: {m.id}"
        elif isinstance(item, PortItem): 
            m = item.port_model
            em = item.entity_model
            text = f"<b>{'Terminal' if em.box is None else 'Port'}</b><br>Label: {em.label if em.box is None else m.label}<br>ID: {em.id if em.box is None else m.id}"
        elif isinstance(item, ConnectionLineItem): 
            m = item.connection_model
            text = f"<b>Connection</b><br>ID: {m['id']}<br>Label: {m.get('label', '')}"
        elif isinstance(item, GroupItem): 
            m = item.group_model
            text = f"<b>Group</b><br>Label: {m.label}<br>ID: {m.id}"
        self.info_label.setText(text)

    def show_context_menu(self, scene_pos, global_pos):
        menu = QMenu(self)
        item = self.view.itemAt(self.view.mapFromScene(scene_pos))
        if isinstance(item, (PortItem, ConnectionLineItem, EntityItem, GroupItem)):
            item.setSelected(True)
            menu.addAction("Rename / Edit Label...", self.rename_selected)
        else:
            action = menu.addAction("Add New Terminal")
            if action == menu.exec(global_pos):
                label, ok = QInputDialog.getText(self, "New Terminal", "Enter terminal label:")
                if ok and label:
                    entity = self.diagram.add_entity(label, "Terminal", None, [scene_pos.x(), scene_pos.y()])
                    self.diagram.add_port(entity.id, 'io', 'inout', [0, 0])
                    self.refresh_scene_from_model()
    
    def rename_selected(self):
        items = self.scene.selectedItems()
        if not items: return
        item = items[0]
        if isinstance(item, EntityItem):
            m = item.entity_model
            new, ok = QInputDialog.getText(self, "Rename Entity", "New Label:", text=m.label)
            if ok: 
                self.diagram.rename_entity(m.id, new)
                self.refresh_scene_from_model()
        elif isinstance(item, PortItem):
            m, em = item.port_model, item.entity_model
            if em.box is None:
                new, ok = QInputDialog.getText(self, "Rename Terminal", "New Label:", text=em.label)
                if ok: 
                    self.diagram.rename_entity(em.id, new)
                    self.refresh_scene_from_model()
            else:
                new, ok = QInputDialog.getText(self, "Rename Port", "New Label:", text=m.label)
                if ok: 
                    self.diagram.rename_port(em.id, m.id, new)
                    self.refresh_scene_from_model()
        elif isinstance(item, ConnectionLineItem):
            m = item.connection_model
            new, ok = QInputDialog.getText(self, "Edit Connection Label", "Label:", text=m.get('label', ''))
            if ok: 
                self.diagram.update_connection_label(m['id'], new)
                self.refresh_scene_from_model()
        elif isinstance(item, GroupItem):
            m = item.group_model
            new, ok = QInputDialog.getText(self, "Rename Group", "New Label:", text=m.label)
            if ok: 
                self.diagram.rename_group(m.id, new)
                self.refresh_scene_from_model()