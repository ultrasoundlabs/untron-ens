# pragma version 0.4.0
# @license MIT

from pcaversaccio.snekmate.src.snekmate.auth import ownable

initializes: ownable

urls: public(DynArray[String[1024], 16])

@external
def popUrl() -> String[1024]:
    assert msg.sender == ownable.owner, "unauthorized"
    return self.urls.pop()

@external
def pushUrl(url: String[1024]):
    assert msg.sender == ownable.owner, "unauthorized"
    self.urls.append(url)

@deploy
def __init__():
    ownable.__init__()

@external
def supportsInterface(interfaceID: bytes4) -> bool:
    if interfaceID == 0x01ffc9a7: # supportsInterface(bytes4)
        return True
    if interfaceID == 0x3b3b57de: # addr(bytes32)
        return True
    if interfaceID == 0x9061b923: # resolve(bytes,bytes)
        return True
    return False

@external
def addr(node: bytes32) -> address:
    return ownable.owner

@internal
def base58IndexOf(char: uint256) -> uint256:
    if char >= 49 and char <= 57:
        return char - 49
    if char >= 65 and char <= 72:
        return char - 56
    if char >= 74 and char <= 78:
        return char - 57
    if char >= 80 and char <= 90:
        return char - 58
    if char >= 97 and char <= 107:
        return char - 64
    if char >= 109 and char <= 122:
        return char - 65
    raise uint2str(char)

@internal
def base58CheckIntoRawTronAddress(name: Bytes[64], length: uint256) -> bytes20:
    num: uint256 = 0

    # max 35 chars length of a Tron address
    # we turn it into a 32-byte big endian decoded value
    for i: uint256 in range(length, bound=35):
        num = num * 58 + self.base58IndexOf(convert(slice(name, i, 1), uint256))

    num >>= 32 # last 4 bytes are the checksum (base58check)
    # strip the first 0x41 byte and get the last 20 bytes
    # conversion between address is necessary to not change endianness
    return convert(convert(num & convert(convert(0xffffffffffffffffffffffffffffffffffffffff, uint160), uint256), uint160), bytes20)

@external
def resolve(name: Bytes[64], data: Bytes[1024]) -> Bytes[32]:

    # sig OffchainLookup(address,string[],bytes,bytes4,bytes) == 0x556f1830
    # sig untronSubdomain(bytes,bytes) == 0xddf425a6
    # ask to ping the relayer to bruteforce the case of the lowercased Tron address
    # (ENS normalizes all names to lowercase but we need the proper case to decode the Tron address)
    raw_revert(concat(b"\x55\x6f\x18\x30", abi_encode(self, self.urls, name, 0xddf425a6, name)))

@internal
def extractSubdomain(fullDomain: Bytes[64]) -> (Bytes[64], uint256):
    # ENS encodes the domains in DNS wire format, which is a set of length-prefixed strings
    subdomainLength: uint256 = convert(slice(fullDomain, 0, 1), uint256)

    # extract the subdomain from the full domain
    subdomain: Bytes[64] = slice(fullDomain, 1, subdomainLength)

    return subdomain, subdomainLength

@internal
def isThisJustLowercase(string: Bytes[64], lowercasedString: Bytes[64]) -> bool:
    for i: uint256 in range(len(string), bound=64):
        leftLetter: uint256 = convert(slice(string, i, 1), uint256)
        rightLetter: uint256 = convert(slice(lowercasedString, i, 1), uint256)
        if leftLetter != rightLetter and leftLetter != rightLetter - 32:
            return False
    return True

@external
def untronSubdomain(serverResponse: Bytes[64], originalDomain: Bytes[64]) -> Bytes[32]:
    
    serverTronAddress: Bytes[64] = b""
    serverTronAddressLength: uint256 = 0
    serverTronAddress, serverTronAddressLength = self.extractSubdomain(serverResponse)
    assert len(serverResponse) == len(originalDomain) and self.isThisJustLowercase(serverResponse, originalDomain), "server response is invalid"

    tronAddress: bytes20 = self.base58CheckIntoRawTronAddress(serverTronAddress, serverTronAddressLength)

    return abi_encode(convert(tronAddress, address))