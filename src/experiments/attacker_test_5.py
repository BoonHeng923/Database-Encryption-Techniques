import re
import base64
from pymongo import MongoClient
from dotenv import load_dotenv

from src.core import encryption

def extract_patient_codes(text):
    # Extract numbers that look like patient codes (e.g. 29949, 37777)
    codes = []
    lines = text.split('\n')
    for line in lines:
        match = re.search(r"patient_value:\s*'?(\d+)'?", line)
        if match:
            codes.append(match.group(1))
    return codes

def main():
    load_dotenv()
    
    print("--- Attack Test 5: Cross-Collection Linkage Table ---")
    
    # 1. Connect to the database
    client = MongoClient('mongodb://encbench_user:encbench_pass@localhost:27018/encbench?authSource=encbench')
    db = client.encbench

    # 2. Prompt user for 5 patient codes
    print("Paste the 5 patient codes from A_patients.")
    print("(Paste the text, then press Enter on an empty line to finish):")
    
    user_input = []
    while True:
        try:
            line = input()
            if line.strip() == "" or line.strip() == "]":
                user_input.append(line)
                break
            user_input.append(line)
        except EOFError:
            break
            
    patient_codes = extract_patient_codes("\n".join(user_input))
    
    if not patient_codes:
        print("Could not parse patient_codes from input.")
        return
        
    print(f"\nExtracted {len(patient_codes)} patient codes.")
    
    # Generate the tokens dynamically based on the keys!
    global_key = encryption.derive_token_key(None)
    patients_d_key = encryption.derive_token_key("patients")
    billing_d_key = encryption.derive_token_key("billing")
    
    print(f"\n{'='*130}")
    print(f"{'patient_code':<12} | {'patients token (B)':<20} | {'billing token (B)':<20} | {'verdict (B)':<15} | {'patients token (D)':<20} | {'billing token (D)':<20} | {'verdict (D)':<15}")
    print("-" * 130)
    
    b_linked = 0
    d_linked = 0
    
    for code in patient_codes:
        # Approach B uses the exact same global key for everything
        token_b_patients = encryption.deterministic_token(code, key=global_key)
        token_b_billing = encryption.deterministic_token(code, key=global_key)
        
        # Approach D uses completely different keys per collection
        token_d_patients = encryption.deterministic_token(code, key=patients_d_key)
        token_d_billing = encryption.deterministic_token(code, key=billing_d_key)
        
        # Determine verdict
        verdict_b = "LINKED" if token_b_patients == token_b_billing else "not linked"
        verdict_d = "LINKED" if token_d_patients == token_d_billing else "not linked"
        
        if verdict_b == "LINKED": b_linked += 1
        if verdict_d == "LINKED": d_linked += 1
        
        print(f"{code:<12} | {token_b_patients.hex()[:10]}...{' '*7} | {token_b_billing.hex()[:10]}...{' '*7} | {verdict_b:<15} | {token_d_patients.hex()[:10]}...{' '*7} | {token_d_billing.hex()[:10]}...{' '*7} | {verdict_d:<15}")
        
    print("-" * 130)
    print(f"The attacker's only signal is whether the same patient's token is identical across collections.")
    print(f"Measured across these patients: B links {b_linked/len(patient_codes)*100:.0f}%, D links {d_linked/len(patient_codes)*100:.0f}%.")

if __name__ == "__main__":
    main()
