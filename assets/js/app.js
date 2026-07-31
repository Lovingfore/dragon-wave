(() => {
  "use strict";

  const metricConfig = {
    price: { label: "BTC 现货价格", color: "#e0ae54", decimals: 0, currency: true },
    nupl: { label: "NUPL", color: "#4fbe8a", decimals: 3 },
    realizedPrice: { label: "已实现价格", color: "#55bdc6", decimals: 0, currency: true },
    mvrv: { label: "MVRV", color: "#4d9de0", decimals: 2 },
    mvrvZ: { label: "MVRV Z-Score", color: "#ef6f51", decimals: 2 },
    wwi: { label: "狼波周期指数", color: "#e55c6d", decimals: 3 },
  };

  const waveColorStops = [
    [0, [38, 60, 219]],
    [0.25, [62, 196, 233]],
    [0.5, [72, 190, 80]],
    [0.7, [214, 223, 56]],
    [0.85, [246, 156, 28]],
    [1, [236, 38, 38]],
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
    { key: "wwi", label: "狼波周期指数" },
    { key: "riskScore", label: "综合风险分" },
  ];

  const state = {
    data: null,
    charts: new Map(),
    selectedMetrics: new Set(["price", "nupl", "mvrvZ", "wwi"]),
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
    if (score >= 70) return { label: "顶部风险升高", tone: "warning", detail: "估值或周期信号偏热，但尚未形成明确顶部共振。" };
    if (score <= 15) return { label: "接近熊市底部", tone: "positive", detail: "多项指标处于历史低分位，底部信号已进入高关注区。" };
    if (score <= 30) return { label: "底部区间观察", tone: "info", detail: "估值信号偏冷，正在靠近历史底部观察区。" };
    return { label: "周期中性区间", tone: "neutral", detail: "顶部与底部信号均未形成共振，市场仍处于周期中段。" };
  }

  function sourceLabel(sourceAge) {
    return { live: "尽量实时", daily: "日更", block: "区块实时" }[sourceAge] || "--";
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("lfcx-epoch-theme", theme);
    const icon = theme === "dark" ? "sun" : "moon";
    $("#themeButton").innerHTML = `<i data-lucide="${icon}"></i>`;
    if (window.lucide) window.lucide.createIcons();
    if (state.data) renderCharts();
  }

  function initTheme() {
    const saved = localStorage.getItem("lfcx-epoch-theme") || "dark";
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

  function median(values) {
    const sorted = values.filter(Number.isFinite).sort((left, right) => left - right);
    if (!sorted.length) return null;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function recencyWeightedMean(values) {
    const usable = values.filter(Number.isFinite);
    if (!usable.length) return null;
    const totalWeight = usable.reduce((sum, _, index) => sum + index + 1, 0);
    return usable.reduce((sum, value, index) => sum + value * (index + 1), 0) / totalWeight;
  }

  function expectedBottomForecast(bottoms) {
    const series = state.data.series || [];
    const isFiniteValue = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));
    const latestRow = [...series].reverse().find((row) => isFiniteValue(row.realizedPrice));
    const latestDate = latestRow?.date || state.data.metadata?.dailyDataDate;
    const latestBottomDate = bottoms[bottoms.length - 1]?.row?.date;
    const currentCycleRows = series.filter((row) => (!latestBottomDate || row.date >= latestBottomDate) && isFiniteValue(row.price));
    const currentTop = currentCycleRows.reduce((highest, row) => (!highest || Number(row.price) > Number(highest.price) ? row : highest), null);
    const forecastRows = currentTop ? series.filter((row) => row.date >= currentTop.date) : series;
    const currentBlockHeight = Number(state.data.cycle?.blockHeight || latestRow?.blockHeight);
    const phase = Number.isFinite(currentBlockHeight) ? (currentBlockHeight + 78750) % 210000 : null;
    const blocksToBottom = Number.isFinite(phase) ? (210000 - phase) % 210000 : 0;
    const recentBlockRows = series.filter((row) => Number(row.blocks) > 0 && latestDate && row.date >= latestDate.slice(0, 8) + "01");
    const averageBlocksPerDay = recentBlockRows.length
      ? recentBlockRows.reduce((sum, row) => sum + Number(row.blocks), 0) / recentBlockRows.length
      : 144;
    const daysToBottom = averageBlocksPerDay > 0 ? blocksToBottom / averageBlocksPerDay : 0;
    const target = latestDate ? new Date(`${latestDate}T00:00:00Z`) : null;
    if (target) target.setUTCDate(target.getUTCDate() + Math.round(daysToBottom));

    const historicalValue = (key) => bottoms.map((bottom) => Number(bottom.row?.[key])).filter((value, index) => isFiniteValue(bottoms[index].row?.[key]));
    const expectedMvrvBaseline = recencyWeightedMean(historicalValue("mvrv"));
    const expectedMvrvZ = recencyWeightedMean(historicalValue("mvrvZ"));
    const expectedWwi = recencyWeightedMean(historicalValue("wwi"));
    const currentCycleMvrv = forecastRows.filter((row) => isFiniteValue(row.mvrv)).map((row) => Number(row.mvrv));
    const expectedMvrv = currentCycleMvrv.length
      ? Math.min(expectedMvrvBaseline, Math.min(...currentCycleMvrv))
      : expectedMvrvBaseline;

    const realizedRows = series.filter((row) => isFiniteValue(row.realizedPrice));
    const trendStart = realizedRows[Math.max(0, realizedRows.length - 181)];
    const trendEnd = realizedRows[realizedRows.length - 1];
    const trendDays = trendStart && trendEnd ? Math.max(1, (new Date(trendEnd.date) - new Date(trendStart.date)) / 86400000) : 0;
    const trendRate = trendDays && Number(trendStart.realizedPrice) > 0 && Number(trendEnd.realizedPrice) > 0
      ? Math.max(-0.001, Math.min(0.001, Math.log(Number(trendEnd.realizedPrice) / Number(trendStart.realizedPrice)) / trendDays))
      : 0;
    const currentRealizedPrice = Number(state.data.current?.realizedPrice?.value || latestRow?.realizedPrice);
    const projectedDays = Math.min(540, Math.max(0, daysToBottom));
    const expectedRealizedPrice = Number.isFinite(currentRealizedPrice)
      ? currentRealizedPrice * Math.exp(trendRate * projectedDays)
      : null;
    const expectedPrice = Number.isFinite(expectedRealizedPrice) && Number.isFinite(expectedMvrv)
      ? expectedRealizedPrice * expectedMvrv
      : median(historicalValue("price"));
    const expectedNupl = Number.isFinite(expectedMvrv) && expectedMvrv > 0 ? 1 - 1 / expectedMvrv : null;
    const riskScorePart = (value, low, high) => Number.isFinite(value) ? Math.max(0, Math.min(100, (value - low) / (high - low) * 100)) : null;
    const riskParts = [
      [riskScorePart(expectedNupl, -0.15, 0.75), 0.18],
      [riskScorePart(expectedMvrv, 0.75, 3.75), 0.17],
      [riskScorePart(expectedMvrvZ, -0.5, 7.5), 0.22],
      [riskScorePart(expectedMvrv, 0.8, 3.2), 0.13],
      [riskScorePart(expectedWwi, 0, 1), 0.18],
    ].filter(([value]) => value !== null);
    const riskWeight = riskParts.reduce((sum, [, weight]) => sum + weight, 0);
    const expectedRiskScore = riskWeight ? Math.round(riskParts.reduce((sum, [value, weight]) => sum + value * weight, 0) / riskWeight * 10) / 10 : null;

    return {
      values: { price: expectedPrice, realizedPrice: expectedRealizedPrice, nupl: expectedNupl, mvrv: expectedMvrv, mvrvZ: expectedMvrvZ, wwi: expectedWwi, riskScore: expectedRiskScore },
      asOf: state.data.metadata?.dailyDataDate || latestDate,
      targetDate: target ? target.toISOString().slice(0, 10) : null,
    };
  }

  function renderBottomComparison() {
    const bottoms = findBearMarketBottoms();
    const forecast = expectedBottomForecast(bottoms);
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

    const expectedHeader = document.createElement("th");
    expectedHeader.scope = "col";
    expectedHeader.className = "bottom-expected";
    const expectedTitle = document.createElement("strong");
    expectedTitle.textContent = "本次熊市低点预期";
    const expectedDate = document.createElement("span");
    expectedDate.textContent = forecast.targetDate ? `动态估计 · ${forecast.targetDate}` : `动态估计 · ${forecast.asOf || "最新数据"}`;
    expectedHeader.append(expectedTitle, expectedDate);
    headerRow.appendChild(expectedHeader);

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
      appendComparisonCell(row, formatComparisonValue(metric.key, forecast.values[metric.key]), "bottom-expected");
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

  function metricSeriesForChart(key) {
    const rows = filteredDailySeries();
    if (state.range === "all" && ["mvrv", "mvrvZ"].includes(key)) {
      return rows.filter((row) => row.date >= "2011-01-01");
    }
    return rows;
  }

  function sampledChartRows(rows, maxPoints = 1800, valueKey) {
    if (rows.length <= maxPoints) return rows;
    const step = Math.ceil(rows.length / Math.floor(maxPoints / 2));
    const sampled = [];
    for (let index = 0; index < rows.length; index += step) {
      const bucket = rows.slice(index, index + step);
      const valueFor = (row) => row[valueKey];
      const usable = bucket.filter((row) => valueFor(row) !== null && valueFor(row) !== undefined);
      if (!usable.length) continue;
      const low = usable.reduce((best, row) => Number(valueFor(row)) < Number(valueFor(best)) ? row : best);
      const high = usable.reduce((best, row) => Number(valueFor(row)) > Number(valueFor(best)) ? row : best);
      sampled.push(...(low.date === high.date ? [low] : [low, high]));
    }
    const last = rows[rows.length - 1];
    if (sampled[sampled.length - 1]?.date !== last.date) sampled.push(last);
    return sampled.sort((left, right) => left.date.localeCompare(right.date));
  }

  function chartRowsForMetric(key) {
    const source = metricSeriesForChart(key);
    const sampled = sampledChartRows(source, 1800, key);
    const bottomDates = new Set(findBearMarketBottoms().map((bottom) => bottom.row?.date).filter(Boolean));
    const bottomRows = source.filter((row) => bottomDates.has(row.date));
    return [...new Map([...sampled, ...bottomRows].map((row) => [row.date, row])).values()]
      .sort((left, right) => left.date.localeCompare(right.date));
  }

  function waveColor(value) {
    const bounded = Math.max(0, Math.min(1, Number(value)));
    for (let index = 0; index < waveColorStops.length - 1; index += 1) {
      const [start, startColor] = waveColorStops[index];
      const [end, endColor] = waveColorStops[index + 1];
      if (bounded <= end) {
        const progress = (bounded - start) / (end - start);
        const color = startColor.map((channel, channelIndex) => Math.round(channel + progress * (endColor[channelIndex] - channel)));
        return `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
      }
    }
    return "rgb(236, 38, 38)";
  }

  function phaseWaveSegmentColor(context) {
    const start = Number(context.p0?.parsed?.y);
    const end = Number(context.p1?.parsed?.y);
    return waveColor(Number.isFinite(start) && Number.isFinite(end) ? (start + end) / 2 : start);
  }

  function priceWaveSegmentColor(context) {
    const start = Number(context.p0?.raw?.wwi);
    const end = Number(context.p1?.raw?.wwi);
    return waveColor(Number.isFinite(start) && Number.isFinite(end) ? (start + end) / 2 : start);
  }

  function chartColors() {
    const styles = getComputedStyle(document.documentElement);
    return {
      text: styles.getPropertyValue("--muted").trim(),
      grid: styles.getPropertyValue("--border").trim(),
      surface: styles.getPropertyValue("--surface").trim(),
    };
  }

  function formatXAxisLabel(label) {
    if (typeof label !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(label)) return label;
    if (state.range === "all") return label.slice(0, 4);
    if (Number(state.range) >= 365) return label.slice(0, 7);
    return label.slice(5);
  }

  function chartOptions(yFormat, min, max, scaleType = "linear", spanGaps = false, xAxis = {}) {
    const colors = chartColors();
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      animation: state.range === "all" ? false : { duration: 260 },
      normalized: true,
      spanGaps,
      plugins: {
        legend: {
          display: false,
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
            title: xAxis.tooltipTitle,
            label: (context) => xAxis.tooltipLabel ? xAxis.tooltipLabel(context) : `${context.dataset.label}: ${yFormat(context.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          display: xAxis.display !== false,
          type: xAxis.type || "category",
          min: Number.isFinite(xAxis.min) ? xAxis.min : undefined,
          max: Number.isFinite(xAxis.max) ? xAxis.max : undefined,
          grid: { display: Boolean(xAxis.showGrid), color: colors.grid },
          afterBuildTicks(scale) {
            if (xAxis.tickValues) scale.ticks = xAxis.tickValues.map((value) => ({ value }));
          },
          ticks: {
            color: colors.text,
            maxTicksLimit: xAxis.tickValues ? undefined : 7,
            maxRotation: 0,
            font: { size: 10 },
            callback(value) {
              if (xAxis.formatTick) return xAxis.formatTick(value);
              return formatXAxisLabel(this.getLabelForValue(value));
            },
          },
          border: { color: colors.grid },
        },
        y: {
          type: scaleType,
          min,
          max,
          afterFit: xAxis.fixedYAxis ? (scale) => { scale.width = xAxis.fixedYAxis; } : undefined,
          grid: { color: colors.grid, drawTicks: false },
          ticks: { color: colors.text, padding: 10, maxTicksLimit: 6, font: { size: 10 }, callback: yFormat },
          border: { display: false },
        },
      },
    };
  }

  function formatChartCurrency(value) {
    const number = Number(value);
    const digits = Math.abs(number) < 0.01 ? 4 : Math.abs(number) < 1 ? 2 : Math.abs(number) < 100 ? 2 : 0;
    return `$${number.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  }

  function metricChartBounds(key, rows) {
    const values = rows.map((row) => Number(row[key])).filter(Number.isFinite);
    if (!values.length) return {};
    const lowest = Math.min(...values);
    const highest = Math.max(...values);
    if (key === "wwi") {
      const span = highest - lowest;
      if (state.range === "all" || span >= 0.6) return { min: 0, max: 1, detailed: false };
      const padding = Math.max(0.01, span * 0.12);
      return {
        min: Math.max(0, Math.floor((lowest - padding) * 100) / 100),
        max: Math.min(1, Math.ceil((highest + padding) * 100) / 100),
        detailed: true,
      };
    }
    if (key === "mvrv") return { min: 0, max: Math.ceil(highest) };
    if (key === "mvrvZ") return { min: Math.floor(Math.min(-1, lowest) * 2) / 2, max: Math.ceil(highest) };
    if (key === "nupl") return {
      min: Math.floor(Math.min(-0.5, lowest) * 10) / 10,
      max: Math.ceil(Math.max(0.8, highest) * 10) / 10,
    };
    return {};
  }

  function bottomReference(key) {
    const samples = findBearMarketBottoms().map((bottom) => ({
      cycle: bottom.cycle,
      date: bottom.row?.date,
      blockHeight: Number(bottom.row?.blockHeight),
      value: Number(bottom.row?.[key]),
    })).filter((sample) => sample.date && Number.isFinite(sample.value));
    const sorted = samples.map((sample) => sample.value).sort((left, right) => left - right);
    const middle = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    return {
      samples,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      median,
      current: Number(state.data.current?.[key]?.value),
    };
  }

  function formatBottomRange(key, reference) {
    if (!Number.isFinite(reference.min) || !Number.isFinite(reference.max)) return "暂无样本";
    return `${formatMetric(key, reference.min)} 至 ${formatMetric(key, reference.max)}`;
  }

  function bottomDistance(key, reference) {
    const { current, min, max } = reference;
    if (![current, min, max].every(Number.isFinite)) return { text: "暂不可用", inside: false };
    if (current >= min && current <= max) return { text: "已进入参考区间", inside: true };
    const above = current > max;
    const edge = above ? max : min;
    const gap = Math.abs(current - edge);
    const config = metricConfig[key];
    const formattedGap = config.currency ? formatChartCurrency(gap) : gap.toFixed(config.decimals);
    const percentage = config.currency && edge !== 0 ? ` · ${(gap / Math.abs(edge) * 100).toFixed(0)}%` : "";
    return { text: `${above ? "高于上沿" : "低于下沿"} ${formattedGap}${percentage}`, inside: false };
  }

  function bottomReferencePlugin(key, reference) {
    const config = metricConfig[key];
    const drawLabel = (ctx, text, x, y, align = "right") => {
      ctx.font = "600 10px system-ui, sans-serif";
      ctx.textAlign = align;
      ctx.textBaseline = "bottom";
      ctx.fillStyle = chartColors().text;
      ctx.fillText(text, x, y);
    };
    return {
      id: `bottomReference-${key}`,
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        const yScale = scales.y;
        if (!chartArea || !yScale || !Number.isFinite(reference.min) || !Number.isFinite(reference.max)) return;
        const visibleMin = Number(yScale.min);
        const visibleMax = Number(yScale.max);
        const intersects = reference.max >= visibleMin && reference.min <= visibleMax;
        ctx.save();
        if (intersects) {
          const top = yScale.getPixelForValue(Math.min(reference.max, visibleMax));
          const bottom = yScale.getPixelForValue(Math.max(reference.min, visibleMin));
          ctx.fillStyle = `${config.color}16`;
          ctx.fillRect(chartArea.left, Math.min(top, bottom), chartArea.width, Math.abs(bottom - top));
          if (reference.median >= visibleMin && reference.median <= visibleMax) {
            const medianY = yScale.getPixelForValue(reference.median);
            ctx.strokeStyle = `${config.color}a8`;
            ctx.lineWidth = 1;
            ctx.setLineDash([5, 4]);
            ctx.beginPath();
            ctx.moveTo(chartArea.left, medianY);
            ctx.lineTo(chartArea.right, medianY);
            ctx.stroke();
          }
          drawLabel(ctx, "历史底部参考", chartArea.right - 5, Math.max(chartArea.top + 13, Math.min(top, bottom) + 13));
        } else {
          const below = reference.max < visibleMin;
          const edgeY = below ? chartArea.bottom - 1 : chartArea.top + 11;
          ctx.strokeStyle = `${config.color}a8`;
          ctx.lineWidth = 1;
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.moveTo(chartArea.left, below ? chartArea.bottom - 1 : chartArea.top + 1);
          ctx.lineTo(chartArea.right, below ? chartArea.bottom - 1 : chartArea.top + 1);
          ctx.stroke();
          drawLabel(ctx, `${below ? "↓" : "↑"} 历史底部区间`, chartArea.right - 5, edgeY);
        }
        ctx.restore();
      },
      afterDatasetsDraw(chart) {
        const { ctx, chartArea, scales, data } = chart;
        if (!chartArea || !scales.x || !scales.y) return;
        ctx.save();
        reference.samples.forEach((sample) => {
          const usesBlockAxis = scales.x.type === "linear";
          const xValue = usesBlockAxis ? sample.blockHeight : data.labels.indexOf(sample.date);
          if (!Number.isFinite(xValue) || xValue < scales.x.min || xValue > scales.x.max || sample.value < scales.y.min || sample.value > scales.y.max) return;
          const x = scales.x.getPixelForValue(xValue);
          const y = scales.y.getPixelForValue(sample.value);
          ctx.fillStyle = config.color;
          ctx.beginPath();
          ctx.arc(x, y, 3.5, 0, Math.PI * 2);
          ctx.fill();
          drawLabel(ctx, sample.cycle, x + 5, y - 4, "left");
        });
        ctx.restore();
      },
    };
  }

  function nearestRowForHeight(rows, height) {
    if (!rows.length) return null;
    let low = 0;
    let high = rows.length - 1;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (Number(rows[middle].blockHeight) < height) low = middle + 1;
      else high = middle;
    }
    const current = rows[low];
    const previous = rows[Math.max(0, low - 1)];
    return Math.abs(Number(previous.blockHeight) - height) <= Math.abs(Number(current.blockHeight) - height) ? previous : current;
  }

  function wwiTurningRows(rows) {
    if (!rows.length) return [];
    const min = Number(rows[0].blockHeight);
    const max = Number(rows[rows.length - 1].blockHeight);
    const targets = [];
    for (let cycle = -1; cycle <= Math.ceil(max / 210000) + 1; cycle += 1) {
      const risingStart = cycle * 210000 - 78750;
      const peak = cycle * 210000 + 78750;
      const halving = cycle * 210000;
      [risingStart, halving, peak].forEach((height) => {
        if (height >= min && height <= max) targets.push(height);
      });
    }
    return targets.map((height) => nearestRowForHeight(rows, height)).filter(Boolean);
  }

  function sampledWavePriceRows(rows) {
    const sampled = sampledChartRows(rows, 2600, "price");
    const bottomDates = new Set(findBearMarketBottoms().map((bottom) => bottom.row?.date).filter(Boolean));
    const anchors = rows.filter((row) => bottomDates.has(row.date));
    return [...new Map([...sampled, ...anchors, ...wwiTurningRows(rows)].map((row) => [row.blockHeight, row])).values()]
      .sort((left, right) => Number(left.blockHeight) - Number(right.blockHeight));
  }

  function sampledWaveIndexRows(rows, maxPoints = 1800) {
    if (rows.length <= maxPoints) return rows;
    const step = Math.ceil(rows.length / maxPoints);
    const sampled = rows.filter((_, index) => index % step === 0);
    sampled.push(rows[rows.length - 1], ...wwiTurningRows(rows));
    return [...new Map(sampled.map((row) => [row.blockHeight, row])).values()]
      .sort((left, right) => Number(left.blockHeight) - Number(right.blockHeight));
  }

  function blockAxisStep(min, max) {
    const span = Math.max(1, max - min);
    const rough = span / 6;
    const steps = [1000, 2000, 5000, 10000, 20000, 50000, 100000, 210000, 420000];
    return steps.find((step) => step >= rough) || 840000;
  }

  function blockAxisOptions(rows, display = true) {
    const min = Number(rows[0]?.blockHeight);
    const max = Number(rows[rows.length - 1]?.blockHeight);
    const step = blockAxisStep(min, max);
    const ticks = [];
    for (let height = Math.ceil(min / step) * step; height <= max; height += step) ticks.push(height);
    return {
      type: "linear",
      min,
      max,
      display,
      tickValues: ticks,
      fixedYAxis: 72,
      formatTick: (height) => Number(height) >= 1000 ? `${Math.round(Number(height) / 1000)}k` : Math.round(Number(height)),
      tooltipTitle(items) {
        const point = items[0]?.raw;
        return point?.date ? `${point.date} · 区块 #${Number(point.x).toLocaleString("en-US")}` : "";
      },
    };
  }

  function wwiCycleGuidePlugin(showLabels = false) {
    const palette = document.documentElement.dataset.theme === "light"
      ? { bull: "rgba(79, 190, 138, .08)", bear: "rgba(229, 92, 109, .07)", line: "rgba(77, 157, 224, .5)", label: "#4d9de0" }
      : { bull: "rgba(79, 190, 138, .07)", bear: "rgba(229, 92, 109, .065)", line: "rgba(77, 157, 224, .46)", label: "#79b8ec" };
    return {
      id: `wwiCycleGuide-${showLabels ? "price" : "index"}`,
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea, scales } = chart;
        if (!chartArea || !scales.x) return;
        const min = Number(scales.x.min);
        const max = Number(scales.x.max);
        ctx.save();
        ctx.beginPath();
        ctx.rect(chartArea.left, chartArea.top, chartArea.width, chartArea.height);
        ctx.clip();
        const firstCycle = Math.floor((min + 78750) / 210000) - 1;
        const lastCycle = Math.ceil((max + 78750) / 210000) + 1;
        for (let cycle = firstCycle; cycle <= lastCycle; cycle += 1) {
          const risingStart = cycle * 210000 - 78750;
          const peak = risingStart + 157500;
          const cycleEnd = risingStart + 210000;
          [[risingStart, peak, palette.bull], [peak, cycleEnd, palette.bear]].forEach(([from, to, color]) => {
            const left = scales.x.getPixelForValue(Math.max(min, from));
            const right = scales.x.getPixelForValue(Math.min(max, to));
            if (right > left) {
              ctx.fillStyle = color;
              ctx.fillRect(left, chartArea.top, right - left, chartArea.height);
            }
          });
        }
        ctx.strokeStyle = palette.line;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        for (let height = Math.max(210000, Math.ceil(min / 210000) * 210000); height <= max; height += 210000) {
          const x = scales.x.getPixelForValue(height);
          ctx.beginPath();
          ctx.moveTo(x, chartArea.top);
          ctx.lineTo(x, chartArea.bottom);
          ctx.stroke();
        }
        ctx.restore();
      },
      afterDatasetsDraw(chart) {
        if (!showLabels) return;
        const { ctx, chartArea, scales } = chart;
        if (!chartArea || !scales.x) return;
        ctx.save();
        ctx.font = "600 9px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = palette.label;
        for (let height = Math.max(210000, Math.ceil(scales.x.min / 210000) * 210000); height <= scales.x.max; height += 210000) {
          const x = scales.x.getPixelForValue(height);
          ctx.fillText(`第 ${height / 210000} 次减半`, x, chartArea.top + 5);
        }
        ctx.restore();
      },
    };
  }

  function appendChartStat(parent, label, value, className = "") {
    const item = document.createElement("div");
    item.className = `metric-chart-stat ${className}`.trim();
    const term = document.createElement("span");
    term.textContent = label;
    const detail = document.createElement("strong");
    detail.textContent = value;
    item.append(term, detail);
    parent.appendChild(item);
  }

  function buildMetricChartHeader(key, reference) {
    const config = metricConfig[key];
    const distance = bottomDistance(key, reference);
    const header = document.createElement("header");
    header.className = "metric-chart-header";
    const title = document.createElement("div");
    title.className = "metric-chart-title";
    const heading = document.createElement("h3");
    heading.textContent = config.label;
    title.appendChild(heading);
    const stats = document.createElement("div");
    stats.className = "metric-chart-stats";
    appendChartStat(stats, "当前", formatMetric(key, reference.current));
    appendChartStat(stats, "底部参考", formatBottomRange(key, reference));
    appendChartStat(stats, "中位", Number.isFinite(reference.median) ? formatMetric(key, reference.median) : "暂无样本");
    appendChartStat(stats, "距离", distance.text, `distance${distance.inside ? " inside" : ""}`);
    header.append(title, stats);
    return header;
  }

  function buildBottomSamples(key, reference) {
    const sampleList = document.createElement("div");
    sampleList.className = "bottom-samples";
    reference.samples.forEach((sample) => {
      const item = document.createElement("span");
      const cycle = document.createElement("strong");
      cycle.textContent = sample.cycle;
      item.append(cycle, ` · ${formatMetric(key, sample.value)}`);
      sampleList.appendChild(item);
    });
    return sampleList;
  }

  function buildWwiPane(label, className, ariaLabel) {
    const pane = document.createElement("div");
    pane.className = `wwi-pane ${className}`;
    const paneHeader = document.createElement("div");
    paneHeader.className = "wwi-pane-label";
    paneHeader.textContent = label;
    const chartBody = document.createElement("div");
    chartBody.className = "metric-chart-canvas";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-label", ariaLabel);
    chartBody.appendChild(canvas);
    pane.append(paneHeader, chartBody);
    return { pane, canvas, chartBody };
  }

  function renderWwiChart(container) {
    const key = "wwi";
    const config = metricConfig[key];
    const reference = bottomReference(key);
    const sourceRows = filteredDailySeries()
      .filter((row) => Number.isFinite(Number(row.blockHeight)) && Number.isFinite(Number(row.wwi)))
      .sort((left, right) => Number(left.blockHeight) - Number(right.blockHeight));
    const priceSourceRows = sourceRows.filter((row) => Number.isFinite(Number(row.price)) && Number(row.price) > 0);

    const panel = document.createElement("article");
    panel.className = "metric-chart metric-chart-wwi";
    panel.style.setProperty("--metric-color", config.color);
    const header = buildMetricChartHeader(key, reference);
    const stack = document.createElement("div");
    stack.className = "wwi-chart-stack";
    const pricePane = buildWwiPane("BTC / USD", "wwi-price-pane", "按狼波周期着色的 BTC 对数价格走势");
    const indexPane = buildWwiPane("WOLFY WAVE INDEX · 0–1", "wwi-index-pane", "狼波周期指数走势与历史底部参考");
    stack.append(pricePane.pane, indexPane.pane);
    panel.append(header, stack, buildBottomSamples(key, reference));
    container.appendChild(panel);

    if (!sourceRows.length || !priceSourceRows.length) {
      stack.textContent = "狼波周期数据正在积累";
      return;
    }

    const priceRows = sampledWavePriceRows(priceSourceRows);
    const indexRows = sampledWaveIndexRows(sourceRows);
    const axisRows = [sourceRows[0], sourceRows[sourceRows.length - 1]];
    const priceAxis = blockAxisOptions(axisRows, false);
    const indexAxis = blockAxisOptions(axisRows, true);
    const priceOptions = chartOptions(formatChartCurrency, undefined, undefined, "logarithmic", false, priceAxis);
    priceOptions.layout = { padding: { top: 14 } };
    const indexOptions = chartOptions((value) => Number(value).toFixed(2), 0, 1, "linear", false, indexAxis);
    indexOptions.layout = { padding: { top: 6 } };

    const priceDataset = {
      label: "BTC / USD",
      data: priceRows.map((row) => ({ x: Number(row.blockHeight), y: Number(row.price), wwi: Number(row.wwi), date: row.date })),
      borderColor: config.color,
      backgroundColor: "transparent",
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: false,
      spanGaps: false,
      tension: 0,
      parsing: false,
      segment: { borderColor: priceWaveSegmentColor },
    };
    const indexDataset = {
      label: config.label,
      data: indexRows.map((row) => ({ x: Number(row.blockHeight), y: Number(row.wwi), date: row.date })),
      borderColor: config.color,
      backgroundColor: "transparent",
      borderWidth: 1.8,
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: false,
      spanGaps: false,
      tension: 0,
      parsing: false,
      segment: { borderColor: phaseWaveSegmentColor },
    };
    state.charts.set("wwi-price", new Chart(pricePane.canvas, {
      type: "line",
      data: { datasets: [priceDataset] },
      options: priceOptions,
      plugins: [wwiCycleGuidePlugin(true)],
    }));
    state.charts.set("wwi", new Chart(indexPane.canvas, {
      type: "line",
      data: { datasets: [indexDataset] },
      options: indexOptions,
      plugins: [wwiCycleGuidePlugin(false), bottomReferencePlugin(key, reference)],
    }));
  }

  function renderMetricChart(key, container) {
    const config = metricConfig[key];
    const reference = bottomReference(key);
    const rows = chartRowsForMetric(key);
    const hasData = rows.some((row) => Number.isFinite(Number(row[key])));

    const panel = document.createElement("article");
    panel.className = "metric-chart";
    panel.style.setProperty("--metric-color", config.color);
    const header = buildMetricChartHeader(key, reference);

    const chartBody = document.createElement("div");
    chartBody.className = "metric-chart-canvas";
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-label", `${config.label}历史走势与底部参考`);
    chartBody.appendChild(canvas);

    const sampleList = buildBottomSamples(key, reference);
    panel.append(header, chartBody, sampleList);
    container.appendChild(panel);

    if (!hasData) {
      chartBody.textContent = "该指标正在积累历史数据";
      return;
    }

    const logarithmic = state.range === "all" && ["price", "realizedPrice"].includes(key);
    const bounds = metricChartBounds(key, rows);
    const options = chartOptions(
      (value) => config.currency ? formatChartCurrency(value) : Number(value).toFixed(config.decimals),
      bounds.min,
      bounds.max,
      logarithmic ? "logarithmic" : "linear",
      false,
      {},
    );
    options.layout = { padding: { top: 12 } };
    const dataset = {
      label: config.label,
      data: rows.map((row) => row[key] ?? null),
      borderColor: config.color,
      backgroundColor: `${config.color}22`,
      borderWidth: key === "wwi" ? 2.2 : 2,
      pointRadius: 0,
      pointHoverRadius: 3,
      fill: false,
      spanGaps: false,
      tension: 0,
    };
    state.charts.set(key, new Chart(canvas, {
      type: "line",
      data: { labels: rows.map((row) => row.date), datasets: [dataset] },
      options,
      plugins: [bottomReferencePlugin(key, reference)],
    }));
  }

  function syncMetricControls() {
    $$("[data-metric-toggle]").forEach((input) => {
      input.checked = state.selectedMetrics.has(input.dataset.metricToggle);
    });
  }

  function persistMetricSelection() {
    localStorage.setItem("lfcx-epoch-chart-metrics", JSON.stringify([...state.selectedMetrics]));
  }

  function setMetricSelection(keys) {
    state.selectedMetrics = new Set(keys.filter((key) => metricConfig[key]));
    syncMetricControls();
    persistMetricSelection();
    renderCharts();
  }

  function initMetricSelection() {
    try {
      const saved = JSON.parse(localStorage.getItem("lfcx-epoch-chart-metrics"));
      if (Array.isArray(saved)) state.selectedMetrics = new Set(saved.filter((key) => metricConfig[key]));
    } catch (_) {
      localStorage.removeItem("lfcx-epoch-chart-metrics");
    }
    syncMetricControls();
  }

  function renderCharts() {
    if (!state.data || !window.Chart) return;
    state.charts.forEach((chart) => chart.destroy());
    state.charts.clear();
    const grid = $("#chartGrid");
    const empty = $("#chartEmpty");
    grid.replaceChildren();
    const selected = Object.keys(metricConfig).filter((key) => state.selectedMetrics.has(key));
    $("#chartTitle").textContent = "指标历史走势";
    $("#chartSubtitle").textContent = selected.length ? `已选择 ${selected.length} 项 · 底部参考取四轮周期低点` : "底部参考取四轮周期低点";
    empty.hidden = selected.length > 0;
    if (!selected.length) {
      $("#chartEmptyText").textContent = "请选择指标";
      return;
    }
    selected.forEach((key) => key === "wwi" ? renderWwiChart(grid) : renderMetricChart(key, grid));
  }

  function renderAll() {
    renderAssessment();
    renderMetrics();
    renderBottomComparison();
    renderCharts();
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
      const response = await fetch(`data/metrics.json?t=${Date.now()}`, { cache: "no-store" });
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
      renderCharts();
    }));
    $$("[data-metric-toggle]").forEach((input) => input.addEventListener("change", () => {
      const selected = new Set(state.selectedMetrics);
      if (input.checked) selected.add(input.dataset.metricToggle);
      else selected.delete(input.dataset.metricToggle);
      setMetricSelection([...selected]);
    }));
    $("#selectAllMetrics").addEventListener("click", () => setMetricSelection(Object.keys(metricConfig)));
    $("#clearMetrics").addEventListener("click", () => setMetricSelection([]));
    $$(".metric-card").forEach((card) => card.addEventListener("click", () => {
      setMetricSelection([card.dataset.metric]);
      $("#chartTitle").scrollIntoView({ behavior: "smooth", block: "center" });
    }));
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initMetricSelection();
    bindEvents();
    if (window.lucide) window.lucide.createIcons();
    loadData();
  });
})();
