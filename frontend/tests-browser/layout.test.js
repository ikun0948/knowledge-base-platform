// 阶段三 ⑧：把阶段二 Task 12 的一次性 Edge 探针里**能常驻的那一半**钉成回归判据。
// 跑法：`npm run test:browser`（要 dev server + 后端 + 本机 Edge，见 _browser-probe.js 的 requireStack）。
//
// 为什么它不在 `npm test` 里：jsdom 不做布局，`clientHeight` 恒 0，一切"看得见/在视口内/不撑破"
// 在 jsdom 里只能断结构、断不了几何（spec 五节当时就是这么分的）。
// 为什么不是 skip：这一套判据唯一的用途是被人为跑起来，skip 会让人以为"布局验过了"。
//
// 口径挑的是什么：**数据无关**的几何不变式。不依赖账号里有几篇文档、名单里有几枚模型，
// 因此不烧真凭证配额、不写业务数据（跑完只剩一枚已被登出删掉的票），下一个人在任何库上都能重跑。

import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import {
  APP_ORIGIN,
  insideViewport,
  launchBrowser,
  login,
  loginCredentials,
  rectOf,
  rectsOverlap,
  requireStack,
  setViewport,
  twoFrames,
  wipeStorage,
} from './_browser-probe.js'

const WIDE = { width: 1280, height: 900 }
const NARROW = { width: 375, height: 800 }
const MIDDLE = { width: 500, height: 900 }

let browser
let page
let consoleErrors
let pageErrors
let baseline

beforeAll(async () => {
  await requireStack()
  browser = await launchBrowser()
  page = await browser.newPage()
  consoleErrors = []
  pageErrors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', (err) => pageErrors.push(String(err.message ?? err)))
  await wipeStorage(page)
  await login(page, loginCredentials())
  // 基线取在登录完成之后（阶段二 R4 的口径）：401 落回登录页是设计路径，不是故障
  baseline = { console: consoleErrors.length, page: pageErrors.length }
}, 120_000)

afterAll(async () => {
  // 测尾登出：票是库里的一行，不登出每跑一次多留一枚（阶段一终审 advisory ④ 记的就是这个面）。
  // 走 API 而不是点界面按钮——最后一档可能是窄屏且开着浮层，那一下点击会被遮罩吃掉（怪癖 6），
  // 清理环节不该依赖界面状态。
  if (page) {
    await page.evaluate(async () => {
      const token = localStorage.getItem('auth_token')
      if (token) {
        await fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } })
      }
      localStorage.clear()
    }).catch(() => {})
  }
  await browser?.close()
})

async function clickText(page, selector, label) {
  // 按可见文字找元素而不是按下标：TABS 里存的是 value（'' 表示"全部"），下标口径一崩就崩在后面整条判据上
  const handle = await page.evaluateHandle((sel, text) => {
    const found = [...document.querySelectorAll(sel)].find((el) => el.textContent.trim() === text)
    return found ?? globalThis.document.body
  }, selector, label)
  const element = handle.asElement()
  if (!element) throw new Error(`找不到文字为「${label}」的 ${selector}`)
  await element.click()
  await twoFrames(page)
}

async function openSidePanel(page) {
  // ≤768 时 .side-panel 是 display:none 的浮层，.rail-settings / .picker-open 都住在里面：不先展开就点不到
  const panel = await rectOf(page, '.side-panel')
  if (panel?.visible) return
  await clickText(page, '.panel-toggle', '展开文档面板')
}

async function openModal(page, trigger) {
  await openSidePanel(page)
  const handle = await page.$(trigger)
  if (!handle) throw new Error(`触发弹窗的 ${trigger} 不在界面上`)
  await handle.click()
  await twoFrames(page)
}

async function closeModal(page) {
  const handle = await page.$('.picker-close')
  if (handle) await handle.click()
  await page.keyboard.press('Escape')
  await twoFrames(page)
  expect(await rectOf(page, '.picker-modal')).toBeNull()
}

describe(`视口基建（${APP_ORIGIN}）`, () => {
  for (const vp of [WIDE, NARROW, MIDDLE]) {
    it(`${vp.width}×${vp.height} 这一档真的设进去了`, async () => {
      const read = await setViewport(page, vp)
      // 不回读就等于没量：in-app 浏览器可能给出 0×0 的无 surface 窗口，那时下面每一条数字都是编的
      expect([read.innerWidth, read.innerHeight]).toEqual([vp.width, vp.height])
    })
  }
})

