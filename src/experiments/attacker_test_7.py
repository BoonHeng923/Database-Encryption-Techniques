import re
import base64
from pymongo import MongoClient

def extract_base64(user_input):
    if "Binary.createFromBase64" in user_input:
        match = re.search(r"'(.*?)'", user_input)
        if match:
            return match.group(1)
    return user_input.strip()

def main():
    print("--- Attack Test 7: Interactive Cross-Collection Linkage ---")
    print("As an attacker, you want to track a patient across all hospital departments.")
    print("Paste a patient_token from mongosh (e.g., from B_patients or D_patients):")
    
    raw_input = input().strip()
    token_b64 = extract_base64(raw_input)
    
    if not token_b64:
        print("Invalid input!")
        return
        
    try:
        token_bytes = base64.b64decode(token_b64)
    except:
        print("Failed to parse base64.")
        return

    client = MongoClient('mongodb://encbench_user:encbench_pass@localhost:27018/encbench?authSource=encbench')
    db = client.encbench
    
    print("\n[Attacker Tool] Searching the entire database for this exact token...")
    
    collections_to_search = [
        "B_patients", "B_billing", "B_lab_orders",
        "D_patients", "D_billing", "D_lab_orders"
    ]
    
    matches = {}
    for coll in collections_to_search:
        count = db[coll].count_documents({"patient_token": token_bytes})
        if count > 0:
            matches[coll] = count
            print(f" -> FOUND {count} match(es) in {coll}!")
            
    print("\n--- Attacker Conclusion ---")
    if len(matches) > 1:
        print("CONCLUSION: You successfully linked this patient's identity across multiple tables!")
        print("This proves the fatal flaw of Approach B (Global Deterministic Encryption).")
    elif len(matches) == 1:
        coll_found = list(matches.keys())[0]
        print(f"CONCLUSION: The token was only found in {coll_found}.")
        print("ZERO matches were found in any other table.")
        print("This proves Approach D (Collection-Specific Keys) successfully stopped you from linking records!")
    else:
        print("CONCLUSION: Token not found anywhere in the database.")

if __name__ == "__main__":
    main()
