from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient

from block import Block
from peers import PeerStore
from submission import APPROVED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from transaction import Transaction
from wallet import Wallet
from wallet_auth import WalletAuthManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
NODE_NETWORK_NAME = "zoidberg-testnet"
NODE_A_URL = "http://node-a.test:8000"
NODE_B_URL = "http://node-b.test:8001"
TRANSFER_AMOUNT = "3"
REWARD_AMOUNT = "5"
TRACKED_ENV_VARS = (
    "ENVIRONMENT",
    "NETWORK_NAME",
    "NODE_ID",
    "PUBLIC_NODE_URL",
    "DATA_DIR",
    "NODE_DATA_DIR",
    "NODE_HOST",
    "NODE_PORT",
    "CONTENT_STORAGE_DIR",
)


@dataclass
class NodeHandle:
    node_id: str
    public_url: str
    data_dir: Path
    api_module: Any
    client: TestClient

    @property
    def blockchain(self):
        return self.api_module.blockchain

    @property
    def peer_store(self):
        return self.api_module.peer_store


def _log(verbose: bool, message: str):
    if verbose:
        print(message, flush=True)


def _assert_equal(actual, expected, message: str):
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def _assert_true(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def _response_json(response, *, expected_status: int, context: str):
    if response.status_code != expected_status:
        raise AssertionError(
            f"{context} returned {response.status_code}, expected {expected_status}: {response.text}"
        )
    return response.json()


def _sign_message(message: str, account) -> str:
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def _create_wallets() -> dict[str, Wallet]:
    return {
        "owner": Wallet(),
        "contributor_one": Wallet(),
        "contributor_two": Wallet(),
    }


def _clone_block(block: Block) -> Block:
    block_data = block.to_dict()
    return Block(
        index=block_data["index"],
        previous_hash=block_data["previous_hash"],
        timestamp=block_data["timestamp"],
        transactions=[Transaction.from_dict(tx) for tx in block_data["transactions"]],
        miner=block_data["miner"],
        meme=block_data.get("meme", {}),
        hash=block_data["hash"],
        submission_id=block_data.get("submission_id"),
        certificate_id=block_data.get("certificate_id"),
        content_hash=block_data.get("content_hash"),
        content_id=block_data.get("content_id"),
        content_type=block_data.get("content_type"),
        mime_type=block_data.get("mime_type"),
        creator_wallet=block_data.get("creator_wallet"),
        vote_hash=block_data.get("vote_hash"),
        approval_percentage=block_data.get("approval_percentage"),
        decisive_vote_total=block_data.get("decisive_vote_total"),
        minimum_votes_required=block_data.get("minimum_votes_required"),
        approved_at=block_data.get("approved_at"),
        originality_score=block_data.get("originality_score"),
        reward_type=block_data.get("reward_type"),
        reward_recipient=block_data.get("reward_recipient"),
        reward_amount=block_data.get("reward_amount"),
        reward_source=block_data.get("reward_source"),
        minted_at=block_data.get("minted_at"),
        native_transactions=block_data.get("native_transactions", []),
        transaction_ids=block_data.get("transaction_ids"),
        transaction_count=block_data.get("transaction_count"),
        transactions_hash=block_data.get("transactions_hash"),
    )


@contextmanager
def _preserved_environment():
    previous = {name: os.environ.get(name) for name in TRACKED_ENV_VARS}
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        import config
        import blockchain as blockchain_module

        importlib.reload(config)
        importlib.reload(blockchain_module)


def _load_api_module(alias: str, *, node_id: str, public_url: str, data_dir: Path):
    os.environ["ENVIRONMENT"] = "development"
    os.environ["NETWORK_NAME"] = NODE_NETWORK_NAME
    os.environ["NODE_ID"] = node_id
    os.environ["PUBLIC_NODE_URL"] = public_url
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["NODE_DATA_DIR"] = str(data_dir)
    os.environ["NODE_HOST"] = "127.0.0.1"
    os.environ["NODE_PORT"] = public_url.rsplit(":", 1)[-1]
    os.environ["CONTENT_STORAGE_DIR"] = str(data_dir / "content")

    import config
    import blockchain as blockchain_module

    importlib.reload(config)
    importlib.reload(blockchain_module)

    spec = importlib.util.spec_from_file_location(alias, PROJECT_ROOT / "api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _build_node(alias: str, *, node_id: str, public_url: str, data_dir: Path, wallets: dict[str, Wallet]) -> NodeHandle:
    data_dir.mkdir(parents=True, exist_ok=True)
    module = _load_api_module(alias, node_id=node_id, public_url=public_url, data_dir=data_dir)
    module.NODE_ID = node_id
    module.PUBLIC_NODE_URL = public_url
    module.NETWORK_NAME = NODE_NETWORK_NAME
    module.blockchain = module.Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
    )
    module.peer_store = PeerStore(file_path=str(data_dir / "peers.json"))
    module.wallet_auth_manager = WalletAuthManager(
        network_name=module.NETWORK_NAME,
        environment=module.ENVIRONMENT,
    )
    client = TestClient(module.app)
    return NodeHandle(
        node_id=node_id,
        public_url=public_url,
        data_dir=data_dir,
        api_module=module,
        client=client,
    )


def _align_node_b_genesis(node_a: NodeHandle, node_b: NodeHandle):
    node_b.blockchain.chain = [_clone_block(node_a.blockchain.chain[0])]
    node_b.blockchain.pending_transactions = []
    node_b.blockchain.submissions = []
    node_b.blockchain.content_objects = []
    node_b.blockchain.mint_queue = []
    node_b.blockchain.votes = []
    node_b.blockchain.transfer_intents = []
    node_b.blockchain.native_transactions = []
    node_b.blockchain.originality_certificates = []
    node_b.blockchain.image_validation_cache = {}
    node_b.blockchain.text_validation_cache = {}


class _RoutedResponse:
    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code
        self.text = response.text

    def json(self):
        return self._response.json()


def _route_target(nodes_by_url: dict[str, NodeHandle], url: str) -> tuple[NodeHandle, str]:
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    try:
        node = nodes_by_url[base_url]
    except KeyError as exc:
        raise AssertionError(f"Unexpected routed peer URL: {url}") from exc
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return node, path


@contextmanager
def _patched_peer_http(nodes_by_url: dict[str, NodeHandle]):
    def fake_get(url, params=None, headers=None, timeout=None):
        node, path = _route_target(nodes_by_url, url)
        response = node.client.get(path, params=params, headers=headers or {})
        return _RoutedResponse(response)

    def fake_post(url, json=None, data=None, headers=None, timeout=None):
        node, path = _route_target(nodes_by_url, url)
        response = node.client.post(path, json=json, data=data, headers=headers or {})
        return _RoutedResponse(response)

    with patch("peer_sync.requests.get", side_effect=fake_get), patch("peer_sync.requests.post", side_effect=fake_post):
        yield


def _verified_headers(client: TestClient, account) -> dict[str, str]:
    challenge = _response_json(
        client.post("/auth/wallet/challenge", json={"wallet_address": account.address}),
        expected_status=200,
        context="wallet challenge",
    )
    verify = _response_json(
        client.post(
            "/auth/wallet/verify",
            json={
                "wallet_address": account.address,
                "message": challenge["message"],
                "signature": _sign_message(challenge["message"], account),
            },
        ),
        expected_status=200,
        context="wallet verify",
    )
    return {"Authorization": f"Bearer {verify['session_token']}"}


def _transfer_challenge(client: TestClient, account, headers: dict[str, str], *, to_address: str, amount: str, memo: str):
    return _response_json(
        client.post(
            "/auth/wallet/transfer-challenge",
            json={
                "from_address": account.address,
                "to_address": to_address,
                "amount": amount,
                "fee": "0",
                "memo": memo,
            },
            headers=headers,
        ),
        expected_status=200,
        context="transfer challenge",
    )


def _submit_transfer(client: TestClient, account, headers: dict[str, str], challenge: dict[str, Any], *, memo: str, admit_to_mempool: bool):
    return _response_json(
        client.post(
            "/transfers/submit",
            json={
                "from_address": account.address,
                "to_address": challenge["transfer_preview"]["to_address"],
                "amount": challenge["transfer_preview"]["amount"],
                "fee": challenge["transfer_preview"]["fee"],
                "memo": memo,
                "message": challenge["message"],
                "signature": _sign_message(challenge["message"], account),
                "admit_to_mempool": admit_to_mempool,
            },
            headers=headers,
        ),
        expected_status=200,
        context="transfer submit",
    )


def _wallet_balance(client: TestClient, wallet_address: str):
    return _response_json(
        client.get(f"/wallets/{wallet_address.lower()}/balance"),
        expected_status=200,
        context=f"wallet balance {wallet_address}",
    )


def _account_summary(client: TestClient, wallet_address: str):
    return _response_json(
        client.get(f"/accounts/{wallet_address.lower()}"),
        expected_status=200,
        context=f"account summary {wallet_address}",
    )


def _transaction_record(client: TestClient, tx_id: str):
    return _response_json(
        client.get(f"/transactions/{tx_id}"),
        expected_status=200,
        context=f"transaction lookup {tx_id}",
    )["transaction"]


def _mempool(client: TestClient):
    return _response_json(
        client.get("/mempool"),
        expected_status=200,
        context="mempool lookup",
    )


def _prepare_mintable_submission(
    blockchain,
    image_path: Path,
    wallets: dict[str, Wallet],
    *,
    text: str,
    voter_prefix: str,
    submitter: str | None = None,
):
    submission = blockchain.submit_content(
        image_path=str(image_path),
        text_content=text,
        submitter=submitter or wallets["owner"].public_key,
    )
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"{voter_prefix}-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )
    submission.transition_to(APPROVED)
    certificate = blockchain.create_originality_certificate(submission.submission_id, approved_at=1_000_100)
    blockchain.add_to_mint_queue(submission.submission_id)
    return submission, certificate


def _fund_native_wallet(blockchain, wallet_address: str, amount: str):
    blockchain.chain[0].transactions.append(
        Transaction(sender="GENESIS", recipient=wallet_address.lower(), amount=float(amount), tip=0)
    )
    blockchain.chain[0].hash = blockchain.chain[0].calculate_hash()


def _build_signed_transaction_payload(
    account,
    *,
    network: str,
    to_address: str,
    amount: str,
    nonce: str,
    memo: str,
):
    from native_transfer import (
        NATIVE_TRANSFER_SIGNATURE_SCHEME,
        build_native_transaction,
        hash_transfer_signing_message,
    )
    from protocol_v1 import PROTOCOL_VERSION
    from protocol_v1_native_transfer import (
        build_protocol_v1_native_transfer_message,
        build_protocol_v1_native_transfer_payload,
        resolve_protocol_v1_network_id,
    )

    timestamp = "2026-08-01T12:00:00+00:00"
    network_id = resolve_protocol_v1_network_id(network_name=network)
    transfer_payload = build_protocol_v1_native_transfer_payload(
        from_address=account.address,
        to_address=to_address,
        amount=amount,
        fee="0",
        nonce=nonce,
        timestamp=timestamp,
        memo=memo,
    )
    signed_message = build_protocol_v1_native_transfer_message(
        from_address=str(transfer_payload["from_address"]),
        to_address=str(transfer_payload["to_address"]),
        amount=str(transfer_payload["amount"]),
        fee=str(transfer_payload["fee"]),
        nonce=str(transfer_payload["nonce"]),
        timestamp=str(transfer_payload["timestamp"]),
        memo=transfer_payload.get("memo"),
        network_id=network_id,
    )
    transaction = build_native_transaction(
        network=network,
        from_address=account.address,
        to_address=to_address,
        amount=amount,
        fee="0",
        nonce=nonce,
        memo=memo,
        timestamp=timestamp,
        signature=_sign_message(signed_message, account),
        signature_scheme=NATIVE_TRANSFER_SIGNATURE_SCHEME,
        signed_message=signed_message,
        signed_message_hash=hash_transfer_signing_message(signed_message),
        transaction_version=PROTOCOL_VERSION,
        protocol_version=PROTOCOL_VERSION,
        network_id=network_id,
    )
    return transaction.to_dict()


def _rebuild_transaction_with_signature(base_transaction: dict[str, Any], signature: str):
    from native_transfer import build_native_transaction

    rebuilt = build_native_transaction(
        network=str(base_transaction["network"]),
        from_address=str(base_transaction["from_address"]),
        to_address=str(base_transaction["to_address"]),
        amount=str(base_transaction["amount"]),
        fee=str(base_transaction["fee"]),
        nonce=str(base_transaction["nonce"]),
        memo=base_transaction.get("memo"),
        timestamp=str(base_transaction["timestamp"]),
        signature=signature,
        signature_scheme=str(base_transaction["signature_scheme"]),
        signed_message=str(base_transaction["signed_message"]),
        signed_message_hash=str(base_transaction["signed_message_hash"]),
        transaction_version=base_transaction.get("transaction_version"),
        protocol_version=base_transaction.get("protocol_version"),
        network_id=base_transaction.get("network_id"),
        status="signed_pending",
        created_at=str(base_transaction["created_at"]),
        updated_at=str(base_transaction["updated_at"]),
    )
    return rebuilt.to_dict()


def _build_peer_block(blockchain, *, latest_block: Block, submission, certificate, miner: str, text: str, native_transactions: list[dict[str, Any]]):
    minted_at = 1_000_500.0 + latest_block.index
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=minted_at,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=minted_at)],
        miner=miner,
        meme={"encoded_image": "peer-image", "text": text},
        native_transactions=native_transactions,
        transaction_ids=[transaction["tx_id"] for transaction in native_transactions],
        transaction_count=len(native_transactions),
        transactions_hash=blockchain._compute_block_native_transactions_hash(native_transactions),
        **blockchain.certificate_block_metadata(certificate),
        **blockchain.build_meme_reward_metadata(submission, certificate, minted_at=minted_at),
    )


