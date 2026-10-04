// AI Trading Signal Agent Frontend JavaScript

const SEPOLIA_CHAIN_ID_HEX = '0xaa36a7'; // 11155111
const SEPOLIA_CHAIN_ID_DEC = 11155111;

let userAccount = null;
let currentChainId = null;
let contractConfig = null;

// DOM Elements
const connectWalletBtn = document.getElementById('connectWalletBtn');
const walletBtnText = document.getElementById('walletBtnText');
const networkBadge = document.getElementById('networkBadge');
const networkName = document.getElementById('networkName');
const alertBanner = document.getElementById('alertBanner');
const contractAddressDisplay = document.getElementById('contractAddressDisplay');
const copyAddressBtn = document.getElementById('copyAddressBtn');
const contractEtherscanLink = document.getElementById('contractEtherscanLink');
const llmEnginePill = document.getElementById('llmEnginePill');
const totalSignalsPill = document.getElementById('totalSignalsPill');

const ethPriceDisplay = document.getElementById('ethPriceDisplay');
const ethChangePill = document.getElementById('ethChangePill');
const ethVolumeDisplay = document.getElementById('ethVolumeDisplay');
const priceSourceBadge = document.getElementById('priceSourceBadge');
const lastUpdatedDisplay = document.getElementById('lastUpdatedDisplay');

const triggerAgentBtn = document.getElementById('triggerAgentBtn');
const triggerBtnText = document.getElementById('triggerBtnText');
const triggerStatusBox = document.getElementById('triggerStatusBox');
const statusMessage = document.getElementById('statusMessage');

const step1 = document.getElementById('step1');
const step2 = document.getElementById('step2');
const step3 = document.getElementById('step3');

const latestSignalCard = document.querySelector('.latest-signal-card');
const latestSignalContent = document.getElementById('latestSignalContent');
const refreshSignalsBtn = document.getElementById('refreshSignalsBtn');
const signalsTableBody = document.getElementById('signalsTableBody');
const historyCountText = document.getElementById('historyCountText');

// Provider resolution (supports window.ethereum, multiple injected wallets, and EIP-6963)
let activeProvider = null;

function getMetaMaskProvider() {
  if (activeProvider) return activeProvider;

  if (window.ethereum) {
    if (window.ethereum.providers && window.ethereum.providers.length) {
      const mm = window.ethereum.providers.find(p => p.isMetaMask);
      if (mm) {
        activeProvider = mm;
        return mm;
      }
    }
    activeProvider = window.ethereum;
    return window.ethereum;
  }
  return null;
}

// EIP-6963 discovery for modern extensions
window.addEventListener('eip6963:announceProvider', (event) => {
  if (event.detail && event.detail.info && event.detail.info.name.toLowerCase().includes('metamask')) {
    activeProvider = event.detail.provider;
    initWalletState();
  }
});

window.addEventListener('ethereum#initialized', () => {
  initWalletState();
}, { once: true });

async function initWalletState() {
  const provider = getMetaMaskProvider();
  if (!provider) return;

  try {
    const accounts = await provider.request({ method: 'eth_accounts' });
    if (accounts && accounts.length > 0) {
      handleAccountsChanged(accounts);
    }
    const chainId = await provider.request({ method: 'eth_chainId' });
    handleChainChanged(chainId);

    provider.on('accountsChanged', handleAccountsChanged);
    provider.on('chainChanged', handleChainChanged);
  } catch (err) {
    console.warn('Wallet initialization check:', err);
  }
}

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
  await loadConfig();
  await fetchLivePrice();
  await fetchOnChainSignals();

  // Price refresh interval (every 30 seconds)
  setInterval(fetchLivePrice, 30000);

  // Initialize wallet check
  await initWalletState();

  // Event Listeners
  connectWalletBtn.addEventListener('click', connectMetaMask);
  triggerAgentBtn.addEventListener('click', handleTriggerAgent);
  refreshSignalsBtn.addEventListener('click', fetchOnChainSignals);
  copyAddressBtn.addEventListener('click', copyContractAddress);
});

