"""Native API HTTP adapters."""

from fastapi import APIRouter

import api_runtime as _runtime
from api_runtime import *  # noqa: F401,F403 - shared API wiring and schemas

_ROUTER_RUNTIME_GENERATION = _runtime._ROUTER_RUNTIME_GENERATION
router = APIRouter()


def _sync_runtime_globals():
    """Refresh compatibility globals for api monkeypatches and isolated nodes."""
    globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

@router.post('/transfers/submit')
@api_limit("wallet_create")
async def submit_transfer_intent(
    request: Request,
    payload: WalletTransferSubmitRequest,
    wallet_address: str = Depends(_verified_wallet_dependency),
):
    _sync_runtime_globals()
    normalized_from = normalize_wallet_address(payload.from_address)
    if normalized_from is None or normalized_from != wallet_address:
        raise HTTPException(status_code=403, detail="from_address must match the verified wallet session.")
    _enforce_access_for_feature(wallet_address, feature="transfers")

    try:
        transfer_intent, admission, duplicate = blockchain.submit_signed_transfer_operation(
            payload=payload,
            wallet_address=wallet_address,
            auth_manager=wallet_auth_manager,
            build_preview=_build_submitted_native_transaction_preview,
            network_name=NETWORK_NAME,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 400
        if "expired" in detail.lower() or "already been used" in detail.lower():
            status_code = 401
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409 if "already exists" in str(exc) else 500, detail=str(exc)) from exc

    body = _serialize_transfer_intent(transfer_intent)
    if duplicate:
        body["duplicate"] = True
        body["message"] = "Transaction already recorded."
        return body
    if admission:
        body["admitted"] = True
        body["admitted_at"] = admission.get("admitted_at")
        body["message"] = admission["message"]
        return body
    body["message"] = "Signed native ZOID transaction recorded. It is not settled until included in a meme-mined block."
    return body


