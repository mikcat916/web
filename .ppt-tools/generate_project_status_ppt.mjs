import path from "node:path";
import pptxgen from "pptxgenjs";

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "OpenAI Codex";
pptx.company = "Project4";
pptx.subject = "项目进展与后续工作汇报";
pptx.title = "Project4 项目进展与后续工作汇报";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};

const COLORS = {
  navy: "13315C",
  blue: "1F6FEB",
  cyan: "35C2F1",
  green: "16A34A",
  orange: "EA580C",
  red: "DC2626",
  text: "1E293B",
  muted: "64748B",
  line: "D9E4F0",
  soft: "EEF6FF",
  soft2: "F8FBFF",
  white: "FFFFFF",
};

function addBackground(slide) {
  slide.background = { color: "F7FAFC" };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.35,
    line: { color: COLORS.navy, transparency: 100 },
    fill: { color: COLORS.navy },
  });
}

function addHeader(slide, title, subtitle = "") {
  addBackground(slide);
  slide.addText(title, {
    x: 0.6,
    y: 0.55,
    w: 7.8,
    h: 0.5,
    fontFace: "Microsoft YaHei",
    fontSize: 24,
    bold: true,
    color: COLORS.navy,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.6,
      y: 1.0,
      w: 9.4,
      h: 0.35,
      fontFace: "Microsoft YaHei",
      fontSize: 10,
      color: COLORS.muted,
    });
  }
  slide.addText("Project4 | 机器人巡检监控系统", {
    x: 9.1,
    y: 0.62,
    w: 3.5,
    h: 0.3,
    align: "right",
    fontFace: "Microsoft YaHei",
    fontSize: 10,
    color: COLORS.muted,
  });
}

function addFooter(slide, pageNo) {
  slide.addText(`汇报页 ${pageNo}`, {
    x: 11.7,
    y: 7.0,
    w: 1.0,
    h: 0.25,
    align: "right",
    fontFace: "Microsoft YaHei",
    fontSize: 9,
    color: COLORS.muted,
  });
}

function addBulletList(slide, items, opts = {}) {
  const runs = [];
  items.forEach((item) => {
    runs.push({
      text: item,
      options: {
        bullet: { indent: 14 },
        hanging: 3,
        breakLine: true,
      },
    });
  });
  slide.addText(runs, {
    x: opts.x ?? 0.9,
    y: opts.y ?? 1.6,
    w: opts.w ?? 5.2,
    h: opts.h ?? 4.5,
    fontFace: "Microsoft YaHei",
    fontSize: opts.fontSize ?? 16,
    color: COLORS.text,
    valign: "top",
    paraSpaceAfterPt: 10,
    breakLine: false,
  });
}

function addTag(slide, text, x, y, color) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w: 1.55,
    h: 0.38,
    rectRadius: 0.08,
    line: { color, transparency: 100 },
    fill: { color, transparency: 12 },
  });
  slide.addText(text, {
    x: x + 0.08,
    y: y + 0.07,
    w: 1.39,
    h: 0.18,
    align: "center",
    fontFace: "Microsoft YaHei",
    fontSize: 10,
    bold: true,
    color,
  });
}

