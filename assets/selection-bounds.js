// Selection geometry is independent of the reduced preview mesh. Boxer boxes
// are stored in the same REST3D Y-up world coordinates as the GLB vertices.
export function getBoxerBox(panel) {
  const box = panel.report?.assets?.find(asset => asset.id === panel.selected)?.boxerBox;
  const vector = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
  return box?.source === 'boxer-init' && vector(box.center) && vector(box.size)
    && box.size.every(value => value > 0) && Number.isFinite(box.yaw)
    ? box : null;
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
  } else {
    helper.box.setFromObject(object);
  }
}

export function selectionBoundsLabel(panel, Box3, Vector3) {
  const object = panel.assets.get(panel.selected);
  if (!object) return '';
  const box = getBoxerBox(panel);
  const size = box ? box.size : new Box3().setFromObject(object).getSize(new Vector3()).toArray();
  const dimensions = size.map(value => value.toFixed(2)).join(' × ');
  return `${box ? 'Boxer 初始化包围盒' : '世界轴对齐包围盒'} ${dimensions} ${panel.config.unitLabel}`;
}
