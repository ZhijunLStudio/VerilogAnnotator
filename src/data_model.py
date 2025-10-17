# src/data_model.py
import json
import re
from pathlib import Path
from collections import defaultdict

class Port:
    def __init__(self, name, direction, component, position=None):
        self.name = name
        self.direction = direction
        self.component = component
        self.position = position
        self.net = None

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
        self.connections = [] # List of Port objects

class CircuitDiagram:
    def __init__(self):
        self.components = {}
        self.nets = {}
        self.image_path = None
        self.verilog_path = None
        self.metadata_path = None
        self.top_level_module = "top_level_system"
        print("[DEBUG] New CircuitDiagram object created.")

    def load_files(self, image_path, verilog_path, metadata_path):
        print(f"[DEBUG] Loading files: IMG='{image_path.name}', V='{verilog_path.name}', META='{metadata_path.name}'")
        self.image_path, self.verilog_path, self.metadata_path = image_path, verilog_path, metadata_path
        self.components.clear(); self.nets.clear()
        
        with open(metadata_path, 'r', encoding='utf-8') as f: meta = json.load(f)
        try:
            first_key = next(iter(meta.get("visual_metadata", {}))); self.top_level_module = first_key.split('.')[0]
        except StopIteration: pass

        for instance_path, data in meta.get("visual_metadata", {}).items():
            instance_name = instance_path.split('.')[-1]
            comp = Component(instance_name, "", data.get('label'), data.get('box'))
            for port_name, port_data in data.get("ports", {}).items():
                direction = 'input' if 'in' in port_name.lower() else 'output'
                port = Port(port_name, direction, comp, port_data.get('position'))
                comp.ports[port_name] = port
            self.components[instance_name] = comp
        
        with open(verilog_path, 'r', encoding='utf-8') as f: verilog_content = f.read()
        
        instance_pattern = re.compile(r"([\w\\]+)\s+([\w\\]+_(?:inst|port))\s*\((.*?)\);", re.DOTALL) # More robust regex
        port_conn_pattern = re.compile(r"\.(\w+)\s*\((.*?)\)")
        
        top_module_match = re.search(fr"module\s+{self.top_level_module}\s*;(.*?)endmodule", verilog_content, re.DOTALL)
        search_area = top_module_match.group(1) if top_module_match else verilog_content

        for match in instance_pattern.finditer(search_area):
            module_type, instance_name, connections_str = [s.strip() for s in match.groups()]
            
            if instance_name in self.components:
                comp = self.components[instance_name]; comp.module_type = module_type
                for port_match in port_conn_pattern.finditer(connections_str):
                    port_name, net_name = [s.strip() for s in port_match.groups()]
                    if port_name in comp.ports:
                        port = comp.ports[port_name]
                        if net_name not in self.nets: self.nets[net_name] = Net(net_name)
                        self.nets[net_name].connections.append(port); port.net = self.nets[net_name]
        
        print(f"[DEBUG] Loaded {len(self.components)} components and {len(self.nets)} nets.")
        return True

    def add_component(self, instance_name, module_type, box):
        if instance_name in self.components: return None
        print(f"[DEBUG] Adding component: {instance_name}")
        comp = Component(instance_name, module_type, instance_name, box)
        self.components[instance_name] = comp
        return comp

    def delete_component(self, instance_name):
        if instance_name not in self.components: return
        print(f"[DEBUG] Deleting component: {instance_name}")
        comp_to_delete = self.components[instance_name]
        for port in list(comp_to_delete.ports.values()):
            self.delete_port(instance_name, port.name, is_sub_call=True)
        del self.components[instance_name]

    def update_component_box(self, instance_name, new_box):
        if instance_name in self.components:
            self.components[instance_name].box = [round(c) for c in new_box]

    def update_port_position(self, instance_name, port_name, new_pos):
        if instance_name in self.components and port_name in self.components[instance_name].ports:
            self.components[instance_name].ports[port_name].position = [round(p, 2) for p in new_pos]

    def add_port(self, instance_name, direction):
        if instance_name not in self.components: return None
        comp = self.components[instance_name]; i = 0
        dir_prefix = 'in' if direction == 'input' else 'out'
        while f"{dir_prefix}_{i}" in comp.ports: i += 1
        port_name = f"{dir_prefix}_{i}"
        print(f"[DEBUG] Adding port '{port_name}' to '{instance_name}'")
        port = Port(port_name, direction, comp)
        comp.ports[port_name] = port
        return port
        
    def delete_port(self, instance_name, port_name, is_sub_call=False):
        comp = self.components.get(instance_name)
        if not comp or port_name not in comp.ports: return
        if not is_sub_call: print(f"[DEBUG] Deleting port '{port_name}' from '{instance_name}'")
        port_to_delete = comp.ports[port_name]
        if port_to_delete.net:
            net = port_to_delete.net
            if port_to_delete in net.connections: net.connections.remove(port_to_delete)
            if len(net.connections) < 2 and net.name in self.nets:
                print(f"[DEBUG] Deleting dangling net: {net.name}")
                del self.nets[net.name]
        del comp.ports[port_name]

    def save_files(self):
        if not self.metadata_path or not self.verilog_path:
            print("[WARN] Paths not set. Cannot save."); return False
        try:
            with open(self.verilog_path, 'w', encoding='utf-8') as f: f.write(self._generate_verilog())
            print(f"[INFO] Saved Verilog to {self.verilog_path.name}")
            meta_data = {"diagram_info": {"image_source": self.image_path.name, "verilog_source": self.verilog_path.name},
                         "visual_metadata": {f"{self.top_level_module}.{inst_name}": {
                             "label": comp.label, "box": comp.box, 
                             "ports": {p.name: {"position": p.position} for p in comp.ports.values() if p.position}
                         } for inst_name, comp in self.components.items()}, "net_metadata": {}}
            with open(self.metadata_path, 'w', encoding='utf-8') as f: json.dump(meta_data, f, indent=2)
            print(f"[INFO] Saved metadata to {self.metadata_path.name}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save files: {e}"); return False

    def _generate_verilog(self):
        module_definitions = defaultdict(lambda: defaultdict(list))
        for comp in self.components.values():
            if comp.module_type:
                for port in comp.ports.values():
                    if port.name not in module_definitions[comp.module_type][port.direction]:
                        module_definitions[comp.module_type][port.direction].append(port.name)
        output = []
        for module_type, ports_by_dir in sorted(module_definitions.items()):
            decls = [f"{d} wire {p}" for d in ['input', 'output'] for p in sorted(ports_by_dir.get(d, []))]
            output.append(f"module {module_type} (\n    " + ",\n    ".join(decls) + "\n);\nendmodule\n")
        output.append(f"module {self.top_level_module};\n")
        if self.nets:
            output.append("    " + ";\n    ".join([f"wire {n}" for n in sorted(self.nets.keys())]) + ";\n")
        for inst_name, comp in sorted(self.components.items()):
            if comp.module_type:
                conns = [f".{p.name}({p.net.name if p.net else ''})" for p in sorted(comp.ports.values(), key=lambda x:x.name)]
                output.append(f"    {comp.module_type} {inst_name} (\n        " + ",\n        ".join(conns) + "\n    );\n")
        output.append("endmodule\n")
        return "\n".join(output)