#!/usr/bin/env python3
"""
AI Trading Signal Agent
1. Fetches current ETH price from CoinGecko API
2. Sends price and market data to LLM API (Gemini or OpenAI) asking "BUY, SELL, or HOLD"
3. Writes the LLM's response to the deployed TradingSignalStore contract on Sepolia
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

# Load environment
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "contract_config.json"
COMPILED_CONTRACT_PATH = BASE_DIR / "compiled" / "TradingSignalStore.json"

DEFAULT_SEPOLIA_RPC = os.getenv("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

def get_eth_price() -> Dict[str, Any]:
    """
    Fetch current ETH/USD price and 24h market metrics from CoinGecko API.
    Includes automatic fallback to Coinbase/Binance if rate-limited or blocked.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    coingecko_api_key = os.getenv("COINGECKO_API_KEY", "").strip()
    if coingecko_api_key:
        headers["x-cg-demo-api-key"] = coingecko_api_key

    # 1. Primary: CoinGecko API
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json().get("ethereum", {})
            price = float(data.get("usd", 0.0))
            change_24h = float(data.get("usd_24h_change", 0.0))
            volume_24h = float(data.get("usd_24h_vol", 0.0))
            return {
                "asset": "ETH/USD",
                "price": price,
                "change_24h": change_24h,
                "volume_24h": volume_24h,
                "source": "CoinGecko",
                "timestamp": int(time.time()),
            }
        else:
            print(f"[!] CoinGecko returned HTTP {resp.status_code}. Attempting fallback...")
    except Exception as e:
        print(f"[!] CoinGecko fetch failed: {e}. Trying fallback...")

    # 2. Fallback: Binance API (returns 24h price + volume + change)
    try:
        bn_resp = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT", timeout=8)
        if bn_resp.status_code == 200:
            bn_data = bn_resp.json()
            price = float(bn_data.get("lastPrice", 0.0))
            change_24h = float(bn_data.get("priceChangePercent", 0.0))
            vol = float(bn_data.get("quoteVolume", 0.0))
            return {
                "asset": "ETH/USD",
                "price": price,
                "change_24h": change_24h,
                "volume_24h": vol,
                "source": "Binance (Market Feed)",
                "timestamp": int(time.time()),
            }
    except Exception as e:
        print(f"[!] Binance fallback failed: {e}")

    # 3. Fallback: Coinbase API
    try:
        cb_resp = requests.get("https://api.coinbase.com/v2/prices/ETH-USD/spot", timeout=8)
        if cb_resp.status_code == 200:
            cb_data = cb_resp.json().get("data", {})
            price = float(cb_data.get("amount", 0.0))
            return {
                "asset": "ETH/USD",
                "price": price,
                "change_24h": 0.0,
                "volume_24h": 0.0,
                "source": "Coinbase (Market Feed)",
                "timestamp": int(time.time()),
            }
    except Exception as e:
        print(f"[!] Coinbase fallback failed: {e}")

    raise RuntimeError("Failed to fetch current ETH price from CoinGecko and fallback feeds.")