// Slide 1
{
  const slide = pptx.addSlide();
  slide.background = { color: COLORS.white };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 7.5,
    line: { color: COLORS.white, transparency: 100 },
    fill: { color: "F3F8FF" },
  });
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.42,
    line: { color: COLORS.navy, transparency: 100 },
    fill: { color: COLORS.navy },
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8,
    y: 0.9,
    w: 1.65,
    h: 0.45,
    rectRadius: 0.08,
    line: { color: COLORS.cyan, transparency: 100 },
    fill: { color: COLORS.cyan, transparency: 10 },
  });
  slide.addText("项目阶段汇报", {
    x: 0.93,
    y: 1.03,
    w: 1.4,
    h: 0.18,
    fontFace: "Microsoft YaHei",
    fontSize: 11,
    bold: true,
    color: COLORS.blue,
    align: "center",
  });
  slide.addText("Project4 机器人巡检监控系统", {
    x: 0.8,
    y: 1.7,
    w: 7.4,
    h: 0.8,
    fontFace: "Microsoft YaHei",
    fontSize: 28,
    bold: true,
    color: COLORS.navy,
  });
  slide.addText("当前进展总结与后续工作规划", {
    x: 0.8,
    y: 2.45,
    w: 5.8,
    h: 0.4,
    fontFace: "Microsoft YaHei",
    fontSize: 16,
    color: COLORS.muted,
  });
  slide.addText("汇报内容包含：项目概况、阶段成果、当前状态、后续里程碑与风险关注点。", {
    x: 0.8,
    y: 3.15,
    w: 6.5,
    h: 0.6,
    fontFace: "Microsoft YaHei",
    fontSize: 14,
    color: COLORS.text,
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 8.0,
    y: 1.2,
    w: 4.4,
    h: 4.8,
    rectRadius: 0.12,
    line: { color: COLORS.line, pt: 1 },
    fill: { color: COLORS.white },
    shadow: { type: "outer", color: "BFD4EA", blur: 2, angle: 45, distance: 2, opacity: 0.18 },
  });
  slide.addText("进度快照", {
    x: 8.35,
    y: 1.55,
    w: 2.0,
    h: 0.3,
    fontFace: "Microsoft YaHei",
    fontSize: 16,
    bold: true,
    color: COLORS.navy,
  });
  addTag(slide, "阶段一完成", 8.35, 2.1, COLORS.green);
  addTag(slide, "阶段二完成", 10.1, 2.1, COLORS.green);
  addTag(slide, "阶段三完成", 8.35, 2.6, COLORS.green);
  addTag(slide, "阶段四待启动", 10.1, 2.6, COLORS.orange);
  addTag(slide, "阶段五待启动", 8.35, 3.1, COLORS.orange);
  slide.addText("Web 后台已形成可操作界面，当前重点转向设备通信接入与系统联调。", {
    x: 8.35,
    y: 3.8,
    w: 3.5,
    h: 1.1,
    fontFace: "Microsoft YaHei",
    fontSize: 14,
    color: COLORS.text,
    margin: 0.04,
  });
  slide.addText("日期：2026-03-29", {
    x: 0.8,
    y: 6.65,
    w: 2.2,
    h: 0.2,
    fontFace: "Microsoft YaHei",
    fontSize: 10,
    color: COLORS.muted,
  });
}

// Slide 2
{
  const slide = pptx.addSlide();
  addHeader(slide, "01 项目概况", "面向机器人巡检场景的管理平台，包含 Web 应用与桌面端两个子项目");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.7, y: 1.5, w: 5.8, h: 4.9,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("项目定位", {
    x: 1.0, y: 1.8, w: 1.8, h: 0.3, fontSize: 18, bold: true, color: COLORS.navy, fontFace: "Microsoft YaHei",
  });
  addBulletList(slide, [
    "为机器人巡检提供统一的管理、配置、监控与数据沉淀能力。",
    "当前仓库同时包含 Web 端后台系统与桌面端 UAV 控制客户端。",
    "Web 端采用 FastAPI + Jinja2 + MySQL + 原生 JavaScript，强调前后端一体化。",
    "桌面端采用 Python + PyQt5 + qfluentwidgets，作为现场控制与专用操作界面。",
  ], { x: 1.0, y: 2.25, w: 5.0, h: 3.7, fontSize: 16 });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.8, y: 1.5, w: 5.8, h: 4.9,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("当前系统结构", {
    x: 7.1, y: 1.8, w: 2.2, h: 0.3, fontSize: 18, bold: true, color: COLORS.navy, fontFace: "Microsoft YaHei",
  });
  const tableRows = [
    [
      { text: "模块", options: { bold: true, color: COLORS.white, fill: COLORS.navy } },
      { text: "职责", options: { bold: true, color: COLORS.white, fill: COLORS.navy } },
    ],
    ["backend", "Web 管理后台、接口服务、鉴权、数据持久化"],
    ["desktop", "桌面端控制界面、任务操作、状态查看"],
    ["MySQL", "用户、设备、区域、点位、路线等业务数据存储"],
    ["todolist", "阶段规划、交付检查与后续工作清单"],
  ];
  slide.addTable(tableRows, {
    x: 7.1,
    y: 2.3,
    w: 5.0,
    border: { pt: 1, color: COLORS.line },
    fontFace: "Microsoft YaHei",
    fontSize: 13,
    color: COLORS.text,
    rowH: 0.45,
    fill: COLORS.white,
    margin: 0.05,
  });
  addFooter(slide, 2);
}

