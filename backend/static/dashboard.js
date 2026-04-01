const appConfig = window.APP_CONFIG || {};
const pageContent = document.getElementById("page-content");
const logoutButton = document.getElementById("logout-button");
const generatedAt = document.getElementById("generated-at");
const siteName = document.getElementById("site-name");
const clockPill = document.getElementById("clock-pill");
const gpsStatus = document.getElementById("gps-status");
const systemLocation = document.getElementById("system-location");
const heroLocation = document.getElementById("hero-location");
const currentLocation = document.getElementById("current-location");
const crudModal = document.getElementById("crud-modal");
const crudModalForm = document.getElementById("crud-modal-form");
const crudModalTitle = document.getElementById("crud-modal-title");
const crudModalBody = document.getElementById("crud-modal-body");
const crudModalError = document.getElementById("crud-modal-error");
const crudModalSave = document.getElementById("crud-modal-save");

const state = {
  pageId: appConfig.pageId,
  data: null,
  maps: {},
  pageData: {},
  routeEditor: { routeId: null, selected: [] },
  pointDraft: {
    coords: null,
    zoneId: null,
    zoneName: "",
    marker: null,
  },
  deviceFilters: { keyword: "", status: "" },
  deviceImageDraft: { file: null, previewUrl: "", fileName: "" },
  robotDiscovery: {
    items: [],
    scannedAt: "",
    expiresAt: "",
    subnets: [],
    loading: false,
    error: "",
    selectedIp: "",
  },
  modal: { onSubmit: null },
  zoneDraft: {
    path: [],
    strokeColor: "#0db9f2",
    fillColor: "rgba(13, 185, 242, 0.18)",
    complete: false,
    clickTimer: null,
    pendingPoint: null,
  },
  geo: {
    coords: null,
    promise: null,
    status: "idle",
    watchId: null,
      locationText: null,
  },
  realtime: {
    socket: null,
    heartbeatTimer: null,
    reconnectTimer: null,
  },
};

const TOKEN_TEXT = {
  active: "运行中",
  charging: "充电中",
  critical: "严重",
  disabled: "已停用",
  degraded: "性能下降",
  fault: "故障",
  good: "良好",
  healthy: "正常",
  high: "高",
  idle: "待命",
  info: "提示",
  inspection: "巡检区",
  low: "低",
  medium: "中",
  neutral: "平稳",
  normal: "正常",
  offline: "离线",
  online: "在线",
  paused: "暂停",
  positive: "上升",
  repair: "维修中",
  restricted: "管控区",
  scheduled: "已排期",
  storage: "仓储区",
  warning: "告警",
};

const ZONE_PALETTE = [
  "#0db9f2",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#6366f1",
  "#14b8a6",
  "#eab308",
  "#f97316",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ");
}

function localizeToken(value) {
  const token = String(value || "").toLowerCase();
  return TOKEN_TEXT[token] || String(value || "-");
}

function formatRobotLocation(robot) {
  const location = Array.isArray(robot?.location) ? robot.location : [];
  if (location.length !== 2) return "-";
  const [lng, lat] = location;
  return `${formatCoordinate(lat)}, ${formatCoordinate(lng)}`;
}

function describeRobotNetwork(robot) {
  const status = localizeToken(robot.networkStatus || robot.telemetryStatus || "offline");
  const signal = Number.isFinite(Number(robot.signal)) ? `${robot.signal}%` : "-";
  return `${status} · 信号 ${signal}`;
}

function robotMarkerTitle(robot) {
  return `${robot.model} | ${localizeToken(robot.status)} | 网络 ${localizeToken(robot.networkStatus)} | 电量 ${robot.battery}%`;
}

