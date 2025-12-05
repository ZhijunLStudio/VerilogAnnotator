# src/data_model.py
import json
import uuid
from pathlib import Path
from copy import deepcopy
from collections import defaultdict

class Port:
    def __init__(self, id, label, direction, position):
        self.id, self.label, self.direction, self.position = id, label, direction, position

class Entity:
    def __init__(self, id, label, type, box, position):
        self.id, self.label, self.type, self.box, self.position = id, label, type, box, position
        self.ports = {}

class Group:
    def __init__(self, id, label, box):
        self.id, self.label, self.box = id, label, box

class Diagram:
    def __init__(self):
        self.image_path = None; self.entities = {}; self.connections = []; self.groups = {}

    def clear(self):
        self.image_path = None; self.entities.clear(); self.connections.clear(); self.groups.clear()

    def add_entity(self, label, type, box=None, position=[0,0]):
        entity = Entity(f"ent_{uuid.uuid4().hex[:12]}", label, type, box, position)
        self.entities[entity.id] = entity; return entity

    def add_group(self, label, box):
        group = Group(f"grp_{uuid.uuid4().hex[:12]}", label, box)
        self.groups[group.id] = group; return group

    def delete_entity(self, entity_id):
        if entity_id in self.entities:
            del self.entities[entity_id]
            self.connections = [c for c in self.connections if c['endpoints'][0]['entity_id'] != entity_id and c['endpoints'][1]['entity_id'] != entity_id]
            return True
        return False

    def delete_group(self, group_id):
        if group_id in self.groups: del self.groups[group_id]; return True
        return False

    def update_entity_position(self, entity_id, position):
        if entity_id in self.entities: self.entities[entity_id].position = [int(p) for p in position]

    def update_entity_box(self, entity_id, box):
        if entity_id in self.entities: self.entities[entity_id].box = [int(c) for c in box]
    
    def rename_entity(self, entity_id, new_label):
        if entity_id in self.entities: self.entities[entity_id].label = new_label; return True
        return False

    def rename_group(self, group_id, new_label):
        if group_id in self.groups: self.groups[group_id].label = new_label; return True
        return False

    def add_port(self, entity_id, label, direction, rel_position):
        entity = self.entities.get(entity_id)
        if not entity: return None
        port_id = f"port_{len(entity.ports)}"
        while port_id in entity.ports: port_id = f"port_{uuid.uuid4().hex[:4]}"
        port = Port(port_id, label, direction, [int(p) for p in rel_position])
        entity.ports[port_id] = port; return port

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
        conn = {"id": f"conn_{uuid.uuid4().hex[:12]}", "endpoints": [{"entity_id": entity_id1, "port_id": port_id1}, {"entity_id": entity_id2, "port_id": port_id2}], "label": ""}
        self.connections.append(conn); return True

    def delete_connection(self, connection_id):
        self.connections = [c for c in self.connections if c['id'] != connection_id]

    def update_connection_label(self, connection_id, new_label):
        for conn in self.connections:
            if conn['id'] == connection_id: conn['label'] = new_label; return True
        return False

    def save_to_json(self, output_path):
        data = {"diagram_info": {"schema_version": "3.2-WithGroups", "image_source": Path(self.image_path).name if self.image_path else "N/A"}, "entities": {eid: deepcopy(e.__dict__) for eid, e in self.entities.items()}, "connections": self.connections, "groups": {gid: g.__dict__ for gid, g in self.groups.items()}}
        for edata in data["entities"].values(): edata["ports"] = {pid: p.__dict__ for pid, p in edata["ports"].items()}
        try:
            with open(output_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e: print(f"[ERROR] Failed to save project JSON: {e}"); return False

    def load_from_json(self, image_path, project_path):
        self.clear(); self.image_path = image_path
        try:
            with open(project_path, 'r', encoding='utf-8') as f: data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return False
        for eid, edata in data.get("entities", {}).items():
            pos = edata.get('position', [0, 0])
            entity = Entity(eid, edata['label'], edata['type'], edata['box'], pos)
            for pid, pdata in edata.get("ports", {}).items():
                entity.ports[pid] = Port(pid, pdata['label'], pdata['direction'], pdata['position'])
            self.entities[eid] = entity
        self.connections = data.get("connections", [])
        for gid, gdata in data.get("groups", {}).items():
            self.groups[gid] = Group(gid, gdata['label'], gdata['box'])
        return True

    def load_from_raw_json(self, image_path, raw_json_path):
        self.clear(); self.image_path = image_path
        try:
            with open(raw_json_path, 'r', encoding='utf-8') as f: raw_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return False
        all_labels, conns = set(raw_data.keys()), set()
        for src, data in raw_data.items():
            for ctype in ['input', 'output', 'inout']:
                for conn in data.get('connections', {}).get(ctype, []):
                    if 'name' in conn:
                        tgt = conn['name']; all_labels.add(tgt)
                        if ctype == 'input': conns.add((tgt, src))
                        else: conns.add((src, tgt))
        id_map = {}
        for label in sorted(list(all_labels)):
            rbox = raw_data.get(label, {}).get("component_box"); box, pos = None, [0,0]
            if rbox: box, pos = [rbox[2] - rbox[0], rbox[3] - rbox[1]], [rbox[0], rbox[1]]
            etype = "Terminal" if box is None else label
            entity = self.add_entity(label, etype, box, pos); id_map[label] = entity.id
        ptrack, pmap = defaultdict(lambda: defaultdict(int)), {}
        for src_lbl, tgt_lbl in sorted(list(conns)):
            src_id, tgt_id = id_map[src_lbl], id_map[tgt_lbl]
            src_idx, tgt_idx = ptrack[src_lbl]['output'], ptrack[tgt_lbl]['input']
            src_plbl, tgt_plbl = f"out_{src_idx}", f"in_{tgt_idx}"
            if (src_lbl, 'out', src_idx) not in pmap: pmap[(src_lbl, 'out', src_idx)] = self.add_port(src_id, src_plbl, 'output', [0,0]).id
            if (tgt_lbl, 'in', tgt_idx) not in pmap: pmap[(tgt_lbl, 'in', tgt_idx)] = self.add_port(tgt_id, tgt_plbl, 'input', [0,0]).id
            self.create_connection((src_id, pmap[(src_lbl, 'out', src_idx)]), (tgt_id, pmap[(tgt_lbl, 'in', tgt_idx)]))
            ptrack[src_lbl]['output'] += 1; ptrack[tgt_lbl]['input'] += 1
        return True