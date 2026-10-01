# 知识库平台前端拆分（阶段一 · Vue 3 + Vite）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `legacy_streamlit/app.py`（原 `D:/AI-python/知识库平台/app.py`，526 行）的界面与交互迁成独立的 Vue 3 + Vite 进程，能力等价：文档入库、RAG 问答、普通对话、会话历史恢复、清空对话。

**Architecture:** 两个进程，前端只讲 HTTP 与 `/api/*` 相对路径对话，开发期靠 `vite.config.js` 的 `server.proxy` 同源（spec 三节）。状态管理不用库：`useSession` / `useDocuments` / `useChat` 三个 composable 在 `App.vue` 里显式传参；`localStorage` 只存 `session_id`，消息列表永远以后端为准（spec 五节）。`api/` 是唯一碰网络的一层，组件不认 fetch。

**Tech Stack:** Node v24.15.0 + npm 11.12.1、Vite ^8.3.0、@vitejs/plugin-vue ^6.0.8、Vue ^3.5.42（`vue` 单文件组件 + `<script setup>`），手写 CSS 三件套，无 TypeScript、无 UI 组件库、无 Pinia/Vuex、无 Vitest。

**Spec:** `docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md`（本文"坑 N"指 `知识库平台开发文档.md` 第七节编号，"spec x.x"指该设计文档章节；后端侧真相在 `docs/superpowers/plans/2026-09-30-kb-platform-backend.md` 与 `backend/` 代码）

---

## Global Constraints

- **环境是 Windows + Git Bash（POSIX sh）**，仓库路径含中文：所有命令用绝对路径并用双引号包住，形如 `cd "D:/知识库平台-前后端分离/frontend"`。不假设 `cmd.exe` 语法。
- **Node v24.15.0、npm 11.12.1 已在 PATH**（实测）。不装任何全局包；依赖只进 `frontend/node_modules/`。Task 1 Step 1 是一条快速失败的冒烟 `node --version && npm --version`，任一不满足就停下报错，不要往下写文件。
- **目标目录 `frontend/` 当前只有已入库的 `README.md`（非空）**。实测 `create-vite` 对非空目录只会打印 `Operation cancelled`，而它的 `--overwrite` 会连 `README.md` 一起删——所以走"临时目录脚手架 + 逐项 `mv`"的序列（Task 1），且**任何情况下都不准把脚手架直接铺进仓库根**。
- **语言与库的边界**：纯 JavaScript（不写 `.ts`、不装 TypeScript）；不装任何 UI 组件库；不装 Pinia/Vuex；不引 Vitest。CSS 全部手写，只允许 `src/styles/` 三件套（`variables.css` / `base.css` / `layout.css`），组件文件里**不写 `<style>` 块**。
- **文件布局严格照 spec 第五节**，不新增清单外的源文件：`api/client.js+documents.js+chat.js+history.js`、`composables/useSession.js+useDocuments.js+useChat.js`、`components/ChatHeader StatusBar MessageList MessageBubble ReferenceList ChatInput DocumentPanel FileUploader DocCard`、`utils/typewriter.js`、`styles/` 三件套。小工具（如日期格式化）就地写在唯一用到它的组件里。
- **开发期代理**：`vite.config.js` 写 `server: { proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } } }`；前端代码里**永不出现** `http://localhost:8000` 或 `http://127.0.0.1:8000`，全部走 `/api/...` 相对路径。
- **客户端错误规则只有一条**：`!res.ok` → 读响应体的 `detail` → `throw new Error(detail)`；没有统一响应壳要剥（spec 六节）。
- **会话**：`localStorage` 只存 `session_id` 这一个键，缺失时用 `crypto.randomUUID()` 生成；消息**永不**写进 `localStorage`；刷新后靠 `GET /api/history/{session_id}` 恢复（后端已把一行 DB 展开成 user+assistant 两条并带 `references`）。
- **安全（坑 6）**：**全项目不出现 `v-html`**，一处都不许。文档正文、答案、引用片段一律 `{{ }}` 文本插值 + `white-space: pre-wrap`。
- **阶段一对话是非流式** `POST /api/chat`：整段答案到手后，由 `utils/typewriter.js` 在前端本地逐字吐字（正则沿用 `app.py` 的 `[A-Za-z0-9]+|\s+|.`）；**阶段二 SSE 落地当天整文件删除 `typewriter.js`**（spec 十一节第 8 步：不能两套逐字逻辑并存）。
- **字段命名保持后端的 snake_case**（`session_id` / `document_ids` / `chunk_count` / `references[].document_id` / `used_chunks`）：前端不做 camelCase 转换层——少一层映射就少一处会写错的地方。
- **引用形状**：`{document_id, parent_id, filename, snippet}`；`snippet` 最长 83 字符（后端 `SNIPPET_LIMIT = 80` + `"..."`，见 `backend/schemas/common.py`），不要在前端再截断。文档在界面上的显示约定是 `{filename}(#{id})`（坑 5：同名文档靠 id 区分）。
- **上传只认单文件端点** `POST /api/documents`（multipart 字段名 `file`）：前端 `for` 循环逐个串行发，每个文件独立 pending/上传中/成功/失败 + 重试 + 进度（spec 6.2）。传输方式选 **`XMLHttpRequest`**，理由见 Task 4。
- **`mode: "rag" | "normal"`** 驱动状态标签文案；`document_ids: []` 即普通对话链（spec 6.2）。
- **CSS 迁移取舍**（spec 五节）：搬 `.message` / `.doc-card` / `.status-indicator` / 打字机 `@keyframes blink` / 品牌色 `#667eea`+`#764ba2` / user+assistant 气泡配色；**丢弃**全部 `[data-testid="st..."]`、`stChatInput`、`stMainBlockContainer`、`stButton > button`、`#MainMenu`、`footer` 这批 Streamlit DOM 专有覆盖。
- **联调后端命令**：`cd "D:/知识库平台-前后端分离/backend" && python -m uvicorn main:app --reload --port 8000`。用 PATH 上的 `python`（3.12.3，依赖已齐）；**绝不用 `D:/AI-python/.venv`**——那是个只有 pip 的空 3.14 venv，用了必 "module not found"（spec 第十节写的那条 venv 命令已过时，以本条为准）。MySQL 常驻，基线数据：`documents` 1 行、Chroma parent 2 / child 7、`chat_history` 2 行。
- **验证 = 手测**：没有前端单测框架。每个 Task 结尾是"浏览器里点什么、看到什么"的核对步骤，加一次人工契约核对（`api/client.js` 抛的 `Error.message` 等于后端 `detail`，spec 九节"契约"行）。
- **Git**：仓库根 `D:/知识库平台-前后端分离`，当前活动分支 `feat/backend-split`（前端各 Task 就提在该分支上，不新建分支）。每个 Task 提交一次，身份临时指定：`git -c user.name="31439" -c user.email="31439@local" commit ...`；**不改 git 配置**。根 `.gitignore` 已含 `frontend/node_modules/`、`frontend/dist/`，无需再动。
- **文案与注释**：界面字符串全部中文；注释只写"为什么"，一行以内，不解释代码在做什么。
- **本计划的范围只有前端。** 后端 `api/chat.py` / `api/history.py` 已落地（后端 Task 8，通过评审 + 修复轮），契约行以 `backend/` 代码实测行为为准：chat 的 rag/normal 两条链只把 `RetrievalError`/`LLMError` 就地转 502，其余领域错误走 `main.py` 的 `STATUS_BY_ERROR` 中央映射；history 的 user 行 `references` 是 `null`（`api/history.py` 构造 `references=None`），消费端必须 `msg.references ?? []`。

---

## File Structure

```
frontend/                             # 本计划的全部产物（脚手架合并进这个非空目录）
├── index.html                        # 脚手架生成 → 改 lang="zh-CN" 与 <title>知识库平台</title>
├── package.json                      # 脚手架生成：dev/build/preview 三个脚本，不手动改版本
├── vite.config.js                    # 脚手架生成 → 加 server.proxy（Task 1）
├── .gitignore                        # 脚手架生成（node_modules/dist/logs），与根 .gitignore 并存不冲突
├── README.md                         # 已入库，保持原样不动（脚手架的同名文件不要盖进来）
├── node_modules/                     # npm install 产物，gitignored
└── src/
    ├── main.js                       # 只做两件事：按序 import 三个 css、mount(App)
    ├── App.vue                       # 两栏布局 + 三个 composable 的显式接线（唯一持有状态的地方）
    ├── api/
    │   ├── client.js                 # 唯一的 fetch 封装 + detailFromText()（XHR 上传复用）
    │   ├── documents.js              # listDocuments() / uploadDocument(file, {onProgress})  ← XHR
    │   ├── chat.js                   # sendChat(payload)；阶段二在这里加 sendChatStream
    │   └── history.js                # getHistory(sessionId, limit) / clearHistory(sessionId)
    ├── composables/
    │   ├── useSession.js             # sessionId + resetSession()，localStorage 只碰 session_id
    │   ├── useDocuments.js           # documents / selectedIds / queue / 串行上传队列 / docLabel()
    │   └── useChat.js                # messages / pending / error / restore() / send() / clear()
    ├── components/
    │   ├── ChatHeader.vue            # 渐变头部：标题 + 副标题（原 .chat-header）
    │   ├── StatusBar.vue             # 模式标签 + session 短显（原 status-indicator 那块）
    │   ├── MessageList.vue           # v-for 消息 + 欢迎语 + 自动滚到底
    │   ├── MessageBubble.vue         # 头像 + 气泡正文（pre-wrap）+ 打字机光标 + 引用
    │   ├── ReferenceList.vue         # 📎 filename(#id) snippet，纯文本插值
    │   ├── ChatInput.vue             # textarea + 发送；Enter 发、Shift+Enter 换行
    │   ├── DocumentPanel.vue         # 左栏装配：上传器 + 文档列表 + 文档数 + 清空对话
    │   ├── FileUploader.vue          # <input type=file multiple> + 队列渲染（进度/失败/重试）
    │   └── DocCard.vue               # 单张卡片：勾选框 + 文件名/时间/块数（原 .doc-card）
    ├── utils/typewriter.js           # tokenize() + startTypewriter()，阶段二整文件删除
    └── styles/
        ├── variables.css             # 品牌色/气泡色/状态色等 token
        ├── base.css                  # reset + 字体 + @keyframes blink + 按钮/链接
        └── layout.css                # 两栏栅格 + 迁移过来的 .message/.doc-card/.status-indicator + 断点
```

**删掉的脚手架样板**（Task 1 一次清干净，别留到 Task 3）：`src/style.css`、`src/components/HelloWorld.vue`、`src/assets/hero.png`、`src/assets/vite.svg`、`src/assets/vue.svg`、`src/App.vue` 的样板内容（Task 3 整文件重写）。`public/favicon.svg` 保留（`index.html` 引用它），`public/icons.svg` 与 `.vscode/` **不拷进 `frontend/`**（前者是模板站的图标集，后者是编辑器推荐插件列表，与本工程无关；根 `.gitignore` 也已忽略 `.vscode/`）。

---

## Task 1: Vite 骨架落地 `frontend/` + 同源代理 + 冒烟

**Files:**
- Create: `frontend/.gitignore`、`frontend/index.html`、`frontend/package.json`、`frontend/vite.config.js`、`frontend/src/main.js`、`frontend/src/App.vue`、`frontend/public/favicon.svg`
- Create（`npm install` 产物，要入库）: `frontend/package-lock.json`
- Keep untouched: `frontend/README.md`（已入库；脚手架的同名文件不要盖进来）

**Interfaces:**
- Consumes: 无
- Produces: 一个能 `npm run dev` 起来的空壳工程；`vite.config.js` 里的 `/api` 代理是 Task 2 之后所有请求能同源的前提；npm scripts 只有 `dev` / `build` / `preview` 三个，本计划只用前两个。

- [ ] **Step 1: 环境冒烟（不满足就停在这一步）**

```bash
node --version && npm --version
```

预期 `v24.15.0` 与 `11.12.1`（本机实测值）。任一命令不存在就停下报错，**不要**继续建文件——后面每一步都依赖 npm。

- [ ] **Step 2: 在临时目录里脚手架（`frontend/` 非空，不能原地生成）**

```bash
mkdir -p /tmp/kb-scaffold && cd /tmp/kb-scaffold
npm create -y vite@latest tmp-app -- --template vue
```

