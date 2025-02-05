import ecdsa
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64


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
        Generates a key pair using ECDSA.
        Returns:
            tuple: private_key (hex), public_key (compressed hex)
        """
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        private_key = sk.to_string().hex()
        public_key = Wallet.compress_public_key(sk.verifying_key)
        return private_key, public_key

    @staticmethod
    def compress_public_key(vk):
        """
        Compresses the public key.
        Args:
            vk (ecdsa.VerifyingKey): The verifying key.
        Returns:
            str: Compressed public key in hexadecimal format.
        """
        x = vk.pubkey.point.x()
        y = vk.pubkey.point.y()
        prefix = "02" if y % 2 == 0 else "03"
        return prefix + format(x, "x").zfill(64)  # Pad x to 64 hex characters

    def generate_public_key(self):
        """
        Generates the public key from the private key.
        Returns:
            str: Compressed public key in hexadecimal format.
        """
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        public_key = Wallet.compress_public_key(vk)
        return public_key

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
            sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
            vk = sk.verifying_key
            generated_public_key = Wallet.compress_public_key(vk)
            return generated_public_key == public_key
        except Exception as e:
            print(f"Key validation failed: {e}")
            return False

    def sign_data(self, data):
        """
        Signs data using the private key.
        Args:
            data (str): The data to be signed.
        Returns:
            str: The signature as a base64-encoded string.
        """
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
        signature = sk.sign(data.encode('utf-8'))
        return base64.b64encode(signature).decode('utf-8')

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
            vk = ecdsa.VerifyingKey.from_string(
                bytes.fromhex(public_key[2:]), curve=ecdsa.SECP256k1
            )
            vk.verify(base64.b64decode(signature), data.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Verification failed: {e}")
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
        wallet = cls()
        wallet.public_key = data["public_key"]
        wallet.private_key = data["private_key"]
        return wallet  # ✅ Ensures wallet object is correctly reconstructed

    def __str__(self):
        return f"Wallet(Public Key: {self.public_key}, Private Key: {self.private_key})"