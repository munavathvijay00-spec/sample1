#!/usr/bin/env python3
"""
Deploy TradingSignalStore smart contract to Ethereum Sepolia testnet.
"""

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
COMPILED_CONTRACT_PATH = BASE_DIR / "compiled" / "TradingSignalStore.json"
CONFIG_PATH = BASE_DIR / "contract_config.json"

DEFAULT_SEPOLIA_RPC = os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()

def get_web3_connection(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        fallback_rpcs = [
            "https://rpc.sepolia.org",
            "https://sepolia.drpc.org",
            "https://1rpc.io/sepolia",
        ]
        for fb_rpc in fallback_rpcs:
            if fb_rpc == rpc_url:
                continue
            print(f"[!] Primary RPC failed. Attempting fallback: {fb_rpc}")
            w3 = Web3(Web3.HTTPProvider(fb_rpc))
            if w3.is_connected():
                return w3
        raise ConnectionError(f"Could not connect to Sepolia RPC at {rpc_url} or fallback endpoints.")
    return w3

def deploy():
    print("=" * 60)
    print(" Deploying TradingSignalStore to Sepolia Testnet")
    print("=" * 60)

    if not COMPILED_CONTRACT_PATH.exists():
        print(f"Error: Compiled contract artifact not found at {COMPILED_CONTRACT_PATH}")
        print("Please run `node compile.js` first.")
        sys.exit(1)

    with open(COMPILED_CONTRACT_PATH, "r") as f:
        artifact = json.load(f)

    abi = artifact.get("abi")
    bytecode = artifact.get("bytecode")

    if not abi or not bytecode:
        print("Error: Invalid contract artifact. Missing abi or bytecode.")
        sys.exit(1)

    if not PRIVATE_KEY:
        print("\n[ERROR] PRIVATE_KEY is not set in environment or .env file.")
        print("Please copy .env.example to .env and configure your PRIVATE_KEY and SEPOLIA_RPC_URL.")
        print("\nNeed Sepolia ETH? You can obtain testnet ETH from:")
        print("  - https://cloud.google.com/application/web3/faucet/ethereum/sepolia")
        print("  - https://sepoliafaucet.com")
        print("  - https://www.infura.io/faucet/sepolia")
        sys.exit(1)

    # Clean key format
    pk = PRIVATE_KEY if not PRIVATE_KEY.startswith("0x") else PRIVATE_KEY[2:]
    try:
        account = Account.from_key("0x" + pk)
    except Exception as e:
        print(f"[ERROR] Failed to load account from PRIVATE_KEY: {e}")
        sys.exit(1)

    w3 = get_web3_connection(DEFAULT_SEPOLIA_RPC)
    chain_id = w3.eth.chain_id
    deployer_address = account.address

    print(f"Network:           Sepolia (Chain ID: {chain_id})")
    print(f"Deployer Address:  {deployer_address}")

    balance_wei = w3.eth.get_balance(deployer_address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    print(f"Balance:           {balance_eth:.6f} SepoliaETH")

    if balance_wei == 0:
        print("\n[ERROR] Deployer wallet has 0 SepoliaETH balance. Gas is required to deploy.")
        print("Please fund the address with SepoliaETH from a faucet.")
        sys.exit(1)

    print("\nPreparing deployment transaction...")
    ContractFactory = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(deployer_address, "pending")
    gas_price = w3.eth.gas_price

    # Estimate gas or use default safe limit
    try:
        estimated_gas = ContractFactory.constructor().estimate_gas({"from": deployer_address})
        gas_limit = int(estimated_gas * 1.25)
    except Exception as e:
        print(f"Gas estimation warning: {e}. Falling back to 1,500,000 gas limit.")
        gas_limit = 1500000

    print(f"Estimated Gas:     {gas_limit}")
    print(f"Gas Price:         {w3.from_wei(gas_price, 'gwei'):.2f} Gwei")
    print(f"Nonce:             {nonce}")

    tx_params = {
        "from": deployer_address,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": int(gas_price * 1.15),  # slight boost for quick mining
        "chainId": chain_id,
    }

    construct_tx = ContractFactory.constructor().build_transaction(tx_params)

    print("\nSigning transaction with private key...")
    signed_tx = w3.eth.account.sign_transaction(construct_tx, private_key="0x" + pk)

    print("Broadcasting transaction to Sepolia...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    print(f"Tx Hash:           {tx_hash_hex}")
    print(f"Explorer URL:      https://sepolia.etherscan.io/tx/{tx_hash_hex}")

    print("\nWaiting for block confirmation (this usually takes 10-30 seconds)...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

    if receipt.status != 1:
        print(f"[ERROR] Deployment transaction failed on-chain! Status: {receipt.status}")
        sys.exit(1)

    contract_address = receipt.contractAddress
    print("\n" + "=" * 60)
    print(" CONTRACT DEPLOYED SUCCESSFULLY!")
    print("=" * 60)
    print(f"Contract Address:  {contract_address}")
    print(f"Block Number:      {receipt.blockNumber}")
    print(f"Gas Used:          {receipt.gasUsed}")
    print(f"Etherscan:         https://sepolia.etherscan.io/address/{contract_address}")
    print("=" * 60)

    # Save to contract_config.json
    config_data = {
        "network": "Sepolia",
        "chainId": chain_id,
        "contractAddress": contract_address,
        "deployerAddress": deployer_address,
        "deploymentTx": tx_hash_hex,
        "blockNumber": receipt.blockNumber,
        "abi": abi,
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f, indent=2)

    print(f"\nConfiguration successfully saved to {CONFIG_PATH}")
    return contract_address

if __name__ == "__main__":
    deploy()