function toRgba(hex, alpha = 0.18) {
  const normalized = String(hex || "").replace("#", "");
  if (normalized.length !== 6) return `rgba(13, 185, 242, ${alpha})`;
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function resetZoneDraft() {
  if (state.zoneDraft.clickTimer) {
    window.clearTimeout(state.zoneDraft.clickTimer);
    state.zoneDraft.clickTimer = null;
  }
  state.zoneDraft.pendingPoint = null;
  state.zoneDraft.path = [];
  state.zoneDraft.complete = false;
  syncZoneDraftUi();
  refreshZoneDraftPreview();
}

function updateZoneColor(color) {
  state.zoneDraft.strokeColor = color;
  state.zoneDraft.fillColor = toRgba(color);
  syncZoneDraftUi();
  refreshZoneDraftPreview();
}

function syncZoneDraftUi() {
  const pathField = document.querySelector('#zone-form [name="path"]');
  const strokeField = document.querySelector('#zone-form [name="strokeColor"]');
  const fillField = document.querySelector('#zone-form [name="fillColor"]');
  const status = document.getElementById("zone-draw-status");
  const preview = document.getElementById("zone-color-preview");
  const pointCount = state.zoneDraft.path.length;
  if (pathField) pathField.value = JSON.stringify(state.zoneDraft.path);
  if (strokeField) strokeField.value = state.zoneDraft.strokeColor;
  if (fillField) fillField.value = state.zoneDraft.fillColor;
  if (status) {
    if (!pointCount) {
      status.textContent = "地图单击加点，双击完成，右键撤销。";
    } else if (state.zoneDraft.complete) {
      status.textContent = `已完成绘制，共 ${pointCount} 个点。`;
    } else {
      status.textContent = `已选择 ${pointCount} 个点，至少 3 个点后可完成。`;
    }
  }
  if (preview) {
    preview.style.background = state.zoneDraft.strokeColor;
  }
  document.querySelectorAll("[data-zone-color]").forEach((button) => {
    button.classList.toggle("active", button.dataset.zoneColor === state.zoneDraft.strokeColor);
  });
}

function refreshZoneDraftPreview() {
  const entry = state.maps["zones-map"];
  if (!entry?.map) return;
  if (entry.draftPolyline) {
    entry.draftPolyline.setMap(null);
    entry.draftPolyline = null;
  }
  if (entry.draftPolygon) {
    entry.draftPolygon.setMap(null);
    entry.draftPolygon = null;
  }
  const path = state.zoneDraft.path;
  if (path.length >= 2) {
    entry.draftPolyline = new AMap.Polyline({
      map: entry.map,
      path,
      strokeColor: state.zoneDraft.strokeColor,
      strokeWeight: 3,
      strokeStyle: state.zoneDraft.complete ? "solid" : "dashed",
      bubble: true,
    });
  }
  if (path.length >= 3) {
    entry.draftPolygon = new AMap.Polygon({
      map: entry.map,
      path,
      strokeColor: state.zoneDraft.strokeColor,
      fillColor: state.zoneDraft.fillColor,
      fillOpacity: state.zoneDraft.complete ? 0.28 : 0.16,
      strokeWeight: 2,
      bubble: true,
    });
  }
}

function queueZonePoint(coords) {
  if (state.zoneDraft.clickTimer) {
    window.clearTimeout(state.zoneDraft.clickTimer);
  }
  state.zoneDraft.pendingPoint = coords;
  state.zoneDraft.clickTimer = window.setTimeout(() => {
    commitPendingZonePoint();
  }, 220);
}

function commitPendingZonePoint() {
  if (!state.zoneDraft.pendingPoint) return false;
  const lastPoint = state.zoneDraft.path[state.zoneDraft.path.length - 1] || null;
  const isDuplicatePoint = lastPoint
    && Math.abs(lastPoint[0] - state.zoneDraft.pendingPoint[0]) < 1e-6
    && Math.abs(lastPoint[1] - state.zoneDraft.pendingPoint[1]) < 1e-6;
  if (!isDuplicatePoint) {
    state.zoneDraft.path = [...state.zoneDraft.path, state.zoneDraft.pendingPoint];
  }
  state.zoneDraft.pendingPoint = null;
  state.zoneDraft.complete = false;
  if (state.zoneDraft.clickTimer) {
    window.clearTimeout(state.zoneDraft.clickTimer);
    state.zoneDraft.clickTimer = null;
  }
  syncZoneDraftUi();
  refreshZoneDraftPreview();
  return true;
}

function clearPendingZonePoint() {
  if (state.zoneDraft.clickTimer) {
    window.clearTimeout(state.zoneDraft.clickTimer);
    state.zoneDraft.clickTimer = null;
  }
  state.zoneDraft.pendingPoint = null;
}

function setupZoneDrawing(map) {
  if (typeof map.setStatus === "function") {
    map.setStatus({ doubleClickZoom: false });
  }
  map.on("click", (event) => {
    queueZonePoint([event.lnglat.getLng(), event.lnglat.getLat()]);
  });
  map.on("dblclick", () => {
    commitPendingZonePoint();
    if (state.zoneDraft.path.length >= 3) {
      state.zoneDraft.complete = true;
      syncZoneDraftUi();
      refreshZoneDraftPreview();
    }
  });
  map.on("rightclick", () => {
    if (state.zoneDraft.pendingPoint) {
      clearPendingZonePoint();
      syncZoneDraftUi();
      refreshZoneDraftPreview();
      return;
    }
    if (!state.zoneDraft.path.length) return;
    state.zoneDraft.path = state.zoneDraft.path.slice(0, -1);
    state.zoneDraft.complete = false;
    syncZoneDraftUi();
    refreshZoneDraftPreview();
  });
  syncZoneDraftUi();
  refreshZoneDraftPreview();
}

function padSerial(value) {
  return String(value).padStart(2, "0");
}

function nextDraftIndex(type, listName) {
  return ((state.data?.[listName]?.length || 0) + 1);
}

function todayLabel() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${month}-${day}`;
}

function friendlyDefaults(formName) {
  const draftIndexMap = {
    task: nextDraftIndex("task", "tasks"),
    robot: nextDraftIndex("robot", "robots"),
    alert: nextDraftIndex("alert", "alerts"),
    report: nextDraftIndex("report", "reports"),
    zone: nextDraftIndex("zone", "zones"),
  };
  const index = draftIndexMap[formName] || 1;
  const serial = padSerial(index);

  const defaults = {
    task: {
      name: `临港巡检任务-${serial}`,
      description: "重点检查主通道、围栏和设备点位。",
    },
    robot: {
      model: `巡检机器人-${serial}`,
    },
    alert: {
      title: `东侧通道异常告警-${serial}`,
      detail: "发现现场状态异常，请值班人员尽快核查。",
    },
    report: {
      title: `${todayLabel()} 巡检运行简报`,
      value: "98%",
      detail: "今日任务执行稳定，重点区域状态正常。",
      trend: "+2%",
    },
    zone: {
      name: `${index}号巡检区`,
      type: "inspection",
      frequency: "30分钟/次",
      notes: "覆盖主干道、设备柜和围栏转角。",
    },
  };

  return defaults[formName] || {};
}

function applyFriendlyFormDefaults(formName, form) {
  if (!form) return;
  const defaults = friendlyDefaults(formName);
  Object.entries(defaults).forEach(([name, value]) => {
    const field = form.elements.namedItem(name);
    if (!field) return;
    if (field.tagName === "SELECT") {
      field.value = value;
      return;
    }
    if (!field.value) {
      field.value = value;
    }
  });
}

function pillClass(value) {
  const token = String(value || "").toLowerCase();
  if (["critical", "offline", "danger"].includes(token)) return "pill critical";
  if (["warning", "degraded", "medium"].includes(token)) return "pill warning";
  if (["active", "healthy", "online", "good", "low", "positive"].includes(token)) return "pill healthy";
  return "pill";
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("登录状态已失效，请重新登录。");
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    throw new Error(payload?.detail || `请求失败：${response.status}`);
  }

  return payload;
}

async function loadDashboard() {
  const payload = await apiFetch("/api/dashboard");
  state.data = payload.data;
  renderShellMeta();
  renderCurrentPage();
}

function renderShellMeta() {
  if (!state.data) return;
  siteName.textContent = state.data.site.name;
  updateLocationLabels(state.geo.locationText || state.data.site.city);
  generatedAt.textContent = `最近更新时间：${formatDateTime(state.data.generatedAt)}`;
}

function setGpsStatus(text, tone = "") {
  if (!gpsStatus) return;
  gpsStatus.textContent = text;
  gpsStatus.className = `meta-pill${tone ? ` ${tone}` : ""}`;
}

function updateLocationLabels(text) {
  const label = text || state.data?.site?.city || "未知位置";
  if (systemLocation) systemLocation.textContent = label;
  if (heroLocation) heroLocation.textContent = label;
  if (currentLocation) currentLocation.textContent = `当前位置：${label}`;
}

async function reverseGeocode(coords) {
  if (typeof window.AMap === "undefined" || typeof window.AMap.Geocoder === "undefined") {
    return `${coords[1].toFixed(6)}, ${coords[0].toFixed(6)}`;
  }
  return new Promise((resolve) => {
    const geocoder = new AMap.Geocoder({ radius: 1000, extensions: "all" });
    geocoder.getAddress(coords, (status, result) => {
      if (status === "complete" && result?.regeocode) {
        const address = result.regeocode.formattedAddress;
        const component = result.regeocode.addressComponent || {};
        resolve(
          component.township ||
            component.street ||
            component.district ||
            component.city ||
            component.province ||
            address ||
            `${coords[1].toFixed(6)}, ${coords[0].toFixed(6)}`,
        );
        return;
      }
      resolve(`${coords[1].toFixed(6)}, ${coords[0].toFixed(6)}`);
    });
  });
}

async function applyGeoUpdate(coords, sourceLabel) {
  state.geo.coords = coords;
  state.geo.status = "ready";
  const locationText = await reverseGeocode(coords);
  state.geo.locationText = locationText;
  updateLocationLabels(locationText);
  setGpsStatus(`${sourceLabel}已定位`, "success");
  refreshMapsWithLocation();
  return coords;
}

async function locateWithBrowser() {
  if (!navigator.geolocation) {
    throw new Error("当前浏览器不支持 GPS 定位。");
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve([position.coords.longitude, position.coords.latitude]);
      },
      () => reject(new Error("浏览器定位失败或定位权限被拒绝。")),
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      },
    );
  });
}

async function locateWithAmap() {
  if (typeof window.AMap === "undefined") {
    throw new Error("高德地图尚未加载。");
  }
  return new Promise((resolve, reject) => {
    const geolocation = new AMap.Geolocation({
      enableHighAccuracy: true,
      timeout: 10000,
      zoomToAccuracy: false,
      convert: true,
    });
    geolocation.getCurrentPosition((status, result) => {
      if (status === "complete" && result?.position) {
        resolve([result.position.lng, result.position.lat]);
        return;
      }
      reject(new Error("高德定位失败。"));
    });
  });
}

async function ensureUserLocation() {
  if (state.geo.coords) {
    return state.geo.coords;
  }
  if (state.geo.promise) {
    return state.geo.promise;
  }

  state.geo.status = "locating";
  setGpsStatus("定位中");

  state.geo.promise = (async () => {
    try {
      const coords = await locateWithBrowser();
      return await applyGeoUpdate(coords, "GPS ");
    } catch (browserError) {
      try {
        const coords = await locateWithAmap();
        return await applyGeoUpdate(coords, "高德");
      } catch (amapError) {
        state.geo.status = "failed";
        setGpsStatus("定位失败", "danger");
        throw new Error(browserError.message || amapError.message);
      }
    } finally {
      state.geo.promise = null;
    }
  })();

  return state.geo.promise;
}

function renderStats() {
  const counts = state.data.counts;
  return `
    <section class="stats-grid">
      <article class="stat-card"><span>机器人</span><strong>${counts.robots}</strong><small class="muted">当前接入设备数</small></article>
      <article class="stat-card"><span>任务</span><strong>${counts.tasks}</strong><small class="muted">已创建巡检任务</small></article>
      <article class="stat-card"><span>告警</span><strong>${counts.alerts}</strong><small class="muted">待处理事件数量</small></article>
      <article class="stat-card"><span>区域</span><strong>${counts.zones}</strong><small class="muted">已管理巡检区域</small></article>
    </section>
  `;
}

function refreshMapsWithLocation() {
  const coords = state.geo.coords;
  if (!coords) return;
  Object.values(state.maps).forEach((entry) => {
    if (!entry?.map) return;
    entry.map.setCenter(coords);
    if (!entry.userMarker) {
      entry.userMarker = new AMap.Marker({
        map: entry.map,
        position: coords,
        title: "我的当前位置",
        label: { content: "我", direction: "top" },
        bubble: true,
      });
    } else {
      entry.userMarker.setPosition(coords);
    }
  });
}

function startLocationWatch() {
  if (!navigator.geolocation || state.geo.watchId !== null) {
    return;
  }
  state.geo.watchId = navigator.geolocation.watchPosition(
    async (position) => {
      const coords = [position.coords.longitude, position.coords.latitude];
      await applyGeoUpdate(coords, "GPS ");
    },
    () => {
      if (!state.geo.coords) {
        setGpsStatus("定位失败", "danger");
      }
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 10000,
    },
  );
}

function renderOverviewPage() {
  const robots = state.data.robots.slice(0, 4);
  const alerts = state.data.alerts.slice(0, 5);
  const zones = state.data.zones.slice(0, 4);
  return `
    ${renderStats()}
    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>机器人动态</h2><p class="muted">车队实时遥测信息</p></div></div>
        <div class="list-stack">
          ${robots.length ? robots.map((robot) => `
            <div class="list-item">
              <div>
                <strong>${escapeHtml(robot.model)}</strong>
                <p>${escapeHtml(robot.zoneName)} · 最近上报 ${escapeHtml(formatDateTime(robot.lastSeenAt || robot.createdAt))}</p>
                <div class="inline-meta">
                  <span class="${pillClass(robot.status)}">${escapeHtml(localizeToken(robot.status))}</span>
                  <span class="${pillClass(robot.networkStatus)}">网络 ${escapeHtml(localizeToken(robot.networkStatus))}</span>
                  <span class="meta-pill">电量 ${robot.battery}%</span>
                  <span class="meta-pill">信号 ${robot.signal}%</span>
                  <span class="meta-pill">健康度 ${robot.health}%</span>
                </div>
              </div>
              <div class="muted">位置 ${escapeHtml(formatRobotLocation(robot))} · 速度 ${robot.speed} m/s</div>
            </div>
          `).join("") : `<div class="empty-state">暂无机器人数据。</div>`}
        </div>
      </article>

      <article class="panel">
        <div class="panel-header"><div><h2>告警流</h2><p class="muted">最新事件记录</p></div></div>
        <div class="list-stack">
          ${alerts.length ? alerts.map((alert) => `
            <div class="list-item">
              <div>
                <strong>${escapeHtml(alert.title)}</strong>
                <p>${escapeHtml(alert.detail || "暂无详细说明。")}</p>
              </div>
              <div>
                <span class="${pillClass(alert.level)}">${escapeHtml(localizeToken(alert.level))}</span>
                <p class="muted">${formatDateTime(alert.happenedAt)}</p>
              </div>
            </div>
          `).join("") : `<div class="empty-state">暂无告警记录。</div>`}
        </div>
      </article>
    </section>
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>区域地图</h2><p class="muted">区域多边形与机器人位置</p></div></div>
        <div id="overview-map" class="map-shell"><div class="map-fallback">检测到高德地图后将在此渲染。</div></div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>重点区域</h2><p class="muted">优先关注的巡检区域</p></div></div>
        <div class="list-stack">
          ${zones.length ? zones.map((zone) => `
            <div class="list-item">
              <div>
                <strong>${escapeHtml(zone.name)}</strong>
                <p>${escapeHtml(localizeToken(zone.type))} · ${escapeHtml(zone.frequency)}</p>
              </div>
              <span class="${pillClass(zone.risk)}">${escapeHtml(localizeToken(zone.risk))}</span>
            </div>
          `).join("") : `<div class="empty-state">暂无区域配置。</div>`}
        </div>
      </article>
    </section>
  `;
}

function renderTasksPage() {
  return `
    ${renderStats()}
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>新建任务</h2><p class="muted">为机器人分配巡检时间窗口</p></div></div>
        <form id="task-form" class="stack-form">
          <div class="grid-form">
            <label><span>任务名称</span><input name="name" placeholder="例：临港主通道晨检任务" required></label>
            <label><span>优先级</span><select name="priority"><option value="low">低</option><option value="medium" selected>中</option><option value="high">高</option></select></label>
            <label><span>机器人 ID</span><input name="robotId" type="number"></label>
            <label><span>区域 ID</span><input name="zoneId" type="number"></label>
            <label><span>开始时间</span><input name="startAt" type="datetime-local" required></label>
            <label><span>结束时间</span><input name="endAt" type="datetime-local" required></label>
          </div>
          <label><span>任务说明</span><textarea name="description" placeholder="填写本次巡检范围、关注点和执行要求"></textarea></label>
          <div class="button-row"><button class="primary-button" type="submit">创建任务</button></div>
          <p class="form-error" data-form-error="task"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>任务列表</h2><p class="muted">当前巡检任务队列</p></div></div>
        ${renderTable("tasks", ["ID", "任务名称", "机器人", "区域", "时间窗口", "优先级", "状态", "操作"], state.data.tasks.map((task) => `
          <tr>
            <td>${task.id}</td>
            <td>${escapeHtml(task.name)}</td>
            <td>${escapeHtml(task.robotName)}</td>
            <td>${escapeHtml(task.zoneName)}</td>
            <td>${escapeHtml(task.window)}</td>
            <td><span class="${pillClass(task.priority)}">${escapeHtml(localizeToken(task.priority))}</span></td>
            <td><span class="${pillClass(task.status)}">${escapeHtml(localizeToken(task.status))}</span></td>
            <td><button class="danger-button" data-delete="tasks" data-id="${task.id}">删除</button></td>
          </tr>
        `))}
      </article>
    </section>
  `;
}

function renderReportsPage() {
  return `
    ${renderStats()}
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>新建报告卡片</h2><p class="muted">向总览页补充统计指标</p></div></div>
        <form id="report-form" class="stack-form">
          <div class="grid-form">
            <label><span>标题</span><input name="title" placeholder="例：当日巡检完成率" required></label>
            <label><span>指标值</span><input name="value" placeholder="例：98%" required></label>
            <label><span>趋势</span><input name="trend" value="+2%"></label>
            <label><span>趋势语义</span><select name="tone"><option value="neutral">持平</option><option value="positive">上升</option><option value="warning">预警</option></select></label>
            <label><span>报告日期</span><input name="reportDate" type="date" required></label>
          </div>
          <label><span>说明</span><textarea name="detail" placeholder="补充这个指标的业务解释"></textarea></label>
          <div class="button-row"><button class="primary-button" type="submit">创建报告</button></div>
          <p class="form-error" data-form-error="report"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>历史报告</h2><p class="muted">已有管理统计快照</p></div></div>
        <div class="metric-grid">
          ${state.data.reports.length ? state.data.reports.map((report) => `
            <article class="metric-card">
              <strong>${escapeHtml(report.title)}</strong>
              <div class="inline-meta">
                <span class="meta-pill">${escapeHtml(report.value)}</span>
                <span class="${pillClass(report.tone)}">${escapeHtml(report.trend)}</span>
              </div>
              <p>${escapeHtml(report.detail || "暂无说明。")}</p>
              <div class="button-row">
                <span class="muted">${escapeHtml(report.reportDate)}</span>
                <button class="danger-button" data-delete="reports" data-id="${report.id}">删除</button>
              </div>
            </article>
          `).join("") : `<div class="empty-state">暂无报告数据。</div>`}
        </div>
      </article>
    </section>
  `;
}

function renderStatusPage() {
  const discovery = state.robotDiscovery;
  const confirmedItems = discovery.items.filter((item) => item.confirmed);
  const selectedIp = confirmedItems.some((item) => item.ipAddress === discovery.selectedIp)
    ? discovery.selectedIp
    : "";
  const submitDisabled = !selectedIp || discovery.loading;
  return `
    ${renderStats()}
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>新增机器人</h2><p class="muted">必须先扫描当前 Wi-Fi 网络并确认机器人实体</p></div></div>
        <form id="robot-form" class="stack-form">
          <div class="grid-form">
            <label><span>名称</span><input name="model" placeholder="例：巡检机器人-01" required></label>
            <label class="field-span-2">
              <span>Wi-Fi 扫描确认</span>
              <div class="inline-meta robot-discovery-toolbar">
                <button class="secondary-button" id="robot-discovery-refresh" type="button"${discovery.loading ? " disabled" : ""}>${discovery.loading ? "扫描中..." : "扫描 Wi-Fi 网络"}</button>
                <span class="muted">${discovery.scannedAt ? `最近扫描：${escapeHtml(formatDateTime(discovery.scannedAt))}` : "尚未扫描"}</span>
              </div>
              <select id="robot-discovery-select" name="ipAddress" required${discovery.loading ? " disabled" : ""}>
                <option value="">请先扫描并选择已确认的机器人 IP</option>
                ${confirmedItems.map((item) => `
                  <option value="${escapeHtml(item.ipAddress)}"${item.ipAddress === selectedIp ? " selected" : ""}>
                    ${escapeHtml(item.ipAddress)} | ${escapeHtml(item.deviceName || item.hostName || "unknown")} | ${escapeHtml(item.summary || "")}
                  </option>
                `).join("")}
              </select>
              <small class="muted">${discovery.subnets?.length ? `扫描网段：${escapeHtml(discovery.subnets.join(", "))}` : "仅允许添加当前 Wi-Fi 网络中已识别的机器人。"}</small>
            </label>
            <label><span>区域 ID</span><input name="zoneId" type="number"></label>
            <label><span>状态</span><select name="status"><option value="idle">待命</option><option value="active">执行中</option><option value="charging">充电中</option><option value="offline">离线</option></select></label>
            <label><span>健康度</span><input name="health" type="number" value="92" min="0" max="100"></label>
            <label><span>电量</span><input name="battery" type="number" value="78" min="0" max="100"></label>
            <label><span>速度</span><input name="speed" type="number" step="0.1" value="1.2"></label>
            <label><span>信号</span><input name="signal" type="number" value="88" min="0" max="100"></label>
            <label><span>延迟</span><input name="latency" type="number" value="28"></label>
            <label><span>经度</span><input name="lng" type="number" step="0.000001" value="121.81742"></label>
            <label><span>纬度</span><input name="lat" type="number" step="0.000001" value="31.09161"></label>
            <label><span>航向角</span><input name="heading" type="number" value="0" min="0" max="359"></label>
          </div>
          ${discovery.error ? `<div class="form-error">${escapeHtml(discovery.error)}</div>` : ""}
          <div class="button-row"><button class="primary-button" type="submit"${submitDisabled ? " disabled" : ""}>添加机器人</button></div>
          <p class="form-error" data-form-error="robot"></p>
        </form>
        <div class="list-stack robot-discovery-list">
          ${discovery.items.length ? discovery.items.map((item) => `
            <div class="list-item robot-discovery-item${item.confirmed ? " confirmed" : ""}">
              <div>
                <strong>${escapeHtml(item.ipAddress)}</strong>
                <p>${escapeHtml(item.deviceName || item.hostName || "unknown host")} | MAC ${escapeHtml(item.macAddress || "-")}</p>
              </div>
              <div>
                <span class="${item.confirmed ? "pill healthy" : "pill warning"}">${item.confirmed ? "已确认" : "未确认"}</span>
                <p class="muted">ports: ${escapeHtml(formatPorts(item.openPorts))}</p>
              </div>
            </div>
          `).join("") : `<div class="empty-state">还没有扫描结果。</div>`}
        </div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>机器人状态板</h2><p class="muted">遥测与运行状态</p></div></div>
        ${renderTable("robots", ["ID", "机器人名称", "IP", "区域", "运行状态", "网络", "电量", "位置", "最近上报", "操作"], state.data.robots.map((robot) => `
          <tr>
            <td>${robot.id}</td>
            <td>${escapeHtml(robot.model)}</td>
            <td>${escapeHtml(robot.ipAddress || "-")}</td>
            <td>${escapeHtml(robot.zoneName)}</td>
            <td><span class="${pillClass(robot.status)}">${escapeHtml(localizeToken(robot.status))}</span></td>
            <td>
              <div class="inline-meta">
                <span class="${pillClass(robot.networkStatus)}">${escapeHtml(localizeToken(robot.networkStatus))}</span>
                <span class="muted">信号 ${robot.signal}%</span>
              </div>
            </td>
            <td>${robot.battery}%</td>
            <td>${escapeHtml(formatRobotLocation(robot))}</td>
            <td>${escapeHtml(formatDateTime(robot.lastSeenAt || robot.createdAt))}</td>
            <td><button class="danger-button" data-delete="robots" data-id="${robot.id}">删除</button></td>
          </tr>
        `))}
      </article>
    </section>
  `;
}

function renderMaintenancePage() {
  return `
    ${renderStats()}
    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>维护队列</h2><p class="muted">机器人健康与告警联动处理</p></div></div>
        <div class="list-stack">
          ${state.data.maintenance.length ? state.data.maintenance.map((item) => `
            <div class="list-item">
              <div>
                <strong>${escapeHtml(item.asset)}</strong>
                <p>${escapeHtml(item.zoneName)} · ${escapeHtml(item.summary)}</p>
              </div>
              <div>
                <span class="${pillClass(item.state)}">${escapeHtml(localizeToken(item.state))}</span>
                <p class="muted">${formatDateTime(item.lastCheck)}</p>
              </div>
            </div>
          `).join("") : `<div class="empty-state">暂无维护项。</div>`}
        </div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>手动创建告警</h2><p class="muted">供值班人员手动录入事件</p></div></div>
        <form id="alert-form" class="stack-form">
          <div class="grid-form">
            <label><span>等级</span><select name="level"><option value="info">提示</option><option value="warning" selected>告警</option><option value="critical">严重</option></select></label>
            <label><span>标题</span><input name="title" placeholder="例：东侧围栏异常告警" required></label>
            <label><span>发生时间</span><input name="happenedAt" type="datetime-local"></label>
          </div>
          <label><span>详情</span><textarea name="detail" placeholder="填写现场现象、影响范围和处理建议"></textarea></label>
          <div class="button-row"><button class="primary-button" type="submit">创建告警</button></div>
          <p class="form-error" data-form-error="alert"></p>
        </form>
      </article>
    </section>
  `;
}

function renderZonesPage() {
  return `
    ${renderStats()}
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>新建区域</h2><p class="muted">在地图上点选轮廓并选择区域颜色</p></div></div>
        <form id="zone-form" class="stack-form">
          <div class="grid-form">
            <label><span>区域名称</span><input name="name" placeholder="例：1号泊位巡检区" required></label>
            <label><span>区域类型</span><select name="type"><option value="inspection">巡检区</option><option value="charging">充电区</option><option value="storage">仓储区</option><option value="restricted">管控区</option></select></label>
            <label><span>风险等级</span><select name="risk"><option value="low">低</option><option value="medium" selected>中</option><option value="high">高</option></select></label>
            <label><span>状态</span><select name="status"><option value="active" selected>启用</option><option value="paused">暂停</option></select></label>
            <label><span>巡检频率</span><input name="frequency" value="30分钟/次"></label>
          </div>
          <input name="strokeColor" type="hidden">
          <input name="fillColor" type="hidden">
          <input name="path" type="hidden">
          <div class="inline-meta">
            <span class="meta-pill" id="zone-color-preview">色</span>
            <span class="muted" id="zone-draw-status">地图单击加点，双击完成，右键撤销。</span>
          </div>
          <div class="zone-palette">
            ${ZONE_PALETTE.map((color) => `<button class="zone-color-chip" type="button" data-zone-color="${color}" style="background:${color}"></button>`).join("")}
          </div>
          <label><span>备注</span><textarea name="notes" placeholder="说明区域用途、重点设备和巡检要求"></textarea></label>
          <div class="button-row">
            <button class="secondary-button" id="zone-reset-button" type="button">清空绘制</button>
            <button class="primary-button" type="submit">创建区域</button>
          </div>
          <p class="form-error" data-form-error="zone"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>区域列表</h2><p class="muted">已保存区域与风险标签</p></div></div>
        <div id="zones-map" class="map-shell"><div class="map-fallback">检测到高德地图后将在此渲染。</div></div>
        <div class="list-stack">
          ${state.data.zones.length ? state.data.zones.map((zone) => `
            <div class="list-item">
              <div>
                <strong>${escapeHtml(zone.name)}</strong>
                <p>${escapeHtml(localizeToken(zone.type))} · ${escapeHtml(zone.notes || "暂无备注")}</p>
              </div>
              <div>
                <span class="${pillClass(zone.risk)}">${escapeHtml(localizeToken(zone.risk))}</span>
                <p class="muted">${escapeHtml(zone.frequency)}</p>
                <div class="inline-meta">
                  <button class="secondary-button" type="button" data-zone-edit data-id="${zone.id}">编辑</button>
                  <button class="danger-button" type="button" data-zone-delete data-id="${zone.id}">删除</button>
                </div>
              </div>
            </div>
          `).join("") : `<div class="empty-state">暂无区域配置。</div>`}
        </div>
      </article>
    </section>
  `;
}

function renderLoadingPage(title, description) {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <h2>${escapeHtml(title)}</h2>
          <p class="muted">${escapeHtml(description)}</p>
        </div>
      </div>
      <div class="empty-state">加载中...</div>
    </section>
  `;
}

