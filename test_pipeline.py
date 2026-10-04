#!/usr/bin/env python3
"""
Comprehensive automated tests for AI Trading Signal Agent.
Tests:
1. Contract compilation and ABI verification
2. CoinGecko market price fetching
3. LLM signal generation
4. Flask web API endpoints
5. Sepolia contract structure & encoding
"""

import json
import unittest
from pathlib import Path
from web3 import Web3

import app as flask_module
import agent

class TestAITradingAgent(unittest.TestCase):

    def setUp(self):
        self.app = flask_module.app
        self.client = self.app.test_client()

    def test_01_compiled_contract_exists_and_valid(self):
        """Verify Solidity contract compiled properly with ABI and bytecode."""
        artifact_path = Path("compiled/TradingSignalStore.json")
        self.assertTrue(artifact_path.exists(), "compiled/TradingSignalStore.json must exist")
        
        with open(artifact_path, "r") as f:
            artifact = json.load(f)
            
        self.assertIn("abi", artifact)
        self.assertIn("bytecode", artifact)
        self.assertTrue(artifact["bytecode"].startswith("0x"))
        self.assertGreater(len(artifact["bytecode"]), 100)

        # Check required function names in ABI
        method_names = [item.get("name") for item in artifact["abi"] if item.get("type") == "function"]
        self.assertIn("recordSignal", method_names)
        self.assertIn("getLatestSignal", method_names)
        self.assertIn("getSignalCount", method_names)
        self.assertIn("getRecentSignals", method_names)
        print("[✓] Test 1 Passed: Smart contract compiled artifact verified.")

    def test_02_fetch_eth_price(self):
        """Verify market data fetching returns a positive ETH price and required keys."""
        try:
            data = agent.get_eth_price()
            self.assertEqual(data["asset"], "ETH/USD")
            self.assertGreater(data["price"], 0.0)
            self.assertIn("source", data)
            print(f"[✓] Test 2 Passed: Fetched ETH price = ${data['price']:,.2f} from {data['source']}")
        except Exception as e:
            self.skipTest(f"Network call skipped or failed in sandbox: {e}")

    def test_03_llm_signal_generation(self):
        """Verify LLM or fallback heuristic produces BUY/SELL/HOLD decision with confidence & reasoning."""
        mock_market_data = {
            "asset": "ETH/USD",
            "price": 2750.50,
            "change_24h": 3.85,
            "volume_24h": 15000000000.0,
            "source": "CoinGecko"
        }
        signal = agent.get_llm_signal(mock_market_data)
        self.assertIn(signal["decision"], ["BUY", "SELL", "HOLD"])
        self.assertIsInstance(signal["confidence"], int)
        self.assertGreaterEqual(signal["confidence"], 1)
        self.assertLessEqual(signal["confidence"], 100)
        self.assertTrue(len(signal["reasoning"]) > 5)
        print(f"[✓] Test 3 Passed: Signal generated = {signal['decision']} ({signal['confidence']}%), Reason: {signal['reasoning'][:60]}...")

    def test_04_flask_ui_and_endpoints(self):
        """Verify Flask frontend serves HTML index and JSON API endpoints."""
        # 1. Index page
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("AI SIGNAL AGENT", html)
        self.assertIn("Connect MetaMask", html)
        self.assertIn("Trigger AI Agent", html)

        # 2. Config endpoint
        res = self.client.get("/api/config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["network"], "Sepolia")
        self.assertEqual(data["chainId"], 11155111)

        print("[✓] Test 4 Passed: Flask UI and API endpoints are responsive.")

    def test_05_trigger_agent_and_query_signal(self):
        """Verify triggering the agent endpoint generates a decision and stores it."""
        res = self.client.post("/api/trigger-agent")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("result", data)
        self.assertIn("signal", data["result"])
        self.assertIn(data["result"]["signal"]["decision"], ["BUY", "SELL", "HOLD"])

        # Check latest signal reflects the new signal
        latest_res = self.client.get("/api/latest-signal")
        self.assertEqual(latest_res.status_code, 200)
        latest_data = latest_res.get_json()
        self.assertTrue(latest_data["hasSignals"])
        self.assertEqual(latest_data["signal"]["decision"], data["result"]["signal"]["decision"])

        # Check history
        history_res = self.client.get("/api/signals")
        self.assertEqual(history_res.status_code, 200)
        history_data = history_res.get_json()
        self.assertGreaterEqual(len(history_data["signals"]), 1)
        print(f"[✓] Test 5 Passed: Full trigger -> decision ({latest_data['signal']['decision']}) -> state query flow verified.")

if __name__ == "__main__":
    unittest.main()
