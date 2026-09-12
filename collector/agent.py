import os
import time
import logging
import platform
from datetime import datetime, timezone

import psutil
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

NODE_ID = os.getenv("NODE_ID", "default-node")
INGEST_URL = os.getenv("INGEST_URL", "http://localhost:8002/ingest")
COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", "30"))
HAS_GPU = os.getenv("HAS_GPU", "false").lower() == "true"

pynvml = None
if HAS_GPU:
    try:
        import pynvml
        pynvml.nvmlInit()
        GPU_AVAILABLE = True
    except ImportError:
        logger.warning("pynvml not installed, GPU metrics will be unavailable")
        GPU_AVAILABLE = False
    except Exception as e:
        logger.warning(f"NVML initialization failed ({e}), GPU metrics will be unavailable")
        GPU_AVAILABLE = False
else:
    GPU_AVAILABLE = False

class Collector:
    def __init__(self):
        self.last_net_io = psutil.net_io_counters()
        self.last_disk_io = psutil.disk_io_counters()
        self.last_time = time.monotonic()
        self.session = requests.Session()
        
        # Prime the CPU percentage calculation
        psutil.cpu_percent(interval=None)

        # Cache GPU handle if GPU collection is available
        self.gpu_handle = None
        if GPU_AVAILABLE:
            try:
                self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except Exception as e:
                logger.warning(f"Failed to acquire GPU handle at index 0: {e}")
                self.gpu_handle = None

    def collect_metrics(self):
        now_time = time.monotonic()
        elapsed = now_time - self.last_time
        
        # CPU
        cpu_pct = psutil.cpu_percent(interval=None)
        
        # Memory
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        
        # Swap
        swap = psutil.swap_memory()
        swap_pct = swap.percent
        
        # Disk IO
        disk_io = psutil.disk_io_counters()
        disk_read_bps = None
        disk_write_bps = None
        if disk_io and self.last_disk_io and elapsed > 0:
            delta_read = disk_io.read_bytes - self.last_disk_io.read_bytes
            delta_write = disk_io.write_bytes - self.last_disk_io.write_bytes
            disk_read_bps = (delta_read / elapsed) if delta_read >= 0 else None
            disk_write_bps = (delta_write / elapsed) if delta_write >= 0 else None
            
        # Disk Usage (using root/C: drive depending on OS)
        try:
            path = "C:\\" if platform.system() == "Windows" else "/"
            disk_usage = psutil.disk_usage(path)
            disk_used_pct = disk_usage.percent
        except Exception as e:
            logger.debug(f"Could not get disk usage: {e}")
            disk_used_pct = None
            
        # Network IO
        net_io = psutil.net_io_counters()
        net_in_bps = None
        net_out_bps = None
        if net_io and self.last_net_io and elapsed > 0:
            delta_recv = net_io.bytes_recv - self.last_net_io.bytes_recv
            delta_sent = net_io.bytes_sent - self.last_net_io.bytes_sent
            net_in_bps = (delta_recv / elapsed) if delta_recv >= 0 else None
            net_out_bps = (delta_sent / elapsed) if delta_sent >= 0 else None
            
        # Load averages (Not supported natively on Windows via psutil in the same way)
        load1, load5, load15 = None, None, None
        if hasattr(psutil, "getloadavg"):
            try:
                load1, load5, load15 = psutil.getloadavg()
            except Exception:
                pass
                
        # Temperature
        temp_c = None
        if hasattr(psutil, "sensors_temperatures"):
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    # Just grab the first coretemp if available, otherwise just grab the first available
                    first_sensor = list(temps.values())[0]
                    if first_sensor:
                        temp_c = first_sensor[0].current
            except Exception:
                pass
                
        # GPU Metrics
        gpu_util_pct = None
        gpu_vram_pct = None
        if GPU_AVAILABLE and self.gpu_handle is not None:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
                gpu_util_pct = float(util.gpu)
                
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                gpu_vram_pct = (mem_info.used / mem_info.total) * 100.0
            except Exception as e:
                logger.debug(f"Failed to collect GPU metrics: {e}")
                
        # Update last counters
        self.last_net_io = net_io
        self.last_disk_io = disk_io
        self.last_time = now_time
        
        return {
            "node_id": NODE_ID,
            "ts": datetime.now(timezone.utc).isoformat(),
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "swap_pct": swap_pct,
            "disk_read_bps": disk_read_bps,
            "disk_write_bps": disk_write_bps,
            "disk_used_pct": disk_used_pct,
            "net_in_bps": net_in_bps,
            "net_out_bps": net_out_bps,
            "load1": load1,
            "load5": load5,
            "load15": load15,
            "temp_c": temp_c,
            "gpu_util_pct": gpu_util_pct,
            "gpu_vram_pct": gpu_vram_pct
        }

    def run(self):
        logger.info(f"Starting collector for node '{NODE_ID}'")
        logger.info(f"Ingest URL: {INGEST_URL}")
        logger.info(f"Interval: {COLLECT_INTERVAL}s")
        
        # Give initial interval to prime rates accurately
        time.sleep(1)
        
        while True:
            try:
                metrics = self.collect_metrics()
                response = self.session.post(INGEST_URL, json=metrics, timeout=5)
                response.raise_for_status()
                logger.debug("Metrics ingested successfully")
            except requests.RequestException as e:
                logger.error(f"Failed to send metrics: {e}")
            except Exception as e:
                logger.error(f"Unexpected error during collection: {e}")
                
            time.sleep(COLLECT_INTERVAL)

    def close(self):
        if hasattr(self, "session") and self.session:
            self.session.close()

if __name__ == "__main__":
    collector = Collector()
    try:
        collector.run()
    finally:
        collector.close()