function renderSelectOptions(items, selectedValue = "", emptyLabel = "未设置") {
  const normalized = selectedValue === undefined || selectedValue === null ? "" : String(selectedValue);
  const options = [];
  if (emptyLabel !== null) {
    options.push(`<option value="">${escapeHtml(emptyLabel)}</option>`);
  }
  items.forEach((item) => {
    const value = String(item.id);
    const label = String(item.name || item.title || item.username || item.displayName || item.id);
    options.push(
      `<option value="${escapeHtml(value)}"${value === normalized ? " selected" : ""}>${escapeHtml(label)}</option>`,
    );
  });
  return options.join("");
}

function formatCoordinate(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(6) : "-";
}

function formatPorts(value) {
  return Array.isArray(value) && value.length ? value.join(", ") : "-";
}

async function fetchRobotDiscovery(refresh = false) {
  state.robotDiscovery.loading = true;
  state.robotDiscovery.error = "";
  if (state.pageId === "status") {
    renderCurrentPage();
  }
  try {
    const query = refresh ? "?refresh=1" : "";
    const payload = await apiFetch(`/api/robots/discovery${query}`);
    state.robotDiscovery.items = payload.items || [];
    state.robotDiscovery.scannedAt = payload.scannedAt || "";
    state.robotDiscovery.expiresAt = payload.expiresAt || "";
    state.robotDiscovery.subnets = payload.subnets || [];
    if (!state.robotDiscovery.items.some((item) => item.confirmed && item.ipAddress === state.robotDiscovery.selectedIp)) {
      state.robotDiscovery.selectedIp = "";
    }
  } catch (error) {
    state.robotDiscovery.error = error.message;
  } finally {
    state.robotDiscovery.loading = false;
    if (state.pageId === "status") {
      renderCurrentPage();
    }
  }
}