实测要点（不要临场改写法）：
- `-y` 是 npm 自己的 `--yes`，必须写在 `--` **之前**：本机没有缓存 `create-vite`，不给就是 `npm error npx canceled due to missing packages and no YES option`。`--` 之后的参数才交给 `create-vite`。
- `--template vue` 是 JS 模板（`vue-ts` 才是 TS），带上它就不进交互式提问。
- 期望输出以 `└  Done. Now run:` 结尾；产物为 `index.html package.json vite.config.js src/ public/ .gitignore .vscode/ README.md`。
- **绝不**在 `D:/知识库平台-前后端分离` 或 `frontend/` 里直接跑这条命令：实测 `create-vite` 撞到非空目录只打印 `Operation cancelled`（什么都不写），而它的 `--overwrite` 是"删除已有文件"语义，会把已入库的 `frontend/README.md` 干掉。
- `--no-interactive` 只控制提问与否，与"合并进非空目录"无关，本计划不用它。

- [ ] **Step 3: 逐项拷进 `frontend/`（跳过 README.md），清样板**

```bash
SRC=/tmp/kb-scaffold/tmp-app
cd "D:/知识库平台-前后端分离/frontend"
cp -a "$SRC"/.gitignore "$SRC"/index.html "$SRC"/package.json "$SRC"/vite.config.js "$SRC"/src .
mkdir -p public && cp -a "$SRC"/public/favicon.svg public/
rm -f src/style.css src/components/HelloWorld.vue src/assets/hero.png src/assets/vite.svg src/assets/vue.svg
rmdir src/assets src/components
rm -rf /tmp/kb-scaffold
ls -a
```

预期 `ls -a`：`. .. .gitignore README.md index.html package.json public src vite.config.js`，且 `src/` 里只剩 `App.vue main.js`。`rmdir` 报 "Directory not empty" 说明模板与这里假设的不一致，**停下来核对**，别 `rm -rf` 硬来。

- [ ] **Step 4: 把样板 `src/App.vue` 换成能确认挂载成功的最小壳**

`frontend/src/App.vue`（整文件覆盖；Task 3 会连样式三件套一起重写，这里只求"确实 mount 上了"）：

```vue
<script setup>
// Task 1 冒烟壳：证明 Vite 能编译 SFC 并挂载，Task 3 整文件重写
</script>

<template>
  <div class="smoke">前端骨架已就绪</div>
</template>
```

`frontend/src/main.js`（整文件覆盖；样板里的 `import './style.css'` 指向 Step 3 已删的文件，留着就是启动报错）：

```js
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

`frontend/index.html`（只改语言与标题两处，`favicon.svg` 那行保持样板原样，文件还在）：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>知识库平台</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 5: 写代理配置**

`frontend/vite.config.js`（整文件覆盖；样板只有 `plugins: [vue()]`）：

```js
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- `target` 写 `127.0.0.1` 不写 `localhost`：uvicorn 绑的是 `127.0.0.1`，Windows 上 `localhost` 会先试 IPv6 解析，偶发 `ECONNREFUSED`。
- 不写 `rewrite`：后端路由自带 `/api` 前缀（`backend/api/documents.py` 是 `APIRouter(prefix="/api/documents")`）。
- 不配 `server.host` / `server.port`：默认 `localhost:5173` 就够；后端那两份 CORS 白名单在同源代理下用不上，只是"直接打开 dist"的兜底（spec 三节）。

- [ ] **Step 6: 装依赖（只装进本工程，不碰全局）**

```bash
cd "D:/知识库平台-前后端分离/frontend" && npm install
```

预期：`added N packages`、无 error，生成 `node_modules/` 与 `package-lock.json`；`package.json` 保持 `vue ^3.5.42 / vite ^8.3.0 / @vitejs/plugin-vue ^6.0.8`。**不要**顺手加任何清单外的包（UI 库、Pinia、Axios、Vitest 全部排除）。

- [ ] **Step 7: dev server 冒烟**

终端 A（保持运行）：

```bash
cd "D:/知识库平台-前后端分离/frontend" && npm run dev
```

终端 B：

```bash
curl -s http://localhost:5173/ | head -8
```

预期：返回原始 HTML，含 `<title>知识库平台</title>` 与 `<div id="app">`。浏览器打开终端 A 打印的地址（默认 `http://localhost:5173/`；端口被占时 Vite 会打印实际端口，手测以打印值为准——代理与端口无关），页面显示"前端骨架已就绪"，DevTools Console 无红色报错。

- [ ] **Step 8: 代理连通性核对（需要后端在跑）**

终端 C：

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m uvicorn main:app --reload --port 8000
```

终端 B：

```bash
curl -s http://localhost:5173/api/health
curl -s http://localhost:5173/api/documents
```

预期：`/api/health` 返回 `{"status":"ok","chroma_dir":...,"document_count":1,"vector_counts":{"parent":2,"child":7}}`——`status`、`document_count`、`vector_counts` 三个对齐基线就算过（`chroma_dir` 只要指向 `backend/data/chroma_db` 即可，分隔符按实际输出，不逐字比），`/api/documents` 返回 1 个元素的数组——这一步成立即证明"浏览器视角同源"。
若直连 `http://127.0.0.1:8000/api/health` 通、经 5173 不通，问题只在 `vite.config.js` 的 proxy 写法，别去改前端代码。

- [ ] **Step 9: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/.gitignore frontend/index.html frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src frontend/public
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "chore(frontend): Vite + Vue3 骨架落地，/api 走同源代理"
```

预期 `git status --short`（add 后、commit 前）里没有 `node_modules/`、没有 `dist/`，`frontend/README.md` 不在暂存区（未修改）。

---

## Task 2: `api/` 四个模块 + 一次人工契约核对

**Files:**
- Create: `frontend/src/api/client.js`、`frontend/src/api/documents.js`、`frontend/src/api/chat.js`、`frontend/src/api/history.js`

**Interfaces:**
- Consumes: Task 1 的 `/api` 同源代理。
- Produces（后续 Task 只按这些签名调用，不再直接 `fetch`）:
  - `detailFromText(text: string, status: number) → string`
  - `request(path: string, { method = 'GET', body?: object, headers?: object, signal?: AbortSignal }) → Promise<any>`；`!res.ok` 一律 `throw new Error(detail)`
  - `listDocuments() → Promise<Array<{id:number, filename:string, chunk_count:number, created_at:string}>>`
  - `uploadDocument(file: File, { onProgress?: (percent:number)=>void }) → Promise<{id, filename, chunk_count, created_at}>`（HTTP 201 由 `request` 之外的 XHR 分支接受）
  - `sendChat({session_id, question, document_ids}) → Promise<{answer:string, references:Array<{document_id,parent_id,filename,snippet}>, mode:'rag'|'normal'}>`
  - `getHistory(sessionId, limit=50) → Promise<Array<{role:'user'|'assistant', content:string, references|null, created_at|null}>>`
  - `clearHistory(sessionId) → Promise<{cleared:number}>`

- [ ] **Step 1: 写 `frontend/src/api/client.js`**

```js
// 全项目唯一的网络出口：组件层永远看不到 fetch 与 Response（spec 六节"不加响应壳"）

// 独立成纯函数是因为上传走 XHR（见 documents.js），它手上没有 Response 只有文本，
// 但错误规则必须和 fetch 那条完全一致，否则同一个 415 在两个入口显示两种文案。
export function detailFromText(text, status) {
  let body
  try {
    body = JSON.parse(text)
  } catch {
    // 代理层或静态服务器给的 HTML 错误页：别让 JSON.parse 抛出的怪话盖掉真实状态码
    return `HTTP ${status}`
  }
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI 的参数校验把 detail 组成数组（422），领域异常 handler 给的是字符串
    return detail.map((item) => item?.msg ?? JSON.stringify(item)).join('；')
  }
  return `HTTP ${status}`
}

export async function request(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const isJson = body !== undefined
  let res
  try {
    res = await fetch(path, {
      method,
      headers: {
        Accept: 'application/json',
        ...(isJson ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: isJson ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch {
    // fetch 只在网络层失败时 reject：此时没有 detail 可读，给一句能行动的中文
    throw new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) throw new Error(detailFromText(await res.text(), res.status))
  return res.json()
}
```

- [ ] **Step 2: 写 `frontend/src/api/documents.js`**

```js
import { detailFromText, request } from './client.js'

export function listDocuments() {
  return request('/api/documents')
}

// 上传选 XMLHttpRequest 不选 fetch：fetch 没有上传方向的事件（ReadableStream 管的是读响应），
// 而 spec 6.2 要求每个文件独立的进度；阶段二的 SSE 才回到 fetch + ReadableStream，两者不冲突。
export function uploadDocument(file, { onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file) // 字段名是后端 File(...) 定的：单数 file
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/documents')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          reject(new Error(`上传成功但响应不是 JSON（HTTP ${xhr.status}）`))
        }
      } else {
        reject(new Error(detailFromText(xhr.responseText, xhr.status)))
      }
    }
    xhr.onerror = () => reject(new Error('无法连接后端，上传中断'))
    xhr.send(form)
  })
}
```

- [ ] **Step 3: 记下"代码为准"的 5 条契约差异**

本 Task 已把 `backend/` 现有代码与 spec 6.1 端点表逐条对过，差异如下，**全部以代码为准**（后面的 Task 都按这些写）：

1. `POST /api/documents` 除了 spec 列的 415/422/500，还会返回 **413 `文件超过 20MB`**（`backend/api/documents.py:14` 的 `MAX_UPLOAD_BYTES`，spec 端点表之外新增的守卫）。前端不做大小预检：同一条 `detail` 规则已经覆盖它，两处判定只会漂移。
2. **422 有两种体**：领域异常与 handler 给的 `detail` 是字符串，FastAPI 自动参数校验给的是**数组**（元素含 `msg`）。`detailFromText` 里那条 `Array.isArray` 分支就是为它存在的——spec 六节"只读 detail"的写法在这一条上是不完整的。
3. `GET /api/history` 的 user 行 `references` 是 **`null`**（`backend/schemas/chat.py` 的 `HistoryMessage` 默认值 + 后端 Task 8 Step 5 的实现），assistant 行才是数组；`useChat.restore` 用 `row.references ?? []` 归一，模板里再判 `.length`。
4. 老行 `used_chunks` 为 `NULL` 或不是合法 JSON 时，后端降级成 `references: []` 而不是 500（后端计划 Task 8 的 `test_legacy_rows_without_used_chunks_still_load` / `test_corrupt_used_chunks_degrades_to_empty`）——所以"历史能恢复但没有引用区"是**预期行为**，不是前端 bug。
5. 检索为空是 **200 + 一段说明文案**（`backend/core/rag_system.py:67-69`），不是错误码：前端不能把它当失败弹错误条。

- [ ] **Step 4: 写 `frontend/src/api/chat.js`**

```js
import { request } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// 形状即 backend/api/chat.py 的实测行为：ChatRequest 三字段入，ChatResponse 出（answer/references/mode），
// 失败 502 {"detail"}（RetrievalError/LLMError 就地转，其余领域错误走中央映射）。
export function sendChat(payload) {
  return request('/api/chat', { method: 'POST', body: payload })
}
```

- [ ] **Step 5: 写 `frontend/src/api/history.js`**

```js
import { request } from './client.js'

// 形状即 backend/api/history.py 的实测行为：GET 返回"一行 DB 展开成 user + assistant 两条"的列表（spec 6.2 第 3 条），
// user 行的 references 为 null，assistant 行为数组（used_chunks 脏数据已降级成 []）。
export function getHistory(sessionId, limit = 50) {
  // session_id 进路径段。值本该是 UUID，但 localStorage 可被手改成含 "/" 的串，编一下才不会莫名 404
  return request(`/api/history/${encodeURIComponent(sessionId)}?limit=${limit}`)
}

