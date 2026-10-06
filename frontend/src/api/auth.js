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
