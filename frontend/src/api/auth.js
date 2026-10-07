// 四个认证端点的薄封装。字段名在这层从后端的 snake_case 翻成前端的 camelCase：
// 界面上 `identifierType` 读起来顺，而契约的真相（identifier_type）只留在这里一行。
import { request } from './client.js'

export function register({ identifierType, identifier, password, nickname }) {
  const body = { identifier_type: identifierType, identifier, password }
  // 昵称留空时连键都不发：后端的默认昵称靠 identifier 推（邮箱取 @ 前、手机取后四位），
  // 前端多发一个 null 就等于替后端决定了"不要默认值"。
  if (nickname) body.nickname = nickname
  return request('/api/auth/register', { method: 'POST', body })
}

export function login({ identifier, password }) {
  return request('/api/auth/login', { method: 'POST', body: { identifier, password } })
}

export function logout() {
  return request('/api/auth/logout', { method: 'POST' })
}

export function getMe() {
  return request('/api/auth/me')
}

// —— 阶段二：六个设置端点。这层仍然只做两件事：camelCase → snake_case 的字段翻译、路径拼装。
//    不碰组件状态、不吞错误、不写 localStorage：返回值就是后端响应体
//    （`{user}` / `{models, default_model}` / 204 的 null），谁调用谁负责安置它。

export function updateProfile({ nickname, avatar }) {
  // 与 register 同一条规矩：留空的字段连键都不发。ProfileIn 要求"昵称与头像至少改一样"，
  // 而 nickname 的 min_length=1——多发一个 '' 不是"清空"，是 422。
  const body = {}
  if (nickname) body.nickname = nickname
  if (avatar) body.avatar = avatar
  return request('/api/auth/me', { method: 'PUT', body })
}

export function updatePassword({ oldPassword, newPassword }) {
  // 204：request 那一格回 null。调用方只能靠"没抛错"判成功，拿不到任何回执。
  return request('/api/auth/me/password', {
    method: 'PUT',
    body: { old_password: oldPassword, new_password: newPassword },
  })
}

export function updateLlmConfig({ apiKey, baseUrl }) {
  return request('/api/auth/me/llm', { method: 'PUT', body: { api_key: apiKey, base_url: baseUrl } })
}

export function addModel(name) {
  return request('/api/auth/me/models', { method: 'POST', body: { name } })
}

export function removeModel(name) {
  // 模型名是用户手打的（"qwen 2.5/coder" 这种带空格与斜杠的真存在）。不编码就会把一段路径
  // 劈成两段，坏法是 404「模型不在你的名单里」而不是 422——那句话这时候是假的。
  return request(`/api/auth/me/models/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function setDefaultModel(name) {
  return request('/api/auth/me/models/default', { method: 'PUT', body: { name } })
}
