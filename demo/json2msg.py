import json
import msgpack
import sys

#file:///data/trace
#file:///data/trace-0001.msgpack when creating CR s
#actual generated file -> /home/bogao/.local/kind-node-data/cluster/[].msgpack
def main():
    if len(sys.argv) < 3:
        print("Usage: python json2msg.py <input.json> <output.msgpack>")
        sys.exit(1)
    
    INPUT_JSON = sys.argv[1]
    OUTPUT_MSGP = sys.argv[2]
    
    # 1) Load JSON from disk
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2) Serialize to MessagePack and save
    with open(OUTPUT_MSGP, "wb") as f:
        # use use_bin_type=True to write binary types correctly
        packed = msgpack.packb(data, use_bin_type=True)
        f.write(packed)

    print(f"Converted {INPUT_JSON} → {OUTPUT_MSGP}")

if __name__ == "__main__":
    main()
