import os
import re
import base64
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from src.core import encryption

def extract_base64(user_input):
    """Extracts the base64 payload from a mongosh Binary.createFromBase64 string"""
    if "Binary.createFromBase64" in user_input:
        match = re.search(r"'(.*?)'", user_input)
        if match:
            return match.group(1)
    # Fallback: maybe they just pasted the raw base64
    return user_input.strip()

def main():
    load_dotenv()
    
    print("--- User Test 4: Cross-Collection Linkage ---")
    
    # 1. Prompt the user for the two tokens
    raw_input_1 = input("Paste the patient_token from D_patients: ").strip()
    raw_input_2 = input("Paste the patient_token from D_billing: ").strip()
    
    patients_token_b64 = extract_base64(raw_input_1)
    billing_token_b64 = extract_base64(raw_input_2)

    if not patients_token_b64 or not billing_token_b64:
        print("Invalid input!")
        return

    print(f"\nDecrypting D_patients token: {patients_token_b64[:10]}...")
    print(f"Decrypting D_billing token: {billing_token_b64[:10]}...")
    
    # 2. Derive the collection-specific token keys!
    # Because Approach D uses different keys per collection, we must derive them separately
    patients_key = encryption.derive_token_key("patients")
    billing_key = encryption.derive_token_key("billing")

    # 3. Decrypt both!
    try:
        patient_id_1 = AESSIV(patients_key).decrypt(
            base64.b64decode(patients_token_b64), None
        ).decode('utf-8')
        
        patient_id_2 = AESSIV(billing_key).decrypt(
            base64.b64decode(billing_token_b64), None
        ).decode('utf-8')
        
        print("\n--- Results ---")
        print(f"Plaintext from D_patients: {patient_id_1}")
        print(f"Plaintext from D_billing:  {patient_id_2}")
        
        if patient_id_1 == patient_id_2:
            print("\nSUCCESS! The legitimate user successfully linked the records.")
        else:
            print("\nFAILED! The records did not match.")
            
    except Exception as e:
        print(f"\nFAILED to decrypt! Error: {e}")

if __name__ == "__main__":
    main()
