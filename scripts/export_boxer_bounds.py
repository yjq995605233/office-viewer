#!/usr/bin/env python3
"""Attach Boxer initialization OBBs to a matching viewer conversion report.

Standard library only. Reject mismatched source meshes before writing anything.
Keep initial placement unchanged: do not apply subsequent agent translations,
support snapping, or scale review to an initialization-stage prediction.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError('Expected a three-component vector')
    result = [float(component) for component in value]
    if not all(math.isfinite(component) for component in result):
        raise ValueError('Non-finite box component')
    return result


def convert_box(record):
    if record['initialization_source'] != 'boxer':
        raise ValueError('Object has no Boxer initialization prediction')
    meters_per_unit = float(record['meters_per_world_unit'])
    if not math.isfinite(meters_per_unit) or meters_per_unit <= 0:
        raise ValueError('Invalid meters_per_world_unit')
    center_metric = vector(record['boxer_center_metric_m'])
    size_metric = vector(record['boxer_size_m'])
    if min(size_metric) <= 0:
        raise ValueError('Box dimensions must be positive')
    # Inverse of REST_YUP_TO_BOXER_ZUP: (x, y, z) -> (x, z, -y).
    center = [center_metric[0] / meters_per_unit,
              center_metric[2] / meters_per_unit,
              -center_metric[1] / meters_per_unit]
    if any(abs(a - b) > 1e-6 for a, b in zip(center, vector(record['boxer_center_rest']))):
        raise ValueError('Boxer and REST centers disagree')
    size = [size_metric[i] / meters_per_unit for i in (0, 2, 1)]
    yaw = float(record['boxer_yaw_zup'])
    if not math.isfinite(yaw):
        raise ValueError('Non-finite yaw')
    return dict(source='boxer-init', center=center, size=size, yaw=yaw,
                metersPerWorldUnit=meters_per_unit)


def export(report_path, initialization_path, scene_path):
    report = json.loads(report_path.read_text())
    initialization = json.loads(initialization_path.read_text())
    scene = json.loads(scene_path.read_text())
    if scene['coordinate_frame'] != 'rest3d_floor_canonical_y_up':
        raise ValueError('Expected a REST3D Y-up source scene')
    objects = {obj['instance_id']: obj for obj in scene['objects']}
    assets = report['assets']
    if len({asset['id'] for asset in assets}) != len(assets):
        raise ValueError('Duplicate asset IDs')
    for asset in assets:
        object_id = asset['id']
        if asset['sourceSHA256'] != objects[object_id]['final_sha256']:
            raise ValueError(f'{object_id}: published mesh does not match this experiment')
        asset['boxerBox'] = convert_box(initialization['objects'][object_id])
    report['selectionBounds'] = {
        'source': 'boxer-init',
        'coordinateFrame': 'rest3d_floor_canonical_y_up',
        'sizeOrder': 'local X, local Y (height), local Z',
        'yawConvention': 'radians about +Y; same sign as boxer_yaw_zup',
        'placement': 'original initialization prediction; no later pose or scale adjustments',
        'sceneId': scene['scene_id'],
        'initializationManifestSHA256': sha256(initialization_path),
        'finalSceneManifestSHA256': sha256(scene_path),
        'matchedSourceMeshHashes': len(assets),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return len(assets)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--initialization', type=Path, required=True)
    parser.add_argument('--final-scene', type=Path, required=True)
    args = parser.parse_args()
    count = export(args.report, args.initialization, args.final_scene)
    print(f'Exported {count} Boxer OBBs; all source mesh hashes match.')
