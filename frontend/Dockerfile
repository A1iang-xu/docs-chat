# ── 阶段 1：构建 ──
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── 阶段 2：生产运行 ──
FROM node:20-alpine

WORKDIR /app

# 安装 serve 用于托管静态文件
RUN npm install -g serve

# 复制构建产物
COPY --from=builder /app/dist ./dist

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:5173/ || exit 1

CMD ["serve", "-s", "dist", "-l", "5173"]