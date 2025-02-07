from web3 import Web3
from ens import ENS
from base58 import b58decode_check

w3 = Web3(Web3.HTTPProvider(
    'https://ethereum-sepolia-rpc.publicnode.com'
))
ns = ENS.from_web3(w3)

resolved = ns.address("TEVr7jCiRofduU2wtQsMWLBr1m132A3S5j.totron.eth").lower()
tron_address_in_evm_format = "0x" + b58decode_check("TEVr7jCiRofduU2wtQsMWLBr1m132A3S5j")[1:].hex()
print(resolved)
print(tron_address_in_evm_format)
print(resolved == tron_address_in_evm_format)