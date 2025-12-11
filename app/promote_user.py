import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.utils.mongodb import get_db

def promote_to_instructor(email):
    app = create_app()
    with app.app_context():
        _, db = get_db()
        users_col = db['users']
        
        user = users_col.find_one({"email": email})
        
        if not user:
            print(f"Error: User with email '{email}' not found.")
            return

        result = users_col.update_one(
            {"email": email},
            {"$set": {"role": "instructor"}}
        )
        
        if result.modified_count > 0:
            print(f"✅ Success: User '{email}' has been promoted to instructor.")
        else:
            print(f"⚠️ Warning: User '{email}' is already an instructor or no change made.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python promote_user.py <email>")
    else:
        email_input = sys.argv[1]
        promote_to_instructor(email_input)