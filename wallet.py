# Import statements
import ecdsa

class Wallet:
    def __init__(self, private_key=None):
        if private_key:
            self.private_key = private_key
            self.public_key = self.generate_public_key()
        else:
            self.private_key, self.public_key = self.generate_key_pair()

    @staticmethod
    def generate_key_pair():
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        private_key = sk.to_string().hex()
        public_key = sk.verifying_key.to_string().hex()
        return private_key, public_key

    def generate_public_key(self):
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
        return sk.verifying_key.to_string().hex()

    def get_keys(self):
        """Return the private and public keys."""
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
        }

    def __str__(self):
        return f"Wallet(Public Key: {self.public_key}, Private Key: {self.private_key})"
