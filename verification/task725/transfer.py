"""Simulated v3 loopback transfers through real peer wrappers/client/serializers.

No active router, blockchain, peer directory or public address is used. Counts
are actual HTTP stream octets, not IP/TCP/TLS packet-size estimates.
"""
import json
import logging
from pathlib import Path
import sys
import socketserver
import threading
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))

import requests
from starlette.responses import JSONResponse
from canonical_v3.primitives import canonical
from codec_prototype.isolated_decoder import IsolatedDecoder
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_peer_message import build_protocol_v1_peer_request_headers, verify_protocol_v1_peer_request
from services.peer_transport_service import PeerHttpTransport, PeerBroadcastService
from services.peer_chain_sync_service import PeerChainSyncService
from verification.task721.bridge import canonical_media
from verification.task725.measure import CONFIG, save, sha

NODE = 'task725-loopback'
NETWORK = 'zoidberg-testnet'
SECRET = 'PUBLIC-task725-fixture-only'
NOW = 1793743200


class Harness:
    def __init__(self, decoder):
        self.decoder = decoder
        self.rows = []
        self.records = []
        self.label = ''
        self.errors = []
        self.sequence = 0

    def headers(self, method, path, payload, origin, **_):
        self.sequence += 1
        return build_protocol_v1_peer_request_headers(method, path, payload if method == 'POST' else None,
            origin, network_name=NETWORK, secret=SECRET, timestamp=NOW,
            nonce=f'task725-{self.sequence:08d}', query_params=payload if method == 'GET' else None)

    def validate(self, rec):
        raw = canonical(rec)
        result = canonical_media(raw, CONFIG, decoder=self.decoder)
        assert result.integrity_verified and not result.consensus_authorized
        assert result.block_hash == rec['hash']
        return len(raw)

    def handle(self, handler):
        # Read the original stream, retaining exact delimiters and capitalization.
        request_line = handler.rfile.readline(8192)
        header_lines = []
        while True:
            line = handler.rfile.readline(16384)
            assert line
            header_lines.append(line)
            if line == b'\r\n':
                break
        headers = dict(line.decode('latin1').strip().split(': ', 1) for line in header_lines[:-1])
        method, target, version = request_line.decode('ascii').strip().split(' ')
        assert version == 'HTTP/1.1'
        parsed = urlsplit(target)
        length = int(headers.get('Content-Length', '0'))
        assert length <= 16*1024*1024
        body = handler.rfile.read(length)
        assert len(body) == length
        payload = json.loads(body) if body else None
        if method == 'GET':
            query = parse_qs(parsed.query)
            auth_payload = dict(from_height=int(query['from_height'][0]), include_media_bytes=True)
        else:
            auth_payload = payload
        auth = verify_protocol_v1_peer_request(method=method, path=parsed.path, headers=headers,
            payload=auth_payload, expected_network_id=PUBLIC_TESTNET_V1_NETWORK_ID, secret=SECRET,
            timestamp_window_seconds=60, now=NOW)
        assert auth.sender_node_id == NODE
        canonical_bytes = 0; certificate_bytes = 0; n = 0
        if method == 'POST':
            if parsed.path == '/peers/blocks/receive':
                canonical_bytes = self.validate(payload['block']); n = 1
                if payload.get('certificate') is not None:
                    certificate_bytes = len(canonical(payload['certificate']))
                result = dict(accepted=True, integration_status='SIMULATED_ONLY')
            else:
                assert parsed.path == '/peers/certificates/receive'
                certificate_bytes = len(canonical(payload['certificate']))
                result = dict(accepted=True, integration_status='SIMULATED_ONLY')
        else:
            assert parsed.path == '/peers/chain/blocks'
            selected = [rec for rec in self.records if rec['envelope']['payload']['index'] >= auth_payload['from_height']]
            canonical_bytes = sum(len(canonical(r)) for r in selected); n = len(selected)
            certificates = [r['envelope']['payload']['admission_certificate'] for r in selected]
            certificate_bytes = sum(len(canonical(c)) for c in certificates)
            result = dict(blocks=selected, certificates=certificates, originality_evidence=[])
        # Actual Starlette JSONResponse serializer used by the API stack. The
        # response wrapper is source-derived; this is NOT an active v3 route.
        response = JSONResponse(result)
        response_headers = b'HTTP/1.1 200 OK\r\n' + b''.join(k+b': '+v+b'\r\n' for k,v in response.raw_headers) + b'connection: close\r\n\r\n'
        request_headers = request_line + b''.join(header_lines)
        auth_bytes = sum(len(line) for line in header_lines if line.lower().startswith(b'x-zoid-'))
        self.rows.append(dict(label=self.label, method=method, target=target, blocks=n,
            canonical_payload_bytes=canonical_bytes, duplicated_certificate_value_bytes=certificate_bytes,
            request_body_bytes=len(body), response_body_bytes=len(response.body),
            application_framing_bytes=len(body)+len(response.body)-canonical_bytes,
            request_http_framing_bytes=len(request_headers), response_http_framing_bytes=len(response_headers),
            peer_auth_header_bytes=auth_bytes, http_stream_bytes=len(request_headers)+len(body)+len(response_headers)+len(response.body),
            request_body_sha256=sha(body), response_body_sha256=sha(response.body),
            authenticated_fixture_headers=True,
            content_encoding=headers.get('Content-Encoding'), transfer_encoding=headers.get('Transfer-Encoding')))
        # Record before publishing the response so the sequential client cannot
        # finish a request and advance the label before accounting is complete.
        handler.wfile.write(response_headers + response.body)
        handler.wfile.flush()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(30)
        try:
            self.server.harness.handle(self)
        except BaseException as exc:
            self.server.harness.errors.append(repr(exc))
            raise


