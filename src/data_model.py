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

    def load_files(self, image_path, verilog_path, metadata_path):
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
        instance_pattern = re.compile(r"([\w\\]+)\s+([\w\\]+_(?:inst|port))\s*\((.*?)\);", re.DOTALL)
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
        return True

    def _get_unique_name(self, base, existing_keys):
        i = 0
        while f"{base}_{i}" in existing_keys: i += 1
        return f"{base}_{i}"

    # --- FIX: Restore the 'label' parameter to the method signature ---
    def add_component(self, instance_name, module_type, label, box):
        if instance_name in self.components: return None
        # Ensure box coordinates are integers if box exists
        int_box = [int(c) for c in box] if box else None
        comp = Component(instance_name, module_type, label, int_box)
        self.components[instance_name] = comp
        return comp

    def delete_component(self, instance_name):
        if instance_name not in self.components: return
        comp_to_delete = self.components[instance_name]
        for port in list(comp_to_delete.ports.values()):
            self.delete_port(instance_name, port.name, is_sub_call=True)
        del self.components[instance_name]

    def update_component_box(self, instance_name, new_box):
        if instance_name in self.components:
            self.components[instance_name].box = [int(c) for c in new_box]

    def update_port_position(self, instance_name, port_name, new_pos):
        comp = self.components.get(instance_name)
        if comp and port_name in comp.ports:
            port = comp.ports[port_name]
            port.position = [int(p) for p in new_pos]
            port.was_manually_positioned = True 

    def add_port(self, instance_name, direction, position=None):
        comp = self.components.get(instance_name)
        if instance_name is None:
            base_name = "term"
            instance_name = self._get_unique_name(base_name + "_port", self.components)
            # --- FIX: The call now matches the corrected signature ---
            comp = self.add_component(instance_name, "Terminal", base_name, None)
            
        if not comp: return None
        dir_prefix = 'in' if direction == 'input' else 'out'
        port_name = self._get_unique_name(dir_prefix, comp.ports)
        port = Port(port_name, direction, comp, position)
        if position:
            port.position = [int(p) for p in position]
            port.was_manually_positioned = True
        comp.ports[port_name] = port
        return port

    def delete_port(self, instance_name, port_name, is_sub_call=False):
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

    # ... The rest of the methods (rename, split, merge, create_connection, save, generate_verilog) are correct and unchanged ...
    def rename_port(self, instance_name, old_name, new_name):
        comp = self.components.get(instance_name)
        if not comp or old_name not in comp.ports: return False
        if new_name in comp.ports: return False 
        port = comp.ports.pop(old_name)
        port.name = new_name
        comp.ports[new_name] = port
        return True

    def split_port(self, instance_name, port_name):
        comp = self.components.get(instance_name)
        if not comp or port_name not in comp.ports: return False
        original_port = comp.ports[port_name]
        name1 = self._get_unique_name(original_port.name, comp.ports)
        port1 = Port(name1, original_port.direction, comp, original_port.position)
        if port1.position: port1.position = [port1.position[0] - 5, port1.position[1] - 5]
        port1.was_manually_positioned = original_port.was_manually_positioned
        comp.ports[name1] = port1
        name2 = self._get_unique_name(original_port.name, comp.ports)
        port2 = Port(name2, original_port.direction, comp, original_port.position)
        if port2.position: port2.position = [port2.position[0] + 5, port2.position[1] + 5]
        port2.was_manually_positioned = original_port.was_manually_positioned
        comp.ports[name2] = port2
        if original_port.net:
            net = original_port.net
            net.connections.remove(original_port)
            net.connections.append(port1)
            net.connections.append(port2)
            port1.net = net
            port2.net = net
        del comp.ports[port_name]
        return True

    def merge_ports(self, key1, key2):
        inst1, name1 = key1; inst2, name2 = key2
        comp1 = self.components.get(inst1); comp2 = self.components.get(inst2)
        if not comp1 or not comp2 or name1 not in comp1.ports or name2 not in comp2.ports: return False
        port1 = comp1.ports[name1]; port2 = comp2.ports[name2]
        if port1.component != port2.component or port1.direction != port2.direction: return False
        net1, net2 = port1.net, port2.net
        if net2: net2.connections.remove(port2)
        if net1 and net2 and net1 != net2:
            for p in list(net2.connections):
                p.net = net1
                net1.connections.append(p)
            if net2.name in self.nets: del self.nets[net2.name]
        elif net2 and not net1:
            port1.net = net2
            net2.connections.append(port1)
        del comp2.ports[name2]
        return True
        
    def create_connection(self, key1, key2):
        inst1, name1 = key1; inst2, name2 = key2
        comp1 = self.components.get(inst1); comp2 = self.components.get(inst2)
        if not comp1 or not comp2 or name1 not in comp1.ports or name2 not in comp2.ports: return False
        port1 = comp1.ports[name1]; port2 = comp2.ports[name2]
        net1, net2 = port1.net, port2.net
        if net1 and net1 == net2: return True
        if not net1 and not net2:
            new_net_name = self._get_unique_name("net", self.nets)
            new_net = Net(new_net_name)
            self.nets[new_net_name] = new_net
            new_net.connections.extend([port1, port2])
            port1.net = new_net
            port2.net = new_net
        elif net1 and not net2:
            net1.connections.append(port2); port2.net = net1
        elif not net1 and net2:
            net2.connections.append(port1); port1.net = net2
        elif net1 and net2 and net1 != net2:
            for p in list(net2.connections):
                p.net = net1
                net1.connections.append(p)
            if net2.name in self.nets: del self.nets[net2.name]
        return True

    def save_files(self):
        if not self.metadata_path or not self.verilog_path: return False
        try:
            with open(self.verilog_path, 'w', encoding='utf-8') as f: f.write(self._generate_verilog())
            meta_data = {"diagram_info": {"image_source": self.image_path.name, "verilog_source": self.verilog_path.name}, "visual_metadata": {}}
            for inst_name, comp in self.components.items():
                ports_data = { p.name: {"position": p.position} for p in comp.ports.values() if p.was_manually_positioned and p.position is not None }
                meta_data["visual_metadata"][f"{self.top_level_module}.{inst_name}"] = {"label": comp.label, "box": comp.box, "ports": ports_data}
            with open(self.metadata_path, 'w', encoding='utf-8') as f: json.dump(meta_data, f, indent=2, ensure_ascii=False)
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
        if self.nets: output.append("    " + ";\n    ".join([f"wire {n}" for n in sorted(self.nets.keys())]) + ";\n")
        for inst_name, comp in sorted(self.components.items()):
            if comp.module_type:
                conns = [f".{p.name}({p.net.name if p.net else ''})" for p in sorted(comp.ports.values(), key=lambda x:x.name)]
                output.append(f"    {comp.module_type} {inst_name} (\n        " + ",\n        ".join(conns) + "\n    );\n")
        output.append("endmodule\n")
        return "\n".join(output)