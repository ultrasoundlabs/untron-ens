# pragma version 0.4.0
# @license MIT

import Resolver
from pcaversaccio.snekmate.src.snekmate.auth import ownable

initializes: ownable
implements: Resolver

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
    tronAddressLength: uint256 = convert(slice(name, 0, 1), uint256)

    # a Tron address (base58-encoded 25 bytes) is between 22 and 35 chars long
    # Source: https://chatgpt.com/share/67a60383-9340-8002-9d9c-218deb0f5a0c
    assert tronAddressLength >= 22 and tronAddressLength <= 35, "invalid subdomain length"

    tronAddress: bytes20 = self.base58CheckIntoRawTronAddress(slice(name, 1, tronAddressLength), tronAddressLength)


    return abi_encode(tronAddress)