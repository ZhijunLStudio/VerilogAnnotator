import math
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QGraphicsView, 
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter, 
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog, QGroupBox,
    QMenu
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap, QPen, QColor, QCursor, QBrush
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import CircuitDiagram
from .style import DARK_THEME
from ..graphics_items import ComponentItem, PortItem, ConnectionLineItem, ConnectionLabelItem

class EditableGraphicsView(QGraphicsView):
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.drawing_mode = None
        self.start_pos = None
        self.temp_rect = None
        self.temp_line = None

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if self.drawing_mode:
            target_port = None
            if self.drawing_mode in ['connect', 'merge_ports']:
                item_under_cursor = self.itemAt(event.pos())
                if isinstance(item_under_cursor, PortItem):
                    target_port = item_under_cursor
                else:
                    search_rect = QRectF(scene_pos - QPointF(10, 10), scene_pos + QPointF(10, 10))
                    nearby_items = self.scene().items(search_rect)
                    port_items = [item for item in nearby_items if isinstance(item, PortItem)]
                    if port_items:
                        min_dist = float('inf')
                        for port in port_items:
                            dist = math.hypot(port.scenePos().x() - scene_pos.x(), port.scenePos().y() - scene_pos.y())
                            if dist < min_dist:
                                min_dist = dist; target_port = port
            if self.drawing_mode in ['add_input', 'add_output']:
                self.main_window.handle_add_port_click(scene_pos)
            elif self.drawing_mode == 'connect':
                self.main_window.handle_connection_click(target_port)
            elif self.drawing_mode == 'merge_ports':
                self.main_window.handle_merge_click(target_port)
            elif self.drawing_mode == 'component_draw' and event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = scene_pos
                rect = QRectF(self.start_pos, self.start_pos)
                self.temp_rect = self.scene().addRect(rect, QPen(QColor("gold"), 2, Qt.PenStyle.DashLine))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_mode == 'component_draw' and self.start_pos:
            current_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, current_pos).normalized()
            self.temp_rect.setRect(rect)
            event.accept()
        elif self.drawing_mode == 'connect' and self.main_window.pending_port_1:
            if not self.temp_line:
                start_point = self.main_window.pending_port_1.scenePos()
                self.temp_line = self.scene().addLine(start_point.x(), start_point.y(), start_point.x(), start_point.y(), QPen(QColor("lime"), 2, Qt.PenStyle.DashLine))
                self.temp_line.setZValue(10)
            end_point = self.mapToScene(event.pos())
            line = self.temp_line.line(); line.setP2(end_point); self.temp_line.setLine(line)
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_mode == 'component_draw' and self.start_pos:
            end_pos = self.mapToScene(event.pos())
            if self.temp_rect:
                self.scene().removeItem(self.temp_rect); self.temp_rect = None
            box = QRectF(self.start_pos, end_pos).normalized()
            if box.width() > 5 and box.height() > 5:
                self.main_window.create_new_component_at(box)
            self.main_window.exit_special_modes()
            event.accept()
        else: super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.main_window.show_context_menu(self.mapToScene(event.pos()), event.globalPos())
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Verilog Annotator Pro")
        self.resize(1800, 1000)
        self.diagram = CircuitDiagram()
        self.edit_mode = 'port' 
        self.pending_port_1 = None
        self.pending_port_for_merge = None
        self.image_files, self.current_index = [], -1
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        self.image_folder, self.verilog_folder, self.metadata_folder = None, None, None
        self.scene = QGraphicsScene(); self.scene.setParent(self)
        self.component_items, self.port_items = {}, {}
        self._init_ui()
        self.set_edit_mode(self.edit_mode)
        self.show()

    def _init_ui(self):
        self.setStyleSheet(DARK_THEME)
        toolbar = QToolBar("Main Toolbar"); self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.act_save = QAction("Save (Ctrl+S)", self, triggered=self.save_current_changes, shortcut=QKeySequence.StandardKey.Save)
        self.act_port = QAction("Port Mode (P)", self, checkable=True, triggered=lambda: self.set_edit_mode('port'))
        self.act_comp = QAction("Component Mode (C)", self, checkable=True, triggered=lambda: self.set_edit_mode('component'))
        self.act_new_comp = QAction("Draw Component (W)", self, triggered=self.enter_component_drawing_mode, shortcut="W")
        self.act_connect = QAction("Connect Ports (L)", self, triggered=self.enter_connection_mode, shortcut="L")
        self.act_del = QAction("Delete (Del)", self, triggered=self.delete_selected_item, shortcut=QKeySequence.StandardKey.Delete)
        toolbar.addAction(self.act_save); toolbar.addSeparator()
        toolbar.addAction(self.act_port); toolbar.addAction(self.act_comp); toolbar.addSeparator()
        toolbar.addAction(self.act_new_comp); toolbar.addAction(self.act_connect); toolbar.addSeparator()
        toolbar.addAction(self.act_del)
        
        main_splitter = QSplitter(Qt.Orientation.Horizontal); self.setCentralWidget(main_splitter)
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        folder_group = QGroupBox("Project Folders"); folder_layout = QVBoxLayout(folder_group)
        self.image_path_btn = QPushButton("1. Select Images Folder"); self.image_path_btn.clicked.connect(lambda: self.select_folder('image'))
        self.verilog_path_btn = QPushButton("2. Select Verilog Folder"); self.verilog_path_btn.clicked.connect(lambda: self.select_folder('verilog'))
        self.metadata_path_btn = QPushButton("3. Select Metadata Folder"); self.metadata_path_btn.clicked.connect(lambda: self.select_folder('metadata'))
        folder_layout.addWidget(self.image_path_btn); folder_layout.addWidget(self.verilog_path_btn); folder_layout.addWidget(self.metadata_path_btn)
        left_layout.addWidget(folder_group)
        self.file_list = QListWidget(); self.file_list.currentItemChanged.connect(self.on_file_selected)
        file_group = QGroupBox("Image Files"); file_layout = QVBoxLayout(file_group); file_layout.addWidget(self.file_list)
        left_layout.addWidget(file_group)

        self.view = EditableGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing); self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse); self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        prop_group = QGroupBox("Properties")
        prop_layout = QVBoxLayout(prop_group)
        self.info_label = QLabel("Select an item to see details."); self.info_label.setObjectName("infoLabel"); self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop); self.info_label.setWordWrap(True)
        prop_layout.addWidget(self.info_label)
        
        ops_group = QGroupBox("Operations"); ops_layout = QVBoxLayout(ops_group)
        self.btn_add_port_in = QPushButton("Add Input Port"); self.btn_add_port_in.clicked.connect(lambda: self.enter_add_port_mode('input'))
        self.btn_add_port_out = QPushButton("Add Output Port"); self.btn_add_port_out.clicked.connect(lambda: self.enter_add_port_mode('output'))
        self.btn_merge_ports = QPushButton("Merge Ports"); self.btn_merge_ports.clicked.connect(self.enter_merge_mode)
        self.btn_rename_port = QPushButton("Rename Port Label"); self.btn_rename_port.clicked.connect(self.rename_selected_port)
        self.btn_split_port = QPushButton("Split Selected Port"); self.btn_split_port.clicked.connect(self.split_selected_port)
        self.btn_add_conn_label = QPushButton("Add/Edit Connection Label"); self.btn_add_conn_label.clicked.connect(self.add_edit_connection_label)
        
        ops_layout.addWidget(self.btn_add_port_in); ops_layout.addWidget(self.btn_add_port_out)
        ops_layout.addWidget(self.btn_merge_ports); ops_layout.addWidget(self.btn_rename_port)
        ops_layout.addWidget(self.btn_split_port); ops_layout.addWidget(self.btn_add_conn_label)

        right_layout.addWidget(prop_group)
        right_layout.addWidget(ops_group)
        right_layout.addStretch(1)

        main_splitter.addWidget(left_panel); main_splitter.addWidget(self.view); main_splitter.addWidget(right_panel)
        main_splitter.setSizes([250, 1200, 350])
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.scene.selectionChanged.connect(self.on_selection_changed)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.exit_special_modes()
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_D: self.navigate_image(1)
            elif event.key() == Qt.Key.Key_A: self.navigate_image(-1)
            elif event.key() == Qt.Key.Key_C: self.set_edit_mode('component')
            elif event.key() == Qt.Key.Key_P: self.set_edit_mode('port')
        super().keyPressEvent(event)
        
    def wheelEvent(self, event):
        if self.view.underMouse() and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.view.scale(1.15 if event.angleDelta().y() > 0 else 1 / 1.15, 1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
        else: super().wheelEvent(event)
        
    def select_folder(self, folder_type):
        path = QFileDialog.getExistingDirectory(self, f"Select {folder_type.capitalize()} Folder")
        if not path: return
        p = Path(path)
        if folder_type == 'image': self.image_folder = p; self.image_path_btn.setText(f"Images: ...{p.name}")
        elif folder_type == 'verilog': self.verilog_folder = p; self.verilog_path_btn.setText(f"Verilog: ...{p.name}")
        elif folder_type == 'metadata': self.metadata_folder = p; self.metadata_path_btn.setText(f"Metadata: ...{p.name}")
        if self.image_folder and self.verilog_folder and self.metadata_folder: self.scan_and_load_files()
        
    def scan_and_load_files(self):
        self.image_files = sorted([f for ext in self.supported_formats for f in self.image_folder.glob(f"*{ext}")])
        self.file_list.clear()
        for f in self.image_files: self.file_list.addItem(f.name)
        if self.image_files: self.file_list.setCurrentRow(0)
        
    def on_file_selected(self, current, previous):
        if previous is not None and self.current_index != -1:
            self.save_current_changes()
        
        if not current:
            self.current_index = -1
            return

        new_index = self.file_list.row(current)
        if new_index == self.current_index:
            return
            
        self.current_index = new_index
        self.load_diagram()
        
    def navigate_image(self, direction):
        if not self.image_files: return
        new_index = (self.current_index + direction) % len(self.image_files)
        self.file_list.setCurrentRow(new_index)
        
    def save_current_changes(self):
        if self.diagram and self.diagram.image_path:
            if self.diagram.save_files(): self.status_bar.showMessage(f"Saved: {self.diagram.image_path.name}", 3000)
            
    def load_diagram(self):
        if not (0 <= self.current_index < len(self.image_files)): return
        img_path = self.image_files[self.current_index]
        v_path = self.verilog_folder / (img_path.stem + ".v")
        m_path = self.metadata_folder / (img_path.stem + ".meta.json")
        try:
            self.diagram = CircuitDiagram(); self.diagram.load_files(img_path, v_path, m_path)
            self.refresh_scene_from_model(); self.status_bar.showMessage(f"Loaded: {img_path.name}")
        except Exception as e:
            self.status_bar.showMessage(f"Error loading {img_path.name}: {e}")
            import traceback; traceback.print_exc()

    def delete_selected_item(self):
        items_to_delete = self.scene.selectedItems()
        for item in items_to_delete:
            if isinstance(item, ComponentItem): self.diagram.delete_component(item.component_model.instance_name)
            elif isinstance(item, PortItem):
                pm = item.port_model; self.diagram.delete_port(pm.component.instance_name, pm.name)
        self.refresh_scene_from_model()
    
    def refresh_scene_from_model(self):
        self.scene.clear(); self.component_items.clear(); self.port_items.clear()
        pixmap = QPixmap(str(self.diagram.image_path))
        
        image_rect = QRectF(pixmap.rect()) if not pixmap.isNull() else QRectF(0, 0, 1000, 1000)
        layout_rect = image_rect.adjusted(-50, -50, 50, 50)

        if not pixmap.isNull(): 
            self.scene.addPixmap(pixmap)
        
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = ComponentItem(comp_model)
            self.scene.addItem(comp_item)
            self.component_items[inst_name] = comp_item
            if comp_model.box:
                comp_item.setPos(QPointF(*comp_model.box[:2]))
            else:
                comp_item.setVisible(False)
        
        for inst_name, comp_model in self.diagram.components.items():
            if comp_model.box and comp_model.module_type not in ("InputPort", "OutputPort"):
                unpositioned_ports = [p for p in comp_model.ports.values() if not p.was_manually_positioned]
                if unpositioned_ports:
                    inputs = sorted([p for p in unpositioned_ports if p.direction == 'input'], key=lambda p: p.label)
                    outputs = sorted([p for p in unpositioned_ports if p.direction == 'output'], key=lambda p: p.label)
                    box_rect = QRectF(comp_model.box[0], comp_model.box[1], comp_model.box[2] - comp_model.box[0], comp_model.box[3] - comp_model.box[1])
                    for i, p_model in enumerate(inputs):
                        y = box_rect.top() + (i + 1) * box_rect.height() / (len(inputs) + 1)
                        p_model.position = [int(box_rect.left()), int(y)]
                    for i, p_model in enumerate(outputs):
                        y = box_rect.top() + (i + 1) * box_rect.height() / (len(outputs) + 1)
                        p_model.position = [int(box_rect.right()), int(y)]
        
        terminals = [p for c in self.diagram.components.values() for p in c.ports.values() if c.module_type in ("InputPort", "OutputPort")]
        unpositioned_terminals = [p for p in terminals if not p.was_manually_positioned]
        if unpositioned_terminals:
            top_inputs = sorted([p for p in unpositioned_terminals if p.direction == 'output'], key=lambda p: p.label)
            top_outputs = sorted([p for p in unpositioned_terminals if p.direction == 'input'], key=lambda p: p.label)
            for i, p_model in enumerate(top_inputs):
                y = layout_rect.top() + (i + 1) * layout_rect.height() / (len(top_inputs) + 1)
                p_model.position = [int(layout_rect.left() + 20), int(y)]
            for i, p_model in enumerate(top_outputs):
                y = layout_rect.top() + (i + 1) * layout_rect.height() / (len(top_outputs) + 1)
                p_model.position = [int(layout_rect.right() - 20), int(y)]

        for inst_name, comp_model in self.diagram.components.items():
            comp_item = self.component_items[inst_name]
            for p_name, p_model in comp_model.ports.items():
                is_terminal = comp_model.module_type in ("InputPort", "OutputPort")
                parent_item = None if is_terminal else comp_item
                port_item = PortItem(p_model, parent_item=parent_item)
                if not parent_item: self.scene.addItem(port_item)
                self.port_items[(inst_name, p_name)] = port_item
                if p_model.position:
                    if parent_item:
                        port_item.setPos(parent_item.mapFromScene(QPointF(*p_model.position)))
                    else:
                        port_item.setPos(QPointF(*p_model.position))
        
        all_lines = []
        for net in self.diagram.nets.values():
            ports_in_net = [self.port_items.get((p.component.instance_name, p.name)) for p in net.connections]
            ports_in_net = [p for p in ports_in_net if p is not None]

            if len(ports_in_net) < 2:
                continue

            num_ports = len(ports_in_net)
            in_tree = [False] * num_ports
            distance = [float('inf')] * num_ports
            parent_edge = [-1] * num_ports
            distance[0] = 0
            
            for _ in range(num_ports):
                min_dist, u = float('inf'), -1
                for i in range(num_ports):
                    if not in_tree[i] and distance[i] < min_dist:
                        min_dist, u = distance[i], i
                if u == -1: break
                in_tree[u] = True
                
                port_u, pos_u = ports_in_net[u], ports_in_net[u].scenePos()
                for v in range(num_ports):
                    if not in_tree[v]:
                        port_v, pos_v = ports_in_net[v], ports_in_net[v].scenePos()
                        dist_uv = math.hypot(pos_u.x() - pos_v.x(), pos_u.y() - pos_v.y())
                        if dist_uv < distance[v]:
                            distance[v], parent_edge[v] = dist_uv, u
                            
            for i in range(1, num_ports):
                parent_idx = parent_edge[i]
                if parent_idx != -1:
                    line = ConnectionLineItem(ports_in_net[parent_idx], ports_in_net[i])
                    self.scene.addItem(line)
                    line.update_path()
                    all_lines.append(line)

        for line in all_lines:
            p1_model, p2_model = line.source_port.port_model, line.dest_port.port_model
            key1, key2 = (p1_model.component.instance_name, p1_model.name), (p2_model.component.instance_name, p2_model.name)
            key_tuple = tuple(sorted((f"{key1[0]}.{key1[1]}", f"{key2[0]}.{key2[1]}")))
            label_key = "--".join(key_tuple)
            if label_key in self.diagram.connection_labels:
                text = self.diagram.connection_labels[label_key].get("text", "")
                label_item = ConnectionLabelItem(text, line)
                line.label_item = label_item
                self.scene.addItem(label_item)
                label_item.update_position()

        self.scene.setSceneRect(layout_rect)
        self.set_edit_mode(self.edit_mode, force_update=True)
        self.on_selection_changed()
    
    def on_selection_changed(self):
        selected_items = self.scene.selectedItems()
        selected_ports = [item for item in selected_items if isinstance(item, PortItem)]
        selected_comps = [item for item in selected_items if isinstance(item, ComponentItem)]
        selected_lines = [item for item in selected_items if isinstance(item, ConnectionLineItem)]
        self.btn_rename_port.setEnabled(len(selected_ports) == 1)
        self.btn_split_port.setEnabled(len(selected_ports) == 1 and selected_ports[0].port_model.component.module_type not in ("Terminal", "InputPort", "OutputPort"))
        self.btn_merge_ports.setEnabled(True)
        self.btn_add_conn_label.setEnabled(len(selected_lines) == 1)
        model_to_show = None
        if selected_ports and selected_ports[0].port_model.component: model_to_show = selected_ports[0].port_model.component
        elif selected_comps: model_to_show = selected_comps[0].component_model
        self.update_info_panel(model_to_show)

    def set_edit_mode(self, mode, force_update=False):
        if self.edit_mode == mode and not force_update: return
        self.exit_special_modes(); self.edit_mode = mode
        is_comp_mode = mode == 'component'
        self.act_comp.setChecked(is_comp_mode); self.act_port.setChecked(not is_comp_mode)
        self.status_bar.showMessage(f"Mode: {'Component' if is_comp_mode else 'Port'}")
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        for item in self.scene.items():
            if isinstance(item, (ComponentItem, PortItem)): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            if isinstance(item, ComponentItem): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_comp_mode)
            elif isinstance(item, PortItem): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_comp_mode)

    def exit_special_modes(self):
        if self.pending_port_1:
            p_model = self.pending_port_1.port_model
            original_color = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}.get(p_model.direction, QColor("#F57C00"))
            self.pending_port_1.setBrush(QBrush(original_color)); self.pending_port_1 = None
        if self.pending_port_for_merge:
            p_model = self.pending_port_for_merge.port_model
            original_color = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}.get(p_model.direction, QColor("#F57C00"))
            self.pending_port_for_merge.setBrush(QBrush(original_color)); self.pending_port_for_merge = None
        if self.view.temp_line:
            self.scene.removeItem(self.view.temp_line); self.view.temp_line = None
        self.view.drawing_mode = None; self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.status_bar.showMessage(f"Mode: {'Component' if self.edit_mode == 'component' else 'Port'}")

    def enter_add_port_mode(self, direction):
        self.set_edit_mode('port'); self.view.drawing_mode = f'add_{direction}'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage(f"Add {direction.capitalize()} Port Mode: Click on the diagram.")
    def enter_connection_mode(self):
        self.set_edit_mode('port'); self.view.drawing_mode = 'connect'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Connect Mode: Click the first port...")
    def enter_component_drawing_mode(self):
        self.set_edit_mode('component'); self.view.drawing_mode = 'component_draw'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Drawing Mode: Click and drag to draw a new component.")
    def enter_merge_mode(self):
        self.set_edit_mode('port'); self.view.drawing_mode = 'merge_ports'; self.view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.status_bar.showMessage("Merge Mode: Click the first port to merge...")

    def handle_add_port_click(self, scene_pos):
        direction = 'input' if self.view.drawing_mode == 'add_input' else 'output'
        label, ok = QInputDialog.getText(self, "New Port", "Enter port label (e.g., 'CLK', 'ADDR[0]'):")
        if not (ok and label): self.exit_special_modes(); return
        comp_item_under = next((item for item in self.view.items(self.view.mapFromScene(scene_pos)) if isinstance(item, ComponentItem)), None)
        instance_name = comp_item_under.component_model.instance_name if comp_item_under else None
        if self.diagram.add_port(instance_name, direction, [scene_pos.x(), scene_pos.y()], label=label): self.refresh_scene_from_model()
        self.exit_special_modes()

    def handle_connection_click(self, clicked_item):
        if not clicked_item:
            self.exit_special_modes()
            return

        if not self.pending_port_1:
            self.pending_port_1 = clicked_item
            clicked_item.setBrush(QColor("lime"))
            self.status_bar.showMessage("Connect Mode: Click the second port...")
        else:
            if self.pending_port_1 == clicked_item:
                self.exit_special_modes()
                return

            p1_model = self.pending_port_1.port_model
            p2_model = clicked_item.port_model
            key1 = (p1_model.component.instance_name, p1_model.name)
            key2 = (p2_model.component.instance_name, p2_model.name)
            
            success = self.diagram.create_connection(key1, key2)
            self.exit_special_modes()
            if success:
                self.refresh_scene_from_model()
            else:
                QMessageBox.warning(self, "Connection Failed", "Could not create connection.")

    def handle_merge_click(self, clicked_port):
        if not clicked_port: self.exit_special_modes(); return
        if not self.pending_port_for_merge:
            self.pending_port_for_merge = clicked_port; clicked_port.setBrush(QBrush(QColor("cyan")))
            self.status_bar.showMessage("Merge Mode: Click the second port on the same component.")
        else:
            p1_item = self.pending_port_for_merge; p2_item = clicked_port
            p1_model = p1_item.port_model; p2_model = p2_item.port_model
            
            if p1_item == p2_item:
                QMessageBox.warning(self, "Merge Failed", "Cannot merge a port with itself."); self.exit_special_modes(); return
            if p1_model.component != p2_model.component or p1_model.component.module_type in ("Terminal", "InputPort", "OutputPort"):
                QMessageBox.warning(self, "Merge Failed", "Ports must be on the same regular component."); self.exit_special_modes(); return
            if p1_model.direction != p2_model.direction:
                QMessageBox.warning(self, "Merge Failed", "Ports must have the same direction."); self.exit_special_modes(); return
            
            key1 = (p1_model.component.instance_name, p1_model.name)
            key2 = (p2_model.component.instance_name, p2_model.name)
            
            success = self.diagram.merge_ports(key1, key2)
            self.exit_special_modes()
            if success:
                self.status_bar.showMessage(f"Successfully merged {p1_model.label} and {p2_model.label}.", 3000)
                self.refresh_scene_from_model()
            else:
                 QMessageBox.warning(self, "Merge Failed", "An unknown error occurred.")
            
    def rename_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1: return
        port_model = selected[0].port_model
        new_label, ok = QInputDialog.getText(self, "Rename Port Label", "Enter new label:", text=port_model.label)
        if ok and new_label:
            if not self.diagram.rename_port_label(port_model.component.instance_name, port_model.name, new_label):
                QMessageBox.warning(self, "Error", "Could not rename port label.")
            else: self.refresh_scene_from_model()

    def split_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1 or selected[0].port_model.component.module_type in ("Terminal", "InputPort", "OutputPort"):
             QMessageBox.information(self, "Split Port", "Only ports belonging to a regular component can be split.")
             return
        port_model = selected[0].port_model
        if self.diagram.split_port(port_model.component.instance_name, port_model.name):
            self.refresh_scene_from_model()
        else:
            QMessageBox.information(self, "Not Implemented", "The split port functionality is not yet implemented.")
        
    def create_new_component_at(self, box_rect):
        # --- START MODIFICATION ---
        # Core Fix: Distinguish between "instance label" and "module type"
        
        # 1. Get the instance label
        label, ok1 = QInputDialog.getText(self, 'New Component Step 1/2', 'Enter instance label (e.g., my_adder_1):')
        if not (ok1 and label): return
        label = label.strip()

        # 2. Get the module type
        # Suggest a default module type to the user for convenience
        suggested_module_type = re.sub(r'_\d+$', '', label) # Attempt to remove trailing numbers
        module_type, ok2 = QInputDialog.getText(self, 'New Component Step 2/2', 'Enter module type (e.g., Adder):', text=suggested_module_type)
        if not (ok2 and module_type): return
        module_type = module_type.strip()

        # 3. Generate the instance name from the label
        instance_name = label.replace(' ', '_') + "_inst"
        # --- END MODIFICATION ---

        if self.diagram.components.get(instance_name):
            QMessageBox.warning(self, "Error", "An instance with this name already exists."); return
        
        box = [box_rect.left(), box_rect.top(), box_rect.right(), box_rect.bottom()]
        
        # Use the user-specified module_type
        if self.diagram.add_component(instance_name, module_type, label, box):
            self.refresh_scene_from_model()
            if instance_name in self.component_items: self.component_items[instance_name].setSelected(True)
    
    def add_edit_connection_label(self):
        selected_lines = [item for item in self.scene.selectedItems() if isinstance(item, ConnectionLineItem)]
        if len(selected_lines) != 1:
            QMessageBox.information(self, "Edit Label", "Please select exactly one connection line."); return
        line = selected_lines[0]; existing_text = line.label_item.toPlainText() if line.label_item else ""
        text, ok = QInputDialog.getText(self, "Connection Label", "Enter label text (leave empty to remove):", text=existing_text)
        if ok:
            p1_model = line.source_port.port_model; p2_model = line.dest_port.port_model
            key1 = (p1_model.component.instance_name, p1_model.name); key2 = (p2_model.component.instance_name, p2_model.name)
            self.diagram.set_connection_label(key1, key2, text)
            if text:
                if line.label_item: line.label_item.setText(text)
                else:
                    label_item = ConnectionLabelItem(text, line)
                    line.label_item = label_item; self.scene.addItem(label_item)
                line.label_item.update_position()
            elif line.label_item:
                self.scene.removeItem(line.label_item); line.label_item = None

    def update_info_panel(self, comp_model):
        if not comp_model: 
            self.info_label.setText("No item selected.")
            return

        txt = (f"<b>Instance:</b> {comp_model.instance_name}<br>"f"<b>Type:</b> {comp_model.module_type}<br>")
        is_terminal = comp_model.module_type in ("InputPort", "OutputPort")
        if is_terminal:
            if comp_model.ports:
                p = list(comp_model.ports.values())[0]
                pos_status = "Manual" if p.was_manually_positioned else "Auto"
                pos_str = f"[{int(p.position[0])},{int(p.position[1])}]" if p.position else "<font color='orange'>N/A</font>"
                net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
                txt = (f"<b>Top-Level Port (Terminal)</b><br>"
                       f"- <b>Label:</b> {p.label}<br>"
                       f"- <b>Name:</b> {p.name}<br>"
                       f"- <b>Direction:</b> {p.direction}<br>"
                       f"- <b>On Net:</b> <i>{net_str}</i><br>"
                       f"- <b>Position:</b> {pos_str} ({pos_status})<br>")
        else:
            txt += f"<b>Ports:</b> ({len(comp_model.ports)})<br>"
            for p_name, p in sorted(comp_model.ports.items(), key=lambda x: x[1].label):
                pos_status = "Manual" if p.was_manually_positioned else "Auto"
                pos_color = "white" if p.was_manually_positioned else "cyan"
                pos_str = f"[{int(p.position[0])},{int(p.position[1])}]" if p.position else "<font color='orange'>N/A</font>"
                net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
                txt += f"- <b>{p.label}</b> ({p.direction}) on <i>{net_str}</i> @ <font color='{pos_color}'>{pos_str} ({pos_status})</font><br>"
        self.info_label.setText(txt)
        
    def show_context_menu(self, scene_pos, global_pos):
        menu = QMenu(self)
        item = self.view.itemAt(self.view.mapFromScene(scene_pos))
        if isinstance(item, PortItem):
            item.setSelected(True)
            menu.addAction("Rename Port Label...", self.rename_selected_port)
            if item.port_model.component.module_type not in ("Terminal", "InputPort", "OutputPort"):
                menu.addAction("Split Port", self.split_selected_port)
        elif isinstance(item, ConnectionLineItem):
            item.setSelected(True)
            menu.addAction("Add/Edit Connection Label...", self.add_edit_connection_label)
        elif item is None:
            add_in_action = menu.addAction("Add New Input Terminal")
            add_out_action = menu.addAction("Add New Output Terminal")
            action = menu.exec(global_pos)
            if action:
                direction = 'input' if action == add_in_action else 'output'
                self.view.drawing_mode = f'add_{direction}'
                self.handle_add_port_click(scene_pos)
        if menu.actions() and not menu.isEmpty(): menu.exec(global_pos)