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
