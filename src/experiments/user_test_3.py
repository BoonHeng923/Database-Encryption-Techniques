import os
import re
import base64
from pymongo import MongoClient
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

# (Workaround imports to peek at the ground truth for n_real and n_decoy)
from src.core import secret_id, config, encryption

def main():
    load_dotenv()
    master_key = base64.b64decode(os.getenv("ENC_MASTER_KEY_B64"))
    
    # 1. Connect to the database
    client = MongoClient('mongodb://encbench_user:encbench_pass@localhost:27018/encbench?authSource=encbench')
    db = client.encbench

    # 2. Prompt the user for the mongosh output
    print("--- User Test 3: Filtering and Decrypting ---")
    print("Paste the JSON output from mongosh (must include _id and token).")
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
    
    # Extract _id and token base64 strings using regex
    pattern = r"_id:\s*'([0-9a-f]{32})'.*?token:\s*Binary\.createFromBase64\('([^']+)'"
    extracted_records = re.findall(pattern, full_input, re.DOTALL)
    
    if not extracted_records:
        print("No valid records found! Ensure your pasted text includes both '_id' and 'token'.")
        return

    print(f"\nExtracted {len(extracted_records)} records from your input.")
    
    returned_ids = [bytes.fromhex(rec[0]) for rec in extracted_records]
    
    # We grab the first token to figure out what the ground truth stats are
    sample_token_bytes = base64.b64decode(extracted_records[0][1])

    # --- SIMULATING THE CLIENT STATE ---
    # In a real deployment, the client queries its local state to get `n_real` and `n_decoy`.
    # Since we don't have that client database, we will dynamically calculate it 
    # by querying the plaintext table (Approach A) as our source of ground truth!
    print("Calculating ground truth n_real and n_decoy from the database...")
    token_key = encryption.derive_token_key("lab_orders")
    
    plain_value = None
    for doc in db.A_lab_orders.find().limit(1000):
        val = doc["sensitive_value"]
        if encryption.deterministic_token(val, key=token_key) == sample_token_bytes:
            plain_value = val
            break

    if not plain_value:
        print("Could not find plaintext for token in the first 1000 records. Please run again.")
        return

    n_real = db.A_lab_orders.count_documents({"sensitive_value": plain_value})
    n_total = db.D_lab_orders.count_documents({"token": sample_token_bytes})
    n_decoy = n_total - n_real

    print(f"Client local state lookup for '{plain_value}': n_real={n_real}, n_decoy={n_decoy}")

    # 3. Filter the records
    real_id_set = secret_id.real_ids(returned_ids, n_real=n_real, n_decoy=n_decoy, collection="lab_orders")
    
    real_records = []
    for rec_id_hex, token_b64 in extracted_records:
        if bytes.fromhex(rec_id_hex) in real_id_set:
            real_records.append((rec_id_hex, token_b64))
            
    print(f"\nAfter filtering, {len(real_records)} records are real.")

    # 4. Decrypt the token for the real records
    # Approach D uses collection-specific keys, so the HKDF info is 'encbench-siv-lab_orders'
    hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=b"encbench-siv-lab_orders")
    siv_key = hkdf.derive(master_key)

    if real_records:
        first_real_token_bytes = base64.b64decode(real_records[0][1])
        try:
            plaintext = AESSIV(siv_key).decrypt(first_real_token_bytes, None).decode('utf-8')
            print(f"Decrypted value of the first real record: {plaintext}")
        except Exception as e:
            print(f"Failed to decrypt! Error: {e}")

if __name__ == "__main__":
    main()
