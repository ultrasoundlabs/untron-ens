from src import UntronResolver
from src import ReceiverFactory
from src import UntronReceiver

def deploy():
    usdt = ""
    usdc = ""
    flexSwapper = ""
    untronTransfers = ""

    receiver = UntronReceiver.deploy(usdt, usdc)
    receiver.setFlexSwapper(flexSwapper)
    receiver.setUntronTransfers(untronTransfers)

    receiverFactory = ReceiverFactory.deploy(receiver)
    
    resolver = UntronResolver.deploy()
    resolver.setReceiverFactory(receiverFactory)
    url = ""
    resolver.pushUrl(url)

    return resolver

def moccasin_main():
    return deploy()