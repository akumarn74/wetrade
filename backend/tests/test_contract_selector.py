from app.trading.contracts import ContractSelector
from app.trading.types import OptionContract


def test_contract_selection_filters_and_sorts():
    selector = ContractSelector()
    contracts = [
        OptionContract('A', '0DTE', 1, 'C', 0.40, 1.0, 1.3, 100, 100),
        OptionContract('B', '0DTE', 1, 'C', 0.45, 1.0, 1.08, 500, 300),
        OptionContract('C', '0DTE', 1, 'P', -0.45, 1.0, 1.05, 500, 300),
    ]
    selected = selector.select(contracts, 'CALL')
    assert selected is not None
    assert selected.option_symbol == 'B'
