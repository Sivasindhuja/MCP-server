import subprocess
import json
import time
import statistics

process = subprocess.Popen(
    ["python", "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)

def read_json_response():
    """Keep reading until we find a valid JSON line"""
    while True:
        line = process.stdout.readline()
        if not line:
            continue

        line = line.strip()

        if line.startswith("{") and "jsonrpc" in line:
            try:
                return json.loads(line)
            except:
                continue


def call_tool(payload):
    start = time.time()

    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()

    response = read_json_response()

    end = time.time()

    return response, end - start


payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "simple_search",
        "arguments": {
            "query": "project"
        }
    }
}

latencies = []

for _ in range(10):
    res, t = call_tool(payload)
    latencies.append(t)

    print("Tool latency:", res.get("latency"), "| End-to-end:", round(t, 4))

print("\n--- FINAL ---")
print("Avg latency:", round(statistics.mean(latencies), 4))
print("Min latency:", round(min(latencies), 4))
print("Max latency:", round(max(latencies), 4))