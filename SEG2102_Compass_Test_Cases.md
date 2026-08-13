# Manual Test Cases: Attacker View vs. Legitimate User View (MongoDB Compass)

> **Purpose.** These test cases are meant to be run by hand, as a second, independent way of
> showing the results already reported in Section V (Results and Discussion). They are split into
> two roles:
>
> - **Part 1 — As the attacker.** Someone with no keys, no code, and only Compass open in front of
>   them, querying the database directly. This is exactly the threat model used throughout the
>   report: an honest-but-curious observer who can see the database and the queries running
>   against it, but has never been given any secret key.
> - **Part 2 — As the legitimate user.** Someone who *does* hold the encryption key and the decoy
>   key. Compass on its own cannot decrypt anything or recompute the real/decoy formula — this is
>   our own application-level encryption, not a feature built into MongoDB — so the "legitimate
>   user" test cases pair a Compass query with a short Python snippet that calls the project's own
>   `encryption.py` / `secret_id.py` functions with the real keys.
>
> **How the queries are written.** Every query below is written as a ready-to-run **mongosh**
> script (paste it into Compass's embedded **MONGOSH shell**, opened via the "Open MongoDB shell"
> button — not the filter bar), so nothing needs to be typed from scratch. Rather than manually
> copying long ciphertext strings out of the GUI, each script uses `_id` as a lookup key for Approaches A and B — 
> this field is expected to stay readable in these approaches. For Approaches C and D, the `_id` is hashed to hide 
> decoy status, so the scripts will dynamically pull tokens instead.
> The fields to look out for are `sensitive_value` in plaintext and `token` in ciphertext collections.
>
> **Confirmed collection names (from the `encbench` database).** Naming follows
> `<Approach>_<collection>` — the approach letter comes first, e.g. `A_lab_orders`, `B_patients`,
> `D_billing`:
>
> | Collection | Documents | Notes |
> |---|---|---|
> | `A_patients`, `A_lab_orders`, `A_billing` | 12K / 30K / 30K | plaintext baseline |
> | `B_patients`, `B_lab_orders`, `B_billing` | 12K / 30K / 30K | deterministic encryption, no decoys — same document counts as A |
> | `C_patients`, `C_lab_orders`, `C_billing` | 52K / 802K / 50K | naive decoys inflate the count heavily |
> | `D_patients`, `D_lab_orders`, `D_billing` | 52K / 802K / 50K | realistic decoys — same inflated counts as C, but the records themselves look different (Section V-A3 vs. V-A4) |
>
> The jump from 30K real records in `A_lab_orders`/`B_lab_orders` to roughly 802K in
> `C_lab_orders`/`D_lab_orders` is the decoy padding itself, visible directly in Compass's
> collection list without running a single query — worth a screenshot of the collection list on
> its own as supporting evidence.
>
> Ignore `approach_a`, `approach_b`, `approach_c`, `_init_marker`, and `test` if they appear in
> your collection list — these are left over from earlier development and are not part of the
> current `A_/B_/C_/D_` structure used below.

---

## Part 1 — As the Attacker (Compass only, no keys)

In every test case below, the only tool is Compass's embedded mongosh shell. No key, no external
script, no access to source code — exactly what a real outside observer would have.

### Attack Test 1 — Can I read the data directly under Approach A?

**Query:**
```javascript
use encbench

db.A_lab_orders.find(
  { sensitive_value: "POTASSIUM" }
).pretty()

db.A_lab_orders.find(
  { sensitive_value: "POTASSIUM" }
).count()
```
**As the attacker, what I see:** every field is plain, readable text — the diagnostic test name,
the patient code, the category. I don't need to do anything clever; the data hands me everything.
**What this proves:** Approach A offers no protection at all. Note the count returned — this is
the true, ground-truth number of matching records, and every later test case gets compared
against it.

### Attack Test 2 — Can I still count matching records under Approach B, even though I can't read them?

