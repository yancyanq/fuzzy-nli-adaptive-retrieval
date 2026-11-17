#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/group13-v3-p0"
trap 'rc=$?; printf "%s\n" "$rc" >logs/env-mirror.status; exit "$rc"' EXIT
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1
mirror=https://mirrors.tencentyun.com/pypi/simple
wheel=vllm-0.8.5-cp38-abi3-manylinux1_x86_64.whl
python3 - <<'PY'
from html.parser import HTMLParser
from pathlib import Path
import json
from urllib.parse import urljoin
from urllib.request import urlopen
base='https://mirrors.tencentyun.com/pypi/simple/vllm/'
wheel='vllm-0.8.5-cp38-abi3-manylinux1_x86_64.whl'
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            self.hrefs.extend(v for k,v in attrs if k=='href' and v and wheel in v)
with urlopen(base,timeout=15) as response: content=response.read()
links=Links(); links.feed(content.decode())
assert len(links.hrefs)==1
with urlopen('https://pypi.org/pypi/vllm/0.8.5/json',timeout=15) as response:
    official=next(r for r in json.load(response)['urls'] if r['filename']==wheel)
Path('wheels/vllm-url.txt').write_text(urljoin(base,links.hrefs[0].split('#')[0])+"\n")
Path('wheels/vllm-sha.txt').write_text(official['digests']['sha256']+"\n")
Path('wheels/vllm-size.txt').write_text(str(official['size'])+"\n")
PY
if ! test -f "wheels/$wheel" || ! printf '%s  %s\n' "$(cat wheels/vllm-sha.txt)" "wheels/$wheel" | sha256sum -c -; then
  saved=0
  if test -f "wheels/$wheel.part"; then saved=$(stat -c %s "wheels/$wheel.part"); fi
  if test "$saved" -lt "$(cat wheels/vllm-size.txt)"; then
    curl -fLsS --connect-timeout 12 --speed-limit 16384 --speed-time 90 --retry 3 -C - \
      -o "wheels/$wheel.part" "$(cat wheels/vllm-url.txt)"
  fi
  printf '%s  %s\n' "$(cat wheels/vllm-sha.txt)" "wheels/$wheel.part" | sha256sum -c -
  mv "wheels/$wheel.part" "wheels/$wheel"
fi
python3 -m pip install --index-url "$mirror" --timeout 45 --retries 3 --target "$PWD/bootstrap" \
  --cache-dir "$PWD/pip-cache" 'pip==24.3.1'
PYTHONPATH="$PWD/bootstrap" python3 -m pip install --index-url "$mirror" --timeout 45 --retries 3 \
  --target "$PWD/packages" --cache-dir "$PWD/pip-cache" --report "$PWD/logs/pip-mirror-report.json" \
  "$PWD/wheels/$wheel" 'torch==2.6.0' 'xformers==0.0.29.post2' 'transformers==4.51.3' \
  'openai==1.76.2' 'rank_bm25==0.2.2' 'setuptools==80.9.0'
python3 - <<'PY'
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

def verified(row):
    metadata=row['metadata']
    name, version=metadata['name'],metadata['version']
    expected=row['download_info']['archive_info']['hashes']['sha256']
    with urlopen(f'https://pypi.org/pypi/{quote(name,safe="")}/{quote(version,safe="")}/json',timeout=20) as response:
        official=json.load(response)
    if expected not in {item['digests']['sha256'] for item in official['urls']}:
        raise ValueError(f'PyPI SHA-256 mismatch for {name} {version}')
    return name, version, expected

report=json.loads(Path('logs/pip-mirror-report.json').read_text())
with ThreadPoolExecutor(max_workers=8) as pool:
    artifacts=sorted(pool.map(verified,report['install']))
Path('logs/pypi-verified-artifacts.tsv').write_text(''.join('\t'.join(row)+'\n' for row in artifacts))
print(f'{len(artifacts)} package files checked against official PyPI SHA-256')
PY
PYTHONPATH="$PWD/packages" python3 - <<'PY'
from importlib.metadata import version
import torch
for name in ('vllm','torch','xformers','transformers','openai','rank-bm25','tokenizers','setuptools'):
    print(name, version(name))
print('torch runtime', torch.__version__, 'CUDA', torch.version.cuda)
assert torch.cuda.is_available()
x=torch.arange(3, device='cuda:0')
torch.cuda.synchronize()
print('CUDA smoke',torch.cuda.get_device_name(0),x.tolist())
PY
