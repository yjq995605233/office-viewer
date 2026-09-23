#!/usr/bin/env python3
"""Import existing Office2 Fire3D and InSpace results without running inference.

Requires NumPy. Fire3D's GLB binary (geometry and textures) is copied unchanged.
InSpace's independent OBJ geometry is exported with a neutral display material:
its per-object exports share an overwritten material_0.png, so the available
texture cannot be assigned reliably to every object.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct

import numpy as np


ROTATION = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def pack_glb(document, binary):
    header = json.dumps(document, separators=(',', ':')).encode()
    header += b' ' * (-len(header) % 4)
    binary += b'\0' * (-len(binary) % 4)
    return (struct.pack('<III', 0x46546C67, 2, 28 + len(header) + len(binary))
            + struct.pack('<II', len(header), 0x4E4F534A) + header
            + struct.pack('<II', len(binary), 0x004E4942) + binary)


def export_fire(root, run, conversion, output):
    source_dir = root / 'results/replicapano' / run / 'reconstruction/office_2_000'
    source = source_dir / 'appearance/predicted_textured_world_scene.glb'
    metadata_path = source_dir / 'appearance/appearance_summary.json'
    metadata = json.loads(metadata_path.read_text())['composed_world_scene']['objects']
    audit_path = source_dir / 'input_audit.json'
    audit = json.loads(audit_path.read_text())
    background = audit['background_room_box_prior']['background_local_instance_id']
    conversion_data = json.loads(conversion.read_text())
    raw = source.read_bytes()
    magic, version, total = struct.unpack_from('<III', raw)
    assert (magic, version, total) == (0x46546C67, 2, len(raw))
    length, kind = struct.unpack_from('<II', raw, 12)
    assert kind == 0x4E4F534A
    document = json.loads(raw[20:20 + length])
    binary_length, kind = struct.unpack_from('<II', raw, 20 + length)
    assert kind == 0x004E4942
    binary = raw[28 + length:]
    assert len(binary) == binary_length
    roots = document['scenes'][document.get('scene', 0)]['nodes']
    assert roots == [0] and document['nodes'][0]['name'] == 'world'
    assert not any(key in document['nodes'][0] for key in ('matrix', 'rotation', 'translation', 'scale'))
    # Attach a display-axis transform without modifying any original node matrix.
    document['nodes'][0]['rotation'] = [-2 ** -.5, 0, 0, 2 ** -.5]
    by_name = {entry['node_name']: entry for entry in metadata}
    assets = []
    for node in document['nodes']:
        if 'mesh' not in node:
            continue
        entry = by_name[node['name']]
        number = entry['instance_id']
        asset_id = f'pred_{number:04d}'
        assert np.allclose(np.array(node['matrix']).reshape(4, 4).T, entry['object_to_world'])
        node['extras'] = {**node.get('extras', {}), 'is_asset_root': True, 'asset_id': asset_id}
        assets.append({'id': asset_id, 'label': f'预测实例 {number:04d}' if number != background
                       else f'房间背景 · {number:04d}', 'sourceNode': node['name'],
                       'sourceTriangles': entry['faces'], 'sourceVertices': entry['vertices']})
    assert len(assets) == len(metadata)
    output.mkdir(parents=True, exist_ok=True)
    target = output / 'scene.glb'
    target.write_bytes(pack_glb(document, binary))
    report = {
        'schemaVersion': 1, 'sceneId': 'office_2_000', 'method': 'Fire3D', 'sourceRun': run,
        'sourceFile': str(source.relative_to(root)), 'sourceSHA256': digest(source),
        'sourceMetadataSHA256': digest(metadata_path), 'inputAuditSHA256': digest(audit_path),
        'sourceFrameIds': conversion_data['source_frame_ids'],
        'inputTangentFrames': audit['num_frames'], 'conversionSHA256': digest(conversion),
        'sourceSpace': 'world', 'sourceUpAxis': '+Z', 'upAxis': '+Y',
        'sourceToViewer': ROTATION.tolist(), 'units': 'source world meters',
        'geometryAndTextureBinarySHA256': hashlib.sha256(binary).hexdigest(),
        'geometryAndTextures': 'original GLB BIN chunk unchanged; no simplification',
        'backgroundAssetId': f'pred_{background:04d}',
        'backgroundIdentification': 'input_audit.background_room_box_prior.background_local_instance_id; not GLB node name',
        'previewSHA256': digest(target), 'previewBytes': target.stat().st_size,
        'assets': assets, 'totals': {'objectsIncludingBackground': len(assets),
                                    'triangles': sum(a['sourceTriangles'] for a in assets)},
    }
    write_json(output / 'provenance.json', report)
    print(output.name, report['totals'], flush=True)
    return report


def read_obj_geometry(path):
    vertices, faces = [], []
    with path.open() as stream:
        for line in stream:
            values = line.split()
            if not values:
                continue
            if values[0] == 'v':
                assert len(values) == 4, 'Unexpected colored or homogeneous vertex'
                vertices.append([float(x) for x in values[1:]])
            elif values[0] == 'f':
                assert len(values) == 4, 'Expected triangulated InSpace output'
                indices = [int(x.split('/')[0]) for x in values[1:]]
                assert 0 not in indices
                faces.append([x - 1 if x > 0 else len(vertices) + x for x in indices])
    vertices, faces = np.array(vertices), np.array(faces)
    assert len(vertices) and len(faces) and np.isfinite(vertices).all()
    assert faces.min() >= 0 and faces.max() < len(vertices)
    return vertices, faces


def geometry_glb(name, vertices, faces):
    positions = (vertices @ ROTATION.T).astype('<f4')
    normals = np.zeros_like(positions)
    triangles = positions[faces]
    face_normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-15)
    normals[lengths <= 1e-15] = [0, 1, 0]
    arrays = [positions, normals, faces.astype('<u4').reshape(-1)]
    views, accessors, offset = [], [], 0
    for index, array in enumerate(arrays):
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': array.nbytes,
                      'target': 34963 if index == 2 else 34962})
        accessor = {'bufferView': index, 'componentType': 5125 if index == 2 else 5126,
                    'count': len(array), 'type': 'SCALAR' if index == 2 else 'VEC3'}
        if index == 0:
            accessor.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        accessors.append(accessor)
        offset += array.nbytes
    binary = b''.join(array.tobytes() for array in arrays)
    document = {
        'asset': {'version': '2.0', 'generator': 'office-viewer/export_office2_baselines.py'},
        'scene': 0, 'scenes': [{'nodes': [0]}],
        'nodes': [{'name': name, 'mesh': 0, 'extras': {'is_asset_root': True, 'asset_id': name}}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1}, 'indices': 2, 'material': 0}]}],
        'materials': [{'name': 'Neutral geometry display; source texture association unavailable',
                       'doubleSided': True, 'pbrMetallicRoughness': {
                           'baseColorFactor': [.72, .72, .72, 1], 'metallicFactor': 0, 'roughnessFactor': .85}}],
        'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors,
    }
    return pack_glb(document, binary), {'min': positions.min(axis=0).tolist(), 'max': positions.max(axis=0).tolist()}


def export_inspace(root, output):
    source = root / 'demo_outputs/replicapano/office_2_000/00086/meshes'
    output.mkdir(parents=True, exist_ok=True)
    assets = []
    files = [source / 'layout.obj', *sorted((source / 'assets').glob('*.obj'))]
    for path in files:
        vertices, faces = read_obj_geometry(path)
        data, bounds = geometry_glb(path.stem, vertices, faces)
        target = output / (path.stem + '.glb')
        target.write_bytes(data)
        assets.append({'id': path.stem, 'label': '房间结构 · layout' if path.stem == 'layout'
                       else f'预测物体 · {path.stem}', 'file': target.name,
                       'sourceFile': str(path.relative_to(source)), 'sourceSHA256': digest(path),
                       'sourceVertices': len(vertices), 'sourceTriangles': len(faces),
                       'previewTriangles': len(faces), 'previewBytes': len(data),
                       'previewSHA256': digest(target), 'bounds': bounds})
    report = {
        'schemaVersion': 1, 'sceneId': 'office_2_000', 'method': 'InSpace', 'sourceFrameIds': ['00086'],
        'sourceDirectory': str(source.relative_to(root)), 'sourceUpAxis': '+Z', 'upAxis': '+Y',
        'sourceToViewer': ROTATION.tolist(), 'units': 'normalized source coordinates; not verified meters',
        'geometry': 'independent assets plus layout; original vertices and triangle indices, no simplification',
        'overallScenePolicy': 'scene.obj is a separate overall decoder output; not added on top of independent parts',
        'overallSceneSHA256': digest(source / 'scene.obj'),
        'missingSourceAssetIds': ['007_asset_007'],
        'displayAppearance': 'neutral gray, generated normals; not a claim that the source is untextured',
        'textureLimitation': 'source assets all reference material.mtl/material_0.png; sequential Trimesh exports overwrite this shared file. Per-object texture associations cannot be recovered from this directory.',
        'assets': assets, 'totals': {'objects': len(assets) - 1, 'layouts': 1,
                                    'triangles': sum(a['sourceTriangles'] for a in assets),
                                    'previewBytes': sum(a['previewBytes'] for a in assets)},
    }
    write_json(output / 'manifest.json', report)
    print(output.name, report['totals'], flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fire3d', type=Path, required=True)
    parser.add_argument('--inspace', type=Path, required=True)
    parser.add_argument('--replicapano', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('scenes'))
    args = parser.parse_args()
    export_fire(args.fire3d, 'office_2_000', args.fire3d / 'data/replicapano/scenes/office_2_000/conversion.json',
                args.output / 'office2-fire3d-erp4')
    export_fire(args.fire3d, 'office_2_000_frame86',
                args.fire3d / 'data/replicapano_office2_frame86/replicapano/scenes/office_2_000/conversion.json',
                args.output / 'office2-fire3d-frame86')
    export_inspace(args.inspace, args.output / 'office2-inspace-frame86')
    shared = args.output / 'office2-inputs'
    shared.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.replicapano / 'office_2_000/office_2_000/Scene_Info/00086/rgb.png', shared / '86_rgb.png')
