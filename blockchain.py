"""
blockchain.py

Registers an image's SHA-256 fingerprint on the Ethereum Sepolia testnet,
and retrieves it back later for comparison.

HOW THIS WORKS (beginner explanation):
There is no smart contract here - that's a deliberate simplification for a
hackathon demo. Instead, we send a normal, tiny (0 ETH) transaction from our
wallet to itself, and put the SHA-256 hash in the transaction's "data"
field. Once a transaction is confirmed on Ethereum it is permanent and
public, so that data field can never be changed afterwards - which is
exactly the "tamper-evident timestamp" property we want.

To check a fingerprint later, we don't search the whole blockchain (that
would require a smart contract with a lookup table). Instead, the caller
keeps the transaction hash returned by register_fingerprint() - e.g. saved
next to the image record in your own app data - and passes it back into
retrieve_fingerprint() to read the hash back off-chain.

IMPORTANT: registering a hash on Sepolia does NOT prove that the underlying
face match was correct. It only proves that this exact hash existed at this
exact time and has not been altered since. Treat it as a tamper-evident
timestamp, not as proof of identity.
"""

import binascii

from web3.exceptions import TransactionNotFound, TimeExhausted

from config import get_web3, get_wallet_address, ConfigError, WALLET_PRIVATE_KEY


RECEIPT_TIMEOUT_SECONDS = 120


class BlockchainError(Exception):
    """Base class for all blockchain.py errors."""


class TransactionError(BlockchainError):
    """A transaction could not be built, sent, or confirmed."""


class FingerprintNotFoundError(BlockchainError):
    """No transaction was found for the given transaction hash."""


def _sha256_hex_to_bytes(sha256_hash: str) -> bytes:
    try:
        return bytes.fromhex(sha256_hash)
    except (binascii.Error, ValueError) as exc:
        raise TransactionError(
            f"'{sha256_hash}' is not a valid hex SHA-256 hash: {exc}"
        ) from exc


def register_fingerprint(sha256_hash: str) -> dict:
    """
    Store a SHA-256 fingerprint on Sepolia by sending a 0 ETH transaction
    to our own wallet, with the hash placed in the transaction's data field.

    Args:
        sha256_hash: a 64-character hex SHA-256 string, e.g. the 'sha256'
            value from image_fingerprint.generate_fingerprint().

    Returns:
        {
            "tx_hash": str,        # save this - needed to retrieve later
            "status": "confirmed" | "pending",
            "block_number": int | None,
        }
        "pending" means the transaction was sent but did not confirm within
        RECEIPT_TIMEOUT_SECONDS - this can happen on a slow testnet and is
        not necessarily an error. Call retrieve_fingerprint() later to check.

    Raises:
        ConfigError: required environment variables are missing/invalid.
        TransactionError: the hash is invalid, or the transaction could not
            be built or sent (e.g. insufficient test ETH for gas).
    """
    data_bytes = _sha256_hex_to_bytes(sha256_hash)

    web3 = get_web3()  # raises ConfigError if misconfigured
    address = get_wallet_address()  # raises ConfigError if misconfigured

    try:
        transaction = {
            "from": address,
            "to": address,       # sending to ourselves - we only care
                                  # about the data field, not the value
            "value": 0,
            "data": data_bytes,
            "nonce": web3.eth.get_transaction_count(address),
            "chainId": web3.eth.chain_id,
            "gasPrice": web3.eth.gas_price,
        }
        transaction["gas"] = web3.eth.estimate_gas(transaction)

        signed = web3.eth.account.sign_transaction(
            transaction, private_key=WALLET_PRIVATE_KEY
        )
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = web3.to_hex(tx_hash)

    except ConfigError:
        raise
    except Exception as exc:
        raise TransactionError(
            f"Failed to send fingerprint registration transaction: {exc}. "
            "If this mentions insufficient funds, your wallet needs "
            "Sepolia test ETH from a faucet."
        ) from exc

    try:
        receipt = web3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS
        )
        return {
            "tx_hash": tx_hash_hex,
            "status": "confirmed",
            "block_number": receipt["blockNumber"],
        }
    except TimeExhausted:
        return {
            "tx_hash": tx_hash_hex,
            "status": "pending",
            "block_number": None,
        }


def retrieve_fingerprint(tx_hash: str) -> dict:
    """
    Look up a previously registered fingerprint by its transaction hash.

    Args:
        tx_hash: the transaction hash returned by register_fingerprint().

    Returns:
        {
            "sha256_hash": str,   # the hash that was stored, as hex
            "confirmed": bool,    # True once the transaction is mined
            "block_number": int | None,
        }

    Raises:
        ConfigError: required environment variables are missing/invalid.
        FingerprintNotFoundError: no transaction exists for tx_hash.
        TransactionError: the transaction's data field could not be read.
    """
    web3 = get_web3()  # raises ConfigError if misconfigured

    try:
        tx = web3.eth.get_transaction(tx_hash)
    except TransactionNotFound as exc:
        raise FingerprintNotFoundError(
            f"No transaction found for tx_hash '{tx_hash}': {exc}"
        ) from exc
    except Exception as exc:
        raise TransactionError(
            f"Failed to fetch transaction '{tx_hash}': {exc}"
        ) from exc

    try:
        sha256_hash = tx["input"].hex()
        if sha256_hash.startswith("0x"):
            sha256_hash = sha256_hash[2:]
    except (KeyError, AttributeError) as exc:
        raise TransactionError(
            f"Transaction '{tx_hash}' has no readable data field: {exc}"
        ) from exc

    confirmed = tx["blockNumber"] is not None

    return {
        "sha256_hash": sha256_hash,
        "confirmed": confirmed,
        "block_number": tx["blockNumber"] if confirmed else None,
    }