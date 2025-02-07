from web3 import Web3
from ens import ENS

# Connect to an Ethereum node (for example, using Infura)
w3 = Web3(Web3.HTTPProvider('https://ethereum-sepolia-rpc.publicnode.com'))
ns = ENS.from_web3(w3)

print(ns.address("TEVr7jCiRofduU2wtQsMWLBr1m132A3S5j.totron.eth"))