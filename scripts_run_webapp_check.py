import os, subprocess, sys, socket, time, urllib.request
port = 8765
env = os.environ.copy()
env['FLET_SERVER_PORT'] = str(port)
env['FLET_SERVER_ADDRESS'] = '127.0.0.1'
env['FLET_FORCE_WEB'] = 'true'
cmd = [sys.executable, '-m', 'flet', 'run', '--web', '--port', str(port), 'qwerty_webapp/app/app.py']
proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
# wait for port
deadline = time.time()+25
ready=False
while time.time()<deadline:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            ready=True
            break
    except OSError:
        time.sleep(0.25)
print('READY', ready)
if ready:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}', timeout=3) as resp:
            print('HTTP', resp.status)
    except Exception as e:
        print('HTTP_ERR', e)
# shutdown
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
try:
    out = proc.stdout.read().decode(errors='ignore') if proc.stdout else ''
except Exception:
    out = ''
print('OUT_BEGIN')
print('\n'.join(out.splitlines()[:50]))
print('OUT_END')
