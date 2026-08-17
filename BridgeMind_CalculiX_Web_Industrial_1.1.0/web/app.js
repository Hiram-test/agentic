"use strict"; // 启用严格 JavaScript 模式。
const state = { projects: [], projectId: null, document: null, revisions: [], runs: [], experiences: [], templates: [], selection: null, result: null, hitTargets: [], busy: false, camera: { target: [0, 0, 0], yaw: -0.75, pitch: 0.48, distance: 50 }, drag: { active: false, moved: false, x: 0, y: 0 }, touch: { pointers: new Map(), gesture: null, longPressTimer: null }, deferredInstall: null, currentRevision: null }; // 保存应用、相机、触屏手势和 PWA 安装状态。
const elements = {}; // 保存常用 DOM 元素引用。
const sourceColors = { agent: "#45d5ff", human: "#ffb454", fea: "#ff5f93", imported: "#a98bff" }; // 定义区域来源颜色。
const componentColors = { girder: "#74d8ff", crossbeam: "#8ba7ff", rod: "#75e8c9", deck: "#9cd2da", pier: "#b8a6ff", bearing: "#ffcc75", bridge: "#3a5967", other: "#90aab4" }; // 定义构件类别颜色。

function cacheElements() { // 缓存页面中需要频繁访问的 DOM 元素。
    ["projectSelect", "refreshButton", "validateButton", "strategyButton", "solveButton", "saveButton", "archiveButton", "apiKeyInput", "saveApiKeyButton", "apiKeyStatus", "projectSummary", "cognitiveList", "addRegionButton", "deleteRegionButton", "experienceButton", "resetViewButton", "pointCloudFile", "pointCloudEps", "pointCloudVoxel", "pointCloudButton", "revisionList", "runList", "runChart", "experienceList", "templateKind", "templateId", "templateName", "templateBody", "templateDefault", "saveTemplateButton", "templateList", "exportBsdlButton", "exportGmshButton", "exportCalculixButton", "downloadArea", "calculixStatus", "calculixStatusButton", "runCalculixButton", "runCodeCheckButton", "installButton", "ifcFile", "ifcImportButton", "inpFile", "inpImportButton", "sceneCanvas", "sceneTitle", "selectionBadge", "metricStrip", "objectEditor", "objectJson", "copyObjectButton", "documentJson", "applyDocumentButton", "logView", "leftPanel", "rightPanel", "mobileProjectsButton", "mobileInspectButton", "closeLeftPanelButton", "closeRightPanelButton", "mobileBackdrop", "mobileProjectAction", "mobileAgentAction", "mobileSolveAction", "mobileCalculixAction", "mobileObjectAction", "offlineBanner"].forEach((id) => { elements[id] = document.getElementById(id); }); // 按 ID 保存元素引用。
} // 结束元素缓存函数。

function currentApiKey() { // 读取当前浏览器会话保存的生产 API 密钥。
    return sessionStorage.getItem("bridgemindApiKey") || ""; // 返回会话密钥且不写入持久化本地存储。
} // 结束会话密钥读取函数。

function updateApiKeyStatus(authenticationRequired, message = "") { // 更新访问控制提示并避免显示密钥正文。
    if (!elements.apiKeyStatus) { return; } // 页面尚未缓存访问控件时安全返回。
    const hasKey = Boolean(currentApiKey()); // 检查当前会话是否已经保存密钥。
    const title = authenticationRequired ? (hasKey ? "已配置本会话密钥" : "服务器要求 API 密钥") : "服务器未启用 API 密钥"; // 生成不泄露凭据的状态标题。
    const detail = message || (authenticationRequired ? (hasKey ? "受保护请求将自动携带 X-API-Key。" : "输入部署时配置的密钥后连接项目数据。") : "当前为本地或受信任网络模式。生产部署仍建议启用密钥。" ); // 生成访问状态说明。
    elements.apiKeyStatus.innerHTML = `<strong>${escapeHtml(title)}</strong><br>${escapeHtml(detail)}`; // 渲染访问控制状态。
    elements.apiKeyStatus.className = `summary-card access-status ${authenticationRequired && !hasKey ? "unavailable" : "available"}`; // 根据访问状态设置视觉提示。
} // 结束访问状态更新函数。

async function api(path, options = {}) { // 调用后端 API 并统一处理凭据、JSON 和错误。
    const headers = new Headers(options.headers || {}); // 合并调用方显式请求头并保留浏览器标准化行为。
    if (!(options.body instanceof FormData) && options.body !== undefined && !headers.has("Content-Type")) { headers.set("Content-Type", "application/json"); } // 仅为非表单请求设置 JSON 内容类型。
    const apiKey = currentApiKey(); // 读取当前会话 API 密钥。
    if (apiKey) { headers.set("X-API-Key", apiKey); } // 在受保护和公开 API 上统一附加密钥供服务器验证。
    const response = await fetch(path, { ...options, headers }); // 发起携带标准请求头的 HTTP 请求。
    const contentType = response.headers.get("content-type") || ""; // 读取响应内容类型。
    const payload = contentType.includes("application/json") ? await response.json() : await response.text(); // 根据类型解析响应。
    if (!response.ok) { // 检查 HTTP 状态。
        const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : payload; // 提取 FastAPI 错误详情。
        const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail, null, 2)); // 创建统一请求错误对象。
        error.status = response.status; // 保存 HTTP 状态供初始化和登录流程判断。
        throw error; // 抛出包含状态的统一错误。
    } // 结束状态检查。
    return payload; // 返回解析后的响应。
} // 结束 API 函数。

async function saveApiKeyAndConnect() { // 保存本会话密钥并重新加载受保护项目数据。
    const value = elements.apiKeyInput.value.trim(); // 读取并清理用户输入的密钥。
    if (value) { sessionStorage.setItem("bridgemindApiKey", value); } else { sessionStorage.removeItem("bridgemindApiKey"); } // 保存或清除仅在当前标签会话有效的凭据。
    elements.apiKeyInput.value = value; // 保持输入框与会话状态一致。
    updateApiKeyStatus(true, value ? "正在验证密钥并加载项目。" : "会话密钥已清除。" ); // 显示连接进度且不回显密钥。
    try { // 捕获无效密钥或后端错误。
        await Promise.all([loadTemplates(), loadProjects(state.projectId)]); // 使用新凭据加载模板和项目数据。
        updateApiKeyStatus(true, "密钥验证通过，受保护项目数据已连接。" ); // 显示凭据验证成功。
        log("服务器访问密钥验证通过。", "success"); // 写入不含凭据的成功日志。
    } catch (error) { // 处理访问失败。
        if (error.status === 401) { sessionStorage.removeItem("bridgemindApiKey"); elements.apiKeyInput.value = ""; } // 无效密钥时清除会话凭据避免重复失败。
        updateApiKeyStatus(true, error.status === 401 ? "密钥无效，请检查部署环境中的 BRIDGEMIND_API_KEYS。" : error.message); // 显示可操作的连接错误。
        log("服务器访问连接失败。", "error", error.message); // 写入不包含密钥正文的错误日志。
    } // 结束凭据连接处理。
} // 结束会话密钥保存函数。

function log(message, kind = "info", data = null) { // 把执行信息写入界面日志。
    const entry = document.createElement("div"); // 创建日志条目元素。
    entry.className = `log-entry ${kind}`; // 设置日志类型样式。
    const time = new Date().toLocaleTimeString(); // 获取本地时间。
    entry.textContent = `[${time}] ${message}${data === null ? "" : `\n${typeof data === "string" ? data : JSON.stringify(data, null, 2)}`}`; // 组装日志文本。
    elements.logView.prepend(entry); // 把最新日志插到顶部。
} // 结束日志函数。

function setBusy(value, message = "") { // 统一控制长操作期间的按钮状态。
    state.busy = value; // 保存忙碌状态。
    ["refreshButton", "validateButton", "strategyButton", "solveButton", "saveButton", "archiveButton", "addRegionButton", "deleteRegionButton", "experienceButton", "pointCloudButton", "saveTemplateButton", "exportBsdlButton", "exportGmshButton", "exportCalculixButton", "calculixStatusButton", "runCalculixButton", "runCodeCheckButton", "ifcImportButton", "inpImportButton", "mobileAgentAction", "mobileSolveAction", "mobileCalculixAction"].forEach((id) => { if (elements[id]) { elements[id].disabled = value; } }); // 切换桌面和移动主要按钮禁用状态。
    if (message) { log(message, "info"); } // 可选记录正在执行的操作。
} // 结束忙碌状态函数。

function deepClone(value) { // 深复制纯 JSON 对象。
    return JSON.parse(JSON.stringify(value)); // 使用 JSON 往返创建独立副本。
} // 结束深复制函数。

function clamp(value, minimum, maximum) { // 把数值限制到给定范围。
    return Math.max(minimum, Math.min(maximum, value)); // 返回限制后的数值。
} // 结束数值限制函数。

function vectorAdd(a, b) { // 计算三维向量加法。
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; // 返回逐分量和。
} // 结束向量加法函数。

function vectorSubtract(a, b) { // 计算三维向量减法。
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; // 返回逐分量差。
} // 结束向量减法函数。

function vectorScale(a, scale) { // 计算三维向量数乘。
    return [a[0] * scale, a[1] * scale, a[2] * scale]; // 返回缩放向量。
} // 结束向量数乘函数。

function vectorLength(a) { // 计算三维向量长度。
    return Math.hypot(a[0], a[1], a[2]); // 返回欧氏范数。
} // 结束向量长度函数。

function componentEndpoints(component) { // 获取线构件的两个三维端点。
    if (component.geometry && component.geometry.kind === "line" && Array.isArray(component.geometry.points) && component.geometry.points.length >= 2) { return [component.geometry.points[0], component.geometry.points[component.geometry.points.length - 1]]; } // 优先使用内联线几何。
    const nodeMap = new Map((state.document?.nodes || []).map((node) => [node.id, node])); // 建立节点索引。
    if (Array.isArray(component.nodeRefs) && component.nodeRefs.length >= 2 && nodeMap.has(component.nodeRefs[0]) && nodeMap.has(component.nodeRefs[1])) { return [nodeMap.get(component.nodeRefs[0]).position, nodeMap.get(component.nodeRefs[1]).position]; } // 使用节点引用恢复端点。
    return null; // 对非线构件返回空。
} // 结束构件端点函数。

function allScenePoints(documentValue) { // 收集用于自动取景的全部三维点。
    const points = []; // 初始化三维点列表。
    (documentValue?.nodes || []).forEach((node) => { if (Array.isArray(node.position)) { points.push(node.position); } }); // 收集节点坐标。
    (documentValue?.components || []).forEach((component) => { if (component.geometry?.kind === "box") { const center = component.geometry.center; const half = component.geometry.size.map((value) => value * 0.5); points.push(vectorSubtract(center, half), vectorAdd(center, half)); } }); // 收集代理盒边界。
    (documentValue?.regions || []).forEach((region) => { const geometry = region.geometry || {}; if (geometry.kind === "box") { const half = geometry.size.map((value) => value * 0.5); points.push(vectorSubtract(geometry.center, half), vectorAdd(geometry.center, half)); } else if (geometry.kind === "sphere") { const half = [geometry.radius, geometry.radius, geometry.radius]; points.push(vectorSubtract(geometry.center, half), vectorAdd(geometry.center, half)); } }); // 收集区域边界。
    return points; // 返回场景点列表。
} // 结束场景点收集函数。

function fitCamera() { // 根据当前结构范围自动设置相机目标与距离。
    const points = allScenePoints(state.document); // 收集当前场景点。
    if (!points.length) { state.camera = { target: [0, 0, 0], yaw: -0.75, pitch: 0.48, distance: 50 }; return; } // 对空场景使用默认相机。
    const minimum = [Infinity, Infinity, Infinity]; // 初始化包围盒下界。
    const maximum = [-Infinity, -Infinity, -Infinity]; // 初始化包围盒上界。
    points.forEach((point) => { for (let index = 0; index < 3; index += 1) { minimum[index] = Math.min(minimum[index], Number(point[index])); maximum[index] = Math.max(maximum[index], Number(point[index])); } }); // 计算三维包围盒。
    state.camera.target = [(minimum[0] + maximum[0]) * 0.5, (minimum[1] + maximum[1]) * 0.5, (minimum[2] + maximum[2]) * 0.5]; // 设置相机观察中心。
    const diagonal = vectorLength(vectorSubtract(maximum, minimum)); // 计算包围盒对角长度。
    state.camera.distance = Math.max(diagonal * 1.35, 10); // 设置适合结构尺度的相机距离。
    state.camera.yaw = -0.72; // 设置默认水平视角。
    state.camera.pitch = 0.5; // 设置默认俯视角度。
} // 结束自动取景函数。

