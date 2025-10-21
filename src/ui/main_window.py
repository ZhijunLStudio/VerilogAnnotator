import math
import re
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QGraphicsView, 
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter, 
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog, QGroupBox,
    QMenu, QGraphicsLineItem, QGraphicsPolygonItem
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap, QPen, QColor, QCursor, QBrush, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import CircuitDiagram
from .style import DARK_THEME
from ..graphics_items import ComponentItem, PortItem, ConnectionLineItem, ConnectionLabelItem, GroupItem

class EditableGraphicsView(QGraphicsView):
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.drawing_mode = None
        self.start_pos = None
        self.temp_rect = None
        self.temp_line = None
        self.temp_group_polygon = None
        self.temp_group_rubber_band = None

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        
        if self.drawing_mode == 'group_draw':
            if event.button() == Qt.MouseButton.LeftButton:
                self.main_window.add_group_point(scene_pos)
            elif event.button() == Qt.MouseButton.RightButton:
                self.main_window.finalize_group_drawing()
            event.accept()
            return
            
        if self.drawing_mode:
            target_port = None
            if self.drawing_mode in ['connect', 'merge_ports']:
                item_under_cursor = self.itemAt(event.pos())
                if isinstance(item_under_cursor, PortItem):
                    target_port = item_under_cursor
                else:
                    search_rect = QRectF(scene_pos - QPointF(10, 10), scene_pos + QPointF(10, 10))
                    port_items = [item for item in self.scene().items(search_rect) if isinstance(item, PortItem)]
                    if port_items:
                        target_port = min(port_items, key=lambda p: math.hypot(p.scenePos().x() - scene_pos.x(), p.scenePos().y() - scene_pos.y()))
            if self.drawing_mode in ['add_input', 'add_output']: self.main_window.handle_add_port_click(scene_pos)
            elif self.drawing_mode == 'connect': self.main_window.handle_connection_click(target_port)
            elif self.drawing_mode == 'merge_ports': self.main_window.handle_merge_click(target_port)
            elif self.drawing_mode == 'component_draw' and event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = scene_pos
                self.temp_rect = self.scene().addRect(QRectF(self.start_pos, self.start_pos), QPen(QColor("gold"), 2, Qt.PenStyle.DashLine))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if self.drawing_mode == 'group_draw' and self.main_window.drawing_group_points:
            if not self.temp_group_rubber_band:
                self.temp_group_rubber_band = QGraphicsLineItem()
                self.temp_group_rubber_band.setPen(QPen(QColor("cyan"), 2, Qt.PenStyle.DashLine))
                self.scene().addItem(self.temp_group_rubber_band)
            last_point = self.main_window.drawing_group_points[-1]
            self.temp_group_rubber_band.setLine(last_point.x(), last_point.y(), scene_pos.x(), scene_pos.y())
            event.accept()
        elif self.drawing_mode == 'component_draw' and self.start_pos:
            rect = QRectF(self.start_pos, scene_pos).normalized()
            self.temp_rect.setRect(rect)
            event.accept()
        elif self.drawing_mode == 'connect' and self.main_window.pending_port_1:
            if not self.temp_line:
                start = self.main_window.pending_port_1.scenePos()
                self.temp_line = self.scene().addLine(start.x(), start.y(), start.x(), start.y(), QPen(QColor("lime"), 2, Qt.PenStyle.DashLine))
                self.temp_line.setZValue(10)
            line = self.temp_line.line(); line.setP2(scene_pos); self.temp_line.setLine(line)
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_mode == 'component_draw' and self.start_pos:
            end_pos = self.mapToScene(event.pos())
            if self.temp_rect: self.scene().removeItem(self.temp_rect); self.temp_rect = None
            box = QRectF(self.start_pos, end_pos).normalized()
            if box.width() > 5 and box.height() > 5: self.main_window.create_new_component_at(box)
            self.main_window.exit_special_modes()
            event.accept()
        else: super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event): self.main_window.show_context_menu(self.mapToScene(event.pos()), event.globalPos())
        
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circuit Diagram Editor")
        self.resize(1800, 1000)
        self.diagram = CircuitDiagram()
        self.edit_mode = 'port' 
        self.pending_port_1 = None
        self.pending_port_for_merge = None
        self.image_files, self.current_index = [], -1
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        self.image_folder, self.raw_json_folder, self.unified_json_output_folder = None, None, None
        self.scene = QGraphicsScene(); self.scene.setParent(self)
        self.component_items, self.port_items, self.group_items = {}, {}, {}
        self.drawing_group_points = []
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
        self.act_new_group = QAction("Draw Group (G)", self, triggered=self.enter_group_drawing_mode, shortcut="G")
        self.act_connect = QAction("Connect Ports (L)", self, triggered=self.enter_connection_mode, shortcut="L")
        self.act_del = QAction("Delete (Del)", self, triggered=self.delete_selected_item, shortcut=QKeySequence.StandardKey.Delete)
        toolbar.addAction(self.act_save); toolbar.addSeparator()
        toolbar.addAction(self.act_port); toolbar.addAction(self.act_comp); toolbar.addSeparator()
        toolbar.addAction(self.act_new_comp); toolbar.addAction(self.act_new_group); toolbar.addAction(self.act_connect); toolbar.addSeparator()
        toolbar.addAction(self.act_del)
        
        main_splitter = QSplitter(Qt.Orientation.Horizontal); self.setCentralWidget(main_splitter)
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        
        folder_group = QGroupBox("Project Folders"); folder_layout = QVBoxLayout(folder_group)
        self.image_path_btn = QPushButton("1. Select Image Folder"); self.image_path_btn.clicked.connect(lambda: self.select_folder('image'))
        self.raw_json_path_btn = QPushButton("2. Select Raw JSON Folder (Input)"); self.raw_json_path_btn.clicked.connect(lambda: self.select_folder('raw_json_input'))
        self.unified_json_path_btn = QPushButton("3. Select Unified JSON Folder (Output)"); self.unified_json_path_btn.clicked.connect(lambda: self.select_folder('unified_json_output'))
        folder_layout.addWidget(self.image_path_btn); folder_layout.addWidget(self.raw_json_path_btn); folder_layout.addWidget(self.unified_json_path_btn)
        left_layout.addWidget(folder_group)
        
        self.file_list = QListWidget(); self.file_list.currentItemChanged.connect(self.on_file_selected)
        file_group = QGroupBox("Image Files"); file_layout = QVBoxLayout(file_group); file_layout.addWidget(self.file_list)
        left_layout.addWidget(file_group)

        self.view = EditableGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing); self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        prop_group = QGroupBox("Properties")
        prop_layout = QVBoxLayout(prop_group)
        self.info_label = QLabel("Select an item to see details."); self.info_label.setObjectName("infoLabel"); self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop); self.info_label.setWordWrap(True)
        prop_layout.addWidget(self.info_label)
        
        ops_group = QGroupBox("Operations"); ops_layout = QVBoxLayout(ops_group)
        self.btn_add_port_in = QPushButton("Add Input Port"); self.btn_add_port_in.clicked.connect(lambda: self.enter_add_port_mode('input'))
        self.btn_add_port_out = QPushButton("Add Output Port"); self.btn_add_port_out.clicked.connect(lambda: self.enter_add_port_mode('output'))
        self.btn_merge_ports = QPushButton("Merge Ports"); self.btn_merge_ports.clicked.connect(self.enter_merge_mode)
        self.btn_rename = QPushButton("Rename Selected"); self.btn_rename.clicked.connect(self.rename_selected_item)
        self.btn_split_port = QPushButton("Split Selected Port"); self.btn_split_port.clicked.connect(self.split_selected_port)
        self.btn_add_conn_label = QPushButton("Add/Edit Connection Label"); self.btn_add_conn_label.clicked.connect(self.add_edit_connection_label)
        
        ops_layout.addWidget(self.btn_add_port_in); ops_layout.addWidget(self.btn_add_port_out)
        ops_layout.addWidget(self.btn_merge_ports); ops_layout.addWidget(self.btn_rename)
        ops_layout.addWidget(self.btn_split_port); ops_layout.addWidget(self.btn_add_conn_label)

        right_layout.addWidget(prop_group); right_layout.addWidget(ops_group); right_layout.addStretch(1)

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
        path = QFileDialog.getExistingDirectory(self, f"Select {folder_type.replace('_', ' ').title()} Folder")
        if not path: return
        p = Path(path)
        if folder_type == 'image': self.image_folder = p; self.image_path_btn.setText(f"Images: ...{p.name}")
        elif folder_type == 'raw_json_input': self.raw_json_folder = p; self.raw_json_path_btn.setText(f"Raw JSONs: ...{p.name}")
        elif folder_type == 'unified_json_output': self.unified_json_output_folder = p; self.unified_json_path_btn.setText(f"Unified JSONs: ...{p.name}")
        
        if self.image_folder and self.raw_json_folder: self.scan_and_load_files()
        
    def scan_and_load_files(self):
        self.image_files = sorted([f for ext in self.supported_formats for f in self.image_folder.glob(f"*{ext}")])
        self.file_list.clear()
        for f in self.image_files: self.file_list.addItem(f.name)
        if self.image_files: self.file_list.setCurrentRow(0)
        
    def on_file_selected(self, current, previous):
        if previous is not None and self.current_index != -1: self.save_current_changes()
        if not current: self.current_index = -1; return
        new_index = self.file_list.row(current)
        if new_index == self.current_index: return
        self.current_index = new_index
        self.load_diagram()
        
    def navigate_image(self, direction):
        if not self.image_files: return
        new_index = (self.current_index + direction) % len(self.image_files)
        self.file_list.setCurrentRow(new_index)
        
    def save_current_changes(self):
        if not (self.diagram and self.diagram.image_path): return
        if not self.unified_json_output_folder: QMessageBox.warning(self, "Save Error", "Please select a Unified JSON Output Folder before saving."); return
        json_filename = self.diagram.image_path.stem + ".diagram.json"
        output_path = self.unified_json_output_folder / json_filename
        if self.diagram.save_to_unified_json(output_path): self.status_bar.showMessage(f"Saved: {json_filename}", 3000)
        else: self.status_bar.showMessage(f"Failed to save {json_filename}", 3000)

    def load_diagram(self):
        if not (0 <= self.current_index < len(self.image_files)): return
        img_path = self.image_files[self.current_index]
        if not self.raw_json_folder: self.status_bar.showMessage("Error: Raw JSON input folder not selected."); return
        raw_json_path = self.raw_json_folder / (img_path.stem + ".json")
        if not raw_json_path.exists(): self.status_bar.showMessage(f"Error: No corresponding JSON found for {img_path.name}"); self.scene.clear(); return
            
        try:
            self.diagram = CircuitDiagram()
            if self.diagram.load_from_raw_json(img_path, raw_json_path):
                self.refresh_scene_from_model(); self.status_bar.showMessage(f"Loaded: {img_path.name}")
            else: self.status_bar.showMessage(f"Failed to process {raw_json_path.name}")
        except Exception as e:
            self.status_bar.showMessage(f"Critical error loading {img_path.name}: {e}")
            import traceback; traceback.print_exc()

    def delete_selected_item(self):
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentItem): self.diagram.delete_component(item.component_model.instance_name)
            elif isinstance(item, PortItem): pm = item.port_model; self.diagram.delete_port(pm.component.instance_name, pm.name)
            elif isinstance(item, GroupItem): self.diagram.delete_group(item.group_model.name)
        self.refresh_scene_from_model()
    
    def refresh_scene_from_model(self):
        self.scene.clear(); self.component_items.clear(); self.port_items.clear(); self.group_items.clear()
        
        if self.diagram.image_path and self.diagram.image_path.exists():
            pixmap = QPixmap(str(self.diagram.image_path)); self.scene.addPixmap(pixmap)
            image_rect = QRectF(pixmap.rect())
        else: image_rect = QRectF(0, 0, 1000, 1000)
        layout_rect = image_rect.adjusted(-50, -50, 50, 50)
        
        for group_name, group_model in self.diagram.groups.items():
            group_item = GroupItem(group_model); self.scene.addItem(group_item); self.group_items[group_name] = group_item
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = ComponentItem(comp_model); self.scene.addItem(comp_item); self.component_items[inst_name] = comp_item
            if comp_model.box: comp_item.setPos(QPointF(*comp_model.box[:2]))
            else: comp_item.setVisible(False)
        for inst_name, comp_model in self.diagram.components.items():
            if comp_model.box and comp_model.module_type not in ("InputPort", "OutputPort"):
                unpositioned_ports = [p for p in comp_model.ports.values() if not p.was_manually_positioned]
                if unpositioned_ports:
                    inputs = sorted([p for p in unpositioned_ports if p.direction == 'input'], key=lambda p: p.label)
                    outputs = sorted([p for p in unpositioned_ports if p.direction == 'output'], key=lambda p: p.label)
                    box = comp_model.box; box_rect = QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1])
                    for i, p_model in enumerate(inputs): p_model.position = [int(box_rect.left()), int(box_rect.top() + (i + 1) * box_rect.height() / (len(inputs) + 1))]
                    for i, p_model in enumerate(outputs): p_model.position = [int(box_rect.right()), int(box_rect.top() + (i + 1) * box_rect.height() / (len(outputs) + 1))]
        terminals = [p for c in self.diagram.components.values() for p in c.ports.values() if c.module_type in ("InputPort", "OutputPort")]
        unpositioned_terminals = [p for p in terminals if not p.was_manually_positioned]
        if unpositioned_terminals:
            top_inputs = sorted([p for p in unpositioned_terminals if p.direction == 'output'], key=lambda p: p.label)
            top_outputs = sorted([p for p in unpositioned_terminals if p.direction == 'input'], key=lambda p: p.label)
            for i, p_model in enumerate(top_inputs): p_model.position = [int(layout_rect.left() + 20), int(layout_rect.top() + (i + 1) * layout_rect.height() / (len(top_inputs) + 1))]
            for i, p_model in enumerate(top_outputs): p_model.position = [int(layout_rect.right() - 20), int(layout_rect.top() + (i + 1) * layout_rect.height() / (len(top_outputs) + 1))]
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = self.component_items[inst_name]
            for p_name, p_model in comp_model.ports.items():
                is_terminal = comp_model.module_type in ("InputPort", "OutputPort")
                parent_item = None if is_terminal else comp_item
                port_item = PortItem(p_model, parent_item=parent_item)
                if not parent_item: self.scene.addItem(port_item)
                self.port_items[(inst_name, p_name)] = port_item
                if p_model.position:
                    if parent_item: port_item.setPos(parent_item.mapFromScene(QPointF(*p_model.position)))
                    else: port_item.setPos(QPointF(*p_model.position))
        all_lines = []
        for net in self.diagram.nets.values():
            ports_in_net = [self.port_items.get((p.component.instance_name, p.name)) for p in net.connections]
            ports_in_net = [p for p in ports_in_net if p is not None]
            ports_in_net.sort(key=lambda item: (item.port_model.component.instance_name, item.port_model.name))
            if len(ports_in_net) < 2: continue
            num_ports = len(ports_in_net); in_tree = [False]*num_ports; distance = [float('inf')]*num_ports; parent_edge = [-1]*num_ports; distance[0] = 0
            for _ in range(num_ports):
                min_dist, u = float('inf'), -1
                for i in range(num_ports):
                    if not in_tree[i] and distance[i] < min_dist: min_dist, u = distance[i], i
                if u == -1: break
                in_tree[u] = True
                port_u, pos_u = ports_in_net[u], ports_in_net[u].scenePos()
                for v in range(num_ports):
                    if not in_tree[v]:
                        port_v, pos_v = ports_in_net[v], ports_in_net[v].scenePos()
                        dist_uv = math.hypot(pos_u.x() - pos_v.x(), pos_u.y() - pos_v.y())
                        if dist_uv < distance[v]: distance[v], parent_edge[v] = dist_uv, u
            for i in range(1, num_ports):
                parent_idx = parent_edge[i]
                if parent_idx != -1: line = ConnectionLineItem(ports_in_net[parent_idx], ports_in_net[i]); self.scene.addItem(line); line.update_path(); all_lines.append(line)
        for line in all_lines:
            p1_model, p2_model = line.source_port.port_model, line.dest_port.port_model
            k1,k2 = (p1_model.component.instance_name,p1_model.name), (p2_model.component.instance_name,p2_model.name)
            key_tuple = tuple(sorted((f"{k1[0]}.{k1[1]}", f"{k2[0]}.{k2[1]}"))); label_key = "--".join(key_tuple)
            if label_key in self.diagram.connection_labels:
                text = self.diagram.connection_labels[label_key].get("text", "")
                label_item = ConnectionLabelItem(text, line); line.label_item = label_item; self.scene.addItem(label_item); label_item.update_position()
        self.scene.setSceneRect(layout_rect); self.set_edit_mode(self.edit_mode, force_update=True); self.on_selection_changed()
    
    def on_selection_changed(self):
        selected = self.scene.selectedItems()
        self.btn_rename.setEnabled(len(selected) == 1 and isinstance(selected[0], (PortItem, GroupItem)))
        self.btn_split_port.setEnabled(len(selected) == 1 and isinstance(selected[0], PortItem) and selected[0].port_model.component.module_type not in ("InputPort", "OutputPort"))
        self.btn_add_conn_label.setEnabled(len(selected) == 1 and isinstance(selected[0], ConnectionLineItem))
        model_to_show = None
        if selected:
            item = selected[0]
            if isinstance(item, PortItem): model_to_show = item.port_model.component
            elif isinstance(item, ComponentItem): model_to_show = item.component_model
        self.update_info_panel(model_to_show)

    def exit_special_modes(self):
        if self.view.temp_group_polygon: self.scene.removeItem(self.view.temp_group_polygon); self.view.temp_group_polygon = None
        if self.view.temp_group_rubber_band: self.scene.removeItem(self.view.temp_group_rubber_band); self.view.temp_group_rubber_band = None
        self.drawing_group_points.clear()
        
        if self.pending_port_1: p = self.pending_port_1; c = {'i':"#D32F2F", 'o':"#388E3C"}.get(p.port_model.direction[0], "#F57C00"); p.setBrush(QColor(c)); self.pending_port_1 = None
        if self.pending_port_for_merge: p = self.pending_port_for_merge; c = {'i':"#D32F2F", 'o':"#388E3C"}.get(p.port_model.direction[0], "#F57C00"); p.setBrush(QColor(c)); self.pending_port_for_merge = None
        if self.view.temp_line: self.scene.removeItem(self.view.temp_line); self.view.temp_line = None
        self.view.drawing_mode = None; self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.status_bar.showMessage(f"Mode: {'Component' if self.edit_mode == 'component' else 'Port'}")

    def enter_group_drawing_mode(self):
        self.exit_special_modes()
        self.view.drawing_mode = 'group_draw'
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Draw Group: Left-click to add points, Right-click to finish.")
        
    def add_group_point(self, point):
        self.drawing_group_points.append(point)
        if not self.view.temp_group_polygon:
            self.view.temp_group_polygon = QGraphicsPolygonItem()
            self.view.temp_group_polygon.setPen(QPen(QColor("cyan"), 2, Qt.PenStyle.DashLine))
            self.scene.addItem(self.view.temp_group_polygon)
        self.view.temp_group_polygon.setPolygon(QPolygonF(self.drawing_group_points))

    def finalize_group_drawing(self):
        if len(self.drawing_group_points) < 3:
            QMessageBox.warning(self, "Group Error", "A group must have at least 3 points.")
        else:
            label, ok = QInputDialog.getText(self, "New Group", "Enter group label (optional):")
            if ok:
                final_label = label if label else "Unnamed Group"
                points = [[p.x(), p.y()] for p in self.drawing_group_points]
                self.diagram.add_group(final_label, points)
                self.refresh_scene_from_model()
        self.exit_special_modes()
    
    def rename_selected_item(self):
        if not self.scene.selectedItems(): return
        item = self.scene.selectedItems()[0]
        if isinstance(item, PortItem):
            port_model = item.port_model
            new_label, ok = QInputDialog.getText(self, "Rename Port Label", "Enter new label:", text=port_model.label)
            if ok and new_label: self.diagram.rename_port_label(port_model.component.instance_name, port_model.name, new_label); self.refresh_scene_from_model()
        elif isinstance(item, GroupItem):
            group_model = item.group_model
            new_label, ok = QInputDialog.getText(self, "Rename Group Label", "Enter new label:", text=group_model.label)
            if ok and new_label: self.diagram.rename_group_label(group_model.name, new_label); self.refresh_scene_from_model()
    
    def set_edit_mode(self, mode, force_update=False):
        if self.edit_mode == mode and not force_update: return
        self.exit_special_modes(); self.edit_mode = mode
        is_comp_mode = mode == 'component'
        self.act_comp.setChecked(is_comp_mode); self.act_port.setChecked(not is_comp_mode)
        self.status_bar.showMessage(f"Mode: {'Component' if is_comp_mode else 'Port'}")
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        for item in self.scene.items():
            if isinstance(item, (ComponentItem, PortItem, GroupItem)): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            if isinstance(item, (ComponentItem, GroupItem)): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_comp_mode)
            elif isinstance(item, PortItem): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_comp_mode)
    
    def handle_merge_click(self, clicked_port):
        if not clicked_port: self.exit_special_modes(); return
        if not self.pending_port_for_merge:
            self.pending_port_for_merge = clicked_port; clicked_port.setBrush(QBrush(QColor("cyan")))
            self.status_bar.showMessage("Merge Mode: Click the second port on the same component.")
        else:
            p1i, p2i = self.pending_port_for_merge, clicked_port
            p1m, p2m = p1i.port_model, p2i.port_model
            
            # --- BUG FIX: Call exit_special_modes() BEFORE refreshing the scene ---
            self.exit_special_modes()
            
            if p1i == p2i: QMessageBox.warning(self, "Merge Failed", "Cannot merge a port with itself.")
            elif p1m.component != p2m.component or p1m.component.module_type in ("InputPort", "OutputPort"): QMessageBox.warning(self, "Merge Failed", "Ports must be on the same regular component.")
            elif p1m.direction != p2m.direction: QMessageBox.warning(self, "Merge Failed", "Ports must have the same direction.")
            else:
                k1, k2 = (p1m.component.instance_name, p1m.name), (p2m.component.instance_name, p2m.name)
                if self.diagram.merge_ports(k1, k2):
                    self.status_bar.showMessage(f"Successfully merged {p1m.label} and {p2m.label}.", 3000)
                    self.refresh_scene_from_model() # Refresh only on success
                else:
                    QMessageBox.warning(self, "Merge Failed", "An unknown error occurred.")

    def add_edit_connection_label(self):
        # We find the line under the cursor for the context menu, which is more reliable
        # than relying on selection, which is now disabled.
        pos = self.view.mapFromGlobal(QCursor.pos())
        item = self.view.itemAt(pos)
        if not isinstance(item, ConnectionLineItem):
            QMessageBox.information(self, "Edit Label", "Please right-click directly on a connection line to add a label."); return
        line = item
        existing_text = line.label_item.text() if line.label_item else ""
        text, ok = QInputDialog.getText(self, "Connection Label", "Enter label text:", text=existing_text)
        if ok:
            p1m, p2m = line.source_port.port_model, line.dest_port.port_model
            k1,k2 = (p1m.component.instance_name, p1m.name), (p2m.component.instance_name, p2m.name)
            self.diagram.set_connection_label(k1, k2, text)
            if text:
                if line.label_item: line.label_item.setText(text)
                else: label_item = ConnectionLabelItem(text, line); line.label_item = label_item; self.scene.addItem(label_item)
                line.label_item.update_position()
            elif line.label_item: self.scene.removeItem(line.label_item); line.label_item = None
            
    def show_context_menu(self, scene_pos, global_pos):
        menu = QMenu(self)
        # Find item directly under cursor for context actions
        item = self.view.itemAt(self.view.mapFromScene(scene_pos))
        
        if isinstance(item, PortItem):
            item.setSelected(True); menu.addAction("Rename Port Label...", self.rename_selected_item)
            if item.port_model.component.module_type not in ("InputPort", "OutputPort"): menu.addAction("Split Port", self.split_selected_port)
        elif isinstance(item, ConnectionLineItem):
            item.setSelected(True); menu.addAction("Add/Edit Connection Label...", self.add_edit_connection_label)
        elif isinstance(item, GroupItem):
            item.setSelected(True); menu.addAction("Rename Group...", self.rename_selected_item); menu.addAction("Delete Group", self.delete_selected_item)
        elif item is None:
            add_in = menu.addAction("Add New Input Terminal"); add_out = menu.addAction("Add New Output Terminal")
            action = menu.exec(global_pos)
            if action: self.view.drawing_mode = 'add_input' if action == add_in else 'add_output'; self.handle_add_port_click(scene_pos)
        
        if menu.actions() and not menu.isEmpty(): menu.exec(global_pos)
        
    # ... all other methods are unchanged ...
    def enter_add_port_mode(self, direction): self.set_edit_mode('port'); self.view.drawing_mode = f'add_{direction}'; self.view.setCursor(Qt.CursorShape.CrossCursor); self.status_bar.showMessage(f"Add {direction.capitalize()} Port Mode: Click on the diagram.")
    def enter_connection_mode(self): self.set_edit_mode('port'); self.view.drawing_mode = 'connect'; self.view.setCursor(Qt.CursorShape.CrossCursor); self.status_bar.showMessage("Connect Mode: Click the first port...")
    def enter_component_drawing_mode(self): self.set_edit_mode('component'); self.view.drawing_mode = 'component_draw'; self.view.setCursor(Qt.CursorShape.CrossCursor); self.status_bar.showMessage("Drawing Mode: Click and drag to draw a new component.")
    def enter_merge_mode(self): self.set_edit_mode('port'); self.view.drawing_mode = 'merge_ports'; self.view.setCursor(Qt.CursorShape.PointingHandCursor); self.status_bar.showMessage("Merge Mode: Click the first port to merge...")
    def handle_add_port_click(self, scene_pos):
        direction = 'input' if self.view.drawing_mode == 'add_input' else 'output'
        label, ok = QInputDialog.getText(self, "New Port", "Enter port label (e.g., 'CLK', 'ADDR[0]'):")
        if not (ok and label): self.exit_special_modes(); return
        comp_item_under = next((item for item in self.view.items(self.view.mapFromScene(scene_pos)) if isinstance(item, ComponentItem)), None)
        instance_name = comp_item_under.component_model.instance_name if comp_item_under else None
        if self.diagram.add_port(instance_name, direction, [scene_pos.x(), scene_pos.y()], label=label): self.refresh_scene_from_model()
        self.exit_special_modes()
    def handle_connection_click(self, clicked_item):
        if not clicked_item: self.exit_special_modes(); return
        if not self.pending_port_1: self.pending_port_1 = clicked_item; clicked_item.setBrush(QColor("lime")); self.status_bar.showMessage("Connect Mode: Click the second port...")
        else:
            if self.pending_port_1 == clicked_item: self.exit_special_modes(); return
            p1m, p2m = self.pending_port_1.port_model, clicked_item.port_model
            k1, k2 = (p1m.component.instance_name, p1m.name), (p2m.component.instance_name, p2m.name)
            self.exit_special_modes()
            if self.diagram.create_connection(k1, k2): self.refresh_scene_from_model()
            else: QMessageBox.warning(self, "Connection Failed", "Could not create connection.")
    def split_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1 or selected[0].port_model.component.module_type in ("InputPort", "OutputPort"): QMessageBox.information(self, "Split Port", "Only ports belonging to a regular component can be split."); return
        pm = selected[0].port_model
        if self.diagram.split_port(pm.component.instance_name, pm.name): self.refresh_scene_from_model()
        else: QMessageBox.information(self, "Not Implemented", "The split port functionality is not yet implemented.")
    def create_new_component_at(self, box_rect):
        label, ok1 = QInputDialog.getText(self, 'New Component Step 1/2', 'Enter instance label (e.g., my_adder_1):')
        if not (ok1 and label): return
        label = label.strip()
        suggested_module_type = re.sub(r'_\d+$', '', label)
        module_type, ok2 = QInputDialog.getText(self, 'New Component Step 2/2', 'Enter module type (e.g., Adder):', text=suggested_module_type)
        if not (ok2 and module_type): return
        module_type = module_type.strip()
        instance_name = label.replace(' ', '_') + "_inst"
        if self.diagram.components.get(instance_name): QMessageBox.warning(self, "Error", "An instance with this name already exists."); return
        box = [box_rect.left(), box_rect.top(), box_rect.right(), box_rect.bottom()]
        if self.diagram.add_component(instance_name, module_type, label, box):
            self.refresh_scene_from_model()
            if instance_name in self.component_items: self.component_items[instance_name].setSelected(True)
    def update_info_panel(self, comp_model):
        if not comp_model: self.info_label.setText("No item selected."); return
        txt = (f"<b>Instance:</b> {comp_model.instance_name}<br>"f"<b>Type:</b> {comp_model.module_type}<br>")
        if comp_model.module_type in ("InputPort", "OutputPort"):
            if comp_model.ports:
                p = list(comp_model.ports.values())[0]
                pos_str = f"[{int(p.position[0])},{int(p.position[1])}]" if p.position else "<font color='orange'>N/A</font>"
                net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
                txt = (f"<b>Top-Level Port (Terminal)</b><br>" f"- <b>Label:</b> {p.label}<br>" f"- <b>Name:</b> {p.name}<br>" f"- <b>Direction:</b> {p.direction}<br>" f"- <b>On Net:</b> <i>{net_str}</i><br>" f"- <b>Position:</b> {pos_str} ({'Manual' if p.was_manually_positioned else 'Auto'})<br>")
        else:
            txt += f"<b>Ports:</b> ({len(comp_model.ports)})<br>"
            for p_name, p in sorted(comp_model.ports.items(), key=lambda x: x[1].label):
                pos_color = "white" if p.was_manually_positioned else "cyan"
                pos_str = f"[{int(p.position[0])},{int(p.position[1])}]" if p.position else "<font color='orange'>N/A</font>"
                net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
                txt += f"- <b>{p.label}</b> ({p.direction}) on <i>{net_str}</i> @ <font color='{pos_color}'>{pos_str} ({'Manual' if p.was_manually_positioned else 'Auto'})</font><br>"
        self.info_label.setText(txt)