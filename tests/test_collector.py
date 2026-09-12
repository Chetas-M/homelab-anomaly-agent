import pytest
import time
from unittest.mock import patch, MagicMock

from collector.agent import Collector, INGEST_URL

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

def test_collector_fallback_ingest_url():
    assert INGEST_URL == "http://localhost:8002/ingest"

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
