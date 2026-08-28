import collections
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import uuid

MAGIC = b'bw'
KEY_PREFIX = 'bw-source +cipher'
PROFILE_DIR = 'blocksworld_develop'
PROFILE_DIRS = ('Blocksworld', 'blocksworld_develop')
GAME_PROCESSES = ('blocksworld.exe', 'blocksworld')
PARALLEL_KEYS = ('connections', 'connectionTypes', 'frozen-in-terrain')
HOME = os.path.expanduser('~')
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'transfer.log')
KNOWN_PREFIXES = (
    b'{\n "blocks":[\n  {"tile-rows":[[{"type":"tile"',
    b'[{"tile-rows":[[{"type":"tile","gaf":{"predicate"',
    b'{\n  "blocks":[\n  {"tile-rows":[[{"type":"tile"',
)

def log(message='', screen=True):
    if screen:
        print(message)
    redacted = re.sub(re.escape(HOME), '~', message, flags=re.IGNORECASE)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as handle:
            handle.write(redacted + '\n')
    except OSError:
        pass

def key_for(author_id):
    return f'{KEY_PREFIX}{author_id}'.encode('ascii')

def xor_with(data, key):
    if not data:
        return b''
    stream = (key * (len(data) // len(key) + 1))[:len(data)]
    combined = int.from_bytes(data, 'big') ^ int.from_bytes(stream, 'big')
    return combined.to_bytes(len(data), 'big')

def decrypt(raw, author_id):
    if raw[:2] != MAGIC:
        raise ValueError('not a .bw file')
    return xor_with(raw[2:], key_for(author_id))

def encrypt(plain, author_id):
    return MAGIC + xor_with(plain, key_for(author_id))

def recover_author_id(raw):
    body = raw[2:]
    prefix_length = len(KEY_PREFIX)
    for known in KNOWN_PREFIXES:
        span = min(len(known), len(body))
        stream = bytes(a ^ b for a, b in zip(body[:span], known[:span]))
        if not stream.startswith(KEY_PREFIX.encode('ascii')):
            continue
        digits = ''
        for byte in stream[prefix_length:]:
            if not chr(byte).isdigit():
                break
            digits += chr(byte)
        for length in range(len(digits), 0, -1):
            try:
                json.loads(decrypt(raw, digits[:length]).decode('utf-8'))
                return int(digits[:length])
            except Exception:
                continue
    return None

def find_bw_file(folder):
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith('.bw'))
    if 'source.bw' in names:
        return 'source.bw'
    return names[0] if names else None

def find_metadata_file(folder):
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith('.json'))
    if 'metadata.json' in names:
        return 'metadata.json'
    return names[0] if names else None

def read_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)

def write_json(path, payload):
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, separators=(',', ':')))

def block_signature(blocks):
    digest = hashlib.md5()
    for block in blocks:
        digest.update(json.dumps(block, sort_keys=True, separators=(',', ':')).encode('utf-8'))
        digest.update(b'\x00')
    return digest.hexdigest()

class Item:
    def __init__(self, path, bw_name, metadata_name, metadata, payload):
        self.path = path
        self.bw_name = bw_name
        self.metadata_name = metadata_name
        self.metadata = metadata
        self.kind = 'model' if isinstance(payload, list) else 'world'
        blocks = payload if self.kind == 'model' else payload.get('blocks', [])
        self.block_count = len(blocks)
        self.signature = block_signature(blocks)
        self.problems = []
        if self.kind == 'world':
            self.problems = [f'{key} does not match the block count' for key in PARALLEL_KEYS if len(payload.get(key, [])) != len(blocks)]
        self.title = (metadata.get('title') or '').strip() or 'Untitled'
        self.author_id = metadata['author_id']
        self.updated_at = metadata.get('updated_at') or ''

def load_item(folder):
    bw_name = find_bw_file(folder)
    if bw_name is None:
        return None, 'no .bw file'
    with open(os.path.join(folder, bw_name), 'rb') as handle:
        raw = handle.read()
    metadata = {}
    metadata_name = find_metadata_file(folder)
    if metadata_name:
        try:
            metadata = read_json(os.path.join(folder, metadata_name))
        except Exception:
            metadata = {}
    payload = None
    if metadata.get('author_id') is not None:
        try:
            payload = json.loads(decrypt(raw, metadata['author_id']).decode('utf-8'))
        except Exception:
            payload = None
    if payload is None:
        recovered = recover_author_id(raw)
        if recovered is None:
            return None, 'cannot tell which account this belongs to'
        metadata['author_id'] = recovered
        payload = json.loads(decrypt(raw, recovered).decode('utf-8'))
    return Item(folder, bw_name, metadata_name, metadata, payload), None

