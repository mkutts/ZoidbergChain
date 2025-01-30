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
        public_key = Wallet.compress_public_key(sk.verifying_key)
        return private_key, public_key

    @staticmethod
    def compress_public_key(vk):
        """Compress the public key."""
        x = vk.pubkey.point.x()
        y = vk.pubkey.point.y()
        prefix = "02" if y % 2 == 0 else "03"
        return prefix + format(x, "x").zfill(64)  # Pad x to 64 hex characters

    def generate_public_key(self):
        """Generate the public key from the private key."""
        sk = ecdsa.SigningKey.from_string(bytes.fromhex(self.private_key), curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        public_key = Wallet.compress_public_key(vk)
        print(f"Debug: Public key generated from private key: {public_key}")
        return public_key

    def get_keys(self):
        """Return the private and public keys."""
        return {
            "private_key": self.private_key,
            "public_key": self.public_key,
        }

    def __str__(self):
        return f"Wallet(Public Key: {self.public_key}, Private Key: {self.private_key})"
