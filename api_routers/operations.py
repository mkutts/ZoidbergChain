"""Operations API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals without replacing module identity."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.get('/')
async def home():
    _sync_runtime_globals()
    """Serve the backend info page."""
    return static_asset_response("index.html", missing_message="Home page not found.")


@router.get('/about')
async def about():
    _sync_runtime_globals()
    """Serve the About Us page (White Paper)."""
    return static_asset_response("about.html", missing_message="About page not found.")


@router.get('/download_whitepaper')
async def download_whitepaper():
    _sync_runtime_globals()
    """Serve the White Paper PDF for download."""
    return static_asset_response(
        f"{COIN_NAME}_WhitePaper.pdf",
        download_name=f"{COIN_NAME}_WhitePaper.pdf",
        media_type="application/pdf",
        missing_message="White paper not found.",
    )


@router.post('/dev/reset')
@api_limit("dev_endpoint")
async def dev_reset_blockchain(request: Request):
    _sync_runtime_globals()
    """Development-only reset to Genesis state."""
    require_development_mode(allow_dev_reset_endpoints(), "Development reset endpoints")
    try:
        return {
            "warning": DEV_ENDPOINT_WARNING,
            **reset_runtime_blockchain_operation(),
        }
    except Exception:
        logger.exception("Development reset failed")
        return _safe_server_error()


@router.post('/reset_blockchain')
@api_limit("dev_endpoint")
async def reset_blockchain(request: Request):
    _sync_runtime_globals()
    """Legacy development-only reset route. Prefer /dev/reset."""
    require_development_mode(allow_dev_reset_endpoints(), "Development reset endpoints")
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "deprecated_route": True,
        "replacement": "/dev/reset",
        **reset_runtime_blockchain_operation(),
    }


@router.get('/dev/debug')
@api_limit("dev_endpoint")
async def dev_debug(request: Request):
    _sync_runtime_globals()
    """Development-only node diagnostics with no key material."""
    require_development_mode(allow_dev_reset_endpoints(), "Development debug endpoints")
    latest_block = blockchain.get_latest_block()
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "environment": ENVIRONMENT,
        "network_name": NETWORK_NAME,
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "chain_height": latest_block.index,
        "latest_block_hash": latest_block.hash,
        "wallet_count": len(blockchain.wallets),
        "peer_count": len(peer_store.list_peers()),
    }


@router.get('/health')
@api_limit("public_read")
async def health(request: Request):
    _sync_runtime_globals()
    return _health_payload()


@router.get('/status')
@api_limit("public_read")
async def status(request: Request):
    _sync_runtime_globals()
    return _status_payload()


@router.get('/ops/status')
@api_limit("public_read")
async def public_ops_status(request: Request):
    _sync_runtime_globals()
    return _status_payload()


@router.get('/node-info')
@api_limit("public_read")
async def node_info(request: Request):
    _sync_runtime_globals()
    payload = _health_payload()
    payload.update({
        "node_id": NODE_ID,
        "public_node_url": PUBLIC_NODE_URL,
        "cumulative_originality_score": blockchain.get_cumulative_originality_score(),
    })
    return payload


@router.get('/get_wallets')
@api_limit("public_read")
async def get_wallets(request: Request):
    _sync_runtime_globals()
    """
    Retrieve development-only server wallets using public-safe fields only.
    """
    try:
        return {
            "message": "Development-only server wallets retrieved successfully.",
            "warning": "Development-only server wallets are local test tools and are not the native ZoidbergChain account registry for MetaMask users.",
            "wallets": [
                _wallet_public_response(key, wallet)
                for key, wallet in blockchain.wallets.items()
            ],
        }
    except Exception:
        logger.exception("Failed to retrieve development wallet summaries")
        return _safe_server_error()


@router.get('/dev/wallets')
@api_limit("dev_endpoint")
async def get_dev_wallets(request: Request):
    _sync_runtime_globals()
    _require_dev_private_key_export()
    return {
        "warning": DEV_ENDPOINT_WARNING,
        "message": "Development-only server wallets with private-key export.",
        "wallets": [
            {
                **_wallet_public_response(key, wallet),
                "private_key": wallet.private_key,
            }
            for key, wallet in blockchain.wallets.items()
        ],
    }


@router.post('/dev/submissions/{submission_id}/repair-certificate')
@api_limit("dev_endpoint")
async def repair_submission_certificate(request: Request, submission_id: str):
    _sync_runtime_globals()
    require_development_mode(allow_dev_reset_endpoints(), "Development repair endpoints")
    try:
        submission, certificate, already_exists = blockchain.repair_submission_certificate_operation(submission_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Cannot repair certificate:"):
            raise HTTPException(status_code=400, detail=message) from exc
        raise HTTPException(status_code=400, detail=f"Cannot repair certificate: {message}") from exc
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot repair certificate: {e}")

    return {
        "message": "Originality certificate already exists." if already_exists else "Originality certificate repaired.",
        "submission": _serialize_submission(submission),
        "certificate": _serialize_certificate(certificate),
    }


@router.post('/add_block')
@api_limit("mint")
async def add_block(
    request: Request,
    image: UploadFile,
    miner: Annotated[str, Form(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    private_key: Annotated[str, Form(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")],  # ✅ Validate miner via wallet key
    role: str = Depends(require_legacy_direct_block_access),
):
    _sync_runtime_globals()
    """
    Add a legacy direct block for development-only workflows.
    """
    if not image.filename:
        raise HTTPException(status_code=400, detail="Invalid image format. Allowed formats: jpg, jpeg, png, webp")
    file_bytes = await image.read()
    try:
        validate_content_size(len(file_bytes))
        safe_original_filename, _ = _validate_uploaded_image_payload(image, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        block_added, latest_block = blockchain.legacy_add_block_upload_operation(
            file_bytes=file_bytes,
            original_filename=safe_original_filename,
            miner=miner,
            private_key=private_key,
        )
        broadcast_result = (
            broadcast_block_to_peers(
                block=latest_block,
                peer_store=peer_store,
                origin_node_id=NODE_ID,
                network_name=NETWORK_NAME,
            )
            if latest_block
            else {"attempted": 0, "succeeded": 0, "failed": 0, "results": []}
        )

        return {
            "message": "Legacy direct block added successfully.",
            "legacy_direct_block": True,
            "protocol_v1_mint_path": False,
            "access_role": role,
            "block": _serialize_block(latest_block) if latest_block else False,
            "broadcast": broadcast_result,
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logging.error("Unexpected error in add_block for miner %s: %s", _short_key(miner), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.post('/generate_wallet', summary='Generate a new wallet', description='Creates a new wallet.')
@api_limit("wallet_create")
async def generate_wallet(request: Request):  # ✅ No more API key validation
    _sync_runtime_globals()
    """
    Generate a development-only server wallet.
    """
    require_development_mode(True, "Development wallet generation")
    wallet = blockchain.generate_development_wallet_operation()
    logger.info("Wallet registered with public key: %s", _short_key(wallet.public_key))

    response = {
        "message": "Development-only server wallet generated successfully.",
        "warning": "This endpoint creates local test wallets only. MetaMask-backed 0x addresses are the normal native ZoidbergChain account model.",
        "wallet": _wallet_public_response(wallet.public_key, wallet),
    }
    if _dev_private_key_export_enabled():
        response["key_export"] = {
            "enabled": True,
            "endpoint": "/dev/wallets",
            "warning": DEV_ENDPOINT_WARNING,
        }
    else:
        response["key_export"] = {
            "enabled": False,
            "message": "Private key export is disabled for this environment.",
        }
    return response


@router.post('/dev/mint-queue/cleanup-bad-items')
@api_limit("dev_endpoint")
async def cleanup_bad_mint_queue_items(
    request: Request,
    payload: MintQueueCleanupRequest,
    role: str = Depends(require_mint_queue_management_access),
):
    _sync_runtime_globals()
    return blockchain.cleanup_bad_mint_queue_items_operation(
        block_unmintable=payload.block_unmintable and not payload.dry_run,
    )


ROUTES = (
    (0, 'get', '/', 'home', {}),
    (1, 'get', '/about', 'about', {}),
    (2, 'get', '/download_whitepaper', 'download_whitepaper', {}),
    (3, 'post', '/dev/reset', 'dev_reset_blockchain', {}),
    (4, 'post', '/reset_blockchain', 'reset_blockchain', {}),
    (5, 'get', '/dev/debug', 'dev_debug', {}),
    (7, 'get', '/health', 'health', {}),
    (8, 'get', '/status', 'status', {}),
    (9, 'get', '/ops/status', 'public_ops_status', {}),
    (10, 'get', '/node-info', 'node_info', {}),
    (75, 'get', '/get_wallets', 'get_wallets', {}),
    (76, 'get', '/dev/wallets', 'get_dev_wallets', {}),
    (91, 'post', '/dev/submissions/{submission_id}/repair-certificate', 'repair_submission_certificate', {}),
    (98, 'post', '/add_block', 'add_block', {}),
    (99, 'post', '/generate_wallet', 'generate_wallet', {'summary': 'Generate a new wallet', 'description': 'Creates a new wallet.'}),
    (128, 'post', '/dev/mint-queue/cleanup-bad-items', 'cleanup_bad_mint_queue_items', {}),
)

EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('GET', '/', 'home'): 0,
    ('GET', '/about', 'about'): 1,
    ('GET', '/download_whitepaper', 'download_whitepaper'): 2,
    ('POST', '/dev/reset', 'dev_reset_blockchain'): 3,
    ('POST', '/reset_blockchain', 'reset_blockchain'): 4,
    ('GET', '/dev/debug', 'dev_debug'): 5,
    ('GET', '/health', 'health'): 7,
    ('GET', '/status', 'status'): 8,
    ('GET', '/ops/status', 'public_ops_status'): 9,
    ('GET', '/node-info', 'node_info'): 10,
    ('GET', '/get_wallets', 'get_wallets'): 75,
    ('GET', '/dev/wallets', 'get_dev_wallets'): 76,
    ('POST', '/dev/submissions/{submission_id}/repair-certificate', 'repair_submission_certificate'): 91,
    ('POST', '/add_block', 'add_block'): 98,
    ('POST', '/generate_wallet', 'generate_wallet'): 99,
    ('POST', '/dev/mint-queue/cleanup-bad-items', 'cleanup_bad_mint_queue_items'): 128,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
