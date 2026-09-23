# Scene Study · 办公室结果对比

在线查看：[办公室三维场景对比](https://yjq995605233.github.io/office-viewer/)。

## 当前结果

- Office2 · GT：ReplicaPano `office_2_000` 完整彩色网格，原始米制尺度；默认与 Pipeline 并排显示。
- 单张全景 Office V2：原有场景，20 个语义资产，名义米制尺寸。
- 我的 Pipeline / 4 帧 ERP：来自 first_full_scene_agent_v1，23 个独立物体；输入为 office2_4 的 32、66、85、97 帧。
- 新结果仍存在物体穿插与门放置不合理的问题，按原布局展示。该批次没有房间壳体；网格是观察辅助。

## 操作

- 左右下拉框选择结果，支持双场景对比和单场景查看。网址会保留所选结果与显示模式，可直接复制分享。
- 拖动旋转、右键平移、滚轮缩放；点击模型或右侧列表选中、聚焦、隐藏或恢复物体。
- A / B 切换检查侧，可开关网格、坐标轴、线框；原有场景可剖开房间。
- 自由漫游：WASD 移动、Q / E 升降、Shift 加速、R 复位、Esc 退出。允许穿过物体，便于检查错误。
- 原有场景另保留室内行走，采用固定视高与简化碰撞；进入行走会恢复隐藏物体。
- 输入全景按钮查看各结果对应的 ERP 图；全屏按钮放大当前场景。

建议在桌面 Chrome 或 Edge 中使用键盘鼠标漫游。触屏支持旋转、平移与缩放，暂不支持触屏漫游。

## 数据说明

各结果未完成坐标与尺度配准。联动视角仅按各自场景大小同步观察方向和相对位置，不表示像素或几何对齐。

新结果由约 1277 万三角面减至约 115 万面，OBJ 约 688 MiB 转为 GLB 约 33 MiB。保留原始世界坐标、实例编号与顶点颜色，重新计算法线。各物体的转换记录见 scenes/pipeline-erp4-v1/conversion-report.json。网页轻量副本用于目视检查，定量评估应使用原始网格。

此仓库包含构建后的网页和展示资源，不包含原始 OBJ、Blender 工程或重建 pipeline。公开访问不代表另行授予场景数据和输入图片的再利用许可。

### Office2 GT

GT 来自 `RplicaPano/office_2_000/office_2_000/office_2_aligned.ply`，包含完整房间与家具；没有使用 `Object_Mesh` 中的低面数物体代理替代扫描网格。858,623 个源顶点和 857,845 个四边形保留，四边形拆成 1,715,690 个三角形，不减面。仅将 Z-up 米制坐标旋转为 Y-up：`(x, y, z) → (x, z, -y)`。颜色从 sRGB 转为线性顶点色，使用无光照材质显示原始颜色。

为支持可逆剖切，按房间边界的窄空间带分为地面、四面侧墙、顶棚和室内主体共 7 个显示区域。它们不是语义实例标签；所有源面恰好分配一次，关闭剖切可恢复全部几何。默认隐藏顶棚、X− 侧墙和源坐标 Y− 侧墙；原始尺度和布局不变。GT 尚未与 Pipeline 配准，不提供实例一一对应或定量误差评估。

转换记录及哈希见 `scenes/office2-gt/provenance.json`。已有四帧输入图与 GT 对应帧文件的 SHA256 一致，因此复用图片资源。

```bash
python -m pip install numpy plyfile
python scripts/export_office2_gt.py \
  --source /path/to/office_2_aligned.ply \
  --output scenes/office2-gt
```

### Boxer 初始化包围盒

Pipeline 的选中框读取 `conversion-report.json` 中逐物体的 `boxerBox`，使用同一实验的 Boxer 初始化中心、尺寸和朝向，不再从减面模型计算世界轴对齐框。23 个发布模型的源 SHA256 均与 `full_scene_agent_v1/final_scene/scene_manifest.json` 一致。

框保留 **boxer-init 时刻** 的预测位置和尺寸，不应用后续的落地、贴墙、支撑吸附、缩放复核或 Agent 平移。因此它可用于检查初始化预测，但不保证紧贴最终网格。尺寸按框自身的 X、Y（高）、Z 轴排列；无 Boxer 数据的场景继续显示并标注世界轴对齐包围盒。

服务器上的更新命令（Python 标准库，无需运行模型推理）：

```bash
python scripts/export_boxer_bounds.py \
  --report scenes/pipeline-erp4-v1/conversion-report.json \
  --initialization /path/to/run/boxer_init/initialization_manifest.json \
  --final-scene /path/to/run/full_scene_agent_v1/final_scene/scene_manifest.json
```

导出器先核对全部物体编号和源网格哈希，再写入数据；不匹配时直接报错。Boxer 的米制 Z-up 坐标按 `(x, z, -y) / meters_per_world_unit` 转为模型使用的 REST3D Y-up 坐标，尺寸重排为 `(sx, sz, sy) / meters_per_world_unit`，绕 Y 的角度与 `boxer_yaw_zup` 同号。源清单哈希记录在 `selectionBounds` 中。

选中框逻辑保留为可维护模块 `assets/selection-bounds.js`；当前发布入口直接导入它，可在服务器修改后用 `python -m http.server 8000` 预览。发布仍通过 GitHub Pages 的 main 分支。

场景目录和物体清单使用版本化请求并在加载时重新验证缓存，避免新代码读取旧清单。声明 `selectionBounds: "boxer-init"` 的场景必须具备全部物体的有效 Boxer 数据，否则显示加载错误，不能静默退回世界轴对齐框。没有这一声明的原有场景仍可使用轴对齐框。

## 扩展与托管

场景登记在 scenes/catalog.json。新增结果可独立配置模型、输入图、说明与已知问题；不必重写查看器。现有 files 格式加载完整 GLB，assetManifest 格式加载一组物体 GLB。

GitHub Pages 从 main 分支根目录发布，所有资源路径兼容 /office-viewer/ 子目录。界面使用 three.js 0.186.0；构建使用 Vite 8.2.2，离线减面使用 meshoptimizer 1.2.0。第三方许可证见 THIRD_PARTY_NOTICES.txt。