def progress(label, done, total):
    width = 30
    filled = width * done // total
    print(f'\r  {label:<16} [{"#" * filled}{"." * (width - filled)}] {done}/{total}', end='', flush=True)
    if done == total:
        print()
        log(f'  {label:<16} {total} read', screen=False)

def scan_library(root, label=None):
    if find_bw_file(root):
        item, reason = load_item(root)
        return ([item], []) if item else ([], [(os.path.basename(root), reason)])
    folders = [os.path.join(root, name) for name in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, name))]
    items, unreadable = [], []
    for number, folder in enumerate(folders, 1):
        item, reason = load_item(folder)
        if item is None:
            unreadable.append((os.path.basename(folder), reason))
        else:
            items.append(item)
        if label:
            progress(label, number, len(folders))
    return items, unreadable

def looks_like_library(folder):
    try:
        for name in os.listdir(folder):
            sub = os.path.join(folder, name)
            if os.path.isdir(sub) and find_bw_file(sub):
                return True
    except OSError:
        pass
    return False

def libraries_under(path):
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return []
    if find_bw_file(path):
        return [path]
    if os.path.basename(path).lower() in ('worlds', 'models'):
        return [path]
    children = [os.path.join(path, name) for name in ('worlds', 'models') if os.path.isdir(os.path.join(path, name))]
    if children:
        return children
    if looks_like_library(path):
        return [path]
    return []

def find_profile_dirs():
    playtest = os.path.join('Fortell Games', 'Blocksworld', PROFILE_DIR)
    roots = [HOME, os.path.join(HOME, 'OneDrive')]
    for steam in (os.path.join(HOME, '.steam', 'steam'), os.path.join(HOME, '.local', 'share', 'Steam')):
        roots.append(os.path.join(steam, 'steamapps', 'compatdata', '*', 'pfx', 'drive_c', 'users', 'steamuser'))
    patterns = []
    for root in roots:
        for name in PROFILE_DIRS:
            patterns.append(os.path.join(root, 'Documents', name))
        patterns.append(os.path.join(root, 'AppData', 'LocalLow', playtest))
        patterns.append(os.path.join(root, 'Library', 'Application Support', playtest))
    found = []
    for pattern in patterns:
        found.extend(path for path in sorted(glob.glob(pattern)) if os.path.isdir(path))
    return found

def find_accounts():
    accounts = []
    for profile_dir in find_profile_dirs():
        for name in sorted(os.listdir(profile_dir)):
            folder = os.path.join(profile_dir, name)
            if os.path.isdir(folder) and any(looks_like_library(library) for library in libraries_under(folder)):
                accounts.append(folder)
    return accounts

def label_for(folder):
    lowered = folder.lower()
    if 'fortell' in lowered:
        return 'Playtest'
    if PROFILE_DIR not in lowered and os.sep + 'blocksworld' + os.sep not in lowered:
        return None
    if 'onedrive' in lowered:
        return 'Original (OneDrive)'
    return 'Original'

def describe_account(folder):
    counts, authors = [], collections.Counter()
    for library in libraries_under(folder):
        total = 0
        for name in os.listdir(library):
            sub = os.path.join(library, name)
            try:
                if not os.path.isdir(sub) or not find_bw_file(sub):
                    continue
                total += 1
                metadata_name = find_metadata_file(sub)
                author_id = read_json(os.path.join(sub, metadata_name)).get('author_id') if metadata_name else None
                if author_id is not None:
                    authors[author_id] += 1
            except Exception:
                continue
        counts.append(f'{total} {os.path.basename(library)}')
    account = authors.most_common(1)[0][0] if authors else 'unknown'
    return f'{label_for(folder) or "Folder"}   account {account}   {", ".join(counts)}\n     {folder}'

def browse():
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        picked = filedialog.askdirectory(title='Pick an account folder, a worlds or models folder, or a single world or model')
        root.destroy()
        return picked or None
    except Exception:
        try:
            return input('paste the folder path: ').strip().strip('"') or None
        except EOFError:
            return None

