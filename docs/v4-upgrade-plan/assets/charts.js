(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  /* ---------- Mermaid ---------- */
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'neutral',
      securityLevel: 'loose',
      flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
      gantt: { useMaxWidth: true, fontSize: 12 }
    });
  }

  /* ---------- Chart: capability v3.3 vs v4.0 ---------- */
  var el = document.getElementById('chart-capability');
  if (el && window.echarts) {
    var chart = echarts.init(el, null, { renderer: 'svg' });

    var dims = ['入库灵活性', '代码感知', '库隔离', '可观测性', '反馈闭环', '引用溯源'];
    chart.setOption({
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, appendToBody: true },
      legend: {
        data: ['v3.3 基线', 'v4.0 预期'],
        top: 0,
        textStyle: { color: muted, fontSize: 12 }
      },
      grid: { left: 8, right: 24, top: 44, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        max: 100,
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { lineStyle: { color: rule } },
        axisLine: { show: false }
      },
      yAxis: {
        type: 'category',
        data: dims,
        axisLabel: { color: ink, fontSize: 12, fontWeight: 600 },
        axisTick: { show: false },
        axisLine: { lineStyle: { color: rule } }
      },
      series: [
        {
          name: 'v3.3 基线',
          type: 'bar',
          data: [20, 30, 15, 25, 5, 10],
          barWidth: 14,
          itemStyle: { color: muted, borderRadius: [0, 3, 3, 0] }
        },
        {
          name: 'v4.0 预期',
          type: 'bar',
          data: [95, 90, 88, 85, 80, 90],
          barWidth: 14,
          itemStyle: {
            color: accent,
            borderRadius: [0, 3, 3, 0]
          },
          label: {
            show: true,
            position: 'right',
            color: accent,
            fontSize: 11,
            fontWeight: 600,
            formatter: '{c}'
          }
        }
      ]
    });

    window.addEventListener('resize', function () { chart.resize(); });
  }
})();
