"""
config.py

Minimal configuration for connecting to the Ethereum Sepolia testnet.

WHAT THIS FILE DOES (beginner explanation):
- Reads two secrets from environment variables (never from source code):
    SEPOLIA_RPC_URL     - the URL of a Sepolia node provider (Infura,
                           Alchemy, or a public RPC). This is how we "talk"
                           to the Sepolia blockchain over the internet.
    WALLET_PRIVATE_KEY  - the private key of a throwaway wallet used only
                           for this project. It's needed to sign (authorize)
                           transactions. NEVER use a real/mainnet wallet's
                           key here, and never commit it.
- Exposes get_web3(), which returns a ready-to-use connection, and
  get_wallet_address(), which derives the wallet's public address from the
  private key so you don't have to store the address separately.

Both values must be set via a .env file or real environment variables.
See .env.example for the variable names to add.
"""

import os

from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

SEPOLIA_RPC_URL = os.environ.get("SEPOLIA_RPC_URL")
WALLET_PRIVATE_KEY = os.environ.get("WALLET_PRIVATE_KEY")


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def get_web3() -> Web3:
    """
    Build and return a Web3 connection to Sepolia.

    Raises:
        ConfigError: SEPOLIA_RPC_URL is not set, or the node did not
            respond to a basic connectivity check.
    """
    if not SEPOLIA_RPC_URL:
        raise ConfigError(
            "SEPOLIA_RPC_URL is not set. Add it to your .env file. "
            "Free options: Infura, Alchemy, or a public RPC such as "
            "https://ethereum-sepolia-rpc.publicnode.com "
            "See .env.example."
        )

    web3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC_URL))

    if not web3.is_connected():
        raise ConfigError(
            "Could not connect to Sepolia using SEPOLIA_RPC_URL. "
            "Check the URL is correct and the provider is online."
        )

    return web3


def get_wallet_address() -> str:
    """
    Derive the wallet's public address from WALLET_PRIVATE_KEY.

    Raises:
        ConfigError: WALLET_PRIVATE_KEY is not set or is not a valid key.
    """
    if not WALLET_PRIVATE_KEY:
        raise ConfigError(
            "WALLET_PRIVATE_KEY is not set. Add it to your .env file. "
            "Use a throwaway wallet created just for this project - "
            "never your real/mainnet wallet. See .env.example."
        )

    try:
        account = Account.from_key(WALLET_PRIVATE_KEY)
    except (ValueError, TypeError) as exc:
        raise ConfigError(
            f"WALLET_PRIVATE_KEY is not a valid private key: {exc}"
        ) from exc

    return account.address