function pointInPolygon(coords, polygon) {
  const [lng, lat] = coords;
  let inside = false;
  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current, current += 1) {
    const [currentLng, currentLat] = polygon[current];
    const [previousLng, previousLat] = polygon[previous];
    const intersects = ((currentLat > lat) !== (previousLat > lat))
      && (lng < ((previousLng - currentLng) * (lat - currentLat)) / ((previousLat - currentLat) || 1e-12) + currentLng);
    if (intersects) inside = !inside;
  }
  return inside;
}

function resolveZoneForPoint(coords) {
  return (state.data?.zones || []).find((zone) => pointInPolygon(coords, zone.path)) || null;
}

function syncPointDraftUi() {
  const form = document.getElementById("point-form");
  const status = document.getElementById("point-picker-status");
  if (!form) return;
  const latField = form.elements.namedItem("lat");
  const lngField = form.elements.namedItem("lng");
  if (latField) latField.value = state.pointDraft.coords ? state.pointDraft.coords[1].toFixed(6) : "";
  if (lngField) lngField.value = state.pointDraft.coords ? state.pointDraft.coords[0].toFixed(6) : "";
  if (status) {
    status.textContent = state.pointDraft.coords
      ? `已选择 ${state.pointDraft.zoneName} 内的巡检点：${state.pointDraft.coords[1].toFixed(6)}, ${state.pointDraft.coords[0].toFixed(6)}`
      : "请在地图中的巡检区域内点击选择巡检点。";
  }
}

function resetPointDraft() {
  state.pointDraft.coords = null;
  state.pointDraft.zoneId = null;
  state.pointDraft.zoneName = "";
  if (state.pointDraft.marker) {
    state.pointDraft.marker.setMap(null);
    state.pointDraft.marker = null;
  }
  syncPointDraftUi();
}

function setupPointPicker(map) {
  syncPointDraftUi();
  map.on("click", (event) => {
    const coords = [event.lnglat.getLng(), event.lnglat.getLat()];
    const zone = resolveZoneForPoint(coords);
    if (!zone) {
      setFormError("point", "请在巡检区域多边形内部点击选择巡检点。");
      return;
    }
    setFormError("point");
    state.pointDraft.coords = coords;
    state.pointDraft.zoneId = zone.id;
    state.pointDraft.zoneName = zone.name;
    if (!state.pointDraft.marker) {
      state.pointDraft.marker = new AMap.Marker({
        map,
        position: coords,
        title: `巡检点 | ${zone.name}`,
        bubble: true,
      });
    } else {
      state.pointDraft.marker.setPosition(coords);
      state.pointDraft.marker.setMap(map);
    }
    syncPointDraftUi();
  });
}

function findPageItem(pageId, itemId) {
  const source = state.pageData[pageId];
  const items = Array.isArray(source?.items) ? source.items : [];
  return items.find((item) => Number(item.id) === Number(itemId)) || null;
}

async function ensureManagementPageData(pageId, force = false) {
  if (!force && state.pageData[pageId]) {
    return state.pageData[pageId];
  }

  if (pageId === "users") {
    state.pageData.users = await apiFetch("/api/users?page=1&size=100");
  } else if (pageId === "devices") {
    const [devices, areas] = await Promise.all([apiFetch("/api/devices"), apiFetch("/api/areas")]);
    state.pageData.devices = { items: devices.items || [], areas: areas.items || [] };
  } else if (pageId === "areas") {
    state.pageData.areas = await apiFetch("/api/areas");
  } else if (pageId === "points") {
    const [points, areas, devices] = await Promise.all([
      apiFetch("/api/points"),
      apiFetch("/api/areas"),
      apiFetch("/api/devices"),
    ]);
    state.pageData.points = {
      items: points.items || [],
      areas: areas.items || [],
      devices: devices.items || [],
    };
  } else if (pageId === "routes") {
    const previousRoutePoints = state.pageData.routes?.routePoints || {};
    const [routes, areas, points] = await Promise.all([
      apiFetch("/api/routes"),
      apiFetch("/api/areas"),
      apiFetch("/api/points"),
    ]);
    state.pageData.routes = {
      items: routes.items || [],
      areas: areas.items || [],
      points: points.items || [],
      routePoints: previousRoutePoints,
    };
    if (
      state.routeEditor.routeId &&
      !state.pageData.routes.items.some((route) => Number(route.id) === Number(state.routeEditor.routeId))
    ) {
      state.routeEditor = { routeId: null, selected: [] };
    }
  }

  if (state.pageId === pageId) {
    renderCurrentPage();
  }
  return state.pageData[pageId];
}

async function ensureRoutePoints(routeId, force = false) {
  if (!state.pageData.routes) {
    await ensureManagementPageData("routes");
  }
  const current = state.pageData.routes?.routePoints?.[routeId];
  if (!force && current) {
    state.routeEditor.selected = current.map((item) => item.id);
    return current;
  }
  const payload = await apiFetch(`/api/routes/${routeId}/points`);
  state.pageData.routes.routePoints = {
    ...(state.pageData.routes.routePoints || {}),
    [routeId]: payload.items || [],
  };
  state.routeEditor.selected = (payload.items || []).map((item) => item.id);
  if (state.pageId === "routes") {
    renderCurrentPage();
  }
  return payload.items || [];
}

function bindManagedForm(formId, errorKey, handler) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormError(errorKey);
    try {
      await handler(form);
    } catch (error) {
      setFormError(errorKey, error.message);
    }
  });
}

function renderModalField(field, values) {
  const value = values[field.name] ?? "";
  const required = field.required ? "required" : "";
  const disabled = field.disabled ? "disabled" : "";
  const readonly = field.readonly ? "readonly" : "";
  const className = field.className ? ` ${field.className}` : "";

  if (field.type === "select") {
    return `
      <label class="${className.trim()}">
        <span>${escapeHtml(field.label)}</span>
        <select name="${escapeHtml(field.name)}" ${required} ${disabled}>
          ${(field.options || []).map((option) => {
            const optionValue = String(option.value);
            return `<option value="${escapeHtml(optionValue)}"${optionValue === String(value) ? " selected" : ""}>${escapeHtml(option.label)}</option>`;
          }).join("")}
        </select>
      </label>
    `;
  }

  if (field.type === "textarea") {
    return `
      <label class="${className.trim()}">
        <span>${escapeHtml(field.label)}</span>
        <textarea name="${escapeHtml(field.name)}" placeholder="${escapeHtml(field.placeholder || "")}" ${required} ${disabled} ${readonly}>${escapeHtml(value)}</textarea>
      </label>
    `;
  }

  return `
    <label class="${className.trim()}">
      <span>${escapeHtml(field.label)}</span>
      <input
        name="${escapeHtml(field.name)}"
        type="${escapeHtml(field.type || "text")}"
        value="${escapeHtml(value)}"
        placeholder="${escapeHtml(field.placeholder || "")}"
        ${required}
        ${disabled}
        ${readonly}
        ${field.min !== undefined ? `min="${escapeHtml(field.min)}"` : ""}
        ${field.max !== undefined ? `max="${escapeHtml(field.max)}"` : ""}
        ${field.step !== undefined ? `step="${escapeHtml(field.step)}"` : ""}
      />
    </label>
  `;
}

function closeCrudModal() {
  state.modal.onSubmit = null;
  if (crudModalError) crudModalError.textContent = "";
  if (crudModalBody) crudModalBody.innerHTML = "";
  crudModalForm?.reset();
  if (!crudModal) return;
  if (typeof crudModal.close === "function" && crudModal.open) {
    crudModal.close();
  } else {
    crudModal.removeAttribute("open");
  }
}

function showCrudModal({ title, fields, values = {}, saveText = "保存", onSubmit }) {
  if (!crudModal || !crudModalForm || !crudModalBody || !crudModalTitle || !crudModalSave) {
    return;
  }
  if (crudModal.open && typeof crudModal.close === "function") {
    crudModal.close();
  }
  crudModalTitle.textContent = title;
  crudModalSave.textContent = saveText;
  crudModalError.textContent = "";
  crudModalBody.innerHTML = fields.map((field) => renderModalField(field, values)).join("");
  state.modal.onSubmit = async () => {
    crudModalError.textContent = "";
    crudModalSave.disabled = true;
    try {
      const payload = formToObject(crudModalForm);
      await onSubmit(payload);
      closeCrudModal();
    } catch (error) {
      crudModalError.textContent = error.message;
    } finally {
      crudModalSave.disabled = false;
    }
  };
  if (typeof crudModal.showModal === "function") {
    crudModal.showModal();
  } else {
    crudModal.setAttribute("open", "open");
  }
}

