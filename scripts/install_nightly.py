"""Install/update only this repository's cron entry, preserving other entries."""
import argparse
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
MARKER = "# job-seeking-nightly:" + str(BASE)


def merge_crontab(existing, line):
    lines = [s for s in existing.splitlines() if not s.endswith(MARKER)]
    lines.append(line + " " + MARKER)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ai', action='store_true')
    args = parser.parse_args()
    command = [sys.executable, str(BASE / 'career.py'), 'cron']
    if args.ai:
        command.append('--ai')
    line = subprocess.check_output(command, text=True).strip()
    old = subprocess.run(['crontab', '-l'], text=True, capture_output=True)
    if old.returncode and 'no crontab for' not in old.stderr:
        raise RuntimeError('Unable to read existing crontab: ' + old.stderr)
    content = merge_crontab(old.stdout, line)
    out = BASE / 'output'
    out.mkdir(exist_ok=True)
    (out / 'crontab.before-install.txt').write_text(old.stdout)
    subprocess.run(['crontab', '-'], input=content, text=True, check=True)
    installed = subprocess.check_output(['crontab', '-l'], text=True)
    if line + ' ' + MARKER not in installed.splitlines():
        raise RuntimeError('Installed cron entry did not verify')
    print('Verified nightly update at 02:00 local time; AI ' + ('enabled' if args.ai else 'disabled'))


if __name__ == '__main__':
    main()