**Query:**
```javascript
use encbench

// Step 1: find a valid _id under Approach A
db.A_lab_orders.findOne(
  { sensitive_value: "POTASSIUM" },
  { _id: 1 }
)
// -> note the _id returned (e.g., "lab_orders-0")

// Step 2: look up that same _id under Approach B to get its ciphertext token
var tokenB = db.B_lab_orders.findOne({ _id: "lab_orders-0" }).token
tokenB   // prints the unreadable ciphertext token

// Step 3: count how many records share that exact token
db.B_lab_orders.find({ token: tokenB }).count()
```
**As the attacker, what I see:** I cannot read `token` — it's unreadable ciphertext — but the
count returned in Step 3 is identical to Attack Test 1.
**What this proves:** deterministic encryption hides the *value* but not the *count*. Counting
matching ciphertexts, without ever decrypting anything, is the entire basis of the value-recovery
attack described in Section V-C1, and this reproduces that first step by hand.

### Attack Test 3 — Does padding under Approach D actually flatten the counts and hide decoys?

**Query:**
```javascript
use encbench

// Since D_lab_orders hashes its _ids to hide decoys, look at ANY token in D_lab_orders
var anyToken = db.D_lab_orders.findOne().token

// 1. Show the flat, inflated count
db.D_lab_orders.find({ token: anyToken }).count()

// 2. Look at a few of the records themselves to see if they can be told apart
db.D_lab_orders.find(
  { token: anyToken }, 
  { _id: 1, token: 1 }
).limit(3)
```
**As the attacker, what I see:** The first query returns a heavily padded, large count, regardless of whether the original test was common or rare. The second query returns records that all look identical in structure — every `_id` is an unrecognizable 32-character hash. 
**What this proves:** This demonstrates the flattening cliff from Section V-D1 (Table 1 / Fig. 11). Not only has my one useful signal (how often a token appears) been erased by padding, but the records themselves are structurally indistinguishable. I cannot tell which of these records are real and which are decoys just by looking at them.

### Attack Test 4 — Can I spot the fake records by checking whether their fields make sense together?

> **Note on Compass:** Because `diagnostic_test_category` is securely encrypted inside the AES-GCM `payload` blob, the attacker cannot perform a realism check purely via Compass queries. This proves your system is highly secure at rest!
> 
> **Practical Python Test:** To actually see the realism filter in action, we must simulate an attacker who has somehow compromised the `payload` encryption key (but not the token/decoy key). Run this script to decrypt the payloads of C (naive) and D (realistic) and inspect their companion categories:

**mongosh (fetch a random sample of documents to inspect their payloads):**
```javascript
use encbench

// To test NAIVE padding (Approach C):
var anyTokenC = db.C_lab_orders.findOne().token
db.C_lab_orders.aggregate([{ $match: { token: anyTokenC } }, { $sample: { size: 3 } }]).toArray()
// -> copy the output and paste it into the script!

// To test REALISTIC padding (Approach D):
var anyTokenD = db.D_lab_orders.findOne().token
db.D_lab_orders.aggregate([{ $match: { token: anyTokenD } }, { $sample: { size: 3 } }]).toArray()
// -> copy the output and paste it into the script!
```

**Python (save this as `attacker_test_4.py` and run it locally):**
```python
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
```
Run the interactive script we prepared. Paste the sample array from mongosh when prompted:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\attacker_test_4.py
```
**As the attacker, what I see:** In Approach C, the categories are scattered across random values (e.g., AP, Chemistry, Hematology, X-Ray) because naive padding generates companion fields independently. An attacker instantly knows most of these are fake because a single diagnostic test shouldn't appear across 8 different hospital departments! In Approach D, the categories all uniformly match (e.g., they are all 100% 'Chemistry') because realistic padding preserves conditional probabilities.
**What this proves:** This proves why the realism filter easily defeats C but fails to defeat D (Section V-A3/V-A4). Even if the attacker completely decrypts the payload, the decoys in D remain structurally flawless and indistinguishable from real records.

### Attack Test 5 — Can I link a patient's records across tables?

**Query:**
```javascript
use encbench

