import type { Register } from 'claude-code'

export const register: Register = (on) => {
  on('classic.PreToolUse', async ($, e, next) => {
    const downstream = await next(e)
    if (downstream.ask !== undefined || downstream.deny !== undefined) return downstream

    try {
      const { tool, tool_use_id, ...originalInput } = e
      const input = downstream.updatedInput ?? originalInput
      const cwd = await $.session.cwd()
      const proc = await $.process.run(['python3', `${$.plugin.root}/hooks/tribunal.py`, '--native'], {
        stdin: JSON.stringify({ tool_name: tool, tool_input: input, cwd }),
        cwd, timeoutMs: 30000,
      })
      if (proc.exitCode !== 0 || proc.isStdoutTruncated || proc.isStderrTruncated) {
        throw new Error('invalid subprocess result')
      }
      const verdict = JSON.parse(proc.stdout)
      if (!verdict || !['allow', 'ask', 'deny'].includes(verdict.decision)
          || typeof verdict.reason !== 'string'
          || typeof verdict.respect_saved_permission !== 'boolean'
          || (verdict.respect_saved_permission && verdict.decision !== 'ask')) {
        throw new Error('invalid verdict')
      }
      // An allow below cannot override Tribunal; retain rewrites/context.
      const { allow, ...rest } = downstream
      if (verdict.respect_saved_permission) {
        const permission = await $.tool.check({ tool, input })
        if (permission.decision === 'allow' && typeof permission.rule === 'string'
            && permission.rule.trim()) return rest
      }
      if (verdict.decision === 'allow') return { ...rest, allow: true }
      if (verdict.decision === 'deny') return { ...rest, deny: verdict.reason }
      return { ...rest, ask: verdict.reason }
    } catch {
      const { allow, ...rest } = downstream
      return { ...rest, ask: 'tribunal unavailable: native adapter' }
    }
  }).catch(async () => ({ ask: 'tribunal unavailable: native adapter' }))
}