function project(point, width, height) { // 把三维点投影到画布二维坐标。
    const relative = vectorSubtract(point, state.camera.target); // 转换为相机目标局部坐标。
    const cosineYaw = Math.cos(state.camera.yaw); // 计算水平旋转余弦。
    const sineYaw = Math.sin(state.camera.yaw); // 计算水平旋转正弦。
    const xYaw = cosineYaw * relative[0] - sineYaw * relative[1]; // 应用绕 Z 轴水平旋转。
    const yYaw = sineYaw * relative[0] + cosineYaw * relative[1]; // 计算水平旋转后的深度分量。
    const zYaw = relative[2]; // 保留竖向分量。
    const cosinePitch = Math.cos(state.camera.pitch); // 计算俯仰旋转余弦。
    const sinePitch = Math.sin(state.camera.pitch); // 计算俯仰旋转正弦。
    const yPitch = cosinePitch * yYaw - sinePitch * zYaw; // 应用绕 X 轴俯仰旋转。
    const zPitch = sinePitch * yYaw + cosinePitch * zYaw; // 计算俯仰后的竖向分量。
    const depth = state.camera.distance + yPitch; // 计算透视深度。
    if (depth <= 0.1) { return null; } // 丢弃位于相机后方的点。
    const focal = Math.min(width, height) * 0.92; // 设置透视焦距。
    const scale = focal / depth; // 计算透视缩放比例。
    return { x: width * 0.5 + xYaw * scale, y: height * 0.5 - zPitch * scale, depth, scale }; // 返回屏幕坐标与深度。
} // 结束投影函数。

function eulerRotate(point, rotation) { // 按 XYZ 欧拉角旋转局部点。
    const [rx, ry, rz] = rotation || [0, 0, 0]; // 读取三个旋转角。
    let [x, y, z] = point; // 解包局部坐标。
    let nextY = Math.cos(rx) * y - Math.sin(rx) * z; // 计算绕 X 轴后的 Y。
    let nextZ = Math.sin(rx) * y + Math.cos(rx) * z; // 计算绕 X 轴后的 Z。
    y = nextY; z = nextZ; // 更新 X 轴旋转结果。
    let nextX = Math.cos(ry) * x + Math.sin(ry) * z; // 计算绕 Y 轴后的 X。
    nextZ = -Math.sin(ry) * x + Math.cos(ry) * z; // 计算绕 Y 轴后的 Z。
    x = nextX; z = nextZ; // 更新 Y 轴旋转结果。
    nextX = Math.cos(rz) * x - Math.sin(rz) * y; // 计算绕 Z 轴后的 X。
    nextY = Math.sin(rz) * x + Math.cos(rz) * y; // 计算绕 Z 轴后的 Y。
    return [nextX, nextY, z]; // 返回旋转后的坐标。
} // 结束欧拉旋转函数。

function boxCorners(geometry) { // 计算旋转包围盒的八个全局角点。
    const center = geometry.center || [0, 0, 0]; // 读取包围盒中心。
    const half = (geometry.size || [1, 1, 1]).map((value) => Number(value) * 0.5); // 计算半尺寸。
    const corners = []; // 初始化角点列表。
    [-1, 1].forEach((sx) => { [-1, 1].forEach((sy) => { [-1, 1].forEach((sz) => { const local = [sx * half[0], sy * half[1], sz * half[2]]; corners.push(vectorAdd(center, eulerRotate(local, geometry.rotation || [0, 0, 0]))); }); }); }); // 生成并旋转八个角点。
    return corners; // 返回角点列表。
} // 结束包围盒角点函数。

function resizeCanvas() { // 根据显示尺寸和设备像素比调整画布分辨率。
    const canvas = elements.sceneCanvas; // 获取三维画布。
    const ratio = window.devicePixelRatio || 1; // 获取设备像素比。
    const rect = canvas.getBoundingClientRect(); // 读取画布 CSS 尺寸。
    const width = Math.max(1, Math.floor(rect.width * ratio)); // 计算实际像素宽度。
    const height = Math.max(1, Math.floor(rect.height * ratio)); // 计算实际像素高度。
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; } // 仅在尺寸变化时更新画布缓冲。
} // 结束画布尺寸函数。

function drawLine(context, first, second, color, width = 1, dash = []) { // 绘制屏幕空间线段。
    if (!first || !second) { return; } // 跳过不可见端点。
    context.beginPath(); // 开始新路径。
    context.setLineDash(dash); // 设置虚线模式。
    context.strokeStyle = color; // 设置线条颜色。
    context.lineWidth = width; // 设置线条宽度。
    context.moveTo(first.x, first.y); // 移动到起点。
    context.lineTo(second.x, second.y); // 连线到终点。
    context.stroke(); // 绘制路径。
    context.setLineDash([]); // 恢复实线模式。
} // 结束线段绘制函数。

function drawGrid(context, width, height) { // 在 Z=0 平面绘制参考网格。
    const spacing = Math.max(1, Math.pow(10, Math.floor(Math.log10(state.camera.distance / 12)))); // 根据相机距离选择网格间距。
    const extent = spacing * 20; // 设置网格绘制范围。
    const centerX = Math.round(state.camera.target[0] / spacing) * spacing; // 对齐网格 X 中心。
    const centerY = Math.round(state.camera.target[1] / spacing) * spacing; // 对齐网格 Y 中心。
    for (let index = -20; index <= 20; index += 1) { // 遍历网格线序号。
        const x = centerX + index * spacing; // 计算当前 X 网格线位置。
        const y = centerY + index * spacing; // 计算当前 Y 网格线位置。
        const alpha = index === 0 ? 0.22 : 0.08; // 为主轴使用更高透明度。
        drawLine(context, project([x, centerY - extent, 0], width, height), project([x, centerY + extent, 0], width, height), `rgba(75, 130, 150, ${alpha})`, index === 0 ? 1.4 : 1); // 绘制平行 Y 轴网格线。
        drawLine(context, project([centerX - extent, y, 0], width, height), project([centerX + extent, y, 0], width, height), `rgba(75, 130, 150, ${alpha})`, index === 0 ? 1.4 : 1); // 绘制平行 X 轴网格线。
    } // 结束网格线遍历。
} // 结束参考网格函数。

function resultDisplacementMap() { // 建立原始节点到 FEA 位移的映射。
    const map = new Map(); // 初始化位移映射。
    (state.result?.nodeResults || []).forEach((item) => { const key = item.originalNodeRef || item.nodeRef; if (key && Array.isArray(item.displacement)) { map.set(key, item.displacement.slice(0, 3)); } }); // 收集原始节点平移。
    return map; // 返回位移映射。
} // 结束结果位移映射函数。

function renderScene() { // 绘制当前结构、区域、节点和计算反馈。
    resizeCanvas(); // 同步画布实际分辨率。
    const canvas = elements.sceneCanvas; // 获取三维画布。
    const context = canvas.getContext("2d"); // 获取二维绘图上下文。
    const width = canvas.width; // 读取画布像素宽度。
    const height = canvas.height; // 读取画布像素高度。
    context.clearRect(0, 0, width, height); // 清空上一帧。
    context.save(); // 保存绘图状态。
    const ratio = window.devicePixelRatio || 1; // 获取设备像素比。
    context.scale(ratio, ratio); // 把绘图坐标缩放到 CSS 像素。
    const cssWidth = width / ratio; // 计算 CSS 宽度。
    const cssHeight = height / ratio; // 计算 CSS 高度。
    drawGrid(context, cssWidth, cssHeight); // 绘制地面参考网格。
    state.hitTargets = []; // 清空本帧拾取对象。
    if (!state.document) { context.restore(); requestAnimationFrame(renderScene); return; } // 无文档时保持动画循环。
    const nodeMap = new Map((state.document.nodes || []).map((node) => [node.id, node])); // 建立节点索引。
    const displacementMap = resultDisplacementMap(); // 建立 FEA 位移映射。
    const maxDisplacement = Number(state.result?.globalMetrics?.maxTranslation || 0); // 读取最大位移。
    const structurePoints = allScenePoints(state.document); // 收集结构范围点。
    const structuralScale = structurePoints.length ? Math.max(...structurePoints.map((point) => vectorLength(vectorSubtract(point, state.camera.target)))) : 1; // 估计结构尺度。
    const deformScale = maxDisplacement > 0 ? Math.min(structuralScale * 0.12 / maxDisplacement, 800) : 0; // 自动计算变形放大倍数。
    (state.document.components || []).forEach((component) => { // 遍历并绘制构件。
        if (component.topology !== "line") { return; } // 当前三维线框主要绘制线构件。
        const endpoints = componentEndpoints(component); // 获取构件端点。
        if (!endpoints) { return; } // 跳过无法获取端点的构件。
        const first = project(endpoints[0], cssWidth, cssHeight); // 投影构件起点。
        const second = project(endpoints[1], cssWidth, cssHeight); // 投影构件终点。
        const selected = state.selection?.kind === "component" && state.selection.id === component.id; // 判断当前构件是否选中。
        const color = selected ? "#ffffff" : (componentColors[component.category] || componentColors.other); // 选择构件显示颜色。
        drawLine(context, first, second, color, selected ? 4 : 2.2); // 绘制未变形构件。
        if (first && second) { state.hitTargets.push({ kind: "component", id: component.id, type: "segment", first, second, depth: (first.depth + second.depth) * 0.5 }); } // 保存构件拾取线段。
        if (deformScale > 0 && component.nodeRefs?.length >= 2 && displacementMap.has(component.nodeRefs[0]) && displacementMap.has(component.nodeRefs[1])) { // 检查是否可绘制变形构件。
            const deformedFirst = vectorAdd(endpoints[0], vectorScale(displacementMap.get(component.nodeRefs[0]), deformScale)); // 计算放大后的起点。
            const deformedSecond = vectorAdd(endpoints[1], vectorScale(displacementMap.get(component.nodeRefs[1]), deformScale)); // 计算放大后的终点。
            drawLine(context, project(deformedFirst, cssWidth, cssHeight), project(deformedSecond, cssWidth, cssHeight), "rgba(255,95,147,0.85)", 1.4, [5, 4]); // 绘制变形后构件。
        } // 结束变形构件绘制。
    }); // 结束构件遍历。
    (state.document.nodes || []).forEach((node) => { // 遍历并绘制结构节点。
        const screen = project(node.position, cssWidth, cssHeight); // 投影节点坐标。
        if (!screen) { return; } // 跳过不可见节点。
        const selected = state.selection?.kind === "node" && state.selection.id === node.id; // 判断当前节点是否选中。
        const isSupport = (node.roles || []).includes("support") || Object.values(node.constraints || {}).some(Boolean); // 判断节点是否具有支承约束。
        context.beginPath(); // 开始节点圆形路径。
        context.arc(screen.x, screen.y, selected ? 5.5 : (isSupport ? 4.2 : 3.0), 0, Math.PI * 2); // 绘制节点圆。
        context.fillStyle = selected ? "#ffffff" : (isSupport ? "#ffcc75" : "#7be3d0"); // 设置节点填充颜色。
        context.fill(); // 填充节点圆。
        state.hitTargets.push({ kind: "node", id: node.id, type: "point", point: screen, depth: screen.depth }); // 保存节点拾取点。
    }); // 结束节点遍历。
    const boxEdges = [[0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3], [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7]]; // 定义包围盒十二条边。
    (state.document.regions || []).forEach((region) => { // 遍历并绘制三维区域。
        const geometry = region.geometry || {}; // 读取区域几何。
        const color = sourceColors[region.source] || "#9eb3bc"; // 根据来源选择颜色。
        const selected = state.selection?.kind === "region" && state.selection.id === region.id; // 判断区域是否选中。
        const alpha = region.status === "rejected" || region.active === false ? 0.22 : 0.82; // 根据状态设置透明度。
        if (geometry.kind === "box") { // 绘制包围盒区域。
            const corners = boxCorners(geometry); // 计算区域八个角点。
            const projected = corners.map((corner) => project(corner, cssWidth, cssHeight)); // 投影全部角点。
            boxEdges.forEach(([firstIndex, secondIndex]) => { drawLine(context, projected[firstIndex], projected[secondIndex], colorWithAlpha(color, alpha), selected ? 3 : 1.6, region.status === "rejected" ? [5, 4] : []); }); // 绘制区域十二条边。
            const center = project(geometry.center, cssWidth, cssHeight); // 投影区域中心用于拾取。
            if (center) { state.hitTargets.push({ kind: "region", id: region.id, type: "point", point: center, depth: center.depth, radius: 14 }); } // 保存区域中心拾取点。
        } else if (geometry.kind === "sphere") { // 绘制球形区域的屏幕近似圆。
            const center = project(geometry.center, cssWidth, cssHeight); // 投影球心。
            const edge = project([geometry.center[0] + geometry.radius, geometry.center[1], geometry.center[2]], cssWidth, cssHeight); // 投影一个半径端点。
            if (center && edge) { context.beginPath(); context.strokeStyle = colorWithAlpha(color, alpha); context.lineWidth = selected ? 3 : 1.6; context.arc(center.x, center.y, Math.hypot(edge.x - center.x, edge.y - center.y), 0, Math.PI * 2); context.stroke(); state.hitTargets.push({ kind: "region", id: region.id, type: "point", point: center, depth: center.depth, radius: 14 }); } // 绘制球形区域并保存拾取点。
        } // 结束区域几何类型处理。
    }); // 结束区域遍历。
    context.restore(); // 恢复绘图状态。
    requestAnimationFrame(renderScene); // 请求下一帧持续响应交互。
} // 结束场景渲染函数。