export function clearHistory(sessionId) {
  return request(`/api/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}
```

- [ ] **Step 6: 契约核对（一次人工，spec 九节"契约"行；这就是本计划的"测试"）**

后端在跑（Task 1 Step 8 的终端 C），dev server 在跑（终端 A）。浏览器打开 `http://localhost:5173/`，F12 → Console，逐条粘贴执行（Vite 在 dev 下直接按路径提供源码模块，所以能这样 import）：

```js
const c = await import('/src/api/client.js')
const d = await import('/src/api/documents.js')

await d.listDocuments()
await c.request('/api/documents/nonexistent')
await d.uploadDocument(new File([], 'empty.txt', { type: 'text/plain' }))
await d.uploadDocument(new File(['x'], 'bad.exe', { type: 'text/plain' }))
```

另开终端，用 curl 拿同一批接口的原始响应体做对照：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/api/documents/nonexistent
curl -s http://localhost:5173/api/documents/nonexistent; echo
curl -s -X POST http://localhost:5173/api/documents -F "file=@-;filename=empty.txt;type=text/plain" <<< ""; echo
curl -s -X POST http://localhost:5173/api/documents -F "file=@-;filename=bad.exe;type=text/plain" <<< "x"; echo
```

必须逐条对上（这是本 Task 的通过判据）：
1. `d.listDocuments()` 打印出 1 个元素的数组，字段是 `id / filename / chunk_count / created_at`——与 `backend/schemas/documents.py` 一致。
2. `c.request('/api/documents/nonexistent')` 抛出的 `Error.message` **逐字等于** curl 那条 `{"detail":"Not Found"}` 里的 `Not Found`（没有壳、没有包装前缀）。
3. 空文件上传 reject 的 message 是 `文件内容为空`（HTTP 422，来自 `backend/api/documents.py:26`）。
4. `.exe` 上传 reject 的 message 是 `不支持的文件类型: .exe`（HTTP 415，来自 `backend/core/document_processor.py:51`）——同一条规则在 XHR 路径和 fetch 路径文案一致，说明 `detailFromText` 抽对了。
5. `uploadDocument` 的成功路径与进度：`await d.uploadDocument(new File(['甲公司的营收是 100 元。'], 'smoke-t2.txt', { type: 'text/plain' }), { onProgress: (p) => console.log('progress', p) })` → Console 依次打印若干百分比，promise resolve 出恰好四个键 `{id, filename:"smoke-t2.txt", chunk_count, created_at}`。**这条会真的入库一份文档**：本计划不做清理（后端没有删除接口，坑 10），它和 Task 4 Step 8 上传的那几份一起构成 Task 7 全量清单的基线，"文档数"按当时实际值看即可。不想在本 Task 留脏数据，就把文件名换成 `smoke-t2.exe`——`progress` 照样跑、最后 reject 415，只是 201 的响应形状得留到 Task 4 用真实文件验。

契约核对结果（哪条对上、`Error.message` 原文）记在提交信息里，不另开文档。

- [ ] **Step 7: 顺带确认 chat/history 是否已可联调**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5173/api/chat -H "Content-Type: application/json" -d '{"session_id":"probe","question":"你好","document_ids":[]}'
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/api/history/probe
```

- 打印 `200` / `200`：后端 Task 8 已落地，继续验一条真实形状：

```bash
curl -s -X POST http://localhost:5173/api/chat -H "Content-Type: application/json" -d '{"session_id":"probe","question":"你好","document_ids":[]}'
curl -s http://localhost:5173/api/history/probe
curl -s -X DELETE http://localhost:5173/api/history/probe
```

  预期依次是 `{"answer":"...","references":[],"mode":"normal"}`、`[{"role":"user","content":"你好","references":null,"created_at":"..."},{"role":"assistant","content":"...","references":[],"created_at":"..."}]`、`{"cleared":1}`。与本计划的 `sendChat/getHistory/clearHistory` 签名逐个对，不一致就**以实际返回为准**改 Task 5/6 的调用代码（并在提交信息里记下差异）。
- 打印 `404` / `404`：后端 Task 8 还没落地。**这不影响本 Task 提交**——`api/chat.js`、`api/history.js` 只是纯转发封装，签名由 spec 6.1 与 `backend/schemas/chat.py` 钉住；继续做 Task 3/4，到 Task 5 之前必须回来重跑本 Step。

- [ ] **Step 8: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/api
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): api 层四个模块，detail 解析与后端逐字对齐"
```

---

## Task 3: `useSession` + 样式三件套 + `App.vue` 骨架（含 `ChatHeader` / `StatusBar`）

**Files:**
- Create: `frontend/src/composables/useSession.js`、`frontend/src/styles/variables.css`、`frontend/src/styles/base.css`、`frontend/src/styles/layout.css`、`frontend/src/components/ChatHeader.vue`、`frontend/src/components/StatusBar.vue`
- Modify: `frontend/src/main.js`（三行 css import）、`frontend/src/App.vue`（整文件重写为两栏骨架）

**Interfaces:**
- Consumes: 无（不碰 `api/`）。
- Produces:
  - `useSession() → { sessionId: Ref<string>, resetSession: () => string }`，`localStorage` 只读写 `session_id` 这一个键。
  - CSS 类名契约（Task 4/5 直接沿用、不再新增 token）：`.app-shell` `.panel-open` `.panel-toggle` `.side-panel` `.side-panel-inner` `.panel-title` `.panel-hr` `.panel-hint` `.chat-main` `.chat-container` `.chat-header` `.chat-title` `.chat-subtitle` `.chat-body` `.chat-messages` `.empty-hint` `.status-bar` `.status-indicator` `.status-rag` `.status-normal` `.session-chip` `.session-debug` `.session-value` `.error-banner` `.btn` `.btn-ghost` `.btn-small` `.pre-wrap` `.streaming-cursor`，以及全部 `--*` 变量。
  - `App.vue` 里的接线约定：**composable 的返回值一律解构**（`const { sessionId, resetSession } = useSession()`）——解构出的 ref 是 setup 顶层绑定，模板会自动解包；写成 `session.sessionId.value` 那种嵌套形式模板不会解包，容易一路错到 Task 5。

- [ ] **Step 1: 建目录**

```bash
cd "D:/知识库平台-前后端分离/frontend" && mkdir -p src/composables src/components src/utils src/styles && ls src
```

预期：`App.vue api components composables main.js styles utils`（`utils` 空目录先建出来，Task 5 往里放 `typewriter.js`；空目录不会被 git 跟踪，无副作用）。

- [ ] **Step 2: 写 `frontend/src/composables/useSession.js`**

```js
import { ref } from 'vue'

const STORAGE_KEY = 'session_id'

// localStorage 里只有这一个键：消息永不落本地，刷新后靠 GET /api/history 恢复（spec 五节）
export function useSession() {
  const stored = localStorage.getItem(STORAGE_KEY)
  const sessionId = ref(stored ?? crypto.randomUUID())
  if (!stored) localStorage.setItem(STORAGE_KEY, sessionId.value)

  function resetSession() {
    // "清空对话"要换 id（与 app.py 的行为等价）：旧 session 的历史已被 DELETE 清掉，
    // 换新 id 顺带避免"清空后立刻刷新"时和还在飞的请求抢同一个 session。
    const next = crypto.randomUUID()
    sessionId.value = next
    localStorage.setItem(STORAGE_KEY, next)
    return next
  }

  return { sessionId, resetSession }
}
```

`crypto.randomUUID()` 只在安全上下文里有：`http://localhost:5173` 与 `http://127.0.0.1:5173` 都算，**手测只用这两个地址**；哪天用局域网 IP 打开，这行会 `undefined` 报错，那是环境不是代码。

- [ ] **Step 3: 写 `frontend/src/styles/variables.css`（颜色字面值只允许出现在这个文件）**

```css
/* app.py 内联 CSS 的品牌色与气泡配色，抽成 token（spec 五节 CSS 迁移取舍） */
:root {
  --brand-1: #667eea;
  --brand-2: #764ba2;
  --grad-brand: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
  --grad-brand-135: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  --grad-assistant-avatar: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);

  --bubble-user: var(--grad-brand-135);
  --bubble-user-fg: #ffffff;
  --bubble-assistant: #ffffff;
  --bubble-assistant-fg: #333333;

  --page-bg: #f8f9fa;
  --panel-bg: #ffffff;
  --border: #e1e5e9;
  --text-main: #333333;
  --text-muted: #6b7280;

  --status-rag-bg: #e3f2fd;
  --status-rag-fg: #1976d2;
  --status-normal-bg: #f3e5f5;
  --status-normal-fg: #7b1fa2;

  --ok-fg: #2e7d32;
  --fail-bg: #fdecea;
  --fail-fg: #c62828;

  --radius-card: 8px;
  --radius-bubble: 18px;
  --radius-pill: 20px;
  --shadow-panel: 0 8px 32px rgba(0, 0, 0, 0.1);
  --shadow-card-hover: 0 2px 8px rgba(102, 126, 234, 0.1);
  --shadow-bubble: 0 1px 2px rgba(0, 0, 0, 0.1);

  --side-width: 320px;
}
```

- [ ] **Step 4: 写 `frontend/src/styles/base.css`**

```css
*,
*::before,
*::after { box-sizing: border-box; }

html,
body,
#app { height: 100%; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', 'PingFang SC', sans-serif;
  font-size: 14px;
  line-height: 1.4;
  color: var(--text-main);
  background: var(--page-bg);
}

h1, h2, h3, p, ul, ol, figure { margin: 0; }
ul, ol { padding: 0; list-style: none; }
button { font: inherit; cursor: pointer; }
input, textarea { font: inherit; color: inherit; }
code { font-family: ui-monospace, Consolas, monospace; }

/* 原 .stButton > button：只搬样式，Streamlit 的选择器本身丢掉 */
.btn {
  background: var(--grad-brand);
  color: #fff;
  border: none;
  border-radius: var(--radius-card);
  padding: 8px 16px;
  font-weight: 500;
  transition: transform 0.2s, box-shadow 0.2s;
}
.btn:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; box-shadow: none; }
.btn-ghost { background: #fff; color: var(--brand-1); border: 1px solid var(--border); }
.btn-small { padding: 4px 10px; font-size: 12px; }

/* 打字机光标：app.py 的 .streaming-cursor::after + @keyframes blink 原样搬 */
.streaming-cursor::after {
  content: '▌';
  margin-left: 2px;
  color: var(--brand-1);
  animation: blink 1s infinite;
}
@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* 坑 6：正文只走文本插值，pre-wrap 保住后端返回的换行，不引 Markdown 渲染 */
.pre-wrap { white-space: pre-wrap; word-break: break-word; }
```

- [ ] **Step 5: 写 `frontend/src/styles/layout.css`（本 Task 只到"骨架"；Task 4 追加文档区，Task 5 追加消息区）**

```css
/* 两栏：左固定右自适应；≤768px 单栏 + 侧栏可折叠（spec 五节 App.vue） */
.app-shell {
  display: grid;
  grid-template-columns: var(--side-width) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
  height: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 16px;
}

.side-panel {
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-panel);
  overflow-y: auto;
}
.side-panel-inner { display: flex; flex-direction: column; gap: 12px; padding: 16px; }
.panel-title { font-size: 18px; font-weight: 600; }
.panel-hr { border: none; border-top: 1px solid var(--border); margin: 4px 0; }
.panel-hint { font-size: 13px; color: var(--text-muted); }
.session-debug { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-muted); }
.session-value {
  padding: 4px 6px;
  background: var(--page-bg);
  border: 1px dashed var(--border);
  border-radius: 4px;
  word-break: break-all;
}

/* app.py 的 .chat-container / .chat-header / .chat-title / .chat-subtitle */
.chat-main { display: flex; min-width: 0; }
.chat-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-height: 100%;
  overflow: hidden;
  background: #fff;
  border-radius: 12px;
  box-shadow: var(--shadow-panel);
}
.chat-header {
  padding: 20px;
  text-align: center;
  color: #fff;
  background: var(--grad-brand);
  border-radius: 12px 12px 0 0;
}
.chat-title { display: flex; align-items: center; justify-content: center; gap: 10px; font-size: 24px; font-weight: 600; }
.chat-subtitle { margin-top: 5px; font-size: 14px; opacity: 0.9; }

.chat-body { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.chat-messages { flex: 1; padding: 20px; overflow-y: auto; background: var(--page-bg); }
.empty-hint { padding: 24px 0; text-align: center; color: var(--text-muted); }

/* app.py 的 .status-indicator / .status-rag / .status-normal */
.status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  background: #fff;
  border-bottom: 1px solid var(--border);
}
.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 500;
}
.status-rag { background: var(--status-rag-bg); color: var(--status-rag-fg); }
.status-normal { background: var(--status-normal-bg); color: var(--status-normal-fg); }
.session-chip { font-size: 12px; color: var(--text-muted); }

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 20px 0;
  padding: 8px 12px;
  border-radius: var(--radius-card);
  background: var(--fail-bg);
  color: var(--fail-fg);
  font-size: 13px;
}

.panel-toggle { display: none; }

@media (max-width: 768px) {
  .app-shell { grid-template-columns: minmax(0, 1fr); gap: 10px; padding: 10px; }
  .side-panel { display: none; }
  .app-shell.panel-open .side-panel {
    display: block;
    position: sticky;
    top: 10px;
    z-index: 2;
    max-height: 70vh;
  }
  .panel-toggle { display: inline-flex; align-self: start; }
  .chat-messages { padding: 12px; }
}
```

- [ ] **Step 6: 写 `frontend/src/main.js`（css 顺序有讲究：变量在最前）**

```js
import { createApp } from 'vue'
import './styles/variables.css'
import './styles/base.css'
import './styles/layout.css'
import App from './App.vue'

createApp(App).mount('#app')
```

- [ ] **Step 7: 写两个纯展示组件**

`frontend/src/components/ChatHeader.vue`：

```vue
<template>
  <header class="chat-header">
    <div class="chat-title">🤖 智能文档检索助手</div>
    <div class="chat-subtitle">基于知识库的智能问答系统</div>
  </header>
</template>
```

`frontend/src/components/StatusBar.vue`：

```vue
<script setup>
import { computed } from 'vue'

// 模式标签只看"勾了几个文档"，不看后端回传：勾选即 RAG（spec 6.2 document_ids 为空即普通对话）
const props = defineProps({
  selectedCount: { type: Number, required: true },
  sessionId: { type: String, required: true },
})

const shortSession = computed(() => props.sessionId.slice(0, 8))
</script>

<template>
  <div class="status-bar">
    <span v-if="props.selectedCount > 0" class="status-indicator status-rag">
      🔍 知识库模式（{{ props.selectedCount }} 个文档）
    </span>
    <span v-else class="status-indicator status-normal">💬 普通对话模式</span>
    <span class="session-chip" :title="props.sessionId">session {{ shortSession }}</span>
  </div>
</template>
```

两个组件都**不写 `<style>` 块**——样式全在三件套里（Global Constraints）。

- [ ] **Step 8: 重写 `frontend/src/App.vue` 为两栏骨架**

```vue
<script setup>
import { ref } from 'vue'
import ChatHeader from './components/ChatHeader.vue'
import StatusBar from './components/StatusBar.vue'
import { useSession } from './composables/useSession.js'

// 三个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, resetSession } = useSession()

// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)
</script>

<template>
  <div class="app-shell" :class="{ 'panel-open': panelOpen }">
    <aside class="side-panel">
      <div class="side-panel-inner">
        <h2 class="panel-title">📁 文档管理</h2>
        <p class="panel-hint">上传与文档列表在 Task 4 接入</p>
        <hr class="panel-hr" />
        <div class="session-debug">
          <span>当前 session_id</span>
          <code class="session-value">{{ sessionId }}</code>
          <button class="btn btn-ghost btn-small" type="button" @click="resetSession">换一个 session_id</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <StatusBar :selected-count="0" :session-id="sessionId" />
          <section class="chat-messages">
            <p class="empty-hint">消息区与输入框在 Task 5 接入</p>
          </section>
        </div>
      </div>
    </main>

    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>
  </div>
</template>
```

`<StatusBar :selected-count="0">` 是 Task 3 的临时硬编码，Task 4 换成 `:selected-count="selectedIds.length"`。`panel-toggle` 放在 `.app-shell` 末尾是刻意的：CSS 里它 `display:none`，只有 ≤768px 那条断点把它显出来，栅格里 `align-self: start` 让它贴在右上角区域。

- [ ] **Step 9: 浏览器验证（dev server 在跑，终端 A）**

逐项核对，全过才算这个 Task 完成：

1. `http://localhost:5173/` 打开后是**左右两栏**：左窄（320px）右宽，右栏顶部是紫蓝渐变头部，写着"🤖 智能文档检索助手 / 基于知识库的智能问答系统"。
2. 头部下面那条状态栏显示紫色胶囊"💬 普通对话模式"，右侧显示 `session ` + 8 位十六进制；鼠标悬停 `title` 是完整 UUID。
3. Console 执行 `localStorage.getItem('session_id')`，返回值与侧栏 `session-value` 完全一致；`localStorage.length` 必须是 `1`（消息没有落本地）。
4. **按 F5 刷新，UUID 不变**（会话身份稳定）；点"换一个 session_id"，侧栏与状态栏的短显同步变化，Console 再查 `localStorage` 也是新值。
5. Console 执行 `localStorage.removeItem('session_id')` 后刷新：界面出现一个**新的** UUID，且 `localStorage.length` 回到 1。
6. DevTools → Console 零 error、零 warning（尤其不能出现 Vue 的 `Property "xxx" was accessed during render but is not defined`——那基本是忘了 `.value` 或没解构）。
7. DevTools 设备模拟宽度压到 768px 以下：变成单栏，出现"展开文档面板"按钮，点击可开合左栏（Task 7 再走完整响应式清单）。

- [ ] **Step 10: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/composables/useSession.js frontend/src/styles frontend/src/components/ChatHeader.vue frontend/src/components/StatusBar.vue frontend/src/main.js frontend/src/App.vue
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): session 组合式 + 手写样式三件套 + 两栏骨架"
```

---

## Task 4: `DocumentPanel` 家族 + `useDocuments` 串行上传队列

**Files:**
- Create: `frontend/src/composables/useDocuments.js`、`frontend/src/components/DocumentPanel.vue`、`frontend/src/components/FileUploader.vue`、`frontend/src/components/DocCard.vue`
- Modify: `frontend/src/App.vue`（左栏换成 `DocumentPanel`、接 `useDocuments`、`onMounted` 拉列表）、`frontend/src/styles/layout.css`（文件末尾追加"文档区"块）

**Interfaces:**
- Consumes: `listDocuments()` / `uploadDocument(file, {onProgress})`（Task 2）；`.btn` / `.panel-*` / `.side-panel-inner` 类（Task 3）。
- Produces:
  - `docLabel(doc) → string`（`{filename}(#{id})`，坑 5 的唯一出处；`DocCard.vue` 复用它，别再手写第二份格式）
  - `useDocuments() → { documents, selectedIds, queue, listError, docCount, refresh, toggleSelect, enqueue, retry, dismiss, docLabel }`
    - `documents: Ref<Array<{id, filename, chunk_count, created_at}>>`
    - `selectedIds: Ref<number[]>` —— Task 5 的 `sendChat` 直接把它当 `document_ids` 发出去
    - `queue: Ref<Array<{key, file, name, percent, status:'pending'|'uploading'|'ok'|'fail', error}>>`
    - `listError: Ref<string>`、`docCount: ComputedRef<number>`
    - `refresh(): Promise<void>`、`toggleSelect(id: number): void`、`enqueue(files: File[] | FileList): void`、`retry(item): void`、`dismiss(item): void`
  - 新增 CSS 类：`.doc-list` `.doc-card` `.doc-card-checked` `.doc-name` `.doc-meta` `.uploader` `.uploader-label` `.file-input` `.queue` `.queue-item` `.queue-ok` `.queue-fail` `.queue-head` `.queue-name` `.queue-state` `.queue-error` `.progress` `.progress-bar` `.metric`

- [ ] **Step 1: 写 `frontend/src/composables/useDocuments.js`**

```js
import { computed, ref } from 'vue'

import { listDocuments, uploadDocument } from '../api/documents.js'

const UPLOAD_STATUS = { pending: 'pending', uploading: 'uploading', ok: 'ok', fail: 'fail' }

// 坑 5：同名文档必须靠 id 区分，这个格式是界面上唯一的出处
export function docLabel(doc) {
  return `${doc.filename}(#${doc.id})`
}

export function useDocuments() {
  const documents = ref([])
  const selectedIds = ref([])
  const queue = ref([])
  const listError = ref('')
  let running = false

  const docCount = computed(() => documents.value.length)

  async function refresh() {
    try {
      documents.value = await listDocuments()
      listError.value = ''
      // 勾过的文档不在列表里了就要撤勾：留着会让 document_ids 带上后端不认的 id，问答直接 502
      const alive = new Set(documents.value.map((doc) => doc.id))
      selectedIds.value = selectedIds.value.filter((id) => alive.has(id))
    } catch (err) {
      listError.value = err.message
    }
  }

  function toggleSelect(id) {
    selectedIds.value = selectedIds.value.includes(id)
      ? selectedIds.value.filter((x) => x !== id)
      : [...selectedIds.value, id]
  }

  function enqueue(files) {
    const stamp = Date.now()
    queue.value.push(
      ...Array.from(files).map((file, index) => ({
        key: `${stamp}-${index}-${file.name}`,
        file,
        name: file.name,
        percent: 0,
        status: UPLOAD_STATUS.pending,
        error: '',
      })),
    )
    runQueue()
  }

  async function runQueue() {
    if (running) return
    running = true
    try {
      // 串行而不是 Promise.all：后端只有单文件端点（spec 6.2），
      // 并行会让 embedding 与 MySQL 写互相排队，进度条也会跳成乱序
      for (;;) {
        // 从 queue.value 里取到的是响应式代理，直接改字段就能推动进度条
        const item = queue.value.find((q) => q.status === UPLOAD_STATUS.pending)
        if (!item) break
        item.status = UPLOAD_STATUS.uploading
        item.percent = 0
        item.error = ''
        try {
          await uploadDocument(item.file, { onProgress: (percent) => { item.percent = percent } })
          item.percent = 100
          item.status = UPLOAD_STATUS.ok
          await refresh()
        } catch (err) {
          item.status = UPLOAD_STATUS.fail
          item.error = err.message
        }
      }
    } finally {
      running = false
    }
  }

  function retry(item) {
    item.status = UPLOAD_STATUS.pending
    item.percent = 0
    item.error = ''
    runQueue()
  }

  function dismiss(item) {
    queue.value = queue.value.filter((q) => q.key !== item.key)
  }

  return {
    documents,
    selectedIds,
    queue,
    listError,
    docCount,
    refresh,
    toggleSelect,
    enqueue,
    retry,
    dismiss,
    docLabel,
  }
}
```

四个状态里 `pending` 是"排队等前面传完"，`uploading` 是"正在传"；`ok` / `fail` 是终态，只有终态才允许"移除"，只有 `fail` 才允许"重试"。不做取消按钮：单文件请求几十 KB，取消的实际收益比它带来的状态机复杂度高。

- [ ] **Step 2: 写 `frontend/src/components/FileUploader.vue`**

```vue
<script setup>
import { ref } from 'vue'

const props = defineProps({
  queue: { type: Array, required: true },
})
const emit = defineEmits(['enqueue', 'retry', 'dismiss'])

// accept 的三种扩展名与后端 SUPPORTED_SUFFIXES 对齐（backend/core/document_processor.py:14）
const inputEl = ref(null)

function onPick(event) {
  const files = Array.from(event.target.files ?? [])
  if (files.length) emit('enqueue', files)
  // 不清空 value，连续两次选同一个文件不会触发 change，队列里就永远少一条
  event.target.value = ''
}

function stateText(item) {
  if (item.status === 'pending') return '排队中'
  if (item.status === 'uploading') return `上传中 ${item.percent}%`
  if (item.status === 'ok') return '✅ 成功'
  return '❌ 失败'
}
</script>

<template>
  <div class="uploader">
    <label class="btn btn-small uploader-label">
      📥 选择文档（可多选）
      <input
        ref="inputEl"
        class="file-input"
        type="file"
        multiple
        accept=".pdf,.docx,.txt"
        @change="onPick"
      />
    </label>
    <p class="panel-hint">支持 PDF、Word、txt；逐个上传，失败可单独重试。</p>

    <ul v-if="props.queue.length" class="queue">
      <li
        v-for="item in props.queue"
        :key="item.key"
        class="queue-item"
        :class="{ 'queue-ok': item.status === 'ok', 'queue-fail': item.status === 'fail' }"
      >
        <div class="queue-head">
          <span class="queue-name" :title="item.name">{{ item.name }}</span>
          <span class="queue-state">{{ stateText(item) }}</span>
          <button
            v-if="item.status === 'fail'"
            class="btn btn-ghost btn-small"
            type="button"
            @click="emit('retry', item)"
          >
            重试
          </button>
          <button
            v-if="item.status === 'ok' || item.status === 'fail'"
            class="btn btn-ghost btn-small"
            type="button"
            @click="emit('dismiss', item)"
          >
            移除
          </button>
        </div>
        <div v-if="item.status === 'uploading'" class="progress">
          <div class="progress-bar" :style="{ width: `${item.percent}%` }"></div>
        </div>
        <p v-if="item.error" class="queue-error">{{ item.error }}</p>
      </li>
    </ul>
  </div>
</template>
```

不在前端做后缀名二次校验：`accept` 只是过滤文件选择框的显示，真正的类型判定是后端 `load_document` 抛 415——两处都判就会有两套会漂移的规则（spec 八节的分层）。

- [ ] **Step 3: 写 `frontend/src/components/DocCard.vue`**

```vue
<script setup>
import { docLabel } from '../composables/useDocuments.js'

const props = defineProps({
  doc: { type: Object, required: true },
  checked: { type: Boolean, required: true },
})
const emit = defineEmits(['toggle'])

function formatTime(iso) {
  // 后端 datetime 不带时区，new Date 按本地时区解析——联调就在本机，够用
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
</script>

<template>
  <label class="doc-card" :class="{ 'doc-card-checked': props.checked }">
    <input type="checkbox" :checked="props.checked" @change="emit('toggle', props.doc.id)" />
    <span class="doc-name">📄 {{ docLabel(props.doc) }}</span>
    <span class="doc-meta">🕒 {{ formatTime(props.doc.created_at) }}</span>
    <span class="doc-meta">📊 {{ props.doc.chunk_count }} 个文档块</span>
  </label>
</template>
```

- [ ] **Step 4: 写 `frontend/src/components/DocumentPanel.vue`**

```vue
<script setup>
import DocCard from './DocCard.vue'
import FileUploader from './FileUploader.vue'

const props = defineProps({
  documents: { type: Array, required: true },
  selectedIds: { type: Array, required: true },
  queue: { type: Array, required: true },
  listError: { type: String, default: '' },
  docCount: { type: Number, required: true },
})
const emit = defineEmits(['enqueue', 'retry', 'dismiss', 'toggle'])
</script>

<template>
  <div class="side-panel-inner">
    <h2 class="panel-title">📁 文档管理</h2>
    <FileUploader
      :queue="props.queue"
      @enqueue="emit('enqueue', $event)"
      @retry="emit('retry', $event)"
      @dismiss="emit('dismiss', $event)"
    />

    <p v-if="props.listError" class="queue-error">📚 文档列表加载失败：{{ props.listError }}</p>

    <hr class="panel-hr" />
    <h2 class="panel-title">📚 知识库</h2>
    <p class="panel-hint">勾选后基于文档内容回答；一个都不勾就是普通对话。</p>

    <ul v-if="props.documents.length" class="doc-list">
      <li v-for="doc in props.documents" :key="doc.id">
        <DocCard
          :doc="doc"
          :checked="props.selectedIds.includes(doc.id)"
          @toggle="emit('toggle', $event)"
        />
      </li>
    </ul>
    <p v-else-if="!props.listError" class="panel-hint">暂无文档，请先上传</p>

    <div class="metric">📊 文档数 {{ props.docCount }}</div>
  </div>
</template>
```

"🗑️ 清空对话"按钮**不在这里**，Task 6 与它的 DELETE 调用一起加——那时才有人真能删历史。

- [ ] **Step 5: `layout.css` 末尾追加文档区**

```css
/* ---- 文档区（Task 4）：.doc-card 从 app.py 搬，margin/padding 的侧栏居中hack 改成随栏宽 ---- */
.doc-list { display: flex; flex-direction: column; gap: 8px; }
.doc-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  box-sizing: border-box;
  max-width: 100%;
  padding: 8px 12px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  cursor: pointer;
}
.doc-card:hover,
.doc-card-checked {
  border-color: var(--brand-1);
  box-shadow: var(--shadow-card-hover);
}
.doc-name { font-weight: 600; }
.doc-meta { font-size: 12px; color: var(--text-muted); }

.uploader { display: flex; flex-direction: column; gap: 8px; }
.uploader-label { display: inline-flex; align-items: center; justify-content: center; }
.file-input { display: none; }

.queue { display: flex; flex-direction: column; gap: 6px; }
.queue-item { padding: 6px 8px; background: #fff; border: 1px solid var(--border); border-radius: 6px; }
.queue-ok { border-color: var(--ok-fg); }
.queue-fail { background: var(--fail-bg); border-color: var(--fail-fg); }
.queue-head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.queue-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.queue-state { color: var(--text-muted); }
.queue-error { font-size: 12px; color: var(--fail-fg); }
.progress { height: 6px; margin-top: 6px; overflow: hidden; background: var(--page-bg); border-radius: 3px; }
.progress-bar { height: 100%; background: var(--grad-brand); transition: width 0.15s linear; }

.metric {
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 500;
  background: var(--page-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
}
```

- [ ] **Step 6: 把文档区接进 `App.vue`**

`frontend/src/App.vue` 整文件重写（`<style>` 依然没有；`.session-debug` 那块**留着**——Task 6/7 的手测要靠它核对 `localStorage`）：

```vue
<script setup>
import { onMounted, ref } from 'vue'

import ChatHeader from './components/ChatHeader.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import StatusBar from './components/StatusBar.vue'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 三个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, resetSession } = useSession()
const {
  documents,
  selectedIds,
  queue,
  listError,
  docCount,
  refresh,
  toggleSelect,
  enqueue,
  retry,
  dismiss,
} = useDocuments()

// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(refresh)
</script>

<template>
  <div class="app-shell" :class="{ 'panel-open': panelOpen }">
    <aside class="side-panel">
      <DocumentPanel
        :documents="documents"
        :selected-ids="selectedIds"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @toggle="toggleSelect"
      />
      <div class="side-panel-inner">
        <hr class="panel-hr" />
        <div class="session-debug">
          <span>当前 session_id</span>
          <code class="session-value">{{ sessionId }}</code>
          <button class="btn btn-ghost btn-small" type="button" @click="resetSession">换一个 session_id</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <StatusBar :selected-count="selectedIds.length" :session-id="sessionId" />
          <section class="chat-messages">
            <p class="empty-hint">消息区与输入框在 Task 5 接入</p>
          </section>
        </div>
      </div>
    </main>

    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>
  </div>
</template>
```

`.side-panel` 现在是 `DocumentPanel` + 一个 `.side-panel-inner` 调试块两段并列；`.side-panel` 本身已有 `overflow-y: auto`，文档多了可以滚。

- [ ] **Step 7: 准备手测文件（放在 Git Bash 的 `/tmp`，不进仓库）**

```bash
mkdir -p /tmp/kb-files
printf '甲公司的营收是 100 元。\n\n乙公司的成本是 40 元。' > /tmp/kb-files/comp.txt
printf '知识库平台使用父子分块检索，子块召回后回溯父块。' > /tmp/kb-files/rag.txt
printf '第三份占位文档，只用来验串行上传队列。' > /tmp/kb-files/third.txt
printf '' > /tmp/kb-files/empty.txt
ls -l /tmp/kb-files
```

Chrome 的文件选择框里把路径粘成 `%LOCALAPPDATA%\Temp\kb-files`（Git Bash 的 `/tmp` 就映射到那里）。

- [ ] **Step 8: 浏览器验证**

1. 左栏出现"📁 文档管理"和"📥 选择文档（可多选）"；"📚 知识库"下列出基线那 1 份文档，卡片文案形如 `📄 恢复流程评估文件.docx(#1)`，下方两行小字是时间与块数；最底部 `📊 文档数 1`。
2. 勾选它 → 顶部状态栏从紫色胶囊变成蓝色"🔍 知识库模式（1 个文档）"；取消勾选 → 变回"💬 普通对话模式"。
3. 选 `/tmp/kb-files/comp.txt` → 队列出现一行"上传中 x%"，进度条从 0 走到 100 → 变成"✅ 成功"；`comp.txt(#2)` **自动出现在知识库里**（`refresh()` 生效），文档数变 2，卡片时间显示的是**刚刚**而不是后端进程启动时刻（spec 十节判据 2 的前半，验坑 1）。
4. 一次选 `comp.txt + rag.txt + third.txt` 三份 → 队列三行，状态**依次**变 ok；DevTools → Network 里三个 `POST /api/documents` 是**串行**发出（前一个 201 之后下一个才 pending 转 active），不是三条并发。
5. 选 `empty.txt` → 那一行红底"❌ 失败"，下面小字是 `文件内容为空`（后端 422 的 `detail` 原文）；点"重试"再点一次 → 仍失败，说明重试真的重新发了请求（Network 里多一条）。点"移除" → 该行消失，其它行不受影响。
6. 后端停掉（终端 C Ctrl-C）再选一个正常文件 → 该行走 `xhr.onerror`，文案是 `无法连接后端，上传中断`；文档列表区同时出现 `📚 文档列表加载失败：无法连接后端，请确认 uvicorn 已在 :8000 运行`。重启后端后刷新页面 → 错误消失、列表回来。
7. Console 里 `document.querySelectorAll('.doc-card').length` 与"📊 文档数"数字相等；Console 零 error / 零 Vue warning。

做完 3～4 之后，MySQL 里会多出 3～4 份 `documents` 行（本计划不清理：后端不做删除接口，坑 10）。**这是预期的基线漂移**——Task 7 的全量清单里"文档数"按当时实际值看，不要拿后端计划里的 `documents 1` 当判据。

- [ ] **Step 9: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/composables/useDocuments.js frontend/src/components/DocumentPanel.vue frontend/src/components/FileUploader.vue frontend/src/components/DocCard.vue frontend/src/App.vue frontend/src/styles/layout.css
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 文档面板家族与串行上传队列（进度/失败/重试）"
```

---

## Task 5: Chat 家族 + `typewriter` + `useChat`

**Files:**
- Create: `frontend/src/utils/typewriter.js`、`frontend/src/composables/useChat.js`、`frontend/src/components/MessageList.vue`、`frontend/src/components/MessageBubble.vue`、`frontend/src/components/ReferenceList.vue`、`frontend/src/components/ChatInput.vue`
- Modify: `frontend/src/App.vue`（接 `useChat`、错误条、输入框）、`frontend/src/styles/layout.css`（文件末尾追加"消息区"块）

**Interfaces:**
- Consumes: `sendChat`（Task 2）、`getHistory` / `clearHistory`（Task 2，`clear` 在 Task 6 用到）、`selectedIds`（Task 4）、`.streaming-cursor` / `.pre-wrap` / `.error-banner`（Task 3）。`.empty-hint` 在本 Task 之后不再被任何模板引用（欢迎态改由 `MessageList` 的气泡承担），但 `layout.css` 里那两行**留着不删**：删它会让 Task 3 抄下来的 CSS 与本文其他段落对不上。
- Produces:
  - `tokenize(text: string) → string[]`；`startTypewriter(text, { onUpdate(partial, done), onDone(), interval = 20 }) → { stop() }`
  - `useChat() → { messages, pending, error, restore, send, clear, finishTyping }`
    - `messages: Ref<Array<{key, role:'user'|'assistant', content, references: Array<Reference>, mode?: 'rag'|'normal', streaming: boolean, fullText?: string}>>`
    - `pending: Ref<boolean>`（**只覆盖网络往返**，打字机放字期间为 false，输入框可用）
    - `error: Ref<string>`
    - `restore(sessionId): Promise<boolean>`、`send({session_id, question, document_ids}): Promise<boolean>`、`clear(sessionId): Promise<boolean>`（Task 6 用）、`finishTyping(): void`（只被 `send`/`clear` 内部调用，`App.vue` 不解构它）
  - 新增 CSS 类：`.bubble-text` `.bubble-meta` `.reference-list` `.reference-item` `.reference-source` `.reference-snippet` `.chat-input` `.chat-textarea`，并给 `.chat-messages` 补 `display:flex; flex-direction:column; gap:16px`。
  - **`mode` 落点**：后端 `mode` 驱动答案气泡上的来源标签（`📚 知识库检索` / `💬 自由对话`）；顶部 `StatusBar` 仍是"勾选即 RAG"的**意图**标签（与 app.py 一致）。后端只看 `document_ids` 是否为空来决定 `mode`（`api/chat.py` 实测如此），所以两者只可能在"请求飞行中改了勾选"时短暂不一致，此时以气泡上的 `mode` 为准，正好能把"后端实际走了哪条链"暴露出来。反过来不成立：空检索仍是 `mode: "rag"` + `references: []`，**别拿引用区有没有渲染去判模式**。

- [ ] **Step 1: 写 `frontend/src/utils/typewriter.js`**

```js
// 阶段一后端 POST /api/chat 一次性返回整段答案，逐字效果是前端本地模拟的。
// spec 十一节第 8 步：SSE 落地当天整个文件删除——不能两套逐字逻辑并存。

// 与 app.py 的 re.findall(r"[A-Za-z0-9]+|\s+|.") 等价：英文数字按词、空白按段、其余按字。
// 两边的 "." 都不匹配换行，换行统一被 \s+ 收走，所以中文按字、换行不会被切碎。
const TOKEN_RE = /[A-Za-z0-9]+|\s+|./g

export function tokenize(text) {
  return text?.match(TOKEN_RE) ?? []
}

export function startTypewriter(text, { onUpdate, onDone, interval = 20 }) {
  const tokens = tokenize(text)
  let index = 0
  let timer = null
  let stopped = false

  function schedule() {
    if (stopped) return
    if (index >= tokens.length) {
      onUpdate(text, true)
      onDone?.()
      return
    }
    // 空白 token 不单独停顿（同 app.py 的 if token.strip()），否则一串空格能把节奏拖死
    const delay = tokens[index].trim() ? interval : 0
    timer = setTimeout(() => {
      index += 1
      onUpdate(tokens.slice(0, index).join(''), index >= tokens.length)
      schedule()
    }, delay)
  }

  schedule()

  return {
    // 开新一轮、清空对话、组件卸载都必须 stop：否则旧答案会继续往新气泡里吐字
    stop() {
      stopped = true
      if (timer) clearTimeout(timer)
    },
  }
}
```

`interval = 20` 对齐 `app.py` 的 `time.sleep(0.02)`。中文按字切，500 字要放 10 秒——所以本 Task 特意把 `pending` 只绑在网络往返上（见 Step 2），放字期间输入框不锁。

- [ ] **Step 2: 写 `frontend/src/composables/useChat.js`**

```js
import { ref } from 'vue'

import { sendChat } from '../api/chat.js'
import { clearHistory, getHistory } from '../api/history.js'
import { startTypewriter } from '../utils/typewriter.js'

let seq = 0

// v-for 的 key 只求稳定唯一，自增比 randomUUID 省事，刷新后按历史重建也不会撞
function nextKey() {
  seq += 1
  return `m${seq}`
}

export function useChat() {
  const messages = ref([])
  const pending = ref(false)
  const error = ref('')
  let typer = null
  let typingBubble = null

  function finishTyping() {
    if (typer) {
      typer.stop()
      typer = null
    }
    if (typingBubble) {
      // 直接补全成整段：中途开新一轮时宁可"字一下全出来"，也不留一条永远残缺的答案
      typingBubble.content = typingBubble.fullText
      typingBubble.streaming = false
      typingBubble = null
    }
  }

  async function restore(sessionId) {
    finishTyping()
    try {
      // 后端已把一行 DB 展开成 user + assistant 两条，形状与实时发送一致（spec 6.2 第 3 条），
      // 所以这里不需要区分"来自历史"和"来自本次会话"
      const rows = await getHistory(sessionId)
      messages.value = rows.map((row) => ({
        key: nextKey(),
        role: row.role,
        content: row.content,
        references: row.references ?? [],
        streaming: false,
      }))
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  async function send({ session_id, question, document_ids }) {
    if (pending.value || !question.trim()) return false
    error.value = ''
    finishTyping()
    pending.value = true

    messages.value.push({ key: nextKey(), role: 'user', content: question, references: [], streaming: false })
    messages.value.push({ key: nextKey(), role: 'assistant', content: '', references: [], streaming: true, fullText: '' })
    // 必须 push 完再按下标取回：拿到的是响应式代理，改它的字段才推动视图；
    // 改 push 之前那个原始对象，数据变了但界面不动。
    const bubble = messages.value[messages.value.length - 1]

    try {
      const resp = await sendChat({ session_id, question, document_ids })
      bubble.mode = resp.mode
      bubble.references = resp.references ?? []
      bubble.fullText = resp.answer
      typer = startTypewriter(resp.answer, {
        onUpdate: (partial) => {
          bubble.content = partial
        },
        onDone: () => {
          bubble.streaming = false
          typer = null
          typingBubble = null
        },
      })
      typingBubble = bubble
      return true
    } catch (err) {
      // 后端 502 时不写历史（spec 七节"新增"那条）。本地这两条也必须一起撤掉：
      // 界面消息比后端历史多，刷新就会"消息蒸发"，比报错更难查。
      messages.value.splice(messages.value.length - 2, 2)
      error.value = err.message
      return false
    } finally {
      pending.value = false
    }
  }

  async function clear(sessionId) {
    try {
      // 先确认后端删掉了再动本地：本地清空而后端没删，刷新会把历史原样冲回来
      await clearHistory(sessionId)
      finishTyping()
      messages.value = []
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  return { messages, pending, error, restore, send, clear, finishTyping }
}
```

不需要 `reactive()` 包装那个气泡对象：`messages` 是 `ref([])`，Vue 会把它里面的对象深度转成响应式，`messages.value[len-1]` 取回来的**已经是代理**，改字段就能推动视图；`reactive` 在这个文件里没有别的用处，所以只 import `ref`。

- [ ] **Step 3: 写 `frontend/src/components/ReferenceList.vue`**

```vue
<script setup>
const props = defineProps({
  references: { type: Array, required: true },
})
</script>

<template>
  <ul class="reference-list">
    <li
      v-for="(reference, i) in props.references"
      :key="`${reference.document_id}-${reference.parent_id}-${i}`"
      class="reference-item"
    >
      <span class="reference-source">📎 {{ reference.filename }}(#{{ reference.document_id }})</span>
      <span class="reference-snippet pre-wrap">{{ reference.snippet }}</span>
    </li>
  </ul>
</template>
```

`snippet` 已由后端截到 83 字符（`SNIPPET_LIMIT = 80` + `"..."`），前端**不再二次截断**——两处截断的语义会漂。`parent_id` 只做 key 的一部分，不显示：它对用户没有信息量，且长度能到 100（坑 8）。

- [ ] **Step 4: 写 `frontend/src/components/MessageBubble.vue`**

```vue
<script setup>
import ReferenceList from './ReferenceList.vue'

const props = defineProps({
  message: { type: Object, required: true },
})
</script>

<template>
  <div class="message" :class="{ user: props.message.role === 'user' }">
    <div
      class="message-avatar"
      :class="props.message.role === 'user' ? 'user-avatar' : 'assistant-avatar'"
    >
      {{ props.message.role === 'user' ? '👤' : '🤖' }}
    </div>
    <div
      class="message-content"
      :class="props.message.role === 'user' ? 'user-message' : 'assistant-message'"
    >
      <span
        class="bubble-text pre-wrap"
        :class="{ 'streaming-cursor': props.message.streaming }"
        >{{ props.message.content }}</span>
      <p v-if="props.message.mode" class="bubble-meta">
        {{ props.message.mode === 'rag' ? '📚 知识库检索' : '💬 自由对话' }}
      </p>
      <ReferenceList v-if="props.message.references?.length" :references="props.message.references" />
    </div>
  </div>
</template>
```

`{{ props.message.content }}` 外面那对尖括号是 Vue 模板里的普通文本插值，**没有** `v-html`——文档正文里出现 `<script>alert(1)</script>` 也只是字符（spec 七节 坑 6 的落点）。

- [ ] **Step 5: 写 `frontend/src/components/MessageList.vue`**

```vue
<script setup>
import { computed, nextTick, ref, watch } from 'vue'

import MessageBubble from './MessageBubble.vue'

const props = defineProps({
  messages: { type: Array, required: true },
  hasDocuments: { type: Boolean, required: true },
})

const listEl = ref(null)

// 用数组 join 而不是模板里的多行文本：Vue 模板默认 condense 空白，
// 写在模板里的换行会被压成一行。
const welcomeText = computed(() =>
  [
    '👋 你好！我是你的 AI 智能助手。',
    '',
    '💡 我能做什么：',
    '• 📚 基于你上传的文档回答问题',
    '• 💬 进行日常对话交流',
    '• 🔍 提供准确的信息检索',
    '',
    props.hasDocuments ? '勾选左侧文档，或直接开始对话吧！' : '请先在左侧上传文档，或直接开始对话吧！',
  ].join('\n'),
)

// 打字机每 20ms 改一次最后一条的 content，所以 watch 的是"长度"而不只是条数，
// 否则气泡会长出视口外而页面不跟到底部。
watch(
  () => [props.messages.length, props.messages.at(-1)?.content.length ?? 0],
  async () => {
    await nextTick()
    const el = listEl.value
    if (el) el.scrollTop = el.scrollHeight
  },
)
</script>

<template>
  <section ref="listEl" class="chat-messages">
    <div v-if="!props.messages.length" class="message">
      <div class="message-avatar assistant-avatar">🤖</div>
      <div class="message-content assistant-message">
        <span class="bubble-text pre-wrap">{{ welcomeText }}</span>
      </div>
    </div>

    <MessageBubble v-for="message in props.messages" :key="message.key" :message="message" />
  </section>
</template>
```

- [ ] **Step 6: 写 `frontend/src/components/ChatInput.vue`**

```vue
<script setup>
const props = defineProps({
  modelValue: { type: String, required: true },
  pending: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'send'])

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function submit() {
  if (props.pending || !props.modelValue.trim()) return
  emit('send', props.modelValue.trim())
}

function onKeydown(event) {
  // 原 st.chat_input 就是回车发送；Shift+Enter 留给人工换行
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      class="chat-textarea"
      rows="2"
      placeholder="💬 输入你的问题…"
      :value="props.modelValue"
      :disabled="props.pending"
      @input="onInput"
      @keydown="onKeydown"
    ></textarea>
    <button class="btn" type="button" :disabled="props.pending || !props.modelValue.trim()" @click="submit">
      {{ props.pending ? '🤔 思考中…' : '发送' }}
    </button>
  </div>
</template>
```

`modelValue` + `update:modelValue` 的命名让 `App.vue` 可以直接 `v-model="question"`。输入文本的所有权在 App（Task 6 的"失败还词"和"清空对话后复位"都要碰它），组件只搬运。

- [ ] **Step 7: `layout.css` 末尾追加消息区**

```css
/* ---- 消息区（Task 5）：.message 家族与两种气泡配色从 app.py 原样搬 ---- */
.chat-messages { display: flex; flex-direction: column; gap: 16px; }
.message { display: flex; align-items: flex-start; gap: 12px; }
.message.user { flex-direction: row-reverse; }
.message-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 18px;
}
.user-avatar { background: var(--grad-brand-135); color: #fff; }
.assistant-avatar { background: var(--grad-assistant-avatar); color: #fff; }
.message-content {
  max-width: 70%;
  padding: 12px 16px;
  border-radius: var(--radius-bubble);
  font-size: 14px;
  line-height: 1.4;
}
.user-message {
  background: var(--bubble-user);
  color: var(--bubble-user-fg);
  border-bottom-right-radius: 4px;
}
.assistant-message {
  background: var(--bubble-assistant);
  color: var(--bubble-assistant-fg);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  box-shadow: var(--shadow-bubble);
}
.bubble-text { display: block; }
.bubble-meta { margin-top: 6px; font-size: 11px; opacity: 0.7; }

.reference-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}
.reference-item { display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: var(--text-muted); }
.reference-source { font-weight: 600; }

.chat-input {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 20px;
  background: #fff;
  border-top: 1px solid var(--border);
}
.chat-textarea {
  flex: 1;
  min-height: 44px;
  max-height: 160px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  resize: vertical;
}
.chat-textarea:focus { outline: 2px solid rgba(102, 126, 234, 0.35); border-color: var(--brand-1); }
.chat-textarea:disabled { opacity: 0.6; }

@media (max-width: 768px) {
  /* app.py 断点里唯一还有意义的规则 */
  .message-content { max-width: 85%; }
}
```

- [ ] **Step 8: 在 `App.vue` 接上 Chat 家族**

`frontend/src/App.vue` 整文件重写。`<script setup>` 部分：

```vue
<script setup>
import { onMounted, ref } from 'vue'

import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import MessageList from './components/MessageList.vue'
import StatusBar from './components/StatusBar.vue'
import { useChat } from './composables/useChat.js'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 三个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, resetSession } = useSession()
const {
  documents, selectedIds, queue, listError, docCount,
  refresh, toggleSelect, enqueue, retry, dismiss,
} = useDocuments()
const { messages, pending, error, restore, send } = useChat()

const question = ref('')
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(async () => {
  await refresh()
  await restore(sessionId.value)
})

async function handleSend() {
  const text = question.value.trim()
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text, document_ids: selectedIds.value })
  // 后端失败时不写历史，本地那两条也已经撤掉；把问题还给输入框，别让用户重打
  if (!ok) question.value = text
}

function dismissError() {
  error.value = ''
}
</script>
```

`<template>` 部分（`.chat-body` 里的内容整块替换）：

```html
<template>
  <div class="app-shell" :class="{ 'panel-open': panelOpen }">
    <aside class="side-panel">
      <DocumentPanel
        :documents="documents"
        :selected-ids="selectedIds"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @toggle="toggleSelect"
      />
      <div class="side-panel-inner">
        <hr class="panel-hr" />
        <div class="session-debug">
          <span>当前 session_id</span>
          <code class="session-value">{{ sessionId }}</code>
          <button class="btn btn-ghost btn-small" type="button" @click="resetSession">换一个 session_id</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <StatusBar :selected-count="selectedIds.length" :session-id="sessionId" />
          <p v-if="error" class="error-banner">
            <span>⚠️ {{ error }}</span>
            <button class="btn btn-ghost btn-small" type="button" @click="dismissError">关闭</button>
          </p>
          <MessageList :messages="messages" :has-documents="documents.length > 0" />
          <ChatInput v-model="question" :pending="pending" @send="handleSend" />
        </div>
      </div>
    </main>

    <button class="btn btn-ghost btn-small panel-toggle" type="button" @click="panelOpen = !panelOpen">
      {{ panelOpen ? '收起文档面板' : '展开文档面板' }}
    </button>
  </div>
</template>
```

模板里 `panelOpen = !panelOpen` 这种赋值是合法的：`<script setup>` 的顶层 ref 绑定，Vue 编译器会翻成 `.value` 赋值；`error.value` 那种需要显式 `.value` 的写法只在 **script** 里用（模板自动解包）。

- [ ] **Step 9: 静态把关——`v-html` 必须为零（坑 6）**

```bash
cd "D:/知识库平台-前后端分离/frontend" && grep -rn "v-html\|innerHTML" src/ ; echo "grep 退出码 $?"
```

预期：**没有任何匹配行**，`grep 退出码 1`。出现匹配就改掉再往下走，别"先跑通再说"。

- [ ] **Step 10: 浏览器验证**

先补一份注入面测试文档（Task 7 的判据 6 会复用）：

```bash
printf '安全测试片段：<script>alert(1)</script> 与 <img src=x onerror=alert(2)>。' > /tmp/kb-files/xss.txt
```

1. 刷新页面：消息区显示 **🤖 欢迎气泡**（头像在左、白底、多行文本带换行与项目符号），底部输入框 placeholder 是 `💬 输入你的问题…`，"发送"按钮为禁用态。
2. **不勾任何文档**，输入 `你好，你能做什么？` 回车：右侧紫蓝渐变 user 气泡立刻出现（`flex-direction: row-reverse`，头像在右），按钮变 `🤔 思考中…`；DevTools → Network 看到**只有一个** `POST /api/chat`，响应 `mode:"normal"`、`references:[]`；响应回来后白底气泡**逐字**长出文字，末尾 `▌` 以 1 秒周期闪烁（验 `@keyframes blink` 搬对了），结束后光标消失，气泡下方小字 `💬 自由对话`。
3. 勾 `comp.txt`（状态栏变蓝 `🔍 知识库模式（1 个文档）`），问 `甲公司的营收是多少？`：答案文本里出现 `100 元`；气泡下方先出现 `📚 知识库检索` 与 **引用区**（`📎 comp.txt(#2)` + 一行片段，末尾可能是 `...`），引用在字还在放的时候就已经在——这正是阶段二 SSE 的渲染前提。
4. 打字还没放完就输入下一句并回车：输入框可用（`pending` 已随响应结束）、上一轮气泡**立刻补全成完整答案**（`finishTyping()` 生效），不会出现半截答案，也不会有两个定时器同时在放字（Network 里第二轮请求正常发出）。
5. 勾 `xss.txt` 问 `尖括号里包着什么？`：引用片段把 `<script>alert(1)</script>` 当**纯文本**显示出来，页面无弹窗、Console 无 `alert` 执行痕迹；`document.querySelectorAll('script').length` 仍只有 Vite 注入的那几个模块脚本。
6. 检索不到不是错误：勾 `third.txt`（内容只有一句占位文本）问 `甲公司的营收是多少？` → **不出现红色错误条**。具体文案两种都算通过：后端 `parent_docs` 为空时返回 `未在选中的文档里找到相关内容，请换个问法或确认文档已上传。`（`backend/core/rag_system.py:67-69`，200 业务结果）；或检索命中了无关块、LLM 按 system prompt 诚实说"上下文里没有相关信息"。区别只在引用区有无，界面都不该报错。
7. 后端停掉（终端 C Ctrl-C）再问一句 → 红色错误条 `⚠️ 无法连接后端，请确认 uvicorn 已在 :8000 运行`，**消息列表里既不留半截 assistant 气泡、也不留那句 user 气泡**（`splice` 撤掉两条），输入框里的原文还给你（`handleSend` 的 `if (!ok)`）。重启后端后刷新，界面与历史都对得上。
8. 点"关闭"能收掉错误条；Console 零 error / 零 Vue warning。

- [ ] **Step 11: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/utils/typewriter.js frontend/src/composables/useChat.js frontend/src/components/MessageList.vue frontend/src/components/MessageBubble.vue frontend/src/components/ReferenceList.vue frontend/src/components/ChatInput.vue frontend/src/App.vue frontend/src/styles/layout.css
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 对话家族 + 本地打字机，引用与 mode 上屏"
```

---

## Task 6: 历史恢复 + 清空对话 + 刷新等价

**Files:**
- Modify: `frontend/src/components/DocumentPanel.vue`（加"🗑️ 清空对话"按钮与 `clearing` prop）、`frontend/src/App.vue`（`handleClear` + `watch(sessionId)` 重新拉历史）

**Interfaces:**
- Consumes: `useChat()` 的 `restore/clear`（Task 5）、`useSession()` 的 `resetSession`（Task 3）、`.error-banner`/`.btn`（Task 3）。
- Produces:
  - `DocumentPanel` 新增 prop `clearing: Boolean`、新增 emit `clear`
  - `App.vue` 新增 `handleClear()` 与 `watch(sessionId, restore)`：任何换 session 的入口（调试按钮、清空对话）都会自动重拉历史，界面不会继续挂着上一个 session 的消息
  - 行为契约：**清空 = `DELETE /api/history/{旧 id}` 成功之后才 `resetSession()`**；失败只报错，本地消息与 session_id 都不动

- [ ] **Step 1: `DocumentPanel.vue` 加清空按钮**

`<script setup>` 里的 `defineProps` 增一项、`defineEmits` 增一个事件（改后的两行原文）：

```js
const props = defineProps({
  documents: { type: Array, required: true },
  selectedIds: { type: Array, required: true },
  queue: { type: Array, required: true },
  listError: { type: String, default: '' },
  docCount: { type: Number, required: true },
  clearing: { type: Boolean, default: false },
})
const emit = defineEmits(['enqueue', 'retry', 'dismiss', 'toggle', 'clear'])
```

模板里紧挨着 `.metric` 那行之后追加（`🗑️ 清空对话` 与 app.py 侧栏那颗按钮位置等价）：

```html
    <div class="metric">📊 文档数 {{ props.docCount }}</div>
    <button class="btn" type="button" :disabled="props.clearing" @click="emit('clear')">
      {{ props.clearing ? '清空中…' : '🗑️ 清空对话' }}
    </button>
```

- [ ] **Step 2: `App.vue` 接清空与会话切换**

`<script setup>` 需要新增/改动的部分（`watch` 记得加进 `vue` 的 import 行，变成 `import { onMounted, ref, watch } from 'vue'`；`useChat()` 的解构里补上 `clear`）：

```js
const { messages, pending, error, restore, send, clear } = useChat()

const question = ref('')
const clearing = ref(false)
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

onMounted(async () => {
  await refresh()
  await restore(sessionId.value)
})

// session_id 一变就重拉历史：调试按钮和"清空对话"都会改它，
// 不 watch 的话界面会继续挂着上一个 session 的消息，看起来像"换 id 没生效"。
watch(sessionId, (next) => restore(next))

async function handleClear() {
  // 没有 UI 库可借，destructive 操作用原生 confirm：误点一次就再也找不回来
  if (!window.confirm('确认清空当前会话的全部消息？会删除后端保存的历史，不可恢复。')) return
  clearing.value = true
  const ok = await clear(sessionId.value)
  if (ok) {
    // 与 app.py 的行为等价：清空后换一个新的 session_id（旧 id 已被 DELETE 清空）
    resetSession()
    question.value = ''
  }
  clearing.value = false
}
```

模板里给 `DocumentPanel` 补两个绑定（其余不动）：

```html
      <DocumentPanel
        :documents="documents"
        :selected-ids="selectedIds"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        :clearing="clearing"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @toggle="toggleSelect"
        @clear="handleClear"
      />
```

`resetSession()` 会触发上面那个 `watch` → 对新 id 再发一次 `GET /api/history/{新 id}`，返回 `[]` → `messages` 保持空。多发一个请求换"界面永远等于后端真相"，这笔买卖划算，别去优化它。

- [ ] **Step 3: 已知边界，写清楚不隐藏**

- `getHistory` 用后端默认 `limit=50`（一轮 = 一条 `chat_history` 行 = 界面两条消息），后端取的是**最近** 50 轮再正序返回（`backend/core/database.py:224` 的 `order_by(id.desc()).limit()` + `reversed`）。所以超长寿会话刷新后只会看到最近 50 轮，更早的不在界面上。本次不做分页/加载更多（spec 一节的非目标）。
- 改造前就写进 `chat_history` 的老行 `used_chunks` 是 `NULL`：后端 Task 8 把它们降级成 `references: []`，所以这些历史**能恢复但没有引用区**。要实测这条路径，就把 `localStorage.session_id` 手工改成一个旧会话 id（`SELECT DISTINCT session_id FROM chat_history;` 任取一条）再刷新——预期是消息照常显示、引用区不出现、页面不报错。
- 后端 `api/history.py` 已落地并通过评审；本 Task 描述的形状（每行 → user+assistant 两条、user 行 `references: null`、assistant 行数组）即其实测行为，若再发现不符，以后端为准并回改 `api/history.js` 的注释。
- 刷新后恢复出来的 assistant 气泡**没有来源标签**：后端 `HistoryMessage` 只暴露 `role/content/references/created_at`，不带 `mode`，连 `document_ids` 都没露出来（`backend/schemas/chat.py`）。于是 `MessageBubble` 的 `v-if="props.message.mode"` 不成立，`📚 知识库检索` / `💬 自由对话` 那一行在刷新后消失，但引用区照常显示——这是预期行为，不是 bug，验证时别当失败报。也别想用"有没有引用区"去反推 `mode`：空检索时后端仍返回 `mode: "rag"` 且 `references: []`（`backend/core/rag_system.py:67-69` 那条说明文案），引用有无和走没走 RAG 链是两件事。真要在刷新后也显示来源标签，就得给后端 `chat_history` 加 `mode` 列并扩 `HistoryMessage` 字段——那是后端的活，本计划不做。

- [ ] **Step 4: 浏览器验证（spec 十节判据 4 的前端一半）**

1. 先攒两轮对话（一轮勾文档、一轮不勾），记下左侧 `session_id`，然后 **F5 刷新**：消息按原顺序全部回来，勾文档那轮的 assistant 气泡下方 **引用区也在**（`📎 comp.txt(#2)` + 片段），说明 `used_chunks` 真的写进去并读得出来。DevTools → Network 里刷新后只有两个请求：`GET /api/documents`、`GET /api/history/{当前 id}?limit=50`（没有第三个请求、没有任何本地缓存读取）。
2. 逐字对比引用：终端里 `curl -s "http://127.0.0.1:8000/api/history/<当前 id>?limit=50"`，把某条 assistant 的 `references[0].snippet` 与界面文本对照，**必须逐字相同**（含末尾的 `...`）。
3. 刷新前后 `session_id` 不变，且 `localStorage.length` 仍是 `1`（只有 `session_id` 一个键——消息没落本地）。
4. 点"🗑️ 清空对话"，弹出原生确认框 → 点**取消**：消息一条不少，Network 里**没有** `DELETE` 请求。
5. 再点"🗑️ 清空对话" → 确定：Network 里 `DELETE /api/history/{旧 id}` 返回 `{"cleared":2}`；消息区立刻变成欢迎气泡；左侧 `session_id` 与状态栏短显**同步换成新 UUID**；紧随其后一条 `GET /api/history/{新 id}` 返回 `[]`；按钮在请求期间显示"清空中…"且不可再点。
6. 清空后再 F5：仍然是欢迎气泡（证明后端确实删了，不是本地假清空）。终端 `curl -s http://127.0.0.1:8000/api/history/<旧 id>` 应返回 `[]`。
7. 手工回滚会话（验"后端是唯一真相"）：Console 执行 `localStorage.setItem('session_id', '<第 5 步之前的旧 id>')` 然后刷新 → 因为第 6 步已把旧会话删干净，界面是空的；于是**换一种做法**：在第 5 步之前先把旧 id 抄下来，第 5 步之后再在第 7 步用**另一个还有历史的 id**（比如第 1 步那个）改回去刷新，看到旧对话连同引用完整回来。这一条过了才算"消息不存本地"是真的。
8. 错误路径：把后端停掉 → 点"清空对话"并确定 → 红色错误条 `⚠️ 无法连接后端，请确认 uvicorn 已在 :8000 运行`，**消息一条没少、`session_id` 没变**（`clear()` 返回 false 才不换 id）。重启后端后刷新，历史原样。
9. Console 零 error / 零 Vue warning。

- [ ] **Step 5: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/components/DocumentPanel.vue frontend/src/App.vue
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 历史恢复与会话切换，清空对话走 DELETE 后再换 id"
```

---

## Task 7: 响应式折叠 + 静态把关 + 生产构建冒烟 + 全量手测清单

**Files:**
- Modify: 只允许在本 Task 的核对中**顺手修掉**发现的问题（改哪个文件就 `git add` 哪个），不新增文件
- Verify: `frontend/src/styles/layout.css` 的断点块、`frontend/package.json` 的 `build` 脚本

**Interfaces:**
- Consumes: Task 1–6 的全部产物。
- Produces: 阶段一前端的验收结论（写进提交信息，不另开文档）。

- [ ] **Step 1: 响应式与折叠核对（DevTools → 设备模拟，三个宽度各走一遍）**

| 宽度 | 预期 |
|---|---|
| 1440 | 两栏：左 320px + 右自适应；`.panel-toggle` **不显示**；气泡 `max-width: 70%`；文档卡片随栏宽，不溢出 |
| 900 | 同上，右栏变窄但 `minmax(0, 1fr)` 保证不被长文本撑破（引用片段一行不断栏外）|
| 375 | 单栏；顶部出现"展开文档面板"按钮；默认左栏隐藏 → 点一下展开（`position: sticky; top: 10px; max-height: 70vh`，可滚）、再点收起；气泡 `max-width: 85%`（app.py 那条断点规则）；输入框与发送按钮不换行重叠 |

375 宽度下额外验两条：① 展开左栏后上传队列的长文件名被 `.queue-name` 省略号截断（不撑破容器）；② 收起左栏后消息区能正常滚动到底。

- [ ] **Step 2: 三条静态把关命令（全部必须"没有匹配"）**

```bash
cd "D:/知识库平台-前后端分离/frontend"
grep -rn "v-html\|innerHTML" src/ ; echo "1) 退出码 $?"
grep -rn "127.0.0.1:8000\|localhost:8000" src/ ; echo "2) 退出码 $?"
grep -rn "from 'typescript'\|lang=\"ts\"" src/ ; echo "3) 退出码 $?"
```

预期三行都打印 `退出码 1`：① 坑 6 的注入面为零；② 所有请求都是相对 `/api/...`，后端地址只出现在 `vite.config.js`（不在 `src/`）；③ 没有 TS 残留。
再补一条人眼核对：`grep -c "<style>" src/components/*.vue src/App.vue` 全部为 `0`（样式只在三件套里）。

- [ ] **Step 3: 生产构建冒烟**

```bash
cd "D:/知识库平台-前后端分离/frontend" && npm run build && ls -la dist && grep -rn "v-html" dist/assets || echo "dist 里没有 v-html 痕迹"
```

预期：`vite build` 零 error 零 warning，产出 `dist/index.html` + `dist/assets/*.js` + `dist/assets/*.css`；`dist/` 不出现在 `git status` 里（被 `.gitignore` 拦住）。

```bash
cd "D:/知识库平台-前后端分离/frontend" && npm run preview
```

浏览器开 `http://localhost:4173/`（Vite preview 默认端口）：界面与 dev 一致。Vite 的 `preview.proxy` 文档写明继承 `server.proxy`，所以 `/api` 仍通；**若实测此处 404**，那是预览模式独有的配置问题，不影响阶段一交付（spec 三节明定生产期由任意静态服务器托管 dist），把现象记进提交信息即可，**不要**为了它在前端代码里写死后端绝对地址。

- [ ] **Step 4: 全量手测清单（对照 spec 第十节；判据 1 已在 Task 1 Step 8 完成）**

准备文件（Task 4 Step 7 已建，缺就补）：`/tmp/kb-files/` 下要有 `comp.txt`、`rag.txt`、`third.txt`、`empty.txt`、`xss.txt`。

- [ ] **判据 2（上传与时间戳）** 依次上传 `comp.txt`、`rag.txt`：两条队列都 ✅ 成功、列表各多一张卡、时间是**刚刚**（坑 1 生效）；选 `empty.txt` → 队列红底 `文件内容为空`（422）；`.exe` 的 415 已在 Task 2 Step 6 用 Console 验过（`accept` 会让文件选择框看不到 `.exe`，这是 UI 层的正常表现，别当成"415 没测到"）；`docx` 用库内已有的那份基线文档勾选即可，pdf 路径由后端 pytest 覆盖，前端只核对 `accept` 含 `.pdf`。
- [ ] **判据 3（双模式）** 勾 `comp.txt` 问"甲公司的营收是多少？"→ 状态栏蓝色"🔍 知识库模式（1 个文档）"、气泡来源标签 `📚 知识库检索`、下方有 `📎 comp.txt(#id)` + 片段；一个都不勾问"你好"→ 紫色"💬 普通对话模式"、`💬 自由对话`、**无引用区**。DevTools Network 两次请求的 body 分别是 `document_ids:[2]` 与 `document_ids:[]`。
- [ ] **判据 4（刷新等价）** 攒三轮对话后 F5：消息顺序、内容、引用片段全部回来；`curl -s "http://127.0.0.1:8000/api/history/<id>?limit=50"` 的每条 `snippet` 与界面逐字一致。
- [ ] **判据 5（坑 3 回滚）** 前端**不测**：spec 第十节第 5 条明说这靠后端 pytest（monkeypatch 让 `save_chunks` 抛异常）。前端只核对一件事——自然遇到 500 时，队列显示后端 `detail` 原文（例如 `文档入库失败，已回滚`），且 `GET /api/documents` 的列表里**没有**那份失败文档（刷新后确认）。
- [ ] **判据 6（注入面）** 上传 `xss.txt` 并提问让它命中引用：页面把 `<script>alert(1)</script>` 当纯文本显示、无弹窗、Console 无异常执行；`curl -s http://127.0.0.1:8000/api/documents` 里那份文档仍在（说明只是显示层安全，没影响入库）。
- [ ] **清空与换会话** Task 6 Step 4 的 1–9 全绿（含取消确认框不发 DELETE、后端不可用时不清空不换 id）。
- [ ] **Console 洁净** 走完上述全流程，Console 始终零 error、零 Vue warning。

- [ ] **Step 5: 与 `app.py` 的能力等价对照（迁移判据，逐条在浏览器里确认）**

| app.py 里的能力 | Vue 侧落点 | 预期表现 |
|---|---|---|
| `st.file_uploader(multiple)` + "📥 处理" 按钮 | `FileUploader` + `useDocuments.enqueue` | 一次选多份，队列逐个串行上传，无需逐个点按钮 |
| `st.success/st.error` 上传反馈 | `.queue-ok` / `.queue-fail` + `item.error` | 成功绿边、失败红底并显示后端 `detail` |
| `db_manager.get_all_documents()` 侧栏列表 + `doc-card` | `DocumentPanel` + `DocCard` | 卡片文案 `📄 filename(#id)`、`🕒 时间`、`📊 N 个文档块` |
| `st.multiselect("选择知识源")`，键 `{filename}(#{id})`（坑 5） | `DocCard` 的 checkbox + `selectedIds` | 按 id 勾选，天然不会因同名互相覆盖 |
| `st.metric("📊 文档数")` | `.metric` | 数字与卡片数量一致，上传后自动 +1 |
| `st.button("🗑️ 清空对话")`（清消息 + 换 session_id） | `DocumentPanel` 清空按钮 → `App.handleClear` | 先 DELETE 后端历史，成功后才换 id |
| 顶部渐变 `chat-header` | `ChatHeader` | 文案与配色逐字一致 |
| `status-indicator status-rag/normal` | `StatusBar` | 勾选数驱动，文案 `🔍 知识库模式（N 个文档）` / `💬 普通对话模式` |
| 欢迎消息那段 HTML | `MessageList.welcomeText` + `.pre-wrap` | 同样的 emoji 与分行，纯文本插值 |
| `render_message_html` 的头像/气泡 | `MessageBubble` | 👤/🤖、紫蓝渐变 vs 白底、圆角方向一致 |
| 引用片段 `<small>📎 …</small>`（80 + `...`） | `ReferenceList` | `📎 filename(#document_id)` + 片段，前端不再截断 |
| `stream_response_generator` 的逐字 + `time.sleep(0.02)` | `utils/typewriter.js` | 同一正则分词、同样 20ms；SSE 落地后整文件删除 |
| `st.chat_input` 回车发送 | `ChatInput` | 回车发送、Shift+Enter 换行、pending 时禁用 |
| `st.session_state.session_id` | `useSession` + `localStorage` | 只存 id，消息一律不存本地 |
| `st.session_state.message`（前端存消息） | **不再存在** | 由 `GET /api/history/{session_id}` 恢复（spec 五节的取舍） |

- [ ] **Step 6: 收尾提交**

```bash
cd "D:/知识库平台-前后端分离"
git status --short
```

- **有改动**（核对中修掉了问题）：`git add <改过的那个文件>`，然后
  `git -c user.name="31439" -c user.email="31439@local" commit -m "test(frontend): 阶段一全量手测清单通过，响应式与注入面核对"`
- **没有改动**（清单一次全绿）：**不要硬凑空提交**，只跑 `git log --oneline -8` 把七条前端提交贴进最终汇报，验收结论写在汇报里而不是提交信息里。

**阶段一前端验收完成判据**：Task 1–7 的浏览器核对全绿 + `git log` 里 7 条前端提交 + `npm run build` 无 error。后端侧的 spec 第十节判据 1（Chroma 计数）与判据 5（回滚）由后端计划负责，不在本计划范围内。

---

## 阶段二预告（SSE，另立计划）

阶段二（`POST /api/chat/stream`，`meta` / `references` / `token` / `done` / `error` 五种帧）在阶段一验收清单全绿后**另起一份 writing-plans**（spec 十一节第 8 步）。本计划刻意为它留的接缝只有三处：`api/chat.js` 里加 `sendChatStream(payload, handlers)`（用 `fetch` + `ReadableStream`，因为 `EventSource` 不支持 POST body）；`useChat.js` 把"先建 assistant 气泡、再填 references、最后放字"的顺序保持成天然可接收流式的形状（引用先于答案上屏，Task 5 Step 10 第 3 条已在验这个）；`utils/typewriter.js` **整文件删除**，`MessageBubble` 的 `streaming-cursor` 与 `.pre-wrap` 保留（SSE 下它由 `done` 帧前一直为 true）。不在本计划里预先实现任何 SSE 代码，也不留兼容分支——两套逐字逻辑并存会让"显示的字数"和"真实的字数"脱节。

---
