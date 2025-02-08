from src import UntronResolver

def deploy():
    resolver = UntronResolver.deploy()
    resolver.setReceiverFactory("0xF94f12392e6A731273fD950718966BD0e9A9858c")
    resolver.pushUrl("https://8ac3-194-36-25-30.ngrok-free.app/resolve")

    return resolver

def moccasin_main():
    return deploy()