describe('三档共判：整页不滚 + 消息区是有界滚动容器', () => {
  for (const vp of [WIDE, NARROW, MIDDLE]) {
    it(`${vp.width}×${vp.height}：工作区收在一屏之内`, async () => {
      await setViewport(page, vp)
      const numbers = await page.evaluate(() => ({
        docScrollHeight: document.scrollingElement.scrollHeight,
        innerHeight: window.innerHeight,
        bodyScrollHeight: document.body.scrollHeight,
      }))
      // app-shell 钉死视口 + 显式轨道（layout.css 的 L-1/L-2/L-3 与 ≤768 分支）之后，
      // 页面本身不该出现第二条滚动条——三档都量过：900/900、800/800、900/900
      expect(numbers.docScrollHeight).toBeLessThanOrEqual(numbers.innerHeight)
      expect(numbers.bodyScrollHeight).toBeLessThanOrEqual(numbers.innerHeight)
    })

    it(`${vp.width}×${vp.height}：消息区自己撑得出高度（旧塌 2px 的防线）`, async () => {
      await setViewport(page, vp)
      const messages = await rectOf(page, '.chat-messages')
      // 下界取半屏：实测 594.2/900=66% 与 469.4/800=59%，而这个高度来自 grid 轨道、与历史里有几条消息无关，
      // 所以"半屏"既挡得住塌陷，又不会因数据多少而假红
      expect(messages.clientHeight).toBeGreaterThanOrEqual(Math.floor(vp.height / 2))
      expect(insideViewport(messages, { innerWidth: vp.width, innerHeight: vp.height })).toBe(true)
    })
  }
})

describe('三档共判：内容长过可用高度时，撑开的是消息区而不是页面', () => {
  // 这一组是变异自证 M5 逼出来的：把宽屏的 `.app-shell{grid-template-rows:minmax(0,1fr)}` 删掉，
  // 前面 18 条判据**照常全绿**——账号里的历史不够长，撑不出"页面被顶开"这个后果。
  // 那就自己在 DOM 里合成高度（一枚 3000px 的占位块，量完立刻移除）：仍然不碰任何业务数据。
  for (const vp of [WIDE, NARROW, MIDDLE]) {
    it(`${vp.width}×${vp.height}：高内容下页面不滚、消息区变成可滚的那个`, async () => {
      await setViewport(page, vp)
      const r = await page.evaluate(async () => {
        const list = document.querySelector('.chat-messages')
        const filler = document.createElement('div')
        // flex:0 0 auto 是必须的：`.chat-messages` 自己是 `display:flex; flex-direction:column`，
        // 占位块作为 flex item 默认 flex-shrink:1，会被压回容器高度（实测 scrollHeight 469 == clientHeight 469，
        // 于是"内容溢出"这件事根本没发生，判据就是在量一个不存在的前提）
        filler.style.flex = '0 0 auto'
        filler.style.height = '3000px'
        list.appendChild(filler)
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
        const out = {
          pageOverflow: document.scrollingElement.scrollHeight - window.innerHeight,
          listClientHeight: list.clientHeight,
          listScrollHeight: list.scrollHeight,
        }
        list.scrollTop = 999_999
        out.clampedScrollTop = list.scrollTop
        filler.remove()
        list.scrollTop = 0
        return out
      })
      expect(r.pageOverflow, `页面被顶开 ${r.pageOverflow}px`).toBeLessThanOrEqual(0)
      expect(r.listScrollHeight, JSON.stringify(r)).toBeGreaterThan(r.listClientHeight)
      // scrollTop 被钳在 scrollHeight - clientHeight 上，才是"有界滚动容器"；能滚出页面就不叫滚动容器
      expect(r.clampedScrollTop, JSON.stringify(r)).toBe(r.listScrollHeight - r.listClientHeight)
    })
  }
})

describe('宽屏 1280×900', () => {
  it('发送按钮在视口内，输入区不横向溢出', async () => {
    await setViewport(page, WIDE)
    const vp = { innerWidth: WIDE.width, innerHeight: WIDE.height }
    const send = await rectOf(page, '.chat-send')
    const input = await rectOf(page, '.chat-input')
    expect(send.visible).toBe(true)
    expect(insideViewport(send, vp)).toBe(true)
    expect(input.scrollWidth).toBe(input.clientWidth)
  })

  it('两块浮层都不压住发送按钮（宽屏档）', async () => {
    await setViewport(page, WIDE)
    for (const trigger of ['.rail-settings', '.picker-open']) {
      await openModal(page, trigger)
      const modal = await rectOf(page, '.picker-modal')
      const send = await rectOf(page, '.chat-send')
      expect(modal.visible, `${trigger} 的浮层没渲染出来`).toBe(true)
      expect(rectsOverlap(modal, send), `${trigger} 浮层 rect=${JSON.stringify(modal)} 压住发送 rect=${JSON.stringify(send)}`).toBe(false)
      // 与窄屏/中档同口径：只断"不压住"的话，浮层自己长到屏幕外也量不出来
      expect(insideViewport(modal, { innerWidth: WIDE.width, innerHeight: WIDE.height }), `${trigger} 浮层 rect=${JSON.stringify(modal)} 超出视口`).toBe(true)
      await closeModal(page)
    }
  })
})

