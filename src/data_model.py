# src/data_model.py
import json
import re
from pathlib import Path
from collections import defaultdict

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

        try:
            first_key = next(iter(meta.get("visual_metadata", {}))); self.top_level_module = first_key.split('.')[0]
        except StopIteration: pass
        
        self.connection_labels = meta.get("connection_labels", {})

        for instance_path, data in meta.get("visual_metadata", {}).items():
            instance_name = instance_path.split('.')[-1]
            comp = Component(instance_name, "", data.get('label'), data.get('box'))
            for port_name, port_data in data.get("ports", {}).items():
                direction = 'input' if 'in' in port_name.lower() else 'output'
                port = Port(port_name, direction, comp, port_data.get('position'), port_data.get('label'))
                comp.ports[port_name] = port
            self.components[instance_name] = comp
        
        try:
            with open(verilog_path, 'r', encoding='utf-8') as f: verilog_content = f.read()
        except FileNotFoundError: return True

        instance_pattern = re.compile(r"([\w\\]+)\s+([\w\\]+)\s*\((.*?)\);", re.DOTALL)
        port_conn_pattern = re.compile(r"\s*\.(\w+)\s*\(([\w\d_\[\]\s:]*?)\)")
        top_module_match = re.search(fr"module\s+{self.top_level_module}\s*\(.*?\);(.*?)endmodule", verilog_content, re.DOTALL)
        search_area = top_module_match.group(1) if top_module_match else verilog_content
        
        for match in instance_pattern.finditer(search_area):
            module_type, instance_name, connections_str = [s.strip() for s in match.groups()]
            if instance_name in self.components:
                comp = self.components[instance_name]; comp.module_type = module_type
                for port_match in port_conn_pattern.finditer(connections_str):
                    port_name, net_name = [s.strip() for s in port_match.groups()]
                    if not net_name: continue
                    if port_name in comp.ports:
                        port = comp.ports[port_name]
                        if net_name not in self.nets: self.nets[net_name] = Net(net_name)
                        self.nets[net_name].connections.append(port); port.net = self.nets[net_name]
        return True

    def _get_unique_name(self, base, existing_keys):
        i = 0; name = base
        while name in existing_keys:
            name = f"{base}_{i}"; i += 1
        return name

    def add_component(self, instance_name, module_type, label, box):
        if instance_name in self.components: return None
        int_box = [int(c) for c in box] if box else None
        comp = Component(instance_name, module_type, label, int_box)
        self.components[instance_name] = comp
        return comp

    def delete_component(self, instance_name):
        if instance_name not in self.components: return
        comp_to_delete = self.components[instance_name]
        for port in list(comp_to_delete.ports.values()):
            self.delete_port(instance_name, port.name)
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

    def add_port(self, instance_name, direction, position=None, label=None):
        comp = self.components.get(instance_name)
        base_name = label.replace(" ","_").replace("[","").replace("]","").replace(":","") if label else ("in" if direction == "input" else "out")
        
        if instance_name is None:
            instance_name = self._get_unique_name(base_name + "_inst", self.components)
            module_type = "OutputPort" if direction == "input" else "InputPort"
            comp = self.add_component(instance_name, module_type, label, None)
        else:
            comp = self.components.get(instance_name)
            
        if not comp: return None
        
        port_name = self._get_unique_name(direction, comp.ports)
        port = Port(port_name, direction, comp, position, label)
        if position:
            port.position = [int(p) for p in position]
            port.was_manually_positioned = True
        comp.ports[port_name] = port
        return port

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
        if comp and port_name in comp.ports:
            comp.ports[port_name].label = new_label
            return True
        return False

    def split_port(self, instance_name, port_name):
        comp = self.components.get(instance_name)
        if not comp or port_name not in comp.ports: return False
        original_port = comp.ports[port_name]
        name1 = self._get_unique_name(original_port.label, comp.ports)
        port1 = Port(name1, original_port.direction, comp, original_port.position, original_port.label)
        if port1.position: port1.position = [port1.position[0] - 5, port1.position[1] - 5]
        port1.was_manually_positioned = original_port.was_manually_positioned
        comp.ports[name1] = port1
        name2 = self._get_unique_name(original_port.label, comp.ports)
        port2 = Port(name2, original_port.direction, comp, original_port.position, original_port.label)
        if port2.position: port2.position = [port2.position[0] + 5, port2.position[1] + 5]
        port2.was_manually_positioned = original_port.was_manually_positioned
        comp.ports[name2] = port2
        if original_port.net:
            net = original_port.net
            net.connections.remove(original_port)
            net.connections.append(port1); net.connections.append(port2)
            port1.net = net; port2.net = net
        del comp.ports[port_name]
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
                for p in list(net2.connections):
                    p.net = net1; net1.connections.append(p)
                if net2.name in self.nets: del self.nets[net2.name]
            elif not net1:
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
            net_base = f"net_{port1.label}_{port2.label}".replace("[","").replace("]","").replace(":","")
            new_net_name = self._get_unique_name(net_base, self.nets)
            new_net = Net(new_net_name)
            self.nets[new_net_name] = new_net
            new_net.connections.extend([port1, port2])
            port1.net = new_net; port2.net = new_net
        elif net1 and not net2:
            net1.connections.append(port2); port2.net = net1
        elif not net1 and net2:
            net2.connections.append(port1); port1.net = net2
        elif net1 and net2 and net1 != net2:
            for p in list(net2.connections):
                p.net = net1; net1.connections.append(p)
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
                ports_data = { p.name: {"position": p.position, "label": p.label} for p in comp.ports.values() if p.position is not None }
                meta_data["visual_metadata"][f"{self.top_level_module}.{inst_name}"] = {"label": comp.label, "box": comp.box, "ports": ports_data}
            with open(self.metadata_path, 'w', encoding='utf-8') as f: json.dump(meta_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save files: {e}"); return False

    def _generate_verilog(self):
        module_definitions = defaultdict(lambda: defaultdict(list))
        
        # Define modules for all components that have a module type
        for comp in self.components.values():
            if comp.module_type:
                for port in comp.ports.values():
                    if port.name not in module_definitions[comp.module_type][port.direction]:
                        module_definitions[comp.module_type][port.direction].append(port.name)
        
        output = []
        for module_type, ports_by_dir in sorted(module_definitions.items()):
            all_ports = sorted(ports_by_dir.get('input', []) + ports_by_dir.get('output', []))
            # Handle modules with no ports
            if not all_ports:
                output.append(f"module {module_type} ();")
            else:
                output.append(f"module {module_type} ({', '.join(all_ports)});")
            
            decls = []
            if ports_by_dir.get('input'): decls.append(f"    input {', '.join(sorted(ports_by_dir['input']))};")
            if ports_by_dir.get('output'): decls.append(f"    output {', '.join(sorted(ports_by_dir['output']))};")
            if decls: output.append('\n'.join(decls))
            output.append("endmodule\n")

        output.append(f"module {self.top_level_module};")
        if self.nets: output.append("\n    wire " + ", ".join(sorted(self.nets.keys())) + ";\n")
        
        for inst_name, comp in sorted(self.components.items()):
            if comp.module_type:
                conns = [f".{p.name}({p.net.name if p.net else ''})" for p in sorted(comp.ports.values(), key=lambda x:x.name)]
                output.append(f"    {comp.module_type} {inst_name} (\n        " + ",\n        ".join(conns) + "\n    );")
        
        output.append("\nendmodule\n")
        return "\n".join(output)