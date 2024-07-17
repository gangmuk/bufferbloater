#! /usr/bin/python

import matplotlib
import matplotlib.pyplot as plt
import csv, sys, os
import numpy as np
import pandas as pd
from collections import Counter

# matplotlib.rcParams.update({'font.size': 22})

# Stats dump interval so we can calculate rates.
# dt = 0.5
dt = 1.0
xlabel_fontsize = 10
ylabel_fontsize = 10
legend_fontsize = 10
xtick_fontsize = 10
ytick_fontsize = 10

if len(sys.argv) == 2:
    data_dir = sys.argv[1]
    assert os.path.exists(data_dir)
else:
    print("Usage: generate_report.py <data_dir>")
    exit(1)

if not os.path.exists(data_dir):
    print("No data directory provided or found.")
    sys.exit(1)

rq_latency_x = []
rq_latency_y = []

timeout_timestamps = []

def xy_from_csv(filename):
    x = []
    y = []
    path = data_dir + "/" + filename
    if os.path.exists(path):
        with open(path,'r') as csvfile:
            plots = csv.reader(csvfile, delimiter=',')
            for row in plots:
                x.append(float(row[0]))
                y.append(float(row[1]))
    else:
        print(f"File {path} does not exist.")
    return x, y

xstart = 0
def adjust(xs):
    assert xstart != 0
    # return list(map(lambda x: (x - xs[0])/1e9, xs))
    return list(map(lambda x: (x - xstart)/1e9, xs))
    
