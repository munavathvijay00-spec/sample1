#!/usr/bin/env python3
"""
Flask Web Application for AI Trading Signal Agent
- Connects MetaMask Wallet
- Displays latest on-chain trading signals from Sepolia
- Provides UI and API to trigger the AI trading agent
"""

import json
import os
import sys
import time
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
from web3 import Web3

# Import agent pipeline
import agent

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "contract_config.json"
DEFAULT_SEPOLIA_RPC = os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")

app = Flask(__name__, template_folder="templates", static_folder="static")

def get_contract_instance():
    """Load deployed contract configuration and initialize Web3 contract."""
    if not CONFIG_PATH.exists():
        return None, None, None

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    contract_address = config.get("contractAddress")
    abi = config.get("abi")

    if not contract_address or not abi:
        return None, None, None

    w3 = Web3(Web3.HTTPProvider(DEFAULT_SEPOLIA_RPC))
    if not w3.is_connected():
        fallback_rpcs = ["https://rpc.sepolia.org", "https://sepolia.drpc.org"]
        for rpc in fallback_rpcs:
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                break

    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
    return w3, contract, config

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    """Return contract configuration and environment status for the frontend."""
    _, _, config = get_contract_instance()
    has_pk = bool(os.getenv("PRIVATE_KEY", "").strip())
    has_gemini = bool(os.getenv("GEMINI_API_KEY", "").strip())
    has_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())

    return jsonify({
        "success": True,
        "contractConfigured": config is not None,
        "contractAddress": config.get("contractAddress") if config else None,
        "chainId": config.get("chainId", 11155111) if config else 11155111,
        "network": "Sepolia",
        "abi": config.get("abi") if config else None,
        "envStatus": {
            "hasPrivateKey": has_pk,
            "hasGeminiKey": has_gemini,
            "hasOpenAIKey": has_openai,
            "llmMode": "Gemini-2.5-Flash" if has_gemini else ("OpenAI gpt-4o-mini" if has_openai else "Heuristic Simulation"),
        }
    })

@app.route("/api/price", methods=["GET"])
def live_price():
    """Fetch live ETH price from CoinGecko."""
    try:
        data = agent.get_eth_price()
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# In-memory storage for demo/simulated mode
SIMULATED_SIGNALS = []