async function apiUpload(url, formData) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    body: formData,
  });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("登录状态已失效，请重新登录。");
  }
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : null;
  if (!response.ok) {
    throw new Error(payload?.detail || `请求失败：${response.status}`);
  }
  return payload;
}

function clearDeviceImageDraft() {
  if (state.deviceImageDraft.previewUrl) {
    URL.revokeObjectURL(state.deviceImageDraft.previewUrl);
  }
  state.deviceImageDraft = { file: null, previewUrl: "", fileName: "" };
}

function setDeviceImageDraft(file) {
  clearDeviceImageDraft();
  if (!file) return;
  state.deviceImageDraft = {
    file,
    previewUrl: URL.createObjectURL(file),
    fileName: file.name,
  };
}

function getFilteredDevices(items) {
  const keyword = state.deviceFilters.keyword.trim().toLowerCase();
  const status = state.deviceFilters.status;
  return (items || []).filter((device) => {
    const matchesKeyword = !keyword || [device.name, device.model, device.areaName, device.notes]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(keyword));
    const matchesStatus = !status || device.status === status;
    return matchesKeyword && matchesStatus;
  });
}

crudModalSave?.addEventListener("click", async () => {
  if (!state.modal.onSubmit) return;
  await state.modal.onSubmit();
});

crudModal?.addEventListener("close", () => {
  state.modal.onSubmit = null;
  if (crudModalError) crudModalError.textContent = "";
  if (crudModalBody) crudModalBody.innerHTML = "";
  crudModalForm?.reset();
});

function renderUsersPage() {
  const usersData = state.pageData.users;
  if (!usersData) {
    return renderLoadingPage("用户管理", "创建账号并管理访问权限。");
  }
  const activeCount = (usersData.items || []).filter((user) => user.status === "active").length;
  const disabledCount = (usersData.items || []).filter((user) => user.status === "disabled").length;
  const rows = (usersData.items || []).map((user) => `
    <tr>
      <td>${escapeHtml(user.username)}</td>
      <td>${escapeHtml(user.displayName || "-")}</td>
      <td><span class="${pillClass(user.status)}">${escapeHtml(localizeToken(user.status))}</span></td>
      <td>${escapeHtml(formatDateTime(user.createdAt))}</td>
      <td>
        <div class="inline-meta">
          <button class="secondary-button" type="button" data-user-edit data-id="${user.id}">编辑</button>
          <button class="ghost-button" type="button" data-user-toggle data-id="${user.id}" data-next-status="${user.status === "active" ? "disabled" : "active"}">
            ${user.status === "active" ? "停用" : "启用"}
          </button>
        </div>
      </td>
    </tr>
  `);
  return `
    <section class="metric-grid">
      <article class="metric-card"><strong>账号总数</strong><span class="muted">${usersData.total || (usersData.items || []).length} 个</span></article>
      <article class="metric-card"><strong>启用中</strong><span class="muted">${activeCount} 个</span></article>
      <article class="metric-card"><strong>已停用</strong><span class="muted">${disabledCount} 个</span></article>
    </section>
    <section class="page-content">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>用户列表</h2>
            <p class="muted">支持状态切换，并通过弹窗新增或编辑用户。</p>
          </div>
          <div class="panel-actions">
            <button class="primary-button" type="button" data-user-create>新增用户</button>
          </div>
        </div>
        ${renderTable("users", ["用户名", "显示名称", "状态", "创建时间", "操作"], rows)}
      </article>
    </section>
  `;
}

function renderDevicesPage() {
  const devicesData = state.pageData.devices;
  if (!devicesData) {
    return renderLoadingPage("设备管理", "管理设备并分配所属区域。");
  }
  const previewUrl = state.deviceImageDraft.previewUrl;
  const filteredDevices = getFilteredDevices(devicesData.items || []);
  const rows = filteredDevices.map((device) => `
    <tr>
      <td>${escapeHtml(device.name)}</td>
      <td>${escapeHtml(device.model)}</td>
      <td>${escapeHtml(device.areaName || "-")}</td>
      <td><span class="${pillClass(device.status)}">${escapeHtml(localizeToken(device.status))}</span></td>
      <td>${device.imagePath ? `<img class="device-thumb" src="${escapeHtml(device.imagePath)}" alt="${escapeHtml(device.name)}">` : "-"}</td>
      <td>
        <div class="inline-meta">
          <button class="secondary-button" type="button" data-device-edit data-id="${device.id}">编辑</button>
          <button class="danger-button" type="button" data-device-delete data-id="${device.id}">删除</button>
        </div>
      </td>
    </tr>
  `);
  return `
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>设备登记</h2>
            <p class="muted">登记平台设备并绑定所属区域。</p>
          </div>
        </div>
        <form id="device-form" class="stack-form">
          <div class="grid-form">
            <label><span>名称</span><input name="name" required /></label>
            <label><span>型号</span><input name="model" required /></label>
            <label><span>状态</span>
              <select name="status">
                <option value="normal">正常</option>
                <option value="repair">维修中</option>
                <option value="offline">离线</option>
              </select>
            </label>
            <label><span>区域</span>
              <select name="areaId">${renderSelectOptions(devicesData.areas || [], "", "未设置")}</select>
            </label>
          </div>
          <label><span>备注</span><textarea name="notes" placeholder="可选设备备注"></textarea></label>
          <div class="device-upload-grid">
            <label>
              <span>设备图片</span>
              <input id="device-image-input" type="file" accept="image/*" />
            </label>
            <div class="image-preview-card">
              <div class="image-preview-shell">
                ${previewUrl ? `<img src="${escapeHtml(previewUrl)}" alt="设备预览">` : `<span class="muted">选择图片后在这里预览</span>`}
              </div>
              <div class="inline-meta">
                <span class="muted">${escapeHtml(state.deviceImageDraft.fileName || "未选择图片")}</span>
                <button class="ghost-button" id="device-image-clear" type="button">清空图片</button>
              </div>
            </div>
          </div>
          <div class="button-row">
            <button class="primary-button" type="submit">新建设备</button>
          </div>
          <p class="form-error" data-form-error="device"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>设备列表</h2>
            <p class="muted">支持按名称、型号、区域和状态筛选。</p>
          </div>
          <div class="panel-actions toolbar-filters">
            <input id="device-search" type="search" value="${escapeHtml(state.deviceFilters.keyword)}" placeholder="搜索名称 / 型号 / 区域" />
            <select id="device-status-filter">
              <option value="">全部状态</option>
              <option value="normal"${state.deviceFilters.status === "normal" ? " selected" : ""}>正常</option>
              <option value="repair"${state.deviceFilters.status === "repair" ? " selected" : ""}>维修中</option>
              <option value="offline"${state.deviceFilters.status === "offline" ? " selected" : ""}>离线</option>
            </select>
            <button class="primary-button" id="device-filter-apply" type="button">筛选</button>
            <button class="secondary-button" id="device-filter-reset" type="button">重置筛选</button>
          </div>
        </div>
        ${renderTable("devices", ["名称", "型号", "区域", "状态", "图片", "操作"], rows)}
      </article>
    </section>
  `;
}

function renderAreasPage() {
  const areasData = state.pageData.areas;
  if (!areasData) {
    return renderLoadingPage("区域管理", "管理巡检区域。");
  }
  const rows = (areasData.items || []).map((area) => `
    <tr>
      <td>${escapeHtml(area.name)}</td>
      <td>${escapeHtml(area.manager || "-")}</td>
      <td>${escapeHtml(area.description || "-")}</td>
      <td>${escapeHtml(formatDateTime(area.createdAt))}</td>
      <td>
        <div class="inline-meta">
          <button class="secondary-button" type="button" data-area-edit data-id="${area.id}">编辑</button>
          <button class="danger-button" type="button" data-area-delete data-id="${area.id}">删除</button>
        </div>
      </td>
    </tr>
  `);
  return `
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>区域配置</h2>
            <p class="muted">创建设备、点位和路线共用的逻辑区域。</p>
          </div>
        </div>
        <form id="area-form" class="stack-form">
          <div class="grid-form">
            <label><span>名称</span><input name="name" required /></label>
            <label><span>负责人</span><input name="manager" /></label>
          </div>
          <label><span>描述</span><textarea name="description" placeholder="区域描述"></textarea></label>
          <div class="button-row">
            <button class="primary-button" type="submit">新建区域</button>
          </div>
          <p class="form-error" data-form-error="area"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>区域列表</h2>
            <p class="muted">删除区域后，后端会解除相关关联。</p>
          </div>
        </div>
        ${renderTable("areas", ["名称", "负责人", "描述", "创建时间", "操作"], rows)}
      </article>
    </section>
  `;
}

function renderPointsPage() {
  const pointsData = state.pageData.points;
  if (!pointsData) {
    return renderLoadingPage("点位管理", "配置巡检点位。");
  }
  const pointPickerStatus = state.pointDraft.coords
    ? `已选择 ${state.pointDraft.zoneName} 内的巡检点：${state.pointDraft.coords[1].toFixed(6)}, ${state.pointDraft.coords[0].toFixed(6)}`
    : "请在地图中的巡检区域内点击选择巡检点。";
  const rows = (pointsData.items || []).map((point) => `
    <tr>
      <td>${escapeHtml(point.name)}</td>
      <td>${escapeHtml(point.areaName || "-")}</td>
      <td>${escapeHtml(point.deviceName || "-")}</td>
      <td>${escapeHtml(formatCoordinate(point.lat))}</td>
      <td>${escapeHtml(formatCoordinate(point.lng))}</td>
      <td>${escapeHtml(point.description || "-")}</td>
      <td>
        <div class="inline-meta">
          <button class="secondary-button" type="button" data-point-edit data-id="${point.id}">编辑</button>
          <button class="danger-button" type="button" data-point-delete data-id="${point.id}">删除</button>
        </div>
      </td>
    </tr>
  `);
  return `
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>巡检点位</h2>
            <p class="muted">先在巡检区域内点击地图选点，再提交点位信息。</p>
          </div>
        </div>
        <form id="point-form" class="stack-form">
          <div id="points-map" class="map-shell"><div class="map-fallback">检测到高德地图后将在此渲染。</div></div>
          <div class="inline-meta point-picker-meta">
            <span id="point-picker-status" class="muted">${escapeHtml(pointPickerStatus)}</span>
            <button class="ghost-button" id="point-picker-reset" type="button">清空选点</button>
          </div>
          <div class="grid-form">
            <label><span>名称</span><input name="name" required /></label>
            <label><span>区域</span>
              <select name="areaId">${renderSelectOptions(pointsData.areas || [], "", "未设置")}</select>
            </label>
            <label><span>设备</span>
              <select name="deviceId">${renderSelectOptions(pointsData.devices || [], "", "未设置")}</select>
            </label>
            <label><span>纬度</span><input name="lat" type="number" step="0.000001" required readonly /></label>
            <label><span>经度</span><input name="lng" type="number" step="0.000001" required readonly /></label>
          </div>
          <label><span>描述</span><textarea name="description" placeholder="点位描述"></textarea></label>
          <div class="button-row">
            <button class="primary-button" type="submit">新建点位</button>
          </div>
          <p class="form-error" data-form-error="point"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>点位列表</h2>
            <p class="muted">这些点位可供路线配置复用。</p>
          </div>
        </div>
        ${renderTable("points", ["名称", "区域", "设备", "纬度", "经度", "描述", "操作"], rows)}
      </article>
    </section>
  `;
}

