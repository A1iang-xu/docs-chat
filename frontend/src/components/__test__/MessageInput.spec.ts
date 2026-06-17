/**
 * MessageInput 组件测试
 *
 * 测试覆盖：
 * 1. 输入框双向绑定
 * 2. 点击发送按钮触发 send 事件
 * 3. Enter 键发送（Shift+Enter 换行）
 * 4. 发送中状态禁用交互
 * 5. 空内容不允许发送
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageInput from '../MessageInput.vue'

describe('MessageInput', () => {
  it('输入框接受用户输入', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('你好')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('你好')
  })

  it('点击发送按钮触发 send 事件并清空输入', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('测试消息')

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeTruthy()
    expect(wrapper.emitted('send')![0]).toEqual(['测试消息'])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('发送中状态禁止发送', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: true },
    })

    await wrapper.find('textarea').setValue('测试')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeFalsy()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('空内容不触发发送', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('   ')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('send')).toBeFalsy()
  })

  it('Enter 键发送消息', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('Enter 测试')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })

    expect(wrapper.emitted('send')).toBeTruthy()
  })

  it('Shift+Enter 不发送（换行）', async () => {
    const wrapper = mount(MessageInput, {
      props: { isSending: false },
    })

    await wrapper.find('textarea').setValue('不发送')
    await wrapper.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })

    expect(wrapper.emitted('send')).toBeFalsy()
  })
})