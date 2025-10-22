import json
import uuid
from pathlib import Path
from copy import deepcopy

class Port:
    """Represents a connection point on an Entity. Position is relative to entity origin."""
    def __init__(self, id, label, direction, position):
        self.id = id
        self.label = label
        self.direction = direction
        self.position = position

class Entity:
    """Represents a component or a terminal in the diagram."""
    def __init__(self, id, label, type, box, position):
        self.id = id
        self.label = label
        self.type = type
        self.box = box  # [width, height] or None for terminals
        self.position = position # [x, y] top-left corner on the scene
        self.ports = {} # {port_id: Port_object}

class Diagram:
    """Manages all data for a single diagram project."""
    def __init__(self):
        self.image_path = None
        self.entities = {}
        self.connections = []

    def clear(self):
        self.image_path = None; self.entities.clear(); self.connections.clear()

    def add_entity(self, label, type, box=None, position=[0,0]):
        entity_id = f"ent_{uuid.uuid4().hex[:12]}"
        new_entity = Entity(entity_id, label, type, box, position)
        self.entities[entity_id] = new_entity
        return new_entity

    def delete_entity(self, entity_id):
        if entity_id in self.entities:
            del self.entities[entity_id]
            self.connections = [c for c in self.connections if c['endpoints'][0]['entity_id'] != entity_id and c['endpoints'][1]['entity_id'] != entity_id]
            return True
        return False

    def update_entity_position(self, entity_id, position):
        if entity_id in self.entities: self.entities[entity_id].position = [int(p) for p in position]

    def update_entity_box(self, entity_id, box):
        if entity_id in self.entities: self.entities[entity_id].box = [int(c) for c in box]
    
    def rename_entity(self, entity_id, new_label):
        if entity_id in self.entities: self.entities[entity_id].label = new_label; return True
        return False

    def add_port(self, entity_id, label, direction, rel_position):
        entity = self.entities.get(entity_id)
        if not entity: return None
        port_id = f"port_{len(entity.ports)}"
        while port_id in entity.ports: port_id = f"port_{uuid.uuid4().hex[:4]}"
        new_port = Port(port_id, label, direction, [int(p) for p in rel_position])
        entity.ports[port_id] = new_port
        return new_port

    def delete_port(self, entity_id, port_id):
        entity = self.entities.get(entity_id)
        if entity and port_id in entity.ports:
            del entity.ports[port_id]
            self.connections = [c for c in self.connections if not (c['endpoints'][0]['entity_id'] == entity_id and c['endpoints'][0]['port_id'] == port_id) and not (c['endpoints'][1]['entity_id'] == entity_id and c['endpoints'][1]['port_id'] == port_id)]
            return True
        return False
        
    def update_port_position(self, entity_id, port_id, rel_position):
        entity = self.entities.get(entity_id)
        if entity and port_id in entity.ports: entity.ports[port_id].position = [int(p) for p in rel_position]

    def rename_port(self, entity_id, port_id, new_label):
        entity = self.entities.get(entity_id)
        if entity and port_id in entity.ports: entity.ports[port_id].label = new_label; return True
        return False

    def create_connection(self, key1, key2):
        (entity_id1, port_id1), (entity_id2, port_id2) = key1, key2
        if not (entity_id1 in self.entities and port_id1 in self.entities[entity_id1].ports and entity_id2 in self.entities and port_id2 in self.entities[entity_id2].ports): return False
        new_conn = {"id": f"conn_{uuid.uuid4().hex[:12]}", "endpoints": [{"entity_id": entity_id1, "port_id": port_id1}, {"entity_id": entity_id2, "port_id": port_id2}], "label": ""}
        self.connections.append(new_conn)
        return True

    def delete_connection(self, connection_id):
        self.connections = [c for c in self.connections if c['id'] != connection_id]

    def update_connection_label(self, connection_id, new_label):
        for conn in self.connections:
            if conn['id'] == connection_id: conn['label'] = new_label; return True
        return False

    def save_to_json(self, output_path):
        data_to_save = {"diagram_info": {"schema_version": "3.1-RelativePos", "image_source": Path(self.image_path).name if self.image_path else "N/A"}, "entities": {eid: deepcopy(e.__dict__) for eid, e in self.entities.items()}, "connections": self.connections}
        for entity_data in data_to_save["entities"].values():
            entity_data["ports"] = {pid: p.__dict__ for pid, p in entity_data["ports"].items()}
        try:
            with open(output_path, 'w', encoding='utf-8') as f: json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e: print(f"[ERROR] Failed to save project JSON: {e}"); return False

    def load_from_json(self, image_path, project_path):
        self.clear(); self.image_path = image_path
        try:
            with open(project_path, 'r', encoding='utf-8') as f: data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return False
        for entity_id, entity_data in data.get("entities", {}).items():
            position = entity_data.get('position', [0, 0])
            entity = Entity(entity_id, entity_data['label'], entity_data['type'], entity_data['box'], position)
            for port_id, port_data in entity_data.get("ports", {}).items():
                port = Port(port_id, port_data['label'], port_data['direction'], port_data['position'])
                entity.ports[port_id] = port
            self.entities[entity_id] = entity
        self.connections = data.get("connections", [])
        return True

    def load_from_raw_json(self, image_path, raw_json_path):
        self.clear(); self.image_path = image_path
        try:
            with open(raw_json_path, 'r', encoding='utf-8') as f: raw_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return False
        defined_components = set(raw_data.keys()); all_entity_labels = set(defined_components); directed_connections = set()
        for src, data in raw_data.items():
            for conn_type in ['input', 'output', 'inout']:
                for conn in data.get('connections', {}).get(conn_type, []):
                    if 'name' in conn:
                        tgt = conn['name']; all_entity_labels.add(tgt)
                        if conn_type == 'input': directed_connections.add((tgt, src))
                        else: directed_connections.add((src, tgt))
        label_to_id_map = {}
        for label in sorted(list(all_entity_labels)):
            raw_box = raw_data.get(label, {}).get("component_box")
            box_dims, position = None, [0,0]
            if raw_box:
                box_dims = [raw_box[2] - raw_box[0], raw_box[3] - raw_box[1]]
                position = [raw_box[0], raw_box[1]]
            entity_type = "Terminal" if box_dims is None else label
            entity = self.add_entity(label, entity_type, box_dims, position)
            label_to_id_map[label] = entity.id
        port_trackers = {label: {'input': 0, 'output': 0} for label in all_entity_labels}
        port_map = {}
        for src_label, tgt_label in sorted(list(directed_connections)):
            src_entity_id, tgt_entity_id = label_to_id_map[src_label], label_to_id_map[tgt_label]
            src_port_idx, tgt_port_idx = port_trackers[src_label]['output'], port_trackers[tgt_label]['input']
            src_port_label, tgt_port_label = f"out_{src_port_idx}", f"in_{tgt_port_idx}"
            if (src_label, 'output', src_port_idx) not in port_map:
                port = self.add_port(src_entity_id, src_port_label, 'output', [0, 0]); port_map[(src_label, 'output', src_port_idx)] = port.id
            src_port_id = port_map[(src_label, 'output', src_port_idx)]
            if (tgt_label, 'input', tgt_port_idx) not in port_map:
                port = self.add_port(tgt_entity_id, tgt_port_label, 'input', [0, 0]); port_map[(tgt_label, 'input', tgt_port_idx)] = port.id
            tgt_port_id = port_map[(tgt_label, 'input', tgt_port_idx)]
            self.create_connection((src_entity_id, src_port_id), (tgt_entity_id, tgt_port_id))
            port_trackers[src_label]['output'] += 1; port_trackers[tgt_label]['input'] += 1
        return True