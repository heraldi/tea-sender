import pandas as pd
import time
import random
from datetime import datetime
from web3 import Web3
from web3.middleware import geth_poa_middleware

# Configuration
RPC = "https://tea-sepolia.g.alchemy.com/public"
CHAIN_ID = 10218
GAS_LIMIT = 100000  # Higher gas limit for token transfers
MAX_TX = 1000

# Load addresses
df = pd.read_csv("address.csv")
if 'address' not in df.columns:
    raise Exception("Kolom 'address' tidak ditemukan di address.csv")

addresses = [Web3.to_checksum_address(addr.strip()) for addr in df['address'].dropna().unique()]

# Load private keys
with open("pk_wallet.txt", "r") as f:
    private_keys = [line.strip() for line in f if line.strip()]

if not private_keys:
    raise Exception("Tidak ada private key ditemukan di pk_wallet.txt")

print(f"🔑 Total wallet: {len(private_keys)} | 🎯 Total address tujuan: {len(addresses)}")

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(RPC))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# Get token details from user
def get_token_details():
    print("\n📝 Masukkan detail token ERC20:")
    while True:
        try:
            contract_address = input("Alamat kontrak token: ").strip()
            if not Web3.is_address(contract_address):
                print("Alamat kontrak tidak valid!")
                continue
                
            symbol = input("Simbol token (contoh: TEA): ").strip()
            if not symbol:
                print("Simbol token harus diisi!")
                continue
                
            decimals = input("Desimal token (default 18): ").strip()
            decimals = int(decimals) if decimals else 18
            
            return Web3.to_checksum_address(contract_address), symbol, decimals
        except ValueError:
            print("Masukkan angka yang valid untuk desimal")

TOKEN_CONTRACT, TOKEN_SYMBOL, TOKEN_DECIMALS = get_token_details()

# Get user input for token amount range
def get_amount_range():
    while True:
        try:
            print(f"\n🔢 Masukkan range jumlah {TOKEN_SYMBOL} yang akan dikirim:")
            min_amount = float(input(f"Jumlah minimal {TOKEN_SYMBOL} yang akan dikirim: "))
            max_amount = float(input(f"Jumlah maksimal {TOKEN_SYMBOL} yang akan dikirim: "))
            
            if min_amount <= 0 or max_amount <= 0:
                print("Jumlah token harus lebih besar dari 0")
                continue
                
            if min_amount > max_amount:
                print("Jumlah minimal tidak boleh lebih besar dari maksimal")
                continue
                
            return min_amount, max_amount
        except ValueError:
            print("Masukkan angka yang valid")

MIN_AMOUNT, MAX_AMOUNT = get_amount_range()
print(f"\n⚙️ Konfigurasi Token:")
print(f"Alamat Kontrak: {TOKEN_CONTRACT}")
print(f"Simbol: {TOKEN_SYMBOL}")
print(f"Desimal: {TOKEN_DECIMALS}")
print(f"Range Kirim: {MIN_AMOUNT} - {MAX_AMOUNT} {TOKEN_SYMBOL}")

# Load ABI for ERC20 token
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

# Create token contract instance
token_contract = w3.eth.contract(address=TOKEN_CONTRACT, abi=ERC20_ABI)

# Accounts setup
accounts = [w3.eth.account.from_key(pk) for pk in private_keys]
done_files = {acc.address: f"done_{acc.address}.txt" for acc in accounts}

# Track sent transactions
sent_map = {}
for acc in accounts:
    try:
        with open(done_files[acc.address], "r") as f:
            sent_map[acc.address] = set(line.strip().lower() for line in f)
    except FileNotFoundError:
        sent_map[acc.address] = set()

tx_counter = 0

def send_token_transaction(sender_account, to_address, amount_in_token):
    """Helper function to send token transaction"""
    nonce = w3.eth.get_transaction_count(sender_account.address)
    gas_price = w3.to_wei(random.randint(8, 15), 'gwei')
    
    # Convert amount according to token decimals
    amount_in_wei = int(amount_in_token * (10 ** TOKEN_DECIMALS))
    
    # Build token transfer transaction
    transfer_func = token_contract.functions.transfer(to_address, amount_in_wei)
    
    estimated_gas = transfer_func.estimate_gas({
        'from': sender_account.address,
        'nonce': nonce
    })
    
    tx = transfer_func.build_transaction({
        'chainId': CHAIN_ID,
        'gas': estimated_gas,
        'gasPrice': gas_price,
        'nonce': nonce
    })
    
    signed_tx = w3.eth.account.sign_transaction(tx, sender_account.key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    return tx_hash

for i, to_address in enumerate(addresses):
    if tx_counter >= MAX_TX:
        print(f"\n🚫 Batas {MAX_TX} transaksi tercapai. Bot berhenti.")
        break

    if all(to_address.lower() in sent_map[acc.address] for acc in accounts):
        continue

    print(f"\n📦 Kirim ke address [{i+1}/{len(addresses)}]: {to_address}")

    wallet_zipped = list(zip(accounts, private_keys))
    random.shuffle(wallet_zipped)

    for acc, pk in wallet_zipped:
        if tx_counter >= MAX_TX:
            print(f"\n🚫 Batas {MAX_TX} transaksi tercapai. Bot berhenti.")
            break

        wallet_index = accounts.index(acc) + 1

        if to_address.lower() in sent_map[acc.address]:
            print(f"[wallet {wallet_index}] ⏭️ Sudah dikirim sebelumnya.")
            continue

        try:
            # Check token balance first
            token_balance = token_contract.functions.balanceOf(acc.address).call()
            token_balance_human = token_balance / (10 ** TOKEN_DECIMALS)
            
            if token_balance <= 0:
                print(f"[wallet {wallet_index}] ❌ Saldo token kosong")
                continue

            # Determine random amount to send within user-defined range
            send_amount = round(random.uniform(MIN_AMOUNT, MAX_AMOUNT), 4)
            amount_in_wei = int(send_amount * (10 ** TOKEN_DECIMALS))

            if amount_in_wei > token_balance:
                print(f"[wallet {wallet_index}] ❌ Saldo tidak cukup (Memiliki: {token_balance_human:.4f} {TOKEN_SYMBOL}, Mencoba mengirim: {send_amount:.4f} {TOKEN_SYMBOL})")
                continue

            start_time = time.time()
            tx_hash = send_token_transaction(acc, to_address, send_amount)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            end_time = time.time()

            waktu = datetime.now().strftime("%H:%M:%S")
            durasi = round(end_time - start_time, 4)
            gas_used = receipt.gasUsed
            gas_price = w3.from_wei(receipt.effectiveGasPrice, 'gwei')
            tx_counter += 1

            print(f"[wallet {wallet_index}] ✅ {send_amount:.4f} {TOKEN_SYMBOL} → {to_address}")
            print(f"    TX Hash: {tx_hash.hex()}")
            print(f"    Gas Used: {gas_used} | Gas Price: {gas_price:.2f} Gwei")
            print(f"    Time: {waktu} | Duration: {durasi}s")
            print(f"    Total TX: #{tx_counter}/{MAX_TX}")

            with open(done_files[acc.address], "a") as f:
                f.write(to_address.lower() + "\n")
            sent_map[acc.address].add(to_address.lower())

            time.sleep(random.uniform(2, 10))
        except Exception as e:
            print(f"[wallet {wallet_index}] ⚠️ Gagal kirim: {str(e)}")

    delay = random.uniform(5, 15)
    print(f"⏳ Delay {delay:.2f} detik sebelum transaksi selanjutnya...")
    time.sleep(delay)

print("\n✅ Proses selesai.")