def choose(prompt, options, what, default=None):
    if default:
        hint = f'Enter for {options.index(default) + 1}, or browse for {what} (b)'
    else:
        hint = ('1 or ' if len(options) == 1 else f'1-{len(options)} or ' if options else '') + f'browse for {what} (b)'
    while True:
        try:
            answer = input(f'{prompt} [{hint}]: ').strip()
        except EOFError:
            sys.exit('aborted')
        log(f'> {answer}', screen=False)
        if answer == '' and default:
            return default
        if answer.isdigit() and options and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if answer.lower() in ('b', 'browse'):
            picked = browse()
            if picked:
                log(f'> {picked}', screen=False)
                return picked
            continue
        if os.path.isdir(answer.strip('"')):
            return answer.strip('"')
        log(f'  type a number from 1 to {len(options)}, b to browse, or paste a folder path' if options else '  type b to browse, or paste a folder path')

def game_is_running():
    try:
        if sys.platform.startswith('win'):
            output = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq Blocksworld.exe'], stderr=subprocess.DEVNULL)
        else:
            output = subprocess.check_output(['ps', '-A'], stderr=subprocess.DEVNULL)
    except Exception:
        return None
    text = output.decode('utf-8', 'replace').lower()
    return any(name in text for name in GAME_PROCESSES)

def now():
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

def world_metadata(template, source, destination, author_id, picture):
    metadata = dict(template)
    metadata['author_id'] = author_id
    metadata['id'] = ''
    metadata['fileId'] = 0
    metadata['ugcID'] = 0
    metadata['local_world_id'] = os.path.basename(destination)
    metadata['title'] = source.title
    metadata['description'] = source.metadata.get('description') or ''
    for field in ('remixed_from_author_id', 'remixed_from_author_username', 'is_downloaded_copy'):
        if field in source.metadata:
            metadata[field] = source.metadata[field]
    metadata['block_count'] = source.block_count
    metadata['created_at'] = source.metadata.get('created_at') or now()
    metadata['updated_at'] = source.updated_at or now()
    metadata['local_changed_source'] = 1
    metadata['local_changed_metadata'] = 1
    metadata['local_changed_screenshot'] = 1 if picture else 0
    metadata['screenshot_checksum'] = None
    metadata['image_urls_for_sizes'] = {'1024x768': picture or '', '512x384': picture or ''}
    for field in ('icon_url', 'image_url', 'author_profile_image_url'):
        if field in metadata:
            metadata[field] = ''
    return metadata

def model_metadata(template, source, destination, author_id, picture):
    metadata = dict(source.metadata)
    metadata['author_id'] = author_id
    for field in ('id', 'u2u_model_id', 'image_url'):
        metadata.pop(field, None)
    for field in ('asset_ulid', 'asset_uuid', 'public_author_id'):
        if field in template:
            metadata[field] = template[field]
    metadata['fileId'] = 0
    metadata['ugcId'] = 0
    metadata['local_id'] = os.path.basename(destination)
    metadata['title'] = source.title
    metadata['short_title'] = source.title[:32]
    metadata['icon_url'] = None
    metadata['author_profile_image_url'] = ''
    metadata['local_changed_metadata'] = True
    metadata['updated_at'] = source.updated_at or now()
    return metadata

def find_picture(folder, stems):
    best = None
    for name in os.listdir(folder):
        stem, extension = os.path.splitext(name)
        if extension.lower() in ('.png', '.jpg', '.jpeg') and stem.lower().startswith(stems):
            size = os.stat(os.path.join(folder, name)).st_size
            if best is None or size > best[1]:
                best = (name, size)
    return best[0] if best else None

def copy_times(source_path, destination_path):
    try:
        info = os.stat(source_path)
        os.utime(destination_path, (info.st_atime, info.st_mtime))
    except OSError:
        pass

