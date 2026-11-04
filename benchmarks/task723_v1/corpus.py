"""Task 7.23 synthetic meme coverage v1.0.0. New artifacts dedicated to CC0-1.0.

Fixed factorial coverage and original-size boundary search, no codec scoring.
No downloaded, private or production media. No traffic weights are inferred.
"""
import hashlib
import io
import random
from PIL import Image, ImageDraw

SEED = 7232026
CAPS = (128*1024, 256*1024, 512*1024, 1024*1024, 2*1024*1024)
STATIC = ('image/jpeg', 'image/png', 'image/webp')


def render(w, h, kind, seed, frame=0):
    rng = random.Random(seed + frame)
    if kind == 'texture':
        im = Image.frombytes('RGB', (w, h), rng.randbytes(w*h*3))
    else:
        im = Image.new('RGBA' if kind == 'transparent' else 'RGB', (w, h),
                       (0, 0, 0, 0) if kind == 'transparent' else '#e8eef4')
    d = ImageDraw.Draw(im)
    if kind == 'screenshot':
        d.rectangle((0, 0, w, h//8), fill='#23354b')
        for n in range(10):
            d.text((12, h//7+n*max(12, h//14)),
                   f'friend {n}: I saved it as final_final_{n}.png', fill='#23354b')
        caption = 'WHEN THE GROUP CHAT BECOMES THE BACKUP'
    elif kind == 'macro':
        d.rectangle((0, h//2, w, h), fill='#7fbba9')
        d.text((12, h//4), 'ME: JUST ONE SMALL MEME', fill='black')
        caption = 'ALSO ME: FOURTEEN SIGNED REVIEWS'
    elif kind in ('caption', 'transparent'):
        x = w//2 + frame*5
        d.ellipse((x-w//6, h//4, x+w//6, h*3//4), fill='#eb815a')
        d.ellipse((x-w//12, h//3, x-w//16, h//3+8), fill='black')
        d.ellipse((x+w//16, h//3, x+w//12, h//3+8), fill='black')
        caption = 'WHEN YOUR MEME NEEDS ITS OWN HARD DRIVE'
    else:
        caption = 'HIGH DETAIL, LOW DISK SPACE'
    d.rectangle((0, 0, w, 24), fill='#152333')
    d.text((5, 6), caption, fill='white')
    return im


def encode(mime, w, h, kind, seed, animated=False):
    images = [render(w, h, kind, seed, f) for f in range(2 if animated else 1)]
    if mime == 'image/gif':
        images = [im.convert('RGB').quantize(colors=256) for im in images]
    stream = io.BytesIO()
    options = {
        'image/jpeg': dict(format='JPEG', quality=90, subsampling=0, optimize=False),
        'image/png': dict(format='PNG', compress_level=6, optimize=False),
        'image/webp': dict(format='WEBP', quality=88, method=4, lossless=False),
        'image/gif': dict(format='GIF', optimize=False),
    }[mime]
    if animated:
        options.update(save_all=True, append_images=images[1:], duration=[120, 180], loop=0)
    images[0].save(stream, **options)
    return stream.getvalue()


def boundary(mime, cap, seed, animated):
    lo, hi, best = 16, 2200, None
    # No outer compression, runtime or selection outcome participates here.
    while lo <= hi:
        w = (lo+hi)//2
        raw = encode(mime, w, w*3//4, 'texture', seed, animated)
        if len(raw) <= cap:
            best = raw
            lo = w+1
        else:
            hi = w-1
    assert best and .90*cap <= len(best) <= cap
    return best


def build():
    samples = []
    def add(sid, mime, kind, raw, method, target=None):
        if mime == 'text/plain':
            dims = dict(width=None, height=None, frames=None, aggregate_pixels=None, transparent=False)
        else:
            with Image.open(io.BytesIO(raw)) as im:
                frames = getattr(im, 'n_frames', 1)
                dims = dict(width=im.width, height=im.height, frames=frames,
                            aggregate_pixels=im.width*im.height*frames,
                            transparent='A' in im.getbands() or 'transparency' in im.info)
                for i in range(frames):
                    im.seek(i)
                    im.load()
        samples.append(dict(id=sid, mime=mime, category=kind, raw=raw,
            original_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), **dims,
            construction=method, target_bytes=target, license='CC0-1.0',
            provenance='Self-created Task 7.23; procedural raster/text, Pillow default font; seed 7232026',
            dataset=mime.removeprefix('image/'), synthetic=True, production_traffic=False))
    for mi, mime in enumerate(STATIC):
        for ki, kind in enumerate(('caption', 'screenshot', 'macro', 'texture')):
            for w, h in ((320, 240), (1280, 960)):
                sid = f'{mime[6:]}-{kind}-{w}'
                add(sid, mime, kind, encode(mime,w,h,kind,SEED+mi*100+ki),
                    f'Fixed factorial raster {w}x{h}; format settings in encode()')
        for ci, cap in enumerate(CAPS):
            add(f'{mime[6:]}-boundary-{cap}',mime,'size-boundary',
                boundary(mime,cap,SEED+mi*100+ci,False),
                'Bisection of texture dimensions by original file size only',cap)
    for w, h in ((320,240),(1280,960)):
        add(f'png-transparent-{w}','image/png','transparent',
            encode('image/png',w,h,'transparent',SEED), 'Self-drawn transparent RGBA sticker')
    for kind in ('caption','texture'):
        for w,h in ((160,120),(640,480)):
            add(f'gif-{kind}-{w}','image/gif','animation-'+kind,
                encode('image/gif',w,h,kind,SEED,True),'Two distinct frames, fixed 120/180 ms')
    for ci, cap in enumerate(CAPS):
        add(f'gif-boundary-{cap}','image/gif','animation-boundary',
            boundary('image/gif',cap,SEED+ci,True),'Two-frame noise; original-size bisection only',cap)
    add('webp-animation','image/webp','animation-caption',
        encode('image/webp',320,240,'caption',SEED,True),'Two-frame WebP supported-MIME control')
    for n in (8,64,512,4096,16384,65536,262144):
        rng = random.Random(SEED+n)
        lines = []
        while sum(map(len,lines)) < n:
            lines.append(rng.choice(('me: one more meme. ', 'disk: please have mercy. ',
                        'friend: is this the final version? ', 'node: receipts included. ')))
        raw = ''.join(lines).encode()[:n-1].rstrip()+b'!'
        raw = raw.ljust(n,b'!')
        add(f'text-{n}','text/plain','text-meme',raw,'Seeded original quips, exact ASCII byte length',n)
    raw = b'bmozvaibkgjhevxdmqzukt0c328pqlcgchkq90vew8mgc394iojl7lc8ycj3kn2fdjeaiphe490948m1tbb577bbqbm52hfmpftgkea0'
    add('text-expansion-control','text/plain','diagnostic-control',raw,
        'Public self-created Task 7.22 counterexample; separate diagnostic, never primary coverage')
    return samples


def manifest(samples):
    return dict(version='1.0.0',seed=SEED,license='CC0-1.0',
        selection='Fixed semantic factorial plus five original-size boundaries per format; equal records, no traffic weighting',
        samples=[{k:v for k,v in s.items() if k!='raw'} for s in samples])