colors = ["blue", "green", "red"]
# fig, (ax1, ax2, ax3) = plt.subplots(3)
fig, (ax1, ax2) = plt.subplots(2)
for i in range(1):
    # We want to plot the request are, latency, and the moment timeouts happen.
    # While we're at it, let's just adjust the timestamp to be relative to the
    # simulation start.
    in_rq_rate_x, in_rq_rate_y = xy_from_csv("client.rps.{}.csv".format(i))
    out_rq_rate_x, out_rq_rate_y = xy_from_csv("client.rq.total.count.{}.csv".format(i))
    retry_rate_x, retry_rate_y = xy_from_csv("client.rq.retry.count.{}.csv".format(i))
    rq_latency_x, rq_latency_y = xy_from_csv("client.rq.latency.{}.csv".format(i))
    # rq_latency_y = [x*1000 for x in rq_latency_y] # convert to ms
    success_stamps, _ = xy_from_csv("client.rq.success_hist.{}.csv".format(i))
    goodput_x, goodput_y = xy_from_csv("client.rq.success.count.{}.csv".format(i))
    failure_x, failure_y = xy_from_csv("client.rq.failure.count.{}.csv".format(i))
    timeout_x, timeout_y = xy_from_csv("client.rq.timeout.{}.csv".format(i))
    timeout_origin_x, timeout_origin_y = xy_from_csv("client.rq.timeout_origin.{}.csv".format(i))
    
    expected_latency_x, expected_latency_y = xy_from_csv("server.expected_latency.{}.csv".format(i))

    # Adjust for dt.
    goodput_y = list(map(lambda x: x / dt, goodput_y))

    # print(f"{in_rq_rate_x}, {out_rq_rate_x}, {rq_latency_x}, {goodput_x}")
    
    ymax = max(in_rq_rate_y + rq_latency_y + goodput_y + failure_y + retry_rate_y)
    print("ymax", ymax)
    
    xstart = min(in_rq_rate_x + out_rq_rate_x + rq_latency_x + goodput_x + failure_x + timeout_x + timeout_origin_x)
    xend = (max(in_rq_rate_x + out_rq_rate_x + rq_latency_x + goodput_x + failure_x + timeout_x + timeout_origin_x) - xstart)/1e9
    # xend = 60
    
    adjusted_rq_latency_endtime = [adjusted_start_time+latency for adjusted_start_time, latency in zip(adjust(rq_latency_x), rq_latency_y)]

    ax1.set_xlabel('Time (s)', fontsize=xlabel_fontsize)
    ax1.set_ylabel('Request Latency(s)', fontsize=ylabel_fontsize)
    #ax1.set_yscale('log') # log scale
    # ax1.plot(adjust(rq_latency_x),rq_latency_y, color=colors[i], label="observed latency")
    ax1.scatter(adjust(rq_latency_x),rq_latency_y, color=colors[i], label="observed latency", marker='.')
    # ax1.scatter(adjusted_rq_latency_endtime,rq_latency_y, marker='.', color=colors[i], label="observed latency")
    ax1.tick_params(axis='x', labelsize=xtick_fontsize)
    ax1.tick_params(axis='y', labelsize=ytick_fontsize)
    ax1.set_xlim([0,xend])
    ax1.set_ylim([0,max(rq_latency_y)*1.3])
    ax1.legend(fontsize=legend_fontsize)
    # ax1.yaxis.set_major_locator(plt.MultipleLocator(1))

    ax2.set_xlabel('Time (s)', fontsize=xlabel_fontsize)
    ax2.set_ylabel('Offered Load', fontsize=ylabel_fontsize)
    
    # for i, tx in enumerate(adjust(timeout_x)):
    #     if i == 0:
    #         ax2.axvline(tx, color="pink", linestyle="-", alpha=0.7, label="timeout")
    #     else:
    #         ax2.axvline(tx, color="pink", linestyle="-", alpha=0.7)
            
    if len(timeout_x) > 0:
        ax2.axvline(adjust(timeout_x)[0], ymin=0.5, ymax=0.1, color="red", linestyle="-", alpha=0.7, label="timeout")
        quantized_timeout_x = [round(tx, 1) for tx in adjust(timeout_x)]  # Quantize timeout x values to 0.1s intervals
        timeout_counts = Counter(quantized_timeout_x)
        max_count = max(timeout_counts.values())
        for tx, count in timeout_counts.items():
            alpha_value = min(1.0, count / max_count * 0.9 + 0.2)
            ax2.axvline(tx, ymin=0.5, ymax=1.0, color="red", linestyle="-", alpha=alpha_value)
    if len(timeout_origin_x) > 0:
        ax2.axvline(adjust(timeout_origin_x)[0], ymin=0.0, ymax=0.5, color="orange", linestyle="-", alpha=0.7, label="timeout_origin")
        quantized_timeout_origin_x = [round(tx, 1) for tx in adjust(timeout_origin_x)]
        timeout_counts = Counter(quantized_timeout_origin_x)
        max_count = max(timeout_counts.values())
        for tx, count in timeout_counts.items():
            alpha_value = min(1.0, count / max_count * 0.9 + 0.2)
            ax2.axvline(tx, ymin=0.0, ymax=0.5, color="orange", linestyle="-", alpha=alpha_value)
    
    ax2.plot(adjust(in_rq_rate_x), in_rq_rate_y, label="load")
    ax2.plot(adjust(goodput_x), goodput_y, color="green", label="goodput", marker='^')
    ax2.plot(adjust(failure_x), failure_y, color="black", label="failure", linestyle="--", marker='o')
    ax2.plot(adjust(retry_rate_x),retry_rate_y, color="cyan", label="retries", marker='x', linestyle=":")
    ax2.axhline(0)
    ax2.tick_params(axis='x', labelsize=xtick_fontsize)
    ax2.tick_params(axis='y', labelsize=ytick_fontsize)
    ax2.set_xlim([0,xend])
    ax2.set_ylim([-50,ymax*1.3])
    ax2.yaxis.set_major_locator(plt.MultipleLocator(100))
    ax2.grid(True)
    ax2.legend(fontsize=legend_fontsize, ncol=2)

    # ax3.set_xlabel('Time (s)', fontsize=xlabel_fontsize)
    # ax3.set_ylabel("Timeout", fontsize=ylabel_fontsize)
    # for i, tx in enumerate(adjust(timeout_x)):
    #     if i == 0:
    #         ax3.axvline(tx, color="pink", linestyle="-", alpha=0.5, label="timeout")
    #     else:
    #         ax3.axvline(tx, color="pink", linestyle="-", alpha=0.5)
    # ax3.tick_params(axis='x', labelsize=xtick_fontsize)
    # ax3.tick_params(axis='y', labelsize=ytick_fontsize)
    # ax3.set_xlim([0,xend])
    # ax3.set_ylim([0,1.0])
    # ax3.legend(fontsize=legend_fontsize)

plt.tight_layout()
report_path = f"{data_dir}/report.pdf"
plt.savefig(report_path)
print(f"Report saved to ./{report_path}")
# plt.show()
