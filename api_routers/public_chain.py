"""Public Chain API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals so existing api monkeypatches remain effective."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.get('/sync')
@api_limit("chain_sync")
async def sync_blockchain(request: Request):
    """Returns the latest blockchain state for syncing with other nodes."""
    _sync_runtime_globals()
    return {"chain": blockchain.get_chain()}


@router.get('/chain')
@api_limit("public_read")
async def get_chain(request: Request):
    """Retrieve the blockchain."""
    _sync_runtime_globals()
    return {"chain": [_serialize_block(block) for block in blockchain.chain]}


@router.get('/chain/summary')
@api_limit("public_read")
async def chain_summary(request: Request):
    _sync_runtime_globals()
    return _chain_summary_payload()


@router.get('/chain/blocks')
@api_limit("public_read")
async def chain_blocks(request: Request, from_height: int = 0, include_media_bytes: bool = False):
    _sync_runtime_globals()
    if from_height < 0:
        raise HTTPException(status_code=400, detail="from_height must be non-negative.")

    blocks = [
        block
        for block in blockchain.chain
        if block.index >= from_height
    ]
    certificate_ids = {
        block.certificate_id
        for block in blocks
        if block.certificate_id
    }
    return {
        "blocks": [
            _serialize_block(block, include_media_bytes=include_media_bytes)
            for block in blocks
        ],
        "certificates": [
            _serialize_certificate(certificate)
            for certificate in blockchain.originality_certificates
            if certificate.certificate_id in certificate_ids
        ],
    }


@router.get('/blocks/{block_hash}/media')
@api_limit("public_read")
async def download_block_media(request: Request, block_hash: str):
    _sync_runtime_globals()
    if not is_valid_block_hash(block_hash):
        raise HTTPException(status_code=422, detail="block_hash must be a 64-character lowercase hexadecimal string.")

    block = blockchain.get_block_by_hash(block_hash)
    if block is None:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_hash}")

    try:
        media_bytes = blockchain.recover_block_media_bytes(block)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"Block does not contain recoverable media bytes: {block_hash}") from exc

    media_hash = str(getattr(block, "media_hash", "") or "").strip().lower()
    actual_media_hash = hashlib.sha256(media_bytes).hexdigest()
    if media_hash and media_hash != actual_media_hash:
        raise HTTPException(status_code=409, detail="Block media bytes failed integrity verification.")

    mime_type = str(getattr(block, "mime_type", "") or "").strip().lower() or "application/octet-stream"
    if mime_type == TEXT_MIME_TYPE:
        try:
            return PlainTextResponse(content=media_bytes.decode("utf-8"), media_type=TEXT_MIME_TYPE)
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=409, detail="Block text media could not be decoded safely.") from exc

    return Response(content=media_bytes, media_type=mime_type)


ROUTES = (
    (6, 'get', '/sync', 'sync_blockchain', {}),
    (66, 'get', '/chain', 'get_chain', {}),
    (67, 'get', '/chain/summary', 'chain_summary', {}),
    (69, 'get', '/chain/blocks', 'chain_blocks', {}),
    (72, 'get', '/blocks/{block_hash}/media', 'download_block_media', {}),
)

EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('GET', '/sync', 'sync_blockchain'): 6,
    ('GET', '/chain', 'get_chain'): 66,
    ('GET', '/chain/summary', 'chain_summary'): 67,
    ('GET', '/chain/blocks', 'chain_blocks'): 69,
    ('GET', '/blocks/{block_hash}/media', 'download_block_media'): 72,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