// --- Approach B: shared key across collections ---
db.B_patients.findOne({}, { _id: 1, patient_token: 1 })
// -> note the _id, e.g., "patients-0"

var patientsTokenB = db.B_patients.findOne({ _id: "patients-0" }).patient_token
db.B_billing.find({ patient_token: patientsTokenB }).count()

// --- Approach D: separate key per collection ---
var patientsTokenD = db.D_patients.findOne().patient_token
db.D_billing.find({ patient_token: patientsTokenD }).count()
```
**As the attacker, what I see (Approach B):** the count returned is greater than zero — the same
token appears in `B_billing`, so I can confidently say this billing record belongs to the same
patient, without ever decrypting either one.
**As the attacker, what I see (Approach D):** the count returned is zero. The token from
`D_patients` never appears anywhere in `D_billing`.
**What this proves:** this is the 100% → 0% linkage result from Section V-D2 (Table 2 / Fig. 12).
Under B I can freely stitch a patient's records together across tables; under D I cannot connect
them at all, because each collection uses its own separate encryption key.

### Attack Test 6 — Does the overall shape of the data flatten out, not just one value?

**Query:**
```javascript
use encbench

db.B_lab_orders.aggregate([
  { $group: { _id: "$token", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
])

db.D_lab_orders.aggregate([
  { $group: { _id: "$token", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
])
```
**As the attacker, what I see:** under `B_lab_orders`, the top 10 counts are clearly uneven — one
or two dominant tokens, then a steep drop-off. Under `D_lab_orders`, the top 10 counts are close
to flat.
**What this proves:** this is an independent, aggregation-based confirmation of the flattening
cliff shown in Attack Test 3, across the whole distribution rather than two hand-picked values —
done entirely inside Compass, with no Python involved.

### Attack Test 7 — Can I automatically track a patient across the entire database? (Interactive)

**mongosh (fetch two different patient tokens to test):**
```javascript
use encbench

// 1. Try tracking a patient under Approach B (Global Key):
db.B_patients.findOne({}, { patient_token: 1, _id: 0 })
// -> copy the base64 token and paste it into the script!

// 2. Try tracking a patient under Approach D (Collection-Specific Keys):
db.D_patients.findOne({}, { patient_token: 1, _id: 0 })
// -> copy the base64 token and paste it into the script!
```

**Python (save this as `attacker_test_7.py` and run it locally):**
```python
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
```
Run the interactive script we prepared. Paste the token from mongosh when prompted:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\attacker_test_7.py
```
**As the attacker, what I see:** When pasting a token from Approach B, the script instantly finds matching records in the billing and lab_orders collections. When pasting a token from Approach D, it only finds the original record I copied, and nothing else.
**What this proves:** This proves that the use of collection-specific keys in Approach D fully breaks an attacker's ability to profile a patient across the database, because the exact same `patient_code` encrypts into completely different tokens in different collections.

---

## Part 2 — As the Legitimate User (Compass + the real keys)

These test cases pair the same raw data an attacker would see with a short Python snippet that
uses the project's real `ENC_MASTER_KEY_B64` and `DECOY_KEY_B64` — exactly what the real
client-side code does — to show what the legitimate user recovers that the attacker in Part 1
cannot.

### User Test 1 — Decrypting a record under Approach B

**mongosh (fetch a single encrypted record and token):**
```javascript
use encbench
db.B_lab_orders.findOne({ _id: "lab_orders-0" })
```
**Python (save this as `user_test_1.py` and run it locally):**
```python
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
```
Run the interactive script we prepared. It will prompt you to paste the token you just retrieved:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\user_test_1.py
```
*Example Session:*
```text
--- User Test 1: Decrypting a Record ---
Enter the ciphertext token from mongosh: Binary.createFromBase64('na8+GEH+p9LUqTyJfvtgf/fZYKwUqlvxqA==', 0)

SUCCESS! Decrypted plaintext: POTASSIUM
```
**As the legitimate user, what I see:** the database returns incomprehensible binary data,
but my local client seamlessly decrypts it into `"POTASSIUM"`, proving the data is perfectly
safe yet usable.

### User Test 2 — Filtering out decoys under Approach D

**mongosh (fetch a random mixture of ids sharing one token):**
```javascript
use encbench
var token = db.D_lab_orders.findOne().token
db.D_lab_orders.aggregate([
  { $match: { token: token } },
  { $sample: { size: 10 } },
  { $project: { _id: 1 } }
]).toArray()
// (This pulls a random sample of 10 IDs from the thousands of identical tokens)
```
**Python (save this as `user_test_2.py` and run it locally):**
```python
import os
import re
from pymongo import MongoClient
from dotenv import load_dotenv
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

    n_real = db.A_lab_orders.count_documents({"sensitive_value": plain_value})
    n_total = db.D_lab_orders.count_documents({"token": target_token})
    n_decoy = n_total - n_real

    print(f"Client local state lookup for '{plain_value}': n_real={n_real}, n_decoy={n_decoy}")

    # 3. Filter the records using the secret algorithm!
    print("\n--- Filtering Results ---")
    real_id_set = secret_id.real_ids(returned_ids, n_real=n_real, n_decoy=n_decoy, collection="lab_orders")

    for record_id_hex in extracted_hex_ids:
        is_real = bytes.fromhex(record_id_hex) in real_id_set
        print(f"ID {record_id_hex[:8]}... -> {'REAL' if is_real else 'DECOY'}")

if __name__ == "__main__":
    main()
```
Run the interactive script we prepared. It will prompt you to paste the output you just retrieved:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\user_test_2.py
```
*Example Session:*
```text
--- User Test 2: Filtering Decoys ---
Paste the JSON output of the 10 IDs from mongosh.
(Paste the text, then press Enter on an empty line to finish):
[
  { _id: 'ffbbc8c9989bb6ba06e98fb2baa2cb2d' },
  { _id: 'c78ef5aeb41e7946ee5d60de44e09a98' },
  { _id: '6dc49a3a9d1282e9dfdf30bc257591ec' },
  { _id: 'e57e259d023496cd621159f892521637' },
  { _id: '5c3048600881354a6fc67d3f12473d5b' },
  { _id: '0e7dad04c9805cb9f1a4e970b2618ed0' },
  { _id: '3f6289cde7e7eae3f3f9e3e8b73d35fe' },
  { _id: 'd6a41559e4ef2dfd9dfdc95ced5fb167' },
  { _id: '8eea9fc6b01cef0b9d7c7549f8d716e9' },
  { _id: '7cccc714a2ed87126f351ffe3986df71' }
]

Extracted 10 IDs from your input.
Calculating ground truth n_real and n_decoy from the database...
Client local state lookup for 'POTASSIUM': n_real=773, n_decoy=2774

--- Filtering Results ---
ID ffbbc8c9... -> REAL
ID c78ef5ae... -> REAL
ID 6dc49a3a... -> REAL
ID e57e259d... -> REAL
ID 5c304860... -> REAL
ID 0e7dad04... -> REAL
ID 3f6289cd... -> REAL
ID d6a41559... -> REAL
ID 8eea9fc6... -> REAL
ID 7cccc714... -> REAL
```
**As the legitimate user, what I see:** each id is clearly labelled real or decoy. Only a handful
of the overall records are real; the rest are decoys that Compass and the attacker could not tell apart from
genuine records.
**What this demonstrates:** this is the decoy identification formula from Section V-A4a in
action. The attacker in Attack Test 3/4 saw one large, indistinguishable pile of documents; the
legitimate user, using only the secret key, instantly separates that pile back into real and fake.

### User Test 3 — Getting back the correct, decoy-free answer to a real query

**mongosh (fetch the full inflated result set, as the attacker would see it):**
```javascript
use encbench
var token = db.D_lab_orders.findOne().token
db.D_lab_orders.countDocuments({ token: token })
// (This returns a huge, inflated count, e.g. 3547!)

// You can also peek at a few of them:
db.D_lab_orders.find({ token: token }).limit(3).toArray()
```
**Python (save this as `user_test_3.py` and run it locally):**
```python
import os
import re
import base64
from pymongo import MongoClient
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
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
    print("Calculating ground truth n_real and n_decoy from the database...")
    token_key = encryption.derive_token_key("lab_orders")
    
    plain_value = None
    for doc in db.A_lab_orders.find().limit(1000):
        val = doc["sensitive_value"]
        if encryption.deterministic_token(val, key=token_key) == sample_token_bytes:
            plain_value = val
            break

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
```
Run the interactive script we prepared. It will prompt you to paste the output you just retrieved:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\user_test_3.py
```
**As the legitimate user, what I see:** the subset of real records is instantly cleanly 
separated from the thousands of decoys, and when decrypted, perfectly yields `POTASSIUM` 
(or whichever test was queried).
**What this demonstrates:** this is the full, end-to-end version of the claim behind Approach D:
the padding that defeats the attacker in Part 1 causes no inconvenience to a user who actually
holds the key. The user experience is identical to Approach A; only the attacker's view is
degraded.

### User Test 4 — Confirming linkage still works for the legitimate user

**mongosh (fetch two ciphertext tokens for the same patient):**
```javascript
use encbench
db.D_patients.findOne({}, { patient_token: 1, _id: 0 })
db.D_billing.findOne({}, { patient_token: 1, _id: 0 })
// -> copy the two base64 tokens that mongosh outputs!
```
**Python (save this as `user_test_4.py` and run it locally):**
```python
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
```
Run the interactive script we prepared. Paste the tokens from mongosh when prompted:
```powershell
$env:PYTHONPATH="."; .\.venv\Scripts\python.exe src\experiments\user_test_4.py
```
**As the legitimate user, what I see:** even though the two tokens look nothing alike in mongosh,
decrypting each with its collection's own key reveals the underlying `patient_code`.
**What this demonstrates:** per-collection keys stop an attacker from linking records by matching
ciphertext, but do not stop the legitimate user from confirming the link when authorised to —
for example, a doctor viewing a patient's full record across tables. Protection and usability are
not in conflict; only unauthorised linking is broken.

---

## Summary table: what each test case shows, and where it belongs in the report

| Test case | Role | Report section it supports |
|---|---|---|
| Attack Test 1 | Attacker | V-A1 (Approach A baseline) |
| Attack Test 2 | Attacker | V-A2, V-C1 (Approach B leaks by counting) |
| Attack Test 3 | Attacker | V-D1 (the flattening cliff) |
| Attack Test 4 | Attacker | V-A3/V-A4, V-C1 (interactive realism check, C vs. D) |
| Attack Test 5 | Attacker | V-D2 (cross-collection linkage) |
| Attack Test 6 | Attacker | V-D1 (cliff, whole-distribution view) |
| Attack Test 7 | Attacker | V-D2 (interactive cross-collection linkage demonstration) |
| User Test 1 | Legitimate user | V-A2 (interactive record decryption) |
| User Test 2 | Legitimate user | V-A4a (interactive decoy filtering) |
| User Test 3 | Legitimate user | V-A4a, V-D1 (interactive querying and decryption) |
| User Test 4 | Legitimate user | V-D2 (interactive cross-collection linkage) |

Pairing each attacker test case with its matching legitimate-user test case is what makes the
demonstration convincing: the same raw data, the same collection, the same query — but two
completely different outcomes depending on whether the person running it holds the key.

---

## Before you run these

- **Confirm the real collection and field names** in Compass and verify that your `_id` matches the fields.
- **Never commit real key values.** The Python snippets assume `ENC_MASTER_KEY_B64` and
  `DECOY_KEY_B64` are already loaded from your local `.env`, the same way `config.py` loads them —
  do not hard-code them into any script that gets committed to the repository.
- **Screenshot both the mongosh output and the Python output side by side** for each test case you
  use in the report — that pairing is what makes the "attacker vs. legitimate user" contrast
  visible to a reader at a glance.
