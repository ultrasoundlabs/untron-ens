from web3 import Web3
from ens import ENS
import os

# Connect to an Ethereum node with the mitmproxy certificate
w3 = Web3(Web3.HTTPProvider(
    'https://rpc.ankr.com/eth',
    # request_kwargs={
    #     'verify': os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.pem'),
    #     'proxies': {
    #         'https': 'http://127.0.0.1:8080',
    #         'http': 'http://127.0.0.1:8080'
    #     }
    # }
))
ns = ENS.from_web3(w3)

resolved = ns.address("TDWrw2Ra3tBCQjWwzFf387Z57bLrYq7YTr.totron.eth")
print(resolved)