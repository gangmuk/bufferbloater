import os
import sys
import datetime

if __name__ == "__main__":
    config_path = sys.argv[1]
    output_posfix = sys.argv[2]
    if len(sys.argv) != 3:
        print("Usage: run.py <config_path> <output_posfix>")
        exit(1)
    # now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    # output_dir = f"output/{now}-{output_posfix}"
    output_dir = f"output/{output_posfix}"
    os.system(f"mkdir -p {output_dir}")
    os.system(f"./bin/bufferbloater -config {config_path} -data_dir {output_dir}")
    os.system(f"python generate_report.py {output_dir}")
    os.system(f"cp {config_path} {output_dir}/config.yaml")