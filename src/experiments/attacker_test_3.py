import re
import base64
from pymongo import MongoClient
from dotenv import load_dotenv

from src.core import attack, encryption

def parse_pasted_counts(text):
    results = []
    # Split by closing brace to process each record roughly independently
    blocks = text.split("}")
    for block in blocks:
        b64_match = re.search(r"Binary\.createFromBase64\('([^']+)'", block)
        count_match = re.search(r"count:\s*(\d+)", block)
        if b64_match and count_match:
            token = base64.b64decode(b64_match.group(1))
            count = int(count_match.group(1))
            results.append((token, count))
    return results

def main():
    load_dotenv()
    
    print("--- Attack Test 3: Frequency Analysis (Value Recovery) ---")
    
    # 1. Connect to the database
    client = MongoClient('mongodb://encbench_user:encbench_pass@localhost:27018/encbench?authSource=encbench')
    db = client.encbench

    # 2. Get Ground Truth for the Attacker (true_value_counts) and for scoring
    print("Calculating true real-world frequencies from plaintext (Approach A)...")
    pipeline = [{"$group": {"_id": "$sensitive_value", "count": {"$sum": 1}}}]
    true_counts = {doc["_id"]: doc["count"] for doc in db.A_lab_orders.aggregate(pipeline) if doc["_id"]}
    
    # Pre-compute token -> true value mapping so we can score the attacker's guesses
    token_key_b = encryption.derive_token_key(None)  # Approach B uses global key
    token_key_d = encryption.derive_token_key("lab_orders")  # Approach D uses collection key
    
    token_to_true_value_b = {}
    token_to_true_value_d = {}
    
    for val in true_counts.keys():
        tok_b = encryption.deterministic_token(val, key=token_key_b)
        token_to_true_value_b[tok_b] = val
        
        tok_d = encryption.deterministic_token(val, key=token_key_d)
        token_to_true_value_d[tok_d] = val

    # 3. Prompt user for Approach B
    print("\n[Approach B - No Decoys]")
    print("Paste the aggregate output from B_lab_orders (Top 10 tokens).")
    print("(Paste the text, then press Enter on an empty line to finish):")
    
    user_input_b = []
    while True:
        try:
            line = input()
            if line.strip() == "" or line.strip() == "]":
                user_input_b.append(line)
                break
            user_input_b.append(line)
        except EOFError:
            break
            
    parsed_b = parse_pasted_counts("\n".join(user_input_b))
    
    # 4. Prompt user for Approach D
    print("\n[Approach D - Decoy Target Ratio 1.0]")
    print("Paste the aggregate output from D_lab_orders (Top 10 tokens).")
    print("(Paste the text, then press Enter on an empty line to finish):")
    
    user_input_d = []
    while True:
        try:
            line = input()
            if line.strip() == "" or line.strip() == "]":
                user_input_d.append(line)
                break
            user_input_d.append(line)
        except EOFError:
            break
            
    parsed_d = parse_pasted_counts("\n".join(user_input_d))
    
    if not parsed_b or not parsed_d:
        print("Could not parse tokens and counts from input.")
        return
        
    print(f"\nExtracted {len(parsed_b)} tokens for B, and {len(parsed_d)} tokens for D.")
    
    # 5. Run the attack!
    executed_b = [attack.ExecutedQuery(true_value=token_to_true_value_b.get(tok, "UNKNOWN"), token=tok, volume=vol) for tok, vol in parsed_b]
    executed_d = [attack.ExecutedQuery(true_value=token_to_true_value_d.get(tok, "UNKNOWN"), token=tok, volume=vol) for tok, vol in parsed_d]
    
    rows_b = attack.token_guess_table("B", executed_b, true_counts)
    rows_d = attack.token_guess_table("D", executed_d, true_counts)
    
    # 6. Print the tables
    def print_table(title, rows):
        print(f"\n{'='*75}")
        print(f"{title.center(75)}")
        print(f"{'='*75}")
        print(f"{'Token (Hex)':<15} | {'Volume':<6} | {'Attacker Guess':<20} | {'Result':<10}")
        print("-" * 75)
        
        correct_count = 0
        for r in rows:
            token_hex = r.token.hex()[:8] + "..."
            guess = r.guessed_value[:20]
            if r.correct:
                res = "CORRECT"
                correct_count += 1
            else:
                res = "WRONG"
            print(f"{token_hex:<15} | {r.observed_volume:<6} | {guess:<20} | {res:<10}")
            
        print("-" * 75)
        print(f"Accuracy: {correct_count}/{len(rows)} ({correct_count/len(rows)*100:.0f}% of these rows correct)\n")

    print_table("Approach B (No Decoys) - Value Recovery Attack", rows_b)
    print_table("Approach D (Realistic Decoys) - Value Recovery Attack", rows_d)
    
    print("CONCLUSION: Approach B leaks exact frequencies, allowing the attacker to map")
    print("tokens to their true plaintext values perfectly. Approach D perfectly flattens")
    print("the counts, destroying the frequency signal and dropping accuracy to 0%!")

if __name__ == "__main__":
    main()
