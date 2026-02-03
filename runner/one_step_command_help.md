cp demo/trace-0001.msgpack ~/.local/kind-node-data/cluster/
python runner/one_step.py --trace demo/trace-0001.msgpack --ns virtual-default --deploy web --target 3 --duration 40