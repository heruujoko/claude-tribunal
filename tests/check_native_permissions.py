"""Check real Claude Code permissions with local Jev/model fixtures (no provider spend).

Usage: python3 tests/check_native_permissions.py (Claude Code 2.1.289+)
PermissionRequest hooks simulate approvals, not interactive human clicks.
"""
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
COMMAND = 'touch tribunal-permission-check'
COMPOUND = COMMAND + ' && touch tribunal-other-check'
DRIVER = """
export function register(on) {
  on('classic.PreToolUse', async ($, e, next) => {
    const observed = await next(e)
    const { tool, tool_use_id, ...input } = e
    const permission = await $.tool.check({ tool, input })
    await $.http.fetch('ENDPOINT/observe', {
      method: 'POST', body: JSON.stringify({ permission, observed }),
    })
    return observed
  })
}
"""


class Fixture(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/observe':
            self.server.observed.append(body)
            self.reply({})
        elif self.path == '/decide':
            assert body['state']['input'] == json.dumps({'command': self.server.command})
            self.reply({'answers': {'verdict': {
                'type': 'choice', 'choice': 'human_ask', 'confidence': 0.99,
            }}})
        elif self.path.endswith('/count_tokens'):
            self.reply({'input_tokens': 100})
        elif self.path.startswith('/v1/messages'):
            completed = sum(block.get('type') == 'tool_result'
                            for message in body['messages']
                            for block in message['content'] if isinstance(block, dict))
            tool = completed < self.server.calls
            content = ({'type': 'tool_use', 'id': f'toolu_check_{completed}',
                        'name': 'Bash', 'input': {}} if tool else {'type': 'text', 'text': ''})
            events = [
                ('message_start', {'message': {
                    'id': f'msg_check_{completed}', 'type': 'message', 'role': 'assistant',
                    'model': body['model'], 'content': [], 'stop_reason': None,
                    'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 0},
                }}),
                ('content_block_start', {'index': 0, 'content_block': content}),
                ('content_block_delta', {'index': 0, 'delta':
                    {'type': 'input_json_delta', 'partial_json': json.dumps({
                        'command': self.server.command,
                    })} if tool else {'type': 'text_delta', 'text': 'Done.'}}),
                ('content_block_stop', {'index': 0}),
                ('message_delta', {'delta': {'stop_reason': 'tool_use' if tool else 'end_turn',
                                            'stop_sequence': None},
                                   'usage': {'output_tokens': 10}}),
                ('message_stop', {}),
            ]
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for event, data in events:
                self.wfile.write(f'event: {event}\ndata: {json.dumps({"type": event, **data})}\n\n'.encode())
        else:
            self.send_error(404)

    def reply(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, *_):
        pass


def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='tribunal-check-') as directory:
            project = Path(directory)
            driver = project / 'driver'
            (driver / '.claude-plugin').mkdir(parents=True)
            (driver / 'hooks').mkdir()
            (driver / '.claude-plugin/plugin.json').write_text(json.dumps({
                'name': 'aaa-permission-check', 'version': '0.1.0',
                'description': 'Temporary native permission test',
            }))
            endpoint = f'http://127.0.0.1:{server.server_port}'
            (driver / 'hooks/register.js').write_text(DRIVER.replace('ENDPOINT', endpoint))
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('TRIBUNAL_', 'CCV_', 'CLOUDFLARE_', 'CLAUDE', 'ANTHROPIC_'))
                   and k != 'JEV_API_KEY'}
            # Throwaway user config dir: user-level settings never touch the real ~/.claude.
            home = project / 'home'
            (home / '.claude').mkdir(parents=True)
            env.update(HOME=str(home), CLAUDE_CONFIG_DIR=str(home / '.claude'),
                       TRIBUNAL_PROVIDER='hosted', TRIBUNAL_API_KEY='local-fixture',
                       TRIBUNAL_ENDPOINT=endpoint + '/decide',
                       TRIBUNAL_CONFIG=str(project / 'no-config.json'),
                       ANTHROPIC_API_KEY='local-fixture', ANTHROPIC_BASE_URL=endpoint,
                       CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')

            def run(rules=None, approval=None, command=COMMAND, sources=''):
                server.observed = []
                server.command = command
                server.calls = 2 if approval else 1
                hooks = {'modules': ['./register.js']}
                if approval:
                    decision = {'behavior': 'allow'}
                    if approval != 'once':
                        decision['updatedPermissions'] = [{
                            'type': 'addRules', 'behavior': 'allow', 'destination': approval,
                            'rules': [{'toolName': 'Bash', 'ruleContent': command}],
                        }]
                    output = json.dumps({'hookSpecificOutput': {
                        'hookEventName': 'PermissionRequest', 'decision': decision,
                    }})
                    hooks['hooks'] = {'PermissionRequest': [{'matcher': 'Bash', 'hooks': [{
                        'type': 'command', 'command': 'python3',
                        'args': ['-c', f'print({output!r})'],
                    }]}]}
                (driver / 'hooks/hooks.json').write_text(json.dumps(hooks))
                proc = subprocess.run([
                    'claude', '-p', 'Run the permission fixture.', '--no-session-persistence',
                    '--setting-sources', sources,
                    '--settings', json.dumps({'permissions': rules or {}}),
                    '--permission-mode', 'manual', '--permission-prompts', 'none',
                    '--strict-mcp-config', '--tools', 'Bash', '--model', 'haiku',
                    '--plugin-dir', str(driver), '--plugin-dir', str(ROOT),
                ], cwd=project, env=env, capture_output=True, text=True, timeout=60)
                assert proc.returncode == 0, (proc.stdout, proc.stderr)
                assert len(server.observed) == server.calls, (proc.stdout, proc.stderr, server.observed)
                return server.observed

            rule = f'Bash({COMMAND})'
            cases = [
                ('saved allow', {'allow': [rule]}, COMMAND, 'allow', False),
                ('no permission', {}, COMMAND, 'ask', True),
                ('different command', {'allow': ['Bash(touch other)']}, COMMAND, 'ask', True),
                ('compound command', {'allow': [rule]}, COMPOUND, 'ask', True),
                ('deny precedence', {'allow': [rule], 'deny': [rule]}, COMMAND, 'deny', True),
                ('ask precedence', {'allow': [rule], 'ask': [rule]}, COMMAND, 'ask', True),
            ]
            for name, rules, command, expected, should_ask in cases:
                result = run(rules, command=command)[0]
                assert result['permission']['decision'] == expected, (name, result)
                assert ('ask' in result['observed']) == should_ask, (name, result)
                if not should_ask:
                    assert result['permission']['rule'] == rule, result
                print(f'PASS: {name}')

            for approval in ('session', 'once'):
                first, second = run(approval=approval)
                assert 'ask' in first['observed'], first
                assert ('ask' in second['observed']) == (approval == 'once'), second
                if approval == 'session':
                    assert second['permission']['rule'] == rule, second
                else:
                    assert 'rule' not in second['permission'], second
                assert 'ask' in run()[0]['observed'], 'approval survived session end'
                print(f'PASS: {approval} approval and fresh-session expiry')

            def write(path, permissions):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({'permissions': permissions}))

            user = home / '.claude/settings.json'
            shared = project / '.claude/settings.json'
            for name, files, sources, expected in [
                ('user-level allow', [(user, {'allow': [rule]})], 'user', 'allow'),
                ('project-level allow in untrusted workspace', [(shared, {'allow': [rule]})],
                 'project', 'ask'),
                ('project-level allow', [(shared, {'allow': [rule]})], 'project', 'allow'),
                ('project deny beats user allow',
                 [(user, {'allow': [rule]}), (shared, {'deny': [rule]})], 'user,project', 'deny'),
                ('user allow ignored when source disabled', [(user, {'allow': [rule]})], '', 'ask'),
            ]:
                for path, permissions in files:
                    write(path, permissions)
                # Claude Code drops project allow rules until the workspace is trusted.
                trusted = 'untrusted' not in name
                (home / '.claude/.claude.json').write_text(json.dumps({'projects': {
                    str(project): {'hasTrustDialogAccepted': trusted}}}))
                result = run(sources=sources)[0]
                assert result['permission']['decision'] == expected, (name, result)
                assert ('ask' in result['observed']) == (expected != 'allow'), (name, result)
                if expected == 'allow':
                    assert result['permission']['rule'] == rule, (name, result)
                user.unlink(missing_ok=True)
                shared.unlink(missing_ok=True)
                print(f'PASS: {name}')

            result = run(approval='localSettings', sources='local')
            assert result[1]['permission']['rule'] == rule, result
            saved = project / '.claude/settings.local.json'
            assert rule in json.loads(saved.read_text())['permissions']['allow']
            result = run(sources='local')[0]
            assert result['permission']['rule'] == rule and 'ask' not in result['observed'], result
            print('PASS: persisted local approval in a fresh session')
            # Only the temporary fixture file is edited; the user's settings are untouched.
            saved.write_text('{"permissions":{"allow":[]}}')
            assert 'ask' in run(sources='local')[0]['observed']
            print('PASS: removing the saved rule restores the ask')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