function colorWithAlpha(hex, alpha) { // 把十六进制颜色转换为带透明度的 rgba。
    const value = hex.replace("#", ""); // 去除颜色前缀。
    const red = parseInt(value.slice(0, 2), 16); // 解析红色分量。
    const green = parseInt(value.slice(2, 4), 16); // 解析绿色分量。
    const blue = parseInt(value.slice(4, 6), 16); // 解析蓝色分量。
    return `rgba(${red},${green},${blue},${alpha})`; // 返回 rgba 字符串。
} // 结束颜色透明度函数。

function pointSegmentDistance(point, first, second) { // 计算二维点到线段距离。
    const dx = second.x - first.x; // 计算线段 X 方向。
    const dy = second.y - first.y; // 计算线段 Y 方向。
    const denominator = dx * dx + dy * dy; // 计算线段长度平方。
    const parameter = denominator > 0 ? clamp(((point.x - first.x) * dx + (point.y - first.y) * dy) / denominator, 0, 1) : 0; // 计算最近点参数。
    const nearestX = first.x + parameter * dx; // 计算最近点 X 坐标。
    const nearestY = first.y + parameter * dy; // 计算最近点 Y 坐标。
    return Math.hypot(point.x - nearestX, point.y - nearestY); // 返回点线段距离。
} // 结束点线段距离函数。

function pickAt(x, y) { // 根据画布坐标选择最近构件、节点或区域。
    const candidates = []; // 初始化拾取候选列表。
    state.hitTargets.forEach((target) => { // 遍历本帧可拾取对象。
        let distance = Infinity; // 初始化候选距离。
        if (target.type === "point") { distance = Math.hypot(x - target.point.x, y - target.point.y); } // 计算点对象距离。
        if (target.type === "segment") { distance = pointSegmentDistance({ x, y }, target.first, target.second); } // 计算线段对象距离。
        const threshold = target.radius || (target.kind === "component" ? 9 : 11); // 根据对象类型设置拾取阈值。
        if (distance <= threshold) { candidates.push({ ...target, distance }); } // 保存阈值内候选。
    }); // 结束拾取候选遍历。
    candidates.sort((a, b) => a.distance - b.distance || a.depth - b.depth || (a.kind === "region" ? -1 : 1)); // 按距离、深度和区域优先级排序。
    return candidates[0] || null; // 返回最近候选或空。
} // 结束拾取函数。

function selectedObject() { // 根据当前选择状态返回 BSDL 对象。
    if (!state.document || !state.selection) { return null; } // 无文档或选择时返回空。
    const collection = state.selection.kind === "component" ? "components" : (state.selection.kind === "node" ? "nodes" : "regions"); // 把选择类型映射到文档集合。
    return (state.document[collection] || []).find((item) => item.id === state.selection.id) || null; // 查找并返回对象。
} // 结束选择对象函数。

function selectObject(kind, id) { // 更新当前选择并刷新属性面板。
    state.selection = kind && id ? { kind, id } : null; // 保存选择状态。
    const object = selectedObject(); // 获取选中对象。
    elements.selectionBadge.textContent = object ? `${kind} · ${id}` : "未选择对象"; // 更新场景选择标识。
    elements.objectJson.textContent = JSON.stringify(object || {}, null, 2); // 更新对象 JSON 视图。
    renderObjectEditor(object, kind); // 更新对象属性编辑器。
} // 结束对象选择函数。

function renderObjectEditor(object, kind) { // 根据对象类型生成属性编辑器。
    const container = elements.objectEditor; // 获取编辑器容器。
    container.innerHTML = ""; // 清空旧编辑器内容。
    if (!object) { container.className = "editor empty"; container.textContent = "在三维视图中选择构件、节点或区域。"; return; } // 处理无选择状态。
    container.className = "editor"; // 设置正常编辑器样式。
    const title = document.createElement("div"); // 创建对象标题。
    title.innerHTML = `<strong>${escapeHtml(object.name || object.id)}</strong><br><span style="color:#6f8f9c">${escapeHtml(object.id)}</span>`; // 显示对象名称和 ID。
    container.appendChild(title); // 加入对象标题。
    if (kind !== "region") { // 处理构件和节点只读摘要。
        const details = document.createElement("div"); // 创建只读详情区。
        details.style.color = "#86a2af"; // 设置详情文本颜色。
        details.style.lineHeight = "1.55"; // 设置详情行高。
        details.textContent = kind === "component" ? `类别：${object.category}\n拓扑：${object.topology}\n节点：${(object.nodeRefs || []).join(", ")}\n分析单元：${object.analysis?.elementType || "-"}` : `坐标：${(object.position || []).join(", ")}\n角色：${(object.roles || []).join(", ")}\n约束：${Object.entries(object.constraints || {}).filter(([, value]) => value).map(([key]) => key).join(", ") || "无"}`; // 组装构件或节点摘要。
        container.appendChild(details); // 加入详情区。
        const focusButton = document.createElement("button"); // 创建聚焦按钮。
        focusButton.className = "secondary"; // 设置次级按钮样式。
        focusButton.textContent = "聚焦对象"; // 设置按钮文本。
        focusButton.addEventListener("click", focusSelection); // 绑定聚焦操作。
        container.appendChild(focusButton); // 加入聚焦按钮。
        return; // 结束只读对象编辑器。
    } // 结束非区域对象处理。
    const semanticLabel = fieldSelect("语义类型", "regionSemanticType", ["support", "joint", "discontinuity", "smooth", "hotspot", "boundary", "user_defined"], object.semanticType); // 创建语义类型选择器。
    const sourceLabel = fieldSelect("来源", "regionSource", ["human", "agent", "fea", "imported"], object.source); // 创建来源选择器。
    const statusLabel = fieldSelect("状态", "regionStatus", ["proposed", "accepted", "rejected", "needs_review", "archived"], object.status); // 创建状态选择器。
    const levelLabel = fieldNumber("网格等级 0–10", "regionMeshLevel", object.meshLevel, 1); // 创建网格等级输入。
    const sizeLabel = fieldNumber("目标尺寸 m", "regionTargetSize", object.targetSize, 0.05); // 创建目标尺寸输入。
    container.append(semanticLabel, sourceLabel, statusLabel, levelLabel, sizeLabel); // 加入区域基础字段。
    if (object.geometry?.kind === "box") { // 处理包围盒区域几何编辑。
        container.appendChild(tripleField("中心 XYZ", "regionCenter", object.geometry.center)); // 加入中心三分量输入。
        container.appendChild(tripleField("尺寸 XYZ", "regionSize", object.geometry.size)); // 加入尺寸三分量输入。
    } // 结束包围盒几何编辑。
    const activeLabel = document.createElement("label"); // 创建活跃状态标签。
    activeLabel.innerHTML = `<span>参与策略</span><select id="regionActive"><option value="true">是</option><option value="false">否</option></select>`; // 创建布尔选择器。
    activeLabel.querySelector("select").value = String(object.active !== false); // 设置当前活跃状态。
    container.appendChild(activeLabel); // 加入活跃状态字段。
    const actions = document.createElement("div"); // 创建区域编辑操作区。
    actions.className = "actions"; // 设置操作区样式。
    const applyButton = document.createElement("button"); // 创建应用区域修改按钮。
    applyButton.textContent = "应用区域修改"; // 设置按钮文本。
    applyButton.addEventListener("click", applyRegionEdits); // 绑定区域修改处理。
    actions.appendChild(applyButton); // 加入应用按钮。
    container.appendChild(actions); // 加入操作区。
} // 结束对象编辑器渲染函数。

function fieldSelect(labelText, id, options, value) { // 创建标准选择字段。
    const label = document.createElement("label"); // 创建字段标签。
    const select = document.createElement("select"); // 创建选择控件。
    select.id = id; // 设置控件 ID。
    options.forEach((optionValue) => { const option = document.createElement("option"); option.value = optionValue; option.textContent = optionValue; select.appendChild(option); }); // 加入全部选项。
    select.value = value; // 设置当前值。
    const span = document.createElement("span"); // 创建字段标题。
    span.textContent = labelText; // 设置字段标题文本。
    label.append(span, select); // 组装标签与选择控件。
    return label; // 返回完整字段。
} // 结束选择字段函数。

function fieldNumber(labelText, id, value, step) { // 创建标准数值输入字段。
    const label = document.createElement("label"); // 创建字段标签。
    const input = document.createElement("input"); // 创建数值输入控件。
    input.type = "number"; // 设置输入类型。
    input.id = id; // 设置控件 ID。
    input.step = String(step); // 设置输入步长。
    input.value = String(value ?? 0); // 设置当前数值。
    const span = document.createElement("span"); // 创建字段标题。
    span.textContent = labelText; // 设置字段标题文本。
    label.append(span, input); // 组装标签与输入控件。
    return label; // 返回完整字段。
} // 结束数值字段函数。

function tripleField(labelText, prefix, values) { // 创建三分量数值输入字段。
    const label = document.createElement("label"); // 创建字段标签。
    const span = document.createElement("span"); // 创建字段标题。
    span.textContent = labelText; // 设置字段标题文本。
    const row = document.createElement("div"); // 创建三分量布局容器。
    row.className = "triple"; // 设置三列布局样式。
    [0, 1, 2].forEach((index) => { const input = document.createElement("input"); input.type = "number"; input.step = "0.05"; input.id = `${prefix}${index}`; input.value = String(values?.[index] ?? 0); row.appendChild(input); }); // 创建 X、Y、Z 三个输入。
    label.append(span, row); // 组装标题与三分量控件。
    return label; // 返回完整字段。
} // 结束三分量字段函数。

