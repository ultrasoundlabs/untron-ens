from src import UntronResolver

def deploy():
    resolver = UntronResolver.deploy()
    resolver.setReceiverFactory("0xA17ff8aFe3a671BEa5340bcaE9F45AB28cB8e9D4")
    resolver.pushUrl("https://8ac3-194-36-25-30.ngrok-free.app/resolve")

    return resolver

def moccasin_main():
    return deploy()