def transfer(source, library, author_id, template):
    if source.problems:
        raise RuntimeError('; '.join(source.problems))
    with open(os.path.join(source.path, source.bw_name), 'rb') as handle:
        raw = handle.read()
    plain = decrypt(raw, source.author_id)
    payload = encrypt(plain, author_id)
    if decrypt(payload, author_id) != plain:
        raise RuntimeError('re-encryption did not round trip')
    destination = os.path.join(library, str(uuid.uuid4()))
    os.makedirs(destination)
    try:
        target = os.path.join(destination, 'source.bw')
        with open(target, 'wb') as handle:
            handle.write(payload)
        stems = ('screenshot',) if source.kind == 'world' else ('image', 'iconhd', 'iconsd')
        picture = find_picture(source.path, stems)
        picture_path = None
        if picture:
            base = 'screenshot' if source.kind == 'world' else 'iconHD'
            picture_path = os.path.join(destination, base + os.path.splitext(picture)[1].lower())
            shutil.copyfile(os.path.join(source.path, picture), picture_path)
            copy_times(os.path.join(source.path, picture), picture_path)
        builder = world_metadata if source.kind == 'world' else model_metadata
        metadata = builder(template, source, destination, author_id, picture_path)
        metadata_path = os.path.join(destination, 'metadata.json')
        write_json(metadata_path, metadata)
        with open(target, 'rb') as handle:
            written = handle.read()
        if written != payload:
            raise RuntimeError('the written file does not match')
        check, _ = load_item(destination)
        if check is None or check.signature != source.signature:
            raise RuntimeError('verification failed after writing')
        copy_times(os.path.join(source.path, source.bw_name), target)
        if source.metadata_name:
            copy_times(os.path.join(source.path, source.metadata_name), metadata_path)
        copy_times(source.path, destination)
        return destination
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise

def resolve(path, label):
    libraries = libraries_under(path)
    if not libraries:
        sys.exit(f'{label} has no Blocksworld worlds or models under it: {path}')
    return libraries

def index_destination(libraries):
    present, items = {}, []
    for library in libraries:
        found, _ = scan_library(library, 'checking ' + os.path.basename(library))
        for item in found:
            present[item.signature] = item
            items.append(item)
    return present, items

def newest_only(items):
    newest = {}
    for item in items:
        held = newest.get(item.signature)
        if held is None or item.updated_at > held.updated_at:
            newest[item.signature] = item
    return list(newest.values())

def describe_side(path, items):
    label = label_for(path)
    author_id = collections.Counter(item.author_id for item in items).most_common(1)[0][0]
    return f'{label + ", " if label else ""}account {author_id}', os.path.abspath(path)

def ask(question, choices):
    while True:
        try:
            answer = input(f'{question} [{"/".join(choices)}]: ').strip().lower()
        except EOFError:
            return 'n'
        log(f'> {answer}', screen=False)
        if answer == 'yes':
            answer = 'y'
        if answer == 'no':
            answer = 'n'
        if answer in choices:
            return answer
        log(f'  type {" or ".join(choices)}')

def confirm(question):
    return ask(question, ('y', 'n')) == 'y'

def pick_accounts():
    accounts = find_accounts()
    log('found these Blocksworld accounts:' if accounts else 'no Blocksworld accounts found')
    for number, account in enumerate(accounts, 1):
        log(f'  {number}. {describe_account(account)}')
    log()
    if len(accounts) == 1:
        log('only one account was found. If the other game has never saved a world or model on')
        log('this computer there is nothing to find yet: start it, save one, and run this again.')
        log()
    log('world data and model data are ready to be transferred')
    log('select a destination account, then select the account with the data you want to transfer from')
    log('or b to browse, letting you import single world/model folders, or another folder containing your world/model data')
    log()
    destination_path = choose('select a destination account to transfer your data into', accounts, 'destination')
    default = accounts[1 - accounts.index(destination_path)] if len(accounts) == 2 and destination_path in accounts else None
    source_path = choose('which account has the data you want to transfer from?', accounts, 'data', default)
    while source_path == destination_path:
        log('  that is the same account, pick a different one or b to browse')
        source_path = choose('which account has the data you want to transfer from?', accounts, 'data', default)
    return source_path, destination_path

