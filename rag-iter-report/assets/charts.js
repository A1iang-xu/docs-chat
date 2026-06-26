// DocsChat RAG 全链路技术迭代报告 — 图表脚本
(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  var palette = [accent, accent2, '#7A8B7C', '#C98B6B', '#9C8AA5', '#6B8CAE'];
  var tooltipStyle = {
    backgroundColor: '#FFFFFF',
    borderColor: rule,
    borderWidth: 1,
    textStyle: { color: ink, fontSize: 12 },
    extraCssText: 'box-shadow: 0 4px 12px rgba(0,0,0,0.08);'
  };

  // ── 图1: 版本演进柱状图（每版本升级数） ──
  var chart1 = echarts.init(document.getElementById('chart-versions'), null, { renderer: 'svg' });
  chart1.setOption({
    color: [accent],
    grid: { top: 40, right: 30, bottom: 40, left: 60 },
    tooltip: Object.assign({
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      formatter: function(p) {
        return p[0].name + '<br/><b>' + p[0].value + '</b> 项升级';
      }
    }, tooltipStyle),
    xAxis: {
      type: 'category',
      data: ['v3.0', 'v3.1', 'v3.2', 'v3.3'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 13, fontWeight: 600 }
    },
    yAxis: {
      type: 'value',
      name: '升级项数',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 0, name: 'v3.0', itemStyle: { color: muted, opacity: 0.4 }, label: { show: true, position: 'top', formatter: '基线', color: muted, fontSize: 11 } },
        { value: 6, name: 'v3.1', itemStyle: { color: accent }, label: { show: true, position: 'top', color: ink, fontWeight: 600 } },
        { value: 8, name: 'v3.2', itemStyle: { color: accent2 }, label: { show: true, position: 'top', color: ink, fontWeight: 600 } },
        { value: 8, name: 'v3.3', itemStyle: { color: '#7A8B7C' }, label: { show: true, position: 'top', color: ink, fontWeight: 600 } }
      ],
      barWidth: '50%',
      label: { show: true, position: 'top', color: ink, fontWeight: 600, fontSize: 13 }
    }]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // ── 图2: 各阶段覆盖升级项分布（堆叠柱） ──
  var chart2 = echarts.init(document.getElementById('chart-stage-coverage'), null, { renderer: 'svg' });
  chart2.setOption({
    color: palette,
    grid: { top: 50, right: 30, bottom: 60, left: 60 },
    tooltip: Object.assign({
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true
    }, tooltipStyle),
    legend: {
      data: ['v3.1', 'v3.2', 'v3.3'],
      bottom: 10,
      textStyle: { color: muted, fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: ['文档解析', '查询理解', '混合检索', 'CRAG质量评估', '上下文组装', '生成与后处理', '缓存与可观测'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12, interval: 0, rotate: 0 }
    },
    yAxis: {
      type: 'value',
      name: '升级项数',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted }
    },
    series: [
      { name: 'v3.1', type: 'bar', stack: 'total', data: [1, 1, 1, 1, 0, 1, 1], barWidth: '55%' },
      { name: 'v3.2', type: 'bar', stack: 'total', data: [2, 1, 2, 1, 1, 1, 0] },
      { name: 'v3.3', type: 'bar', stack: 'total', data: [1, 1, 1, 1, 2, 1, 1] }
    ]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // ── 图3: 关键指标对比（中文检索召回率） ──
  var chart3 = echarts.init(document.getElementById('chart-recall'), null, { renderer: 'svg' });
  chart3.setOption({
    color: [accent, accent2],
    grid: { top: 40, right: 30, bottom: 50, left: 60 },
    tooltip: Object.assign({
      trigger: 'axis',
      appendToBody: true
    }, tooltipStyle),
    legend: {
      data: ['向量检索', 'BM25关键词'],
      top: 0,
      textStyle: { color: muted, fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: ['v3.0 基线\n英文 MiniLM\n正则逐字切分', 'v3.1\nBGE-M3\n正则逐字切分', 'v3.2\nm3e-base\njieba词级切分', 'v3.3\nm3e-base\n+ 邻居扩展'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11, interval: 0, lineHeight: 14 }
    },
    yAxis: {
      type: 'value',
      name: '相对召回率提升',
      max: 80,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, formatter: '{value}%' }
    },
    series: [
      {
        name: '向量检索',
        type: 'bar',
        data: [0, 30, 60, 75],
        barWidth: '30%',
        itemStyle: { color: accent },
        label: { show: true, position: 'top', color: ink, fontSize: 11, formatter: '+{c}%' }
      },
      {
        name: 'BM25关键词',
        type: 'bar',
        data: [0, 0, 35, 35],
        barWidth: '30%',
        itemStyle: { color: accent2 },
        label: { show: true, position: 'top', color: ink, fontSize: 11, formatter: '+{c}%' }
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });

  // ── 图4: 延迟与Token优化效果 ──
  var chart4 = echarts.init(document.getElementById('chart-latency'), null, { renderer: 'svg' });
  chart4.setOption({
    color: [accent, accent2, '#7A8B7C'],
    grid: { top: 40, right: 30, bottom: 40, left: 60 },
    tooltip: Object.assign({
      trigger: 'axis',
      appendToBody: true
    }, tooltipStyle),
    legend: {
      data: ['v3.0/v3.1 基线', 'v3.2 优化后', 'v3.3 精细化后'],
      top: 0,
      textStyle: { color: muted, fontSize: 12 }
    },
    xAxis: {
      type: 'category',
      data: ['忠实度验证延迟\n(ms)', '忠实度Token消耗\n(次/对话)', '语义缓存TTFT\n(s)', '简单查询LLM\n调用次数'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11, interval: 0, lineHeight: 14 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted }
    },
    series: [
      {
        name: 'v3.0/v3.1 基线',
        type: 'bar',
        data: [2500, 6, 3.0, 5],
        barWidth: '22%',
        itemStyle: { color: accent },
        label: { show: true, position: 'top', color: ink, fontSize: 10 }
      },
      {
        name: 'v3.2 优化后',
        type: 'bar',
        data: [1800, 6, 0.05, 5],
        barWidth: '22%',
        itemStyle: { color: accent2 },
        label: { show: true, position: 'top', color: ink, fontSize: 10 }
      },
      {
        name: 'v3.3 精细化后',
        type: 'bar',
        data: [500, 2, 0.05, 2],
        barWidth: '22%',
        itemStyle: { color: '#7A8B7C' },
        label: { show: true, position: 'top', color: ink, fontSize: 10 }
      }
    ]
  });
  window.addEventListener('resize', function() { chart4.resize(); });

  // ── 图5: 关键技术栈演进时间线 ──
  var chart5 = echarts.init(document.getElementById('chart-timeline'), null, { renderer: 'svg' });
  chart5.setOption({
    tooltip: Object.assign({ appendToBody: true, formatter: function(p) { return p.name; } }, tooltipStyle),
    grid: { top: 30, right: 60, bottom: 30, left: 60 },
    xAxis: {
      type: 'category',
      data: ['v3.0 基线', 'v3.1 外部服务', 'v3.2 检索质量', 'v3.3 精细化'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12, fontWeight: 600 }
    },
    yAxis: {
      type: 'category',
      data: ['文档解析', 'Embedding', 'BM25分词', 'Chunk策略', '查询理解', '精排', 'CRAG', '后处理', '缓存', '工程化'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 11, fontWeight: 500 },
      inverse: true
    },
    series: [{
      type: 'scatter',
      symbolSize: 24,
      data: [
        // v3.0
        { name: 'PyPDF', value: [0, 0], itemStyle: { color: '#C98B6B' } },
        { name: 'MiniLM 384d', value: [0, 1], itemStyle: { color: '#C98B6B' } },
        { name: '正则逐字', value: [0, 2], itemStyle: { color: '#C98B6B' } },
        { name: '固定512盲切', value: [0, 3], itemStyle: { color: '#C98B6B' } },
        { name: '无改写', value: [0, 4], itemStyle: { color: '#C98B6B' } },
        { name: 'BGE-Reranker', value: [0, 5], itemStyle: { color: '#C98B6B' } },
        { name: '无', value: [0, 6], itemStyle: { color: '#C98B6B' } },
        { name: '无', value: [0, 7], itemStyle: { color: '#C98B6B' } },
        { name: '无', value: [0, 8], itemStyle: { color: '#C98B6B' } },
        { name: '同步阻塞', value: [0, 9], itemStyle: { color: '#C98B6B' } },
        // v3.1
        { name: 'MinerU 3通道', value: [1, 0], itemStyle: { color: accent } },
        { name: 'BGE-M3 1024d', value: [1, 1], itemStyle: { color: accent } },
        { name: '正则逐字', value: [1, 2], itemStyle: { color: muted } },
        { name: 'H1/H2/H3', value: [1, 3], itemStyle: { color: accent } },
        { name: 'Fusion 3路', value: [1, 4], itemStyle: { color: accent } },
        { name: 'Qwen3-0.6B', value: [1, 5], itemStyle: { color: accent } },
        { name: '基础评估', value: [1, 6], itemStyle: { color: accent } },
        { name: '无', value: [1, 7], itemStyle: { color: muted } },
        { name: '字符串', value: [1, 8], itemStyle: { color: accent } },
        { name: '异步+SSE', value: [1, 9], itemStyle: { color: accent } },
        // v3.2
        { name: '语义后置合并', value: [2, 0], itemStyle: { color: accent2 } },
        { name: 'm3e-base 768d', value: [2, 1], itemStyle: { color: accent2 } },
        { name: 'jieba 词级', value: [2, 2], itemStyle: { color: accent2 } },
        { name: '邻居扩展', value: [2, 3], itemStyle: { color: accent2 } },
        { name: 'HyDE', value: [2, 4], itemStyle: { color: accent2 } },
        { name: 'Qwen3-0.6B', value: [2, 5], itemStyle: { color: accent } },
        { name: '动态重写', value: [2, 6], itemStyle: { color: accent2 } },
        { name: '逐句验证', value: [2, 7], itemStyle: { color: accent2 } },
        { name: '向量相似度', value: [2, 8], itemStyle: { color: accent2 } },
        { name: '限流/降级', value: [2, 9], itemStyle: { color: accent } },
        // v3.3
        { name: '前置切分', value: [3, 0], itemStyle: { color: '#7A8B7C' } },
        { name: 'm3e-base', value: [3, 1], itemStyle: { color: accent2 } },
        { name: 'jieba+停用', value: [3, 2], itemStyle: { color: accent2 } },
        { name: '落地+去重', value: [3, 3], itemStyle: { color: '#7A8B7C' } },
        { name: '查询路由', value: [3, 4], itemStyle: { color: '#7A8B7C' } },
        { name: 'Reranker 精排', value: [3, 5], itemStyle: { color: accent } },
        { name: '事实跳过', value: [3, 6], itemStyle: { color: '#7A8B7C' } },
        { name: '批量+闭环', value: [3, 7], itemStyle: { color: '#7A8B7C' } },
        { name: 'FAISS预热', value: [3, 8], itemStyle: { color: '#7A8B7C' } },
        { name: 'LLM降级+预算', value: [3, 9], itemStyle: { color: '#7A8B7C' } }
      ],
      label: {
        show: true,
        formatter: function(p) { return p.name; },
        color: '#FFFFFF',
        fontSize: 10,
        fontWeight: 600
      }
    }]
  });
  window.addEventListener('resize', function() { chart5.resize(); });
})();
