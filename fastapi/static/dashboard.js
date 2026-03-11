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

const state = {
  pageId: appConfig.pageId,
  data: null,
  maps: {},
  geo: {
    coords: null,
    promise: null,
    status: "idle",
    watchId: null,
    locationText: null,
  },
};

const TOKEN_TEXT = {
  active: "运行中",
  charging: "充电中",
  critical: "严重",
  degraded: "性能下降",
  good: "良好",
  healthy: "正常",
  high: "高",
  idle: "待命",
  info: "提示",
  inspection: "巡检区",
  low: "低",
  medium: "中",
  neutral: "平稳",
  offline: "离线",
  online: "在线",
  paused: "暂停",
  positive: "上升",
  restricted: "管控区",
  scheduled: "已排期",
  storage: "仓储区",
  warning: "告警",
};

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
      path: "[[121.81742,31.09161],[121.81942,31.09161],[121.81842,31.09321]]",
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
                <p>${escapeHtml(robot.zoneName)} · ${formatDateTime(robot.createdAt)}</p>
                <div class="inline-meta">
                  <span class="${pillClass(robot.status)}">${escapeHtml(localizeToken(robot.status))}</span>
                  <span class="meta-pill">电量 ${robot.battery}%</span>
                  <span class="meta-pill">健康度 ${robot.health}%</span>
                </div>
              </div>
              <div class="muted">速度 ${robot.speed} m/s</div>
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
  return `
    ${renderStats()}
    <section class="dual-grid">
      <article class="panel">
        <div class="panel-header"><div><h2>新增机器人</h2><p class="muted">将机器人注册到当前车队</p></div></div>
        <form id="robot-form" class="stack-form">
          <div class="grid-form">
            <label><span>名称</span><input name="model" placeholder="例：巡检机器人-01" required></label>
            <label><span>区域 ID</span><input name="zoneId" type="number"></label>
            <label><span>状态</span><select name="status"><option value="idle">待命</option><option value="active">执行中</option><option value="charging">充电中</option><option value="offline">离线</option></select></label>
            <label><span>健康度</span><input name="health" type="number" value="92" min="0" max="100"></label>
            <label><span>电量</span><input name="battery" type="number" value="78" min="0" max="100"></label>
            <label><span>速度</span><input name="speed" type="number" step="0.1" value="1.2"></label>
            <label><span>信号</span><input name="signal" type="number" value="88" min="0" max="100"></label>
            <label><span>延迟</span><input name="latency" type="number" value="28"></label>
            <label><span>经度</span><input name="lng" type="number" step="0.000001" value="121.81742"></label>
            <label><span>纬度</span><input name="lat" type="number" step="0.000001" value="31.09161"></label>
            <label><span>航向角</span><input name="heading" type="number" value="0" min="0" max="360"></label>
          </div>
          <div class="button-row"><button class="primary-button" type="submit">添加机器人</button></div>
          <p class="form-error" data-form-error="robot"></p>
        </form>
      </article>
      <article class="panel">
        <div class="panel-header"><div><h2>机器人状态板</h2><p class="muted">遥测与运行状态</p></div></div>
        ${renderTable("robots", ["ID", "机器人名称", "区域", "状态", "电量", "健康度", "信号", "操作"], state.data.robots.map((robot) => `
          <tr>
            <td>${robot.id}</td>
            <td>${escapeHtml(robot.model)}</td>
            <td>${escapeHtml(robot.zoneName)}</td>
            <td><span class="${pillClass(robot.status)}">${escapeHtml(localizeToken(robot.status))}</span></td>
            <td>${robot.battery}%</td>
            <td>${robot.health}%</td>
            <td>${robot.signal}%</td>
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
        <div class="panel-header"><div><h2>新建区域</h2><p class="muted">使用 JSON 多边形坐标定义巡检区域</p></div></div>
        <form id="zone-form" class="stack-form">
          <div class="grid-form">
            <label><span>区域名称</span><input name="name" placeholder="例：1号泊位巡检区" required></label>
            <label><span>区域类型</span><select name="type"><option value="inspection">巡检区</option><option value="charging">充电区</option><option value="storage">仓储区</option><option value="restricted">管控区</option></select></label>
            <label><span>风险等级</span><select name="risk"><option value="low">低</option><option value="medium" selected>中</option><option value="high">高</option></select></label>
            <label><span>状态</span><select name="status"><option value="active" selected>启用</option><option value="paused">暂停</option></select></label>
            <label><span>巡检频率</span><input name="frequency" value="30分钟/次"></label>
            <label><span>边框颜色</span><input name="strokeColor" value="#7cc7ff"></label>
            <label><span>填充颜色</span><input name="fillColor" value="rgba(124, 199, 255, 0.18)"></label>
          </div>
          <label><span>多边形路径 JSON</span><textarea name="path">[[121.81742,31.09161],[121.81942,31.09161],[121.81842,31.09321]]</textarea></label>
          <label><span>备注</span><textarea name="notes" placeholder="说明区域用途、重点设备和巡检要求"></textarea></label>
          <div class="button-row"><button class="primary-button" type="submit">创建区域</button></div>
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
              </div>
            </div>
          `).join("") : `<div class="empty-state">暂无区域配置。</div>`}
        </div>
      </article>
    </section>
  `;
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
  };
  pageContent.innerHTML = renderers[state.pageId]();
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
      await apiFetch(endpoint, { method: "POST", body: JSON.stringify(payload) });
      form.reset();
      applyFriendlyFormDefaults(formName, form);
      await loadDashboard();
    } catch (error) {
      setFormError(formName, error.message);
    }
  });
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
  handleCreate("zone", "/api/zones");
  bindDeleteButtons();
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

async function renderMaps() {
  const mapIds = ["overview-map", "zones-map"].filter((id) => document.getElementById(id));
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
    state.maps[id] = { map, userMarker: null };
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
      });
    });
    state.data.robots.forEach((robot) => {
      new AMap.Marker({
        map,
        position: robot.location,
        title: `${robot.model}（${localizeToken(robot.status)}）`,
      });
    });
    if (userCoords) {
      state.maps[id].userMarker = new AMap.Marker({
        map,
        position: userCoords,
        title: "我的当前位置",
        label: {
          content: "我",
          direction: "top",
        },
      });
    }
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

loadDashboard().catch((error) => {
  pageContent.innerHTML = `<section class="panel"><div class="empty-state">${escapeHtml(error.message)}</div></section>`;
});