// Slide 3
{
  const slide = pptx.addSlide();
  addHeader(slide, "02 当前进展总览", "依据 todolist 统计：阶段一到阶段三已完成，阶段四与阶段五尚未开始");
  slide.addChart(pptx.ChartType.bar, [
    {
      name: "完成度",
      labels: ["阶段一", "阶段二", "阶段三", "阶段四", "阶段五"],
      values: [100, 100, 100, 0, 0],
    },
  ], {
    x: 0.8,
    y: 1.6,
    w: 6.2,
    h: 4.6,
    catAxisLabelFontFace: "Microsoft YaHei",
    catAxisLabelFontSize: 12,
    valAxisLabelFontFace: "Microsoft YaHei",
    valAxisLabelFontSize: 11,
    valAxisMinVal: 0,
    valAxisMaxVal: 100,
    valAxisMajorUnit: 20,
    showLegend: false,
    showTitle: false,
    chartColors: [COLORS.blue],
    showValue: true,
    dataLabelColor: COLORS.text,
    dataLabelPosition: "outEnd",
    showCatName: false,
    showValAxisTitle: false,
    showCatAxisTitle: false,
    gridLine: { color: "DCE6F2" },
  });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 7.45, y: 1.8, w: 4.9, h: 4.2,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("已完成阶段", {
    x: 7.8, y: 2.15, w: 1.8, h: 0.3, fontSize: 18, bold: true, color: COLORS.navy, fontFace: "Microsoft YaHei",
  });
  addBulletList(slide, [
    "阶段一：完成业务关系梳理、MySQL 表结构设计和数据库脚本执行。",
    "阶段二：完成用户、设备、区域、点位、路线等后端 CRUD API 和鉴权能力。",
    "阶段三：完成 Web 后台框架、登录页、用户管理、设备管理、巡检配置界面。",
  ], { x: 7.8, y: 2.6, w: 4.0, h: 2.4, fontSize: 15 });
  slide.addText("结论：项目已从“后端能力搭建”进入“物联接入与联调验证”阶段。", {
    x: 7.8, y: 5.35, w: 4.0, h: 0.6, fontFace: "Microsoft YaHei", fontSize: 14, bold: true, color: COLORS.orange,
  });
  addFooter(slide, 3);
}

// Slide 4
{
  const slide = pptx.addSlide();
  addHeader(slide, "03 已交付成果", "从数据层、接口层到前端交互层，当前主线闭环已经形成");
  const cards = [
    {
      x: 0.8, title: "数据与模型", color: COLORS.blue, items: [
        "完成 users / devices / areas / points / routes 核心表设计。",
        "建立区域、设备、点位、路线之间的业务关联关系。",
        "数据库脚本已可支撑当前后台管理能力。"
      ],
    },
    {
      x: 4.45, title: "后端 API", color: COLORS.green, items: [
        "完成登录鉴权、用户状态切换、设备 CRUD、巡检配置 CRUD。",
        "支持设备图片上传与路径保存。",
        "支持路线与点位绑定、排序写入。"
      ],
    },
    {
      x: 8.1, title: "Web 前端", color: COLORS.orange, items: [
        "完成登录页与后台框架布局。",
        "完成用户、设备、区域、点位、路线管理页面。",
        "新增弹窗表单、设备筛选、图片预览、路线编排交互。"
      ],
    },
  ];
  cards.forEach((card) => {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: card.x, y: 1.8, w: 3.0, h: 4.6,
      rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
    });
    slide.addShape(pptx.ShapeType.rect, {
      x: card.x, y: 1.8, w: 3.0, h: 0.18,
      line: { color: card.color, transparency: 100 }, fill: { color: card.color },
    });
    slide.addText(card.title, {
      x: card.x + 0.25, y: 2.15, w: 2.1, h: 0.28,
      fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: COLORS.navy,
    });
    addBulletList(slide, card.items, {
      x: card.x + 0.18, y: 2.65, w: 2.5, h: 3.2, fontSize: 13,
    });
  });
  addFooter(slide, 4);
}

// Slide 5
{
  const slide = pptx.addSlide();
  addHeader(slide, "04 当前状态判断", "项目已具备后台操作能力，但尚未形成真实设备在线闭环");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.6, w: 5.9, h: 4.8,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("当前可演示内容", {
    x: 1.1, y: 1.95, w: 2.6, h: 0.3, fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: COLORS.navy,
  });
  addBulletList(slide, [
    "基于 FastAPI + Jinja2 的管理后台页面已可访问与操作。",
    "用户、设备、区域、点位、路线等核心主数据已可录入和维护。",
    "设备表单支持图片预览与上传；路线管理支持点位编排。",
    "桌面端工程仍在仓库内，可作为后续端到端联动对象。"
  ], { x: 1.1, y: 2.35, w: 5.0, h: 3.4, fontSize: 15 });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 7.0, y: 1.6, w: 5.5, h: 4.8,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("当前主要缺口", {
    x: 7.3, y: 1.95, w: 2.4, h: 0.3, fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: COLORS.navy,
  });
  addBulletList(slide, [
    "尚未确定设备通信协议，阶段四工作未启动。",
    "尚未实现设备上报数据接入、解析与实时状态更新。",
    "尚未开展阶段五联调测试，缺少完整业务链路验证。",
    "目前以管理后台为主，监控大屏与在线监测能力还未交付。"
  ], { x: 7.3, y: 2.35, w: 4.6, h: 3.4, fontSize: 15 });
  addFooter(slide, 5);
}

