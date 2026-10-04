const fs = require('fs');
const path = require('path');
const solc = require('solc');

const contractPath = path.resolve(__dirname, 'contracts', 'TradingSignalStore.sol');
const source = fs.readFileSync(contractPath, 'utf8');

const input = {
  language: 'Solidity',
  sources: {
    'TradingSignalStore.sol': {
      content: source,
    },
  },
  settings: {
    optimizer: {
      enabled: true,
      runs: 200,
    },
    outputSelection: {
      '*': {
        '*': ['abi', 'evm.bytecode.object'],
      },
    },
  },
};

console.log('Compiling TradingSignalStore.sol...');
const output = JSON.parse(solc.compile(JSON.stringify(input)));

let hasErrors = false;
if (output.errors) {
  for (const error of output.errors) {
    if (error.severity === 'error') {
      hasErrors = true;
      console.error(error.formattedMessage);
    } else {
      console.warn(error.formattedMessage);
    }
  }
}

if (hasErrors) {
  console.error('Compilation failed.');
  process.exit(1);
}

const contract = output.contracts['TradingSignalStore.sol']['TradingSignalStore'];
const compiledDir = path.resolve(__dirname, 'compiled');
if (!fs.existsSync(compiledDir)) {
  fs.mkdirSync(compiledDir, { recursive: true });
}

const artifact = {
  contractName: 'TradingSignalStore',
  abi: contract.abi,
  bytecode: '0x' + contract.evm.bytecode.object,
};

const artifactPath = path.resolve(compiledDir, 'TradingSignalStore.json');
fs.writeFileSync(artifactPath, JSON.stringify(artifact, null, 2));

console.log(`Contract compiled successfully! Artifact saved to ${artifactPath}`);