def _register_peers(node_a: NodeHandle, node_b: NodeHandle):
    _response_json(
        node_a.client.post(
            "/peers/register",
            json={
                "node_id": node_b.node_id,
                "url": node_b.public_url,
                "network_name": NODE_NETWORK_NAME,
            },
        ),
        expected_status=200,
        context="register node B on node A",
    )
    _response_json(
        node_b.client.post(
            "/peers/register",
            json={
                "node_id": node_a.node_id,
                "url": node_a.public_url,
                "network_name": NODE_NETWORK_NAME,
            },
        ),
        expected_status=200,
        context="register node A on node B",
    )


def _negative_receive_transaction(node_b: NodeHandle, payload: dict[str, Any], *, expected_status: int, expected_reason: str, origin_node_id: str):
    response = node_b.client.post(
        "/peers/transactions/receive",
        json={
            "origin_node_id": origin_node_id,
            "network_name": NODE_NETWORK_NAME,
            "transaction": payload,
        },
    )
    body = _response_json(
        response,
        expected_status=expected_status,
        context=f"negative peer receive transaction {expected_reason}",
    )
    _assert_equal(body["reason"], expected_reason, f"unexpected peer transaction rejection reason for {expected_reason}")
    return body


def _detail_code(body: dict[str, Any]) -> str | None:
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


