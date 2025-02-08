import pytest
from script.deploy_receiver_factory import deploy

@pytest.fixture
def untron_receiver_factory_contract():
    return deploy()