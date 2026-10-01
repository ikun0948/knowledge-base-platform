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