def _detail_message(body: dict[str, Any]) -> str:
    detail = body.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("message") or "")
    return str(detail or "")


def run_two_node_native_transfer_verification(*, verbose: bool = False) -> dict[str, Any]:
    project_image = PROJECT_ROOT / "zoidberg.jpg"
    if not project_image.exists():
        raise FileNotFoundError(f"Missing test image: {project_image}")

    summary: dict[str, Any] = {}

    with _preserved_environment():
        with tempfile.TemporaryDirectory(prefix="zoid-two-node-native-") as temp_root_raw:
            temp_root = Path(temp_root_raw)
            node_a = None
            node_b = None
            try:
                wallets = _create_wallets()
                sender = Account.create()
                recipient = Account.create()
                node_a = _build_node(
                    "task8_9_node_a_api",
                    node_id="node-a",
                    public_url=NODE_A_URL,
                    data_dir=temp_root / "node-a",
                    wallets=wallets,
                )
                node_b = _build_node(
                    "task8_9_node_b_api",
                    node_id="node-b",
                    public_url=NODE_B_URL,
                    data_dir=temp_root / "node-b",
                    wallets=wallets,
                )
                _align_node_b_genesis(node_a, node_b)
                _fund_native_wallet(node_a.blockchain, sender.address, REWARD_AMOUNT)
                _align_node_b_genesis(node_a, node_b)

                nodes_by_url = {
                    node_a.public_url: node_a,
                    node_b.public_url: node_b,
                }

                with _patched_peer_http(nodes_by_url):
                    _log(verbose, "Step 1/8: Establishing two isolated local nodes and registering peers.")
                    _register_peers(node_a, node_b)
                    peers_a = _response_json(node_a.client.get("/peers"), expected_status=200, context="node A peers")
                    peers_b = _response_json(node_b.client.get("/peers"), expected_status=200, context="node B peers")
                    _assert_equal(len(peers_a["peers"]), 1, "node A peer count")
                    _assert_equal(len(peers_b["peers"]), 1, "node B peer count")
                    summary_a = _response_json(node_a.client.get("/chain/summary"), expected_status=200, context="node A chain summary")
                    summary_b = _response_json(node_b.client.get("/chain/summary"), expected_status=200, context="node B chain summary")
                    _assert_equal(summary_a["network_name"], NODE_NETWORK_NAME, "node A network name")
                    _assert_equal(summary_b["network_name"], NODE_NETWORK_NAME, "node B network name")
                    sync_probe = _response_json(node_b.client.post("/chain/sync"), expected_status=200, context="node B sync probe")
                    _assert_equal(sync_probe["attempted"], 1, "node B sync attempted peers")
                    prefund_balance_a = _wallet_balance(node_a.client, sender.address)
                    prefund_balance_b = _wallet_balance(node_b.client, sender.address)
                    _assert_equal(prefund_balance_a["final_balance"], REWARD_AMOUNT, "node A prefunded sender balance")
                    _assert_equal(prefund_balance_b["final_balance"], REWARD_AMOUNT, "node B prefunded sender balance")

                    _log(verbose, "Step 2/8: Minting a certified reward block on Node A and proving Node B accepts the peer block while sender balances stay aligned.")
                    reward_submission, _reward_certificate = _prepare_mintable_submission(
                        node_a.blockchain,
                        project_image,
                        wallets,
                        text="Task 8.9 reward funding block",
                        voter_prefix="task8-9-reward",
                    )
                    reward_mint = _response_json(
                        node_a.client.post(
                            f"/mint-queue/{reward_submission.submission_id}/mint",
                            data={"miner": sender.address.lower()},
                        ),
                        expected_status=200,
                        context="reward block mint",
                    )
                    _assert_true(reward_mint["minted"] is True, "reward mint should succeed")
                    _assert_equal(reward_mint["transactions_included"], 0, "reward block should not include native transfers")
                    reward_balance_a = _wallet_balance(node_a.client, sender.address)
                    reward_balance_b = _wallet_balance(node_b.client, sender.address)
                    _assert_equal(reward_balance_a["final_balance"], REWARD_AMOUNT, "node A sender reward balance")
                    _assert_equal(reward_balance_b["final_balance"], REWARD_AMOUNT, "node B sender reward balance")
                    _assert_equal(node_b.blockchain.get_latest_block().hash, reward_mint["block_hash"], "node B reward block hash")

                    _log(verbose, "Step 3/8: Creating a signed native transfer on Node A without settling balances yet.")
                    headers = _verified_headers(node_a.client, sender)
                    transfer_challenge = _transfer_challenge(
                        node_a.client,
                        sender,
                        headers,
                        to_address=recipient.address,
                        amount=TRANSFER_AMOUNT,
                        memo="Task 8.9 native transfer",
                    )
                    initial_nonce = int(transfer_challenge["transfer_preview"]["nonce"])
                    _assert_true(initial_nonce >= 1, "initial sender nonce should respect the configured nonce floor")
                    submit_response = _submit_transfer(
                        node_a.client,
                        sender,
                        headers,
                        transfer_challenge,
                        memo="Task 8.9 native transfer",
                        admit_to_mempool=False,
                    )
                    tx_id = submit_response["tx_id"]
                    signed_pending = _transaction_record(node_a.client, tx_id)
                    _assert_equal(signed_pending["status"], "signed_pending", "signed transfer status on node A")
                    balance_after_submit = _wallet_balance(node_a.client, sender.address)
                    _assert_equal(balance_after_submit["final_balance"], REWARD_AMOUNT, "final balance must not change on submit")
                    _assert_equal(balance_after_submit["available_balance"], "2", "available balance should reserve signed transfer")
                    sender_account_summary = _account_summary(node_a.client, sender.address)
                    _assert_equal(sender_account_summary["nonce"]["next_nonce"], initial_nonce + 1, "next nonce after signed transfer")

                    _log(verbose, "Step 4/8: Admitting the transfer to Node A mempool, broadcasting to Node B, and proving duplicate gossip is idempotent.")
                    admission = _response_json(
                        node_a.client.post(f"/transactions/{tx_id}/admit"),
                        expected_status=200,
                        context="node A admit transfer",
                    )
                    _assert_equal(admission["status"], "mempool", "node A admitted transaction status")
                    node_a_mempool = _mempool(node_a.client)
                    _assert_equal(node_a_mempool["count"], 1, "node A mempool count after admit")
                    _assert_equal(node_a_mempool["transactions"][0]["tx_id"], tx_id, "node A mempool tx id")
                    _assert_equal(_wallet_balance(node_a.client, sender.address)["final_balance"], REWARD_AMOUNT, "node A final balance before settlement")

                    first_broadcast = _response_json(
                        node_a.client.post(f"/transactions/{tx_id}/broadcast"),
                        expected_status=200,
                        context="node A broadcast transfer",
                    )
                    _assert_equal(first_broadcast["peers_accepted"], 1, "first transfer broadcast accepted peers")
                    node_b_transaction = _transaction_record(node_b.client, tx_id)
                    _assert_equal(node_b_transaction["status"], "mempool", "node B mempool status after gossip")
                    node_b_balance = _wallet_balance(node_b.client, sender.address)
                    _assert_equal(node_b_balance["available_balance"], "2", "node B available balance before settlement")
                    _assert_equal(node_b_balance["final_balance"], REWARD_AMOUNT, "node B final balance before settlement")
                    node_b_mempool = _mempool(node_b.client)
                    _assert_equal(node_b_mempool["count"], 1, "node B mempool count after first gossip")

                    second_broadcast = _response_json(
                        node_a.client.post(f"/transactions/{tx_id}/broadcast"),
                        expected_status=200,
                        context="node A duplicate transfer broadcast",
                    )
                    duplicate_result = second_broadcast["results"][0]
                    _assert_true(bool(duplicate_result["duplicate"]), "duplicate transfer broadcast should be idempotent on node B")
                    _assert_equal(_mempool(node_b.client)["count"], 1, "node B mempool count after duplicate gossip")
                    _assert_equal(_wallet_balance(node_b.client, sender.address)["available_balance"], "2", "node B must not double-reserve duplicate gossip")

                    _log(verbose, "Step 5/8: Rejecting malformed peer transactions and invalid transfer-bearing blocks without mutating balances.")
                    baseline_node_b_sender = _wallet_balance(node_b.client, sender.address)
                    baseline_node_b_recipient = _wallet_balance(node_b.client, recipient.address)
                    canonical_transaction = node_a.blockchain.get_native_transaction(tx_id)
                    _assert_true(canonical_transaction is not None, "canonical transaction should exist on node A")
                    canonical_transaction = dict(canonical_transaction)

                    tampered_amount = dict(canonical_transaction)
                    tampered_amount["amount"] = "4"
                    _negative_receive_transaction(
                        node_b,
                        tampered_amount,
                        expected_status=400,
                        expected_reason="invalid_tx_id",
                        origin_node_id=node_a.node_id,
                    )

                    invalid_signature_base = _build_signed_transaction_payload(
                        sender,
                        network=NODE_NETWORK_NAME,
                        to_address=recipient.address,
                        amount="1",
                        nonce=str(initial_nonce + 1),
                        memo="Task 8.9 invalid signature",
                    )
                    tampered_signature = _rebuild_transaction_with_signature(
                        invalid_signature_base,
                        _sign_message(invalid_signature_base["signed_message"], Account.create()),
                    )
                    _negative_receive_transaction(
                        node_b,
                        tampered_signature,
                        expected_status=400,
                        expected_reason="invalid_signature",
                        origin_node_id=node_a.node_id,
                    )

                    wrong_network = dict(canonical_transaction)
                    wrong_network["network"] = "zoidberg-wrongnet"
                    wrong_network_response = node_b.client.post(
                        "/peers/transactions/receive",
                        json={
                            "origin_node_id": node_a.node_id,
                            "network_name": NODE_NETWORK_NAME,
                            "transaction": wrong_network,
                        },
                    )
                    wrong_network_body = _response_json(
                        wrong_network_response,
                        expected_status=400,
                        context="wrong network peer transaction",
                    )
                    _assert_equal(wrong_network_body["reason"], "validation_failed", "wrong network rejection reason")
                    _assert_true(
                        "network does not match" in wrong_network_body["message"].lower(),
                        "wrong network rejection message should explain the network mismatch",
                    )

                    conflicting_payload = _build_signed_transaction_payload(
                        sender,
                        network=NODE_NETWORK_NAME,
                        to_address=Account.create().address,
                        amount="1",
                        nonce=str(initial_nonce),
                        memo="Task 8.9 conflicting nonce",
                    )
                    conflicting_response = node_b.client.post(
                        "/peers/transactions/receive",
                        json={
                            "origin_node_id": node_a.node_id,
                            "network_name": NODE_NETWORK_NAME,
                            "transaction": conflicting_payload,
                        },
                    )
                    conflicting_body = _response_json(
                        conflicting_response,
                        expected_status=409,
                        context="conflicting nonce peer transaction",
                    )
                    _assert_equal(conflicting_body["reason"], "conflicting_nonce", "conflicting nonce rejection reason")
                    _assert_equal(_wallet_balance(node_b.client, sender.address), baseline_node_b_sender, "node B sender balance should remain unchanged after invalid gossip")
                    _assert_equal(_wallet_balance(node_b.client, recipient.address), baseline_node_b_recipient, "node B recipient balance should remain unchanged after invalid gossip")
                    _assert_equal(_mempool(node_b.client)["count"], 1, "node B mempool should still contain only the original transaction")

                    invalid_submission, invalid_certificate = _prepare_mintable_submission(
                        node_a.blockchain,
                        project_image,
                        wallets,
                        text="Task 8.9 invalid transfer-bearing block",
                        voter_prefix="task8-9-invalid-block",
                    )
                    invalid_snapshot = node_a.blockchain._serialize_native_transaction_for_block(canonical_transaction)
                    invalid_snapshot["signature"] = "0xdeadbeef"
                    invalid_block = _build_peer_block(
                        node_a.blockchain,
                        latest_block=node_a.blockchain.get_latest_block(),
                        submission=invalid_submission,
                        certificate=invalid_certificate,
                        miner=wallets["contributor_one"].public_key,
                        text="Task 8.9 invalid native transaction block",
                        native_transactions=[invalid_snapshot],
                    )
                    invalid_block_response = node_b.client.post(
                        "/peers/blocks/receive",
                        json={
                            "origin_node_id": node_a.node_id,
                            "network_name": NODE_NETWORK_NAME,
                            "related_submission_id": invalid_submission.submission_id,
                            "certificate": invalid_certificate.to_dict(),
                            "block": invalid_block.to_dict(),
                        },
                    )
                    invalid_block_body = _response_json(
                        invalid_block_response,
                        expected_status=400,
                        context="invalid transfer-bearing block receive",
                    )
                    invalid_block_code = _detail_code(invalid_block_body)
                    invalid_block_message = _detail_message(invalid_block_body).lower()
                    _assert_true(
                        invalid_block_code in {"invalid_transaction_signature", "transaction_id_mismatch"}
                        or "signature" in invalid_block_message
                        or "tx_id" in invalid_block_message,
                        "invalid transfer-bearing block should be rejected for its malformed native transaction payload",
                    )
                    _assert_equal(_wallet_balance(node_b.client, sender.address), baseline_node_b_sender, "node B sender balance unchanged after invalid block")
                    _assert_equal(_wallet_balance(node_b.client, recipient.address), baseline_node_b_recipient, "node B recipient balance unchanged after invalid block")

                    transfer_only_block = Block(
                        index=node_a.blockchain.get_latest_block().index + 1,
                        previous_hash=node_a.blockchain.get_latest_block().hash,
                        timestamp=1_000_900.0,
                        transactions=[Transaction("REWARD_POOL", wallets["contributor_one"].public_key, 5, created_at=1_000_900.0)],
                        miner=wallets["contributor_one"].public_key,
                        meme={"encoded_image": "peer-image", "text": "Transfer-only block should fail"},
                        native_transactions=[node_a.blockchain._serialize_native_transaction_for_block(canonical_transaction)],
                        transaction_ids=[tx_id],
                        transaction_count=1,
                        transactions_hash=node_a.blockchain._compute_block_native_transactions_hash(
                            [node_a.blockchain._serialize_native_transaction_for_block(canonical_transaction)]
                        ),
                    )
                    transfer_only_response = node_b.client.post(
                        "/peers/blocks/receive",
                        json={
                            "origin_node_id": node_a.node_id,
                            "network_name": NODE_NETWORK_NAME,
                            "block": transfer_only_block.to_dict(),
                        },
                    )
                    transfer_only_body = _response_json(
                        transfer_only_response,
                        expected_status=400,
                        context="transfer-only block receive",
                    )
                    transfer_only_code = _detail_code(transfer_only_body)
                    transfer_only_message = _detail_message(transfer_only_body).lower()
                    _assert_true(
                        transfer_only_code == "invalid_block_context"
                        or "meme-mined" in transfer_only_message
                        or "certified meme block metadata" in transfer_only_message,
                        "transfer-only block rejection should preserve the meme-mined block requirement",
                    )
                    _assert_equal(node_b.blockchain.get_latest_block().hash, reward_mint["block_hash"], "transfer-only block must not advance node B chain")

                    _log(verbose, "Step 6/8: Verifying that settlement does not happen until a real meme-mined block includes the transaction.")
                    pre_settlement_a = _transaction_record(node_a.client, tx_id)
                    pre_settlement_b = _transaction_record(node_b.client, tx_id)
                    _assert_equal(pre_settlement_a["status"], "mempool", "node A transaction should remain in mempool before settlement")
                    _assert_equal(pre_settlement_b["status"], "mempool", "node B transaction should remain in mempool before settlement")
                    _assert_equal(_wallet_balance(node_a.client, recipient.address)["final_balance"], "0", "recipient must not settle before block inclusion on node A")
                    _assert_equal(_wallet_balance(node_b.client, recipient.address)["final_balance"], "0", "recipient must not settle before block inclusion on node B")

                    _log(verbose, "Step 7/8: Minting a certified meme block on Node A that includes the transfer and settles it locally.")
                    settlement_submission, _settlement_certificate = _prepare_mintable_submission(
                        node_a.blockchain,
                        project_image,
                        wallets,
                        text="Task 8.9 settlement block",
                        voter_prefix="task8-9-settlement",
                    )
                    settlement_mint = _response_json(
                        node_a.client.post(
                            f"/mint-queue/{settlement_submission.submission_id}/mint",
                            data={"miner": wallets["contributor_one"].public_key},
                        ),
                        expected_status=200,
                        context="settlement block mint",
                    )
                    _assert_true(settlement_mint["minted"] is True, "settlement mint should succeed")
                    _assert_true(settlement_mint["transactions_included"] >= 1, "settlement block should include at least one native transfer")
                    _assert_true(tx_id in settlement_mint["transaction_ids"], "settlement block should include the expected tx_id")
                    chain_view = _response_json(node_a.client.get("/chain"), expected_status=200, context="node A chain view")
                    settlement_block = chain_view["chain"][-1]
                    settlement_block_payload = node_a.blockchain.get_latest_block().to_dict()
                    _assert_true(tx_id in settlement_block["transaction_ids"], "settlement block explorer view should include the tx_id")
                    settled_a = _transaction_record(node_a.client, tx_id)
                    _assert_equal(settled_a["status"], "settled", "node A transaction should settle after mint")
                    _assert_equal(settled_a["included_block_hash"], settlement_mint["block_hash"], "node A included block hash")
                    _assert_equal(str(settled_a["included_block_height"]), str(settlement_mint["block_height"]), "node A included block height")
                    _assert_equal(_mempool(node_a.client)["count"], 0, "node A mempool should be empty after settlement")
                    final_sender_a = _wallet_balance(node_a.client, sender.address)
                    final_recipient_a = _wallet_balance(node_a.client, recipient.address)
                    _assert_equal(final_sender_a["final_balance"], "2", "node A final sender balance after settlement")
                    _assert_equal(final_recipient_a["final_balance"], TRANSFER_AMOUNT, "node A final recipient balance after settlement")

                    _log(verbose, "Step 8/8: Confirming Node B accepts the settlement block, clears mempool state, and matches Node A exactly.")
                    settled_b = _transaction_record(node_b.client, tx_id)
                    _assert_equal(settled_b["status"], "settled", "node B transaction should settle after peer block receive")
                    _assert_equal(settled_b["included_block_hash"], settlement_mint["block_hash"], "node B included block hash")
                    _assert_equal(str(settled_b["included_block_height"]), str(settlement_mint["block_height"]), "node B included block height")
                    _assert_equal(_mempool(node_b.client)["count"], 0, "node B mempool should be empty after settlement")
                    final_sender_b = _wallet_balance(node_b.client, sender.address)
                    final_recipient_b = _wallet_balance(node_b.client, recipient.address)
                    _assert_equal(final_sender_b["final_balance"], final_sender_a["final_balance"], "sender final balances must match")
                    _assert_equal(final_recipient_b["final_balance"], final_recipient_a["final_balance"], "recipient final balances must match")
                    latest_summary_a = _response_json(node_a.client.get("/chain/summary"), expected_status=200, context="node A final chain summary")
                    latest_summary_b = _response_json(node_b.client.get("/chain/summary"), expected_status=200, context="node B final chain summary")
                    _assert_equal(latest_summary_b["chain_height"], latest_summary_a["chain_height"], "final chain heights must match")
                    _assert_equal(latest_summary_b["latest_block_hash"], latest_summary_a["latest_block_hash"], "final latest block hash must match")

                    duplicate_block = node_b.client.post(
                        "/peers/blocks/receive",
                        json={
                            "origin_node_id": node_a.node_id,
                            "network_name": NODE_NETWORK_NAME,
                            "related_submission_id": settlement_submission.submission_id,
                            "block": settlement_block_payload,
                        },
                    )
                    duplicate_block_body = _response_json(
                        duplicate_block,
                        expected_status=200,
                        context="duplicate block receive",
                    )
                    _assert_equal(duplicate_block_body["status"], "duplicate", "duplicate settlement block should be idempotent")
                    _assert_equal(_wallet_balance(node_b.client, sender.address)["final_balance"], final_sender_b["final_balance"], "duplicate block must not double-settle sender")
                    _assert_equal(_wallet_balance(node_b.client, recipient.address)["final_balance"], final_recipient_b["final_balance"], "duplicate block must not double-settle recipient")

                    summary = {
                        "passed": True,
                        "node_a_url": node_a.public_url,
                        "node_b_url": node_b.public_url,
                        "network_name": NODE_NETWORK_NAME,
                        "sender_address": sender.address.lower(),
                        "recipient_address": recipient.address.lower(),
                        "reward_block_hash": reward_mint["block_hash"],
                        "reward_block_height": reward_mint["block_height"],
                        "transfer_tx_id": tx_id,
                        "transfer_amount": TRANSFER_AMOUNT,
                        "mempool_status_node_a": pre_settlement_a["status"],
                        "mempool_status_node_b": pre_settlement_b["status"],
                        "settlement_block_hash": settlement_mint["block_hash"],
                        "settlement_block_height": settlement_mint["block_height"],
                        "final_sender_balance_node_a": final_sender_a["final_balance"],
                        "final_sender_balance_node_b": final_sender_b["final_balance"],
                        "final_recipient_balance_node_a": final_recipient_a["final_balance"],
                        "final_recipient_balance_node_b": final_recipient_b["final_balance"],
                        "negative_checks": {
                            "duplicate_transaction_gossip_idempotent": True,
                            "duplicate_block_receive_idempotent": True,
                            "tampered_amount_rejected": True,
                            "tampered_signature_rejected": True,
                            "wrong_network_transaction_rejected": True,
                            "conflicting_nonce_rejected": True,
                            "invalid_transfer_bearing_block_rejected_without_balance_mutation": True,
                            "transfer_only_block_rejected": True,
                            "transaction_cannot_settle_without_meme_mined_block": True,
                            "peer_receive_required_no_wallet_session": True,
                        },
                    }
            finally:
                if node_a is not None:
                    node_a.client.close()
                if node_b is not None:
                    node_b.client.close()
                for alias in ["task8_9_node_a_api", "task8_9_node_b_api"]:
                    sys.modules.pop(alias, None)

    if verbose:
        print("", flush=True)
        print("Two-node native transfer verification summary", flush=True)
        print(f"Node A URL: {summary['node_a_url']}", flush=True)
        print(f"Node B URL: {summary['node_b_url']}", flush=True)
        print(f"Network: {summary['network_name']}", flush=True)
        print(f"Sender: {summary['sender_address']}", flush=True)
        print(f"Recipient: {summary['recipient_address']}", flush=True)
        print(f"Reward block: {summary['reward_block_hash']} @ height {summary['reward_block_height']}", flush=True)
        print(f"Transfer tx_id: {summary['transfer_tx_id']}", flush=True)
        print(f"Transfer amount: {summary['transfer_amount']} ZOID", flush=True)
        print(f"Node A mempool status before settlement: {summary['mempool_status_node_a']}", flush=True)
        print(f"Node B mempool status before settlement: {summary['mempool_status_node_b']}", flush=True)
        print(
            f"Settlement block: {summary['settlement_block_hash']} @ height {summary['settlement_block_height']}",
            flush=True,
        )
        print(
            f"Sender final balance: Node A {summary['final_sender_balance_node_a']} / Node B {summary['final_sender_balance_node_b']}",
            flush=True,
        )
        print(
            f"Recipient final balance: Node A {summary['final_recipient_balance_node_a']} / Node B {summary['final_recipient_balance_node_b']}",
            flush=True,
        )
        print("TWO-NODE NATIVE TRANSFER TEST PASSED", flush=True)

    return summary
