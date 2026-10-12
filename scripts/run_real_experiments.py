import json
import time
import subprocess
import threading
from datetime import datetime, timezone

def run_alpha_stress(duration=120):
    print("Starting Alpha CPU stress...")
    start_time = datetime.now(timezone.utc)
    
    script = """
import multiprocessing, time
def stress():
    while True: pass
if __name__ == '__main__':
    procs = [multiprocessing.Process(target=stress) for _ in range(multiprocessing.cpu_count())]
    for p in procs: p.start()
    time.sleep(120)
    for p in procs: p.terminate()
    """
    with open('alpha_stress.py', 'w') as f:
        f.write(script)
        
    subprocess.run(["python", "alpha_stress.py"])
    
    end_time = datetime.now(timezone.utc)
    return {
        "node_id": "alpha-win",
        "experiment_id": f"real_alpha_cpu_{int(time.time())}",
        "stress_type": "cpu",
        "start_time_utc": start_time.isoformat(),
        "end_time_utc": end_time.isoformat()
    }

def run_beta_stress(duration=120):
    print("Starting Beta Disk stress...")
    start_time = datetime.now(timezone.utc)
    
    # Replace SECSECONDS with $(date +%s)
    bash_script = f"end=$(( $(date +%s) + {duration} )); while [ $(date +%s) -lt $end ]; do dd if=/dev/zero of=/tmp/beta_stress.tmp bs=1M count=1000 oflag=direct 2>/dev/null; done; rm -f /tmp/beta_stress.tmp"
    cmd = ["ssh", "beta", "-o", "BatchMode=yes", bash_script]
    
    subprocess.run(cmd)
    
    end_time = datetime.now(timezone.utc)
    return {
        "node_id": "beta",
        "experiment_id": f"real_beta_disk_{int(time.time())}",
        "stress_type": "disk",
        "start_time_utc": start_time.isoformat(),
        "end_time_utc": end_time.isoformat()
    }

def run_gamma_stress(duration=120):
    print("Starting Gamma Network stress...")
    start_time = datetime.now(timezone.utc)
    
    # Network download to /dev/null
    bash_script = f"end=$(( $(date +%s) + {duration} )); while [ $(date +%s) -lt $end ]; do wget -O /dev/null http://speedtest.tele2.net/1GB.zip 2>/dev/null; done"
    cmd = ["ssh", "gamma", "-o", "BatchMode=yes", bash_script]
    subprocess.run(cmd)
    
    end_time = datetime.now(timezone.utc)
    return {
        "node_id": "gamma",
        "experiment_id": f"real_gamma_net_{int(time.time())}",
        "stress_type": "net",
        "start_time_utc": start_time.isoformat(),
        "end_time_utc": end_time.isoformat()
    }

def main():
    duration = 180 # 3 minutes per test to get ~6 samples
    experiments = []
    
    # Run them concurrently to save time
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_alpha = executor.submit(run_alpha_stress, duration)
        future_beta = executor.submit(run_beta_stress, duration)
        future_gamma = executor.submit(run_gamma_stress, duration)
        
        experiments.append(future_alpha.result())
        print("Alpha done.")
        experiments.append(future_beta.result())
        print("Beta done.")
        experiments.append(future_gamma.result())
        print("Gamma done.")
    
    with open('analysis/outputs/real_experiment_log.json', 'w') as f:
        json.dump(experiments, f, indent=2)
        
    print("All real experiments completed and logged.")

if __name__ == '__main__':
    main()