// Load backend contract & environment configuration
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    if (data.success) {
      contractConfig = data;
      llmEnginePill.textContent = `LLM: ${data.envStatus.llmMode}`;

      if (data.contractConfigured && data.contractAddress) {
        const addr = data.contractAddress;
        contractAddressDisplay.textContent = `${addr.substring(0, 6)}...${addr.substring(addr.length - 4)}`;
        contractAddressDisplay.title = addr;
        contractEtherscanLink.href = `https://sepolia.etherscan.io/address/${addr}`;
      } else {
        contractAddressDisplay.textContent = 'Contract Not Deployed';
        showAlert(
          'Smart contract is not yet deployed to Sepolia. Run `python deploy.py` to deploy.',
          'warning'
        );
      }
    }
  } catch (err) {
    console.error('Failed to load contract config:', err);
  }
}

// Fetch live ETH price from backend (CoinGecko)
async function fetchLivePrice() {
  try {
    const res = await fetch('/api/price');
    const json = await res.json();
    if (json.success && json.data) {
      const d = json.data;
      ethPriceDisplay.textContent = `$${d.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      
      const change = d.change_24h || 0;
      ethChangePill.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
      ethChangePill.className = `price-change-pill ${change >= 0 ? 'positive' : 'negative'}`;

      if (d.volume_24h > 0) {
        ethVolumeDisplay.textContent = `$${(d.volume_24h / 1e9).toFixed(2)}B`;
      } else {
        ethVolumeDisplay.textContent = 'Active';
      }

      priceSourceBadge.textContent = d.source || 'CoinGecko API';
      const now = new Date();
      lastUpdatedDisplay.textContent = now.toLocaleTimeString();
    }
  } catch (err) {
    console.warn('Failed to fetch live price:', err);
  }
}

// Fetch latest and recent signals from Sepolia
async function fetchOnChainSignals() {
  refreshSignalsBtn.disabled = true;
  refreshSignalsBtn.innerHTML = `Refreshing...`;

  try {
    // 1. Fetch latest signal
    const latestRes = await fetch('/api/latest-signal');
    const latestData = await latestRes.json();

    if (latestData.success && latestData.hasSignals && latestData.signal) {
      renderLatestSignal(latestData.signal, latestData.contractAddress);
      totalSignalsPill.textContent = `Signals: ${latestData.totalCount}`;
    } else if (latestData.success && !latestData.hasSignals) {
      latestSignalContent.innerHTML = `
        <div class="empty-state">
          <p>No signals recorded on Sepolia yet.</p>
          <p style="margin-top: 8px; font-size: 0.85rem; color: #94a3b8;">Click <strong>Trigger AI Agent</strong> to query LLM and record the first immutable signal!</p>
        </div>
      `;
      totalSignalsPill.textContent = `Signals: 0`;
    }

    // 2. Fetch history
    const historyRes = await fetch('/api/signals?limit=10');
    const historyData = await historyRes.json();
    if (historyData.success && historyData.signals) {
      renderSignalsHistory(historyData.signals);
    }
  } catch (err) {
    console.error('Failed to fetch on-chain signals:', err);
  } finally {
    refreshSignalsBtn.disabled = false;
    refreshSignalsBtn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="23 4 23 10 17 10"></polyline>
        <polyline points="1 20 1 14 7 14"></polyline>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
      </svg>
      Refresh On-Chain
    `;
  }
}

function renderLatestSignal(signal, contractAddress) {
  const decision = signal.decision.toUpperCase();
  const decisionClass = decision === 'BUY' ? 'buy' : (decision === 'SELL' ? 'sell' : 'hold');

  latestSignalCard.className = `card latest-signal-card ${decisionClass}`;

  const shortReporter = `${signal.reporter.substring(0, 6)}...${signal.reporter.substring(signal.reporter.length - 4)}`;

  latestSignalContent.innerHTML = `
    <div class="signal-hero">
      <div class="signal-badge-large ${decisionClass}">
        ${decision}
      </div>
      <div class="signal-meta">
        <div class="signal-meta-top">
          <span class="signal-asset">${signal.asset}</span>
          <span class="signal-price">$${signal.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        </div>
        <div class="signal-reasoning">
          <strong>AI Analysis:</strong> ${escapeHtml(signal.reasoning)}
        </div>
      </div>
      <div class="signal-footer-info">
        <div>Signal ID: #${signal.id}</div>
        <div>Recorded: ${signal.timestampFormatted}</div>
        <div>
          Reporter:
          <a href="https://sepolia.etherscan.io/address/${signal.reporter}" target="_blank" class="btn-link">
            ${shortReporter}
          </a>
        </div>
      </div>
    </div>
  `;
}

function renderSignalsHistory(signals) {
  if (!signals || signals.length === 0) {
    signalsTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center text-muted" style="padding: 24px;">No signals on-chain yet.</td>
      </tr>
    `;
    return;
  }

  historyCountText.textContent = `Showing last ${signals.length} on-chain records`;

  signalsTableBody.innerHTML = signals.map(s => {
    const dec = s.decision.toUpperCase();
    const decClass = dec === 'BUY' ? 'buy' : (dec === 'SELL' ? 'sell' : 'hold');
    const shortRep = `${s.reporter.substring(0, 6)}...${s.reporter.substring(s.reporter.length - 4)}`;

    return `
      <tr>
        <td><strong>#${s.id}</strong></td>
        <td>${s.asset}</td>
        <td><span class="action-pill ${decClass}">${dec}</span></td>
        <td style="font-family: var(--font-mono); font-weight: 600;">$${s.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
        <td style="max-width: 380px;">${escapeHtml(s.reasoning)}</td>
        <td style="font-size: 0.8rem; font-family: var(--font-mono);">${s.timestampFormatted}</td>
        <td>
          <a href="https://sepolia.etherscan.io/address/${s.reporter}" target="_blank" class="btn-link" style="font-family: var(--font-mono); font-size: 0.8rem;">
            ${shortRep}
          </a>
        </td>
      </tr>
    `;
  }).join('');
}

// Trigger Agent Pipeline
async function handleTriggerAgent() {
  triggerAgentBtn.disabled = true;
  triggerBtnText.textContent = 'Agent Executing...';
  triggerStatusBox.classList.remove('hidden');

  // Step 1: CoinGecko
  setStepState(step1, 'active');
  setStepState(step2, '');
  setStepState(step3, '');
  statusMessage.textContent = 'Step 1/3: Fetching live ETH price from CoinGecko...';

  try {
    const res = await fetch('/api/trigger-agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    const data = await res.json();

    if (!data.success) {
      throw new Error(data.error || 'Failed to trigger agent');
    }

    // Step 2 Completed
    setStepState(step1, 'completed');
    setStepState(step2, 'completed');
    statusMessage.textContent = `Step 2/3: LLM generated signal: ${data.result.signal.decision} (${data.result.signal.confidence}% confidence)`;

    // Step 3 Completed
    setStepState(step3, 'completed');
    const tx = data.result.blockchain;
    statusMessage.innerHTML = `
      ✓ Signal confirmed on Sepolia! Block #${tx.blockNumber}.
      <a href="${tx.explorerUrl}" target="_blank" style="color: #a5b4fc; text-decoration: underline; margin-left: 6px;">View on Etherscan &rarr;</a>
    `;

    // Refresh signals immediately
    await fetchOnChainSignals();
    await fetchLivePrice();

    showAlert(`Success: Recorded ${data.result.signal.decision} signal to Sepolia contract! Tx: ${tx.txHash.substring(0, 10)}...`, 'success');

  } catch (err) {
    console.error('Trigger agent error:', err);
    statusMessage.textContent = `Error: ${err.message}`;
    setStepState(step1, '');
    setStepState(step2, '');
    setStepState(step3, '');
    showAlert(err.message, 'danger');
  } finally {
    triggerAgentBtn.disabled = false;
    triggerBtnText.textContent = 'Trigger AI Agent';
  }
}

function setStepState(stepEl, state) {
  stepEl.classList.remove('active', 'completed');
  if (state) stepEl.classList.add(state);
}

// MetaMask Connection Handling
async function connectMetaMask() {
  const provider = getMetaMaskProvider();
  if (!provider) {
    showAlert('MetaMask is not detected in this tab. Please refresh the page (Cmd + R) or make sure MetaMask extension is enabled in chrome://extensions.', 'warning');
    return;
  }

  const prevText = walletBtnText.textContent;
  walletBtnText.textContent = 'Connecting...';

  try {
    console.log('[MetaMask] Requesting accounts...');
    
    // First check if already unlocked and authorized
    let accounts = await provider.request({ method: 'eth_accounts' });
    
    if (!accounts || accounts.length === 0) {
      // Prompt user to connect
      accounts = await provider.request({ method: 'eth_requestAccounts' });
    }

    if (accounts && accounts.length > 0) {
      handleAccountsChanged(accounts);
      const chainId = await provider.request({ method: 'eth_chainId' });
      handleChainChanged(chainId);
      hideAlert();
      console.log('[MetaMask] Connected account:', accounts[0], 'Chain ID:', chainId);
    }
  } catch (err) {
    console.error('[MetaMask] Connection error:', err);
    walletBtnText.textContent = prevText;

    if (err.code === 4001) {
      showAlert('MetaMask connection request was rejected. Click "Connect MetaMask" to try again.', 'warning');
    } else if (err.code === -32002) {
      showAlert('A connection prompt is already pending in MetaMask! Please look at your MetaMask panel/extension icon on the right and click "Connect" or approve the request.', 'warning');
    } else if (err.message && err.message.toLowerCase().includes('locked')) {
      showAlert('MetaMask is locked. Please unlock MetaMask with your password first, then click Connect.', 'warning');
    } else {
      showAlert(`MetaMask error: ${err.message || 'Unknown error. Check browser console.'}`, 'danger');
    }
  }
}

function handleAccountsChanged(accounts) {
  if (!accounts || accounts.length === 0) {
    userAccount = null;
    walletBtnText.textContent = 'Connect MetaMask';
    connectWalletBtn.classList.remove('connected');
  } else {
    userAccount = accounts[0];
    const shortAcc = `${userAccount.substring(0, 6)}...${userAccount.substring(userAccount.length - 4)}`;
    walletBtnText.textContent = shortAcc;
    connectWalletBtn.classList.add('connected');
    hideAlert();
  }
}

async function handleChainChanged(chainIdHex) {
  currentChainId = parseInt(chainIdHex, 16);
  if (currentChainId === SEPOLIA_CHAIN_ID_DEC) {
    networkBadge.className = 'network-badge connected';
    networkName.textContent = 'Sepolia (11155111)';
    hideAlert();
  } else {
    networkBadge.className = 'network-badge';
    networkName.textContent = `Chain ID: ${currentChainId}`;
    showAlert(
      `MetaMask is connected to Chain ID ${currentChainId}. Please switch to Sepolia Testnet (11155111). <button id="switchNetworkBtn" style="margin-left: 10px; padding: 4px 10px; border-radius: 4px; background: #6366f1; color: white; border: none; cursor: pointer;">Switch to Sepolia</button>`,
      'warning',
      true
    );

    const switchBtn = document.getElementById('switchNetworkBtn');
    if (switchBtn) {
      switchBtn.onclick = switchToSepolia;
    }
  }
}

async function switchToSepolia() {
  const provider = getMetaMaskProvider();
  if (!provider) return;

  try {
    await provider.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: SEPOLIA_CHAIN_ID_HEX }],
    });
  } catch (switchError) {
    // If chain has not been added to MetaMask
    if (switchError.code === 4902) {
      try {
        await provider.request({
          method: 'wallet_addEthereumChain',
          params: [
            {
              chainId: SEPOLIA_CHAIN_ID_HEX,
              chainName: 'Sepolia Testnet',
              nativeCurrency: { name: 'SepoliaETH', symbol: 'ETH', decimals: 18 },
              rpcUrls: ['https://ethereum-sepolia-rpc.publicnode.com', 'https://rpc.sepolia.org'],
              blockExplorerUrls: ['https://sepolia.etherscan.io'],
            },
          ],
        });
      } catch (addError) {
        showAlert(`Failed to add Sepolia network: ${addError.message}`, 'danger');
      }
    } else {
      showAlert(`Failed to switch network: ${switchError.message}`, 'danger');
    }
  }
}

function copyContractAddress() {
  if (!contractConfig || !contractConfig.contractAddress) return;
  navigator.clipboard.writeText(contractConfig.contractAddress);
  copyAddressBtn.title = 'Copied!';
  setTimeout(() => {
    copyAddressBtn.title = 'Copy Address';
  }, 2000);
}

function showAlert(msg, type = 'warning', isHtml = false) {
  alertBanner.className = `alert-banner ${type}`;
  if (isHtml) {
    alertBanner.innerHTML = msg;
  } else {
    alertBanner.textContent = msg;
  }
  alertBanner.classList.remove('hidden');
}

function hideAlert() {
  alertBanner.classList.add('hidden');
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
