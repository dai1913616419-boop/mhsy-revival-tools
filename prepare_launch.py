"""Prepare a separate Windows runtime and current client; leave source assets intact."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
# Private checkout contains the assets; public checkout uses its private sibling.
SOURCE = ROOT if (ROOT / 'work/apk').is_dir() else ROOT.parent / 'mhsy-offline-revival'
BUILD = ROOT / 'launch-build'
RUNTIME = Path('/mnt/c/mhsy-local')
args = argparse.ArgumentParser(description=__doc__)
args.add_argument('--mode', choices=('demo', 'opening'), default='demo')
args.add_argument('--host', default='192.168.1.104')
options = args.parse_args()
HOST = options.host
OPENING = options.mode == 'opening'
BUILD.mkdir(exist_ok=True)
RUNTIME.mkdir(exist_ok=True)

def module(name):
    spec = importlib.util.spec_from_file_location(name, SOURCE / 'server' / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

patcher = module('patch_login_system')
client = bytearray((SOURCE / 'work/apk/Client_patched6.bin').read_bytes())
sys.path.insert(0, str(BUILD))
from patch_prompt_stubs import patch_prompt_stubs
from test_prompt_stubs import verify_stub_bodies
client = patch_prompt_stubs(client)
verify_stub_bodies(client)
from patch_device_identifier import apply_patch as patch_device_identifier
client = bytearray(patch_device_identifier(client))
if OPENING:
    from restore_tutorial import restore_guide_click
    client = restore_guide_click(client, (SOURCE / 'work/apk/Client_4201.dll').read_bytes())
pe_offset = patcher.find_pe_offset(bytes(client))
start = pe_offset + patcher.US_URL_OFF
end = start + patcher.US_URL_LEN * 2
old = bytes(client[start:end]).decode('utf-16le')
assert old.startswith('http://192.168.0.12:80/Other/serverlist.txt'), old
list_name = 'opening.txt' if OPENING else 'serverlist.txt'
url = patcher.build_url(f'http://{HOST}/Other/{list_name}')
client[start:end] = url.encode('utf-16le')
client_path = BUILD / ('Client_opening.bin' if OPENING else 'Client_launch.bin')
client_path.write_bytes(client)

repack = module('repack_apk')
apk = BUILD / ('mhsy_opening.apk' if OPENING else 'mhsy_local_latest.apk')
sys.argv = ['repack_apk.py', '--apk', str(SOURCE / 'work/apk/mhsy_qihoo_4201.apk'),
            '--dll', str(client_path), '--out', str(apk)]
repack.main()

# Patch the Qihoo version resource explicitly; no emulator root/hosts needed.
version_patcher = module('patch_apk_version')
version_patcher.RES_PATH = 'assets/bin/Data/0b5196eb3ba028645999f84336a2252e'
with zipfile.ZipFile(apk) as z:
    original_version = z.read(version_patcher.RES_PATH)
patched_version = version_patcher.patch_res(original_version, HOST.encode('ascii'))
version_apk = BUILD / 'mhsy_local_latest.version.apk'
version_patcher.rebuild_apk(str(apk), str(version_apk), patched_version)
version_apk.replace(apk)

signer = module('sign_apk')
from cryptography.hazmat.primitives import serialization
from cryptography import x509
key_path = BUILD / 'local-signing-key.pem'
cert_path = BUILD / 'local-signing-cert.pem'
if not key_path.exists():
    key, cert = signer.make_keypair()
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
signer.make_keypair = lambda: (key, cert)
tmp = BUILD / 'mhsy_local_latest.signed.apk'
assert signer.sign(str(apk), str(tmp)) == 0
tmp.replace(apk)
with zipfile.ZipFile(apk) as z:
    assert z.testzip() is None
    assert z.read(repack.CLIENT_ENTRY) == client
    assert z.read(version_patcher.RES_PATH) == patched_version

# Preserve server runtime data across preparation reruns.
server = RUNTIME / 'server'
server.mkdir(exist_ok=True)
for p in (SOURCE / 'server').iterdir():
    if p.name in ('logs', '__pycache__'):
        continue
    dest = server / p.name
    if p.name == 'save.json' and dest.exists():
        continue
    if p.is_dir():
        shutil.copytree(p, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(p, dest)
if not (server / 'save.original.json').exists():
    shutil.copy2(server / 'save.json', server / 'save.original.json')
data_dest = RUNTIME / 'work/apk/luapack_extracted/GameData'
shutil.copytree(SOURCE / 'work/apk/luapack_extracted/GameData', data_dest, dirs_exist_ok=True)
list_path = server / 'www/Other/serverlist.txt'
list_path.write_text(list_path.read_text(encoding='utf-8').replace('192.168.0.12', HOST), encoding='utf-8')
if OPENING:
    opening_list = list_path.with_name('opening.txt')
    opening_list.write_text(list_path.read_text(encoding='utf-8').replace('9001', '9003').replace('本地服', '新手体验服'), encoding='utf-8')
# Contain update HTTP file resolution, in runtime copy only.
update = server / 'update_server.py'
text = update.read_text(encoding='utf-8')
text = text.replace('if os.path.isfile(cand):',
    'if os.path.commonpath([os.path.realpath(self.www), os.path.realpath(cand)]) == os.path.realpath(self.www) and os.path.isfile(cand):')
text = text.replace('if os.path.isfile(cand2):',
    'if os.path.commonpath([os.path.realpath(self.mirror), os.path.realpath(cand2)]) == os.path.realpath(self.mirror) and os.path.isfile(cand2):')
update.write_text(text, encoding='utf-8')
shutil.copy2(apk, RUNTIME / apk.name)
manifest = {'server_host': HOST, 'mode': options.mode,
    'client_revision': 'Client_patched6 + Mono-safe prompt stubs + stable offline device identifier + local endpoints' + (' + restored GuideClick' if OPENING else ''),
    'client_sha256': hashlib.sha256(client).hexdigest(),
    'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
    'runtime': str(RUNTIME), 'server_list_url': url}
(BUILD / ('opening-build-manifest.json' if OPENING else 'build-manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
