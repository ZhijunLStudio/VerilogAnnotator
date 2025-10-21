import json
import re
from pathlib import Path
from collections import defaultdict

def sanitize_for_verilog(name):
    if not isinstance(name, str): name = str(name)
    s = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if s and s[0].isdigit(): s = 'p_' + s
    keywords = {'module', 'endmodule', 'input', 'output', 'wire', 'reg', 'assign', 'always', 'if', 'else', 'begin', 'end'}
    if s in keywords: s += '_'
    if not s: return "unnamed_port"
    return s

class Port:
    def __init__(self, name, direction, component, position=None, label=None):
        self.name = name
        self.direction = direction
        self.component = component
        self.position = position 
        self.label = label if label else name
        self.net = None
        self.was_manually_positioned = position is not None

class Component:
    def __init__(self, instance_name, module_type, label, box):
        self.instance_name = instance_name
        self.module_type = module_type
        self.label = label
        self.box = box
        self.ports = {}

class Net:
    def __init__(self, name):
        self.name = name
        self.connections = [] 

# --- NEW: Data model for a group ---
class Group:
    def __init__(self, name, label, points):
        self.name = name
        self.label = label
        self.points = points # List of [x, y] coordinates

class CircuitDiagram:
    def __init__(self):
        self.components = {}
        self.nets = {}
        self.groups = {} # --- NEW: Dictionary to store groups
        self.image_path = None
        self.top_level_module = "top_level_system"
        self.connection_labels = {}
        self.module_definitions = defaultdict(lambda: {'ports': {}})

    def load_from_raw_json(self, image_path, raw_json_path):
        self.image_path = image_path
        self.components.clear(); self.nets.clear(); self.connection_labels.clear()
        self.module_definitions.clear(); self.groups.clear()

        try:
            with open(raw_json_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Could not load or parse raw JSON file {raw_json_path}: {e}")
            return False

        defined_components = set(raw_data.keys())
        all_entities = set(defined_components)
        directed_connections = set()

        for source_name, data in raw_data.items():
            connections = data.get('connections', {})
            for conn in connections.get('input', []):
                target_name = conn.get('name')
                if target_name:
                    directed_connections.add((target_name, source_name))
                    all_entities.add(target_name)
            for conn in connections.get('output', []):
                target_name = conn.get('name')
                if target_name:
                    directed_connections.add((source_name, target_name))
                    all_entities.add(target_name)
            for conn in connections.get('inout', []):
                target_name = conn.get('name')
                if target_name:
                    directed_connections.add((source_name, target_name))
                    directed_connections.add((target_name, source_name))
                    all_entities.add(target_name)
        
        terminals = all_entities - defined_components
        entity_ports = {name: defaultdict(list) for name in all_entities}
        
        for source, target in sorted(list(directed_connections)):
            sane_source = sanitize_for_verilog(source)
            sane_target = sanitize_for_verilog(target)
            
            out_port_idx = len(entity_ports[source]['output'])
            in_port_idx = len(entity_ports[target]['input'])
            
            net_name = self._get_unique_name(f"net_{sane_source}_to_{sane_target}", self.nets)
            net = Net(net_name)
            self.nets[net_name] = net

            source_port_name = f"out_{out_port_idx}"
            target_port_name = f"in_{in_port_idx}"
            
            entity_ports[source]['output'].append({'name': source_port_name, 'net': net})
            entity_ports[target]['input'].append({'name': target_port_name, 'net': net})

        for entity_name in sorted(list(all_entities)):
            is_terminal = entity_name in terminals
            is_input_terminal = is_terminal and entity_ports[entity_name]['output'] and not entity_ports[entity_name]['input']
            is_output_terminal = is_terminal and entity_ports[entity_name]['input'] and not entity_ports[entity_name]['output']
            
            sane_name = sanitize_for_verilog(entity_name)
            module_type, instance_name = "", ""

            if is_input_terminal:
                module_type, instance_name = "InputPort", f"{sane_name}_port"
            elif is_output_terminal:
                module_type, instance_name = "OutputPort", f"{sane_name}_port"
            else:
                module_type, instance_name = sane_name, f"{sane_name}_inst"

            comp_box = raw_data.get(entity_name, {}).get("component_box")
            comp = Component(instance_name, module_type, entity_name, comp_box)
            self.components[instance_name] = comp

            for port_info in entity_ports[entity_name]['input']:
                p = Port(port_info['name'], 'input', comp, label=port_info['name'])
                p.net = port_info['net']; p.net.connections.append(p)
                comp.ports[p.name] = p
                self.module_definitions[module_type]['ports'][p.name] = 'input'

            for port_info in entity_ports[entity_name]['output']:
                p = Port(port_info['name'], 'output', comp, label=port_info['name'])
                p.net = port_info['net']; p.net.connections.append(p)
                comp.ports[p.name] = p
                self.module_definitions[module_type]['ports'][p.name] = 'output'
        
        self.module_definitions['InputPort']['ports']['out_0'] = 'output'
        self.module_definitions['OutputPort']['ports']['in_0'] = 'input'

        return True

    def _get_unique_name(self, base, existing_keys):
        sanitized_base = sanitize_for_verilog(base)
        if sanitized_base not in existing_keys: return sanitized_base
        i = 0; name = f"{sanitized_base}_{i}"
        while name in existing_keys:
            i += 1; name = f"{sanitized_base}_{i}"
        return name

    def add_group(self, label, points):
        name = self._get_unique_name(label, self.groups)
        group = Group(name, label, points)
        self.groups[name] = group
        return group

    def delete_group(self, group_name):
        if group_name in self.groups:
            del self.groups[group_name]

    def rename_group_label(self, group_name, new_label):
        if group_name in self.groups:
            self.groups[group_name].label = new_label
            return True
        return False

    def update_group_polygon(self, group_name, new_points):
        if group_name in self.groups:
            self.groups[group_name].points = new_points
            return True
        return False

    def add_component(self, instance_name, module_type, label, box):
        sane_instance_name = self._get_unique_name(instance_name, self.components)
        sane_module_type = sanitize_for_verilog(module_type)
        comp = Component(sane_instance_name, sane_module_type, label, [int(c) for c in box] if box else None)
        self.components[sane_instance_name] = comp
        _ = self.module_definitions[sane_module_type]
        return comp

    def add_port(self, instance_name, direction, position=None, label=None):
        if not label: return None
        sane_label = sanitize_for_verilog(label)
        
        target_comp = None
        if instance_name:
            target_comp = self.components.get(instance_name)
        else:
            inst_name_base = sane_label + "_port"
            instance_name = self._get_unique_name(inst_name_base, self.components)
            module_type = "InputPort" if direction == "input" else "OutputPort"
            target_comp = self.add_component(instance_name, module_type, label, None)
        
        if not target_comp: return None

        port_name, final_direction = "", direction
        if target_comp.module_type == "InputPort":
            final_direction, port_name = 'output', 'out_0'
        elif target_comp.module_type == "OutputPort":
            final_direction, port_name = 'input', 'in_0'
        else:
            port_name = self._get_unique_name(sane_label, target_comp.ports)
        
        if port_name in target_comp.ports:
            return None

        port = Port(port_name, final_direction, target_comp, position, label)
        if position:
            port.position = [int(p) for p in position]
            port.was_manually_positioned = True
        target_comp.ports[port_name] = port
        
        module_type = target_comp.module_type
        if port_name not in self.module_definitions[module_type]['ports']:
            self.module_definitions[module_type]['ports'][port_name] = final_direction
        return port
    
    def save_to_unified_json(self, output_path):
        if not output_path: return False
        
        modules_block = {name: {"ports": [{"name": pn, "direction": d} for pn, d in sorted(defn['ports'].items())]} for name, defn in sorted(self.module_definitions.items())}
        
        instances_block = {}
        for inst_name, comp in sorted(self.components.items()):
            ports_metadata = { p.name: {"position": p.position} for p in comp.ports.values() if p.was_manually_positioned }
            instances_block[inst_name] = {
                "module_type": comp.module_type,
                "visual_metadata": {"label": comp.label, "box": comp.box, "ports": ports_metadata}
            }

        nets_block = {net_name: {"connections": [{"instance": p.component.instance_name, "port": p.name} for p in net.connections]} for net_name, net in sorted(self.nets.items())}

        # --- NEW: Serialize groups ---
        groups_block = {name: {"label": group.label, "points": group.points} for name, group in sorted(self.groups.items())}

        unified_json = {
            "diagram_info": {
                "image_source": self.image_path.name if self.image_path else "N/A",
                "schema_version": "1.2-UnifiedWithGroups"
            },
            "modules": modules_block,
            "design": {
                "top_module_name": self.top_level_module,
                "instances": instances_block,
                "nets": nets_block,
                "groups": groups_block, # --- NEW ---
                "connection_labels": self.connection_labels
            }
        }

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(unified_json, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save unified JSON: {e}")
            return False

    # ... (other methods like delete_port, rename_port_label, etc. remain the same) ...
    def delete_port(self, instance_name, port_name):
        comp = self.components.get(instance_name)
        if not comp or port_name not in comp.ports: return
        port_to_delete = comp.ports[port_name]
        if port_to_delete.net:
            net = port_to_delete.net
            if port_to_delete in net.connections: net.connections.remove(port_to_delete)
            if len(net.connections) < 2:
                for p in net.connections: p.net = None
                if net.name in self.nets: del self.nets[net.name]
        del comp.ports[port_name]
    def rename_port_label(self, instance_name, port_name, new_label):
        comp = self.components.get(instance_name)
        if not (comp and port_name in comp.ports): return False
        port = comp.ports[port_name]
        port.label = new_label
        if comp.module_type in ("InputPort", "OutputPort"):
            comp.label = new_label
            new_inst_name = self._get_unique_name(new_label + "_port", {k:v for k,v in self.components.items() if k != instance_name})
            if new_inst_name != instance_name:
                self.components[new_inst_name] = self.components.pop(instance_name)
                comp.instance_name = new_inst_name
        return True
    def update_component_box(self, instance_name, new_box):
        if instance_name in self.components: self.components[instance_name].box = [int(c) for c in new_box]
    def update_port_position(self, instance_name, port_name, new_pos):
        comp = self.components.get(instance_name)
        if comp and port_name in comp.ports:
            port = comp.ports[port_name]
            port.position = [int(p) for p in new_pos]
            port.was_manually_positioned = True
    def delete_component(self, instance_name):
        if instance_name not in self.components: return
        comp_to_delete = self.components[instance_name]
        for port in list(comp_to_delete.ports.values()): self.delete_port(instance_name, port.name)
        del self.components[instance_name]
    def merge_ports(self, key1, key2):
        inst1, name1 = key1; inst2, name2 = key2
        if inst1 != inst2: return False
        comp = self.components.get(inst1)
        if not comp or name1 not in comp.ports or name2 not in comp.ports: return False
        port1 = comp.ports[name1]; port2 = comp.ports[name2]
        if port1.direction != port2.direction: return False
        net1, net2 = port1.net, port2.net
        if net2:
            if port2 in net2.connections: net2.connections.remove(port2)
            if net1 and net1 != net2:
                for p in list(net2.connections): p.net = net1; net1.connections.append(p)
                if net2.name in self.nets: del self.nets[net2.name]
            elif not net1 and net2.connections:
                port1.net = net2; net2.connections.append(port1)
        del comp.ports[name2]
        return True
    def create_connection(self, key1, key2):
        inst1, name1 = key1; inst2, name2 = key2
        comp1 = self.components.get(inst1); comp2 = self.components.get(inst2)
        if not comp1 or not comp2 or name1 not in comp1.ports or name2 not in comp2.ports: return False
        port1 = comp1.ports[name1]; port2 = comp2.ports[name2]
        net1, net2 = port1.net, port2.net
        if net1 and net1 == net2: return True
        if not net1 and not net2:
            net_base = f"net"
            new_net_name = self._get_unique_name(net_base, self.nets)
            new_net = Net(new_net_name); self.nets[new_net_name] = new_net
            new_net.connections.extend([port1, port2]); port1.net = new_net; port2.net = new_net
        elif net1 and not net2: net1.connections.append(port2); port2.net = net1
        elif not net1 and net2: net2.connections.append(port1); port1.net = net2
        elif net1 and net2 and net1 != net2:
            if len(net1.connections) < len(net2.connections): net1, net2 = net2, net1
            for p in list(net2.connections): p.net = net1; net1.connections.append(p)
            if net2.name in self.nets: del self.nets[net2.name]
        return True
    def set_connection_label(self, key1, key2, text):
        inst1, name1 = key1; inst2, name2 = key2
        key_tuple = tuple(sorted((f"{inst1}.{name1}", f"{inst2}.{name2}")))
        label_key = "--".join(key_tuple)
        if text: self.connection_labels[label_key] = {"text": text}
        elif label_key in self.connection_labels: del self.connection_labels[label_key]
    def split_port(self, instance_name, port_name):
        print(f"Functionality not implemented: Split port {instance_name}.{port_name}")
        return False