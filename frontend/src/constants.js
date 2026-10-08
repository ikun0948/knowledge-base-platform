// 后端契约在前端的镜像，唯一的落点：组件里不许再各写一份。
// 权威定义在 backend/（数字与正则出自 schemas/auth.py，AVATARS 出自 api/auth.py:27 的元组），
// backend/tests/test_frontend_constants.py 两头都钉——这里多写一份副本会红，后端改了数值而这里
// 没跟上也会红。"改动要两边一起改"从一句记性约定变成了门禁。
export const AVATARS = ['auto', '😀', '🤖', '🦊', '🐼', '🚀']
// 只在渲染选择条时用；'auto' 不是图片，是"用昵称首字母"的编码，标签要说清这件事
export const AVATAR_LABELS = { auto: '昵称首字母', '😀': '笑脸', '🤖': '机器人', '🦊': '狐狸', '🐼': '熊猫', '🚀': '火箭' }
export const PASSWORD_MIN = 6
export const PASSWORD_MAX = 64
export const NICKNAME_MAX = 50 // = schemas/auth.py 里 nickname 那格的 max_length
export const MODEL_NAME_MAX = 100 // = schemas/auth.py 里模型名那格的 max_length
export const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
export const PHONE_RE = /^1[3-9]\d{9}$/
