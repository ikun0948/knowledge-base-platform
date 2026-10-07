// 需求 3 说"不显示 session_id"。`.session-debug` 块删了，但 StatusBar 顶部那个
// 显示前 8 位的 chip 也在同一句话的账上（spec 5.4：留着等于把 id 从左下挪到了顶上）。
// 这条测就是为了让它别哪天被"顺手加回去"。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatusBar from '../src/components/StatusBar.vue'

describe('StatusBar', () => {
  it('模式标签两态：选了块报数量，一个不选就是普通对话', () => {
    const rag = mount(StatusBar, { props: { selectedCount: 3 } })
    expect(rag.text()).toContain('知识库模式')
    expect(rag.text()).toContain('3')
    expect(mount(StatusBar, { props: { selectedCount: 0 } }).text()).toContain('普通对话模式')
  })

  it('界面上不出现 session 字样，也不再接 sessionId prop', () => {
    // 故意把 sessionId 传进去：删掉 prop 之后 Vue 只会把它当 attrs 忽略，
    // 于是"传了但没人读"这种残留在测里也照样绿——所以判据看的是文本而不是 prop 声明。
    const wrapper = mount(StatusBar, { props: { selectedCount: 0, sessionId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' } })
    expect(wrapper.find('.session-chip').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('session')
    expect(wrapper.text()).not.toContain('aaaaaaaa')
  })
})
