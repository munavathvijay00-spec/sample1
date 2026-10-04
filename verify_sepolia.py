#!/usr/bin/env python3
"""
Utility script to check Sepolia RPC connectivity, block number, and account balance.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

DEFAULT_SEPOLIA_RPC = os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()

def check_connection():
    print("=" * 60)
    print(" Sepolia Network Connectivity & Account Checker")
    print("=" * 60)
    print(f"Connecting to RPC: {DEFAULT_SEPOLIA_RPC}...")

    w3 = Web3(Web3.HTTPProvider(DEFAULT_SEPOLIA_RPC))
    if not w3.is_connected():
        fallback_rpcs = [
            "https://rpc.sepolia.org",
            "https://sepolia.drpc.org",
            "https://1rpc.io/sepolia",
        ]
        connected = False
        for fb in fallback_rpcs:
            print(f"Trying fallback: {fb}...")
            w3 = Web3(Web3.HTTPProvider(fb))
            if w3.is_connected():
                connected = True
                print(f"Connected successfully to {fb}")
                break
        if not connected:
            print("[ERROR] Could not connect to any Sepolia RPC endpoint.")
            sys.exit(1)
    else:
        print("[✓] Connected to Sepolia successfully!")

    chain_id = w3.eth.chain_id
    latest_block = w3.eth.block_number
    gas_price = w3.eth.gas_price

    print(f"Chain ID:      {chain_id} (Expected: 11155111)")
    print(f"Latest Block:  {latest_block:,}")
    print(f"Gas Price:     {w3.from_wei(gas_price, 'gwei'):.2f} Gwei")

    if PRIVATE_KEY:
        pk = PRIVATE_KEY if not PRIVATE_KEY.startswith("0x") else PRIVATE_KEY[2:]
        try:
            acc = Account.from_key("0x" + pk)
            balance_wei = w3.eth.get_balance(acc.address)
            balance_eth = w3.from_wei(balance_wei, "ether")
            print(f"\nAccount Address: {acc.address}")
            print(f"SepoliaETH:      {balance_eth:.6f} ETH")
            if balance_wei > 0:
                print("[✓] Account has funds! Ready to deploy and submit signals.")
            else:
                print("[!] Account has 0 ETH. Please request testnet ETH from a faucet:")
                print("    - https://cloud.google.com/application/web3/faucet/ethereum/sepolia")
                print("    - https://sepoliafaucet.com")
        except Exception as e:
            print(f"[!] Invalid PRIVATE_KEY: {e}")
    else:
        print("\n[!] No PRIVATE_KEY configured in .env yet.")
        print("    Configure PRIVATE_KEY in .env before running `python deploy.py`.")
    print("=" * 60)

if __name__ == "__main__":
    check_connection()
