// Selection geometry is independent of the reduced preview mesh. Boxer boxes
// are stored in the same REST3D Y-up world coordinates as the GLB vertices.
function validBox(box) {
  const vector = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
  return box?.source === 'boxer-init' && vector(box.center) && vector(box.size)
    && box.size.every(value => value > 0) && Number.isFinite(box.yaw);
}

export function getBoxerBox(panel) {
  const box = panel.report?.assets?.find(asset => asset.id === panel.selected)?.boxerBox;
  return validBox(box) ? box : null;
}

export function requiresBoxerBounds(panel) {
  return panel.config?.selectionBounds === 'boxer-init';
}

export function validateSelectionBoundsReport(config, report) {
  if (config.selectionBounds !== 'boxer-init') return;
  if (report.selectionBounds?.source !== 'boxer-init' || !report.assets?.length
    || !report.assets.every(asset => validBox(asset.boxerBox))) {
    throw new Error('Boxer 包围盒数据缺失或版本不匹配，请重试加载。');
  }
}

// Version the small data requests and revalidate them on load. Preview GLBs keep
// their existing cache URLs, so updating metadata does not re-download meshes.
export function sceneDataURL(path) {
  const url = new URL(path, document.baseURI);
  url.searchParams.set('v', 'office2-baselines-1');
  return url;
}

export function updateSelectionBounds(panel, Vector3) {
  const object = panel.assets.get(panel.selected);
  const helper = panel.selectionBox;
  helper.visible = !!object && !panel.hidden.has(panel.selected);
  // Reset when moving between scenes or selecting an object without Boxer data.
  helper.rotation.set(0, 0, 0);
  if (!object) return;
  const box = getBoxerBox(panel);
  if (box) {
    // Box3Helper uses box only to derive position and scale. Its rotation then
    // orients the twelve edges about that center, without re-enclosing the OBB.
    helper.box.setFromCenterAndSize(new Vector3(...box.center), new Vector3(...box.size));
    helper.rotation.y = box.yaw;
  } else if (!requiresBoxerBounds(panel)) {
    helper.box.setFromObject(object);
  } else {
    // Never disguise missing initialization data as a valid mesh AABB.
    helper.visible = false;
  }
}

export function selectionBoundsLabel(panel, Box3, Vector3) {
  const object = panel.assets.get(panel.selected);
  if (!object) return '';
  const box = getBoxerBox(panel);
  if (!box && requiresBoxerBounds(panel)) return 'Boxer 包围盒数据缺失，请重试加载。';
  const size = box ? box.size : new Box3().setFromObject(object).getSize(new Vector3()).toArray();
  const dimensions = size.map(value => value.toFixed(2)).join(' × ');
  return `${box ? 'Boxer 初始化包围盒' : '世界轴对齐包围盒'} ${dimensions} ${panel.config.unitLabel}`;
}