function renderRoutesPage() {
  const routesData = state.pageData.routes;
  if (!routesData) {
    return renderLoadingPage("路线管理", "由巡检点位组成巡检路线。");
  }
  const activeRoute = (routesData.items || []).find((route) => Number(route.id) === Number(state.routeEditor.routeId)) || null;
  const activePointIds = new Set((state.routeEditor.selected || []).map((value) => Number(value)));
  const activeRoutePoints = activeRoute ? (routesData.routePoints?.[activeRoute.id] || []) : [];
  const pointsById = new Map((routesData.points || []).map((point) => [Number(point.id), point]));
  const selectedPoints = (state.routeEditor.selected || []).map((id) => pointsById.get(Number(id))).filter(Boolean);
  const availablePoints = (routesData.points || []).filter((point) => !activePointIds.has(Number(point.id)));
  const rows = (routesData.items || []).map((route) => `
    <tr>
      <td>${escapeHtml(route.name)}</td>
      <td>${escapeHtml(route.areaName || "-")}</td>
      <td>${escapeHtml(route.description || "-")}</td>
      <td>${escapeHtml(String(route.pointCount || 0))}</td>
      <td>${escapeHtml(formatDateTime(route.createdAt))}</td>
      <td>
        <div class="inline-meta">
          <button class="secondary-button" type="button" data-route-edit data-id="${route.id}">编辑</button>
          <button class="ghost-button" type="button" data-route-manage data-id="${route.id}">
            ${activeRoute && activeRoute.id === route.id ? "收起点位" : "配置点位"}
          </button>
          <button class="danger-button" type="button" data-route-delete data-id="${route.id}">删除</button>
        </div>
      </td>
    </tr>
  `);
  const editorHtml = activeRoute ? `
    <article class="panel">
      <div class="panel-header">
        <div>
          <h2>路线点位</h2>
          <p class="muted">${escapeHtml(activeRoute.name)} 当前已绑定 ${activeRoutePoints.length} 个点位。</p>
        </div>
        <span class="pill">已选 ${state.routeEditor.selected.length}</span>
      </div>
      <div class="route-transfer">
        <div class="transfer-panel">
          <strong>待选点位</strong>
          <select id="route-available-points" class="transfer-select" multiple size="12">
            ${availablePoints.map((point) => `
              <option value="${point.id}">
                ${escapeHtml(`${point.name} ｜ ${point.areaName || "-"} ｜ ${formatCoordinate(point.lat)}, ${formatCoordinate(point.lng)}`)}
              </option>
            `).join("")}
          </select>
          <p class="muted">左侧展示还未加入该路线的巡检点。</p>
        </div>
        <div class="transfer-actions">
          <button class="secondary-button" id="route-points-add" type="button">加入 →</button>
          <button class="secondary-button" id="route-points-remove" type="button">← 移出</button>
          <button class="ghost-button" id="route-points-up" type="button">上移</button>
          <button class="ghost-button" id="route-points-down" type="button">下移</button>
        </div>
        <div class="transfer-panel">
          <strong>路线顺序</strong>
          <select id="route-selected-points" class="transfer-select" multiple size="12">
            ${selectedPoints.map((point, index) => `
              <option value="${point.id}">
                ${escapeHtml(`${index + 1}. ${point.name} ｜ ${point.areaName || "-"} ｜ ${formatCoordinate(point.lat)}, ${formatCoordinate(point.lng)}`)}
              </option>
            `).join("")}
          </select>
          <p class="muted">右侧顺序即保存后的巡检顺序。</p>
        </div>
      </div>
      <div class="button-row">
        <button class="primary-button" id="route-points-save" type="button">保存点位配置</button>
        <button class="secondary-button" id="route-points-close" type="button">关闭</button>
      </div>
      <p class="form-error" data-form-error="route-points"></p>
    </article>
  ` : "";
  return `
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>巡检路线</h2>
            <p class="muted">创建巡检路线并绑定所属区域。</p>
          </div>
        </div>
        <form id="route-form" class="stack-form">
          <div class="grid-form">
            <label><span>名称</span><input name="name" required /></label>
            <label><span>区域</span>
              <select name="areaId">${renderSelectOptions(routesData.areas || [], "", "未设置")}</select>
            </label>
          </div>
          <label><span>描述</span><textarea name="description" placeholder="路线描述"></textarea></label>
          <div class="button-row">
            <button class="primary-button" type="submit">新建路线</button>
          </div>
          <p class="form-error" data-form-error="route"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div>
            <h2>路线列表</h2>
            <p class="muted">点击“配置点位”设置路线点位。</p>
          </div>
        </div>
        ${renderTable("routes", ["名称", "区域", "描述", "点位数", "创建时间", "操作"], rows)}
      </article>
    </section>
    ${editorHtml}
  `;
}

function bindUsersPage() {
  if (!state.pageData.users) {
    void ensureManagementPageData("users");
    return;
  }
  document.querySelector("[data-user-create]")?.addEventListener("click", () => {
    showCrudModal({
      title: "新增用户",
      saveText: "创建用户",
      fields: [
        { name: "username", label: "用户名", required: true },
        { name: "displayName", label: "显示名称" },
        { name: "password", label: "密码", type: "password", required: true },
      ],
      onSubmit: async (payload) => {
        await apiFetch("/api/users", { method: "POST", body: JSON.stringify(payload) });
        await ensureManagementPageData("users", true);
      },
    });
  });
  document.querySelectorAll("[data-user-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const user = findPageItem("users", button.dataset.id);
      if (!user) return;
      showCrudModal({
        title: `编辑用户：${user.username}`,
        saveText: "保存修改",
        values: {
          displayName: user.displayName || user.username,
          password: "",
        },
        fields: [
          { name: "displayName", label: "显示名称", required: true },
          { name: "password", label: "新密码", type: "password", placeholder: "留空则保持不变" },
        ],
        onSubmit: async (payload) => {
          if (!payload.displayName && !payload.password) {
            throw new Error("请至少填写显示名称或新密码。");
          }
          await apiFetch(`/api/users/${user.id}`, { method: "PUT", body: JSON.stringify(payload) });
          await ensureManagementPageData("users", true);
        },
      });
    });
  });
  document.querySelectorAll("[data-user-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      await apiFetch(`/api/users/${button.dataset.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: button.dataset.nextStatus }),
      });
      await ensureManagementPageData("users", true);
    });
  });
}

function bindDevicesPage() {
  if (!state.pageData.devices) {
    void ensureManagementPageData("devices");
    return;
  }
  bindManagedForm("device-form", "device", async (form) => {
    const payload = numericPayload(formToObject(form), ["areaId"]);
    const created = await apiFetch("/api/devices", { method: "POST", body: JSON.stringify(payload) });
    if (state.deviceImageDraft.file && created.deviceId) {
      const formData = new FormData();
      formData.append("file", state.deviceImageDraft.file);
      await apiUpload(`/api/devices/${created.deviceId}/image`, formData);
    }
    form.reset();
    clearDeviceImageDraft();
    await ensureManagementPageData("devices", true);
  });
  document.getElementById("device-image-input")?.addEventListener("change", (event) => {
    const [file] = event.target.files || [];
    setDeviceImageDraft(file || null);
    renderCurrentPage();
  });
  document.getElementById("device-image-clear")?.addEventListener("click", () => {
    clearDeviceImageDraft();
    renderCurrentPage();
  });
  document.getElementById("device-filter-apply")?.addEventListener("click", () => {
    state.deviceFilters.keyword = document.getElementById("device-search")?.value || "";
    state.deviceFilters.status = document.getElementById("device-status-filter")?.value || "";
    renderCurrentPage();
  });
  document.getElementById("device-filter-reset")?.addEventListener("click", () => {
    state.deviceFilters = { keyword: "", status: "" };
    renderCurrentPage();
  });
  document.querySelectorAll("[data-device-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const device = findPageItem("devices", button.dataset.id);
      if (!device) return;
      showCrudModal({
        title: `编辑设备：${device.name}`,
        saveText: "保存设备",
        values: {
          name: device.name,
          model: device.model,
          status: device.status || "normal",
          areaId: device.areaId == null ? "" : String(device.areaId),
          notes: device.notes || "",
        },
        fields: [
          { name: "name", label: "名称", required: true },
          { name: "model", label: "型号", required: true },
          {
            name: "status",
            label: "状态",
            type: "select",
            options: [
              { value: "normal", label: "正常" },
              { value: "repair", label: "维修中" },
              { value: "offline", label: "离线" },
            ],
          },
          {
            name: "areaId",
            label: "区域",
            type: "select",
            options: [{ value: "", label: "未设置" }].concat(
              (state.pageData.devices?.areas || []).map((area) => ({ value: String(area.id), label: area.name })),
            ),
          },
          { name: "notes", label: "备注", type: "textarea", className: "field-span-2" },
        ],
        onSubmit: async (payload) => {
          const nextPayload = numericPayload(payload, ["areaId"]);
          await apiFetch(`/api/devices/${device.id}`, { method: "PUT", body: JSON.stringify(nextPayload) });
          await ensureManagementPageData("devices", true);
        },
      });
    });
  });
  document.querySelectorAll("[data-device-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除该设备？")) return;
      await apiFetch(`/api/devices/${button.dataset.id}`, { method: "DELETE" });
      await ensureManagementPageData("devices", true);
    });
  });
}