def plan(source_path, destination_path):
    source_libraries = resolve(source_path, 'the folder to copy from')
    destination_libraries = resolve(destination_path, 'the destination')
    overlap = set(map(os.path.normcase, source_libraries)) & set(map(os.path.normcase, destination_libraries))
    if overlap:
        sys.exit('the destination and the folder to copy from are the same place')
    if any(find_bw_file(library) for library in destination_libraries):
        sys.exit('the destination must be an account folder or a worlds or models folder, not a single world or model')

    source_items, unreadable = [], []
    for library in source_libraries:
        found, bad = scan_library(library, 'reading ' + os.path.basename(library))
        source_items.extend(found)
        unreadable.extend(bad)
    if not source_items:
        sys.exit('nothing readable to copy from')

    present, destination_items = index_destination(destination_libraries)
    if not destination_items:
        sys.exit('the destination is empty; save one world or model in that game first, the tool copies how the game lays out its files from an existing one')
    author_counts = collections.Counter(item.author_id for item in destination_items)
    author_id = author_counts.most_common(1)[0][0]

    templates, libraries_by_kind = {}, {}
    for library in destination_libraries:
        found = [item for item in destination_items if os.path.dirname(item.path) == library]
        base = os.path.basename(library).lower()
        kind = base[:-1] if base in ('worlds', 'models') else (found[0].kind if found else None)
        if kind:
            libraries_by_kind[kind] = library
            if found:
                templates[kind] = found[0].metadata

    pending, skipped = [], collections.Counter()
    for item in newest_only(source_items):
        if item.signature in present:
            skipped['already in the destination account'] += 1
        elif item.kind not in templates:
            skipped[f'the destination account has no {item.kind} yet to copy the file layout from'] += 1
        else:
            pending.append(item)
    pending.sort(key=lambda item: (item.kind, -item.block_count))

    log()
    what, where = describe_side(source_path, source_items)
    log(f'copying from  {what}')
    log(f'              {where}')
    what, where = describe_side(destination_path, destination_items)
    log(f'destination   {what}')
    log(f'              {where}')
    log()
    for item in pending:
        log(f'  {item.kind:<6} {item.title[:44]:<44} {item.block_count:>8,} blocks')
    for reason, count in sorted(skipped.items()):
        log(f'  skipping {count}: {reason}')
    if unreadable:
        log(f'  skipping {len(unreadable)} empty or unfinished folder{"" if len(unreadable) == 1 else "s"}')
        for name, reason in unreadable:
            log(f'    {name}: {reason}', screen=False)
    return pending, libraries_by_kind, templates, author_id

def main():
    arguments = sys.argv[1:]
    log(f'--- {now()}  python {sys.version.split()[0]}  {sys.platform}  arguments {arguments}', screen=False)
    if len(arguments) not in (0, 2):
        sys.exit('usage: python transfer.py [copy_from copy_into]')
    while True:
        source_path, destination_path = arguments if arguments else pick_accounts()
        pending, libraries_by_kind, templates, author_id = plan(source_path, destination_path)
        if arguments:
            if not pending:
                log('nothing to do')
                return
            if not confirm(f'transfer {len(pending)} item(s)?'):
                sys.exit('aborted')
            break
        if not pending:
            if ask('nothing to do. r to pick the accounts again, n to quit', ('r', 'n')) == 'n':
                return
            log()
            continue
        answer = ask(f'transfer {len(pending)} item(s)? y to transfer, n to quit, r to pick the accounts again', ('y', 'n', 'r'))
        if answer == 'y':
            break
        if answer == 'n':
            sys.exit('aborted')
        log()

    running = game_is_running()
    if running:
        sys.exit('Blocksworld is running, close it first')
    if running is None and not confirm('could not check whether Blocksworld is running, make sure it is closed.'):
        sys.exit('aborted')

    done = failed = 0
    for number, item in enumerate(pending, 1):
        count = f'{number}/{len(pending)}'
        try:
            destination = transfer(item, libraries_by_kind[item.kind], author_id, templates[item.kind])
            done += 1
            log(f'  ok     {count:>9}  {item.title[:44]:<44} -> {os.path.basename(destination)}')
        except Exception as error:
            failed += 1
            log(f'  FAILED {count:>9}  {item.title}: {error}')

    log()
    if failed:
        log(f'Finished with problems: {done} transferred, {failed} failed. The failures are listed above and in transfer.log.')
    else:
        log(f'Task finished. {done} item{"" if done == 1 else "s"} transferred and verified. Start Blocksworld to see {"it" if done == 1 else "them"}.')

if __name__ == '__main__':
    sys.stdout.reconfigure(errors='replace')
    code = 0
    try:
        main()
    except SystemExit as stop:
        code = stop.code
        if isinstance(code, str):
            log(code)
            code = 1
    except KeyboardInterrupt:
        log('interrupted')
        code = 1
    except Exception:
        log(traceback.format_exc())
        code = 1
    if not sys.argv[1:]:
        try:
            input('press enter to close')
        except EOFError:
            pass
    sys.exit(code)
