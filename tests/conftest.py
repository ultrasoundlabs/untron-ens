import pytest
from script.deploy import deploy

@pytest.fixture
def untron_resolver_contract():
    return deploy()