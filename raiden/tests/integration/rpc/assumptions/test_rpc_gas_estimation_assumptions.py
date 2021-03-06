import pytest

from raiden.constants import RECEIPT_FAILURE_CODE
from raiden.network.rpc.client import JSONRPCClient
from raiden.tests.utils.smartcontracts import deploy_rpc_test_contract

SSTORE_COST = 20000


def test_estimate_gas_fail(deploy_client: JSONRPCClient) -> None:
    """ A JSON RPC estimate gas call for a throwing transaction returns None"""
    contract_proxy, _ = deploy_rpc_test_contract(deploy_client, "RpcTest")

    address = contract_proxy.address
    assert len(deploy_client.web3.eth.getCode(address)) > 0

    msg = "Estimate gas should return None if the transaction hit an assert"
    assert deploy_client.estimate_gas(contract_proxy, "fail_assert", {}) is None, msg

    msg = "Estimate gas should return None if the transaction hit a revert."
    assert deploy_client.estimate_gas(contract_proxy, "fail_require", {}) is None, msg


def test_estimate_gas_fails_if_startgas_is_higher_than_blockgaslimit(
    deploy_client: JSONRPCClient
) -> None:
    """ Gas estimation fails if the transaction execution requires more gas
    then the block's gas limit.
    """
    contract_proxy, _ = deploy_rpc_test_contract(deploy_client, "RpcWithStorageTest")

    latest_block_hash = deploy_client.blockhash_from_blocknumber("latest")
    current_gas_limit = deploy_client.get_block(latest_block_hash)["gasLimit"]

    # This number of iterations is an over estimation to accomodate for races,
    # this cannot be significantly large because on parity it is a blocking
    # call.
    number_iterations = current_gas_limit // SSTORE_COST

    # This race condition cannot be fixed because geth does not support
    # block_identifier for eth_estimateGas. The test should not be flaky
    # because number_iterations is order of magnitudes larger then it needs to
    # be
    estimated_transaction = deploy_client.estimate_gas(
        contract_proxy, "waste_storage", {}, number_iterations
    )
    msg = "estimate_gas must return empty if sending the transaction would fail"
    assert estimated_transaction is None, msg


@pytest.mark.xfail(reason="The pending block is not taken into consideration")
def test_estimate_gas_defaults_to_pending(deploy_client: JSONRPCClient) -> None:
    """Estimating gas without an explicit block identifier always return an
    usable value.

    This test makes sure that the gas estimation works as expected (IOW, it
    will produce a value that can be used for start_gas and the transaction
    will be mined).

    This test was added because the clients Geth and Parity diverge in their
    estimate_gas interface. Geth never accepts a block_identifier for
    eth_estimateGas, and Parity rejects anything but `latest` if it is run with
    `--pruning=fast`.
    """
    contract_proxy, _ = deploy_rpc_test_contract(deploy_client, "RpcWithStorageTest")

    estimated_first_transaction = deploy_client.estimate_gas(
        contract_proxy, "gas_increase_exponential", {}
    )
    assert estimated_first_transaction, "gas estimation should not have failed"
    first_tx = deploy_client.transact(estimated_first_transaction)

    estimated_second_transaction = deploy_client.estimate_gas(
        contract_proxy, "gas_increase_exponential", {}
    )
    assert estimated_second_transaction, "gas estimation should not have failed"
    second_tx = deploy_client.transact(estimated_second_transaction)

    first_receipt = deploy_client.poll_transaction(first_tx)
    second_receipt = deploy_client.poll_transaction(second_tx)

    assert second_receipt["gasLimit"] < deploy_client.get_block("latest")["gasLimit"]
    assert first_receipt["status"] != RECEIPT_FAILURE_CODE
    assert second_receipt["status"] != RECEIPT_FAILURE_CODE
