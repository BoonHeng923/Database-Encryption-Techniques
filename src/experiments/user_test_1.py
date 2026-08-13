import os
import base64
import re
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def main():
    # 1. Load the master key directly from the .env file
    load_dotenv()
    master_key_b64 = os.getenv("ENC_MASTER_KEY_B64")
    if not master_key_b64:
        raise ValueError("Missing ENC_MASTER_KEY_B64 in .env")
    master_key = base64.b64decode(master_key_b64)

    # 2. Derive the token key for Approach B (global key uses 'encbench-siv-token-key' as info)
    hkdf = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=b"encbench-siv-token-key")
    siv_key = hkdf.derive(master_key)

    # 3. Prompt the user for the ciphertext from mongosh
    print("--- User Test 1: Decrypting a Record ---")
    user_input = input("Enter the ciphertext token from mongosh: ").strip()
    
    # If the user pasted the entire "Binary.createFromBase64('...', 0)" string, extract just the base64 part
    if "Binary.createFromBase64" in user_input:
        match = re.search(r"'(.*?)'", user_input)
        if match:
            user_input = match.group(1)

    # 4. Decrypt the token
    try:
        token_bytes = base64.b64decode(user_input)
        plaintext = AESSIV(siv_key).decrypt(token_bytes, None).decode('utf-8')
        print(f"\nSUCCESS! Decrypted plaintext: {plaintext}")
    except Exception as e:
        print(f"\nFAILED to decrypt! Error: {e}")

if __name__ == "__main__":
    main()
