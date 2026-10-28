"""Self-created, synthetic production-like coverage profile 1.0.0.

No traffic weights, downloads, private media or codec-dependent membership.
Original artifacts created for Task 7.20 are dedicated to CC0-1.0.
Native encoder versions are pinned by manifest verification, not assumed portable.
"""
import hashlib
import io
import json
from pathlib import Path
import random

from PIL import Image, ImageDraw, features, __version__ as pillow_version

HERE = Path(__file__).resolve().parent
SEED = 7202026
MIMES = ('text/plain', 'image/png', 'image/jpeg', 'image/webp', 'image/gif')


def raster(width, height, kind, seed):
    rng = random.Random(seed)
    if kind == 'texture':
        # Grain/texture stress, explicitly not a real photograph.
        return Image.frombytes('RGB', (width, height), rng.randbytes(width * height * 3))
    image = Image.new('RGB', (width, height), '#edf0f4')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, max(1, height // 7)), fill='#172b4d')
    draw.text((8, 8), 'NODE OPERATIONS - WEEKLY REVIEW', fill='white')
    for i in range(8):
        y = height // 5 + i * max(1, height // 12)
        draw.text((8, y), f'Region {i+1}: {rng.randrange(150, 970)} accepted; {rng.randrange(2, 41)} queued', fill='#223344')
        x = width * 2 // 3
        draw.rectangle((x, y, min(width-1, x + rng.randrange(1, max(2, width//4))), min(height-1, y+5)), fill='#328e87')
    return image


def image_bytes(mime, width, height, kind, seed, animated=False):
    image = raster(width, height, kind, seed)
    stream = io.BytesIO()
    options = {
        'image/png': dict(format='PNG', compress_level=6, optimize=False),
        'image/jpeg': dict(format='JPEG', quality=91, optimize=False, progressive=False, subsampling=0),
        'image/webp': dict(format='WEBP', quality=88, method=4, lossless=False),
        'image/gif': dict(format='GIF', optimize=False),
    }[mime]
    if mime == 'image/gif':
        image = image.quantize(colors=256)
    if animated:
        options.update(save_all=True, append_images=[image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)], duration=[90, 110], loop=0)
    image.save(stream, **options)
    return stream.getvalue()


def near_limit(mime, cap, seed):
    # Membership chosen by original container size alone; never by codec savings.
    low, high, best = 1, 2200, None
    while low <= high:
        width = (low + high) // 2
        height = max(1, width * 3 // 4)
        raw = image_bytes(mime, width, height, 'texture', seed)
        if len(raw) <= cap:
            best = raw
            low = width + 1
        else:
            high = width - 1
    assert best is not None and cap * .90 <= len(best) <= cap
    return best


def narrative(size, seed):
    rng = random.Random(seed)
    regions = ['harbor', 'ridge', 'orchard', 'station', 'valley', 'meadow', 'crossing']
    actions = ['reviewed the replica inventory', 'checked the recovery checklist', 'scheduled a maintenance window',
               'compared pending submissions', 'inspected the daily audit report', 'confirmed the backup receipt']
    observations = ['The queue cleared before the next shift.', 'A retry completed without losing the original bytes.',
                    'Two operators confirmed the recorded result.', 'The evidence was retained for the weekly review.',
                    'The next shift will check the remaining items.', 'No additional capacity was requested.']
    chunks = []
    while sum(map(len, chunks)) < size:
        chunks.append(f'At {rng.randrange(24):02d}:{rng.randrange(60):02d}, the {rng.choice(regions)} team {rng.choice(actions)}. '
                      f'{rng.choice(observations)} Ticket {rng.randrange(100000,999999)} lists {rng.randrange(1,400)} objects.\n')
    # Byte-sized ASCII text; endpoint is deliberately canonical accepted text.
    return ''.join(chunks).encode()[:size-1].rstrip() + b'.'


def metadata(count, seed):
    rng = random.Random(seed)
    return json.dumps(dict(schema='operations-snapshot/1', window='2026-10-28', events=[
        dict(id=hashlib.sha256(f'{seed}:{i}'.encode()).hexdigest(), region=rng.choice(['east', 'west', 'central']),
             latency_ms=rng.randrange(10,900), size_bytes=rng.randrange(100,2000000),
             state=rng.choice(['accepted','queued','retry']), annotations=['verified original',f'shift-{i%3}'])
        for i in range(count)]), indent=2, sort_keys=True).encode()


def build():
    samples = []
    def add(name, mime, category, raw, origin, seed=None):
        samples.append(dict(id=name, mime=mime, category=category, raw=raw, origin=origin, seed=seed))
    for label, size in [('tiny', 48), ('small', 1024), ('medium', 32768), ('max', 262144)]:
        add('narrative-'+label, 'text/plain', 'plain_text', narrative(size, SEED+size),
            'Self-created seeded operations prose with varied events; synthetic, not human upload', SEED+size)
    for count in (1, 12, 128, 650):
        add(f'json-{count}', 'text/plain', 'structured_metadata_json', metadata(count, SEED+count),
            'Self-created nested operational events, unique digest IDs and varied numeric values', SEED+count)
    # Newly authored real benchmark implementation; no copied/private/licensing-unknown source.
    source = (HERE / 'corpus.py').read_bytes().replace(b'\r\n', b'\n').strip()
    bench = (HERE / 'measure.py').read_bytes().replace(b'\r\n', b'\n').strip()
    for label, raw in [('small', b'def sha256_bytes(value: bytes) -> str:\n    import hashlib\n    return hashlib.sha256(value).hexdigest()'),
                       ('module', source), ('suite', source+b'\n\n'+bench)]:
        add('source-'+label, 'text/plain', 'source_code', raw, 'Self-created Task 7.20 source, CC0-1.0; actual complete modules for larger members')
    rng = random.Random(SEED)
    alphabet = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    add('entropy-text', 'text/plain', 'high_entropy_text', bytes(alphabet[rng.randrange(64)] for _ in range(65536)),
        'Seeded uniform ASCII token stream; synthetic entropy control', SEED)
    for ordinal, mime in enumerate(MIMES[1:]):
        stem = mime.split('/')[1]
        seed = SEED + ordinal
        for label, width, height, kind in [('tiny',1,1,'texture'), ('small',320,180,'dashboard'), ('medium',512,384,'texture')]:
            add(stem+'-'+label, mime, mime, image_bytes(mime,width,height,kind,seed),
                f'Self-created {kind} raster; no camera/photo/production claim',seed)
        for label, cap in [('near-active',262144), ('near-v3',2097152)]:
            add(stem+'-'+label, mime, mime, near_limit(mime, cap, seed),
                'Self-created noise texture; deterministic dimension search for 90-100% original-container cap',seed)
        if mime in ('image/gif','image/webp'):
            add(stem+'-animated',mime,mime,image_bytes(mime,480,270,'dashboard',seed,True),
                'Self-created two-frame operations display; exact animation container retained',seed)
    assert {s['mime'] for s in samples} == set(MIMES)
    assert all(len(s['raw']) <= (262144 if s['mime']=='text/plain' else 2097152) for s in samples)
    return samples


def manifest(samples):
    return dict(profile='task720-production-like-v1', version='1.0.0', license='CC0-1.0 for newly created corpus artifacts',
        representativeness='Synthetic production-like coverage only; no real-world media or observed traffic weights',
        inclusion='All predeclared MIME/size/category members; no codec-dependent exclusions or weighting',
        generator='benchmarks/task720_v1/corpus.py', seed=SEED,
        environment=dict(pillow=pillow_version,jpeg=features.version_codec('jpg'),webp=features.version_module('webp')),
        sources={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('corpus.py','measure.py')},
        samples=[{k:v for k,v in s.items() if k!='raw'} | dict(size=len(s['raw']),sha256=hashlib.sha256(s['raw']).hexdigest()) for s in samples])
