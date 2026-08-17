import os
import re
from pymongo import MongoClient
from dotenv import load_dotenv

# We need these to peek at the ground truth, since a real client app's local state 
# table (storing n_real and n_decoy per token) doesn't exist in this benchmark!
from src.core import secret_id, config, encryption

def main():
    load_dotenv()
    
    # 1. Connect to the database
    client = MongoClient('mongodb://encbench_user:encbench_pass@localhost:27018/encbench?authSource=encbench')
    db = client.encbench

    # 2. Prompt the user for the mongosh output
    print("--- User Test 2: Filtering Decoys ---")
    print("Paste the JSON output of the 10 IDs from mongosh.")
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
    
    # Extract all 32-character hex IDs from the pasted text
    extracted_hex_ids = re.findall(r"([0-9a-f]{32})", full_input)
    
    if not extracted_hex_ids:
        print("No valid 32-character hex IDs found in input!")
        return

    print(f"\nExtracted {len(extracted_hex_ids)} IDs from your input.")
    
    # Parse them to bytes for the crypto function
    returned_ids = [bytes.fromhex(hx) for hx in extracted_hex_ids]

    # Find the token for these IDs so we can calculate the ground truth n_real/n_decoy
    sample_doc = db.D_lab_orders.find_one({"_id": extracted_hex_ids[0]})
    if not sample_doc:
        print(f"Could not find ID {extracted_hex_ids[0]} in the database.")
        return
        
    target_token = sample_doc["token"]

    # --- SIMULATING THE CLIENT STATE ---
    # In a real deployment, the client queries its local state to get `n_real` and `n_decoy`.
    # Since we don't have that client database, we will dynamically calculate it 
    # by querying the plaintext table (Approach A) as our source of ground truth!
    print("Calculating ground truth n_real and n_decoy from the database...")

    token_key = encryption.derive_token_key("lab_orders")
    plain_value = None
    for doc in db.A_lab_orders.find().limit(1000):
        val = doc["sensitive_value"]
        if encryption.deterministic_token(val, key=token_key) == target_token:
            plain_value = val
            break

    if not plain_value:
        print("Could not find plaintext for token in the first 1000 records. Please run again.")
        return

    n_real = db.A_lab_orders.count_documents({"sensitive_value": plain_value})
    n_total = db.D_lab_orders.count_documents({"token": target_token})
    n_decoy = n_total - n_real

    print(f"Client local state lookup for '{plain_value}': n_real={n_real}, n_decoy={n_decoy}")

    # 3. Attacker Attempt (Without the Real Key)
    print("\n--- Attacker Attempt (Guessing the Key) ---")
    # Save the original key to restore later
    original_decoy_key = config.DECOY_MASTER_KEY
    
    # Attacker guesses a random 32-byte key
    config.DECOY_MASTER_KEY = os.urandom(32)
    fake_real_id_set = secret_id.real_ids(returned_ids, n_real=n_real, n_decoy=n_decoy, collection="lab_orders")
    
    attacker_found_real = 0
    for record_id_hex in extracted_hex_ids:
        is_real = bytes.fromhex(record_id_hex) in fake_real_id_set
        print(f"ID {record_id_hex[:8]}... -> {'REAL' if is_real else 'DECOY'}")
        if is_real: 
            attacker_found_real += 1
            
    print(f"Attacker Conclusion: Identified {attacker_found_real} real records.")
    print("(Because the attacker doesn't hold the true key, the formula outputs random noise that matches nothing!)")

    # 4. Legitimate User Attempt (With the Real Key)
    print("\n--- Legitimate User Attempt (With the Real Key) ---")
    # Restore the real key!
    config.DECOY_MASTER_KEY = original_decoy_key
    
    true_real_id_set = secret_id.real_ids(returned_ids, n_real=n_real, n_decoy=n_decoy, collection="lab_orders")

    legit_found_real = 0
    for record_id_hex in extracted_hex_ids:
        is_real = bytes.fromhex(record_id_hex) in true_real_id_set
        print(f"ID {record_id_hex[:8]}... -> {'REAL' if is_real else 'DECOY'}")
        if is_real: 
            legit_found_real += 1

if __name__ == "__main__":
    main()
