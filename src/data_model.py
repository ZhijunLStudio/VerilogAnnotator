# src/data_model.py
import json
import uuid
from pathlib import Path
from copy import deepcopy


class Port:
    def __init__(self, id, coord):
        self.id = id
        self.coord = [int(c) for c in coord]

    def to_dict(self):
        return {"coord": self.coord}


class Component:
    def __init__(self, id, type, shape, parent=None, children=None, references=None):
        self.id = id
        self.type = type
        self.shape = shape  # {"type": "rect", "box": [x1,y1,x2,y2]} or {"type": "polygon", "points": [[x,y],...]}
        self.parent = parent  # 物理包含关系（主要父级）
        self.children = children or []  # 物理包含的子级
        self.references = references or []  # 引用关系（逻辑归属）
        self.ports = {}

    def to_dict(self):
        result = {
            "type": self.type,
            "shape": self.shape,
            "parent": self.parent,
            "children": self.children if self.children else None,
            "references": self.references if self.references else None,
            "ports": {pid: p.to_dict() for pid, p in self.ports.items()} if self.ports else None
        }
        # 移除 None 值
        return {k: v for k, v in result.items() if v is not None}


class ExternalPort:
    def __init__(self, id, type, coord):
        self.id = id
        self.type = type
        self.coord = [int(c) for c in coord]

    def to_dict(self):
        return {
            "type": self.type,
            "coord": self.coord
        }


class Connection:
    def __init__(self, nodes):
        self.nodes = nodes  # [{"component": "id", "port": "port_id"}, ...]

    def to_dict(self):
        return {"nodes": self.nodes}


