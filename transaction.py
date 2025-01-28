# Import statements
import ecdsa
import base64

class Transaction:
    def __init__(self, sender, recipient, amount, tip=0, payload_size_kb=0):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.tip = tip
        self.payload_size_kb = payload_size_kb
        self.signature = None

    def to_dict(self):
        """Convert transaction to a dictionary."""
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "tip": self.tip,
            "signature": self.signature,
            "payload_size_kb": self.payload_size_kb,
        }

    def calculate_fee(self):
        """Calculate the total transaction fee based on payload size."""
        base_fee = 0.01  # Base fee
        additional_fee = 0.001 * self.payload_size_kb  # 0.001 ZoidbergCoins per KB
        return base_fee + additional_fee

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
            # Attempt to sign the transaction
            sk = ecdsa.SigningKey.from_string(bytes.fromhex(private_key), curve=ecdsa.SECP256k1)
            self.signature = base64.b64encode(sk.sign(transaction_data.encode())).decode()
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

            # Validate transaction data against the signature
            transaction_data = f"{self.sender}{self.recipient}{self.amount}{self.tip}"
            print(f"Debug: Validating transaction data: {transaction_data}")
            print(f"Debug: Signature: {self.signature}")

            vk = ecdsa.VerifyingKey.from_string(bytes.fromhex(self.sender), curve=ecdsa.SECP256k1)
            vk.verify(base64.b64decode(self.signature), transaction_data.encode())
            print("Debug: Transaction is valid.")
            return True
        except ecdsa.BadSignatureError:
            # Specific handling for invalid signature
            print("Debug: Invalid signature detected.")
            return False
        except Exception as e:
            # General exception handling
            print(f"Debug: Transaction is not valid - {e}")
            return False