@app.route("/api/latest-signal", methods=["GET"])
def latest_signal():
    """Fetch the latest trading signal directly from the Sepolia contract or simulated store."""
    try:
        w3, contract, config = get_contract_instance()
        if not config:
            return jsonify({
                "success": False,
                "error": "Contract not deployed yet. Please run python deploy.py first."
            }), 404

        # If simulated mode is active
        if config.get("isSimulated", False):
            if not SIMULATED_SIGNALS:
                return jsonify({
                    "success": True,
                    "hasSignals": False,
                    "message": "Demo mode active. Click 'Trigger AI Agent' to generate and record the first signal!"
                })
            latest = SIMULATED_SIGNALS[-1]
            return jsonify({
                "success": True,
                "hasSignals": True,
                "signal": latest,
                "totalCount": len(SIMULATED_SIGNALS),
                "contractAddress": config["contractAddress"],
                "explorerUrl": f"https://sepolia.etherscan.io/address/{config['contractAddress']}",
                "isSimulated": True,
            })

        count = contract.functions.getSignalCount().call()
        if count == 0:
            return jsonify({
                "success": True,
                "hasSignals": False,
                "message": "No signals recorded on-chain yet. Click 'Trigger AI Agent' to generate the first signal!"
            })

        latest = contract.functions.getLatestSignal().call()
        # Returns: (id, timestamp, asset, price, decision, reasoning, reporter)
        signal_id, timestamp, asset, price_cents, decision, reasoning, reporter = latest

        return jsonify({
            "success": True,
            "hasSignals": True,
            "signal": {
                "id": signal_id,
                "timestamp": timestamp,
                "timestampFormatted": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(timestamp)),
                "asset": asset,
                "price": price_cents / 100.0,
                "decision": decision,
                "reasoning": reasoning,
                "reporter": reporter,
            },
            "totalCount": count,
            "contractAddress": config["contractAddress"],
            "explorerUrl": f"https://sepolia.etherscan.io/address/{config['contractAddress']}",
            "isSimulated": False,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/signals", methods=["GET"])
def get_all_signals():
    """Fetch up to N recent signals from the Sepolia contract or simulated store."""
    try:
        w3, contract, config = get_contract_instance()
        if not config:
            return jsonify({"success": False, "error": "Contract not deployed yet."}), 404

        if config.get("isSimulated", False):
            limit = int(request.args.get("limit", 10))
            return jsonify({
                "success": True,
                "totalCount": len(SIMULATED_SIGNALS),
                "signals": list(reversed(SIMULATED_SIGNALS[-limit:])),
                "contractAddress": config["contractAddress"],
                "isSimulated": True,
            })

        limit = int(request.args.get("limit", 10))
        signals_raw = contract.functions.getRecentSignals(limit).call()
        count = contract.functions.getSignalCount().call()

        formatted = []
        for s in signals_raw:
            formatted.append({
                "id": s[0],
                "timestamp": s[1],
                "timestampFormatted": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(s[1])),
                "asset": s[2],
                "price": s[3] / 100.0,
                "decision": s[4],
                "reasoning": s[5],
                "reporter": s[6],
            })

        return jsonify({
            "success": True,
            "totalCount": count,
            "signals": formatted,
            "contractAddress": config["contractAddress"],
            "isSimulated": False,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/trigger-agent", methods=["POST"])
def trigger_agent():
    """
    Trigger the AI agent pipeline:
    1. Fetches current ETH price from CoinGecko
    2. Sends price to LLM API (Gemini/OpenAI) asking "buy or sell"
    3. Writes the LLM response to the deployed contract on Sepolia
    """
    try:
        # Check if contract is deployed
        if not CONFIG_PATH.exists():
            return jsonify({
                "success": False,
                "error": "Contract has not been deployed yet. Please run `python deploy.py` first."
            }), 400

        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)

        # In simulated mode without real gas:
        if cfg.get("isSimulated", False) and not os.getenv("PRIVATE_KEY", "").strip():
            market_data = agent.get_eth_price()
            signal_data = agent.get_llm_signal(market_data)
            now_ts = int(time.time())
            simulated_tx_hash = "0x" + f"{int(time.time())}" + "ab" * 26
            sim_signal = {
                "id": len(SIMULATED_SIGNALS),
                "timestamp": now_ts,
                "timestampFormatted": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(now_ts)),
                "asset": market_data["asset"],
                "price": market_data["price"],
                "decision": signal_data["decision"],
                "reasoning": f"[{signal_data.get('confidence', 80)}% Conf] {signal_data['reasoning']}",
                "reporter": cfg.get("deployerAddress", "0xDemoAgentWallet11155111"),
            }
            SIMULATED_SIGNALS.append(sim_signal)
            return jsonify({
                "success": True,
                "message": "AI trading signal generated and recorded (Demo Simulation Mode)!",
                "result": {
                    "market": market_data,
                    "signal": signal_data,
                    "blockchain": {
                        "success": True,
                        "txHash": simulated_tx_hash,
                        "blockNumber": 11809050 + len(SIMULATED_SIGNALS),
                        "gasUsed": 78420,
                        "contractAddress": cfg["contractAddress"],
                        "explorerUrl": f"https://sepolia.etherscan.io/address/{cfg['contractAddress']}",
                        "reporter": cfg.get("deployerAddress", "0xDemoAgentWallet11155111"),
                    }
                }
            })

        # Real Sepolia On-Chain flow
        if not os.getenv("PRIVATE_KEY", "").strip():
            return jsonify({
                "success": False,
                "error": "PRIVATE_KEY is not configured in .env. The agent needs a funded Sepolia private key to sign on-chain transactions."
            }), 400

        result = agent.run_trading_agent()
        return jsonify({
            "success": True,
            "message": "AI trading signal generated and successfully recorded on Sepolia testnet!",
            "result": result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    print("=" * 60)
    print(f" Starting AI Trading Signal Dashboard on:")
    print(f" -> http://127.0.0.1:{port}")
    print(f" -> http://localhost:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=True)
