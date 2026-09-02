import base64
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from wallet import _legacy_der_signature_from_raw, _legacy_private_key_from_hex, _legacy_raw_signature_from_der

class Transaction:
    def __init__(self, sender, recipient, amount, tip=0, payload_size_kb=0, signature=None, created_at=None):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.tip = tip
        self.payload_size_kb = payload_size_kb
        self.signature = signature
        self.created_at = created_at if created_at is not None else time.time()

    def to_dict(self):
        """Convert transaction to a dictionary."""
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "tip": self.tip,
            "signature": self.signature,
            "payload_size_kb": self.payload_size_kb,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data):
        """Convert a dictionary back to a Transaction object"""
        return cls(
            sender=data["sender"],
            recipient=data["recipient"],
            amount=data["amount"],
            tip=data.get("tip", 0),
            payload_size_kb=data.get("payload_size_kb", 0),
            signature=data.get("signature"),
            created_at=data.get("created_at", 0),
        )

    def sign_transaction(self, private_key):
        if self.sender == "GENESIS" or self.sender == "REWARD_POOL":
            print("Debug: Skipping signing for GENESIS or REWARD_POOL transaction.")
            return  # Skip signing for special transactions

        if not private_key:
            raise Exception("No private key provided for signing!")

        # Create transaction data string for signing
        transaction_data = f"{self.sender}{self.recipient}{self.amount}{self.tip}"
        print(f"Debug: Signing transaction data: {transaction_data}")

        try:
            private_key_object = _legacy_private_key_from_hex(private_key)
            der_signature = private_key_object.sign(
                transaction_data.encode(), ec.ECDSA(hashes.SHA1())
            )
            self.signature = base64.b64encode(_legacy_raw_signature_from_der(der_signature)).decode()
            print(f"Debug: Transaction signed with signature: {self.signature}")
        except Exception as e:
            # Log any errors during the signing process
            print(f"Debug: Error during signing - {e}")
            raise Exception(f"Failed to sign transaction: {e}")

    def is_valid(self):
        try:
            if self.sender == "GENESIS" or self.sender == "REWARD_POOL":
                print("Debug: Skipping validation for GENESIS or REWARD_POOL transaction.")
                return True  # Skip validation for special transactions

            if not self.signature:
                raise Exception("Transaction signature is missing.")

            # Validate transaction data against the signature (NO FEES)
            transaction_data = f"{self.sender}{self.recipient}{self.amount}{self.tip}"
            print(f"Debug: Validating transaction data: {transaction_data}")
            print(f"Debug: Signature: {self.signature}")

            vk = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256K1(), bytes.fromhex(self.sender)
            )
            vk.verify(
                _legacy_der_signature_from_raw(base64.b64decode(self.signature)),
                transaction_data.encode(),
                ec.ECDSA(hashes.SHA1()),
            )
            print("Debug: Transaction is valid.")
            return True
        except InvalidSignature:
            print("Debug: Invalid signature detected.")
            return False
        except Exception as e:
            print(f"Debug: Transaction is not valid - {e}")
            return False
