# src/ui/main_window.py
import math
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QGraphicsView, 
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter, 
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import CircuitDiagram
from .style import DARK_THEME
from ..graphics_items import ComponentItem, PortItem, ConnectionLineItem

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Verilog Annotator Pro")
        self.resize(1800, 1000)
        # self.setStyleSheet(DARK_THEME) # 取消注释以使用深色主题

        self.diagram = CircuitDiagram()
        self.edit_mode = 'component'
        
        # 文件和路径管理
        self.image_files, self.current_index = [], -1
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        self.image_folder, self.verilog_folder, self.metadata_folder = None, None, None
        
        # 场景和图形项管理
        self.scene = QGraphicsScene()
        self.component_items, self.port_items = {}, {}

        self._init_ui()
        self.show()

    def _init_ui(self):
        toolbar = QToolBar("Main Toolbar"); self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.act_save = QAction("Save (Ctrl+S)", self, triggered=self.save_current_changes, shortcut=QKeySequence.StandardKey.Save)
        self.act_comp = QAction("Component Mode (C)", self, checkable=True, triggered=lambda: self.set_edit_mode('component'))
        self.act_port = QAction("Port Mode (P)", self, checkable=True, triggered=lambda: self.set_edit_mode('port'))
        self.act_new = QAction("New Component (N)", self, triggered=self.create_new_component)
        self.act_del = QAction("Delete (Del)", self, triggered=self.delete_selected_item, shortcut=QKeySequence.StandardKey.Delete)
        toolbar.addAction(self.act_save); toolbar.addSeparator()
        toolbar.addAction(self.act_comp); toolbar.addAction(self.act_port); toolbar.addSeparator()
        toolbar.addAction(self.act_new); toolbar.addAction(self.act_del)

        main_splitter = QSplitter(Qt.Orientation.Horizontal); self.setCentralWidget(main_splitter)

        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        self.image_path_btn = QPushButton("1. Select Images Folder"); self.image_path_btn.clicked.connect(lambda: self.select_folder('image'))
        self.verilog_path_btn = QPushButton("2. Select Verilog Folder"); self.verilog_path_btn.clicked.connect(lambda: self.select_folder('verilog'))
        self.metadata_path_btn = QPushButton("3. Select Metadata Folder"); self.metadata_path_btn.clicked.connect(lambda: self.select_folder('metadata'))
        left_layout.addWidget(QLabel("<b>Project Folders</b>")); left_layout.addWidget(self.image_path_btn); left_layout.addWidget(self.verilog_path_btn); left_layout.addWidget(self.metadata_path_btn); left_layout.addStretch()

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing); self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse); self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        prop_panel = QWidget(); prop_layout = QVBoxLayout(prop_panel)
        self.info_label = QLabel("Select an item to see details."); self.info_label.setObjectName("infoLabel"); self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop); self.info_label.setWordWrap(True)
        self.btn_add_port = QPushButton("Add Port to Component"); self.btn_add_port.setEnabled(False); self.btn_add_port.clicked.connect(self.add_port_to_selected)
        prop_layout.addWidget(QLabel("<b>Properties</b>")); prop_layout.addWidget(self.info_label, 1); prop_layout.addWidget(self.btn_add_port)
        list_panel = QWidget(); list_layout = QVBoxLayout(list_panel)
        self.file_list = QListWidget(); self.file_list.currentItemChanged.connect(self.on_file_selected)
        list_layout.addWidget(QLabel("<b>Image Files</b>")); list_layout.addWidget(self.file_list)
        right_splitter.addWidget(prop_panel); right_splitter.addWidget(list_panel)

        main_splitter.addWidget(left_panel); main_splitter.addWidget(self.view); main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([250, 1200, 350])
        
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.set_edit_mode('component')
    
    def keyPressEvent(self, event):
        key = event.key()
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_S: self.save_current_changes()
        elif key in [Qt.Key.Key_D, Qt.Key.Key_Right]: self.navigate_image(1)
        elif key in [Qt.Key.Key_A, Qt.Key.Key_Left]: self.navigate_image(-1)
        elif key == Qt.Key.Key_C: self.set_edit_mode('component')
        elif key == Qt.Key.Key_P: self.set_edit_mode('port')
        elif key == Qt.Key.Key_N: self.create_new_component()
        else: super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.view.underMouse() and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            scaleFactor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.view.scale(scaleFactor, scaleFactor)
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
        self.status_bar.showMessage("Scanning for image files...")
        self.image_files = sorted([f for ext in self.supported_formats for f in self.image_folder.glob(f"*{ext}")])
        self.file_list.clear()
        for f in self.image_files: self.file_list.addItem(f.name)
        if self.image_files: self.file_list.setCurrentRow(0)
        else: self.status_bar.showMessage("No supported images found in the selected folder.")

    def on_file_selected(self, current, previous):
        if not current or self.file_list.row(current) == self.current_index: return
        if self.current_index != -1: self.save_current_changes()
        self.current_index = self.file_list.row(current)
        self.load_diagram()

    def navigate_image(self, direction):
        if not self.image_files: return
        new_index = (self.current_index + direction) % len(self.image_files)
        self.file_list.setCurrentRow(new_index)

    def save_current_changes(self):
        if self.diagram and self.diagram.image_path:
            self.update_model_from_scene()
            if self.diagram.save_files():
                self.status_bar.showMessage(f"Saved: {self.diagram.image_path.name}", 3000)

    def load_diagram(self):
        print("\n" + "="*20 + " LOADING DIAGRAM " + "="*20)
        if not (0 <= self.current_index < len(self.image_files)): return
        
        img_path = self.image_files[self.current_index]
        v_path = self.verilog_folder / (img_path.stem + ".v")
        m_path = self.metadata_folder / (img_path.stem + ".meta.json")
        
        if not (v_path.exists() and m_path.exists()):
            self.scene.clear()
            pixmap = QPixmap(str(img_path))
            if not pixmap.isNull():
                self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
            self.status_bar.showMessage(f"Error: Missing .v or .meta.json for {img_path.name}")
            return
        
        try:
            self.diagram = CircuitDiagram()
            self.diagram.load_files(img_path, v_path, m_path)
            self.refresh_scene_from_model() # <<< CRITICAL CALL
            self.status_bar.showMessage(f"Loaded: {img_path.name}")
        except Exception as e:
            self.status_bar.showMessage(f"Error loading {img_path.name}: {e}")
            import traceback; traceback.print_exc()

    def refresh_scene_from_model(self):
        """
        FIXED: Rebuilds the scene in stages to avoid timing issues with coordinates.
        Now includes detailed debug logging.
        """
        print("[DEBUG] Refreshing scene with Parent-Child strategy...")
        self.scene.clear(); self.component_items.clear(); self.port_items.clear()
        
        pixmap = QPixmap(str(self.diagram.image_path))
        if pixmap.isNull(): print("[ERROR] Background pixmap is null!"); return
        self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
        
        # --- STAGE 1: Create all components and their child ports ---
        print("[DEBUG] STAGE 1: Creating all Component and Port Items...")
        unassigned_y_offset = 20.0
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = ComponentItem(comp_model)
            self.scene.addItem(comp_item)
            self.component_items[inst_name] = comp_item

            if comp_model.box:
                comp_item.setPos(comp_model.box[0], comp_model.box[1])
                unpositioned = [p for p in comp_model.ports.values() if not p.position]
                if unpositioned:
                    cx, cy = comp_item.boundingRect().width()/2, comp_item.boundingRect().height()/2
                    radius = min(cx, cy) * 0.7 if min(cx, cy) > 0 else 10
                    for i, p_model in enumerate(unpositioned):
                        angle = 2 * math.pi * i / len(unpositioned)
                        p_model.position = [cx + radius*math.cos(angle), cy + radius*math.sin(angle)]
                
                for p_name, p_model in comp_model.ports.items():
                    port_item = PortItem(p_model, parent_item=comp_item)
                    self.port_items[(inst_name, p_name)] = port_item
            else: # Terminals (no box)
                comp_item.setVisible(False)
                for p_name, p_model in comp_model.ports.items():
                    port_item = PortItem(p_model, parent_item=None)
                    if not p_model.position: p_model.position = [20, unassigned_y_offset]; unassigned_y_offset += 25
                    port_item.setPos(*p_model.position)
                    self.scene.addItem(port_item)
                    self.port_items[(inst_name, p_name)] = port_item
        print(f"[DEBUG] Created {len(self.component_items)} components and {len(self.port_items)} ports.")

        # --- STAGE 2: Create all connection lines ---
        print(f"[DEBUG] STAGE 2: Drawing {len(self.diagram.nets)} nets...")
        all_lines = []
        for net_name, net in self.diagram.nets.items():
            ports = net.connections
            if len(ports) < 2: continue
            for i in range(len(ports)):
                for j in range(i + 1, len(ports)):
                    p1_m, p2_m = ports[i], ports[j]
                    k1, k2 = (p1_m.component.instance_name, p1_m.name), (p2_m.component.instance_name, p2_m.name)
                    if k1 in self.port_items and k2 in self.port_items:
                        print(f"[DEBUG]   - Drawing line for net '{net_name}' between {k1} and {k2}")
                        line = ConnectionLineItem(self.port_items[k1], self.port_items[k2])
                        self.scene.addItem(line)
                        all_lines.append(line)
                    else:
                        print(f"[WARN] Could not draw line for net '{net_name}'. Missing port for {k1} or {k2}")

        # --- STAGE 3 (CRITICAL FIX): Force initial path update ---
        print(f"[DEBUG] STAGE 3: Forcing path update for {len(all_lines)} lines...")
        for line in all_lines:
            line.update_path()

        self.set_edit_mode(self.edit_mode)
        self.update_info_panel(None)
        print("[DEBUG] Scene refresh complete.")

    def update_model_from_scene(self):
        if not self.diagram: return
        print("[DEBUG] Updating model from scene...")
        for inst_name, comp_item in self.component_items.items():
            if comp_item.isVisible():
                pos = comp_item.pos()
                rect = comp_item.boundingRect()
                new_box = [pos.x(), pos.y(), pos.x() + rect.width(), pos.y() + rect.height()]
                self.diagram.update_component_box(inst_name, new_box)
        
        for (inst_name, p_name), p_item in self.port_items.items():
            pos = p_item.pos()
            self.diagram.update_port_position(inst_name, p_name, [pos.x(), pos.y()])
                
    def set_edit_mode(self, mode):
        self.edit_mode = mode; is_comp_mode = mode == 'component'
        self.act_comp.setChecked(is_comp_mode); self.act_port.setChecked(not is_comp_mode)
        self.status_bar.showMessage(f"Mode: {'Component' if is_comp_mode else 'Port'}")
        for item in self.scene.items():
            if isinstance(item, ComponentItem): item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_comp_mode)
            elif isinstance(item, PortItem):
                is_movable = (not is_comp_mode) and (item.parentItem() is not None)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_movable)

    def on_selection_changed(self):
        selected = self.scene.selectedItems(); self.btn_add_port.setEnabled(False); model_to_show = None
        if selected:
            item = selected[0]
            if isinstance(item, ComponentItem): model_to_show = item.component_model
            elif isinstance(item, PortItem): model_to_show = item.port_model.component
        if model_to_show:
            self.update_info_panel(model_to_show); self.btn_add_port.setEnabled(True)
        else: self.update_info_panel(None)

    def update_info_panel(self, comp_model):
        if not comp_model: self.info_label.setText("No item selected."); return
        txt = (f"<b>Instance:</b> {comp_model.instance_name}<br>"
               f"<b>Type:</b> {comp_model.module_type}<br>"
               f"<b>Ports:</b> ({len(comp_model.ports)})<br>")
        for p_name, p in sorted(comp_model.ports.items()):
            pos_str = f"[{p.position[0]:.0f},{p.position[1]:.0f}]" if p.position else "<font color='orange'>Unassigned</font>"
            net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
            txt += f"- {p_name} ({p.direction}) on <i>{net_str}</i> @ {pos_str}<br>"
        self.info_label.setText(txt)

    def create_new_component(self):
        text, ok = QInputDialog.getText(self, 'New Component', 'Enter base name (e.g., My Adder):')
        if not (ok and text): return
        instance_name = text.strip().replace(' ', '_') + "_inst"; module_type = text.strip().replace(' ', '_')
        if self.diagram.components.get(instance_name):
            QMessageBox.warning(self, "Error", "An instance with this name already exists."); return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        default_box = [center.x() - 50, center.y() - 50, center.x() + 50, center.y() + 50]
        if self.diagram.add_component(instance_name, module_type, default_box):
            self.set_edit_mode('component'); self.refresh_scene_from_model()
            if instance_name in self.component_items: self.component_items[instance_name].setSelected(True)

    def add_port_to_selected(self):
        selected = self.scene.selectedItems();
        if not selected: return
        item = selected[0]; comp_model = None
        if isinstance(item, ComponentItem): comp_model = item.component_model
        elif isinstance(item, PortItem): comp_model = item.port_model.component
        if not comp_model: return
        direction, ok = QInputDialog.getItem(self, "Add Port", "Select port direction:", ["input", "output"], 0, False)
        if ok and direction:
            if self.diagram.add_port(comp_model.instance_name, direction): self.refresh_scene_from_model()

    def delete_selected_item(self):
        selected = self.scene.selectedItems()
        if not selected: return
        item = selected[0]
        if isinstance(item, ComponentItem):
            inst_name = item.component_model.instance_name
            reply = QMessageBox.question(self, 'Confirm Delete', f"Delete component '{inst_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.diagram.delete_component(inst_name); self.refresh_scene_from_model()
        elif isinstance(item, PortItem):
            port_model = item.port_model
            reply = QMessageBox.question(self, 'Confirm Delete', f"Delete port '{port_model.name}' from '{port_model.component.instance_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.diagram.delete_port(port_model.component.instance_name, port_model.name); self.refresh_scene_from_model()