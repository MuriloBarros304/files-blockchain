import pytest
from unittest.mock import patch
from miner.miner import Miner

@patch('miner.miner.Blockchain')
@patch('miner.miner.Mempool')
@patch('miner.miner.ConsensusManager')
@patch('miner.miner.MinerNetwork')
def test_miner_initialization(mock_network, mock_consensus, mock_mempool, mock_blockchain):
    miner = Miner(
        broker='localhost:9092',
        difficulty=1,
        finalization_confirmations=2
    )
    assert miner.finalization_confirmations == 2
    assert miner.mempool is not None
    assert miner.blockchain is not None
    assert isinstance(miner.miner_id, str)
    assert mock_network.called
    assert mock_consensus.called

def test_miner_invalid_difficulty():
    with pytest.raises(ValueError, match="difficulty deve ser >= 1"):
        Miner(difficulty=0)

def test_miner_invalid_confirmations():
    with pytest.raises(ValueError, match="finalization_confirmations deve ser >= 0"):
        Miner(difficulty=1, finalization_confirmations=-1)
