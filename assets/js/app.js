(() => {
  "use strict";

  const metricConfig = {
    price: { label: "BTC 现货价格", color: "#e0ae54", decimals: 0, currency: true },
    nupl: { label: "NUPL", color: "#4fbe8a", decimals: 3 },
    realizedPrice: { label: "已实现价格", color: "#55bdc6", decimals: 0, currency: true },
    mvrv: { label: "MVRV", color: "#4d9de0", decimals: 2 },
    mvrvZ: { label: "MVRV Z-Score", color: "#ef6f51", decimals: 2 },
    leverage: { label: "杠杆代理", color: "#9d87db", decimals: 4 },
    wwi: { label: "狼波周期指数", color: "#e55c6d", decimals: 3 },
  };

  const overviewSeries = [
    { key: "nupl", component: "nupl", label: "NUPL", color: "#4fbe8a" },
    { key: "realizedPrice", component: "priceToRealized", label: "价格 / 已实现价格", color: "#55bdc6" },
    { key: "mvrv", component: "mvrv", label: "MVRV", color: "#4d9de0" },
    { key: "mvrvZ", component: "mvrvZ", label: "MVRV Z", color: "#ef6f51" },
    { key: "leverage", component: "leverage", label: "杠杆代理", color: "#9d87db" },
    { key: "wwi", component: "wwi", label: "狼波周期指数", color: "#e55c6d" },
  ];

  const bearMarketWindows = [
    { cycle: "2011", start: "2011-06-01", end: "2012-11-28" },
    { cycle: "2015", start: "2013-12-01", end: "2016-07-09" },
    { cycle: "2018", start: "2017-12-01", end: "2020-05-11" },
    { cycle: "2022", start: "2021-11-01", end: "2024-04-20" },
  ];

  const bottomComparisonMetrics = [
    { key: "price", label: "BTC 现货价格" },
    { key: "nupl", label: "NUPL" },
    { key: "realizedPrice", label: "已实现价格" },
    { key: "mvrv", label: "MVRV" },
    { key: "mvrvZ", label: "MVRV Z-Score" },
    { key: "leverage", label: "杠杆代理" },
    { key: "wwi", label: "狼波周期指数" },
    { key: "riskScore", label: "综合风险分" },
  ];

  const state = {
    data: null,
    chart: null,
    tab: "overview",
    range: 365,
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  function formatMetric(key, value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "暂不可用";
    const config = metricConfig[key];
    if (config.currency) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: config.decimals,
      }).format(value);
    }
    return Number(value).toFixed(config.decimals);
  }

  function formatChange(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return { text: "--", className: "" };
    const number = Number(value);
    return {
      text: `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`,
      className: number > 0 ? "change-up" : number < 0 ? "change-down" : "",
    };
  }

  function riskState(score) {
    if (score === null || score === undefined) return { label: "数据不足", tone: "muted", detail: "等待有效指标形成综合判断。" };
    if (score >= 85) return { label: "接近牛市顶部", tone: "danger", detail: "多项指标处于历史高分位，顶部风险已进入高关注区。" };
    if (score >= 70) return { label: "顶部风险升高", tone: "warning", detail: "估值或杠杆信号偏热，但尚未形成明确顶部共振。" };
    if (score <= 15) return { label: "接近熊市底部", tone: "positive", detail: "多项指标处于历史低分位，底部信号已进入高关注区。" };
    if (score <= 30) return { label: "底部区间观察", tone: "info", detail: "估值信号偏冷，正在靠近历史底部观察区。" };
    return { label: "周期中性区间", tone: "neutral", detail: "顶部与底部信号均未形成共振，市场仍处于周期中段。" };
  }

  function sourceLabel(sourceAge) {
    return { live: "尽量实时", daily: "日更", block: "区块实时", cached: "上次有效值" }[sourceAge] || "--";
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("dragon-wave-theme", theme);
    const icon = theme === "dark" ? "sun" : "moon";
    $("#themeButton").innerHTML = `<i data-lucide="${icon}"></i>`;
    if (window.lucide) window.lucide.createIcons();
    if (state.chart) renderChart();
  }

  function initTheme() {
    const saved = localStorage.getItem("dragon-wave-theme") || "dark";
    applyTheme(saved);
  }

  function setFreshness(kind, text) {
    const element = $("#freshness");
    element.classList.remove("ready", "error");
    if (kind) element.classList.add(kind);
    $("#freshnessText").textContent = text;
  }

  function relativeUpdateTime(iso) {
    if (!iso) return "更新时间未知";
    const timestamp = new Date(iso);
    const minutes = Math.max(0, Math.round((Date.now() - timestamp.getTime()) / 60000));
    if (minutes < 2) return "刚刚更新";
    if (minutes < 60) return `${minutes} 分钟前更新`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} 小时前更新`;
    return timestamp.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function renderAssessment() {
    const assessment = state.data.assessment || {};
    const score = assessment.riskScore;
    const currentState = riskState(score);
    const outlook = assessment.outlook7d || {};
    $("#assessmentTitle").textContent = currentState.label;
    $("#assessmentDetail").textContent = currentState.detail;
    const badge = $("#riskBadge");
    badge.textContent = score === null || score === undefined ? "--" : `${Number(score).toFixed(1)} / 100`;
    badge.className = `risk-badge tone-${currentState.tone}`;
    $("#riskScore").textContent = score === null || score === undefined ? "--" : Number(score).toFixed(1);
    const position = score === null || score === undefined ? 50 : Math.max(0, Math.min(100, score));
    $("#riskFill").style.width = `${position}%`;
    $("#riskMarker").style.left = `${position}%`;
    $("#outlookLabel").textContent = outlook.label || "暂无法形成七日判断";
    $("#outlookDetail").textContent = outlook.detail || "等待下一次数据更新。";
  }

  function renderMetrics() {
    Object.keys(metricConfig).forEach((key) => {
      const metric = state.data.current?.[key] || {};
      const valueElement = document.querySelector(`[data-value="${key}"]`);
      const changeElement = document.querySelector(`[data-change="${key}"]`);
      const sourceElement = document.querySelector(`[data-source="${key}"]`);
      valueElement.textContent = formatMetric(key, metric.value);
      const change = formatChange(metric.change7d);
      changeElement.textContent = change.text;
      changeElement.className = change.className;
      sourceElement.textContent = sourceLabel(metric.sourceAge);
    });
    $("#dailyDataDate").textContent = `链上数据 ${state.data.metadata?.dailyDataDate || "--"}`;
  }

  function findBearMarketBottoms() {
    const series = state.data.series || [];
    return bearMarketWindows.map((window) => {
      const candidates = series.filter((row) => row.date >= window.start && row.date <= window.end && row.price !== null && row.price !== undefined);
      const row = candidates.reduce((lowest, candidate) => (!lowest || Number(candidate.price) < Number(lowest.price) ? candidate : lowest), null);
      return { ...window, row };
    });
  }

  function formatComparisonValue(key, value, historical = false) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return historical ? "无历史数据" : "暂不可用";
    if (key === "riskScore") return Number(value).toFixed(1);
    return formatMetric(key, value);
  }

  function appendComparisonCell(row, text, className = "") {
    const cell = document.createElement("td");
    cell.textContent = text;
    if (className) cell.className = className;
    if (text === "无历史数据" || text === "暂不可用") cell.classList.add("no-history");
    row.appendChild(cell);
  }

  function renderBottomComparison() {
    const bottoms = findBearMarketBottoms();
    const header = $("#bottomComparisonHead");
    const body = $("#bottomComparisonBody");
    const headerRow = document.createElement("tr");
    const metricHeader = document.createElement("th");
    metricHeader.scope = "col";
    metricHeader.textContent = "指标";
    headerRow.appendChild(metricHeader);

    const currentHeader = document.createElement("th");
    currentHeader.scope = "col";
    currentHeader.className = "bottom-current";
    const currentTitle = document.createElement("strong");
    currentTitle.textContent = "当前";
    const currentDate = document.createElement("span");
    currentDate.textContent = state.data.metadata?.dailyDataDate || "--";
    currentHeader.append(currentTitle, currentDate);
    headerRow.appendChild(currentHeader);

    bottoms.forEach((bottom) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      const title = document.createElement("strong");
      title.textContent = `${bottom.cycle} 底部`;
      const date = document.createElement("span");
      date.textContent = bottom.row?.date || "--";
      cell.append(title, date);
      headerRow.appendChild(cell);
    });
    header.replaceChildren(headerRow);

    const rows = bottomComparisonMetrics.map((metric) => {
      const row = document.createElement("tr");
      if (metric.key === "riskScore") row.className = "comparison-risk";
      const label = document.createElement("th");
      label.scope = "row";
      label.textContent = metric.label;
      row.appendChild(label);
      const currentValue = metric.key === "riskScore" ? state.data.assessment?.riskScore : state.data.current?.[metric.key]?.value;
      appendComparisonCell(row, formatComparisonValue(metric.key, currentValue), "bottom-current");
      bottoms.forEach((bottom) => appendComparisonCell(row, formatComparisonValue(metric.key, bottom.row?.[metric.key], true)));
      return row;
    });
    body.replaceChildren(...rows);
  }

  function filteredDailySeries() {
    const series = state.data.series || [];
    if (state.range === "all" || !series.length) return series;
    const end = new Date(`${series[series.length - 1].date}T00:00:00Z`);
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - Number(state.range));
    return series.filter((row) => new Date(`${row.date}T00:00:00Z`) >= start);
  }

  function filteredLeverageSeries() {
    const series = state.data.leverageSeries || [];
    if (state.range === "all") return series;
    const cutoff = Date.now() - Number(state.range) * 86400000;
    return series.filter((point) => new Date(point.time).getTime() >= cutoff);
  }

  function chartColors() {
    const styles = getComputedStyle(document.documentElement);
    return {
      text: styles.getPropertyValue("--muted").trim(),
      grid: styles.getPropertyValue("--border").trim(),
      surface: styles.getPropertyValue("--surface").trim(),
    };
  }

  function chartOptions(yFormat, min, max) {
    const colors = chartColors();
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      animation: { duration: 260 },
      plugins: {
        legend: {
          display: state.tab === "overview",
          position: "bottom",
          align: "start",
          labels: { color: colors.text, boxWidth: 9, boxHeight: 9, padding: 18, font: { size: 10 } },
        },
        tooltip: {
          backgroundColor: colors.surface,
          titleColor: colors.text,
          bodyColor: colors.text,
          borderColor: colors.grid,
          borderWidth: 1,
          padding: 11,
          callbacks: {
            label: (context) => `${context.dataset.label}: ${yFormat(context.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: colors.text, maxTicksLimit: 7, maxRotation: 0, font: { size: 10 } },
          border: { color: colors.grid },
        },
        y: {
          min,
          max,
          grid: { color: colors.grid, drawTicks: false },
          ticks: { color: colors.text, padding: 10, maxTicksLimit: 6, font: { size: 10 }, callback: yFormat },
          border: { display: false },
        },
      },
    };
  }

  function overviewChartData(rows) {
    const datasets = overviewSeries.map((item) => ({
      label: item.label,
      data: rows.map((row) => row.riskComponents?.[item.component] ?? null),
      borderColor: item.color,
      backgroundColor: item.color,
      borderWidth: 1.7,
      pointRadius: 0,
      pointHoverRadius: 3,
      spanGaps: true,
      tension: 0.14,
    }));
    datasets.unshift({
      label: "综合风险",
      data: rows.map((row) => row.riskScore ?? null),
      borderColor: "#f2f6f7",
      backgroundColor: "#f2f6f7",
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 3,
      spanGaps: true,
      tension: 0.12,
    });
    return { labels: rows.map((row) => row.date), datasets };
  }

  function renderChart() {
    if (!state.data || !window.Chart) return;
    const canvas = $("#historyChart");
    const empty = $("#chartEmpty");
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }

    let chartData;
    let options;
    let hasData = true;
    if (state.tab === "overview") {
      const rows = filteredDailySeries();
      chartData = overviewChartData(rows);
      options = chartOptions((value) => `${Number(value).toFixed(0)}`, 0, 100);
      $("#chartTitle").textContent = "综合风险分位";
      $("#chartSubtitle").textContent = "各指标统一映射至 0–100，便于横向比较。";
    } else if (state.tab === "leverage") {
      const rows = filteredLeverageSeries();
      hasData = rows.some((row) => row.value !== null && row.value !== undefined);
      chartData = {
        labels: rows.map((row) => new Date(row.time).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })),
        datasets: [{ label: metricConfig.leverage.label, data: rows.map((row) => row.value), borderColor: metricConfig.leverage.color, backgroundColor: `${metricConfig.leverage.color}22`, borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, fill: true, tension: .16 }],
      };
      options = chartOptions((value) => Number(value).toFixed(4));
      $("#chartTitle").textContent = metricConfig.leverage.label;
      $("#chartSubtitle").textContent = "公开未平仓量 / 交易所 BTC 储备，历史从部署后持续积累。";
    } else {
      const rows = filteredDailySeries();
      const config = metricConfig[state.tab];
      hasData = rows.some((row) => row[state.tab] !== null && row[state.tab] !== undefined);
      chartData = {
        labels: rows.map((row) => row.date),
        datasets: [{ label: config.label, data: rows.map((row) => row[state.tab]), borderColor: config.color, backgroundColor: `${config.color}22`, borderWidth: 2, pointRadius: 0, pointHoverRadius: 3, fill: true, tension: .14 }],
      };
      options = chartOptions((value) => config.currency ? `$${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}` : Number(value).toFixed(config.decimals));
      $("#chartTitle").textContent = config.label;
      $("#chartSubtitle").textContent = state.tab === "wwi" ? "0 为理论熊市底部，1 为理论牛市顶部。" : "原始数值历史轨迹。";
    }

    empty.hidden = hasData;
    canvas.hidden = !hasData;
    if (hasData) {
      state.chart = new Chart(canvas, { type: "line", data: chartData, options });
    }
  }

  function selectTab(tab) {
    state.tab = tab;
    $$("[data-tab]").forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    renderChart();
  }

  function renderAll() {
    renderAssessment();
    renderMetrics();
    renderBottomComparison();
    renderChart();
    setFreshness("ready", relativeUpdateTime(state.data.metadata?.generatedAt));
  }

  function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(showToast.timeout);
    showToast.timeout = window.setTimeout(() => toast.classList.remove("visible"), 2800);
  }

  async function loadData(force = false) {
    const refreshButton = $("#refreshButton");
    refreshButton.classList.add("loading");
    setFreshness("", "正在同步");
    try {
      const response = await fetch(`data/metrics.json${force ? `?t=${Date.now()}` : ""}`, { cache: force ? "no-store" : "default" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.data = await response.json();
      renderAll();
      if (force) showToast("数据已刷新");
    } catch (error) {
      console.error(error);
      setFreshness("error", "数据读取失败");
      showToast("暂时无法读取数据，请稍后重试");
    } finally {
      refreshButton.classList.remove("loading");
    }
  }

  function bindEvents() {
    $("#themeButton").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    $("#refreshButton").addEventListener("click", () => loadData(true));
    $$("[data-range]").forEach((button) => button.addEventListener("click", () => {
      state.range = button.dataset.range === "all" ? "all" : Number(button.dataset.range);
      $$("[data-range]").forEach((item) => item.classList.toggle("active", item === button));
      renderChart();
    }));
    $$("[data-tab]").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab)));
    $$(".metric-card").forEach((card) => card.addEventListener("click", () => {
      selectTab(card.dataset.metric);
      $("#chartTitle").scrollIntoView({ behavior: "smooth", block: "center" });
    }));
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    bindEvents();
    if (window.lucide) window.lucide.createIcons();
    loadData();
  });
})();
