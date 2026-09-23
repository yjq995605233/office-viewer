#!/usr/bin/env python3
"""Convert ReplicaPano office2's complete colored PLY into a lossless GLB preview.

Requires numpy and plyfile. No decimation or fitted object proxies are used.
Quads are triangulated; geometric shell regions allow reversible cutaway views.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from plyfile import PlyData


def export(source, destination):
    ply = PlyData.read(source)
    vertices = ply['vertex']
    positions = np.column_stack([vertices[k] for k in ('x', 'y', 'z')])
    normals = np.column_stack([vertices[k] for k in ('nx', 'ny', 'nz')])
    colors = np.column_stack([vertices[k] for k in ('red', 'green', 'blue')]) / 255.0
    polygons = ply['face']['vertex_indices']
    if not all(len(face) == 4 for face in polygons):
        raise ValueError('This exporter expects the office2 quad mesh')
    quads = np.stack(polygons)
    if quads.min() < 0 or quads.max() >= len(positions):
        raise ValueError('Invalid vertex index')
    if not np.isfinite(positions).all() or not np.isfinite(normals).all():
        raise ValueError('Non-finite mesh attributes')
    # Assign whole original quads to disjoint regions. These are display regions,
    # not semantic instance annotations; all polygons are retained exactly once.
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    center = positions[quads].mean(axis=1)
    region = np.zeros(len(quads), dtype=np.uint8)
    tests = [
        (1, center[:, 2] < lo[2] + .06),
        (2, center[:, 0] < lo[0] + .10),
        (3, center[:, 0] > hi[0] - .10),
        (4, center[:, 1] < lo[1] + .14),
        (5, center[:, 1] > hi[1] - .10),
        (6, center[:, 2] > hi[2] - .17),
    ]
    for index, mask in tests:
        region[mask] = index
    names = ['gt_contents', 'gt_floor', 'gt_wall_x_min', 'gt_wall_x_max',
             'gt_wall_y_min', 'gt_wall_y_max', 'gt_ceiling']
    labels = ['室内主体（含家具）', '地面区域', '侧墙区域 X−', '侧墙区域 X+',
              '侧墙区域 Y−', '侧墙区域 Y+', '顶棚区域']
    # Proper rotation, determinant +1: source Z-up meters -> viewer Y-up meters.
    transform = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float32)
    positions = positions @ transform.T
    normals = normals @ transform.T
    colors = np.where(colors <= .04045, colors / 12.92, ((colors + .055) / 1.055) ** 2.4)
    binary = bytearray()
    gltf = {
        'asset': {'version': '2.0', 'generator': 'office-viewer/export_office2_gt.py'},
        'extensionsUsed': ['KHR_materials_unlit'],
        'scene': 0, 'scenes': [{'nodes': list(range(len(names)))}],
        'nodes': [], 'meshes': [], 'bufferViews': [], 'accessors': [],
        'materials': [{'name': 'GT vertex colors', 'doubleSided': True,
                       'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1],
                                               'metallicFactor': 0, 'roughnessFactor': 1},
                       'extensions': {'KHR_materials_unlit': {}}}],
    }

    def accessor(array, component_type, shape, target, bounds=False):
        while len(binary) % 4:
            binary.append(0)
        raw = array.tobytes()
        view = len(gltf['bufferViews'])
        gltf['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary),
                                   'byteLength': len(raw), 'target': target})
        binary.extend(raw)
        entry = {'bufferView': view, 'componentType': component_type,
                 'count': len(array), 'type': shape}
        if bounds:
            entry.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        gltf['accessors'].append(entry)
        return len(gltf['accessors']) - 1

    parts = []
    for index, (name, label) in enumerate(zip(names, labels)):
        subset = quads[region == index]
        used, inverse = np.unique(subset, return_inverse=True)
        local = inverse.reshape(-1, 4)
        attributes = {
            'POSITION': accessor(positions[used].astype('<f4'), 5126, 'VEC3', 34962, True),
            'NORMAL': accessor(normals[used].astype('<f4'), 5126, 'VEC3', 34962),
            'COLOR_0': accessor(colors[used].astype('<f4'), 5126, 'VEC3', 34962),
        }
        faces = np.stack([local[:, [0, 1, 2]], local[:, [0, 2, 3]]], axis=1).reshape(-1, 3)
        indices = accessor(faces.astype('<u4').reshape(-1), 5125, 'SCALAR', 34963)
        gltf['meshes'].append({'name': name, 'primitives': [
            {'attributes': attributes, 'indices': indices, 'material': 0, 'mode': 4}]})
        gltf['nodes'].append({'name': name, 'mesh': index,
                              'extras': {'is_asset_root': True, 'asset_id': name}})
        parts.append({'id': name, 'label': label, 'vertices': len(used),
                      'quads': len(subset), 'triangles': len(faces)})
    assert sum(part['quads'] for part in parts) == len(quads)
    gltf['buffers'] = [{'byteLength': len(binary)}]
    header = json.dumps(gltf, separators=(',', ':'), ensure_ascii=False).encode()
    header += b' ' * (-len(header) % 4)
    binary += b'\0' * (-len(binary) % 4)
    data = (struct.pack('<III', 0x46546C67, 2, 28 + len(header) + len(binary))
            + struct.pack('<II', len(header), 0x4E4F534A) + header
            + struct.pack('<II', len(binary), 0x004E4942) + binary)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'scene.glb').write_bytes(data)
    provenance = {
        'schemaVersion': 1, 'sceneId': 'office_2_000', 'sourceFile': source.name,
        'sourceSHA256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'sourceBytes': source.stat().st_size, 'vertices': len(positions),
        'sourceQuads': len(quads), 'triangles': len(quads) * 2,
        'previewBytes': len(data), 'previewSHA256': hashlib.sha256(data).hexdigest(),
        'units': 'meters', 'sourceUpAxis': '+Z', 'viewerUpAxis': '+Y',
        'sourceToViewer': transform.tolist(), 'simplification': 'none',
        'colorConversion': 'sRGB uint8 to linear float32; unlit vertex-color material',
        'partition': 'Geometric shell bands for reversible cutaway; not GT instance labels.',
        'partitionBandsMeters': {'floor': .06, 'ceiling': .17, 'wallXMin': .10,
                                 'wallXMax': .10, 'wallYMin': .14, 'wallYMax': .10},
        'parts': parts,
        'bounds': {'min': positions.min(axis=0).tolist(), 'max': positions.max(axis=0).tolist()},
        'pipelineRegistration': 'Not applied. Native GT metric coordinates are retained.',
    }
    (destination / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(provenance, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
