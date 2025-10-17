# src/ui/main_window.py
import math
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QGraphicsView, 
    QGraphicsScene, QPushButton, QLabel, QStatusBar, QToolBar, QSplitter, 
    QMessageBox, QInputDialog, QGraphicsItem, QFileDialog, QGroupBox,
    QMenu
)
from PyQt6.QtGui import QPainter, QAction, QKeySequence, QPixmap, QPen, QColor, QCursor
from PyQt6.QtCore import Qt, QPointF, QRectF

from ..data_model import CircuitDiagram
from .style import DARK_THEME
from ..graphics_items import ComponentItem, PortItem, ConnectionLineItem

class EditableGraphicsView(QGraphicsView):
    """A custom QGraphicsView to handle component drawing."""
    def __init__(self, scene, main_window):
        super().__init__(scene)
        self.main_window = main_window
        self.drawing_mode = None
        self.start_pos = None
        self.temp_rect = None

    def mousePressEvent(self, event):
        if self.drawing_mode == 'component' and event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, self.start_pos)
            self.temp_rect = self.scene().addRect(rect, QPen(QColor("gold"), 2, Qt.PenStyle.DashLine))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing_mode == 'component' and self.start_pos:
            current_pos = self.mapToScene(event.pos())
            rect = QRectF(self.start_pos, current_pos).normalized()
            self.temp_rect.setRect(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing_mode == 'component' and self.start_pos:
            end_pos = self.mapToScene(event.pos())
            if self.temp_rect:
                self.scene().removeItem(self.temp_rect)
                self.temp_rect = None
            
            box = QRectF(self.start_pos, end_pos).normalized()
            # Only create if the box has a valid size
            if box.width() > 5 and box.height() > 5:
                self.main_window.create_new_component_at(box)

            self.drawing_mode = None
            self.start_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.main_window.status_bar.showMessage("Component drawing finished. Back to Component Mode.")
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.main_window.show_context_menu(self.mapToScene(event.pos()), event.globalPos())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Verilog Annotator Pro")
        self.resize(1800, 1000)
        # self.setStyleSheet(DARK_THEME)

        self.diagram = CircuitDiagram()
        self.edit_mode = 'port' # DEFAULT MODE CHANGED
        
        self.image_files, self.current_index = [], -1
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        self.image_folder, self.verilog_folder, self.metadata_folder = None, None, None
        
        self.scene = QGraphicsScene()
        self.component_items, self.port_items = {}, {}

        self._init_ui()
        self.set_edit_mode(self.edit_mode) # Apply default mode on start
        self.show()

    def _init_ui(self):
        # --- Toolbar ---
        toolbar = QToolBar("Main Toolbar"); self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.act_save = QAction("Save (Ctrl+S)", self, triggered=self.save_current_changes, shortcut=QKeySequence.StandardKey.Save)
        self.act_port = QAction("Port Mode (P)", self, checkable=True, triggered=lambda: self.set_edit_mode('port'))
        self.act_comp = QAction("Component Mode (C)", self, checkable=True, triggered=lambda: self.set_edit_mode('component'))
        self.act_new_comp = QAction("Draw Component (W)", self, triggered=self.enter_component_drawing_mode, shortcut="W")
        self.act_del = QAction("Delete (Del)", self, triggered=self.delete_selected_item, shortcut=QKeySequence.StandardKey.Delete)
        
        toolbar.addAction(self.act_save); toolbar.addSeparator()
        toolbar.addAction(self.act_port); toolbar.addAction(self.act_comp); toolbar.addSeparator()
        toolbar.addAction(self.act_new_comp); toolbar.addAction(self.act_del)

        main_splitter = QSplitter(Qt.Orientation.Horizontal); self.setCentralWidget(main_splitter)

        # --- Left Panel ---
        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel)
        folder_group = QGroupBox("Project Folders")
        folder_layout = QVBoxLayout(folder_group)
        self.image_path_btn = QPushButton("1. Select Images Folder"); self.image_path_btn.clicked.connect(lambda: self.select_folder('image'))
        self.verilog_path_btn = QPushButton("2. Select Verilog Folder"); self.verilog_path_btn.clicked.connect(lambda: self.select_folder('verilog'))
        self.metadata_path_btn = QPushButton("3. Select Metadata Folder"); self.metadata_path_btn.clicked.connect(lambda: self.select_folder('metadata'))
        folder_layout.addWidget(self.image_path_btn); folder_layout.addWidget(self.verilog_path_btn); folder_layout.addWidget(self.metadata_path_btn)
        left_layout.addWidget(folder_group)
        
        self.file_list = QListWidget(); self.file_list.currentItemChanged.connect(self.on_file_selected)
        file_group = QGroupBox("Image Files")
        file_layout = QVBoxLayout(file_group)
        file_layout.addWidget(self.file_list)
        left_layout.addWidget(file_group)

        # --- Center View ---
        self.view = EditableGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing); self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse); self.view.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # --- Right Panel ---
        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel)
        self.info_label = QLabel("Select an item to see details."); self.info_label.setObjectName("infoLabel"); self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop); self.info_label.setWordWrap(True)
        prop_group = QGroupBox("Properties"); prop_layout = QVBoxLayout(prop_group); prop_layout.addWidget(self.info_label)
        
        port_ops_group = QGroupBox("Port Operations")
        port_ops_layout = QVBoxLayout(port_ops_group)
        self.btn_add_port_in = QPushButton("Add Input Port"); self.btn_add_port_in.clicked.connect(lambda: self.add_port_to_selected('input'))
        self.btn_add_port_out = QPushButton("Add Output Port"); self.btn_add_port_out.clicked.connect(lambda: self.add_port_to_selected('output'))
        self.btn_rename_port = QPushButton("Rename Port"); self.btn_rename_port.clicked.connect(self.rename_selected_port)
        self.btn_split_port = QPushButton("Split Port"); self.btn_split_port.clicked.connect(self.split_selected_port)
        self.btn_merge_ports = QPushButton("Merge Ports"); self.btn_merge_ports.clicked.connect(self.merge_selected_ports)
        port_ops_layout.addWidget(self.btn_add_port_in); port_ops_layout.addWidget(self.btn_add_port_out); port_ops_layout.addWidget(self.btn_rename_port)
        port_ops_layout.addWidget(self.btn_split_port); port_ops_layout.addWidget(self.btn_merge_ports)

        right_layout.addWidget(prop_group, 1); right_layout.addWidget(port_ops_group)
        
        main_splitter.addWidget(left_panel); main_splitter.addWidget(self.view); main_splitter.addWidget(right_panel)
        main_splitter.setSizes([250, 1200, 350])
        
        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.scene.selectionChanged.connect(self.on_selection_changed)
    
    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_D: self.navigate_image(1)
            elif event.key() == Qt.Key.Key_A: self.navigate_image(-1)
            elif event.key() == Qt.Key.Key_C: self.set_edit_mode('component')
            elif event.key() == Qt.Key.Key_P: self.set_edit_mode('port')
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if self.view.underMouse() and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            scaleFactor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.view.scale(scaleFactor, scaleFactor)
        else: super().wheelEvent(event)

    # --- File and Loading Logic (mostly unchanged) ---
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
            self.update_model_from_scene() # This now happens before save
            if self.diagram.save_files():
                self.status_bar.showMessage(f"Saved: {self.diagram.image_path.name}", 3000)

    def load_diagram(self):
        # ... (same as original)
        if not (0 <= self.current_index < len(self.image_files)): return
        img_path = self.image_files[self.current_index]
        v_path = self.verilog_folder / (img_path.stem + ".v")
        m_path = self.metadata_folder / (img_path.stem + ".meta.json")
        if not (v_path.exists() and m_path.exists()):
            self.scene.clear(); pixmap = QPixmap(str(img_path))
            if not pixmap.isNull(): self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
            self.status_bar.showMessage(f"Error: Missing .v or .meta.json for {img_path.name}")
            return
        try:
            self.diagram = CircuitDiagram()
            self.diagram.load_files(img_path, v_path, m_path)
            self.refresh_scene_from_model()
            self.status_bar.showMessage(f"Loaded: {img_path.name}")
        except Exception as e:
            self.status_bar.showMessage(f"Error loading {img_path.name}: {e}")
            import traceback; traceback.print_exc()

    # --- Scene and Model Synchronization ---
    def refresh_scene_from_model(self):
        self.scene.clear(); self.component_items.clear(); self.port_items.clear()
        pixmap = QPixmap(str(self.diagram.image_path))
        if pixmap.isNull(): return
        self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
        
        unassigned_y_offset = 20.0
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = ComponentItem(comp_model)
            self.scene.addItem(comp_item)
            self.component_items[inst_name] = comp_item

            if comp_model.box: # Component with a bounding box
                comp_item.setPos(comp_model.box[0], comp_model.box[1])
                # Temporarily position un-positioned ports for display
                unpositioned_ports = [p for p in comp_model.ports.values() if not p.position]
                if unpositioned_ports:
                    cx, cy = comp_item.boundingRect().width() / 2, comp_item.boundingRect().height() / 2
                    radius = max(min(cx, cy) * 0.8, 10)
                    for i, p_model in enumerate(unpositioned_ports):
                        angle = 2 * math.pi * i / len(unpositioned_ports)
                        # Create PortItem as child, its position is relative to the parent
                        port_item = PortItem(p_model, parent_item=comp_item)
                        port_item.setPos(cx + radius * math.cos(angle), cy + radius * math.sin(angle))
                        self.port_items[(inst_name, p_model.name)] = port_item
                
                # Create items for ports that already have a position
                for p_name, p_model in comp_model.ports.items():
                    if p_model.position and (inst_name, p_name) not in self.port_items:
                        port_item = PortItem(p_model, parent_item=comp_item)
                        self.port_items[(inst_name, p_name)] = port_item
            
            else: # Terminal (no box), treat its ports as top-level items
                comp_item.setVisible(False)
                for p_name, p_model in comp_model.ports.items():
                    # CRITICAL FIX: parent_item=None makes it a top-level, movable item
                    port_item = PortItem(p_model, parent_item=None)
                    if p_model.position:
                        port_item.setPos(*p_model.position)
                    else:
                        # Assign a temporary position if none exists
                        port_item.setPos(20, unassigned_y_offset)
                        unassigned_y_offset += 25
                    self.scene.addItem(port_item)
                    self.port_items[(inst_name, p_name)] = port_item

        all_lines = []
        for net in self.diagram.nets.values():
            ports = net.connections
            for i in range(len(ports)):
                for j in range(i + 1, len(ports)):
                    p1_m, p2_m = ports[i], ports[j]
                    k1, k2 = (p1_m.component.instance_name, p1_m.name), (p2_m.component.instance_name, p2_m.name)
                    if k1 in self.port_items and k2 in self.port_items:
                        line = ConnectionLineItem(self.port_items[k1], self.port_items[k2])
                        self.scene.addItem(line); all_lines.append(line)
        
        for line in all_lines: line.update_path()
        self.set_edit_mode(self.edit_mode, force_update=True)
        self.on_selection_changed()

    def update_model_from_scene(self):
        if not self.diagram: return
        for inst_name, comp_item in self.component_items.items():
            if comp_item.isVisible():
                pos = comp_item.pos()
                rect = comp_item.rect() # Use rect(), not boundingRect() for accurate size
                new_box = [pos.x(), pos.y(), pos.x() + rect.width(), pos.y() + rect.height()]
                self.diagram.update_component_box(inst_name, new_box)
        
        # NOTE: Port positions are now updated in PortItem.itemChange directly.
        # This function is now mainly for component boxes.

    # --- UI Interaction and Modes ---
    def set_edit_mode(self, mode, force_update=False):
        if self.edit_mode == mode and not force_update: return
        self.edit_mode = mode; is_comp_mode = mode == 'component'
        
        self.act_comp.setChecked(is_comp_mode)
        self.act_port.setChecked(not is_comp_mode)
        self.status_bar.showMessage(f"Mode: {'Component' if is_comp_mode else 'Port'}")
        
        # Enable/disable items based on mode
        for item in self.scene.items():
            if isinstance(item, ComponentItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_comp_mode)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, is_comp_mode)
            elif isinstance(item, PortItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_comp_mode)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not is_comp_mode)
    
    def on_selection_changed(self):
        selected_ports = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        selected_comps = [item for item in self.scene.selectedItems() if isinstance(item, ComponentItem)]
        
        # Update buttons enabled state
        self.btn_rename_port.setEnabled(len(selected_ports) == 1)
        self.btn_split_port.setEnabled(len(selected_ports) == 1)
        self.btn_merge_ports.setEnabled(len(selected_ports) == 2)
        self.btn_add_port_in.setEnabled(len(selected_comps) == 1 or len(selected_ports) > 0)
        self.btn_add_port_out.setEnabled(len(selected_comps) == 1 or len(selected_ports) > 0)
        
        # Update info panel
        if selected_ports:
            self.update_info_panel(selected_ports[0].port_model.component)
        elif selected_comps:
            self.update_info_panel(selected_comps[0].component_model)
        else:
            self.update_info_panel(None)

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

    # --- New Feature Implementations ---
    def enter_component_drawing_mode(self):
        self.set_edit_mode('component')
        self.view.drawing_mode = 'component'
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Drawing Mode: Click and drag to draw a new component.")

    def create_new_component_at(self, box_rect):
        text, ok = QInputDialog.getText(self, 'New Component', 'Enter base name (e.g., My Adder):')
        if not (ok and text): return
        instance_name = text.strip().replace(' ', '_') + "_inst"; module_type = text.strip().replace(' ', '_')
        if self.diagram.components.get(instance_name):
            QMessageBox.warning(self, "Error", "An instance with this name already exists."); return
        
        box = [box_rect.left(), box_rect.top(), box_rect.right(), box_rect.bottom()]
        if self.diagram.add_component(instance_name, module_type, box):
            self.refresh_scene_from_model()
            if instance_name in self.component_items: self.component_items[instance_name].setSelected(True)

    def add_port_to_selected(self, direction):
        selected = self.scene.selectedItems()
        if not selected: return
        item = selected[0]; comp_model = None
        if isinstance(item, ComponentItem): comp_model = item.component_model
        elif isinstance(item, PortItem): comp_model = item.port_model.component
        
        if comp_model:
            if self.diagram.add_port(comp_model.instance_name, direction): self.refresh_scene_from_model()

    def rename_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1: return
        port_item = selected[0]
        port_model = port_item.port_model
        
        new_name, ok = QInputDialog.getText(self, "Rename Port", "Enter new name:", text=port_model.name)
        if ok and new_name and new_name != port_model.name:
            if self.diagram.rename_port(port_model.component.instance_name, port_model.name, new_name):
                self.refresh_scene_from_model()
            else:
                QMessageBox.warning(self, "Error", f"Could not rename. Name '{new_name}' might already exist.")

    def split_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1: return
        port_model = selected[0].port_model
        if self.diagram.split_port(port_model.component.instance_name, port_model.name):
            self.refresh_scene_from_model()

    def merge_selected_ports(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 2: return
        p1_model, p2_model = selected[0].port_model, selected[1].port_model
        
        key1 = (p1_model.component.instance_name, p1_model.name)
        key2 = (p2_model.component.instance_name, p2_model.name)

        if self.diagram.merge_ports(key1, key2):
            self.refresh_scene_from_model()
        else:
            QMessageBox.warning(self, "Merge Failed", "Ports must be on the same component and have the same direction.")

    def delete_selected_item(self):
        selected = self.scene.selectedItems()
        if not selected: return
        # Perform deletion without confirmation
        for item in selected:
            if isinstance(item, ComponentItem):
                self.diagram.delete_component(item.component_model.instance_name)
            elif isinstance(item, PortItem):
                pm = item.port_model
                self.diagram.delete_port(pm.component.instance_name, pm.name)
        self.refresh_scene_from_model()

    def show_context_menu(self, scene_pos, global_pos):
        menu = QMenu(self)
        item = self.itemAt(self.view.mapFromScene(scene_pos))
        
        if isinstance(item, PortItem):
            item.setSelected(True)
            menu.addAction("Rename Port...", self.rename_selected_port)
            menu.addAction("Split Port", self.split_selected_port)
            if len([p for p in self.scene.selectedItems() if isinstance(p, PortItem)]) == 2:
                menu.addAction("Merge Selected Ports", self.merge_selected_ports)
        elif item is None: # Clicked on empty space
            add_in_action = menu.addAction("Add New Input Terminal")
            add_out_action = menu.addAction("Add New Output Terminal")
            action = menu.exec(global_pos)
            if action == add_in_action:
                if self.diagram.add_port(None, 'input', [scene_pos.x(), scene_pos.y()]): self.refresh_scene_from_model()
            elif action == add_out_action:
                if self.diagram.add_port(None, 'output', [scene_pos.x(), scene_pos.y()]): self.refresh_scene_from_model()