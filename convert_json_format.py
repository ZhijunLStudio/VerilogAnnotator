#!/usr/bin/env python3
"""
JSON 格式转换脚本
将旧格式 JSON 转换为新格式

旧格式:
- "box": [x1, y1, x2, y2]
- "ports": [{"name": "...", "coord": [...]}]

新格式:
- "shape": {"type": "rect", "box": [x1, y1, x2, y2]}
- "parent": null
- "children": []
- "references": []
- "ports": {"name": {"coord": [...]}}
"""

import json
import sys
from pathlib import Path
from typing import Any


def convert_port_format(ports_data: list) -> dict:
    """将端口从列表格式转换为字典格式"""
    result = {}
    if isinstance(ports_data, list):
        for port in ports_data:
            if isinstance(port, dict):
                name = port.get("name") or port.get("id")
                coord = port.get("coord", [0, 0])
                if name:
                    result[name] = {"coord": coord}
    elif isinstance(ports_data, dict):
        # 已经是新格式
        result = ports_data
    return result


def convert_component_format(comp_data: dict) -> dict:
    """转换组件格式"""
    result = {
        "type": comp_data.get("type", "unknown"),
        "parent": comp_data.get("parent"),  # 保留已有的 parent
        "children": comp_data.get("children", []),  # 保留已有的 children
        "references": comp_data.get("references", []),  # 保留已有的 references
    }

    # 转换 shape
    if "shape" in comp_data:
        # 已经是新格式
        result["shape"] = comp_data["shape"]
    elif "box" in comp_data:
        # 旧格式：box -> shape
        box = comp_data["box"]
        result["shape"] = {
            "type": "rect",
            "box": box
        }
    else:
        # 默认
        result["shape"] = {
            "type": "rect",
            "box": [0, 0, 100, 100]
        }

    # 转换 ports
    ports_data = comp_data.get("ports", {})
    result["ports"] = convert_port_format(ports_data)

    # 移除 None 值
    return {k: v for k, v in result.items() if v is not None}


def convert_external_port_format(port_data: dict) -> dict:
    """转换外部端口格式"""
    return {
        "type": port_data.get("type", "terminal"),
        "coord": port_data.get("coord", [0, 0])
    }


def convert_connection_format(conn_data: dict) -> dict:
    """转换连接格式"""
    return {
        "nodes": conn_data.get("nodes", [])
    }


def convert_json_file(input_path: Path, output_path: Path):
    """转换单个 JSON 文件"""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load {input_path}: {e}")
        return False

    # 转换 components
    new_components = {}
    for comp_id, comp_data in data.get("components", {}).items():
        new_components[comp_id] = convert_component_format(comp_data)

    # 转换 external_ports
    new_external_ports = {}
    for port_id, port_data in data.get("external_ports", {}).items():
        new_external_ports[port_id] = convert_external_port_format(port_data)

    # 转换 connections
    new_connections = []
    for conn_data in data.get("connections", []):
        new_connections.append(convert_connection_format(conn_data))

    # 构建新格式
    new_data = {
        "components": new_components,
        "external_ports": new_external_ports,
        "connections": new_connections
    }

    # 保存
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save {output_path}: {e}")
        return False


def convert_folder(input_folder: str, output_folder: str):
    """转换整个文件夹"""
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    if not input_path.exists():
        print(f"[ERROR] Input folder does not exist: {input_folder}")
        return

    # 创建输出文件夹
    output_path.mkdir(parents=True, exist_ok=True)

    # 查找所有 JSON 文件
    json_files = list(input_path.glob("*.json"))

    if not json_files:
        print(f"[WARNING] No JSON files found in {input_folder}")
        return

    print(f"Found {len(json_files)} JSON files to convert")
    print("-" * 50)

    success_count = 0
    fail_count = 0

    for json_file in json_files:
        # 保持相对路径结构
        rel_path = json_file.relative_to(input_path)
        out_file = output_path / rel_path

        print(f"Converting: {rel_path} ... ", end="")

        if convert_json_file(json_file, out_file):
            print("✓")
            success_count += 1
        else:
            print("✗ FAILED")
            fail_count += 1

    print("-" * 50)
    print(f"Conversion complete: {success_count} success, {fail_count} failed")
    print(f"Output folder: {output_path.absolute()}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python convert_json_format.py <input_folder> <output_folder>")
        print("\nExample:")
        print("  python convert_json_format.py ./old_jsons ./new_jsons")
        sys.exit(1)

    input_folder = sys.argv[1]
    output_folder = sys.argv[2]

    convert_folder(input_folder, output_folder)


if __name__ == "__main__":
    main()