function bindAreasPage() {
  if (!state.pageData.areas) {
    void ensureManagementPageData("areas");
    return;
  }
  bindManagedForm("area-form", "area", async (form) => {
    await apiFetch("/api/areas", { method: "POST", body: JSON.stringify(formToObject(form)) });
    form.reset();
    await ensureManagementPageData("areas", true);
  });
  document.querySelectorAll("[data-area-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const area = findPageItem("areas", button.dataset.id);
      if (!area) return;
      showCrudModal({
        title: `编辑区域：${area.name}`,
        saveText: "保存区域",
        values: {
          name: area.name,
          manager: area.manager || "",
          description: area.description || "",
        },
        fields: [
          { name: "name", label: "名称", required: true },
          { name: "manager", label: "负责人" },
          { name: "description", label: "描述", type: "textarea", className: "field-span-2" },
        ],
        onSubmit: async (payload) => {
          await apiFetch(`/api/areas/${area.id}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          });
          await ensureManagementPageData("areas", true);
        },
      });
    });
  });
  document.querySelectorAll("[data-area-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除该区域？")) return;
      await apiFetch(`/api/areas/${button.dataset.id}`, { method: "DELETE" });
      await ensureManagementPageData("areas", true);
    });
  });
}

function bindPointsPage() {
  if (!state.pageData.points) {
    void ensureManagementPageData("points");
    return;
  }
  bindManagedForm("point-form", "point", async (form) => {
    if (!state.pointDraft.coords) {
      throw new Error("请先在巡检区域内点击地图选择巡检点。");
    }
    const payload = numericPayload(formToObject(form), ["areaId", "deviceId"]);
    payload.lat = state.pointDraft.coords[1];
    payload.lng = state.pointDraft.coords[0];
    await apiFetch("/api/points", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    resetPointDraft();
    await ensureManagementPageData("points", true);
  });
  document.getElementById("point-picker-reset")?.addEventListener("click", () => {
    resetPointDraft();
    setFormError("point");
  });
  syncPointDraftUi();
  document.querySelectorAll("[data-point-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const point = findPageItem("points", button.dataset.id);
      if (!point) return;
      showCrudModal({
        title: `编辑点位：${point.name}`,
        saveText: "保存点位",
        values: {
          name: point.name,
          areaId: point.areaId == null ? "" : String(point.areaId),
          deviceId: point.deviceId == null ? "" : String(point.deviceId),
          lat: String(point.lat ?? ""),
          lng: String(point.lng ?? ""),
          description: point.description || "",
        },
        fields: [
          { name: "name", label: "名称", required: true },
          {
            name: "areaId",
            label: "区域",
            type: "select",
            options: [{ value: "", label: "未设置" }].concat(
              (state.pageData.points?.areas || []).map((area) => ({ value: String(area.id), label: area.name })),
            ),
          },
          {
            name: "deviceId",
            label: "设备",
            type: "select",
            options: [{ value: "", label: "未设置" }].concat(
              (state.pageData.points?.devices || []).map((device) => ({ value: String(device.id), label: device.name })),
            ),
          },
          { name: "lat", label: "纬度", type: "number", step: "0.000001", required: true },
          { name: "lng", label: "经度", type: "number", step: "0.000001", required: true },
          { name: "description", label: "描述", type: "textarea", className: "field-span-2" },
        ],
        onSubmit: async (payload) => {
          const nextPayload = numericPayload(payload, ["areaId", "deviceId", "lat", "lng"]);
          await apiFetch(`/api/points/${point.id}`, { method: "PUT", body: JSON.stringify(nextPayload) });
          await ensureManagementPageData("points", true);
        },
      });
    });
  });
  document.querySelectorAll("[data-point-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除该点位？")) return;
      await apiFetch(`/api/points/${button.dataset.id}`, { method: "DELETE" });
      await ensureManagementPageData("points", true);
    });
  });
}

function bindRoutesPage() {
  if (!state.pageData.routes) {
    void ensureManagementPageData("routes");
    return;
  }
  bindManagedForm("route-form", "route", async (form) => {
    const payload = numericPayload(formToObject(form), ["areaId"]);
    await apiFetch("/api/routes", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await ensureManagementPageData("routes", true);
  });
  document.querySelectorAll("[data-route-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const route = findPageItem("routes", button.dataset.id);
      if (!route) return;
      showCrudModal({
        title: `编辑路线：${route.name}`,
        saveText: "保存路线",
        values: {
          name: route.name,
          areaId: route.areaId == null ? "" : String(route.areaId),
          description: route.description || "",
        },
        fields: [
          { name: "name", label: "名称", required: true },
          {
            name: "areaId",
            label: "区域",
            type: "select",
            options: [{ value: "", label: "未设置" }].concat(
              (state.pageData.routes?.areas || []).map((area) => ({ value: String(area.id), label: area.name })),
            ),
          },
          { name: "description", label: "描述", type: "textarea", className: "field-span-2" },
        ],
        onSubmit: async (payload) => {
          const nextPayload = numericPayload(payload, ["areaId"]);
          await apiFetch(`/api/routes/${route.id}`, { method: "PUT", body: JSON.stringify(nextPayload) });
          await ensureManagementPageData("routes", true);
        },
      });
    });
  });
  document.querySelectorAll("[data-route-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除该路线？")) return;
      await apiFetch(`/api/routes/${button.dataset.id}`, { method: "DELETE" });
      if (Number(state.routeEditor.routeId) === Number(button.dataset.id)) {
        state.routeEditor = { routeId: null, selected: [] };
      }
      await ensureManagementPageData("routes", true);
    });
  });
  document.querySelectorAll("[data-route-manage]").forEach((button) => {
    button.addEventListener("click", async () => {
      const routeId = Number(button.dataset.id);
      if (Number(state.routeEditor.routeId) === routeId) {
        state.routeEditor = { routeId: null, selected: [] };
        renderCurrentPage();
        return;
      }
      state.routeEditor.routeId = routeId;
      state.routeEditor.selected = [];
      await ensureRoutePoints(routeId, true);
    });
  });
  document.getElementById("route-points-add")?.addEventListener("click", () => {
    const availableSelect = document.getElementById("route-available-points");
    const ids = Array.from(availableSelect?.selectedOptions || []).map((option) => Number(option.value));
    if (!ids.length) return;
    state.routeEditor.selected = [...state.routeEditor.selected, ...ids.filter((id) => !state.routeEditor.selected.includes(id))];
    renderCurrentPage();
  });
  document.getElementById("route-points-remove")?.addEventListener("click", () => {
    const selectedSelect = document.getElementById("route-selected-points");
    const ids = new Set(Array.from(selectedSelect?.selectedOptions || []).map((option) => Number(option.value)));
    if (!ids.size) return;
    state.routeEditor.selected = state.routeEditor.selected.filter((id) => !ids.has(Number(id)));
    renderCurrentPage();
  });
  document.getElementById("route-points-up")?.addEventListener("click", () => {
    const selectedSelect = document.getElementById("route-selected-points");
    const ids = new Set(Array.from(selectedSelect?.selectedOptions || []).map((option) => Number(option.value)));
    if (!ids.size) return;
    for (let index = 1; index < state.routeEditor.selected.length; index += 1) {
      const currentId = Number(state.routeEditor.selected[index]);
      const previousId = Number(state.routeEditor.selected[index - 1]);
      if (ids.has(currentId) && !ids.has(previousId)) {
        [state.routeEditor.selected[index - 1], state.routeEditor.selected[index]] = [state.routeEditor.selected[index], state.routeEditor.selected[index - 1]];
      }
    }
    renderCurrentPage();
  });
  document.getElementById("route-points-down")?.addEventListener("click", () => {
    const selectedSelect = document.getElementById("route-selected-points");
    const ids = new Set(Array.from(selectedSelect?.selectedOptions || []).map((option) => Number(option.value)));
    if (!ids.size) return;
    for (let index = state.routeEditor.selected.length - 2; index >= 0; index -= 1) {
      const currentId = Number(state.routeEditor.selected[index]);
      const nextId = Number(state.routeEditor.selected[index + 1]);
      if (ids.has(currentId) && !ids.has(nextId)) {
        [state.routeEditor.selected[index + 1], state.routeEditor.selected[index]] = [state.routeEditor.selected[index], state.routeEditor.selected[index + 1]];
      }
    }
    renderCurrentPage();
  });
  document.getElementById("route-points-save")?.addEventListener("click", async () => {
    if (!state.routeEditor.routeId) return;
    setFormError("route-points");
    try {
      await apiFetch(`/api/routes/${state.routeEditor.routeId}/points`, {
        method: "PUT",
        body: JSON.stringify({ pointIds: state.routeEditor.selected }),
      });
      await ensureManagementPageData("routes", true);
      await ensureRoutePoints(state.routeEditor.routeId, true);
    } catch (error) {
      setFormError("route-points", error.message);
    }
  });
  document.getElementById("route-points-close")?.addEventListener("click", () => {
    state.routeEditor = { routeId: null, selected: [] };
    renderCurrentPage();
  });
}

function renderTable(type, headers, rows) {
  return rows.length ? `
    <div class="table-scroll">
      <table class="data-table" data-table="${type}">
        <thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    </div>
  ` : `<div class="empty-state">暂无记录。</div>`;
}

function renderCurrentPage() {
  const renderers = {
    overview: renderOverviewPage,
    tasks: renderTasksPage,
    reports: renderReportsPage,
    status: renderStatusPage,
    maintenance: renderMaintenancePage,
    zones: renderZonesPage,
    users: renderUsersPage,
    devices: renderDevicesPage,
    areas: renderAreasPage,
    points: renderPointsPage,
    routes: renderRoutesPage,
  };
  const renderer = renderers[state.pageId];
  pageContent.innerHTML = renderer ? renderer() : `<section class="panel"><div class="empty-state">页面不存在。</div></section>`;
  bindForms();
  renderMaps();
}

function formToObject(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  for (const key of Object.keys(data)) {
    if (data[key] === "") {
      delete data[key];
    }
  }
  return data;
}

function setFormError(name, message = "") {
  const target = document.querySelector(`[data-form-error="${name}"]`);
  if (target) target.textContent = message;
}

async function handleCreate(formName, endpoint, transform = (payload) => payload) {
  const form = document.getElementById(`${formName}-form`);
  if (!form) return;
  applyFriendlyFormDefaults(formName, form);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormError(formName);
    try {
      const payload = transform(formToObject(form));
      if (formName === "robot" && !payload.ipAddress) {
        throw new Error("请先扫描当前 Wi-Fi 网络，并选择已确认的机器人 IP。");
      }
      await apiFetch(endpoint, { method: "POST", body: JSON.stringify(payload) });
      form.reset();
      applyFriendlyFormDefaults(formName, form);
      if (formName === "zone") {
        resetZoneDraft();
      }
      if (formName === "robot") {
        state.robotDiscovery.selectedIp = "";
      }
      await loadDashboard();
    } catch (error) {
      setFormError(formName, error.message);
    }
  });
}

function bindZoneTools() {
  if (!document.getElementById("zone-form")) return;
  document.querySelectorAll("[data-zone-color]").forEach((button) => {
    button.addEventListener("click", () => {
      updateZoneColor(button.dataset.zoneColor);
    });
  });
  document.getElementById("zone-reset-button")?.addEventListener("click", () => {
    resetZoneDraft();
  });
  document.querySelectorAll("[data-zone-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const zone = (state.data?.zones || []).find((item) => Number(item.id) === Number(button.dataset.id));
      if (!zone) return;
      showCrudModal({
        title: `编辑区域：${zone.name}`,
        saveText: "保存区域",
        values: {
          name: zone.name,
          type: zone.type,
          risk: zone.risk,
          status: zone.status,
          frequency: zone.frequency,
          notes: zone.notes || "",
        },
        fields: [
          { name: "name", label: "区域名称", required: true },
          {
            name: "type",
            label: "区域类型",
            type: "select",
            options: [
              { value: "inspection", label: "巡检区" },
              { value: "charging", label: "充电区" },
              { value: "storage", label: "仓储区" },
              { value: "restricted", label: "管控区" },
            ],
          },
          {
            name: "risk",
            label: "风险等级",
            type: "select",
            options: [
              { value: "low", label: "低" },
              { value: "medium", label: "中" },
              { value: "high", label: "高" },
            ],
          },
          {
            name: "status",
            label: "状态",
            type: "select",
            options: [
              { value: "active", label: "启用" },
              { value: "paused", label: "暂停" },
            ],
          },
          { name: "frequency", label: "巡检频率" },
          { name: "notes", label: "备注", type: "textarea", className: "field-span-2" },
        ],
        onSubmit: async (payload) => {
          await apiFetch(`/api/zones/${zone.id}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          });
          await loadDashboard();
        },
      });
    });
  });
  document.querySelectorAll("[data-zone-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除该区域？")) return;
      await apiFetch(`/api/zones/${button.dataset.id}`, { method: "DELETE" });
      await loadDashboard();
    });
  });
  syncZoneDraftUi();
}

