from src import ReceiverFactory
from src import UntronReceiver

def deploy():
    usdt = "0xd07308A887ffA74b8965C0F26e6E2e70072C97b9"
    usdc = "0xd07308A887ffA74b8965C0F26e6E2e70072C97b9"
    flexSwapper = "0x0000000000000000000000000000000000000000" # fake address
    untronTransfers = "0x0000000000000000000000000000000000000000"

    receiver = UntronReceiver.deploy(usdt, usdc)
    receiver.setFlexSwapper(flexSwapper)
    receiver.setUntronTransfers(untronTransfers)

    receiverFactory = ReceiverFactory.deploy(receiver)
    
    # resolver = UntronResolver.deploy()
    # resolver.setReceiverFactory(receiverFactory)
    # url = ""
    # resolver.pushUrl(url)

    return receiverFactory

def moccasin_main():
    return deploy()