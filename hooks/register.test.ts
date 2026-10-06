import type { Register } from 'claude-code'
import { test, expect } from 'claude-code/testing'

// Observe the permission result itself: this harness lets an ask reach the mock tool.
const observer = {
  name: 'permission-observer',
  tier: 'prepend' as const,
  register: ((on) => {
    on('classic.PreToolUse', async ($, e, next) => {
      const result = await next(e)
      await $.store.set('observed', result)
      return result
    })
  }) satisfies Register,
}

const ask = { decision: 'ask', reason: 'jev: human_ask', respect_saved_permission: true }

for (const [name, permission, expected] of [
  ['saved allow', { decision: 'allow', rule: 'Bash(make)' }, undefined],
  ['mode allow', { decision: 'allow' }, 'jev: human_ask'],
  ['empty rule', { decision: 'allow', rule: '' }, 'jev: human_ask'],
  ['native ask', { decision: 'ask', rule: 'Bash(make)' }, 'jev: human_ask'],
  ['native deny', { decision: 'deny', rule: 'Bash(make)' }, 'jev: human_ask'],
] as const) {
  test(name, { plugins: [observer] }, async ($, on) => {
    let observed: unknown
    on('store.set', async (_$, e) => { observed = e.value; return { value: undefined } })
    on('classic.PreToolUse', async () => ({}))
    on('session.cwd', async () => ({ value: '/tmp' }))
    on('process.run', async (_$, e) => {
      expect(e.argv[0]).toBe('python3')
      expect(e.argv[2]).toBe('--native')
      expect(JSON.parse(e.init!.stdin!)).toEqual({
        tool_name: 'Bash', tool_input: { command: 'make' }, cwd: '/tmp',
      })
      return { value: { exitCode: 0, stdout: JSON.stringify(ask), stderr: '',
               isStdoutTruncated: false, isStderrTruncated: false } }
    })
    on('tool.check', async () => permission)
    on('tool.call', async () => ({ result: 'mock' }))
    await $.tool.call({ tool: 'Bash', command: 'make' })
    expect(observed).toEqual(expected ? { ask: expected } : {})
  })
}

for (const verdict of [
  { decision: 'deny', reason: 'jev rejected', respect_saved_permission: false },
  { decision: 'allow', reason: 'jev allowed', respect_saved_permission: false },
  { decision: 'ask', reason: 'provider failed', respect_saved_permission: false },
]) {
  test(verdict.reason, { plugins: [observer] }, async ($, on) => {
    let observed: unknown
    on('store.set', async (_$, e) => { observed = e.value; return { value: undefined } })
    on('classic.PreToolUse', async () => ({}))
    on('session.cwd', async () => ({ value: '/tmp' }))
    on('process.run', async () => ({ value: { exitCode: 0, stdout: JSON.stringify(verdict),
      stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
    on('tool.check', async () => { throw new Error('must not query') })
    on('tool.call', async () => ({ result: 'mock' }))
    await $.tool.call({ tool: 'Bash', command: 'make' })
    expect(observed).toEqual(verdict.decision === 'allow' ? { allow: true } :
      { [verdict.decision]: verdict.reason })
  })
}

for (const restriction of [{ ask: 'other hook' }, { deny: 'other hook' }]) {
  test('preserves ' + Object.keys(restriction)[0], { plugins: [observer] }, async ($, on) => {
    let observed: unknown
    on('store.set', async (_$, e) => { observed = e.value; return { value: undefined } })
    on('classic.PreToolUse', async () => restriction)
    on('process.run', async () => { throw new Error('must not run') })
    on('tool.call', async () => ({ result: 'mock' }))
    await $.tool.call({ tool: 'Bash', command: 'make' })
    expect(observed).toEqual(restriction)
  })
}

for (const failure of ['downstream', 'cwd', 'query', 'process', 'exit', 'truncated',
                       'stderr', 'json', 'shape', 'eligibility']) {
  test('fails to human: ' + failure, { plugins: [observer] }, async ($, on) => {
    let observed: unknown
    on('store.set', async (_$, e) => { observed = e.value; return { value: undefined } })
    on('classic.PreToolUse', async () => {
      if (failure === 'downstream') throw new Error('downstream unavailable')
      return { allow: true }
    })
    on('session.cwd', async () => {
      if (failure === 'cwd') throw new Error('cwd unavailable')
      return { value: '/tmp' }
    })
    on('process.run', async () => {
      if (failure === 'process') throw new Error('timeout or cannot spawn')
      return { value: { exitCode: failure === 'exit' ? 1 : 0,
        stdout: failure === 'json' ? 'invalid' : JSON.stringify(failure === 'shape' ? {} :
          failure === 'eligibility' ? { ...ask, decision: 'allow' } : ask),
        stderr: '', isStdoutTruncated: failure === 'truncated',
        isStderrTruncated: failure === 'stderr' } }
    })
    on('tool.check', async () => { throw new Error('query unavailable') })
    on('tool.call', async () => ({ result: 'mock' }))
    await $.tool.call({ tool: 'Bash', command: 'make' })
    expect(observed).toEqual({ ask: 'tribunal unavailable: native adapter' })
  })
}

test('checks effective rewritten input and preserves context', { plugins: [observer] }, async ($, on) => {
  let observed: unknown
  on('store.set', async (_$, e) => { observed = e.value; return { value: undefined } })
  const downstream = { updatedInput: { command: 'make && something-else' },
                       additionalContext: ['another hook'] }
  on('classic.PreToolUse', async () => downstream)
  on('session.cwd', async () => ({ value: '/tmp' }))
  on('process.run', async (_$, e) => {
    expect(JSON.parse(e.init!.stdin!).tool_input).toEqual(downstream.updatedInput)
    return { value: { exitCode: 0, stdout: JSON.stringify(ask), stderr: '',
             isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('tool.check', async (_$, e) => {
    expect(e.input).toEqual(downstream.updatedInput)
    return { decision: 'ask' }
  })
  on('tool.call', async () => ({ result: 'mock' }))
  await $.tool.call({ tool: 'Bash', command: 'make' })
  expect(observed).toEqual({ ...downstream, ask: 'jev: human_ask' })
})
