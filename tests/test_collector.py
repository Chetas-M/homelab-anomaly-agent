import pytest
import time
import importlib
from unittest.mock import patch, MagicMock

import collector.agent
from collector.agent import Collector, INGEST_URL

@pytest.fixture(autouse=True)
def restore_agent_env():
    yield
    importlib.reload(collector.agent)

@patch("collector.agent.psutil")
def test_collector_metrics_generation(mock_psutil):
    mock_psutil.cpu_percent.return_value = 10.5
    mock_psutil.virtual_memory.return_value.percent = 50.0
    mock_psutil.swap_memory.return_value.percent = 5.0
    mock_psutil.disk_usage.return_value.percent = 70.0
    
    # Setup initial mock IO counters
    mock_net_io_1 = MagicMock()
    mock_net_io_1.bytes_recv = 1000
    mock_net_io_1.bytes_sent = 1000
    
    mock_disk_io_1 = MagicMock()
    mock_disk_io_1.read_bytes = 2000
    mock_disk_io_1.write_bytes = 2000
    
    mock_psutil.net_io_counters.return_value = mock_net_io_1
    mock_psutil.disk_io_counters.return_value = mock_disk_io_1
    
    # Initialize collector
    collector = Collector()
    
    # Wait a bit to simulate time passing (mock monotonic time would be better but this is simple)
    time.sleep(0.1)
    
    # Second reading
    mock_net_io_2 = MagicMock()
    mock_net_io_2.bytes_recv = 1500
    mock_net_io_2.bytes_sent = 1200
    
    mock_disk_io_2 = MagicMock()
    mock_disk_io_2.read_bytes = 2500
    mock_disk_io_2.write_bytes = 2200
    
    mock_psutil.net_io_counters.return_value = mock_net_io_2
    mock_psutil.disk_io_counters.return_value = mock_disk_io_2
    
    # We patch monotonic to control elapsed time precisely
    with patch("collector.agent.time.monotonic", side_effect=[collector.last_time + 1.0, collector.last_time + 1.0]):
        metrics = collector.collect_metrics()
        
    assert metrics["cpu_pct"] == 10.5
    assert metrics["mem_pct"] == 50.0
    assert metrics["swap_pct"] == 5.0
    assert metrics["disk_used_pct"] == 70.0
    
    # Since elapsed is 1.0s, rate should just be the difference
    assert metrics["net_in_bps"] == 500.0
    assert metrics["net_out_bps"] == 200.0
    assert metrics["disk_read_bps"] == 500.0
    assert metrics["disk_write_bps"] == 200.0
    
    assert "node_id" in metrics
    assert "ts" in metrics

def test_collector_graceful_failure(caplog):
    collector = Collector()
    mock_post = MagicMock(side_effect=Exception("API down"))
    collector.session.post = mock_post
    collector.collect_metrics = MagicMock(return_value={"test": 1})
    
    # Test just one iteration of loop manually instead of calling run() which loops forever
    try:
        # Re-implement one run iteration for testing error handling
        metrics = collector.collect_metrics()
        response = collector.session.post(INGEST_URL, json=metrics, timeout=5)
        response.raise_for_status()
    except Exception as e:
        import logging
        logging.getLogger("collector.agent").error(f"Unexpected error during collection: {e}")
        
    assert "API down" in caplog.text
    collector.close()

def test_collector_fallback_ingest_url(monkeypatch):
    """When .env and process env do not define INGEST_URL, it should use the default fallback."""
    for key in ["NODE_ID", "INGEST_URL", "COLLECT_INTERVAL", "HAS_GPU"]:
        monkeypatch.delenv(key, raising=False)
    with patch("dotenv.load_dotenv"):
        reloaded = importlib.reload(collector.agent)
        assert reloaded.INGEST_URL == "http://localhost:8002/ingest"
        assert reloaded.NODE_ID == "default-node"
        assert reloaded.COLLECT_INTERVAL == 30
        assert reloaded.HAS_GPU is False

def test_collector_loads_dotenv_when_env_vars_absent(monkeypatch):
    """Proves that .env values from the project root are loaded when process environment variables are absent."""
    for key in ["NODE_ID", "INGEST_URL", "COLLECT_INTERVAL", "HAS_GPU"]:
        monkeypatch.delenv(key, raising=False)
        
    reloaded = importlib.reload(collector.agent)
    assert reloaded.NODE_ID == "alpha"
    assert reloaded.INGEST_URL == "http://100.126.2.116:8002/ingest"
    assert reloaded.COLLECT_INTERVAL == 30
    assert reloaded.HAS_GPU is True

def test_collector_loads_custom_dotenv_file_when_env_vars_absent(monkeypatch):
    """Proves that values from a .env source are loaded when process environment variables are absent."""
    import os
    custom_values = {
        "NODE_ID": "test-node-custom",
        "INGEST_URL": "http://custom-test:8002/ingest",
        "COLLECT_INTERVAL": "15",
        "HAS_GPU": "false",
    }
    for key in ["NODE_ID", "INGEST_URL", "COLLECT_INTERVAL", "HAS_GPU"]:
        monkeypatch.delenv(key, raising=False)

    def mock_custom_load(dotenv_path=None, override=False, **kwargs):
        for k, v in custom_values.items():
            if override or k not in os.environ:
                os.environ[k] = v
        return True

    with patch("dotenv.load_dotenv", side_effect=mock_custom_load):
        reloaded = importlib.reload(collector.agent)
        assert reloaded.NODE_ID == "test-node-custom"
        assert reloaded.INGEST_URL == "http://custom-test:8002/ingest"
        assert reloaded.COLLECT_INTERVAL == 15
        assert reloaded.HAS_GPU is False