class Diagram:
    def __init__(self):
        self.image_path = None
        self.components = {}
        self.external_ports = {}
        self.connections = []

    def clear(self):
        self.image_path = None
        self.components.clear()
        self.external_ports.clear()
        self.connections.clear()

    def get_shape_position(self, shape):
        """获取 shape 的左上角坐标用于命名"""
        if shape["type"] == "rect":
            return (shape["box"][0], shape["box"][1])
        elif shape["type"] == "polygon":
            return (shape["points"][0][0], shape["points"][0][1])
        return (0, 0)

    def generate_unique_name(self, base_name, position):
        """自动生成带坐标的唯一名称"""
        x, y = int(position[0]), int(position[1])
        new_name = f"{base_name}_{x}_{y}"
        
        # 如果已存在，尝试添加后缀
        counter = 1
        original_name = new_name
        while new_name in self.components or new_name in self.external_ports:
            new_name = f"{original_name}_{counter}"
            counter += 1
        
        return new_name

    def add_component(self, base_name, type, shape, parent=None):
        """添加组件，自动重命名"""
        pos = self.get_shape_position(shape)
        unique_id = self.generate_unique_name(base_name, pos)
        
        component = Component(unique_id, type, shape, parent)
        self.components[unique_id] = component
        
        # 更新父组件的 children
        if parent and parent in self.components:
            if unique_id not in self.components[parent].children:
                self.components[parent].children.append(unique_id)
        
        return component

    def add_external_port(self, base_name, type, coord):
        """添加外部端口，自动重命名"""
        unique_id = self.generate_unique_name(base_name, coord)
        
        port = ExternalPort(unique_id, type, coord)
        self.external_ports[unique_id] = port
        
        return port

    def add_port_to_component(self, component_id, port_id, coord):
        """为组件添加端口"""
        component = self.components.get(component_id)
        if not component:
            return None
        
        # 检查坐标是否在父组件范围内
        if not self.is_point_in_shape(coord, component.shape):
            return None
        
        port = Port(port_id, coord)
        component.ports[port_id] = port
        return port

    def is_point_in_shape(self, point, shape):
        """检查点是否在 shape 内（用于约束端口位置）"""
        x, y = point
        
        if shape["type"] == "rect":
            box = shape["box"]
            return box[0] <= x <= box[2] and box[1] <= y <= box[3]
        
        elif shape["type"] == "polygon":
            # 射线法判断点是否在多边形内
            points = shape["points"]
            n = len(points)
            inside = False
            j = n - 1
            
            for i in range(n):
                xi, yi = points[i]
                xj, yj = points[j]
                
                if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                    inside = not inside
                j = i
            
            return inside
        
        return False

    def delete_component(self, component_id):
        """删除组件及其所有子组件"""
        if component_id not in self.components:
            return False
        
        component = self.components[component_id]
        
        # 递归删除子组件
        for child_id in component.children[:]:
            self.delete_component(child_id)
        
        # 从父组件的 children 中移除
        if component.parent and component.parent in self.components:
            parent = self.components[component.parent]
            if component_id in parent.children:
                parent.children.remove(component_id)
        
        # 删除相关连接
        self.connections = [
            c for c in self.connections 
            if not any(n.get("component") == component_id for n in c.nodes)
        ]
        
        del self.components[component_id]
        return True

    def delete_external_port(self, port_id):
        """删除外部端口"""
        if port_id not in self.external_ports:
            return False
        
        # 删除相关连接
        self.connections = [
            c for c in self.connections 
            if not any(n.get("component") == "external" and n.get("port") == port_id for n in c.nodes)
        ]
        
        del self.external_ports[port_id]
        return True

    def delete_port(self, component_id, port_id):
        """删除组件端口"""
        component = self.components.get(component_id)
        if not component or port_id not in component.ports:
            return False
        
        # 删除相关连接
        self.connections = [
            c for c in self.connections 
            if not any(
                n.get("component") == component_id and n.get("port") == port_id 
                for n in c.nodes
            )
        ]
        
        del component.ports[port_id]
        return True

    def add_connection(self, nodes):
        """添加连接"""
        # 验证节点
        for node in nodes:
            comp_id = node.get("component")
            port_id = node.get("port")
            
            if comp_id == "external":
                if port_id not in self.external_ports:
                    return False
            else:
                if comp_id not in self.components:
                    return False
                if port_id not in self.components[comp_id].ports:
                    return False
        
        conn = Connection(nodes)
        self.connections.append(conn)
        return True

    def delete_connection(self, index):
        """删除连接（按索引）"""
        if 0 <= index < len(self.connections):
            del self.connections[index]
            return True
        return False

    def remove_node_from_connection(self, conn_index, node_to_remove):
        """从连接中移除一个节点
        
        Args:
            conn_index: 连接在 connections 列表中的索引
            node_to_remove: 要移除的节点 {"component": "id", "port": "port_id"}
        
        Returns:
            True if successful, False otherwise
        """
        if 0 <= conn_index < len(self.connections):
            conn = self.connections[conn_index]
            # 找到并移除匹配的节点
            for i, node in enumerate(conn.nodes):
                if (node.get("component") == node_to_remove.get("component") and
                    node.get("port") == node_to_remove.get("port")):
                    conn.nodes.pop(i)
                    # 如果节点数少于2个，删除整个连接
                    if len(conn.nodes) < 2:
                        self.delete_connection(conn_index)
                    return True
        return False

    def update_component_shape(self, component_id, new_shape):
        """更新组件形状"""
        if component_id not in self.components:
            return False
        
        self.components[component_id].shape = new_shape
        return True

    def update_component_position(self, component_id, delta_x, delta_y):
        """更新组件位置（平移）"""
        if component_id not in self.components:
            return False
        
        component = self.components[component_id]
        shape = component.shape
        
        if shape["type"] == "rect":
            box = shape["box"]
            shape["box"] = [
                box[0] + delta_x, box[1] + delta_y,
                box[2] + delta_x, box[3] + delta_y
            ]
        elif shape["type"] == "polygon":
            shape["points"] = [[p[0] + delta_x, p[1] + delta_y] for p in shape["points"]]
        
        # 同时更新所有端口位置
        for port in component.ports.values():
            port.coord[0] += delta_x
            port.coord[1] += delta_y
        
        return True

    def update_port_position(self, component_id, port_id, new_coord):
        """更新端口位置（约束在父组件内）"""
        component = self.components.get(component_id)
        if not component or port_id not in component.ports:
            return False
        
        # 检查新位置是否在组件内
        if not self.is_point_in_shape(new_coord, component.shape):
            return False
        
        component.ports[port_id].coord = [int(c) for c in new_coord]
        return True

    def rename_component(self, old_id, new_base_name):
        """重命名组件"""
        if old_id not in self.components:
            return None
        
        component = self.components[old_id]
        pos = self.get_shape_position(component.shape)
        new_id = self.generate_unique_name(new_base_name, pos)
        
        if new_id == old_id:
            return old_id
        
        # 更新组件 ID
        component.id = new_id
        self.components[new_id] = component
        del self.components[old_id]
        
        # 更新父组件的 children
        if component.parent and component.parent in self.components:
            parent = self.components[component.parent]
            if old_id in parent.children:
                parent.children[parent.children.index(old_id)] = new_id
        
        # 更新子组件的 parent
        for child_id in component.children:
            if child_id in self.components:
                self.components[child_id].parent = new_id
        
        # 更新连接中的引用
        for conn in self.connections:
            for node in conn.nodes:
                if node.get("component") == old_id:
                    node["component"] = new_id
        
        return new_id

    def get_hierarchy_path(self, component_id):
        """获取组件的完整层级路径"""
        if component_id not in self.components:
            return None
        
        path = []
        current = component_id
        
        while current:
            path.insert(0, current)
            component = self.components.get(current)
            if not component:
                break
            current = component.parent
        
        return "/".join(path)

    def get_components_at_level(self, parent_id=None):
        """获取某一层级的所有组件"""
        result = []
        for comp_id, comp in self.components.items():
            if comp.parent == parent_id:
                result.append(comp_id)
        return result

    def save_to_json(self, output_path):
        """保存为干净 JSON"""
        data = {}
        
        # 只保存非空的 components
        if self.components:
            data["components"] = {cid: c.to_dict() for cid, c in self.components.items()}
        
        # 只保存非空的 external_ports
        if self.external_ports:
            data["external_ports"] = {pid: p.to_dict() for pid, p in self.external_ports.items()}
        
        # 只保存非空的 connections
        if self.connections:
            data["connections"] = [c.to_dict() for c in self.connections]
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save JSON: {e}")
            return False

    def _auto_detect_hierarchy(self):
        """自动检测层级关系 - 大框包含小框时，大框成为父级"""
        # 获取所有组件的边界框
        component_boxes = {}
        for cid, comp in self.components.items():
            shape = comp.shape
            if shape["type"] == "rect":
                box = shape["box"]
                component_boxes[cid] = (box[0], box[1], box[2], box[3])
            elif shape["type"] == "polygon":
                points = shape["points"]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                component_boxes[cid] = (min(xs), min(ys), max(xs), max(ys))

        # 检测包含关系
        for cid1, box1 in component_boxes.items():
            comp1 = self.components[cid1]

            # 如果已经有父级，跳过
            if comp1.parent:
                continue

            rect1 = (box1[0], box1[1], box1[2] - box1[0], box1[3] - box1[1])

            # 找包含 cid1 的最小容器
            best_parent = None
            best_area = float('inf')

            for cid2, box2 in component_boxes.items():
                if cid1 == cid2:
                    continue

                rect2 = (box2[0], box2[1], box2[2] - box2[0], box2[3] - box2[1])

                # 检查 rect1 是否完全在 rect2 内
                if (rect2[0] <= rect1[0] and rect2[1] <= rect1[1] and
                    rect2[0] + rect2[2] >= rect1[0] + rect1[2] and
                    rect2[1] + rect2[3] >= rect1[1] + rect1[3]):

                    area = rect2[2] * rect2[3]
                    if area < best_area:
                        best_area = area
                        best_parent = cid2

            if best_parent:
                comp1.parent = best_parent
                if cid1 not in self.components[best_parent].children:
                    self.components[best_parent].children.append(cid1)

    def load_from_json(self, image_path, json_path):
        """从 JSON 加载"""
        self.clear()
        self.image_path = image_path
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Failed to load JSON: {e}")
            return False
        
        # 加载 components
        for cid, cdata in data.get("components", {}).items():
            # 处理 shape（新格式用 shape，旧格式用 box）
            shape = cdata.get("shape")
            if not shape:
                # 旧格式：使用 box
                box = cdata.get("box")
                if box:
                    shape = {"type": "rect", "box": box}
                else:
                    shape = {"type": "rect", "box": [0, 0, 100, 100]}

            component = Component(
                id=cid,
                type=cdata.get("type", "unknown"),
                shape=shape,
                parent=cdata.get("parent"),
                children=cdata.get("children", []),
                references=cdata.get("references", [])
            )

            # 加载 ports（支持字典格式和列表格式）
            ports_data = cdata.get("ports", {})
            if isinstance(ports_data, dict):
                for pid, pdata in ports_data.items():
                    if isinstance(pdata, dict):
                        port = Port(pid, pdata.get("coord", [0, 0]))
                        component.ports[pid] = port
            elif isinstance(ports_data, list):
                # 旧格式：列表形式
                for pdata in ports_data:
                    if isinstance(pdata, dict):
                        pid = pdata.get("name") or pdata.get("id")
                        if pid:
                            coord = pdata.get("coord") or [0, 0]
                            port = Port(pid, coord)
                            component.ports[pid] = port

            self.components[cid] = component

        # 自动检测层级关系（如果JSON中没有明确的父子关系）
        self._auto_detect_hierarchy()
        
        # 加载 external_ports
        for pid, pdata in data.get("external_ports", {}).items():
            port = ExternalPort(
                id=pid,
                type=pdata.get("type", "terminal"),
                coord=pdata.get("coord", [0, 0])
            )
            self.external_ports[pid] = port
        
        # 加载 connections
        for cdata in data.get("connections", []):
            conn = Connection(cdata.get("nodes", []))
            self.connections.append(conn)
        
        return True
