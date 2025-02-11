from src import UntronResolver

def deploy():
    resolver = UntronResolver.deploy()
    resolver.setReceiverFactory("0x48FF9AAc987feb040D7846c8F4C5Cc794bfe3869")
    resolver.pushUrl("https://bba5-185-209-196-189.ngrok-free.app/resolve")

    return resolver

def moccasin_main():
    return deploy()