function escapeHtml(value) { // 转义用于 innerHTML 的文本。
    return String(value).replace(/[&<>"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[character])); // 返回安全 HTML 文本。
} // 结束 HTML 转义函数。

function syncMeshPolicyRegion(region) { // 把区域参数同步到当前 MeshPolicy 区域规则。
    const policy = (state.document.meshPolicies || [])[0]; // 选择当前首个网格策略。
    if (!policy) { return; } // 无策略时直接返回。
    policy.regionRules = policy.regionRules || []; // 确保区域规则数组存在。
    const existing = policy.regionRules.find((rule) => rule.regionRef === region.id); // 查找已有区域规则。
    const priorityByType = { support: 95, joint: 85, discontinuity: 80, hotspot: 95, boundary: 75, user_defined: 100, smooth: 20 }; // 定义前端同步优先级。
    if (region.active === false || region.status === "rejected") { policy.regionRules = policy.regionRules.filter((rule) => rule.regionRef !== region.id); return; } // 对无效区域删除策略规则。
    const value = { regionRef: region.id, targetSize: Number(region.targetSize), priority: priorityByType[region.semanticType] || 50 }; // 构造区域规则。
    if (existing) { Object.assign(existing, value); } else { policy.regionRules.push(value); } // 更新已有规则或新增规则。
} // 结束网格策略同步函数。

function appendHumanFeedback(kind, targetRefs, before, after, comment) { // 在当前文档中追加人工交互反馈记录。
    state.document.feedback = state.document.feedback || []; // 确保反馈数组存在。
    const id = `feedback.human.${Date.now()}`; // 生成当前会话唯一反馈 ID。
    state.document.feedback.push({ id, source: "human", kind, createdAt: new Date().toISOString(), createdBy: "human.web", targetRefs, before, after, metrics: {}, comment, status: "recorded" }); // 保存结构化人工反馈。
} // 结束人工反馈函数。

function applyRegionEdits() { // 把属性面板中的区域参数写回 BSDL 文档。
    const region = selectedObject(); // 获取选中区域。
    if (!region || state.selection?.kind !== "region") { return; } // 检查选中对象类型。
    const before = deepClone(region); // 保存修改前区域快照。
    region.semanticType = document.getElementById("regionSemanticType").value; // 更新语义类型。
    region.source = document.getElementById("regionSource").value; // 更新来源类型。
    region.status = document.getElementById("regionStatus").value; // 更新区域状态。
    region.meshLevel = clamp(Number(document.getElementById("regionMeshLevel").value), 0, 10); // 更新网格等级。
    region.targetSize = Math.max(Number(document.getElementById("regionTargetSize").value), 1e-6); // 更新目标尺寸。
    region.active = document.getElementById("regionActive").value === "true"; // 更新活跃状态。
    if (region.geometry?.kind === "box") { region.geometry.center = [0, 1, 2].map((index) => Number(document.getElementById(`regionCenter${index}`).value)); region.geometry.size = [0, 1, 2].map((index) => Math.max(Number(document.getElementById(`regionSize${index}`).value), 1e-6)); } // 更新包围盒中心与尺寸。
    syncMeshPolicyRegion(region); // 同步当前网格策略。
    appendHumanFeedback("region_edit", [region.id], before, deepClone(region), "在三维区域属性面板中修改参数。"); // 保存人工编辑证据。
    refreshDocumentViews(); // 刷新 JSON、摘要和属性面板。
    log(`已修改区域 ${region.id}，保存 V+ 后进入版本库。`, "success"); // 记录编辑结果。
} // 结束区域编辑函数。

function addHumanRegion() { // 在当前结构中新增一个人工三维区域框。
    if (!state.document) { return; } // 无项目时不执行。
    const selected = selectedObject(); // 获取当前选中对象。
    let center = state.camera.target.slice(); // 默认使用相机目标作为区域中心。
    let targets = []; // 初始化区域目标对象列表。
    if (state.selection?.kind === "node" && selected?.position) { center = selected.position.slice(); targets = [selected.id]; } // 节点选择时围绕节点建立区域。
    if (state.selection?.kind === "component") { const endpoints = componentEndpoints(selected); if (endpoints) { center = vectorScale(vectorAdd(endpoints[0], endpoints[1]), 0.5); targets = [selected.id, ...(selected.nodeRefs || [])]; } } // 构件选择时围绕构件中点建立区域。
    if (state.selection?.kind === "region" && selected?.geometry?.center) { center = selected.geometry.center.slice(); targets = selected.targetRefs?.slice() || []; } // 区域选择时复制其中心和目标。
    const policy = (state.document.meshPolicies || [])[0]; // 读取当前网格策略。
    const baseSize = Number(policy?.baseSize || 1); // 读取全局基准尺寸。
    const region = { id: `region.human.user_defined.${Date.now()}`, name: `人工区域${(state.document.regions || []).filter((item) => item.source === "human").length + 1}`, semanticType: "user_defined", source: "human", geometry: { kind: "box", center, size: [baseSize * 3, baseSize * 3, baseSize * 3], rotation: [0, 0, 0] }, targetRefs: targets, active: true, meshLevel: 5, targetSize: Math.max(baseSize * 0.45, 0.01), elementFamily: "frame", amrEngine: "rule_based", maxIterations: 4, reason: ["人工在三维界面新增区域"], confidence: 1, status: "accepted", evidenceRefs: [], attributes: { createdInWeb: true } }; // 构造符合 BSDL Schema 的人工区域。
    state.document.regions = state.document.regions || []; // 确保区域数组存在。
    state.document.regions.push(region); // 把人工区域加入文档。
    syncMeshPolicyRegion(region); // 把区域加入当前网格策略。
    appendHumanFeedback("region_edit", [region.id], null, deepClone(region), "在三维视图中新建人工区域框。"); // 保存区域新增证据。
    selectObject("region", region.id); // 选择新建区域便于继续编辑。
    refreshDocumentViews(); // 刷新文档视图。
    log(`已新增人工区域 ${region.id}。`, "success"); // 记录新增结果。
} // 结束人工区域新增函数。

function rejectSelectedRegion() { // 把选中区域标记为拒绝并退出网格策略。
    const region = selectedObject(); // 获取选中对象。
    if (!region || state.selection?.kind !== "region") { log("请先选择一个区域框。", "error"); return; } // 检查区域选择。
    const before = deepClone(region); // 保存拒绝前区域状态。
    region.active = false; // 禁止区域参与策略。
    region.status = "rejected"; // 标记区域已驳回。
    region.source = region.source === "human" ? "human" : region.source; // 保留原始来源。
    syncMeshPolicyRegion(region); // 从网格策略中删除区域规则。
    appendHumanFeedback("region_edit", [region.id], before, deepClone(region), "人工删除或驳回三维区域框。"); // 保存删除证据。
    refreshDocumentViews(); // 刷新界面。
    log(`区域 ${region.id} 已标记为 rejected，历史对象仍保留。`, "success"); // 说明审计保留行为。
} // 结束区域拒绝函数。

function refreshDocumentViews() { // 刷新所有由当前文档驱动的界面区域。
    if (!state.document) { return; } // 无文档时直接返回。
    elements.documentJson.value = JSON.stringify(state.document, null, 2); // 更新完整 BSDL JSON 编辑器。
    elements.sceneTitle.textContent = `${state.document.project?.name || state.projectId} · V${state.document.revision?.number || "?"}`; // 更新场景标题。
    state.currentRevision = Number(state.document.revision?.number || state.currentRevision || 1); // 同步当前修订号。
    renderProjectSummary(); // 更新项目摘要。
    renderCognitiveList(); // 更新有限元认知地图。
    renderMetricStrip(); // 更新指标条。
    const object = selectedObject(); // 重新获取选中对象引用。
    elements.objectJson.textContent = JSON.stringify(object || {}, null, 2); // 更新对象 JSON。
    renderObjectEditor(object, state.selection?.kind); // 更新属性编辑器。
} // 结束文档视图刷新函数。

function renderProjectSummary() { // 显示当前 BSDL 文档的核心规模和状态。
    if (!state.document) { elements.projectSummary.textContent = "尚未载入项目。"; return; } // 处理无项目状态。
    const activeRegions = (state.document.regions || []).filter((region) => region.active !== false && region.status !== "rejected"); // 统计活跃区域。
    const bySource = ["agent", "human", "fea", "imported"].map((source) => `${source}:${activeRegions.filter((region) => region.source === source).length}`).join(" · "); // 汇总区域来源。
    elements.projectSummary.innerHTML = `<strong>${escapeHtml(state.document.project?.name || state.projectId)}</strong><br>修订 V${state.document.revision?.number || "?"} · 节点 ${(state.document.nodes || []).length} · 构件 ${(state.document.components || []).length}<br>活跃区域 ${activeRegions.length}（${bySource}） · 经验引用 ${(state.document.experienceRefs || []).length}<br>任务 ${(state.document.analysisTasks || []).map((task) => task.name).join("、") || "未定义"}`; // 显示项目摘要和已读回经验数量。
} // 结束项目摘要函数。

function renderCognitiveList() { // 显示局部地标、结构特征和下一步网格动作。
    const container = elements.cognitiveList; // 获取认知地图列表容器。
    container.innerHTML = ""; // 清空旧地标列表。
    const map = state.document?.cognitiveMap || {}; // 读取当前认知地图。
    const landmarks = Array.isArray(map.landmarks) ? map.landmarks : []; // 读取局部结构地标。
    const edgeBySource = new Map((map.decisionEdges || []).map((edge) => [edge.fromRef, edge])); // 建立地标到决策边索引。
    if (!landmarks.length) { const empty = document.createElement("div"); empty.className = "list-item"; empty.textContent = "尚未生成认知地图；运行 Agent 策略后形成局部地标。"; container.appendChild(empty); return; } // 显示空状态。
    landmarks.slice(0, 60).forEach((landmark) => { // 遍历并显示有限数量的局部地标。
        const edge = edgeBySource.get(landmark.id); // 读取该地标对应的决策动作。
        const item = document.createElement("div"); // 创建地标列表项。
        item.className = "list-item"; // 设置地标列表样式。
        const feature = landmark.featureVector || {}; // 读取代表性结构特征。
        const featureText = [`degree=${feature.nodeDegree ?? "-"}`, `level=${feature.meshLevel ?? "-"}`, `size=${feature.targetSize ?? "-"}`].join(" · "); // 组装简要特征文本。
        item.innerHTML = `<div class="row"><strong>${escapeHtml(landmark.kind)}</strong><span>${Number(landmark.confidence || 0).toFixed(2)}</span></div><small>${escapeHtml(featureText)}<br>${escapeHtml(edge?.action || "待决策")}</small>`; // 渲染地标和动作。
        item.addEventListener("click", () => { const regionId = edge?.toRef; if ((state.document.regions || []).some((region) => region.id === regionId)) { selectObject("region", regionId); focusSelection(); return; } const target = (landmark.targetRefs || [])[0]; if ((state.document.components || []).some((component) => component.id === target)) { selectObject("component", target); focusSelection(); } else if ((state.document.nodes || []).some((node) => node.id === target)) { selectObject("node", target); focusSelection(); } }); // 点击地标时选择对应区域或结构对象。
        container.appendChild(item); // 把地标加入列表。
    }); // 结束地标遍历。
} // 结束认知地图渲染函数。

function renderMetricStrip() { // 显示网格和试算核心指标。
    const policy = (state.document?.meshPolicies || [])[0]; // 读取当前网格策略。
    const activeRegions = (state.document?.regions || []).filter((region) => region.active !== false && region.status !== "rejected").length; // 统计活跃区域数。
    const metrics = []; // 初始化指标数组。
    metrics.push([policy ? Number(policy.baseSize).toPrecision(3) : "-", "BASE SIZE m"]); // 加入基准尺寸指标。
    metrics.push([String(activeRegions), "ACTIVE REGIONS"]); // 加入活跃区域指标。
    if (state.result?.mesh?.stats) { metrics.push([String(state.result.mesh.stats.elementCount), "MESH ELEMENTS"]); } // 加入网格单元数。
    if (state.result?.globalMetrics) { metrics.push([Number(state.result.globalMetrics.maxVerticalDisplacement).toExponential(3), "MAX |UZ| m"]); metrics.push([Number(state.result.globalMetrics.relativeForceBalanceResidual).toExponential(2), "BALANCE"]); } // 加入位移和平衡指标。
    elements.metricStrip.innerHTML = metrics.map(([value, label]) => `<div class="metric"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`).join(""); // 渲染指标卡。
} // 结束指标条函数。

function drawRunChart() { // 绘制历次快速试算的位移和网格规模变化。
    const canvas = elements.runChart; // 获取试算趋势画布。
    if (!canvas) { return; } // 对缺失画布安全返回。
    const ratio = window.devicePixelRatio || 1; // 获取设备像素比。
    const widthCss = Math.max(canvas.clientWidth, 220); // 获取画布 CSS 宽度。
    const heightCss = Math.max(canvas.clientHeight, 94); // 获取画布 CSS 高度。
    canvas.width = Math.floor(widthCss * ratio); // 设置实际像素宽度。
    canvas.height = Math.floor(heightCss * ratio); // 设置实际像素高度。
    const context = canvas.getContext("2d"); // 获取二维绘图上下文。
    context.clearRect(0, 0, canvas.width, canvas.height); // 清空旧图形。
    context.save(); // 保存绘图状态。
    context.scale(ratio, ratio); // 把绘图坐标转换为 CSS 像素。
    context.fillStyle = "rgba(6,15,22,0.76)"; // 设置图表背景颜色。
    context.fillRect(0, 0, widthCss, heightCss); // 绘制图表背景。
    const succeeded = state.runs.filter((run) => run.status === "succeeded" && run.globalMetrics).slice().reverse(); // 按时间正序筛选成功运行。
    if (!succeeded.length) { // 处理尚无成功运行的状态。
        context.fillStyle = "#607e8b"; // 设置空状态文本颜色。
        context.font = "10px sans-serif"; // 设置空状态字体。
        context.fillText("完成试算后显示过程曲线", 10, 22); // 显示空状态提示。
        context.restore(); // 恢复绘图状态。
        return; // 结束无数据渲染。
    } // 结束无数据处理。
    const left = 28; // 设置左侧绘图区边距。
    const right = widthCss - 10; // 设置右侧绘图区边界。
    const top = 12; // 设置顶部绘图区边距。
    const bottom = heightCss - 20; // 设置底部绘图区边界。
    context.strokeStyle = "rgba(100,167,255,0.22)"; // 设置坐标轴颜色。
    context.lineWidth = 1; // 设置坐标轴线宽。
    context.beginPath(); // 开始坐标轴路径。
    context.moveTo(left, top); // 移动到纵轴顶部。
    context.lineTo(left, bottom); // 绘制纵轴。
    context.lineTo(right, bottom); // 绘制横轴。
    context.stroke(); // 输出坐标轴。
    const displacement = succeeded.map((run) => Number(run.globalMetrics.maxVerticalDisplacement || 0)); // 读取各次最大竖向位移。
    const elementCounts = succeeded.map((run) => Number(run.meshStats?.elementCount || 0)); // 读取各次网格单元数。
    const drawSeries = (values, color, offset) => { // 定义归一化折线绘制器。
        const maximum = Math.max(...values.map((value) => Math.abs(value)), 1.0e-15); // 计算当前序列归一化上限。
        const points = values.map((value, index) => { // 把每个数值转换为屏幕坐标。
            const x = values.length === 1 ? (left + right) * 0.5 : left + (right - left) * index / (values.length - 1); // 计算横坐标。
            const y = bottom - Math.abs(value) / maximum * (bottom - top - offset); // 计算归一化纵坐标。
            return { x, y }; // 返回屏幕点。
        }); // 完成屏幕点生成。
        if (points.length > 1) { // 检查是否可以绘制折线。
            context.beginPath(); // 开始折线路径。
            points.forEach((point, index) => { if (index === 0) { context.moveTo(point.x, point.y); } else { context.lineTo(point.x, point.y); } }); // 依次连接所有点。
            context.strokeStyle = color; // 设置折线颜色。
            context.lineWidth = 1.5; // 设置折线宽度。
            context.stroke(); // 输出折线。
        } // 结束折线绘制。
        points.forEach((point) => { // 遍历绘制数据点。
            context.beginPath(); // 开始圆点路径。
            context.arc(point.x, point.y, 2.3, 0, Math.PI * 2); // 创建数据点圆形。
            context.fillStyle = color; // 设置数据点颜色。
            context.fill(); // 填充数据点。
        }); // 结束数据点绘制。
    }; // 完成折线绘制器定义。
    drawSeries(displacement, "#ff5f93", 0); // 绘制最大竖向位移趋势。
    if (elementCounts.some((value) => value > 0)) { drawSeries(elementCounts, "#45d5ff", 8); } // 在可用时绘制网格规模趋势。
    context.fillStyle = "#86a2af"; // 设置图例文字颜色。
    context.font = "9px sans-serif"; // 设置图例字体。
    context.fillText("粉: |uz|max  蓝: elements", left + 4, heightCss - 6); // 显示曲线图例。
    context.fillText(`runs=${succeeded.length}`, right - 44, heightCss - 6); // 显示成功运行数量。
    context.restore(); // 恢复绘图状态。
} // 结束试算趋势图函数。

async function loadProjects(preferredProjectId = null) { // 从数据库加载项目列表并选择一个项目。
    state.projects = await api("/api/projects"); // 读取项目列表。
    elements.projectSelect.innerHTML = ""; // 清空旧项目选项。
    state.projects.forEach((project) => { const option = document.createElement("option"); option.value = project.projectId; option.textContent = `${project.name} · V${project.currentRevision}`; elements.projectSelect.appendChild(option); }); // 创建项目选择选项。
    const target = preferredProjectId || state.projectId || state.projects[0]?.projectId || null; // 确定需要载入的项目。
    if (target) { elements.projectSelect.value = target; await loadProject(target); } // 载入目标项目。
} // 结束项目列表加载函数。

async function loadProject(projectId, revision = null, fit = true) { // 读取指定项目修订并刷新完整界面。
    setBusy(true); // 锁定操作按钮。
    try { // 捕获项目读取错误。
        const query = revision ? `?revision=${revision}` : ""; // 构造可选修订查询参数。
        state.document = await api(`/api/projects/${encodeURIComponent(projectId)}${query}`); // 读取完整 BSDL 文档。
        state.projectId = projectId; // 保存当前项目 ID。
        state.currentRevision = Number(state.document.revision?.number || revision || 1); // 保存当前修订号。
        state.selection = null; // 清除旧项目选择对象。
        state.result = null; // 清除旧项目求解结果。
        elements.projectSelect.value = projectId; // 同步项目选择器。
        if (fit) { fitCamera(); } // 可选自动取景。
        await Promise.all([loadRevisions(), loadRuns(), loadExperiences()]); // 并行加载修订、运行和经验记录。
        selectObject(null, null); // 重置对象属性面板。
        refreshDocumentViews(); // 刷新所有文档驱动视图。
        log(`已载入 ${projectId} V${state.currentRevision}。`, "success"); // 记录载入结果。
    } catch (error) { log("项目载入失败。", "error", error.message); } finally { setBusy(false); } // 恢复操作按钮。
} // 结束项目载入函数。

async function loadRevisions() { // 读取并显示当前项目修订历史。
    if (!state.projectId) { return; } // 无项目时直接返回。
    state.revisions = await api(`/api/projects/${encodeURIComponent(state.projectId)}/revisions`); // 读取修订元数据。
    elements.revisionList.innerHTML = ""; // 清空旧修订列表。
    state.revisions.forEach((revision) => { const item = document.createElement("div"); item.className = `list-item ${revision.revision === state.currentRevision ? "active" : ""}`; item.innerHTML = `<div class="row"><strong>V${revision.revision}</strong><span>${escapeHtml(revision.source)}</span></div><small>${escapeHtml(revision.summary)}</small>`; item.addEventListener("click", () => loadProject(state.projectId, revision.revision, false)); elements.revisionList.appendChild(item); }); // 创建可点击修订列表。
} // 结束修订历史加载函数。

async function loadRuns() { // 读取并显示当前项目快速试算任务。
    if (!state.projectId) { return; } // 无项目时直接返回。
    state.runs = await api(`/api/projects/${encodeURIComponent(state.projectId)}/runs`); // 读取运行摘要。
    elements.runList.innerHTML = ""; // 清空旧运行列表。
    state.runs.forEach((run) => { const item = document.createElement("div"); item.className = "list-item"; const metric = run.globalMetrics ? `|uz|max=${Number(run.globalMetrics.maxVerticalDisplacement).toExponential(2)} · e=${run.meshStats?.elementCount ?? "-"}` : (run.error?.message || "无结果"); const created = run.createdAt ? new Date(run.createdAt).toLocaleString() : ""; item.innerHTML = `<div class="row"><strong>${escapeHtml(run.runId.slice(0, 18))}</strong><span class="status-${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></div><small>V${run.revision} · ${escapeHtml(created)}<br>${escapeHtml(metric)}</small>`; item.addEventListener("click", async () => { try { const full = await api(`/api/runs/${encodeURIComponent(run.runId)}`); if (full.result) { state.result = full.result; renderMetricStrip(); log(`已载入运行 ${run.runId} 结果。`, "success", full.result.globalMetrics); } else { log(`运行 ${run.runId} 没有成功结果。`, "error", full.error); } } catch (error) { log("运行读取失败。", "error", error.message); } }); elements.runList.appendChild(item); }); // 创建可点击运行列表。
    drawRunChart(); // 根据最新运行列表刷新试算过程曲线。
} // 结束运行列表加载函数。

async function loadExperiences() { // 读取并显示当前项目的局部经验记录。
    if (!state.projectId) { return; } // 无项目时直接返回。
    state.experiences = await api(`/api/experiences?projectId=${encodeURIComponent(state.projectId)}&limit=80`); // 按项目读取经验库。
    elements.experienceList.innerHTML = ""; // 清空旧经验列表。
    if (!state.experiences.length) { const empty = document.createElement("div"); empty.className = "list-item"; empty.textContent = "比较两个修订后可沉淀局部经验。"; elements.experienceList.appendChild(empty); return; } // 显示经验库空状态。
    state.experiences.forEach((record) => { // 遍历经验记录。
        const item = document.createElement("div"); // 创建经验列表项。
        item.className = "list-item"; // 设置经验列表样式。
        item.innerHTML = `<div class="row"><strong>${escapeHtml(record.scopeType)}</strong><span>${escapeHtml(record.outcome)}</span></div><small>V${record.revisionFrom}→V${record.revisionTo}<br>${escapeHtml(record.summary)}</small>`; // 显示版本、范围和经验摘要。
        item.addEventListener("click", () => log(`经验 ${record.experienceId}`, "info", record)); // 点击时在日志中展开完整经验对象。
        elements.experienceList.appendChild(item); // 把经验加入列表。
    }); // 结束经验遍历。
} // 结束经验库加载函数。

function populateTemplateFields(template) { // 把选中模板版本载入编辑表单。
    if (!template) { return; } // 对空模板安全返回。
    elements.templateKind.value = template.kind; // 设置模板类别。
    elements.templateId.value = template.templateId; // 设置稳定模板 ID。
    elements.templateName.value = template.name; // 设置模板名称。
    elements.templateBody.value = JSON.stringify(template.body || {}, null, 2); // 设置结构化模板正文。
    elements.templateDefault.checked = Boolean(template.isDefault); // 设置默认模板状态。
} // 结束模板字段填充函数。

function renderTemplateList() { // 根据当前类别显示模板版本。
    const kind = elements.templateKind.value; // 读取当前模板类别。
    const matches = state.templates.filter((template) => template.kind === kind); // 筛选同类模板版本。
    elements.templateList.innerHTML = ""; // 清空旧模板列表。
    if (!matches.length) { const empty = document.createElement("div"); empty.className = "list-item"; empty.textContent = "当前类别尚无模板版本。"; elements.templateList.appendChild(empty); return; } // 显示模板空状态。
    matches.forEach((template) => { // 遍历同类模板版本。
        const item = document.createElement("div"); // 创建模板列表项。
        item.className = "list-item"; // 设置模板列表样式。
        item.innerHTML = `<div class="row"><strong>${escapeHtml(template.name)}</strong><span>V${template.version}${template.isDefault ? " · default" : ""}</span></div><small>${escapeHtml(template.templateId)}</small>`; // 显示模板名称、版本和默认状态。
        item.addEventListener("click", () => populateTemplateFields(template)); // 点击时载入该模板版本。
        elements.templateList.appendChild(item); // 把模板加入列表。
    }); // 结束模板遍历。
    const preferred = matches.find((template) => template.isDefault) || matches[0]; // 选择默认或最新模板。
    if (!elements.templateId.value || elements.templateId.value === "template.custom") { populateTemplateFields(preferred); } // 初次加载时自动填充推荐模板。
} // 结束模板列表渲染函数。

async function loadTemplates() { // 从数据库加载全部知识与提示模板版本。
    state.templates = await api("/api/templates"); // 读取模板版本列表。
    renderTemplateList(); // 渲染当前类别模板。
} // 结束模板加载函数。

async function saveTemplateVersion() { // 保存当前表单为模板新版本。
    let body; // 声明结构化模板正文。
    try { body = JSON.parse(elements.templateBody.value); } catch (error) { log("模板正文必须是有效 JSON。", "error", error.message); return; } // 解析并检查模板 JSON。
    setBusy(true, "正在保存知识或提示模板新版本。"); // 锁定操作并记录状态。
    try { const response = await api("/api/templates", { method: "POST", body: JSON.stringify({ templateId: elements.templateId.value.trim(), name: elements.templateName.value.trim(), kind: elements.templateKind.value, body, makeDefault: elements.templateDefault.checked }) }); await loadTemplates(); log(`模板 ${response.templateId} V${response.version} 已保存。`, "success"); } catch (error) { log("模板保存失败。", "error", error.message); } finally { setBusy(false); } // 保存模板并恢复操作状态。
} // 结束模板保存函数。

async function validateCurrent() { // 调用后端验证当前数据库修订。
    if (!state.projectId) { return; } // 无项目时直接返回。
    setBusy(true, "正在执行 Schema、引用、拓扑和求解前检查。"); // 锁定操作并记录状态。
    try { const report = await api("/api/validate", { method: "POST", body: JSON.stringify({ document: state.document }) }); if (report.valid) { log(`当前会话文档验证通过：${report.level}，实体 ${report.stats.entities}，阻断错误 0。`, "success", report.stats); } else { log(`当前会话文档验证失败：${report.errors.length} 个阻断问题。`, "error", report.errors.slice(0, 12)); } } catch (error) { log("验证请求失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束当前验证函数。

async function generateStrategy() { // 执行全局分配器和局部多 expert 策略生成。
    if (!state.projectId) { return; } // 无项目时直接返回。
    setBusy(true, "正在运行全局分配、支承节点、突变、平滑与融合 expert。"); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/strategy`, { method: "POST", body: JSON.stringify({ revision: state.currentRevision, commit: true, author: "software.bridgemind", summary: "Web Demo 多专家区域策略", useMemory: true }) }); state.document = response.document; state.currentRevision = response.savedRevision?.revision || state.document.revision?.number; state.selection = null; refreshDocumentViews(); await Promise.all([loadRevisions(), loadRuns(), loadExperiences()]); const memory = response.memory || {}; log(`策略生成完成：${response.strategy.generatedRegionCount} 个新区域，融合后 ${response.strategy.finalRegionCount} 个；经验读回命中 ${memory.matchedRegionCount || 0} 个区域，实质修改 ${memory.appliedRegionCount || 0} 个。`, "success", { strategy: response.strategy, memory }); } catch (error) { log("Agent 策略生成失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束策略生成函数。

async function solveCurrent() { // 执行内置空间梁快速试算并写回 FEA 反馈。
    if (!state.projectId) { return; } // 无项目时直接返回。
    setBusy(true, "正在网格分段、组装空间梁刚度并执行反力平衡检查。"); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/solve`, { method: "POST", body: JSON.stringify({ revision: state.currentRevision, meshPolicyId: (state.document.meshPolicies || [])[0]?.id || null, loadCaseId: (state.document.loadCases || [])[0]?.id || null, commitFeedback: true, author: "software.bridgemind" }) }); state.result = response.result; if (response.feedbackDocument) { state.document = response.feedbackDocument; state.currentRevision = response.feedbackRevision?.revision || state.document.revision?.number; state.selection = null; refreshDocumentViews(); } await Promise.all([loadRevisions(), loadRuns(), loadExperiences()]); log(`快速试算完成：${response.result.mesh.stats.elementCount} 个单元，最大 |uz|=${Number(response.result.globalMetrics.maxVerticalDisplacement).toExponential(4)} m。`, "success", response.result.globalMetrics); } catch (error) { log("快速试算失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束快速试算函数。

async function saveCurrentRevision() { // 把当前浏览器内人工编辑保存为新修订。
    if (!state.projectId || !state.document) { return; } // 无项目时直接返回。
    setBusy(true, "正在验证并保存人工 V+ 修订。"); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/revisions`, { method: "POST", body: JSON.stringify({ document: state.document, author: "human.web", source: "human", summary: "Web 三维交互修改", status: "working" }) }); state.document = response.revision.document; state.currentRevision = response.revision.revision; refreshDocumentViews(); await loadRevisions(); log(`已保存 V${state.currentRevision}，内容哈希 ${response.revision.contentHash.slice(0, 12)}。`, "success"); } catch (error) { log("修订保存失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束修订保存函数。

async function archiveCurrentRevision() { // 把当前会话状态封存为新的归档修订。
    if (!state.projectId || !state.document) { return; } // 无项目时直接返回。
    setBusy(true, "正在验证并归档当前模型、策略和反馈状态。"); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/revisions`, { method: "POST", body: JSON.stringify({ document: state.document, author: "human.web", source: "human", summary: "人工确认并归档完整交互状态", status: "archived" }) }); state.document = response.revision.document; state.currentRevision = response.revision.revision; refreshDocumentViews(); await loadRevisions(); log(`已归档 V${state.currentRevision}，该快照可继续回读和比较。`, "success"); } catch (error) { log("归档修订失败。", "error", error.message); } finally { setBusy(false); } // 保存归档快照并恢复按钮状态。
} // 结束归档函数。

async function extractExperience() { // 比较最近两个修订并写入经验数据库。
    if (!state.projectId) { return; } // 无项目时直接返回。
    const revisions = state.revisions.map((item) => item.revision).sort((a, b) => a - b); // 获取升序修订号。
    const currentIndex = revisions.indexOf(state.currentRevision); // 查找当前修订位置。
    const previous = currentIndex > 0 ? revisions[currentIndex - 1] : null; // 获取前一修订号。
    if (!previous) { log("至少需要两个修订才能提取经验。", "error"); return; } // 检查修订数量。
    setBusy(true, `正在比较 V${previous} 与 V${state.currentRevision}。`); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/experiences/extract`, { method: "POST", body: JSON.stringify({ revisionFrom: previous, revisionTo: state.currentRevision, runId: state.runs[0]?.runId || null }) }); await loadExperiences(); log(`经验提取完成：${response.recordCount} 条局部结构—策略—结果记录。`, "success", response.records.map((record) => record.summary)); } catch (error) { log("经验提取失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束经验提取函数。

async function exportCurrent(adapter) { // 导出当前项目到 BSDL、Gmsh 或 CalculiX。
    if (!state.projectId) { return; } // 无项目时直接返回。
    setBusy(true, `正在导出 ${adapter}。`); // 锁定操作并记录状态。
    try { const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/export`, { method: "POST", body: JSON.stringify({ adapter, revision: state.currentRevision, meshPolicyId: (state.document.meshPolicies || [])[0]?.id || null, loadCaseId: (state.document.loadCases || [])[0]?.id || null }) }); const filename = response.output.split(/[\\/]/).pop(); elements.downloadArea.innerHTML = `<a href="/api/artifacts?path=${encodeURIComponent(filename)}">下载 ${escapeHtml(filename)}</a>`; log(`${adapter} 导出完成。`, response.report.blocked ? "error" : "success", response.report); } catch (error) { log(`${adapter} 导出失败。`, "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束项目导出函数。

async function checkCalculixStatus() { // 检测服务器是否配置真实 CalculiX 可执行程序。
    try { // 捕获网络和探测错误。
        const status = await api("/api/calculix/status"); // 请求服务器端 ccx 探测状态。
        elements.calculixStatus.className = `summary-card ${status.available ? "available" : "unavailable"}`; // 根据可用性设置状态样式。
        elements.calculixStatus.innerHTML = `<strong>${status.available ? "CalculiX 可用" : "CalculiX 未安装"}</strong><br>${escapeHtml(status.executable || status.requested || "ccx")}<br>${escapeHtml(status.message || "")}`; // 显示可执行路径和说明。
        log(status.available ? "服务器 CalculiX 探测通过。" : "服务器未找到 CalculiX，仍可导出和检查 INP。", status.available ? "success" : "info", status); // 写入探测日志。
        return status; // 返回探测结果供初始化或运行使用。
    } catch (error) { // 处理探测请求失败。
        elements.calculixStatus.className = "summary-card unavailable"; // 设置不可用样式。
        elements.calculixStatus.textContent = `CalculiX 状态检测失败：${error.message}`; // 显示探测失败原因。
        log("CalculiX 状态检测失败。", "error", error.message); // 写入错误日志。
        return null; // 返回空状态。
    } // 结束探测异常处理。
} // 结束 CalculiX 状态检测函数。

function selectedIndustrialReferences() { // 从当前 BSDL 文档读取工业求解默认引用。
    return { solverPlanId: (state.document?.solverPlans || [])[0]?.id || null, finiteElementModelId: (state.document?.finiteElementModels || [])[0]?.id || null, meshPolicyId: (state.document?.meshPolicies || [])[0]?.id || null, loadCaseId: (state.document?.loadCases || [])[0]?.id || null }; // 返回求解计划、FE 模型、网格策略和工况引用。
} // 结束工业引用读取函数。

async function runCalculixCurrent() { // 导出、静态检查、执行 CalculiX 并回写结果修订。
    if (!state.projectId) { return; } // 无项目时直接返回。
    const references = selectedIndustrialReferences(); // 读取当前工业模型引用。
    if (!references.solverPlanId || !references.finiteElementModelId) { log("当前项目缺少 solverPlans 或 finiteElementModels，不能执行工业求解。", "error"); openMobilePanel("left"); return; } // 阻止缺少工业模型的运行。
    setBusy(true, "正在生成 CalculiX deck、执行静态检查并调用服务器 ccx。"); // 锁定界面并记录运行状态。
    closeMobilePanels(); // 关闭移动侧栏以显示三维主视图。
    try { // 捕获转换、求解和结果回写错误。
        const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/calculix/run`, { method: "POST", body: JSON.stringify({ revision: state.currentRevision, ...references, strict: true, timeout: 3600, threads: Math.max(1, Math.min(8, navigator.hardwareConcurrency || 1)), actor: "human.web", commitResult: true }) }); // 发起完整 CalculiX 工业运行。
        log(`CalculiX 运行状态：${response.status}。`, response.status === "succeeded" ? "success" : (response.status === "unavailable" ? "info" : "error"), response.summary); // 显示运行状态和摘要。
        const downloadable = response.export?.downloadPath; // 读取可下载输入文件路径。
        if (downloadable) { elements.downloadArea.innerHTML = `<a href="/api/artifacts?path=${encodeURIComponent(downloadable)}">下载 CalculiX 输入与转换产物</a>`; } // 显示输入文件下载链接。
        if (response.resultCommit?.revision) { await loadProject(state.projectId, response.resultCommit.revision, false); } else { await loadRuns(); } // 成功回写时载入新修订，否则只刷新任务。
        await checkCalculixStatus(); // 刷新求解器状态。
    } catch (error) { // 处理运行链路失败。
        log("CalculiX 工业运行失败。", "error", error.message); // 写入错误日志。
        openMobilePanel("left"); // 在移动端打开项目面板查看日志。
    } finally { setBusy(false); } // 恢复界面操作。
} // 结束 CalculiX 工业运行函数。

function buildCodeCheckContext() { // 从快速预览或已导入 ResultSet 构造规则验算上下文。
    const metrics = state.result?.globalMetrics || {}; // 读取内置快速预览指标。
    const resultSets = state.document?.resultSets || []; // 读取文档中的 CalculiX 结果集。
    const latest = resultSets.length ? resultSets[resultSets.length - 1] : null; // 选择最近结果集。
    const fields = latest?.fields || []; // 读取最近结果字段。
    const displacement = fields.find((field) => field.name === "displacement")?.summary?.maximumMagnitude; // 读取 CalculiX 最大位移。
    const stress = fields.find((field) => field.name === "stress")?.summary?.maximumMagnitude; // 读取 CalculiX 最大应力张量模。
    return { maxDisplacement: displacement ?? metrics.maxTranslation ?? metrics.maxVerticalDisplacement ?? null, maxStress: stress ?? metrics.maxStress ?? null, reactionBalanceResidual: metrics.relativeForceBalanceResidual ?? null }; // 返回规则包约定的统一结果摘要。
} // 结束验算上下文构造函数。

async function runCodeCheckCurrent() { // 执行当前项目首个可审计验算计划。
    if (!state.projectId) { return; } // 无项目时直接返回。
    const plan = (state.document?.codeCheckPlans || [])[0]; // 读取首个项目验算计划。
    if (!plan) { log("当前项目没有 codeCheckPlans。", "error"); return; } // 阻止无计划验算。
    setBusy(true, `正在执行验算计划 ${plan.id}。`); // 锁定界面并记录验算状态。
    try { // 捕获规则包和修订错误。
        const response = await api(`/api/projects/${encodeURIComponent(state.projectId)}/code-checks/${encodeURIComponent(plan.id)}`, { method: "POST", body: JSON.stringify({ revision: state.currentRevision, resultContext: buildCodeCheckContext(), commit: true, actor: "human.web" }) }); // 执行规则包并保存结果。
        log(`验算完成：${response.report.status}。`, response.report.summary?.fail ? "error" : "success", response.report); // 显示验算统计和免责声明。
        if (response.resultRevision) { await loadProject(state.projectId, response.resultRevision, false); } // 载入包含验算结果的新修订。
    } catch (error) { log("规范验算失败。", "error", error.message); } finally { setBusy(false); } // 处理错误并恢复界面。
} // 结束规范验算函数。

async function importIfcFile() { // 上传 IFC 4.3 文件并执行项目 MVD 检查与 BSDL 映射。
    const file = elements.ifcFile.files[0]; // 读取用户选择的 IFC 文件。
    if (!file) { log("请先选择 IFC、IFCZIP 或 IFCXML 文件。", "error"); return; } // 检查文件选择。
    const form = new FormData(); // 创建多部分上传表单。
    form.append("file", file); // 加入 IFC 文件。
    setBusy(true, "正在执行 IFC 4.3 读取、项目 MVD 检查、身份映射和几何轻量化。"); // 锁定界面并记录导入状态。
    try { // 捕获 IfcOpenShell 依赖、MVD 和映射错误。
        const response = await api("/api/import/ifc", { method: "POST", body: form }); // 上传并导入 IFC 文件。
        log(`IFC 导入完成：MVD ${response.mvd.valid ? "通过" : "阻断"}。`, response.mvd.valid ? "success" : "error", response.conversionReport); // 显示 MVD 和转换报告。
        await loadProjects(response.project.projectId); // 载入新创建的 IFC 项目。
    } catch (error) { log("IFC 4.3 导入失败。", "error", error.message); } finally { setBusy(false); } // 处理错误并恢复界面。
} // 结束 IFC 导入函数。

async function importCalculixInp() { // 上传 CalculiX .inp 并创建显示-only BSDL 项目。
    const file = elements.inpFile.files[0]; // 读取用户选择的 .inp 文件。
    if (!file) { log("请先选择 CalculiX .inp 文件。", "error"); return; } // 检查文件选择。
    const form = new FormData(); // 创建多部分上传表单。
    form.append("file", file); // 加入 .inp 文件。
    setBusy(true, "正在执行 CalculiX .inp 兼容导入：显示 BSDL + 原生 deck 直通。"); // 锁定界面并记录导入状态。
    try { // 捕获解析和验证错误。
        const response = await api("/api/import/inp", { method: "POST", body: form }); // 上传并导入 .inp 文件。
        log(`CalculiX .inp 导入完成：${response.import?.stats?.elements || 0} 个单元（显示-only）。`, "success", response.import); // 显示导入统计。
        await loadProjects(response.project.projectId); // 载入新创建的导入项目。
    } catch (error) { log("CalculiX .inp 导入失败。", "error", error.message); } finally { setBusy(false); } // 处理错误并恢复界面。
} // 结束 CalculiX .inp 导入函数。

function updateOnlineStatus() { // 更新 PWA 在线和离线状态提示。
    if (elements.offlineBanner) { elements.offlineBanner.hidden = navigator.onLine; } // 根据浏览器网络状态切换提示。
} // 结束在线状态更新函数。

function setupPwa() { // 注册 Service Worker、安装提示和网络状态监听。
    if ("serviceWorker" in navigator) { navigator.serviceWorker.register("/service-worker.js").catch((error) => log("PWA 缓存注册失败。", "error", error.message)); } // 注册同源离线界面缓存。
    window.addEventListener("beforeinstallprompt", (event) => { event.preventDefault(); state.deferredInstall = event; if (elements.installButton) { elements.installButton.hidden = false; } }); // 捕获浏览器 PWA 安装事件。
    elements.installButton?.addEventListener("click", async () => { // 绑定 PWA 安装按钮。
        if (!state.deferredInstall) { log("当前浏览器尚未提供安装提示，可使用浏览器菜单中的添加到主屏幕。", "info"); return; } // 处理安装事件不可用状态。
        state.deferredInstall.prompt(); // 请求浏览器显示安装确认。
        await state.deferredInstall.userChoice; // 等待用户选择。
        state.deferredInstall = null; // 清空一次性安装事件。
        elements.installButton.hidden = true; // 隐藏安装按钮。
    }); // 结束安装按钮绑定。
    window.addEventListener("online", updateOnlineStatus); // 监听恢复网络事件。
    window.addEventListener("offline", updateOnlineStatus); // 监听断开网络事件。
    updateOnlineStatus(); // 初始化当前网络状态。
} // 结束 PWA 初始化函数。

async function importPointCloud() { // 上传点云并创建新的 BSDL 项目。
    const file = elements.pointCloudFile.files[0]; // 读取用户选择的点云文件。
    if (!file) { log("请先选择 XYZ、CSV 或 TXT 点云文件。", "error"); return; } // 检查文件选择。
    const form = new FormData(); // 创建多部分上传表单。
    form.append("file", file); // 加入点云文件。
    const eps = Number(elements.pointCloudEps.value); // 读取 DBSCAN 邻域半径。
    const voxel = Number(elements.pointCloudVoxel.value); // 读取体素尺寸。
    setBusy(true, "正在执行点云降采样、聚类、主方向分析和 BSDL 生成。"); // 锁定操作并记录状态。
    try { const response = await api(`/api/import/point-cloud?eps=${encodeURIComponent(eps)}&minSamples=6&voxelSize=${encodeURIComponent(voxel)}`, { method: "POST", body: form }); const projectId = response.project.projectId; log(`点云导入完成：${response.import.clusterCount} 个分割对象。`, "success", response.import); await loadProjects(projectId); } catch (error) { log("点云导入失败。", "error", error.message); } finally { setBusy(false); } // 恢复按钮状态。
} // 结束点云导入函数。

function applyFullDocument() { // 把全文 JSON 编辑器内容应用到当前会话文档。
    try { const parsed = JSON.parse(elements.documentJson.value); if (parsed.language !== "Bridge-Structural-Description-Language") { throw new Error("language 字段不是 BSDL。 "); } state.document = parsed; state.currentRevision = Number(parsed.revision?.number || state.currentRevision); state.selection = null; fitCamera(); selectObject(null, null); refreshDocumentViews(); log("全文 BSDL JSON 已应用到当前会话，尚未保存新修订。", "success"); } catch (error) { log("全文 JSON 应用失败。", "error", error.message); } // 解析、检查并应用全文文档。
} // 结束全文文档应用函数。

function focusSelection() { // 把相机目标移动到当前选中对象中心。
    const object = selectedObject(); // 获取选中对象。
    if (!object) { return; } // 无选择时直接返回。
    if (state.selection.kind === "node") { state.camera.target = object.position.slice(); } // 节点使用自身坐标。
    if (state.selection.kind === "component") { const endpoints = componentEndpoints(object); if (endpoints) { state.camera.target = vectorScale(vectorAdd(endpoints[0], endpoints[1]), 0.5); state.camera.distance = Math.max(vectorLength(vectorSubtract(endpoints[1], endpoints[0])) * 3, 8); } } // 构件使用中点和长度设置相机。
    if (state.selection.kind === "region") { state.camera.target = object.geometry?.center?.slice() || state.camera.target; state.camera.distance = Math.max(vectorLength(object.geometry?.size || [2, 2, 2]) * 3, 8); } // 区域使用中心和尺寸设置相机。
} // 结束聚焦函数。

function isMobileLayout() { // 判断当前界面是否采用移动抽屉布局。
    return window.matchMedia("(max-width: 900px)").matches; // 返回媒体查询匹配状态。
} // 结束移动布局判断函数。

function closeMobilePanels() { // 关闭手机端左右侧栏。
    document.body.classList.remove("mobile-left-open", "mobile-right-open"); // 移除两个侧栏打开状态。
    if (elements.mobileBackdrop) { elements.mobileBackdrop.hidden = true; } // 隐藏侧栏遮罩。
} // 结束关闭手机侧栏函数。

function openMobilePanel(side) { // 打开指定手机侧栏并关闭另一侧。
    if (!isMobileLayout()) { return; } // 桌面布局无需切换抽屉。
    document.body.classList.toggle("mobile-left-open", side === "left"); // 根据参数切换左侧栏。
    document.body.classList.toggle("mobile-right-open", side === "right"); // 根据参数切换右侧栏。
    if (elements.mobileBackdrop) { elements.mobileBackdrop.hidden = false; } // 显示侧栏遮罩。
} // 结束打开手机侧栏函数。

function gestureDistance(first, second) { // 计算两个触点之间的屏幕距离。
    return Math.hypot(second.x - first.x, second.y - first.y); // 返回触点欧氏距离。
} // 结束触点距离函数。

function gestureMidpoint(first, second) { // 计算两个触点的屏幕中点。
    return { x: (first.x + second.x) * 0.5, y: (first.y + second.y) * 0.5 }; // 返回触点中点。
} // 结束触点中点函数。

function clearLongPress() { // 清理尚未触发的长按计时器。
    if (state.touch.longPressTimer !== null) { window.clearTimeout(state.touch.longPressTimer); state.touch.longPressTimer = null; } // 取消计时器并清空引用。
} // 结束长按清理函数。

function panCameraByScreen(dx, dy, canvas) { // 根据屏幕位移平移三维相机目标。
    const scale = state.camera.distance / Math.max(200, Math.min(canvas.clientWidth, canvas.clientHeight)); // 根据相机距离计算世界空间移动比例。
    const cosine = Math.cos(state.camera.yaw); // 计算水平视角余弦。
    const sine = Math.sin(state.camera.yaw); // 计算水平视角正弦。
    state.camera.target[0] += (-dx * cosine + dy * sine * 0.25) * scale; // 在世界 X 方向平移目标。
    state.camera.target[1] += (dx * sine + dy * cosine * 0.25) * scale; // 在世界 Y 方向平移目标。
    state.camera.target[2] += dy * scale * 0.75; // 在世界 Z 方向平移目标。
} // 结束相机平移函数。

function bindCanvasEvents() { // 绑定鼠标、单指旋转、双指缩放平移、点击和长按事件。
    const canvas = elements.sceneCanvas; // 获取三维画布。
    canvas.addEventListener("pointerdown", (event) => { // 处理鼠标或触屏按下。
        event.preventDefault(); // 阻止浏览器滚动和手势抢占。
        canvas.setPointerCapture(event.pointerId); // 捕获当前指针直到释放。
        const point = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, startedAt: performance.now(), moved: false }; // 保存触点初始状态。
        state.touch.pointers.set(event.pointerId, point); // 把指针加入活动集合。
        clearLongPress(); // 清理旧长按计时器。
        if (state.touch.pointers.size === 1) { // 处理单指或鼠标旋转起点。
            state.drag = { active: true, moved: false, x: event.clientX, y: event.clientY }; // 初始化旋转拖动状态。
            state.touch.longPressTimer = window.setTimeout(() => { // 创建长按对象检查。
                const rect = canvas.getBoundingClientRect(); // 读取画布屏幕位置。
                const target = pickAt(point.startX - rect.left, point.startY - rect.top); // 拾取长按位置下的对象。
                if (target) { selectObject(target.kind, target.id); openMobilePanel("right"); navigator.vibrate?.(25); } // 选中对象、打开属性面板并提供轻触觉反馈。
                state.touch.longPressTimer = null; // 清空已触发计时器引用。
            }, 620); // 使用适合移动端的长按阈值。
        } else if (state.touch.pointers.size === 2) { // 处理双指手势起点。
            clearLongPress(); // 双指操作取消长按。
            const values = [...state.touch.pointers.values()]; // 读取两个活动触点。
            state.touch.gesture = { distance: gestureDistance(values[0], values[1]), midpoint: gestureMidpoint(values[0], values[1]), cameraDistance: state.camera.distance }; // 保存双指缩放和平移基准。
            state.drag.active = false; // 禁止双指期间继续单指旋转。
        } // 结束指针数量分支。
    }); // 结束按下事件。
    canvas.addEventListener("pointermove", (event) => { // 处理活动指针移动。
        const point = state.touch.pointers.get(event.pointerId); // 查找当前指针状态。
        if (!point) { return; } // 忽略未登记指针。
        const dxFromStart = event.clientX - point.startX; // 计算相对起点水平移动。
        const dyFromStart = event.clientY - point.startY; // 计算相对起点竖向移动。
        point.moved = point.moved || Math.abs(dxFromStart) + Math.abs(dyFromStart) > 5; // 根据移动阈值更新手势状态。
        point.x = event.clientX; // 更新触点水平坐标。
        point.y = event.clientY; // 更新触点竖向坐标。
        state.touch.pointers.set(event.pointerId, point); // 保存更新后的触点。
        if (point.moved) { clearLongPress(); } // 发生移动时取消长按。
        if (state.touch.pointers.size >= 2) { // 处理双指缩放和平移。
            const values = [...state.touch.pointers.values()].slice(0, 2); // 获取前两个活动触点。
            const currentDistance = Math.max(8, gestureDistance(values[0], values[1])); // 计算当前双指间距。
            const currentMidpoint = gestureMidpoint(values[0], values[1]); // 计算当前双指中点。
            if (!state.touch.gesture) { state.touch.gesture = { distance: currentDistance, midpoint: currentMidpoint, cameraDistance: state.camera.distance }; } // 补建手势基准。
            const ratio = state.touch.gesture.distance / currentDistance; // 计算捏合缩放比例。
            state.camera.distance = clamp(state.touch.gesture.cameraDistance * ratio, 1, 100000); // 应用双指缩放。
            panCameraByScreen(currentMidpoint.x - state.touch.gesture.midpoint.x, currentMidpoint.y - state.touch.gesture.midpoint.y, canvas); // 应用双指中点平移。
            state.touch.gesture.midpoint = currentMidpoint; // 更新平移基准避免累计重复。
            return; // 双指操作不继续执行单指旋转。
        } // 结束双指分支。
        if (!state.drag.active) { return; } // 无单指拖动时直接返回。
        const dx = event.clientX - state.drag.x; // 计算本帧水平位移。
        const dy = event.clientY - state.drag.y; // 计算本帧竖向位移。
        if (Math.abs(dx) + Math.abs(dy) > 2) { state.drag.moved = true; } // 标记拖动状态以区分点击。
        state.camera.yaw += dx * 0.008; // 更新水平旋转角。
        state.camera.pitch = clamp(state.camera.pitch + dy * 0.006, -1.35, 1.35); // 更新并限制俯仰角。
        state.drag.x = event.clientX; // 保存本帧水平位置。
        state.drag.y = event.clientY; // 保存本帧竖向位置。
    }); // 结束移动事件。
    const finishPointer = (event) => { // 统一处理指针释放和取消。
        const point = state.touch.pointers.get(event.pointerId); // 读取释放指针状态。
        clearLongPress(); // 清理长按计时器。
        if (point && state.touch.pointers.size === 1 && !point.moved && performance.now() - point.startedAt < 620) { // 检查短按选择手势。
            const rect = canvas.getBoundingClientRect(); // 读取画布位置。
            const target = pickAt(event.clientX - rect.left, event.clientY - rect.top); // 拾取点击位置对象。
            selectObject(target?.kind || null, target?.id || null); // 更新对象选择。
        } // 结束短按选择分支。
        state.touch.pointers.delete(event.pointerId); // 从活动集合移除指针。
        try { canvas.releasePointerCapture(event.pointerId); } catch (error) { void error; } // 安全释放指针捕获。
        state.touch.gesture = null; // 清空双指手势基准。
        state.drag.active = false; // 结束当前旋转拖动。
        if (state.touch.pointers.size === 1) { // 检查双指结束后是否剩余一个触点。
            const remaining = [...state.touch.pointers.values()][0]; // 读取剩余触点。
            state.drag = { active: true, moved: true, x: remaining.x, y: remaining.y }; // 从当前位置恢复单指旋转且避免误触选择。
        } // 结束剩余触点分支。
    }; // 完成统一释放处理函数。
    canvas.addEventListener("pointerup", finishPointer); // 绑定正常指针释放。
    canvas.addEventListener("pointercancel", finishPointer); // 绑定系统取消指针。
    canvas.addEventListener("wheel", (event) => { event.preventDefault(); state.camera.distance = clamp(state.camera.distance * Math.exp(event.deltaY * 0.0012), 1, 100000); }, { passive: false }); // 使用鼠标滚轮缩放相机。
    canvas.addEventListener("dblclick", () => focusSelection()); // 双击聚焦当前对象。
} // 结束画布事件绑定函数。

function bindControls() { // 绑定页面按钮和表单事件。
    elements.projectSelect.addEventListener("change", () => loadProject(elements.projectSelect.value)); // 绑定项目选择切换。
    elements.refreshButton.addEventListener("click", () => loadProjects(state.projectId)); // 绑定刷新项目按钮。
    elements.saveApiKeyButton.addEventListener("click", saveApiKeyAndConnect); // 绑定生产 API 密钥会话保存和重新连接按钮。
    elements.apiKeyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); saveApiKeyAndConnect(); } }); // 允许在密钥输入框按回车连接。
    elements.validateButton.addEventListener("click", validateCurrent); // 绑定验证按钮。
    elements.strategyButton.addEventListener("click", generateStrategy); // 绑定 Agent 策略按钮。
    elements.solveButton.addEventListener("click", solveCurrent); // 绑定快速试算按钮。
    elements.saveButton.addEventListener("click", saveCurrentRevision); // 绑定保存修订按钮。
    elements.archiveButton.addEventListener("click", archiveCurrentRevision); // 绑定归档修订按钮。
    elements.addRegionButton.addEventListener("click", addHumanRegion); // 绑定新增人工区域按钮。
    elements.deleteRegionButton.addEventListener("click", rejectSelectedRegion); // 绑定区域删除按钮。
    elements.experienceButton.addEventListener("click", extractExperience); // 绑定经验提取按钮。
    elements.resetViewButton.addEventListener("click", fitCamera); // 绑定重置视角按钮。
    elements.pointCloudButton.addEventListener("click", importPointCloud); // 绑定点云导入按钮。
    elements.templateKind.addEventListener("change", renderTemplateList); // 绑定模板类别切换。
    elements.saveTemplateButton.addEventListener("click", saveTemplateVersion); // 绑定模板版本保存。
    elements.exportBsdlButton.addEventListener("click", () => exportCurrent("bsdl")); // 绑定 BSDL 导出按钮。
    elements.exportGmshButton.addEventListener("click", () => exportCurrent("gmsh")); // 绑定 Gmsh 导出按钮。
    elements.exportCalculixButton.addEventListener("click", () => exportCurrent("calculix")); // 绑定 CalculiX 导出按钮。
    elements.calculixStatusButton.addEventListener("click", checkCalculixStatus); // 绑定 CalculiX 状态检测按钮。
    elements.runCalculixButton.addEventListener("click", runCalculixCurrent); // 绑定 CalculiX 工业求解按钮。
    elements.runCodeCheckButton.addEventListener("click", runCodeCheckCurrent); // 绑定规则验算按钮。
    elements.ifcImportButton.addEventListener("click", importIfcFile); // 绑定 IFC 4.3 导入按钮。
    elements.inpImportButton.addEventListener("click", importCalculixInp); // 绑定 CalculiX .inp 导入按钮。
    elements.applyDocumentButton.addEventListener("click", applyFullDocument); // 绑定全文 JSON 应用按钮。
    elements.copyObjectButton.addEventListener("click", async () => { try { await navigator.clipboard.writeText(elements.objectJson.textContent); log("选中对象 JSON 已复制。", "success"); } catch (error) { log("浏览器未授予剪贴板权限。", "error", error.message); } }); // 绑定对象 JSON 复制按钮并处理权限失败。
    elements.mobileProjectsButton.addEventListener("click", () => openMobilePanel("left")); // 绑定手机顶部项目面板按钮。
    elements.mobileInspectButton.addEventListener("click", () => openMobilePanel("right")); // 绑定手机顶部对象面板按钮。
    elements.closeLeftPanelButton.addEventListener("click", closeMobilePanels); // 绑定左侧抽屉关闭按钮。
    elements.closeRightPanelButton.addEventListener("click", closeMobilePanels); // 绑定右侧抽屉关闭按钮。
    elements.mobileBackdrop.addEventListener("click", closeMobilePanels); // 点击遮罩时关闭抽屉。
    elements.mobileProjectAction.addEventListener("click", () => openMobilePanel("left")); // 绑定底部项目快捷按钮。
    elements.mobileAgentAction.addEventListener("click", generateStrategy); // 绑定底部 Agent 策略按钮。
    elements.mobileSolveAction.addEventListener("click", solveCurrent); // 绑定底部快速预览按钮。
    elements.mobileCalculixAction.addEventListener("click", runCalculixCurrent); // 绑定底部 CalculiX 求解按钮。
    elements.mobileObjectAction.addEventListener("click", () => openMobilePanel("right")); // 绑定底部对象面板按钮。
    window.addEventListener("resize", resizeCanvas); // 绑定浏览器尺寸变化。
} // 结束控件事件绑定函数。

async function initialize() { // 初始化界面、事件和默认项目。
    cacheElements(); // 缓存 DOM 元素。
    bindCanvasEvents(); // 绑定三维画布事件。
    bindControls(); // 绑定页面控件事件。
    setupPwa(); // 注册 PWA 安装、离线缓存和网络状态。
    requestAnimationFrame(renderScene); // 启动持续场景渲染。
    elements.apiKeyInput.value = currentApiKey(); // 恢复当前标签会话中的 API 密钥且不使用持久化本地存储。
    try { // 分阶段检测公开端点和受保护项目数据。
        const health = await api("/api/health"); // 调用无需密钥的健康检查端点。
        const capabilities = await api("/api/capabilities"); // 读取服务器安全和运行能力矩阵。
        log(`BridgeMind Studio ${health.version} 已连接。`, "success"); // 记录后端服务连接成功。
        updateApiKeyStatus(Boolean(capabilities.security?.apiKeyAuthentication)); // 根据服务器配置更新访问控制提示。
        await checkCalculixStatus(); // 检测无需密钥的 CalculiX 运行状态。
        try { const preferred = new URLSearchParams(window.location.search).get("project"); await Promise.all([loadTemplates(), loadProjects(preferred)]); } catch (error) { if (error.status === 401) { updateApiKeyStatus(true, "请输入生产环境 API 密钥后加载项目。" ); openMobilePanel("left"); } else { throw error; } } // 在需要密钥时保留网站可操作状态并打开访问面板。
    } catch (error) { log("后端服务连接失败。", "error", error.message); } // 处理公开服务不可用或受保护数据异常。
} // 结束初始化函数。

document.addEventListener("DOMContentLoaded", initialize); // 在 DOM 就绪后启动应用。
