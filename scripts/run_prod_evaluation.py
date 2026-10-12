import os
import subprocess

def main():
    print("Exporting production database...")
    subprocess.run(["python", "scripts/export_prod_db.py"], check=True)
    
    print("Running evaluation on production data...")
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite:///prod_telemetry.db"
    env["EXPERIMENT_LOG"] = "real_experiment_log.json"
    
    subprocess.run(["python", "analysis/evaluate.py"], env=env, check=True)
    
    print("Complete!")

if __name__ == "__main__":
    main()