function bindRobotDiscoveryTools() {
  const form = document.getElementById("robot-form");
  if (!form) return;
  const select = document.getElementById("robot-discovery-select");
  const submitButton = form.querySelector('button[type="submit"]');
  if (select) {
    state.robotDiscovery.selectedIp = select.value || state.robotDiscovery.selectedIp || "";
    select.addEventListener("change", () => {
      state.robotDiscovery.selectedIp = select.value || "";
      if (submitButton) {
        submitButton.disabled = !state.robotDiscovery.selectedIp || state.robotDiscovery.loading;
      }
    });
  }
  document.getElementById("robot-discovery-refresh")?.addEventListener("click", async () => {
    await fetchRobotDiscovery(true);
  });
  if (!state.robotDiscovery.loading && !state.robotDiscovery.scannedAt && !state.robotDiscovery.items.length && !state.robotDiscovery.error) {
    void fetchRobotDiscovery(true);
  }
}

function bindDeleteButtons() {
  document.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await apiFetch(`/api/${button.dataset.delete}/${button.dataset.id}`, { method: "DELETE" });
        await loadDashboard();
      } catch (error) {
        window.alert(error.message);
      }
    });
  });
}

function bindForms() {
  handleCreate("task", "/api/tasks");
  handleCreate("robot", "/api/robots", (payload) => numericPayload(payload, ["zoneId", "health", "battery", "speed", "signal", "latency", "lng", "lat", "heading"]));
  handleCreate("alert", "/api/alerts");
  handleCreate("report", "/api/reports");
  handleCreate("zone", "/api/zones", (payload) => {
    if (state.zoneDraft.path.length < 3) {
      throw new Error("请先在地图上绘制至少 3 个点的区域。");
    }
    if (!state.zoneDraft.complete) {
      throw new Error("请双击地图完成区域绘制后再提交。");
    }
    return {
      ...payload,
      path: state.zoneDraft.path,
      strokeColor: state.zoneDraft.strokeColor,
      fillColor: state.zoneDraft.fillColor,
    };
  });
  bindZoneTools();
  bindRobotDiscoveryTools();
  bindDeleteButtons();
  if (state.pageId === "users") bindUsersPage();
  if (state.pageId === "devices") bindDevicesPage();
  if (state.pageId === "areas") bindAreasPage();
  if (state.pageId === "points") bindPointsPage();
  if (state.pageId === "routes") bindRoutesPage();
}

function numericPayload(payload, keys) {
  const next = { ...payload };
  keys.forEach((key) => {
    if (next[key] !== undefined && next[key] !== "") {
      next[key] = Number(next[key]);
    }
  });
  return next;
}

function syncRobotMarkersInEntry(entry) {
  if (!entry?.map || typeof window.AMap === "undefined") return;
  if (!entry.robotMarkers) {
    entry.robotMarkers = {};
  }
  const nextIds = new Set((state.data?.robots || []).map((robot) => String(robot.id)));
  Object.entries(entry.robotMarkers).forEach(([robotId, marker]) => {
    if (nextIds.has(robotId)) return;
    marker.setMap(null);
    delete entry.robotMarkers[robotId];
  });
  (state.data?.robots || []).forEach((robot) => {
    const robotId = String(robot.id);
    const position = Array.isArray(robot.location) ? robot.location : null;
    if (!position || position.length !== 2) return;
    const label = {
      content: `${escapeHtml(robot.model)} ${escapeHtml(String(robot.battery))}%`,
      direction: "top",
    };
    if (!entry.robotMarkers[robotId]) {
      entry.robotMarkers[robotId] = new AMap.Marker({
        map: entry.map,
        position,
        title: robotMarkerTitle(robot),
        bubble: true,
        label,
      });
      return;
    }
    entry.robotMarkers[robotId].setPosition(position);
    entry.robotMarkers[robotId].setTitle(robotMarkerTitle(robot));
    entry.robotMarkers[robotId].setLabel(label);
    entry.robotMarkers[robotId].setMap(entry.map);
  });
}

function syncRobotMarkersInMaps() {
  Object.values(state.maps).forEach((entry) => {
    syncRobotMarkersInEntry(entry);
  });
}

async function renderMaps() {
  const mapIds = ["overview-map", "zones-map", "points-map"].filter((id) => document.getElementById(id));
  state.maps = {};
  if (!mapIds.length) {
    return;
  }

  let userCoords = null;
  try {
    userCoords = await ensureUserLocation();
  } catch (error) {
    console.warn(error.message);
  }

  if (typeof window.AMap === "undefined") {
    mapIds.forEach((id) => {
      const container = document.getElementById(id);
      if (!container) return;
      const locationText = userCoords
        ? `当前网页定位：${state.geo.locationText || `${userCoords[1].toFixed(6)}, ${userCoords[0].toFixed(6)}`}`
        : "网页定位未获取成功，请检查浏览器定位权限。";
      const amapText = appConfig.amapKey
        ? "高德脚本加载失败，当前提供的 key 不是可用的 Web JS API Key。"
        : "未配置高德 Web JS API Key。";
      container.innerHTML = `<div class=\"map-fallback\"><div><p>${amapText}</p><p>${locationText}</p></div></div>`;
    });
    return;
  }

  mapIds.forEach((id) => {
    const container = document.getElementById(id);
    if (!container) return;
    container.innerHTML = "";
    const map = new AMap.Map(id, {
      zoom: state.data.site.zoom,
      center: userCoords || state.data.site.center,
    });
    state.maps[id] = { map, userMarker: null, draftPolyline: null, draftPolygon: null, robotMarkers: {} };
    map.addControl(new AMap.Scale());
    map.addControl(new AMap.ToolBar());
    state.data.zones.forEach((zone) => {
      new AMap.Polygon({
        map,
        path: zone.path,
        strokeColor: zone.strokeColor,
        fillColor: zone.fillColor,
        fillOpacity: 0.38,
        strokeWeight: 2,
        bubble: true,
      });
    });
    syncRobotMarkersInEntry(state.maps[id]);
    if (id === "points-map") {
      (state.pageData.points?.items || []).forEach((point) => {
        if (!Number.isFinite(Number(point.lng)) || !Number.isFinite(Number(point.lat))) return;
        new AMap.Marker({
          map,
          position: [Number(point.lng), Number(point.lat)],
          title: point.name,
          bubble: true,
          label: {
            content: escapeHtml(point.name),
            direction: "top",
          },
        });
      });
    }
    if (userCoords) {
      state.maps[id].userMarker = new AMap.Marker({
        map,
        position: userCoords,
        title: "我的当前位置",
        bubble: true,
        label: {
          content: "我",
          direction: "top",
        },
      });
    }
    if (id === "zones-map") {
      setupZoneDrawing(map);
    }
    if (id === "points-map") {
      setupPointPicker(map);
      if (state.pointDraft.coords) {
        if (!state.pointDraft.marker) {
          state.pointDraft.marker = new AMap.Marker({
            map,
            position: state.pointDraft.coords,
            title: `巡检点 | ${state.pointDraft.zoneName || "未命名区域"}`,
            bubble: true,
          });
        } else {
          state.pointDraft.marker.setPosition(state.pointDraft.coords);
          state.pointDraft.marker.setMap(map);
        }
      }
    }
  });
}

function canRefreshRealtimePage() {
  const active = document.activeElement;
  return !(active && (active.closest("form") || active.closest("dialog")));
}

function handleDashboardSocketMessage(message) {
  if (!message || message.type !== "dashboard_update" || !message.data) return;
  state.data = message.data;
  renderShellMeta();
  if (["overview", "status", "maintenance"].includes(state.pageId) && canRefreshRealtimePage()) {
    renderCurrentPage();
    return;
  }
  if (Object.keys(state.maps).length) {
    syncRobotMarkersInMaps();
  }
}

function clearRealtimeTimers() {
  if (state.realtime.heartbeatTimer) {
    window.clearInterval(state.realtime.heartbeatTimer);
    state.realtime.heartbeatTimer = null;
  }
  if (state.realtime.reconnectTimer) {
    window.clearTimeout(state.realtime.reconnectTimer);
    state.realtime.reconnectTimer = null;
  }
}

function scheduleDashboardSocketReconnect() {
  if (state.realtime.reconnectTimer) return;
  state.realtime.reconnectTimer = window.setTimeout(() => {
    state.realtime.reconnectTimer = null;
    connectDashboardSocket();
  }, 3000);
}

function connectDashboardSocket() {
  if (typeof window.WebSocket === "undefined") return;
  const currentSocket = state.realtime.socket;
  if (currentSocket && (currentSocket.readyState === WebSocket.OPEN || currentSocket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  clearRealtimeTimers();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`);
  state.realtime.socket = socket;
  socket.addEventListener("open", () => {
    if (state.realtime.socket !== socket) return;
    state.realtime.heartbeatTimer = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 20000);
  });
  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      handleDashboardSocketMessage(payload);
    } catch (error) {
      console.warn("实时消息解析失败。", error);
    }
  });
  socket.addEventListener("error", () => {
    if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
      socket.close();
    }
  });
  socket.addEventListener("close", () => {
    if (state.realtime.socket === socket) {
      state.realtime.socket = null;
    }
    if (state.realtime.heartbeatTimer) {
      window.clearInterval(state.realtime.heartbeatTimer);
      state.realtime.heartbeatTimer = null;
    }
    scheduleDashboardSocketReconnect();
  });
}

function tickClock() {
  clockPill.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

logoutButton?.addEventListener("click", async () => {
  await apiFetch("/auth/logout", { method: "POST" });
  window.location.href = "/login";
});

tickClock();
setInterval(tickClock, 1000);
startLocationWatch();

loadDashboard()
  .then(() => {
    connectDashboardSocket();
  })
  .catch((error) => {
    pageContent.innerHTML = `<section class="panel"><div class="empty-state">${escapeHtml(error.message)}</div></section>`;
  });