// Slide 6
{
  const slide = pptx.addSlide();
  addHeader(slide, "05 后续工作重点", "建议按“先打通数据链路，再做联调验收”的顺序推进阶段四和阶段五");
  const roadmapRows = [
    [
      { text: "工作阶段", options: { bold: true, color: COLORS.white, fill: COLORS.navy } },
      { text: "重点事项", options: { bold: true, color: COLORS.white, fill: COLORS.navy } },
      { text: "预期产出", options: { bold: true, color: COLORS.white, fill: COLORS.navy } },
    ],
    ["阶段四-通信方案", "确定 HTTP API / MQTT / TCP / UDP / WebSocket 等设备接入协议", "形成技术选型与消息规范"],
    ["阶段四-数据接入", "开发设备数据接收接口与解析逻辑，接入状态、异常和巡检打卡数据", "打通真实设备到 MySQL 的数据链路"],
    ["阶段四-可视化", "按需补充实时监控大屏或状态面板", "形成在线运行态监控界面"],
    ["阶段五-接口联调", "验证后台表单、接口、数据库、设备数据接入流程", "稳定的端到端交付链路"],
    ["阶段五-流程测试", "执行用户 -> 区域 -> 设备 -> 路线的业务闭环测试", "可演示、可验收的系统版本"],
  ];
  slide.addTable(roadmapRows, {
    x: 0.8,
    y: 1.7,
    w: 11.7,
    border: { pt: 1, color: COLORS.line },
    fontFace: "Microsoft YaHei",
    fontSize: 12,
    color: COLORS.text,
    rowH: 0.52,
    margin: 0.05,
    fill: COLORS.white,
  });
  slide.addText("推进原则：优先明确通信协议与接入方式，这是后续实时监控与联调测试的前置条件。", {
    x: 0.9,
    y: 6.55,
    w: 11.2,
    h: 0.35,
    fontFace: "Microsoft YaHei",
    fontSize: 14,
    bold: true,
    color: COLORS.orange,
  });
  addFooter(slide, 6);
}

// Slide 7
{
  const slide = pptx.addSlide();
  addHeader(slide, "06 风险与建议", "当前最大不确定性集中在物联通信方案和联调资源准备");
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.7, w: 5.7, h: 4.8,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("主要风险", {
    x: 1.1, y: 2.0, w: 2.0, h: 0.3, fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: COLORS.red,
  });
  addBulletList(slide, [
    "通信协议迟迟未定，会阻塞设备接入接口和实时功能开发。",
    "缺少真实或模拟设备数据源，会影响阶段四和阶段五验证深度。",
    "当前前端已完成较多管理能力，若没有尽快进入联调，易出现功能与真实场景脱节。"
  ], { x: 1.1, y: 2.45, w: 4.9, h: 3.5, fontSize: 15 });
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.95, y: 1.7, w: 5.55, h: 4.8,
    rectRadius: 0.08, line: { color: COLORS.line, pt: 1 }, fill: { color: COLORS.white },
  });
  slide.addText("建议动作", {
    x: 7.25, y: 2.0, w: 2.0, h: 0.3, fontFace: "Microsoft YaHei", fontSize: 18, bold: true, color: COLORS.green,
  });
  addBulletList(slide, [
    "优先召开一次通信方案评审，明确设备端接入协议和报文结构。",
    "尽快准备模拟设备发送脚本或测试终端，先打通接入链路。",
    "将阶段五的流程测试设计前置，与阶段四同步推进，减少返工。"
  ], { x: 7.25, y: 2.45, w: 4.7, h: 3.5, fontSize: 15 });
  slide.addText("总结：项目主干能力已经具备，下一阶段的成败关键不在页面，而在“设备是否真正接进来”。", {
    x: 0.95,
    y: 6.65,
    w: 11.4,
    h: 0.32,
    fontFace: "Microsoft YaHei",
    fontSize: 14,
    bold: true,
    color: COLORS.navy,
    align: "center",
  });
  addFooter(slide, 7);
}

const output = path.resolve(process.cwd(), "Project4_项目进展与后续工作汇报.pptx");
await pptx.writeFile({ fileName: output });
console.log(output);