@router.post('/add_transaction')
@api_limit("transaction_create")
async def add_transaction(
    request: Request,
    sender: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    recipient: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
    amount: Annotated[float, Query(gt=0)],
    private_key: Annotated[str, Query(..., min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")],
):
    """Add a transaction to the blockchain using wallet validation (no API key)."""
    _sync_runtime_globals()

    try:
        blockchain.legacy_add_transaction_operation(sender, recipient, amount, private_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Transaction signing failed: {exc}") from exc

    return {"message": "Transaction added successfully."}


@router.get('/transaction_pool')
@api_limit("public_read")
async def transaction_pool(request: Request):
    """Retrieve the current transaction pool."""
    _sync_runtime_globals()
    return {"pending_transactions": blockchain.get_transaction_pool()}


@router.get('/accounts/{wallet_address}')
@api_limit("public_read")
async def get_native_account_summary(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return _build_account_summary(normalized_wallet)
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account summary for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/submissions')
@api_limit("public_read")
async def get_native_account_submissions(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        submissions = [
            _serialize_account_submission(submission)
            for submission in _get_account_submissions(normalized_wallet)
        ]
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "submissions": submissions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account submissions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/votes')
@api_limit("public_read")
async def get_native_account_votes(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        votes = [
            _serialize_account_vote(vote)
            for vote in _get_account_votes(normalized_wallet)
        ]
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "votes": votes,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account votes for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/rewards')
@api_limit("public_read")
async def get_native_account_rewards(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "rewards": _get_account_rewards(normalized_wallet),
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account rewards for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/transfers')
@api_limit("public_read")
async def get_native_account_transfers(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "transfers": _get_account_transfers(normalized_wallet),
            "note": "Transfer intents are pending and non-final until included in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account transfers for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/nonce')
@api_limit("public_read")
async def get_native_account_nonce(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return blockchain.get_nonce_state(normalized_wallet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account nonce for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/transactions')
@api_limit("public_read")
async def get_native_account_transactions(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "network_name": NETWORK_NAME,
            "transactions": _get_account_transactions(normalized_wallet),
            "note": "Canonical native ZOID transaction history for this MetaMask-backed ZoidbergChain account.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account transactions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/accounts/{wallet_address}/balance')
@api_limit("public_read")
async def get_native_account_balance(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_native_account_address(wallet_address)
        balance_snapshot = blockchain.get_native_balance_snapshot(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "normalized_wallet_address": normalized_wallet,
            "account_type": "metamask_native",
            "final_balance": balance_snapshot["final_balance"],
            "native_balance": balance_snapshot["native_balance"],
            "pending_outgoing": balance_snapshot["pending_outgoing"],
            "pending_incoming": balance_snapshot["pending_incoming"],
            "available_balance": balance_snapshot["available_balance"],
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "note": "Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native account balance for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/get_balance')
@api_limit("public_read")
async def get_balance(
    request: Request,
    public_key: Annotated[str, Query(..., min_length=66, max_length=66, pattern=PUBLIC_KEY_PATTERN)],
):
    """
    Retrieve the balance for a specific wallet.
    """
    _sync_runtime_globals()
    try:
        if public_key not in blockchain.wallets:
            return JSONResponse(status_code=400, content={"error": f"Public key {public_key} is not registered in the blockchain."})

        balance = blockchain.get_balance(public_key)
        logging.info("Returning balance for wallet %s", _short_key(public_key))

        return {"message": "Balance retrieved successfully.", "balance": balance}
    except Exception as e:
        logging.error("ERROR retrieving balance for wallet %s: %s", _short_key(public_key), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/wallets/{wallet_address}/balance')
@api_limit("public_read")
async def get_native_wallet_balance(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        balance_snapshot = blockchain.get_native_balance_snapshot(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "final_balance": balance_snapshot["final_balance"],
            "native_balance": balance_snapshot["native_balance"],
            "pending_outgoing": balance_snapshot["pending_outgoing"],
            "pending_incoming": balance_snapshot["pending_incoming"],
            "available_balance": balance_snapshot["available_balance"],
            "symbol": TICKER,
            "network_name": NETWORK_NAME,
            "note": "Legacy compatibility balance read. Pending outgoing transfers reduce available balance. Final balance changes only when a transfer is settled in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving native balance for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/wallets/{wallet_address}/rewards')
@api_limit("public_read")
async def get_native_wallet_rewards(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        rewards = blockchain.get_reward_records_for_wallet(normalized_wallet)
        return {
            "wallet_address": normalized_wallet,
            "symbol": COIN_NAME,
            "network_name": NETWORK_NAME,
            "rewards": rewards,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving rewards for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/wallets/{wallet_address}/transfers')
@api_limit("public_read")
async def get_wallet_transfer_intents(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        transfers = [
            _serialize_transfer_intent(record)
            for record in blockchain.get_transfer_intents_for_wallet(normalized_wallet)
        ]
        transfers.sort(key=lambda record: record.get("created_at") or 0, reverse=True)
        return {
            "wallet_address": normalized_wallet,
            "network_name": NETWORK_NAME,
            "transfers": transfers,
            "note": "Legacy compatibility transfer-intent read. Native ZOID transactions settle only when included in a meme-mined block.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving transfer intents for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/wallets/{wallet_address}/transactions')
@api_limit("public_read")
async def get_wallet_transactions(request: Request, wallet_address: str):
    _sync_runtime_globals()
    try:
        normalized_wallet = _normalize_supported_user_identity(wallet_address, field_name="wallet address")
        return {
            "wallet_address": normalized_wallet,
            "network_name": NETWORK_NAME,
            "transactions": _get_account_transactions(normalized_wallet),
            "note": "Legacy compatibility transaction history read for native ZOID account activity.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error("ERROR retrieving transactions for wallet %s: %s", _short_key(wallet_address), e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@router.get('/transfers/{transfer_id}')
@api_limit("public_read")
async def get_transfer_intent(request: Request, transfer_id: str):
    _sync_runtime_globals()
    transfer_intent = blockchain.get_transfer_intent(transfer_id)
    if not transfer_intent:
        raise HTTPException(status_code=404, detail=f"Transfer intent not found: {transfer_id}")
    return {
        "transfer": _serialize_transfer_intent(transfer_intent),
        "note": "Transfer intents are pending and non-final until included in a meme-mined block.",
    }


@router.get('/transactions/{tx_id}')
@api_limit("public_read")
async def get_native_transaction(request: Request, tx_id: str):
    _sync_runtime_globals()
    transaction = blockchain.get_native_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Transaction not found: {tx_id}")
    return {
        "transaction": _serialize_native_transaction(transaction),
        "note": "Native ZOID transaction record. Non-final until included in a meme-mined block unless status is settled.",
    }


@router.post('/transactions/{tx_id}/admit')
@api_limit("transaction_create")
async def admit_native_transaction_to_mempool(request: Request, tx_id: str):
    _sync_runtime_globals()
    try:
        admission = blockchain.admit_native_transaction_operation(tx_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return admission


@router.get('/mempool')
@api_limit("public_read")
async def get_mempool(request: Request):
    _sync_runtime_globals()
    transactions = [
        _serialize_native_transaction(transaction)
        for transaction in blockchain.list_mempool_transactions()
    ]
    return {
        "count": len(transactions),
        "transactions": transactions,
        "ordering_policy": "admitted_at ascending, then from_address ascending, then nonce ascending, then tx_id ascending",
        "note": "Local mempool only. Transactions are not settled until included in a block.",
    }


@router.get('/mempool/{tx_id}')
@api_limit("public_read")
async def get_mempool_transaction(request: Request, tx_id: str):
    _sync_runtime_globals()
    transaction = blockchain.get_mempool_transaction(tx_id)
    if not transaction:
        raise HTTPException(status_code=404, detail=f"Mempool transaction not found: {tx_id}")
    return {
        "transaction": _serialize_native_transaction(transaction),
        "note": "Present in the local mempool. Not settled until included in a block.",
    }


@router.post('/mempool/revalidate')
@api_limit("transaction_create")
async def revalidate_mempool(request: Request):
    _sync_runtime_globals()
    report = blockchain.revalidate_mempool_operation()
    report["message"] = "Local mempool revalidation complete."
    return report


@router.get('/get_reward_pool_balance')
@api_limit("public_read")
async def get_reward_pool_balance(request: Request):
    """
    Retrieve the balance of the reward pool.

    Returns:
        dict: The current balance of the reward pool.
    """
    _sync_runtime_globals()
    try:
        # Get the reward pool balance
        balance = blockchain.reward_pool

        return {
            "message": "Reward pool balance retrieved successfully.",
            "reward_pool_balance": balance
        }
    except Exception as e:
        logging.error("ERROR retrieving reward pool balance: %s", e)
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


EXPLICIT_ROUTER = True

_ROUTE_ORDER = {
    ('POST', '/transfers/submit', 'submit_transfer_intent'): 56,
    ('POST', '/add_transaction', 'add_transaction'): 74,
    ('GET', '/transaction_pool', 'transaction_pool'): 77,
    ('GET', '/accounts/{wallet_address}', 'get_native_account_summary'): 100,
    ('GET', '/accounts/{wallet_address}/submissions', 'get_native_account_submissions'): 101,
    ('GET', '/accounts/{wallet_address}/votes', 'get_native_account_votes'): 102,
    ('GET', '/accounts/{wallet_address}/rewards', 'get_native_account_rewards'): 103,
    ('GET', '/accounts/{wallet_address}/transfers', 'get_native_account_transfers'): 104,
    ('GET', '/accounts/{wallet_address}/nonce', 'get_native_account_nonce'): 105,
    ('GET', '/accounts/{wallet_address}/transactions', 'get_native_account_transactions'): 106,
    ('GET', '/accounts/{wallet_address}/balance', 'get_native_account_balance'): 107,
    ('GET', '/get_balance', 'get_balance'): 108,
    ('GET', '/wallets/{wallet_address}/balance', 'get_native_wallet_balance'): 109,
    ('GET', '/wallets/{wallet_address}/rewards', 'get_native_wallet_rewards'): 110,
    ('GET', '/wallets/{wallet_address}/transfers', 'get_wallet_transfer_intents'): 111,
    ('GET', '/wallets/{wallet_address}/transactions', 'get_wallet_transactions'): 112,
    ('GET', '/transfers/{transfer_id}', 'get_transfer_intent'): 113,
    ('GET', '/transactions/{tx_id}', 'get_native_transaction'): 114,
    ('POST', '/transactions/{tx_id}/admit', 'admit_native_transaction_to_mempool'): 115,
    ('GET', '/mempool', 'get_mempool'): 117,
    ('GET', '/mempool/{tx_id}', 'get_mempool_transaction'): 118,
    ('POST', '/mempool/revalidate', 'revalidate_mempool'): 119,
    ('GET', '/get_reward_pool_balance', 'get_reward_pool_balance'): 120,
}

for _route in router.routes:
    _method = next(iter(_route.methods))
    _route.endpoint.__route_order__ = _ROUTE_ORDER[(_method, _route.path, _route.name)]
