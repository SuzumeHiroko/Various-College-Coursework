import time
import json
from src.logger import DataLogger

# init the logger
logger = DataLogger()
logger.create("radar_log_001")  # auto-adds .jsonl extension

# write 10 entries
for i in range(10):
    logger.write({
        "timestamp": time.time(),
        "serial_no": 123456789,
        "point_cloud": [[i, i+1, i+2]],
        "dimensions": [10, 10, 10]
    })
    time.sleep(0.1)  # simulate 10hz high-speed logging

logger.close()

# read back the JSONL file
with open("radar_log_001.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        print(entry)