def get_llm_signal(market_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send market data to LLM API asking "BUY, SELL, or HOLD".
    Supports Google Gemini (preferred), OpenAI, or technical heuristic fallback.
    """
    price = market_data["price"]
    change_24h = market_data.get("change_24h", 0.0)
    source = market_data.get("source", "CoinGecko")

    prompt = f"""You are an autonomous algorithmic cryptocurrency trading signal engine.
Analyze current market data for Ethereum:
- Asset: ETH/USD
- Current Price: ${price:.2f} USD
- 24h Price Change: {change_24h:+.2f}%
- Data Source: {source}

Generate a clear, high-conviction trading decision.
Respond ONLY with a valid JSON object strictly matching this schema:
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <integer percentage between 1 and 100>,
  "reasoning": "<1-2 sentence crisp rationale based on current price dynamics>"
}}
Do NOT wrap the output in markdown fences or include any conversational text outside the JSON.
"""

    # 1. Try Google Gemini API
    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw_text = response.text.strip()
            # Clean possible markdown fences
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            parsed = json.loads(raw_text.strip())
            decision = str(parsed.get("decision", "HOLD")).upper()
            if decision not in ("BUY", "SELL", "HOLD"):
                decision = "HOLD"
            return {
                "decision": decision,
                "confidence": int(parsed.get("confidence", 75)),
                "reasoning": str(parsed.get("reasoning", "")),
                "model": "Gemini-2.5-Flash",
            }
        except Exception as e:
            print(f"[!] Gemini LLM invocation failed: {e}. Checking alternatives...")

    # 2. Try OpenAI API
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a crypto quantitative analyst. Always respond in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw_text = completion.choices[0].message.content.strip()
            parsed = json.loads(raw_text)
            decision = str(parsed.get("decision", "HOLD")).upper()
            if decision not in ("BUY", "SELL", "HOLD"):
                decision = "HOLD"
            return {
                "decision": decision,
                "confidence": int(parsed.get("confidence", 80)),
                "reasoning": str(parsed.get("reasoning", "")),
                "model": "OpenAI gpt-4o-mini",
            }
        except Exception as e:
            print(f"[!] OpenAI LLM invocation failed: {e}. Falling back to algorithmic engine...")

    # 3. Fallback Quantitative Heuristic (Allows testing when API keys are not yet configured)
    print("[i] Notice: No LLM API key provided (or API unavailable). Generating algorithmic signal.")
    if change_24h >= 2.0:
        decision = "BUY"
        reasoning = f"Strong upward bullish momentum of {change_24h:+.2f}% in 24h, breaking above short-term resistance at ${price:.2f}."
        confidence = 82
    elif change_24h <= -2.0:
        decision = "SELL"
        reasoning = f"Bearish downward pressure of {change_24h:+.2f}% indicates distribution near ${price:.2f}. Recommend de-risking."
        confidence = 79
    else:
        decision = "HOLD"
        reasoning = f"Consolidating within narrow range ({change_24h:+.2f}%) around ${price:.2f}. Awaiting breakout confirmation."
        confidence = 70

    return {
        "decision": decision,
        "confidence": confidence,
        "reasoning": f"[Heuristic Engine] {reasoning}",
        "model": "Algorithmic-Momentum-Model (Configure GEMINI_API_KEY/OPENAI_API_KEY for LLM)",
    }

def record_signal_onchain(market_data: Dict[str, Any], signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Write the LLM decision and market price to the deployed contract on Sepolia testnet.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Configuration file {CONFIG_PATH} not found. Please deploy the contract first using `python deploy.py`."
        )

    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

    contract_address = config.get("contractAddress")
    abi = config.get("abi")

    if not contract_address or not abi:
        raise ValueError("contract_config.json is missing contractAddress or abi.")

    if not PRIVATE_KEY:
        raise ValueError(
            "PRIVATE_KEY is missing from environment. Please set PRIVATE_KEY in .env to sign transactions."
        )

    pk = PRIVATE_KEY if not PRIVATE_KEY.startswith("0x") else PRIVATE_KEY[2:]
    account = Account.from_key("0x" + pk)
    agent_address = account.address

    w3 = Web3(Web3.HTTPProvider(DEFAULT_SEPOLIA_RPC))
    if not w3.is_connected():
        fallback_rpcs = ["https://rpc.sepolia.org", "https://sepolia.drpc.org"]
        connected = False
        for rpc in fallback_rpcs:
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                connected = True
                break
        if not connected:
            raise ConnectionError("Unable to connect to Sepolia RPC.")

    chain_id = w3.eth.chain_id
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

    # Format values for smart contract:
    # asset: "ETH/USD"
    # price: scaled by 100 (cents), e.g. $3450.50 -> 345050
    asset_str = market_data.get("asset", "ETH/USD")
    price_cents = int(round(market_data["price"] * 100))
    decision_str = signal_data["decision"]
    reasoning_str = f"[{signal_data.get('confidence', 80)}% Conf] {signal_data['reasoning']}"
    # Truncate reasoning if too long to save gas
    if len(reasoning_str) > 280:
        reasoning_str = reasoning_str[:277] + "..."

    nonce = w3.eth.get_transaction_count(agent_address, "pending")
    gas_price = w3.eth.gas_price

    tx_func = contract.functions.recordSignal(
        asset_str,
        price_cents,
        decision_str,
        reasoning_str
    )

    try:
        est_gas = tx_func.estimate_gas({"from": agent_address})
        gas_limit = int(est_gas * 1.3)
    except Exception:
        gas_limit = 250000

    tx_dict = tx_func.build_transaction({
        "from": agent_address,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": int(gas_price * 1.2),
        "chainId": chain_id,
    })

    signed = w3.eth.account.sign_transaction(tx_dict, private_key="0x" + pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()

    print(f"Transaction broadcasted to Sepolia: {tx_hash_hex}")
    print("Waiting for on-chain confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    if receipt.status != 1:
        raise RuntimeError(f"On-chain transaction reverted! Status: {receipt.status}")

    return {
        "success": True,
        "txHash": tx_hash_hex,
        "blockNumber": receipt.blockNumber,
        "gasUsed": receipt.gasUsed,
        "contractAddress": contract_address,
        "explorerUrl": f"https://sepolia.etherscan.io/tx/{tx_hash_hex}",
        "reporter": agent_address,
    }

def run_trading_agent() -> Dict[str, Any]:
    """
    Execute the full end-to-end agent workflow:
    1. Fetch ETH price from CoinGecko
    2. Request LLM signal
    3. Write signal to Sepolia smart contract
    """
    print("\n" + "=" * 60)
    print(" [AI AGENT] INITIATING TRADING SIGNAL PIPELINE")
    print("=" * 60)

    # Step 1: Fetch Price
    print("Step 1: Fetching ETH price from CoinGecko...")
    market_data = get_eth_price()
    print(f" -> Price: ${market_data['price']:,.2f} USD")
    print(f" -> 24h Change: {market_data['change_24h']:+.2f}%")
    print(f" -> Source: {market_data['source']}")

    # Step 2: Query LLM
    print("\nStep 2: Sending market context to LLM for trading decision...")
    signal_data = get_llm_signal(market_data)
    print(f" -> Decision:   {signal_data['decision']}")
    print(f" -> Confidence: {signal_data['confidence']}%")
    print(f" -> Model:      {signal_data['model']}")
    print(f" -> Reasoning:  {signal_data['reasoning']}")

    # Step 3: Record On-Chain
    print("\nStep 3: Writing decision to Sepolia testnet contract...")
    tx_result = record_signal_onchain(market_data, signal_data)
    print(f" -> On-chain Status: Confirmed in Block #{tx_result['blockNumber']}")
    print(f" -> Etherscan URL:   {tx_result['explorerUrl']}")
    print("=" * 60)

    return {
        "market": market_data,
        "signal": signal_data,
        "blockchain": tx_result,
        "timestamp": int(time.time()),
    }

if __name__ == "__main__":
    try:
        run_trading_agent()
    except Exception as e:
        print(f"\n[FATAL ERROR] Agent pipeline failed: {e}")
        sys.exit(1)
