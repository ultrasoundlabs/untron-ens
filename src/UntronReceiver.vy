# pragma version 0.4.0
# @license MIT

from pcaversaccio.snekmate.src.snekmate.auth import ownable
from interfaces import UntronReceiver
# from ultrasoundlabs.untron_intents.src import UntronTransfers # not sure why not working

initializes: ownable
implements: UntronReceiver

# TO BE IMPORTED FROM UNTRON_INTENTS WHEN I FIGURE OUT HOW TO IMPORT IT
interface IUntronTransfers:
    def compactUsdt(swapData: bytes32): nonpayable
    def compactUsdc(swapData: bytes32): nonpayable

interface IDaimoFlexSwapper:
    def swapToCoin(tokenIn: address, amountIn: uint256, tokenOut: address, extraData: Bytes[16384]) -> uint256: nonpayable

interface IERC20:
    def approve(spender: address, amount: uint256) -> bool: nonpayable
    def balanceOf(owner: address) -> uint256: view
    def allowance(owner: address, spender: address) -> uint256: view

destinationTronAddress: public(bytes20)
flexSwapper: public(address)
untronTransfers: public(address)
usdt: public(immutable(address))
usdc: public(immutable(address))

@deploy
def __init__(_usdt: address, _usdc: address):
    ownable.__init__()
    usdt = _usdt
    usdc = _usdc

@internal
@view
def _onlyOwner():
    assert msg.sender == ownable.owner, "unauthorized"

@external
def setTronAddress(tronAddress: bytes20):
    self._onlyOwner()
    assert self.destinationTronAddress == empty(bytes20), "destinationTronAddress already set"
    self.destinationTronAddress = tronAddress

@external
def setFlexSwapper(flexSwapper: address):
    self._onlyOwner()
    self.flexSwapper = flexSwapper

@external
def setUntronTransfers(untronTransfers: address):
    self._onlyOwner()
    self.untronTransfers = untronTransfers

@external
def swapIntoUsdc(_token: address, extraData: Bytes[16384]):
    token: IERC20 = IERC20(_token)

    if staticcall token.allowance(self, self.flexSwapper) == 0:
        extcall token.approve(self.flexSwapper, max_value(uint256))

    extcall IDaimoFlexSwapper(self.flexSwapper).swapToCoin(_token, staticcall token.balanceOf(self), usdc, extraData)

@internal
def _constructSwapData(amount: uint256) -> bytes32:
    # output amount (6-12th bytes) is 0 so that Untron Transfers contract uses the recommended one
    return convert((amount << 208) | convert(convert(self.destinationTronAddress, uint160), uint256), bytes32)

@external
def intron():
    usdtBalance: uint256 = staticcall IERC20(usdt).balanceOf(self)
    usdcBalance: uint256 = staticcall IERC20(usdc).balanceOf(self)
    if usdtBalance > 0:
        swapData: bytes32 = self._constructSwapData(usdtBalance)
        extcall IUntronTransfers(self.untronTransfers).compactUsdt(swapData)

    if usdcBalance > 0:
        swapData: bytes32 = self._constructSwapData(usdcBalance)
        extcall IUntronTransfers(self.untronTransfers).compactUsdc(swapData)
