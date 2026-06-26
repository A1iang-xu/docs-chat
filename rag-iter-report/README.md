# DocsChat RAG 全链路技术迭代报告

一份独立的HTML报告,基于 docs-chat 项目四个版本(v3.0 → v3.3)的实际开发流程,梳理 RAG 全链路 9 个阶段(数据预处理、索引构建、查询理解、混合检索、CRAG 评估、上下文组装、生成与后处理、缓存、可观测)的技术迭代过程。

## 文件结构

```
rag-iter-report/
├── rag-iter-report.html    ← 主报告(双击即可在浏览器打开)
├── assets/
│   └── charts.js           ← ECharts 图表脚本
└── _shared/
    ├── js/
    │   ├── echarts.min.js  ← 图表库
    │   └── mermaid.min.js  ← 流程图库
    └── fonts/              ← 字体目录
```

## 报告核心内容

- 12 个章节,覆盖文档解析、Embedding、Chunk 策略、查询理解、混合检索、CRAG、上下文组装、生成与后处理、缓存、可观测
- 5 个 ECharts 图表(版本演进柱状图、阶段覆盖堆叠柱、召回率提升、延迟优化、技术栈演进时间线)
- 1 个 Mermaid 流程图(RAG 全链路数据流)
- 50+ 个具体升级项,每项标注原方法/改进后方法/原因/成果

## 使用方法

1. 双击 `rag-iter-report.html` 在默认浏览器打开
2. 顶部粘性 TOC 可快速跳转到任一阶段
3. 报告完全自包含,无需任何外部依赖(无需网络)
4. 推荐使用 Chrome / Edge / Firefox 现代浏览器

## 报告基于的资料

- 用户上传的 RAG 学习笔记(DOCX)
- docs-chat 项目四个版本的升级方案 (v3.0 / v3.1 / v3.2 / v3.3)
- 实际服务层代码(rag_orchestrator.py 等)
- requirements.txt 实际依赖清单
