// 常驻浏览器探针的公共件：起 Edge headless、按档设视口并回读、登录与登出、量 rect、数页面错误。
// 这里不放判据——判据全在 layout.test.js，一个文件读完整套口径。

import { existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

import puppeteer from 'puppeteer-core'

// 默认走 Vite dev server 而不是 dist：判据 5 的"整页不滚"与代理链路都要在 dev 形态下量，
// 而 dev 的 /api 代理（vite.config.js）正是真浏览器会走的那条路。
// 用 127.0.0.1 而不是 localhost：Windows 上 localhost 可能先走 IPv6 解析，握手失败表现为 ECONNREFUSED，
// 报错看起来像"服务没起"而真相是没监听 ::1。
export const APP_ORIGIN = process.env.KB_APP_ORIGIN ?? 'http://127.0.0.1:5173'

const EDGE_CANDIDATES = [
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
]

function readEnvKey(name) {
  // 只取两枚键，且永不返回给断言消息。引号必须剥：阶段二 Task 12 就栽在"值被引号包着而解析器没剥"，
  // 于是把一次解析错误读成了"配置缺键"。
  const file = path.resolve(import.meta.dirname, '../../backend/.env')
  let text
  try {
    text = readFileSync(file, 'utf8')
  } catch {
    return ''
  }
  for (const line of text.split(/\r?\n/)) {
    const cut = line.indexOf('=')
    if (cut < 0) continue
    if (line.slice(0, cut).trim() !== name) continue
    return line.slice(cut + 1).trim().replace(/^["']|["']$/g, '')
  }
  return ''
}

// 口令的取法与红线：**值永远不外印**——不进 console、不进断言消息、不落盘，报错只说哪一枚键没找到。
// 写死口令进测试文件等于把默认口令第二次推进 git 历史（它已经在 0b22116 之前进去过一次）。
export function loginCredentials() {
  const identifier = process.env.KB_LOGIN_IDENTIFIER || readEnvKey('DEFAULT_USER_IDENTIFIER') || 'default@local'
  const password = process.env.KB_LOGIN_PASSWORD || readEnvKey('DEFAULT_USER_PASSWORD')
  if (!password) {
    throw new Error('拿不到登录口令：导出 KB_LOGIN_PASSWORD，或确认 backend/.env 里有 DEFAULT_USER_PASSWORD（本探针不会打印它的值）')
  }
  return { identifier, password }
}

// 前置条件不满足时要**响亮地失败**，不许 skip：这一套判据唯一的用途就是被人为跑起来，
// 一句 skip 会让人以为"布局验过了"。（Vite 代理在上游死了时回 502 而不是网络失败，所以两种坏法分开报。）
export async function requireStack() {
  let res
  try {
    res = await fetch(`${APP_ORIGIN}/api/health`)
  } catch {
    throw new Error(`连不上 ${APP_ORIGIN}：先 npm run dev（并确认后端 uvicorn 已在 :8000，同一时刻只起一份）`)
  }
  if (!res.ok) {
    throw new Error(`${APP_ORIGIN}/api/health 回 ${res.status}：dev server 在、后端不在或没接上（Vite 把上游不可达翻译成 502，不是网络失败）`)
  }
}

export async function launchBrowser() {
  const executablePath = process.env.KB_BROWSER_PATH ?? EDGE_CANDIDATES.find((p) => existsSync(p))
  if (!executablePath) {
    throw new Error(`找不到 Edge：设 KB_BROWSER_PATH 指向浏览器可执行文件（本机默认在 ${EDGE_CANDIDATES[0]}）`)
  }
  // 独立的 user-data-dir：复用日常 Edge 配置会撞上"已在运行"的单实例锁，而且会把测试profile写进用户目录。
  return puppeteer.launch({
    executablePath,
    headless: true,
    userDataDir: path.join(tmpdir(), 'kb-browser-probe-profile'),
  })
}

export async function wipeStorage(page) {
  await page.goto(APP_ORIGIN, { waitUntil: 'networkidle2' })
  await page.evaluate(() => localStorage.clear())
}

// 票直接写进 localStorage 再刷新，而不是在界面上打字点登录：
// 布局判据要的是"已登录的工作区"这个前提，登录那条链路本身已有 jsdom 判据与 live 判据守着，
// 在这里重走一遍只会让布局红项混进一句口令错误的噪音。
// 'auth_token' 与 useAuth.js 的 TOKEN_KEY 同名、这里是重复的字面量：探针模拟的是"浏览器里已经有票"这个
// 既成事实，从源码导入就得把 src/composables 拖进 node 环境的解析链（它带 .vue 依赖），代价大于收益。
export async function login(page, { identifier, password }) {
  await page.goto(APP_ORIGIN, { waitUntil: 'networkidle2' })
  const outcome = await page.evaluate(async (id, pwd) => {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier: id, password: pwd }),
    })
    if (!res.ok) return { ok: false, status: res.status }
    const body = await res.json()
    localStorage.setItem('auth_token', body.token)
    return { ok: true, status: res.status }
  }, identifier, password)
  if (!outcome.ok) {
    throw new Error(`POST /api/auth/login 回 ${outcome.status}：默认账号的口令不对或账号已不在（本探针不打印任何凭证）`)
  }
  await page.reload({ waitUntil: 'networkidle2' })
  await page.waitForSelector('.user-rail')
}

// 点完由 Vue 状态控制显隐的元素后必须等两帧再量：同帧内量到的是 display:none 的 0×0，
// 会得到"浮层高度 0"这类假阴性（2026-10-03 宽屏回归第一版就栽在这）。
export function twoFrames(page) {
  return page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  )
}

// 设完视口必须回读 innerWidth：in-app 浏览器可能给出 0×0 的无 surface 窗口，
// 那时一切视口判据都在量一个不存在的高度（会把"首屏可见"量成 33 万 px 的假数据）。
export async function setViewport(page, { width, height }) {
  await page.setViewport({ width, height })
  await twoFrames(page)
  const read = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
  }))
  return { ...read, wanted: { width, height } }
}

export async function rectOf(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel)
    if (!el) return null
    const r = el.getBoundingClientRect()
    return {
      left: r.left, top: r.top, right: r.right, bottom: r.bottom,
      width: r.width, height: r.height,
      scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
      scrollHeight: el.scrollHeight, clientHeight: el.clientHeight,
      // display:none 的元素 rect 全 0：puppeteer 的 click 照样会派发，所以"看得见"必须在这里量出来
      visible: r.width > 0 && r.height > 0,
    }
  }, selector)
}

export function rectsOverlap(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
}

export function insideViewport(r, viewport) {
  return r.left >= 0 && r.top >= 0 && r.right <= viewport.innerWidth && r.bottom <= viewport.innerHeight
}
