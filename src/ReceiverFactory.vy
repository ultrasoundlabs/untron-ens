# pragma version 0.4.0
# @license MIT

from pcaversaccio.snekmate.src.snekmate.auth import ownable
from pcaversaccio.snekmate.src.snekmate.utils import create2_address
from interfaces import ReceiverFactory
from interfaces import UntronReceiver

initializes: ownable
implements: ReceiverFactory

receiverImplementation: public(immutable(address))

event ReceiverDeployed:
    destinationTronAddress: bytes20
    receiver: address

@deploy
def __init__(_receiverImplementation: address):
    ownable.__init__()
    receiverImplementation = _receiverImplementation

@external
def deploy(destinationTronAddress: bytes20) -> address:
    contract: address = create_minimal_proxy_to(receiverImplementation, salt=convert(destinationTronAddress, bytes32))
    receiver: UntronReceiver = UntronReceiver(contract)
    extcall receiver.setTronAddress(destinationTronAddress)

    log ReceiverDeployed(destinationTronAddress, contract)

    return contract

@external
@view
def generateReceiverAddress(destinationTronAddress: bytes20) -> address:
    return create2_address._compute_address_self(convert(destinationTronAddress, bytes32), receiverImplementation.codehash)