def run(out, scratch, groups, decoder, *, allow_unavailable=True):
    harness = Harness(decoder)
    server = socketserver.TCPServer(('127.0.0.1', 0), Handler)
    server.harness = harness
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_address[1]}'
    session = requests.Session(); session.trust_env = False
    session.RequestException = requests.RequestException
    transport = PeerHttpTransport(session)
    broadcast = PeerBroadcastService(transport, harness.headers, logging.getLogger('task725'))
    history = PeerChainSyncService(transport, harness.headers, logging.getLogger('task725'))
    peer = dict(node_id='task725-receiver', url=url)
    peers = SimpleNamespace(list_active_peers=lambda **_: [peer])
    populations = {}
    try:
        for name, raws in groups.items():
            if name == 'native_index_control':
                continue
            start = len(harness.rows)
            records = [json.loads(r) for r in raws]
            for rec in records:
                p = rec['envelope']['payload']
                certificate = SimpleNamespace(to_dict=lambda c=p['admission_certificate']: c)
                obj = SimpleNamespace(to_dict=lambda r=rec: r, hash=rec['hash'])
                harness.label = name+':propagation'
                report = broadcast.broadcast_block(obj, peers, NODE, NETWORK, p['submission_id'], certificate, 30)
                if report['failed'] and 'WinError 10013' in str(report):
                    if allow_unavailable:
                        save(out, 'restricted_loopback_attempt.json', dict(status='UNAVAILABLE', reason='Windows socket restriction WinError 10013',
                            action='Run transfer.py separately with permission for 127.0.0.1 only. No transfer totals asserted by this attempt.',
                            report=report))
                        print('Loopback requires local-connection permission; storage/recovery evidence complete. Run transfer.py separately.',flush=True)
                        return
                    raise PermissionError('Windows blocks the disposable loopback connection: WinError 10013')
                assert report['succeeded'] == 1 and report['failed'] == 0, report
                assert report['results'][0]['certificate']['status'] == 'sent'
            # Existing fetch_blocks has no limit; bounded fixture server chooses
            # a finite test history. It is not pagination implemented in v3.
            for label, selected in [('historical_one', records[:1]), ('historical_batch8', records[:8]), ('fresh_history', records)]:
                harness.records = selected
                harness.label = name+':'+label
                result = history.fetch_blocks(peer, 0, origin_node_id=NODE, network_name=NETWORK, timeout_seconds=30)
                assert len(result['blocks']) == len(selected)
                for actual, expected in zip(result['blocks'], selected, strict=True):
                    assert canonical(actual) == canonical(expected)
                    harness.validate(actual)
            sub = harness.rows[start:]
            prop = [r for r in sub if r['label'].endswith(':propagation')]
            historical_rows = [r for r in sub if r['label'].endswith(':fresh_history')]
            assert len(historical_rows) == 1
            total = sum(len(r) for r in raws)
            outgoing = sum(r['request_body_bytes']+r['request_http_framing_bytes'] for r in prop)
            acknowledgments = sum(r['response_body_bytes']+r['response_http_framing_bytes'] for r in prop)
            fresh = historical_rows[0]
            populations[name] = dict(n=len(raws), canonical_bytes=total, propagation_sender_bytes=outgoing,
                propagation_acknowledgment_bytes=acknowledgments, propagation_stream_ratio=outgoing/total,
                propagation_ack_ratio=acknowledgments/total,
                historical_response_bytes=fresh['response_body_bytes']+fresh['response_http_framing_bytes'],
                historical_request_bytes=fresh['request_http_framing_bytes'],
                historical_response_ratio=(fresh['response_body_bytes']+fresh['response_http_framing_bytes'])/total,
                propagation_application_body_bytes=sum(r['request_body_bytes'] for r in prop),
                request_count=len(prop)+3)
            print('Loopback transfer', name, len(raws), 'propagations + single/batch/fresh history', flush=True)
        assert not harness.errors, harness.errors
    finally:
        session.close(); server.shutdown(); server.server_close(); thread.join(timeout=5)
    save(out, 'transfer.json', dict(version=1, populations=populations, exchanges=harness.rows,
        verdict='SIMULATED TRANSFER, measured real HTTP stream bytes; not measured production v3 P2P',
        boundary='Real PeerBroadcastService.broadcast_block (separate certificate then wrapper with duplicated certificate), PeerChainSyncService.fetch_blocks, PeerHttpTransport/requests, real HMAC headers/verifier and Starlette response serializer. v3 fixture handler replaces incompatible active endpoints.',
        framing='Canonical bytes, body/application overhead and HTTP/1.1 header/start-line octets separately measured. Auth header bytes are a SUBSET of request HTTP framing, never added twice.',
        protocol='Unencrypted loopback HTTP/1.1, one connection per exchange, no redirects, default requests retries=0, no content or chunk compression. Response JSON framing mirrors history API shape; external originality_evidence absent/unqualified.',
        packet_overhead_bytes=None, tcp_retransmissions=None, tls_bytes=None,
        retransmission_note='No application retries/failures observed; packet capture not performed, TCP retransmissions and IP/TCP/link overhead unobserved. Not assumed zero for production.',
        sync_limit='Fresh bounded service history only; no genesis/summary/authority/finality/reviewer history handshake or consensus adoption. Unique certificates per test record; repeated certificates in real history may be deduplicated.',
        conditions=dict(bind='127.0.0.1', ephemeral_port=server.server_address[1], sequential=True, concurrency=1, batch_limit=8,
                        header_nonce='Deterministic per-run sequence', timestamp=NOW, public_peers=False)))


if __name__ == '__main__':
    import argparse
    import sqlite3
    import sys
    import tempfile
    import os
    from verification.task725.measure import ROOT
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    args=ap.parse_args();out=args.output.resolve()
    assert out==Path(__file__).resolve().parent or ROOT/'temp' in out.parents
    env=json.loads((out/'environment.json').read_bytes());scratch=Path(env['scratch']).resolve()
    assert ROOT/'temp' in scratch.parents
    os.environ.update(TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1');tempfile.tempdir=str(scratch)
    workloads=json.loads((out/'workloads.json').read_bytes())['rows'];groups={}
    for name,rows in workloads.items():
        source=scratch/f'{name}-full.sqlite'
        c=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        assert c.execute('PRAGMA journal_mode').fetchone()==('delete',)
        groups[name]=[c.execute('SELECT canonical FROM blocks WHERE hash=?',(r['block_hash'],)).fetchone()[0]
                      for r in rows if r['record_bytes'] is not None]
        c.close()
    with IsolatedDecoder() as decoder:
        run(out,scratch,groups,decoder,allow_unavailable=False)