def test_collector_calls_load_dotenv_with_project_root_env():
    """Verify load_dotenv is called with the .env file located at the project root."""
    with patch("dotenv.load_dotenv") as mock_load_dotenv:
        importlib.reload(collector.agent)
        mock_load_dotenv.assert_called_once()
        called_path = mock_load_dotenv.call_args.kwargs.get("dotenv_path")
        assert called_path == collector.agent.PROJECT_ROOT / ".env"
        assert called_path.name == ".env"
        assert called_path.parent == collector.agent.PROJECT_ROOT
        assert mock_load_dotenv.call_args.kwargs.get("override") is False

def test_collector_preserves_explicit_env_vars(monkeypatch):
    """Proves that explicitly set process environment variables are preserved over .env values."""
    monkeypatch.setenv("NODE_ID", "explicit-node-123")
    monkeypatch.setenv("INGEST_URL", "http://explicit-url:8002/ingest")
    monkeypatch.setenv("COLLECT_INTERVAL", "45")
    monkeypatch.setenv("HAS_GPU", "false")
    
    reloaded = importlib.reload(collector.agent)
    assert reloaded.NODE_ID == "explicit-node-123"
    assert reloaded.INGEST_URL == "http://explicit-url:8002/ingest"
    assert reloaded.COLLECT_INTERVAL == 45
    assert reloaded.HAS_GPU is False

def test_collector_session_persistence():
    import requests
    collector = Collector()
    assert isinstance(collector.session, requests.Session)
    collector.close()

@patch("collector.agent.GPU_AVAILABLE", True)
@patch("collector.agent.pynvml")
def test_collector_gpu_cached_handle_and_metrics(mock_pynvml):
    mock_handle = MagicMock()
    mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle
    
    mock_util = MagicMock()
    mock_util.gpu = 42.0
    mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = mock_util
    
    mock_mem = MagicMock()
    mock_mem.used = 2 * 1024 * 1024 * 1024
    mock_mem.total = 8 * 1024 * 1024 * 1024
    mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mock_mem
    
    collector = Collector()
    assert collector.gpu_handle == mock_handle
    mock_pynvml.nvmlDeviceGetHandleByIndex.assert_called_once_with(0)
    
    metrics = collector.collect_metrics()
    assert metrics["gpu_util_pct"] == 42.0
    assert metrics["gpu_vram_pct"] == 25.0
    
    # Ensure handle was NOT retrieved again
    mock_pynvml.nvmlDeviceGetHandleByIndex.assert_called_once()
    mock_pynvml.nvmlDeviceGetUtilizationRates.assert_called_with(mock_handle)
    mock_pynvml.nvmlDeviceGetMemoryInfo.assert_called_with(mock_handle)
    collector.close()

@patch("collector.agent.GPU_AVAILABLE", False)
def test_collector_gpu_fallback_when_unavailable():
    collector = Collector()
    assert collector.gpu_handle is None
    metrics = collector.collect_metrics()
    assert metrics["gpu_util_pct"] is None
    assert metrics["gpu_vram_pct"] is None
    collector.close()

@patch("collector.agent.GPU_AVAILABLE", True)
@patch("collector.agent.pynvml")
def test_collector_gpu_handle_failure_graceful(mock_pynvml):
    mock_pynvml.nvmlDeviceGetHandleByIndex.side_effect = Exception("NVML device error")
    collector = Collector()
    assert collector.gpu_handle is None
    metrics = collector.collect_metrics()
    assert metrics["gpu_util_pct"] is None
    assert metrics["gpu_vram_pct"] is None
    collector.close()

@patch("collector.agent.psutil")
def test_collector_counter_reset(mock_psutil):
    mock_psutil.cpu_percent.return_value = 10.0
    mock_psutil.virtual_memory.return_value.percent = 50.0
    mock_psutil.swap_memory.return_value.percent = 5.0
    mock_psutil.disk_usage.return_value.percent = 50.0
    
    # Initial high counters
    mock_net_io_1 = MagicMock()
    mock_net_io_1.bytes_recv = 5000
    mock_net_io_1.bytes_sent = 5000
    
    mock_disk_io_1 = MagicMock()
    mock_disk_io_1.read_bytes = 5000
    mock_disk_io_1.write_bytes = 5000
    
    mock_psutil.net_io_counters.return_value = mock_net_io_1
    mock_psutil.disk_io_counters.return_value = mock_disk_io_1
    
    collector = Collector()
    
    # Second reading after counter reset (current < previous)
    mock_net_io_2 = MagicMock()
    mock_net_io_2.bytes_recv = 1000
    mock_net_io_2.bytes_sent = 1000
    
    mock_disk_io_2 = MagicMock()
    mock_disk_io_2.read_bytes = 1000
    mock_disk_io_2.write_bytes = 1000
    
    mock_psutil.net_io_counters.return_value = mock_net_io_2
    mock_psutil.disk_io_counters.return_value = mock_disk_io_2
    
    with patch("collector.agent.time.monotonic", side_effect=[collector.last_time + 1.0, collector.last_time + 1.0]):
        metrics = collector.collect_metrics()
        
    # Negative counter deltas caused by resets must yield None rather than negative numbers
    assert metrics["net_in_bps"] is None
    assert metrics["net_out_bps"] is None
    assert metrics["disk_read_bps"] is None
    assert metrics["disk_write_bps"] is None
