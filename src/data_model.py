# src/data_model.py
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

class CircuitDiagram:
    def __init__(self):
        self.components = {}
        self.nets = {}
        self.image_path = None
        self.verilog_path = None
        self.metadata_path = None
        self.top_level_module = "top_level_system"
        self.connection_labels = {}

    def load_files(self, image_path, verilog_path, metadata_path):
        self.image_path, self.verilog_path, self.metadata_path = image_path, verilog_path, metadata_path
        self.components.clear(); self.nets.clear(); self.connection_labels.clear()
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f: meta = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): meta = {}

        self.connection_labels = meta.get("connection_labels", {})

        for instance_path, data in meta.get("visual_metadata", {}).items():
            instance_name = instance_path.split('.')[-1]
            label = data.get("label")
            comp = Component(instance_name, None, label, data.get('box'))
            
            for port_name, port_data in data.get("ports", {}).items():
                sane_port_name = sanitize_for_verilog(port_name)
                direction = 'output' if 'out' in sane_port_name.lower() else 'input'
                port = Port(sane_port_name, direction, comp, port_data.get('position'), port_data.get('label'))
                comp.ports[sane_port_name] = port
            self.components[instance_name] = comp
        
        try:
            with open(verilog_path, 'r', encoding='utf-8') as f: verilog_content = f.read()
        except FileNotFoundError: return True

        port_directions = defaultdict(dict)
        module_pattern = re.compile(r"module\s+([\w\\]+)\s*(#\s*\(.*?\))?\s*(\(.*?\))?\s*;", re.DOTALL)
        declaration_pattern = re.compile(r"\s*(input|output|inout)\s+([^;]+);", re.DOTALL)
        endmodule_pattern = re.compile(r"\bendmodule\b")

        last_pos = 0
        while True:
            match = re.search(r"\bmodule\s+([\w\\]+)", verilog_content[last_pos:])
            if not match: break
            
            module_name = match.group(1)
            start_pos = last_pos + match.end()
            
            end_match = endmodule_pattern.search(verilog_content, start_pos)
            if not end_match: break
            
            module_body = verilog_content[start_pos:end_match.start()]
            last_pos = end_match.end()

            for dir_match in declaration_pattern.finditer(module_body):
                direction, port_list_str = dir_match.groups()
                port_list_str = re.sub(r'\[.*?\]', '', port_list_str)
                for port_name in re.split(r',\s*', port_list_str.strip()):
                    if port_name:
                        port_directions[module_name][port_name.strip()] = direction

        instance_pattern = re.compile(r"([\w\\]+)\s+([\w\\]+)\s*\((.*?)\);", re.DOTALL)
        port_conn_pattern = re.compile(r"\s*\.([\w\\]+)\s*\(([\w\d_\[\]\s:]*?)\)")
        top_module_match = re.search(fr"module\s+{self.top_level_module}\s*\(.*?\);(.*?)endmodule", verilog_content, re.DOTALL)
        search_area = top_module_match.group(1) if top_module_match else verilog_content
        
        for match in instance_pattern.finditer(search_area):
            module_type, instance_name, connections_str = [s.strip() for s in match.groups()]
            if instance_name in self.components:
                comp = self.components[instance_name]
                comp.module_type = module_type
                
                for port_name, port in comp.ports.items():
                    if port_name in port_directions[module_type]:
                        port.direction = port_directions[module_type][port_name]
                
                for port_match in port_conn_pattern.finditer(connections_str):
                    port_name, net_name = [s.strip() for s in port_match.groups()]
                    if not net_name: continue
                    
                    if port_name in comp.ports:
                        port = comp.ports[port_name]
                        if net_name not in self.nets:
                            self.nets[net_name] = Net(net_name)
                        net = self.nets[net_name]
                        if port not in net.connections:
                            net.connections.append(port)
                        port.net = net
        return True

    def _get_unique_name(self, base, existing_keys):
        sanitized_base = sanitize_for_verilog(base)
        if sanitized_base not in existing_keys: return sanitized_base
        i = 0; name = f"{sanitized_base}_{i}"
        while name in existing_keys:
            i += 1; name = f"{sanitized_base}_{i}"
        return name

    def add_component(self, instance_name, module_type, label, box):
        sane_instance_name = self._get_unique_name(instance_name, self.components)
        sane_module_type = sanitize_for_verilog(module_type)
        comp = Component(sane_instance_name, sane_module_type, label, [int(c) for c in box] if box else None)
        self.components[sane_instance_name] = comp
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

        port_name = self._get_unique_name(sane_label, target_comp.ports)
        
        if target_comp.module_type == "InputPort": final_direction = 'output'
        elif target_comp.module_type == "OutputPort": final_direction = 'input'
        else: final_direction = direction

        port = Port(port_name, final_direction, target_comp, position, label)
        if position:
            port.position = [int(p) for p in position]
            port.was_manually_positioned = True
        target_comp.ports[port_name] = port
        return port
    
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
            new_port_name = self._get_unique_name(sanitize_for_verilog(new_label), {p:v for p,v in comp.ports.items() if p != port_name})
            port.name = new_port_name
            comp.ports[new_port_name] = comp.ports.pop(port_name)
            new_inst_name = self._get_unique_name(new_label + "_port", {k:v for k,v in self.components.items() if k != instance_name})
            if new_inst_name != instance_name:
                self.components[new_inst_name] = self.components.pop(instance_name)
                comp.instance_name = new_inst_name
        return True
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
        
        # MODIFIED: CRITICAL FIX for the UnboundLocalError
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

    def save_files(self):
        if not self.metadata_path or not self.verilog_path: return False
        try:
            with open(self.verilog_path, 'w', encoding='utf-8') as f: f.write(self._generate_verilog())
            meta_data = {
                "diagram_info": {"image_source": self.image_path.name, "verilog_source": self.verilog_path.name}, 
                "visual_metadata": {},
                "connection_labels": self.connection_labels
            }
            for inst_name, comp in self.components.items():
                ports_data = { p.name: {"position": p.position, "label": p.label} for p in comp.ports.values() if p.was_manually_positioned }
                if ports_data or comp.box:
                     meta_data["visual_metadata"][f"{self.top_level_module}.{inst_name}"] = {"label": comp.label, "box": comp.box, "ports": ports_data}
            with open(self.metadata_path, 'w', encoding='utf-8') as f: json.dump(meta_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save files: {e}"); return False

    def _generate_verilog(self):
        output = []
        module_definitions = defaultdict(lambda: defaultdict(list))
        
        for comp in self.components.values():
            if comp.module_type:
                for port in comp.ports.values():
                    port_name = sanitize_for_verilog(port.name)
                    if port_name not in module_definitions[comp.module_type][port.direction]:
                        module_definitions[comp.module_type][port.direction].append(port_name)

        for module_type, ports_by_dir in sorted(module_definitions.items()):
            all_ports = sorted(ports_by_dir.get('input', []) + ports_by_dir.get('output', []))
            port_list_str = f"({', '.join(all_ports)})" if all_ports else ""
            output.append(f"module {module_type} {port_list_str};")
            
            if ports_by_dir.get('input'):
                output.append(f"    input {', '.join(sorted(ports_by_dir['input']))};")
            if ports_by_dir.get('output'):
                output.append(f"    output {', '.join(sorted(ports_by_dir['output']))};")
            output.append("endmodule\n")

        output.append(f"module {self.top_level_module};")
        if self.nets: output.append("\n    wire " + ", ".join(sorted(self.nets.keys())) + ";\n")
        
        for inst_name, comp in sorted(self.components.items()):
            if not comp.module_type: continue

            conns = [f".{p.name}({p.net.name if p.net else ''})" for p in sorted(comp.ports.values(), key=lambda x:x.name)]
            if conns:
                output.append(f"    {comp.module_type} {inst_name} (\n        " + ",\n        ".join(conns) + "\n    );")
        
        output.append("\nendmodule\n")
        return "\n".join(output)