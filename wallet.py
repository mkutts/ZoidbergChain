import base64
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils


SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def _legacy_private_key_from_hex(private_key):
    """Load the exact 32-byte scalar format used by legacy wallets."""
    private_key_bytes = bytes.fromhex(private_key)
    if len(private_key_bytes) != 32:
        raise ValueError("Legacy private keys must be exactly 32 bytes.")
    scalar = int.from_bytes(private_key_bytes, "big")
    if not 0 < scalar < SECP256K1_ORDER:
        raise ValueError("Legacy private key scalar is outside SECP256K1 range.")
    return ec.derive_private_key(scalar, ec.SECP256K1())


def _legacy_raw_signature_from_der(der_signature):
    r, s = utils.decode_dss_signature(der_signature)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _legacy_der_signature_from_raw(raw_signature):
    if len(raw_signature) != 64:
        raise ValueError("Legacy signatures must be exactly 64 raw bytes.")
    r = int.from_bytes(raw_signature[:32], "big")
    s = int.from_bytes(raw_signature[32:], "big")
    if not 0 < r < SECP256K1_ORDER or not 0 < s < SECP256K1_ORDER:
        raise ValueError("Legacy signature values are outside SECP256K1 range.")
    return utils.encode_dss_signature(r, s)


class Wallet:
    def __init__(self, private_key=None):
        if private_key:
            self.private_key = private_key
            self.public_key = self.generate_public_key()
        else:
            self.private_key, self.public_key = self.generate_key_pair()

    @staticmethod
    def generate_key_pair():
        """
        Generates a key pair using legacy-compatible SECP256K1 ECDSA.
        Returns:
            tuple: private_key (hex), public_key (compressed hex)
        """
        private_key_object = ec.generate_private_key(ec.SECP256K1())
        private_key = private_key_object.private_numbers().private_value.to_bytes(32, "big").hex()
        public_key = Wallet.compress_public_key(private_key_object.public_key())
        return private_key, public_key

    @staticmethod
    def compress_public_key(vk):
        """
        Compresses the public key.
        Args:
            vk (EllipticCurvePublicKey): The verifying key.
        Returns:
            str: Compressed public key in hexadecimal format.
        """
        return vk.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.CompressedPoint,
        ).hex()

    def generate_public_key(self):
        """
        Generates the public key from the private key.
        Returns:
            str: Compressed public key in hexadecimal format.
        """
        return Wallet.compress_public_key(_legacy_private_key_from_hex(self.private_key).public_key())

    def get_keys(self):
        """
        Returns the private and public keys.
        """
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
        }

    @staticmethod
    def validate_private_key(private_key, public_key):
        """
        Validates if the provided private key matches the public key.
        Args:
            private_key (str): Hexadecimal private key.
            public_key (str): Compressed hexadecimal public key.
        Returns:
            bool: True if the private key matches the public key, False otherwise.
        """
        try:
            generated_public_key = Wallet.compress_public_key(
                _legacy_private_key_from_hex(private_key).public_key()
            )
            return generated_public_key == public_key
        except Exception:
            return False

    def sign_data(self, data):
        """
        Signs data using the private key.
        Args:
            data (str): The data to be signed.
        Returns:
            str: The signature as a base64-encoded string.
        """
        private_key = _legacy_private_key_from_hex(self.private_key)
        der_signature = private_key.sign(data.encode("utf-8"), ec.ECDSA(hashes.SHA1()))
        return base64.b64encode(_legacy_raw_signature_from_der(der_signature)).decode("utf-8")

    @staticmethod
    def verify_signature(public_key, signature, data):
        """
        Verifies a signature with the provided public key and data.
        Args:
            public_key (str): The compressed public key.
            signature (str): The base64-encoded signature to verify.
            data (str): The original data.
        Returns:
            bool: True if the signature is valid, False otherwise.
        """
        try:
            # Keep the historical helper's broken compressed-key behavior.
            vk = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256K1(), bytes.fromhex(public_key[2:])
            )
            vk.verify(
                _legacy_der_signature_from_raw(base64.b64decode(signature)),
                data.encode("utf-8"),
                ec.ECDSA(hashes.SHA1()),
            )
            return True
        except (ValueError, TypeError, InvalidSignature):
            return False
        
    def to_dict(self):
        """Convert the Wallet object into a dictionary."""
        return {
            "public_key": self.public_key,
            "private_key": self.private_key,  # ✅ Save private key for later recovery
        }

    @classmethod
    def from_dict(cls, data):
        """Convert a dictionary back to a Wallet object."""
        wallet = cls.__new__(cls)
        wallet.public_key = data["public_key"]
        wallet.private_key = data.get("private_key")
        return wallet  # ✅ Ensures wallet object is correctly reconstructed

    def __str__(self):
        return f"Wallet(Public Key: {self.public_key})"
