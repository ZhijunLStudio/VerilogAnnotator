# src/ui/main_window.py
import math
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
from ..graphics_items import ComponentItem, PortItem, ConnectionLineItem

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
            if self.drawing_mode in ['add_input', 'add_output']:
                self.main_window.handle_add_port_click(scene_pos)
            
            # --- FIX: New, robust connection logic with snap-to-port ---
            elif self.drawing_mode == 'connect':
                target_port = None
                
                # First, try a direct hit
                item_under_cursor = self.itemAt(event.pos())
                if isinstance(item_under_cursor, PortItem):
                    target_port = item_under_cursor
                else:
                    # If direct hit fails, search for the nearest port in a radius
                    search_rect = QRectF(scene_pos - QPointF(10, 10), scene_pos + QPointF(10, 10))
                    nearby_items = self.scene().items(search_rect)
                    port_items = [item for item in nearby_items if isinstance(item, PortItem)]
                    
                    if port_items:
                        # Find the closest one
                        min_dist = float('inf')
                        for port in port_items:
                            dist = math.hypot(port.scenePos().x() - scene_pos.x(), port.scenePos().y() - scene_pos.y())
                            if dist < min_dist:
                                min_dist = dist
                                target_port = port
                
                # Pass the found port (or None if nothing is nearby) to the handler
                self.main_window.handle_connection_click(target_port)

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
        else:
            super().mouseMoveEvent(event)

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
        else:
            super().mouseReleaseEvent(event)

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
        self.image_files, self.current_index = [], -1
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
        self.image_folder, self.verilog_folder, self.metadata_folder = None, None, None
        self.scene = QGraphicsScene()
        self.scene.setParent(self)
        self.component_items, self.port_items = {}, {}
        self._init_ui()
        self.set_edit_mode(self.edit_mode)
        self.show()

    def _init_ui(self):
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
        folder_group = QGroupBox("Project Folders")
        folder_layout = QVBoxLayout(folder_group)
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
        ops_group = QGroupBox("Operations")
        ops_layout = QVBoxLayout(ops_group)
        self.btn_add_port_in = QPushButton("Add Input Port"); self.btn_add_port_in.clicked.connect(lambda: self.enter_add_port_mode('input'))
        self.btn_add_port_out = QPushButton("Add Output Port"); self.btn_add_port_out.clicked.connect(lambda: self.enter_add_port_mode('output'))
        self.btn_merge_ports = QPushButton("Merge Selected Ports"); self.btn_merge_ports.clicked.connect(self.merge_selected_ports)
        self.btn_rename_port = QPushButton("Rename Selected Port"); self.btn_rename_port.clicked.connect(self.rename_selected_port)
        self.btn_split_port = QPushButton("Split Selected Port"); self.btn_split_port.clicked.connect(self.split_selected_port)
        ops_layout.addWidget(self.btn_add_port_in); ops_layout.addWidget(self.btn_add_port_out)
        ops_layout.addWidget(self.btn_merge_ports); ops_layout.addWidget(self.btn_rename_port)
        ops_layout.addWidget(self.btn_split_port)
        right_layout.addWidget(prop_group)
        right_layout.addStretch(1)
        right_layout.addWidget(ops_group)
        

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
            if self.diagram.save_files(): self.status_bar.showMessage(f"Saved: {self.diagram.image_path.name}", 3000)
    def load_diagram(self):
        if not (0 <= self.current_index < len(self.image_files)): return
        img_path = self.image_files[self.current_index]
        v_path = self.verilog_folder / (img_path.stem + ".v")
        m_path = self.metadata_folder / (img_path.stem + ".meta.json")
        if not (v_path.exists() and m_path.exists()):
            self.scene.clear(); pixmap = QPixmap(str(img_path))
            if not pixmap.isNull(): self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
            self.status_bar.showMessage(f"Error: Missing files for {img_path.name}")
            return
        try:
            self.diagram = CircuitDiagram(); self.diagram.load_files(img_path, v_path, m_path)
            self.refresh_scene_from_model(); self.status_bar.showMessage(f"Loaded: {img_path.name}")
        except Exception as e:
            self.status_bar.showMessage(f"Error loading {img_path.name}: {e}")
            import traceback; traceback.print_exc()
    def delete_selected_item(self):
        for item in self.scene.selectedItems():
            if isinstance(item, ComponentItem): self.diagram.delete_component(item.component_model.instance_name)
            elif isinstance(item, PortItem):
                pm = item.port_model; self.diagram.delete_port(pm.component.instance_name, pm.name)
        self.refresh_scene_from_model()
    
    def refresh_scene_from_model(self):
        # This function is correct and robust from the previous version.
        self.scene.clear(); self.component_items.clear(); self.port_items.clear()
        pixmap = QPixmap(str(self.diagram.image_path))
        if not pixmap.isNull(): self.scene.addPixmap(pixmap); self.view.setSceneRect(QRectF(pixmap.rect()))
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = ComponentItem(comp_model)
            self.scene.addItem(comp_item); self.component_items[inst_name] = comp_item
            if comp_model.box: comp_item.setPos(*comp_model.box[:2])
            else: comp_item.setVisible(False)
        unassigned_y_offset = 20.0
        PORT_OFFSET = 10
        for inst_name, comp_model in self.diagram.components.items():
            comp_item = self.component_items[inst_name]
            temp_positions = {}
            if comp_model.box:
                unpositioned_ports = [p for p in comp_model.ports.values() if p.position is None]
                inputs = sorted([p for p in unpositioned_ports if p.direction == 'input'], key=lambda p: p.name)
                outputs = sorted([p for p in unpositioned_ports if p.direction == 'output'], key=lambda p: p.name)
                comp_rect = comp_item.sceneBoundingRect()
                for i, p_model in enumerate(inputs):
                    y = comp_rect.top() + (i + 1) * comp_rect.height() / (len(inputs) + 1)
                    temp_positions[p_model.name] = QPointF(comp_rect.left() - PORT_OFFSET, y)
                for i, p_model in enumerate(outputs):
                    y = comp_rect.top() + (i + 1) * comp_rect.height() / (len(outputs) + 1)
                    temp_positions[p_model.name] = QPointF(comp_rect.right() + PORT_OFFSET, y)
            for p_name, p_model in comp_model.ports.items():
                parent = comp_item if comp_model.box else None
                port_item = PortItem(p_model, parent_item=parent)
                self.port_items[(inst_name, p_name)] = port_item
                abs_pos = None
                if p_model.position: abs_pos = QPointF(*p_model.position)
                elif p_name in temp_positions: abs_pos = temp_positions[p_name]
                else: abs_pos = QPointF(20, unassigned_y_offset); unassigned_y_offset += 25
                if parent: port_item.setPos(parent.mapFromScene(abs_pos))
                else: self.scene.addItem(port_item); port_item.setPos(abs_pos)
        for net in self.diagram.nets.values():
            if len(net.connections) > 1:
                hub_key = (net.connections[0].component.instance_name, net.connections[0].name)
                for i in range(1, len(net.connections)):
                    spoke_key = (net.connections[i].component.instance_name, net.connections[i].name)
                    if hub_key in self.port_items and spoke_key in self.port_items:
                        line = ConnectionLineItem(self.port_items[hub_key], self.port_items[spoke_key])
                        self.scene.addItem(line); line.update_path()
        self.set_edit_mode(self.edit_mode, force_update=True)
        self.on_selection_changed()

    def update_model_from_scene(self):
        if not self.diagram: return
        for inst_name, comp_item in self.component_items.items():
            if comp_item.isVisible():
                pos = comp_item.pos(); rect = comp_item.rect()
                self.diagram.update_component_box(inst_name, [pos.x(), pos.y(), pos.x() + rect.width(), pos.y() + rect.height()])
    
    # --- Interaction Logic (Refactored) ---

    def on_selection_changed(self):
        """Update button states and info panel based on current selection."""
        selected_items = self.scene.selectedItems()
        selected_ports = [item for item in selected_items if isinstance(item, PortItem)]
        selected_comps = [item for item in selected_items if isinstance(item, ComponentItem)]

        # Button states
        self.btn_rename_port.setEnabled(len(selected_ports) == 1)
        self.btn_split_port.setEnabled(len(selected_ports) == 1)
        self.btn_merge_ports.setEnabled(len(selected_ports) == 2)
        self.btn_add_port_in.setEnabled(True)
        self.btn_add_port_out.setEnabled(True)
        
        # --- FIX: Type-safe info panel update ---
        model_to_show = None
        if selected_ports:
            # If ports are selected, show info of their parent component
            model_to_show = selected_ports[0].port_model.component
        elif selected_comps:
            # If no ports but components are selected, show the first component
            model_to_show = selected_comps[0].component_model
        
        self.update_info_panel(model_to_show)


    def set_edit_mode(self, mode, force_update=False):
        if self.edit_mode == mode and not force_update: return
        self.exit_special_modes()
        self.edit_mode = mode
        is_comp_mode = mode == 'component'
        self.act_comp.setChecked(is_comp_mode); self.act_port.setChecked(not is_comp_mode)
        self.status_bar.showMessage(f"Mode: {'Component' if is_comp_mode else 'Port'}")
        self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        for item in self.scene.items():
            # Make all our custom items selectable in any mode for simplicity
            if isinstance(item, (ComponentItem, PortItem)):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            
            # Control movability based on mode
            if isinstance(item, ComponentItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_comp_mode)
            elif isinstance(item, PortItem):
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not is_comp_mode)

    def exit_special_modes(self):
        # If there was a pending connection, reset its color without a full refresh
        if self.pending_port_1:
            p_model = self.pending_port_1.port_model
            original_color = {'input': QColor("#D32F2F"), 'output': QColor("#388E3C")}.get(p_model.direction, QColor("#F57C00"))
            self.pending_port_1.setBrush(QBrush(original_color))
            self.pending_port_1 = None

        # Clean up temporary drawing items
        if self.view.temp_line:
            self.scene.removeItem(self.view.temp_line)
            self.view.temp_line = None
        
        # Reset cursor and status message
        self.view.drawing_mode = None
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.status_bar.showMessage(f"Mode: {'Component' if self.edit_mode == 'component' else 'Port'}")

    # --- Mode Entry Points ---
    def enter_add_port_mode(self, direction):
        self.set_edit_mode('port')
        self.view.drawing_mode = f'add_{direction}'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage(f"Add {direction.capitalize()} Port Mode: Click on the diagram.")
    def enter_connection_mode(self):
        self.set_edit_mode('port')
        self.view.drawing_mode = 'connect'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Connect Mode: Click the first port...")
    def enter_component_drawing_mode(self):
        self.set_edit_mode('component')
        self.view.drawing_mode = 'component_draw'; self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage("Drawing Mode: Click and drag to draw a new component.")

    # --- Click Handlers ---
    def handle_add_port_click(self, scene_pos):
        direction = 'input' if self.view.drawing_mode == 'add_input' else 'output'
        comp_item_under = next((item for item in self.view.items(self.view.mapFromScene(scene_pos)) if isinstance(item, ComponentItem)), None)
        instance_name = comp_item_under.component_model.instance_name if comp_item_under else None
        
        new_port = self.diagram.add_port(instance_name, direction, [scene_pos.x(), scene_pos.y()])
        if new_port:
            # FIX: 在成功添加端口后，必须刷新场景以显示新端口
            self.refresh_scene_from_model()
            self.exit_special_modes()
        else:
            QMessageBox.warning(self, "Error", "Could not add port.")
            self.exit_special_modes()

    def handle_connection_click(self, clicked_item):
        # The view now gives us a valid PortItem or None
        if not clicked_item:
            self.exit_special_modes()
            return

        if not self.pending_port_1:
            # First port clicked
            self.pending_port_1 = clicked_item
            clicked_item.setBrush(QColor("lime")) # Highlight
            self.status_bar.showMessage("Connect Mode: Click the second port...")
        else:
            # Second port clicked
            if self.pending_port_1 == clicked_item:
                self.exit_special_modes() # Cancel if same port clicked twice
                return

            # Perform the surgical update (this logic from before was correct)
            p1_model = self.pending_port_1.port_model
            p2_model = clicked_item.port_model
            key1 = (p1_model.component.instance_name, p1_model.name)
            key2 = (p2_model.component.instance_name, p2_model.name)
            if self.diagram.create_connection(key1, key2):
                line = ConnectionLineItem(self.pending_port_1, clicked_item)
                self.scene.addItem(line)
                line.update_path()
                
                # Update tooltips
                net_name = p1_model.net.name
                tooltip1 = f"Port: {p1_model.name}\nNet: {net_name}\nType: {p1_model.direction}"
                tooltip2 = f"Port: {p2_model.name}\nNet: {net_name}\nType: {p2_model.direction}"
                self.pending_port_1.setToolTip(tooltip1)
                clicked_item.setToolTip(tooltip2)

            self.exit_special_modes() # Cleans up highlighting and state safely

    # --- Actions triggered from buttons ---
    def merge_selected_ports(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 2:
            QMessageBox.information(self, "Merge Ports", "Please select exactly two ports to merge.")
            return
        p1_model = selected[0].port_model; p2_model = selected[1].port_model
        key1 = (p1_model.component.instance_name, p1_model.name)
        key2 = (p2_model.component.instance_name, p2_model.name)
        if not self.diagram.merge_ports(key1, key2):
            QMessageBox.warning(self, "Merge Failed", "Ports must be on the same component and have the same direction.")
        else:
            self.refresh_scene_from_model()
            
    def rename_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1: return
        port_model = selected[0].port_model
        new_name, ok = QInputDialog.getText(self, "Rename Port", "Enter new name:", text=port_model.name)
        if ok and new_name and new_name != port_model.name:
            if not self.diagram.rename_port(port_model.component.instance_name, port_model.name, new_name):
                QMessageBox.warning(self, "Error", f"Could not rename. Name '{new_name}' might already exist.")
            self.refresh_scene_from_model()

    def split_selected_port(self):
        selected = [item for item in self.scene.selectedItems() if isinstance(item, PortItem)]
        if len(selected) != 1: return
        port_model = selected[0].port_model
        if self.diagram.split_port(port_model.component.instance_name, port_model.name):
            self.refresh_scene_from_model()
        
    def create_new_component_at(self, box_rect):
        text, ok = QInputDialog.getText(self, 'New Component', 'Enter base name:')
        if not (ok and text): return
        instance_name = text.strip().replace(' ', '_') + "_inst"; module_type = text.strip().replace(' ', '_')
        if self.diagram.components.get(instance_name):
            QMessageBox.warning(self, "Error", "An instance with this name already exists."); return
        box = [box_rect.left(), box_rect.top(), box_rect.right(), box_rect.bottom()]
        if self.diagram.add_component(instance_name, module_type, box):
            self.refresh_scene_from_model()
            if instance_name in self.component_items: self.component_items[instance_name].setSelected(True)
            
    def update_info_panel(self, comp_model):
        if not comp_model: self.info_label.setText("No item selected."); return
        txt = (f"<b>Instance:</b> {comp_model.instance_name}<br>" f"<b>Type:</b> {comp_model.module_type}<br>"
               f"<b>Ports:</b> ({len(comp_model.ports)})<br>")
        for p_name, p in sorted(comp_model.ports.items()):
            pos_str = f"[{p.position[0]},{p.position[1]}]" if p.position else "<font color='orange'>null</font>"
            net_str = p.net.name if p.net else "<font color='grey'>N/A</font>"
            txt += f"- {p_name} ({p.direction}) on <i>{net_str}</i> @ {pos_str}<br>"
        self.info_label.setText(txt)
        
    def show_context_menu(self, scene_pos, global_pos):
        menu = QMenu(self)
        item = self.view.itemAt(self.view.mapFromScene(scene_pos))
        if isinstance(item, PortItem):
            item.setSelected(True)
            menu.addAction("Rename Port...", self.rename_selected_port)
            menu.addAction("Split Port", self.split_selected_port)
        elif item is None:
            add_in_action = menu.addAction("Add New Input Terminal")
            add_out_action = menu.addAction("Add New Output Terminal")
            action = menu.exec(global_pos)
            if action == add_in_action:
                if self.diagram.add_port(None, 'input', [scene_pos.x(), scene_pos.y()]): self.refresh_scene_from_model()
            elif action == add_out_action:
                if self.diagram.add_port(None, 'output', [scene_pos.x(), scene_pos.y()]): self.refresh_scene_from_model()