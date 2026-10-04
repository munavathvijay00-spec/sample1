#!/usr/bin/env python3
"""
Simulated deployment generator for instant testing of the UI and data pipeline
without requiring immediate Sepolia testnet ETH faucet funding.
Generates contract_config.json with a valid contract address and initial signals.
"""

import json
import time
from pathlib import Path
from eth_account import Account

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "contract_config.json"
COMPILED_CONTRACT_PATH = BASE_DIR / "compiled" / "TradingSignalStore.json"

def deploy_simulated():
    print("=" * 60)
    print(" Initializing Demo / Simulated Sepolia Contract Config")
    print("=" * 60)

    if not COMPILED_CONTRACT_PATH.exists():
        print("Please run `node compile.js` first.")
        return

    with open(COMPILED_CONTRACT_PATH, "r") as f:
        artifact = json.load(f)

    # Generate a deterministic or random demo contract address
    demo_account = Account.create()
    demo_contract = Account.create()

    config_data = {
        "network": "Sepolia",
        "chainId": 11155111,
        "contractAddress": demo_contract.address,
        "deployerAddress": demo_account.address,
        "deploymentTx": "0x" + "a" * 64,
        "blockNumber": 11809046,
        "abi": artifact["abi"],
        "isSimulated": True,
        "createdAt": int(time.time()),
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f, indent=2)

    print(f"[✓] Demo contract configured at: {demo_contract.address}")
    print(f"[✓] Saved configuration to {CONFIG_PATH}")
    print("You can now run `python app.py` and test the UI immediately!")
    print("To deploy a real contract on Sepolia, add your PRIVATE_KEY to .env and run `python deploy.py`.")
    print("=" * 60)

if __name__ == "__main__":
    deploy_simulated()
