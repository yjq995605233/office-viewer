#!/usr/bin/env python3
"""Export each untextured office2 Object_Mesh OBJ as an independent GLB.

Requires numpy. Preserve source triangles, names and placement; only rotate
Z-up to Y-up. Display normals and a neutral material are generated for viewing.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import struct

import numpy as np


LABELS = {'chair': '椅子', 'door': '门', 'picture': '装饰画', 'pillow': '抱枕',
          'sofa': '沙发', 'stool': '凳子', 'table': '桌子', 'trash_can': '垃圾桶',
          'tv': '电视', 'wall_clock': '挂钟', 'window': '窗'}


def read_obj(path):
    vertices, faces = [], []
    for line in path.read_text().splitlines():
        tokens = line.split('#', 1)[0].split()
        if not tokens:
            continue
        if tokens[0] == 'v':
            if len(tokens) != 4:
                raise ValueError(f'{path.name}: expected XYZ-only vertices')
            vertices.append([float(value) for value in tokens[1:]])
        elif tokens[0] == 'f':
            if len(tokens) != 4 or any('/' in value for value in tokens[1:]):
                raise ValueError(f'{path.name}: expected plain triangular faces')
            indices = [int(value) for value in tokens[1:]]
            if 0 in indices:
                raise ValueError('OBJ indices cannot be zero')
            faces.append([value - 1 if value > 0 else len(vertices) + value for value in indices])
        elif tokens[0] not in {'o', 'g', 's'}:
            raise ValueError(f'{path.name}: unsupported source data {tokens[0]}')
    vertices = np.array(vertices, dtype=np.float64)
    faces = np.array(faces, dtype=np.int64)
    if not len(vertices) or not len(faces) or not np.isfinite(vertices).all():
        raise ValueError(f'{path.name}: invalid or empty mesh')
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError(f'{path.name}: invalid vertex indices')
    return vertices, faces


def make_glb(name, positions, faces):
    # Split vertices at face boundaries to give untextured planar surfaces flat
    # normals. This changes only the storage layout, not triangle coordinates.
    triangles = positions[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    length = np.linalg.norm(normals, axis=1)
    degenerate = int(np.count_nonzero(length <= 1e-15))
    normals /= np.maximum(length[:, None], 1e-15)
    normals[length <= 1e-15] = [0, 1, 0]
    attributes = [triangles.reshape(-1, 3).astype('<f4'), np.repeat(normals, 3, axis=0).astype('<f4')]
    binary = b''.join(array.tobytes() for array in attributes)
    views, accessors, offset = [], [], 0
    for index, array in enumerate(attributes):
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': array.nbytes, 'target': 34962})
        accessor = {'bufferView': index, 'componentType': 5126, 'count': len(array), 'type': 'VEC3'}
        if index == 0:
            accessor.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        accessors.append(accessor)
        offset += array.nbytes
    gltf = {
        'asset': {'version': '2.0', 'generator': 'office-viewer/export_office2_gt_objects.py'},
        'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'name': name, 'mesh': 0, 'extras': {'is_asset_root': True, 'asset_id': name}}],
        'meshes': [{'name': name, 'primitives': [
            {'attributes': {'POSITION': 0, 'NORMAL': 1}, 'mode': 4, 'material': 0}]}],
        'materials': [{'name': 'Neutral display white (not GT color)', 'doubleSided': True,
                       'pbrMetallicRoughness': {'baseColorFactor': [.72, .72, .72, 1],
                                               'metallicFactor': 0, 'roughnessFactor': .85}}],
        'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors,
    }
    header = json.dumps(gltf, separators=(',', ':')).encode()
    header += b' ' * (-len(header) % 4)
    binary += b'\0' * (-len(binary) % 4)
    data = (struct.pack('<III', 0x46546C67, 2, 28 + len(header) + len(binary))
            + struct.pack('<II', len(header), 0x4E4F534A) + header
            + struct.pack('<II', len(binary), 0x004E4942) + binary)
    return data, degenerate


def export(source, output):
    files = sorted(source.glob('*.obj'))
    if not files:
        raise ValueError('No OBJ files found')
    output.mkdir(parents=True, exist_ok=True)
    assets, hashes = [], defaultdict(list)
    rotation = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    for path in files:
        vertices, faces = read_obj(path)
        positions = vertices @ rotation.T
        data, degenerate = make_glb(path.stem, positions, faces)
        filename = path.stem + '.glb'
        (output / filename).write_bytes(data)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[digest].append(path.stem)
        category, number = path.stem.rsplit('_', 1)
        assets.append({'id': path.stem, 'label': f'{LABELS.get(category, category)} {number}',
                       'file': filename, 'sourceFile': path.name, 'sourceSHA256': digest,
                       'sourceBytes': path.stat().st_size, 'sourceVertices': len(vertices),
                       'originalTriangles': len(faces), 'previewTriangles': len(faces),
                       'previewBytes': len(data), 'previewSHA256': hashlib.sha256(data).hexdigest(),
                       'degenerateTrianglesRetained': degenerate,
                       'bounds': {'min': positions.min(axis=0).tolist(), 'max': positions.max(axis=0).tolist()}})
    duplicates = [group for group in hashes.values() if len(group) > 1]
    for asset in assets:
        others = [name for name in hashes[asset['sourceSHA256']] if name != asset['id']]
        if others:
            asset['identicalSourceObjects'] = others
            asset['label'] += '（源文件重复）'
    report = {
        'schemaVersion': 1, 'sceneId': 'office_2_000', 'sourceDirectory': 'Object_Mesh',
        'sourceAppearance': 'XYZ vertices and triangular faces only; no colors, UVs, normals or materials',
        'displayAppearance': 'Neutral white material; generated flat normals; not measured GT color',
        'sourceUpAxis': '+Z', 'upAxis': '+Y', 'units': 'meters',
        'sourceToViewer': rotation.tolist(), 'simplification': 'none',
        'transforms': 'same coordinate rotation as complete GT; no per-object recentering or rescaling',
        'duplicateSourceGroups': duplicates, 'duplicatePolicy': 'preserve all source IDs independently',
        'assets': assets,
        'totals': {'objects': len(assets), 'triangles': sum(a['previewTriangles'] for a in assets),
                   'previewBytes': sum(a['previewBytes'] for a in assets)},
    }
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'totals': report['totals'], 'duplicates': duplicates}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.output)