describe('窄屏 375×800（≤768 分支）', () => {
  it('输入区不撑破视口', async () => {
    await setViewport(page, NARROW)
    const input = await rectOf(page, '.chat-input')
    expect(input.scrollWidth).toBe(input.clientWidth)
    expect(input.right).toBeLessThanOrEqual(NARROW.width)
  })

  it('模型下拉与发送都在视口内、且没叠在一起', async () => {
    await setViewport(page, NARROW)
    const select = await rectOf(page, '.model-select')
    const send = await rectOf(page, '.chat-send')
    const vp = { innerWidth: NARROW.width, innerHeight: NARROW.height }
    // .chat-controls 的 flex-wrap 一旦失效，这两枚要么叠在一起、要么被挤出屏幕外
    expect([select.visible, send.visible]).toEqual([true, true])
    expect(insideViewport(select, vp)).toBe(true)
    expect(insideViewport(send, vp)).toBe(true)
    expect(rectsOverlap(select, send), `下拉 rect=${JSON.stringify(select)} 与发送 rect=${JSON.stringify(send)} 重叠`).toBe(false)
  })

  it('≤768 控件行的两行中和规则在位（计算样式口径）', async () => {
    await setViewport(page, NARROW)
    // 变异自证 M1/M2 实测：删掉 `.chat-controls{flex-wrap:wrap}` 或 `.model-select{flex:1;min-width:0;max-width:none}`
    // 之后，上面那条几何判据**照常绿**——名单里只有一枚短名字，控件行根本没被撑开。
    // 几何判据钉的是结果，撑不撑得开取决于账号里的模型名多长；这两行的牙齿改由计算样式直接给，与数据无关。
    const computed = await page.evaluate(() => {
      const controls = getComputedStyle(document.querySelector('.chat-controls'))
      const select = getComputedStyle(document.querySelector('.model-select'))
      return { wrap: controls.flexWrap, grow: select.flexGrow, minWidth: select.minWidth, maxWidth: select.maxWidth }
    })
    expect(computed, JSON.stringify(computed)).toEqual({ wrap: 'wrap', grow: '1', minWidth: '0px', maxWidth: 'none' })
  })

  it('设置弹窗的内容不横向溢出（名单行 flex-wrap 的常驻版）', async () => {
    await setViewport(page, NARROW)
    await openModal(page, '.rail-settings')
    const body = await rectOf(page, '.settings-body')
    const modal = await rectOf(page, '.picker-modal')
    // 钉容器而不是钉某一行：名单里有几枚模型是账号状态，容器不溢出对任何状态都成立，
    // 而一行太宽的表现恰好就是把容器撑出 scrollWidth > clientWidth
    expect(body.scrollWidth).toBe(body.clientWidth)
    expect(modal.right).toBeLessThanOrEqual(NARROW.width)
    await closeModal(page)
  })

  it('候选池弹窗在视口内，且窄屏退成一列', async () => {
    await setViewport(page, NARROW)
    await openModal(page, '.picker-open')
    const modal = await rectOf(page, '.picker-modal')
    const vp = { innerWidth: NARROW.width, innerHeight: NARROW.height }
    expect(insideViewport(modal, vp)).toBe(true)
    // 等列表那一轮落地再量：`.picker-results` 是 `v-else-if="chunks.length"`，
    // busy（"搜索中…"）那一档它不存在，立刻量就是拿 null 去喂 getComputedStyle
    await page.waitForFunction(
      () => document.querySelector('.picker-results, .picker-hint') !== null,
      { timeout: 15_000 },
    )
    const measured = await page.evaluate(() => {
      const host = document.querySelector('.picker-modal')
      // 账号里没有可选块时真实列表永远不渲染，而这一档判的是 layout.css 那条"窄屏退一列"的**样式规则**：
      // 于是没有真实列表时在弹窗里挂一枚同类名的临时节点，量完就删。两种口径都是真的在量这条规则。
      const real = host.querySelector('.picker-results')
      const node = real ?? (() => {
        const ul = document.createElement('ul')
        ul.className = 'picker-results'
        host.appendChild(ul)
        return ul
      })()
      const value = getComputedStyle(node).gridTemplateColumns
      if (!real) node.remove()
      return { source: real ? '真实结果列表' : '临时同类名探针', value }
    })
    // 两列在 375px 上会挤成两个窄条：数一个 track 就是"退成一列"的直接证据
    expect(measured.value.trim().split(/\s+/), `口径=${measured.source} 值=${measured.value}`).toHaveLength(1)
    await closeModal(page)
  })
})

describe('中档 500×900（浮层高度 66vh 与输入区的贴合）', () => {
  it('两块浮层都不压住发送按钮', async () => {
    await setViewport(page, MIDDLE)
    for (const trigger of ['.rail-settings', '.picker-open']) {
      await openModal(page, trigger)
      const modal = await rectOf(page, '.picker-modal')
      const send = await rectOf(page, '.chat-send')
      expect(rectsOverlap(modal, send), `${trigger} 浮层 rect=${JSON.stringify(modal)} 压住发送 rect=${JSON.stringify(send)}`).toBe(false)
      expect(insideViewport(modal, { innerWidth: MIDDLE.width, innerHeight: MIDDLE.height })).toBe(true)
      await closeModal(page)
    }
  })
})

describe('全程', () => {
  it('登录之后不新增任何页面错误', async () => {
    await setViewport(page, WIDE)
    expect(consoleErrors.slice(baseline.console), consoleErrors.slice(baseline.console).join('\n')).toEqual([])
    expect(pageErrors.slice(baseline.page), pageErrors.slice(baseline.page).join('\n')).toEqual([])
  })
})
