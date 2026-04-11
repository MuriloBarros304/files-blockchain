import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_environment():
    # We patch the Kafka dependencies so the test doesn't hang waiting for a broker
    with patch('gateway.main.KafkaProducer') as mock_producer, \
         patch('gateway.main.kafka_pump.iniciar') as mock_pump_iniciar, \
         patch('gateway.main.kafka_pump.stop') as mock_pump_stop:
        
        mock_producer_instance = MagicMock()
        mock_producer.return_value = mock_producer_instance
        
        # Import the app only AFTER the patches are in place
        from gateway.main import app 
        
        yield app, mock_producer_instance

def test_healthz_endpoint(mock_environment):
    app, _ = mock_environment
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

def test_post_transaction(mock_environment):
    app, mock_producer = mock_environment
    with TestClient(app) as client:
        tx_payload = {
            "sender": "Alice",
            "receiver": "Bob",
            "fee": 1.5,
            "reward": 0.0
        }
        response = client.post("/transactions", json=tx_payload)
        
        assert response.status_code == 200
        assert response.json()["status"] == "sent"
        
        # Verify our gateway actually tried to send the message to Kafka
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()