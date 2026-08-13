import base64
import re
from collections import Counter
from dotenv import load_dotenv
from src.core import encryption

def main():
    load_dotenv()
    
    print("--- Attack Test 4: Payload Realism Check ---")
    print("Assume you have compromised the payload key. Paste a batch of JSON records")
    print("from mongosh (either C_lab_orders or D_lab_orders) to check their realism.")
    print("(Paste the text, then press Enter on an empty line to finish):")
    
    user_input_lines = []
    while True:
        try:
            line = input()
            if line.strip() == "" or line.strip() == "]":
                user_input_lines.append(line)
                break
            user_input_lines.append(line)
        except EOFError:
            break
            
    full_input = "\n".join(user_input_lines)
    
    # Extract payload base64 strings using regex
    pattern = r"payload:\s*Binary\.createFromBase64\('([^']+)'"
    payloads_b64 = re.findall(pattern, full_input)
    
    if not payloads_b64:
        print("No valid payloads found! Ensure your pasted text includes 'payload'.")
        return

    print(f"\nExtracted {len(payloads_b64)} payloads. Decrypting...")
    
    counts = Counter()
    
    for p_b64 in payloads_b64:
        try:
            payload_bytes = base64.b64decode(p_b64)
            decrypted_dict = encryption.decrypt_payload(payload_bytes)
            category = decrypted_dict.get("diagnostic_test_category", "UNKNOWN")
            counts[category] += 1
        except Exception as e:
            print(f"Failed to decrypt a payload: {e}")
            
    print("\n--- Decrypted Categories Frequency ---")
    for cat, count in counts.items():
        print(f"{cat}: {count} records")
        
    print("\n--- Attacker Conclusion ---")
    if len(counts) > 1:
        print("CONCLUSION: These records are scattered across multiple random hospital departments!")
        print("This is NAIVE padding (Approach C). An attacker instantly knows these are fake decoys.")
    elif len(counts) == 1:
        print(f"CONCLUSION: 100% of these records belong to the '{list(counts.keys())[0]}' department.")
        print("This is REALISTIC padding (Approach D). The attacker cannot tell which are decoys!")
    else:
        print("No categories found.")

if __name__ == "__main__":
    main()
