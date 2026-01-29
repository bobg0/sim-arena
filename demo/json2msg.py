import json
import msgpack

# Paths — change as needed
INPUT_JSON  = "david.json"
OUTPUT_MSGP = "trace-0001.msgpack"

#file:///data/trace
#file:///data/trace-0001.msgpack when creating CR s
#actual generated file -> /home/bogao/.local/kind-node-data/cluster/[].msgpack
def main():
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
    # simulation customer resources
